"""
Testes unitarios do reranker LLM-as-Judge (src/query/reranker.py).

O LLM e mockado — cobrem-se as ramificacoes de parsing (envelope, array,
objeto unico, JSON invalido), a normalizacao/clamp dos scores, e a truncagem
dos excertos em modo local. E o codigo que mais ramifica no pipeline e que
ja falhou de formas diferentes com modelos locais.
"""

import pytest

import src.query.reranker as reranker
from src.query.retriever import ChunkRecuperado


def _chunk(i: int, texto: str = None) -> ChunkRecuperado:
    return ChunkRecuperado(
        texto=texto if texto is not None else f"conteudo do excerto {i}",
        metadados={"ficheiro": f"doc{i}.pdf", "pagina": i + 1, "tipo_documento": "bula"},
        score=0.5,
        ponto_id=f"ponto-{i}",
    )


@pytest.fixture()
def llm(monkeypatch):
    """Mock do chamar_llm + modo controlavel; regista prompts e force_json."""
    estado = {"resposta": "[]", "prompts": [], "force_json": None, "modo": "online"}

    def fake_chamar_llm(prompt, system="", max_tokens=1024, temperature=0.0, force_json=False):
        estado["prompts"].append(prompt)
        estado["force_json"] = force_json
        return estado["resposta"]

    monkeypatch.setattr(reranker, "chamar_llm", fake_chamar_llm)
    monkeypatch.setattr(reranker, "obter_modo_llm", lambda: estado["modo"])
    return estado


class TestCasosSemLLM:
    def test_lista_vazia(self, llm):
        assert reranker.rerankar("q", []) == []
        assert llm["prompts"] == []

    def test_poucos_chunks_devolve_sem_chamar_llm(self, llm):
        chunks = [_chunk(0), _chunk(1)]
        resultado = reranker.rerankar("q", chunks, top_n=3)
        assert resultado == chunks
        assert llm["prompts"] == []


class TestParsing:
    def test_envelope_avaliacoes(self, llm):
        chunks = [_chunk(i) for i in range(5)]
        llm["resposta"] = (
            '{"avaliacoes": ['
            '{"indice": 0, "score": 2, "razao": "x"},'
            '{"indice": 1, "score": 9, "razao": "x"},'
            '{"indice": 2, "score": 5, "razao": "x"},'
            '{"indice": 3, "score": 7, "razao": "x"},'
            '{"indice": 4, "score": 1, "razao": "x"}]}'
        )
        resultado = reranker.rerankar("q", chunks, top_n=3)
        assert [r.metadados["ficheiro"] for r in resultado] == ["doc1.pdf", "doc3.pdf", "doc2.pdf"]
        assert [r.score for r in resultado] == [0.9, 0.7, 0.5]
        # Os chunks originais nao sao mutados (replace cria copias)
        assert all(c.score == 0.5 for c in chunks)

    def test_array_directo_estilo_claude(self, llm):
        chunks = [_chunk(i) for i in range(4)]
        llm["resposta"] = (
            '[{"indice": 3, "score": 10, "razao": "x"},'
            ' {"indice": 0, "score": 4, "razao": "x"}]'
        )
        resultado = reranker.rerankar("q", chunks, top_n=3)
        assert [r.metadados["ficheiro"] for r in resultado] == ["doc3.pdf", "doc0.pdf"]

    def test_objeto_unico_e_embrulhado(self, llm):
        # Em format=json os modelos pequenos as vezes avaliam so um excerto.
        chunks = [_chunk(i) for i in range(4)]
        llm["resposta"] = '{"indice": 2, "score": 8, "razao": "x"}'
        resultado = reranker.rerankar("q", chunks, top_n=3)
        assert len(resultado) == 1
        assert resultado[0].metadados["ficheiro"] == "doc2.pdf"
        assert resultado[0].score == 0.8

    def test_markdown_fence_e_removido(self, llm):
        chunks = [_chunk(i) for i in range(4)]
        llm["resposta"] = '```json\n[{"indice": 1, "score": 6, "razao": "x"}]\n```'
        resultado = reranker.rerankar("q", chunks, top_n=3)
        assert resultado[0].metadados["ficheiro"] == "doc1.pdf"

    def test_json_invalido_cai_na_ordem_original(self, llm):
        chunks = [_chunk(i) for i in range(5)]
        llm["resposta"] = '{ "instructions": [ { "step": 1, "description": "...'  # truncado
        resultado = reranker.rerankar("q", chunks, top_n=3)
        assert resultado == chunks[:3]

    def test_dict_alienigena_cai_na_ordem_original(self, llm):
        chunks = [_chunk(i) for i in range(5)]
        llm["resposta"] = '{"foo": "bar"}'   # JSON valido mas sem avaliacoes
        resultado = reranker.rerankar("q", chunks, top_n=3)
        assert resultado == chunks[:3]


class TestScoresEIndices:
    def test_clamp_de_scores_alucinados(self, llm):
        chunks = [_chunk(i) for i in range(4)]
        llm["resposta"] = (
            '[{"indice": 0, "score": 15, "razao": "x"},'
            ' {"indice": 1, "score": -3, "razao": "x"}]'
        )
        resultado = reranker.rerankar("q", chunks, top_n=3)
        assert resultado[0].score == 1.0   # 15 -> clamp 10 -> 1.0
        assert resultado[1].score == 0.0   # -3 -> clamp 0

    def test_indice_fora_do_intervalo_e_ignorado(self, llm):
        chunks = [_chunk(i) for i in range(4)]
        llm["resposta"] = (
            '[{"indice": 99, "score": 10, "razao": "x"},'
            ' {"indice": 1, "score": 5, "razao": "x"}]'
        )
        resultado = reranker.rerankar("q", chunks, top_n=3)
        assert len(resultado) == 1
        assert resultado[0].metadados["ficheiro"] == "doc1.pdf"


class TestTruncagemEModo:
    def test_local_trunca_excertos_a_700(self, llm):
        llm["modo"] = "local"
        chunks = [_chunk(i, texto="a" * 4000) for i in range(4)]
        llm["resposta"] = "[]"
        reranker.rerankar("q", chunks, top_n=3)
        prompt = llm["prompts"][0]
        assert "a" * 700 + " [...]" in prompt
        assert "a" * 701 not in prompt

    def test_online_usa_excertos_completos(self, llm):
        llm["modo"] = "online"
        chunks = [_chunk(i, texto="a" * 4000) for i in range(4)]
        llm["resposta"] = "[]"
        reranker.rerankar("q", chunks, top_n=3)
        assert "a" * 4000 in llm["prompts"][0]

    def test_pede_force_json(self, llm):
        chunks = [_chunk(i) for i in range(4)]
        llm["resposta"] = "[]"
        reranker.rerankar("q", chunks, top_n=3)
        assert llm["force_json"] is True
