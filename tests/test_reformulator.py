"""
Testes unitarios da reformulacao contextual (src/query/reformulator.py).

LLM mockado. Cobrem o early-return com historico vazio (nao paga chamada),
a aceitacao de mensagens como dicts e como objetos, e as defesas contra
outputs anormais do LLM.
"""

from types import SimpleNamespace

import pytest

import src.query.reformulator as reformulator


@pytest.fixture()
def llm(monkeypatch):
    estado = {"resposta": "query autonoma", "chamadas": 0}

    def fake_chamar_llm(prompt, system="", max_tokens=1024, temperature=0.0, force_json=False):
        estado["chamadas"] += 1
        estado["prompt"] = prompt
        return estado["resposta"]

    monkeypatch.setattr(reformulator, "chamar_llm", fake_chamar_llm)
    return estado


class TestReformularComHistoria:
    def test_historia_vazia_devolve_query_sem_chamar_llm(self, llm):
        assert reformulator.reformular_com_historia("e a posologia?", []) == "e a posologia?"
        assert llm["chamadas"] == 0

    def test_com_historia_devolve_reformulacao(self, llm):
        historia = [
            {"role": "user", "conteudo": "O que e o brufen?"},
            {"role": "assistant", "conteudo": "O brufen e um anti-inflamatorio."},
        ]
        llm["resposta"] = "qual a posologia do brufen?"
        resultado = reformulator.reformular_com_historia("e a posologia?", historia)
        assert resultado == "qual a posologia do brufen?"
        assert llm["chamadas"] == 1
        # O historico entra no prompt
        assert "O que e o brufen?" in llm["prompt"]

    def test_aceita_objetos_com_atributos(self, llm):
        historia = [SimpleNamespace(role="user", conteudo="O que e o brufen?")]
        llm["resposta"] = "reformulada"
        assert reformulator.reformular_com_historia("e isso?", historia) == "reformulada"

    def test_output_vazio_cai_na_query_original(self, llm):
        historia = [{"role": "user", "conteudo": "x"}]
        llm["resposta"] = "   "
        assert reformulator.reformular_com_historia("pergunta", historia) == "pergunta"

    def test_output_gigante_cai_na_query_original(self, llm):
        historia = [{"role": "user", "conteudo": "x"}]
        llm["resposta"] = "a" * 2001
        assert reformulator.reformular_com_historia("pergunta", historia) == "pergunta"
