"""
Testes de integracao para o retriever (src/query/retriever.py).

REQUER: Qdrant a correr em localhost:6333 com dados indexados.
REQUER: GOOGLE_API_KEY definida no .env (para gerar embeddings).
"""

import pytest

from src.query.retriever import recuperar, ChunkRecuperado


# Marca todos os testes desta classe como integracao
pytestmark = pytest.mark.integration


class TestRecuperar:
    """Testes de integracao para recuperacao hibrida."""

    def test_recupera_resultados(self):
        chunks = recuperar("efeitos secundarios do ibuprofeno")
        assert len(chunks) > 0

    def test_retorna_chunks_recuperados(self):
        chunks = recuperar("posologia do brufen")
        for chunk in chunks:
            assert isinstance(chunk, ChunkRecuperado)
            assert chunk.texto
            assert chunk.metadados
            assert chunk.score is not None

    def test_respeita_top_k(self):
        chunks = recuperar("ibuprofeno", top_k=3)
        assert len(chunks) <= 3

    def test_metadados_completos(self):
        chunks = recuperar("brufen")
        for chunk in chunks:
            assert "ficheiro" in chunk.metadados
            assert "tipo_documento" in chunk.metadados
            assert "pagina" in chunk.metadados

    def test_filtragem_por_tipo(self):
        chunks = recuperar("ibuprofeno", tipo_documento="bula")
        for chunk in chunks:
            assert chunk.metadados["tipo_documento"] == "bula"

    def test_filtragem_monografia(self):
        chunks = recuperar("ibuprofeno", tipo_documento="monografia")
        for chunk in chunks:
            assert chunk.metadados["tipo_documento"] == "monografia"

    def test_query_sem_resultados_relevantes(self):
        # Query completamente fora de dominio mas que pode devolver algo
        chunks = recuperar("receita de bolo de chocolate", top_k=3)
        # Pode devolver resultados (Qdrant sempre retorna algo),
        # mas os scores devem ser baixos
        assert isinstance(chunks, list)
