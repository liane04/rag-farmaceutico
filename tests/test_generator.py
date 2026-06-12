"""
Testes unitarios do generator (src/query/generator.py) com o LLM mockado.

Cobrem a resposta padrao sem chunks, a extracao/deduplicacao de fontes, o
aviso de contexto insuficiente (CRAG), a numeracao dos excertos no contexto,
e a versao streaming.
"""

import pytest

import src.query.generator as generator
from src.query.retriever import ChunkRecuperado


def _chunk(i: int, ficheiro: str = None, pagina: int = None) -> ChunkRecuperado:
    return ChunkRecuperado(
        texto=f"conteudo {i}",
        metadados={
            "ficheiro": ficheiro or f"doc{i}.pdf",
            "pagina": pagina if pagina is not None else i + 1,
            "tipo_documento": "bula",
        },
        score=0.9,
        ponto_id=f"ponto-{i}",
    )


@pytest.fixture()
def llm(monkeypatch):
    estado = {"resposta": "resposta gerada [1]", "pedacos": ["res", "posta"], "kwargs": None}

    def fake_chamar_llm(prompt, system="", max_tokens=1024, temperature=0.0, force_json=False):
        estado["kwargs"] = {"prompt": prompt, "system": system}
        return estado["resposta"]

    def fake_stream_llm(prompt, system="", max_tokens=1500, temperature=0.2):
        yield from estado["pedacos"]

    monkeypatch.setattr(generator, "chamar_llm", fake_chamar_llm)
    monkeypatch.setattr(generator, "stream_llm", fake_stream_llm)
    return estado


class TestGerarResposta:
    def test_sem_chunks_devolve_resposta_padrao(self, llm):
        r = generator.gerar_resposta("q", [])
        assert "não contém informação suficiente" in r.resposta
        assert r.contexto_suficiente is False
        assert r.fontes == []
        assert llm["kwargs"] is None   # nao chama o LLM

    def test_com_chunks_devolve_resposta_e_fontes(self, llm):
        r = generator.gerar_resposta("q", [_chunk(0), _chunk(1)])
        assert r.resposta == "resposta gerada [1]"
        assert r.contexto_suficiente is True
        assert r.fontes == [
            {"ficheiro": "doc0.pdf", "pagina": 1, "tipo_documento": "bula"},
            {"ficheiro": "doc1.pdf", "pagina": 2, "tipo_documento": "bula"},
        ]

    def test_fontes_deduplicadas_por_ficheiro_e_pagina(self, llm):
        chunks = [
            _chunk(0, ficheiro="a.pdf", pagina=3),
            _chunk(1, ficheiro="a.pdf", pagina=3),   # duplicado
            _chunk(2, ficheiro="b.pdf", pagina=1),
        ]
        r = generator.gerar_resposta("q", chunks)
        assert len(r.fontes) == 2

    def test_contexto_insuficiente_anexa_nota(self, llm):
        r = generator.gerar_resposta("q", [_chunk(0)], contexto_suficiente=False)
        assert r.resposta.startswith("resposta gerada")
        assert "NOTA:" in r.resposta
        assert r.contexto_suficiente is False

    def test_contexto_e_numerado_por_excerto(self, llm):
        generator.gerar_resposta("q", [_chunk(0), _chunk(1)])
        prompt = llm["kwargs"]["prompt"]
        assert "[1] Fonte: doc0.pdf (p.1)" in prompt
        assert "[2] Fonte: doc1.pdf (p.2)" in prompt

    def test_query_usada_propagada(self, llm):
        r = generator.gerar_resposta("original", [_chunk(0)], query_usada="reformulada")
        assert r.query_usada == "reformulada"


class TestGerarRespostaStream:
    def test_yield_dos_pedacos(self, llm):
        pedacos = list(generator.gerar_resposta_stream("q", [_chunk(0)]))
        assert pedacos == ["res", "posta"]

    def test_sem_chunks_yield_da_resposta_padrao(self, llm):
        pedacos = list(generator.gerar_resposta_stream("q", []))
        assert any("não contém informação suficiente" in p for p in pedacos)

    def test_contexto_insuficiente_anexa_nota_no_fim(self, llm):
        pedacos = list(generator.gerar_resposta_stream("q", [_chunk(0)], contexto_suficiente=False))
        assert pedacos[:2] == ["res", "posta"]
        assert "NOTA:" in pedacos[-1]
