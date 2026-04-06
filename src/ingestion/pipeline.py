"""
Pipeline de ingestão completo.

Orquestra as 4 etapas sequenciais:
  1. Carregar PDFs (loader)
  2. Chunking com metadados (chunker)
  3. Gerar embeddings Gemini (embedder)
  4. Indexar no Qdrant (indexer)

Uso:
    python -m src.ingestion.pipeline --pasta data/documents
    python -m src.ingestion.pipeline --ficheiro data/documents/bula_exemplo.pdf --tipo bula
"""

import argparse
import time
from pathlib import Path

from src.ingestion.chunker import chunkar_documento, chunkar_documentos
from src.ingestion.embedder import criar_embedder, gerar_embeddings
from src.ingestion.indexer import contar_pontos, criar_cliente, indexar_chunks
from src.ingestion.loader import carregar_pasta, carregar_pdf

# Mapeamento padrão de nomes de ficheiro para tipo de documento.
# Pode ser expandido conforme os documentos disponíveis.
TIPOS_PADRAO: dict[str, str] = {
    # ex: "bula_paracetamol.pdf": "bula"
}


def correr_pipeline_pasta(
    pasta: str | Path,
    mapeamento_tipos: dict[str, str] | None = None,
) -> None:
    """
    Corre o pipeline de ingestão para todos os PDFs numa pasta.

    Args:
        pasta: Diretório com os ficheiros PDF.
        mapeamento_tipos: {nome_ficheiro: tipo_documento}.
    """
    inicio = time.time()
    mapeamento = {**TIPOS_PADRAO, **(mapeamento_tipos or {})}

    print("\n=== PIPELINE DE INGESTÃO ===")
    print(f"Pasta: {pasta}\n")

    # 1. Carregar
    print("-- Etapa 1: Carregamento de PDFs --")
    documentos = carregar_pasta(pasta, mapeamento)
    print(f"   {len(documentos)} documento(s) carregado(s)\n")

    if not documentos:
        print("Nenhum PDF encontrado. A terminar.")
        return

    # 2. Chunking
    print("-- Etapa 2: Chunking --")
    chunks = chunkar_documentos(documentos)
    print(f"   {len(chunks)} chunk(s) gerado(s)\n")

    # 3. Embeddings
    print("-- Etapa 3: Geração de embeddings (Gemini) --")
    embedder = criar_embedder()
    pares = gerar_embeddings(chunks, embedder)
    print(f"   {len(pares)} embedding(s) gerado(s)\n")

    # 4. Indexação
    print("-- Etapa 4: Indexação no Qdrant --")
    cliente = criar_cliente()
    total = indexar_chunks(pares, cliente)
    total_na_collection = contar_pontos(cliente)
    print(f"   {total} ponto(s) indexado(s)")
    print(f"   Total na collection: {total_na_collection}\n")

    duracao = time.time() - inicio
    print(f"=== Pipeline concluído em {duracao:.1f}s ===\n")


def correr_pipeline_ficheiro(
    caminho: str | Path,
    tipo_documento: str = "desconhecido",
) -> None:
    """
    Corre o pipeline de ingestão para um único ficheiro PDF.
    """
    inicio = time.time()
    print(f"\n=== PIPELINE DE INGESTÃO — {Path(caminho).name} ===\n")

    # 1. Carregar
    print("-- Etapa 1: Carregamento --")
    doc = carregar_pdf(caminho, tipo_documento)
    print(f"   {doc.total_paginas} página(s)\n")

    # 2. Chunking
    print("-- Etapa 2: Chunking --")
    chunks = chunkar_documento(doc)
    print(f"   {len(chunks)} chunk(s)\n")

    # 3. Embeddings
    print("-- Etapa 3: Embeddings --")
    embedder = criar_embedder()
    pares = gerar_embeddings(chunks, embedder)
    print(f"   {len(pares)} embeddings\n")

    # 4. Indexação
    print("-- Etapa 4: Indexação --")
    cliente = criar_cliente()
    total = indexar_chunks(pares, cliente)
    print(f"   {total} ponto(s) indexado(s)\n")

    duracao = time.time() - inicio
    print(f"=== Concluído em {duracao:.1f}s ===\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de ingestão RAG farmacêutico")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--pasta", type=str, help="Pasta com PDFs a ingerir")
    grupo.add_argument("--ficheiro", type=str, help="Ficheiro PDF a ingerir")
    parser.add_argument(
        "--tipo",
        type=str,
        default="desconhecido",
        help="Tipo do documento (bula, monografia, guideline, ...)",
    )
    args = parser.parse_args()

    if args.pasta:
        correr_pipeline_pasta(args.pasta)
    else:
        correr_pipeline_ficheiro(args.ficheiro, args.tipo)
