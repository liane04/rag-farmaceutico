"""
Chunking de documentos farmacêuticos.

Divide o texto extraído em chunks de tamanho configurável com overlap,
preservando os metadados necessários para rastreabilidade (RF09, AI Act Art. 13).

Usa RecursiveCharacterTextSplitter do LangChain com separadores adaptados
ao formato de documentos farmacêuticos em português.
"""

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import CHUNK_SIZE, CHUNK_OVERLAP
from src.ingestion.loader import DocumentoExtraido


@dataclass
class Chunk:
    """Representa um fragmento de texto pronto para embedding."""
    texto: str
    metadados: dict
    # metadados esperados:
    #   ficheiro, tipo_documento, pagina, chunk_index, tem_tabela


def _construir_texto_pagina(pagina: dict) -> str:
    """
    Combina o texto corrido com as tabelas da página num único bloco.
    As tabelas são inseridas a seguir ao texto com um separador visual.
    """
    partes = [pagina["texto"]]
    for i, tabela in enumerate(pagina.get("tabelas", []), start=1):
        if tabela.strip():
            partes.append(f"\n[TABELA {i}]\n{tabela}\n[/TABELA]")
    return "\n".join(partes).strip()


def chunkar_documento(
    documento: DocumentoExtraido,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """
    Divide um DocumentoExtraido em chunks com metadados completos.

    Estratégia:
    1. Constrói um bloco de texto por página (texto + tabelas)
    2. Aplica RecursiveCharacterTextSplitter ao bloco de cada página
    3. Associa metadados de rastreabilidade a cada chunk

    Args:
        documento: Documento carregado pelo loader.
        chunk_size: Tamanho máximo de cada chunk (em caracteres — aprox. tokens).
        chunk_overlap: Sobreposição entre chunks consecutivos.

    Returns:
        Lista de Chunk ordenados por página e posição.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n",    # parágrafos
            "\n",      # linhas
            ". ",      # frases
            ", ",
            " ",
            "",
        ],
    )

    chunks: list[Chunk] = []
    chunk_index = 0

    for pagina in documento.paginas:
        texto_pagina = _construir_texto_pagina(pagina)
        if not texto_pagina:
            continue

        tem_tabela = bool(pagina.get("tabelas"))
        fragmentos = splitter.split_text(texto_pagina)

        for fragmento in fragmentos:
            if not fragmento.strip():
                continue
            chunks.append(Chunk(
                texto=fragmento,
                metadados={
                    "ficheiro": documento.ficheiro,
                    "tipo_documento": documento.tipo_documento,
                    "pagina": pagina["numero"],
                    "chunk_index": chunk_index,
                    "tem_tabela": tem_tabela,
                },
            ))
            chunk_index += 1

    return chunks


def chunkar_documentos(
    documentos: list[DocumentoExtraido],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """
    Chunkifica uma lista de documentos.

    Returns:
        Lista concatenada de todos os chunks, mantendo a ordem dos documentos.
    """
    todos_chunks: list[Chunk] = []
    for doc in documentos:
        chunks = chunkar_documento(doc, chunk_size, chunk_overlap)
        todos_chunks.extend(chunks)
        print(f"[chunker] {doc.ficheiro} → {len(chunks)} chunks")
    return todos_chunks
