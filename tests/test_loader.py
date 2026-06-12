"""
Testes para o loader de PDFs (src/ingestion/loader.py).
"""

import pytest
from pathlib import Path

from src.ingestion.loader import carregar_pdf, carregar_pasta, DocumentoExtraido


# PDFs de teste: fixture propria em tests/fixtures, NAO o corpus real de
# data/documents — esse e gerido pelo admin na UI (upload/apagar) e os testes
# nao podem depender de ficheiros que mudam. (Licao: os testes apontavam ao
# brufen_folheto.pdf, que foi substituido durante a expansao do corpus.)
PASTA_DOCUMENTOS = Path(__file__).parent / "fixtures" / "documents"
PDF_BULA = PASTA_DOCUMENTOS / "bulas" / "bula_exemplo.pdf"


class TestCarregarPdf:
    """Testes para a funcao carregar_pdf."""

    def test_carrega_pdf_existente(self):
        doc = carregar_pdf(PDF_BULA, tipo_documento="bula")
        assert isinstance(doc, DocumentoExtraido)
        assert doc.ficheiro == "bula_exemplo.pdf"
        assert doc.tipo_documento == "bula"
        assert doc.total_paginas > 0

    def test_paginas_tem_estrutura_correta(self):
        doc = carregar_pdf(PDF_BULA, tipo_documento="bula")
        for pagina in doc.paginas:
            assert "numero" in pagina
            assert "texto" in pagina
            assert "tabelas" in pagina
            assert isinstance(pagina["numero"], int)
            assert isinstance(pagina["texto"], str)
            assert isinstance(pagina["tabelas"], list)

    def test_extrai_texto_nao_vazio(self):
        doc = carregar_pdf(PDF_BULA, tipo_documento="bula")
        textos = [p["texto"] for p in doc.paginas if p["texto"].strip()]
        assert len(textos) > 0, "Nenhuma pagina com texto extraido"

    def test_tipo_documento_default(self):
        doc = carregar_pdf(PDF_BULA)
        assert doc.tipo_documento == "desconhecido"

    def test_pdf_inexistente_levanta_erro(self):
        with pytest.raises(FileNotFoundError):
            carregar_pdf("ficheiro_que_nao_existe.pdf")

    def test_total_paginas_calculado(self):
        doc = carregar_pdf(PDF_BULA, tipo_documento="bula")
        assert doc.total_paginas == len(doc.paginas)


class TestCarregarPasta:
    """Testes para a funcao carregar_pasta."""

    def test_carrega_todos_pdfs_recursivamente(self):
        docs = carregar_pasta(PASTA_DOCUMENTOS)
        assert len(docs) >= 1
        for doc in docs:
            assert isinstance(doc, DocumentoExtraido)
            assert doc.ficheiro.endswith(".pdf")

    def test_infere_tipo_bula(self):
        docs = carregar_pasta(PASTA_DOCUMENTOS)
        bulas = [d for d in docs if d.tipo_documento == "bula"]
        assert len(bulas) >= 1
        assert any(d.ficheiro == "bula_exemplo.pdf" for d in bulas)

    def test_infere_tipo_pela_pasta(self, tmp_path):
        """Testa que PDFs na pasta monografias/ são classificados como monografia."""
        mono_dir = tmp_path / "monografias"
        mono_dir.mkdir()
        import shutil
        shutil.copy(PDF_BULA, mono_dir / "qualquer_monografia.pdf")
        docs = carregar_pasta(tmp_path)
        monografias = [d for d in docs if d.tipo_documento == "monografia"]
        assert len(monografias) >= 1

    def test_mapeamento_explicito_tem_prioridade(self):
        mapeamento = {"bula_exemplo.pdf": "guideline"}
        docs = carregar_pasta(PASTA_DOCUMENTOS, mapeamento_tipos=mapeamento)
        bula = next(d for d in docs if d.ficheiro == "bula_exemplo.pdf")
        assert bula.tipo_documento == "guideline"

    def test_pasta_inexistente_levanta_erro(self):
        with pytest.raises(NotADirectoryError):
            carregar_pasta("pasta_que_nao_existe")
