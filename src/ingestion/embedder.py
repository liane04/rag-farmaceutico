"""
Geração de embeddings com Gemini Embedding 2 (Google).

Usa a integração LangChain-Google-GenAI para gerar embeddings
dos chunks de texto farmacêutico.

task_type="RETRIEVAL_DOCUMENT" para indexação;
task_type="RETRIEVAL_QUERY" para queries (usado no pipeline de consulta).
"""

import time

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.config import GOOGLE_API_KEY, EMBEDDING_MODEL
from src.ingestion.chunker import Chunk


# Tamanho do lote para chamadas à API (evita rate limiting)
BATCH_SIZE = 50
# Pausa entre lotes (segundos)
DELAY_ENTRE_LOTES = 1.0


def criar_embedder(task_type: str = "RETRIEVAL_DOCUMENT") -> GoogleGenerativeAIEmbeddings:
    """
    Cria uma instância do modelo de embedding Gemini.

    Args:
        task_type: "RETRIEVAL_DOCUMENT" para indexação,
                   "RETRIEVAL_QUERY" para queries em tempo real.
    """
    return GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
        google_api_key=GOOGLE_API_KEY,
        task_type=task_type,
    )


def gerar_embeddings(
    chunks: list[Chunk],
    embedder: GoogleGenerativeAIEmbeddings | None = None,
) -> list[tuple[Chunk, list[float]]]:
    """
    Gera embeddings para uma lista de chunks.

    Processa em lotes para respeitar os rate limits da API do Google.

    Args:
        chunks: Lista de chunks a embeber.
        embedder: Instância do modelo (criada automaticamente se None).

    Returns:
        Lista de (Chunk, vetor_embedding) na mesma ordem dos chunks de entrada.
    """
    if embedder is None:
        embedder = criar_embedder()

    resultados: list[tuple[Chunk, list[float]]] = []
    total = len(chunks)

    for i in range(0, total, BATCH_SIZE):
        lote = chunks[i : i + BATCH_SIZE]
        textos = [c.texto for c in lote]

        print(f"[embedder] Lote {i // BATCH_SIZE + 1} / {-(-total // BATCH_SIZE)} "
              f"({len(lote)} chunks)")

        vetores = embedder.embed_documents(textos)

        for chunk, vetor in zip(lote, vetores):
            resultados.append((chunk, vetor))

        # Pausa entre lotes (exceto no último)
        if i + BATCH_SIZE < total:
            time.sleep(DELAY_ENTRE_LOTES)

    return resultados


def gerar_embedding_query(
    query: str,
    embedder: GoogleGenerativeAIEmbeddings | None = None,
) -> list[float]:
    """
    Gera o embedding de uma query para recuperação.

    Args:
        query: Texto da pergunta do utilizador.
        embedder: Instância do modelo configurada para RETRIEVAL_QUERY.

    Returns:
        Vetor de embedding da query.
    """
    if embedder is None:
        embedder = criar_embedder(task_type="RETRIEVAL_QUERY")
    return embedder.embed_query(query)
