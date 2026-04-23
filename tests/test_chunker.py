"""
Testes para o chunker (src/ingestion/chunker.py).
"""

import pytest

from src.ingestion.loader import carregar_pdf, DocumentoExtraido
from src.ingestion.chunker import chunkar_documento, chunkar_documentos, Chunk
from src.config import CHUNK_SIZE, CHUNK_OVERLAP
from pathlib import Path


PDF_BULA = Path(__file__).parent.parent / "data" / "documents" / "bulas" / "brufen_folheto.pdf"


@pytest.fixture
def documento():
    return carregar_pdf(PDF_BULA, tipo_documento="bula")


class TestChunkarDocumento:
    """Testes para a funcao chunkar_documento."""

    def test_produz_chunks(self, documento):
        chunks = chunkar_documento(documento)
        assert len(chunks) > 0

    def test_chunks_sao_tipo_correto(self, documento):
        chunks = chunkar_documento(documento)
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert isinstance(chunk.texto, str)
            assert isinstance(chunk.metadados, dict)

    def test_metadados_completos(self, documento):
        chunks = chunkar_documento(documento)
        campos_obrigatorios = ["ficheiro", "tipo_documento", "pagina", "chunk_index", "tem_tabela"]
        for chunk in chunks:
            for campo in campos_obrigatorios:
                assert campo in chunk.metadados, f"Campo '{campo}' em falta nos metadados"

    def test_tipo_documento_preservado(self, documento):
        chunks = chunkar_documento(documento)
        for chunk in chunks:
            assert chunk.metadados["tipo_documento"] == "bula"

    def test_ficheiro_preservado(self, documento):
        chunks = chunkar_documento(documento)
        for chunk in chunks:
            assert chunk.metadados["ficheiro"] == "brufen_folheto.pdf"

    def test_chunk_index_sequencial(self, documento):
        chunks = chunkar_documento(documento)
        indices = [c.metadados["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_tamanho_chunks_respeita_limite(self, documento):
        chunks = chunkar_documento(documento)
        for chunk in chunks:
            # Margem de tolerancia (splitter pode exceder ligeiramente)
            assert len(chunk.texto) <= CHUNK_SIZE * 1.1, \
                f"Chunk com {len(chunk.texto)} chars excede limite de {CHUNK_SIZE}"

    def test_texto_nao_vazio(self, documento):
        chunks = chunkar_documento(documento)
        for chunk in chunks:
            assert chunk.texto.strip(), "Chunk com texto vazio"

    def test_chunk_size_custom(self, documento):
        chunks_pequenos = chunkar_documento(documento, chunk_size=500, chunk_overlap=50)
        chunks_grandes = chunkar_documento(documento, chunk_size=8000, chunk_overlap=200)
        assert len(chunks_pequenos) > len(chunks_grandes)


class TestChunkarDocumentos:
    """Testes para a funcao chunkar_documentos."""

    def test_multiplos_documentos(self):
        doc1 = carregar_pdf(PDF_BULA, tipo_documento="bula")
        docs = [doc1]
        chunks = chunkar_documentos(docs)
        assert len(chunks) > 0

    def test_preserva_ficheiros_diferentes(self):
        doc1 = carregar_pdf(PDF_BULA, tipo_documento="bula")
        doc2 = DocumentoExtraido(
            ficheiro="monografia_sintetica.pdf",
            paginas=[{"numero": 1, "texto": "Ibuprofeno é um anti-inflamatório não esteroide utilizado no tratamento da dor e febre. " * 20, "tabelas": []}],
            tipo_documento="monografia",
        )
        chunks = chunkar_documentos([doc1, doc2])
        ficheiros = set(c.metadados["ficheiro"] for c in chunks)
        assert "brufen_folheto.pdf" in ficheiros
        assert "monografia_sintetica.pdf" in ficheiros
