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


def _encontrar_paginas(inicio_chunk: int, fim_chunk: int, segmentos: list[dict]) -> dict:
    """
    Dado o intervalo [inicio_chunk, fim_chunk) no texto completo,
    determina quais páginas o chunk abrange e se contém tabelas.

    Returns:
        dict com 'pagina' (primeira), 'paginas' (lista), 'tem_tabela' (bool).
    """
    paginas = []
    tem_tabela = False
    for seg in segmentos:
        # Verifica se o chunk se sobrepõe a este segmento de página
        if inicio_chunk < seg["fim"] and fim_chunk > seg["inicio"]:
            paginas.append(seg["numero"])
            if seg["tem_tabela"]:
                tem_tabela = True
    return {
        "pagina": paginas[0] if paginas else 1,
        "paginas": paginas,
        "tem_tabela": tem_tabela,
    }


def chunkar_documento(
    documento: DocumentoExtraido,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """
    Divide um DocumentoExtraido em chunks com metadados completos.

    Estratégia cross-page:
    1. Constrói o texto de cada página (texto + tabelas)
    2. Concatena TODAS as páginas num texto contínuo com separador de parágrafo
    3. Aplica RecursiveCharacterTextSplitter ao texto completo — o overlap
       cruza fronteiras de página, mantendo secções intactas
    4. Mapeia cada chunk de volta às páginas de origem

    Args:
        documento: Documento carregado pelo loader.
        chunk_size: Tamanho máximo de cada chunk (em caracteres — aprox. tokens).
        chunk_overlap: Sobreposição entre chunks consecutivos.

    Returns:
        Lista de Chunk ordenados por posição no documento.
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

    # 1. Concatenar todas as páginas, registando onde cada uma começa/acaba
    texto_completo = ""
    segmentos: list[dict] = []   # {inicio, fim, numero, tem_tabela}

    for pagina in documento.paginas:
        texto_pagina = _construir_texto_pagina(pagina)
        if not texto_pagina:
            continue

        inicio = len(texto_completo)
        texto_completo += texto_pagina + "\n\n"
        segmentos.append({
            "inicio": inicio,
            "fim": len(texto_completo),
            "numero": pagina["numero"],
            "tem_tabela": bool(pagina.get("tabelas")),
        })

    if not texto_completo.strip():
        return []

    # 2. Split global — o overlap agora cruza fronteiras de página
    fragmentos = splitter.split_text(texto_completo)

    # 3. Mapear cada fragmento de volta às páginas de origem
    chunks: list[Chunk] = []
    posicao_busca = 0  # posição de busca para encontrar fragmentos em ordem

    for chunk_index, fragmento in enumerate(fragmentos):
        if not fragmento.strip():
            continue

        # Encontrar onde este fragmento aparece no texto completo
        idx = texto_completo.find(fragmento, posicao_busca)
        if idx == -1:
            # Fallback: procurar desde o início (pode acontecer com overlap)
            idx = texto_completo.find(fragmento)
        if idx == -1:
            idx = posicao_busca  # último recurso

        info_paginas = _encontrar_paginas(idx, idx + len(fragmento), segmentos)
        posicao_busca = idx + 1  # avançar para evitar re-match do mesmo fragmento

        chunks.append(Chunk(
            texto=fragmento,
            metadados={
                "ficheiro": documento.ficheiro,
                "tipo_documento": documento.tipo_documento,
                "pagina": info_paginas["pagina"],
                "paginas": info_paginas["paginas"],
                "chunk_index": chunk_index,
                "tem_tabela": info_paginas["tem_tabela"],
            },
        ))

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
