"""
Indexação de chunks e respetivos embeddings no Qdrant.

Cria (ou reutiliza) uma collection no Qdrant com:
- Indexação vetorial densa (Gemini Embedding 2)
- Indexação esparsa BM25 para recuperação híbrida
- Metadados armazenados como payload para filtragem

A recuperação híbrida (densa + esparsa) é configurada na collection
para suportar o pipeline de consulta (RF03).
"""

import hashlib
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from src.config import (
    EMBEDDING_DIMENSION,
    QDRANT_COLLECTION,
    QDRANT_HOST,
    QDRANT_PORT,
)
from src.ingestion.chunker import Chunk


# Nome do vetor denso e esparso dentro da collection
VETOR_DENSO = "dense"
VETOR_ESPARSO = "sparse"


def criar_cliente() -> QdrantClient:
    """Cria e devolve um cliente Qdrant."""
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def garantir_collection(cliente: QdrantClient, nome: str = QDRANT_COLLECTION) -> None:
    """
    Cria a collection se ainda não existir.
    Configura vetores densos (Cosine) e esparsos (BM25) para recuperação híbrida.
    """
    collections_existentes = [c.name for c in cliente.get_collections().collections]
    if nome in collections_existentes:
        print(f"[indexer] Collection '{nome}' já existe — a reutilizar.")
        return

    cliente.create_collection(
        collection_name=nome,
        vectors_config={
            VETOR_DENSO: VectorParams(
                size=EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            VETOR_ESPARSO: SparseVectorParams(
                index=SparseIndexParams(on_disk=False),
            ),
        },
    )
    print(f"[indexer] Collection '{nome}' criada com sucesso.")


def _texto_para_sparse(texto: str) -> SparseVector:
    """
    Representação esparsa simples baseada em frequência de termos (BM25-like).
    Produz SparseVector com {indice_token: frequencia} para os tokens do texto.

    Usa hashlib (determinístico) em vez de hash() (randomizado por defeito
    em Python ≥3.3 via PYTHONHASHSEED), garantindo consistência entre
    indexação e consulta.

    Colisões de hash são resolvidas por soma dos pesos, garantindo índices únicos.

    Nota: para produção, substituir por um tokenizador BM25 dedicado (ex: rank_bm25).
    """
    import hashlib
    from collections import Counter

    tokens = texto.lower().split()
    contagem = Counter(tokens)

    # Agrega pesos por índice — resolve colisões somando as frequências
    agregado: dict[int, float] = {}
    for token, freq in contagem.items():
        idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % 100_000
        agregado[idx] = agregado.get(idx, 0.0) + float(freq)

    return SparseVector(indices=list(agregado.keys()), values=list(agregado.values()))


def indexar_chunks(
    pares: list[tuple[Chunk, list[float]]],
    cliente: QdrantClient | None = None,
    nome_collection: str = QDRANT_COLLECTION,
    tamanho_lote: int = 100,
) -> int:
    """
    Indexa chunks no Qdrant com vetores densos e esparsos.

    Args:
        pares: Lista de (Chunk, vetor_denso) gerada pelo embedder.
        cliente: Cliente Qdrant (criado automaticamente se None).
        nome_collection: Nome da collection de destino.
        tamanho_lote: Número de pontos enviados por lote (performance).

    Returns:
        Número total de pontos indexados.
    """
    if cliente is None:
        cliente = criar_cliente()

    garantir_collection(cliente, nome_collection)

    pontos: list[PointStruct] = []

    for chunk, vetor_denso in pares:
        sparse = _texto_para_sparse(chunk.texto)

        # ID determinístico: mesmo chunk gera sempre o mesmo ID.
        # Permite re-ingestão sem duplicados (upsert sobrepõe).
        chave = f"{chunk.metadados['ficheiro']}:{chunk.metadados['pagina']}:{chunk.metadados['chunk_index']}"
        ponto_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chave))

        pontos.append(PointStruct(
            id=ponto_id,
            vector={
                VETOR_DENSO: vetor_denso,
                VETOR_ESPARSO: sparse,
            },
            payload={
                "texto": chunk.texto,
                **chunk.metadados,
            },
        ))

    # Envio em lotes
    total = len(pontos)
    for i in range(0, total, tamanho_lote):
        lote = pontos[i : i + tamanho_lote]
        cliente.upsert(collection_name=nome_collection, points=lote)
        print(f"[indexer] Indexados {min(i + tamanho_lote, total)}/{total} pontos")

    return total


def contar_pontos(
    cliente: QdrantClient | None = None,
    nome_collection: str = QDRANT_COLLECTION,
) -> int:
    """Devolve o número de pontos indexados na collection."""
    if cliente is None:
        cliente = criar_cliente()
    info = cliente.get_collection(nome_collection)
    return info.points_count
