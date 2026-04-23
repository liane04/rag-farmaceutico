"""
Geração de embeddings com Gemini Embedding 2 Preview (Google).

Usa a integração LangChain-Google-GenAI para gerar embeddings
dos chunks de texto farmacêutico.

task_type="RETRIEVAL_DOCUMENT" para indexação;
task_type="RETRIEVAL_QUERY" para queries (usado no pipeline de consulta).
"""

import time

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.config import GOOGLE_API_KEY, EMBEDDING_MODEL
from src.ingestion.chunker import Chunk


# Lote pequeno para o gemini-embedding-2-preview (limites mais restritivos)
BATCH_SIZE = 5
# Pausa entre lotes (segundos)
DELAY_ENTRE_LOTES = 1.0
# Retries com backoff exponencial
MAX_RETRIES = 3


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


def _embeber_individual(chunks: list[Chunk], embedder: GoogleGenerativeAIEmbeddings) -> list[tuple[Chunk, list[float]]]:
    """
    Fallback: embebe chunks um a um quando o modo batch falha.
    """
    resultados = []
    for i, chunk in enumerate(chunks):
        for tentativa in range(MAX_RETRIES):
            try:
                vetor = embedder.embed_query(chunk.texto)
                resultados.append((chunk, vetor))
                break
            except Exception as e:
                wait_time = DELAY_ENTRE_LOTES * (2 ** tentativa)
                print(f"[embedder] Erro individual chunk (tentativa {tentativa + 1}/{MAX_RETRIES}): {e}")
                if tentativa < MAX_RETRIES - 1:
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(
                        f"[embedder] Falha após {MAX_RETRIES} tentativas: {e}"
                    )
        if i < len(chunks) - 1:
            time.sleep(0.3)
    return resultados


def gerar_embeddings(
    chunks: list[Chunk],
    embedder: GoogleGenerativeAIEmbeddings | None = None,
) -> list[tuple[Chunk, list[float]]]:
    """
    Gera embeddings para uma lista de chunks.

    Estratégia: lotes pequenos (5 chunks) via embed_documents().
    Se um lote falhar ou devolver número errado de embeddings,
    faz fallback para processamento individual desse lote.

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
    total_lotes = -(-total // BATCH_SIZE)  # ceil division

    for i in range(0, total, BATCH_SIZE):
        lote = chunks[i : i + BATCH_SIZE]
        textos = [c.texto for c in lote]
        num_lote = i // BATCH_SIZE + 1

        print(f"[embedder] Lote {num_lote}/{total_lotes} "
              f"({len(lote)} chunks)")

        sucesso = False
        for tentativa in range(MAX_RETRIES):
            try:
                vetores = embedder.embed_documents(textos)

                if len(vetores) != len(lote):
                    print(f"[embedder] Lote {num_lote}: API devolveu {len(vetores)}/{len(lote)} "
                          f"embeddings — fallback para individual")
                    break  # vai para fallback individual
                
                for chunk, vetor in zip(lote, vetores):
                    resultados.append((chunk, vetor))
                sucesso = True
                break

            except Exception as e:
                wait_time = DELAY_ENTRE_LOTES * (2 ** tentativa)
                print(f"[embedder] Erro lote {num_lote} (tentativa {tentativa + 1}/{MAX_RETRIES}): {e}")
                if tentativa < MAX_RETRIES - 1:
                    time.sleep(wait_time)

        # Fallback: processar este lote individualmente
        if not sucesso:
            print(f"[embedder] Lote {num_lote}: a processar {len(lote)} chunks individualmente...")
            pares_individuais = _embeber_individual(lote, embedder)
            resultados.extend(pares_individuais)

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
