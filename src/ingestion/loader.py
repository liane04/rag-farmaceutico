"""
Carregamento e extração de texto de documentos PDF farmacêuticos.

- PyMuPDF (fitz): extração de texto corrido por página
- pdfplumber: extração de tabelas com preservação da estrutura
"""

from dataclasses import dataclass
from pathlib import Path

import fitz          # PyMuPDF
import pdfplumber


@dataclass
class DocumentoExtraido:
    """Representa o conteúdo extraído de um PDF."""
    ficheiro: str
    paginas: list[dict]   # [{numero, texto, tabelas}]
    tipo_documento: str   # ex: "bula", "monografia", "guideline"
    total_paginas: int = 0

    def __post_init__(self):
        self.total_paginas = len(self.paginas)


def _extrair_tabelas_pagina(pdf_plumber_pagina) -> list[str]:
    """
    Extrai tabelas de uma página via pdfplumber e converte para texto formatado.
    Cada tabela é serializada como linhas separadas por '|'.
    """
    tabelas_texto = []
    tabelas = pdf_plumber_pagina.extract_tables()
    for tabela in tabelas:
        linhas = []
        for linha in tabela:
            # Limpa células None e normaliza espaços
            celulas = [str(c).strip() if c else "" for c in linha]
            linhas.append(" | ".join(celulas))
        tabelas_texto.append("\n".join(linhas))
    return tabelas_texto


def _limpar_texto(texto: str) -> str:
    """
    Limpeza básica do texto extraído:
    - Remove linhas com apenas números de página ou cabeçalhos repetitivos curtos
    - Normaliza espaços múltiplos e linhas em branco excessivas
    """
    linhas = texto.split("\n")
    linhas_limpas = []
    for linha in linhas:
        linha = linha.strip()
        # Ignora linhas que são apenas número de página (ex: "1", "- 2 -")
        if linha.strip("- ").isdigit():
            continue
        # Ignora linhas muito curtas que são provavelmente ruído
        if len(linha) < 3:
            continue
        linhas_limpas.append(linha)

    texto_limpo = "\n".join(linhas_limpas)
    # Colapsa múltiplas linhas em branco em duas
    while "\n\n\n" in texto_limpo:
        texto_limpo = texto_limpo.replace("\n\n\n", "\n\n")
    return texto_limpo.strip()


def carregar_pdf(
    caminho: str | Path,
    tipo_documento: str = "desconhecido",
) -> DocumentoExtraido:
    """
    Carrega um PDF e extrai texto (PyMuPDF) e tabelas (pdfplumber).

    Args:
        caminho: Caminho para o ficheiro PDF.
        tipo_documento: Classificação do documento (ex: "bula", "monografia").

    Returns:
        DocumentoExtraido com o conteúdo de cada página.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Ficheiro não encontrado: {caminho}")

    paginas_extraidas = []

    # Abre ambos os parsers em paralelo (mesmo ficheiro)
    doc_fitz = fitz.open(str(caminho))

    with pdfplumber.open(str(caminho)) as doc_plumber:
        for num_pagina in range(len(doc_fitz)):
            # --- Texto corrido via PyMuPDF ---
            pagina_fitz = doc_fitz[num_pagina]
            texto_bruto = pagina_fitz.get_text("text")
            texto = _limpar_texto(texto_bruto)

            # --- Tabelas via pdfplumber ---
            pagina_plumber = doc_plumber.pages[num_pagina]
            tabelas = _extrair_tabelas_pagina(pagina_plumber)

            paginas_extraidas.append({
                "numero": num_pagina + 1,
                "texto": texto,
                "tabelas": tabelas,
            })

    doc_fitz.close()

    return DocumentoExtraido(
        ficheiro=caminho.name,
        paginas=paginas_extraidas,
        tipo_documento=tipo_documento,
    )


def carregar_pasta(
    pasta: str | Path,
    mapeamento_tipos: dict[str, str] | None = None,
) -> list[DocumentoExtraido]:
    """
    Carrega todos os PDFs de uma pasta.

    Args:
        pasta: Diretório com os ficheiros PDF.
        mapeamento_tipos: Dicionário {nome_ficheiro: tipo_documento}.
                          Documentos sem mapeamento ficam como "desconhecido".

    Returns:
        Lista de DocumentoExtraido, um por ficheiro.
    """
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise NotADirectoryError(f"Pasta não encontrada: {pasta}")

    mapeamento_tipos = mapeamento_tipos or {}
    documentos = []

    for pdf in sorted(pasta.glob("*.pdf")):
        tipo = mapeamento_tipos.get(pdf.name, "desconhecido")
        print(f"[loader] A carregar {pdf.name} (tipo: {tipo})")
        doc = carregar_pdf(pdf, tipo_documento=tipo)
        documentos.append(doc)
        print(f"[loader] {pdf.name} → {doc.total_paginas} páginas")

    return documentos
