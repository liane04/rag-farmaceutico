"""
Recuperacao hibrida no Qdrant (densa + esparsa).

Combina pesquisa semantica (vetores densos Gemini) com pesquisa por
palavras-chave (vetores esparsos BM25-like) para maximizar o recall (RF03).

O Qdrant faz a fusao dos resultados internamente via Reciprocal Rank Fusion.
"""

from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Prefetch,
    FusionQuery,
    Fusion,
    Filter,
    FieldCondition,
    MatchValue,
)

from src.config import QDRANT_COLLECTION, RETRIEVAL_TOP_K
from src.ingestion.embedder import criar_embedder, gerar_embedding_query
from src.ingestion.indexer import criar_cliente, VETOR_DENSO, VETOR_ESPARSO, _texto_para_sparse


@dataclass
class ChunkRecuperado:
    """Resultado de uma recuperacao no Qdrant."""
    texto: str
    metadados: dict       # ficheiro, tipo_documento, pagina, chunk_index, tem_tabela
    score: float          # score combinado (RRF)
    ponto_id: str         # ID do ponto no Qdrant


def recuperar(
    query: str,
    top_k: int = RETRIEVAL_TOP_K,
    tipo_documento: str | None = None,
    cliente: QdrantClient | None = None,
) -> list[ChunkRecuperado]:
    """
    Recupera os chunks mais relevantes para uma query usando pesquisa hibrida.

    Pipeline:
    1. Gera embedding denso da query (Gemini, RETRIEVAL_QUERY)
    2. Gera vetor esparso da query (BM25-like)
    3. Envia ambos ao Qdrant com fusao RRF
    4. Opcionalmente filtra por tipo_documento

    Args:
        query: Pergunta do utilizador em linguagem natural.
        top_k: Numero de resultados a devolver (default: 10).
        tipo_documento: Filtro opcional ("bula", "monografia", "guideline", "norma").
        cliente: Cliente Qdrant (criado automaticamente se None).

    Returns:
        Lista de ChunkRecuperado ordenados por relevancia (score decrescente).
    """
    if cliente is None:
        cliente = criar_cliente()

    # 1. Embedding denso da query
    embedder_query = criar_embedder(task_type="RETRIEVAL_QUERY")
    vetor_denso = gerar_embedding_query(query, embedder_query)

    # 2. Vetor esparso da query
    vetor_esparso = _texto_para_sparse(query)

    # 3. Filtro por tipo de documento (opcional)
    filtro = None
    if tipo_documento:
        filtro = Filter(
            must=[
                FieldCondition(
                    key="tipo_documento",
                    match=MatchValue(value=tipo_documento),
                )
            ]
        )

    # 4. Pesquisa hibrida com fusao RRF
    resultados = cliente.query_points(
        collection_name=QDRANT_COLLECTION,
        prefetch=[
            # Pesquisa densa (semantica)
            Prefetch(
                query=vetor_denso,
                using=VETOR_DENSO,
                limit=top_k,
                filter=filtro,
            ),
            # Pesquisa esparsa (keywords)
            Prefetch(
                query=vetor_esparso,
                using=VETOR_ESPARSO,
                limit=top_k,
                filter=filtro,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
    )

    # 5. Converter resultados
    chunks_recuperados = []
    for ponto in resultados.points:
        payload = ponto.payload
        chunks_recuperados.append(ChunkRecuperado(
            texto=payload.pop("texto"),
            metadados=payload,
            score=ponto.score,
            ponto_id=str(ponto.id),
        ))

    return chunks_recuperados
