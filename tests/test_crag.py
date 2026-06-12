"""
Testes unitarios do CRAG (src/query/crag.py) com o LLM mockado.

Cobrem o parsing da avaliacao (incluindo o fallback conservador), a truncagem
do contexto em modo local, e as ramificacoes do crag_pipeline (suficiente a
primeira / reformulacao que melhora acima e abaixo do threshold / que piora).
"""

import pytest

import src.query.crag as crag
from src.query.retriever import ChunkRecuperado


def _chunk(i: int, texto: str = None) -> ChunkRecuperado:
    return ChunkRecuperado(
        texto=texto if texto is not None else f"conteudo {i}",
        metadados={"ficheiro": f"doc{i}.pdf", "pagina": 1, "tipo_documento": "bula"},
        score=0.5,
        ponto_id=f"ponto-{i}",
    )


@pytest.fixture()
def llm(monkeypatch):
    estado = {"resposta": "{}", "prompts": [], "modo": "online"}

    def fake_chamar_llm(prompt, system="", max_tokens=1024, temperature=0.0, force_json=False):
        estado["prompts"].append(prompt)
        return estado["resposta"]

    monkeypatch.setattr(crag, "chamar_llm", fake_chamar_llm)
    monkeypatch.setattr(crag, "obter_modo_llm", lambda: estado["modo"])
    return estado


class TestAvaliarRelevancia:
    def test_json_valido(self, llm):
        llm["resposta"] = '{"relevante": true, "confianca": 0.9, "razao": "cobre a pergunta"}'
        av = crag.avaliar_relevancia("q", [_chunk(0)])
        assert av["relevante"] is True
        assert av["confianca"] == 0.9

    def test_markdown_fence(self, llm):
        llm["resposta"] = '```json\n{"relevante": false, "confianca": 0.2, "razao": "x"}\n```'
        av = crag.avaliar_relevancia("q", [_chunk(0)])
        assert av["relevante"] is False

    def test_json_invalido_assume_relevante(self, llm):
        llm["resposta"] = "isto nao e json"
        av = crag.avaliar_relevancia("q", [_chunk(0)])
        assert av["relevante"] is True
        assert av["confianca"] == 0.5

    def test_sem_chunks_e_irrelevante_sem_chamar_llm(self, llm):
        av = crag.avaliar_relevancia("q", [])
        assert av["relevante"] is False
        assert llm["prompts"] == []


class TestTruncagemContexto:
    def test_local_trunca_a_1200(self, llm):
        llm["modo"] = "local"
        contexto = crag._formatar_contexto([_chunk(0, texto="b" * 4000)])
        assert "b" * 1200 + " [...]" in contexto
        assert "b" * 1201 not in contexto

    def test_online_mantem_completo(self, llm):
        llm["modo"] = "online"
        contexto = crag._formatar_contexto([_chunk(0, texto="b" * 4000)])
        assert "b" * 4000 in contexto


class TestCragPipeline:
    def test_suficiente_a_primeira(self, llm, monkeypatch):
        chunks = [_chunk(0)]
        monkeypatch.setattr(crag, "avaliar_relevancia",
                            lambda q, c: {"relevante": True, "confianca": 0.9})
        reformulou = []
        monkeypatch.setattr(crag, "reformular_query",
                            lambda q: reformulou.append(q) or "nova")
        finais, suficiente, usada = crag.crag_pipeline("q", chunks, recuperar_fn=lambda nq: [])
        assert (finais, suficiente, usada) == (chunks, True, "q")
        assert reformulou == []   # nem tentou reformular

    def test_insuficiente_sem_recuperar_fn(self, llm, monkeypatch):
        chunks = [_chunk(0)]
        monkeypatch.setattr(crag, "avaliar_relevancia",
                            lambda q, c: {"relevante": False, "confianca": 0.2})
        finais, suficiente, usada = crag.crag_pipeline("q", chunks)
        assert (finais, suficiente, usada) == (chunks, False, "q")

    def _pipeline_com_avaliacoes(self, monkeypatch, avaliacoes):
        """Helper: avaliar_relevancia devolve cada item da lista por ordem."""
        fila = list(avaliacoes)
        monkeypatch.setattr(crag, "avaliar_relevancia", lambda q, c: fila.pop(0))
        monkeypatch.setattr(crag, "reformular_query", lambda q: "query reformulada")

    def test_reformulacao_resolve(self, llm, monkeypatch):
        originais, novos = [_chunk(0)], [_chunk(1)]
        self._pipeline_com_avaliacoes(monkeypatch, [
            {"relevante": False, "confianca": 0.3},
            {"relevante": True, "confianca": 0.9},
        ])
        finais, suficiente, usada = crag.crag_pipeline("q", originais, recuperar_fn=lambda nq: novos)
        assert (finais, suficiente, usada) == (novos, True, "query reformulada")

    def test_reformulacao_melhora_mas_abaixo_do_threshold(self, llm, monkeypatch):
        originais, novos = [_chunk(0)], [_chunk(1)]
        self._pipeline_com_avaliacoes(monkeypatch, [
            {"relevante": False, "confianca": 0.3},
            {"relevante": True, "confianca": 0.6},   # melhor, mas < RELEVANCE_THRESHOLD
        ])
        finais, suficiente, usada = crag.crag_pipeline("q", originais, recuperar_fn=lambda nq: novos)
        assert finais == novos
        assert suficiente is False
        assert usada == "query reformulada"

    def test_reformulacao_que_piora_mantem_originais(self, llm, monkeypatch):
        originais, novos = [_chunk(0)], [_chunk(1)]
        self._pipeline_com_avaliacoes(monkeypatch, [
            {"relevante": False, "confianca": 0.5},
            {"relevante": False, "confianca": 0.2},   # piorou
        ])
        finais, suficiente, usada = crag.crag_pipeline("q", originais, recuperar_fn=lambda nq: novos)
        assert (finais, suficiente, usada) == (originais, False, "q")
