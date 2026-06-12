"""
Testes unitarios do cliente LLM multi-provider (src/llm_client.py).

Cobrem o switch online/local persistido em SQLite e a interface unificada
chamar_llm/stream_llm com AMBOS os providers mockados — nao ha chamadas de
rede nem dependencia do Anthropic/Ollama reais.
"""

from types import SimpleNamespace

import pytest

import src.llm_client as llm
from src.config import LLM_MODE_DEFAULT


# ---------- Stubs dos providers ----------

class _StubAnthropic:
    """Imita o cliente Anthropic: messages.create e messages.stream."""

    def __init__(self, texto="resposta claude"):
        self.texto = texto
        self.kwargs_create = None
        self.kwargs_stream = None
        stub = self

        class _Messages:
            def create(self, **kwargs):
                stub.kwargs_create = kwargs
                return SimpleNamespace(content=[SimpleNamespace(text=f"  {stub.texto}  ")])

            def stream(self, **kwargs):
                stub.kwargs_stream = kwargs

                class _Ctx:
                    def __enter__(self_inner):
                        return SimpleNamespace(text_stream=iter(["res", "posta ", "claude"]))

                    def __exit__(self_inner, *exc):
                        return False

                return _Ctx()

        self.messages = _Messages()


class _StubOllama:
    """Imita o ChatOllama: invoke, stream e bind(format=...)."""

    def __init__(self, texto="resposta ollama"):
        self.texto = texto
        self.bind_kwargs = None
        self.invocado_com = None

    def invoke(self, mensagens):
        self.invocado_com = mensagens
        return SimpleNamespace(content=f"  {self.texto}  ")

    def stream(self, mensagens):
        self.invocado_com = mensagens
        for pedaco in ["res", "posta ", "ollama"]:
            yield SimpleNamespace(content=pedaco)

    def bind(self, **kwargs):
        # Devolve-se a si proprio mas regista o pedido — suficiente para
        # verificar que force_json liga o format="json".
        self.bind_kwargs = kwargs
        return self


@pytest.fixture()
def stubs(bd_temporaria, monkeypatch):
    """Substitui os dois providers por stubs e devolve-os."""
    anthropic = _StubAnthropic()
    ollama = _StubOllama()
    monkeypatch.setattr(llm, "_obter_cliente_anthropic", lambda: anthropic)
    monkeypatch.setattr(llm, "_obter_cliente_ollama", lambda temperature=0.0: ollama)
    return SimpleNamespace(anthropic=anthropic, ollama=ollama)


# ---------- Modo: persistencia e validacao ----------

class TestModoLLM:
    def test_default_sem_definicao_na_bd(self, bd_temporaria):
        assert llm.obter_modo_llm() == LLM_MODE_DEFAULT

    def test_round_trip(self, bd_temporaria):
        llm.definir_modo_llm("local")
        assert llm.obter_modo_llm() == "local"
        llm.definir_modo_llm("online")
        assert llm.obter_modo_llm() == "online"

    def test_modo_invalido_levanta_erro(self, bd_temporaria):
        with pytest.raises(ValueError):
            llm.definir_modo_llm("hibrido")

    def test_valor_corrompido_na_bd_cai_no_default(self, bd_temporaria):
        from src.auth.db import definir_definicao
        definir_definicao("llm_mode", "lixo")
        assert llm.obter_modo_llm() == LLM_MODE_DEFAULT


# ---------- chamar_llm ----------

class TestChamarLLM:
    def test_online_usa_anthropic(self, stubs):
        llm.definir_modo_llm("online")
        resposta = llm.chamar_llm("ola", system="es um teste", max_tokens=42)
        assert resposta == "resposta claude"  # strip aplicado
        assert stubs.anthropic.kwargs_create["max_tokens"] == 42
        assert stubs.anthropic.kwargs_create["system"] == "es um teste"
        assert stubs.ollama.invocado_com is None

    def test_local_usa_ollama(self, stubs):
        llm.definir_modo_llm("local")
        resposta = llm.chamar_llm("ola", system="es um teste")
        assert resposta == "resposta ollama"
        assert stubs.ollama.invocado_com is not None
        assert stubs.anthropic.kwargs_create is None
        # System prompt vai como primeira mensagem
        assert stubs.ollama.invocado_com[0].content == "es um teste"

    def test_force_json_liga_format_json_no_ollama(self, stubs):
        llm.definir_modo_llm("local")
        llm.chamar_llm("ola", force_json=True)
        assert stubs.ollama.bind_kwargs == {"format": "json"}

    def test_force_json_e_ignorado_no_online(self, stubs):
        llm.definir_modo_llm("online")
        llm.chamar_llm("ola", force_json=True)
        # Nao ha equivalente no Anthropic — basta nao rebentar e nao vazar kwargs
        assert "force_json" not in stubs.anthropic.kwargs_create
        assert "format" not in stubs.anthropic.kwargs_create

    def test_modo_e_relido_a_cada_chamada(self, stubs):
        llm.definir_modo_llm("online")
        llm.chamar_llm("primeira")
        llm.definir_modo_llm("local")
        llm.chamar_llm("segunda")
        # Ambos os providers foram usados sem reiniciar nada
        assert stubs.anthropic.kwargs_create is not None
        assert stubs.ollama.invocado_com is not None


# ---------- stream_llm ----------

class TestStreamLLM:
    def test_online_faz_yield_dos_pedacos(self, stubs):
        llm.definir_modo_llm("online")
        pedacos = list(llm.stream_llm("ola"))
        assert "".join(pedacos) == "resposta claude"

    def test_local_faz_yield_dos_pedacos(self, stubs):
        llm.definir_modo_llm("local")
        pedacos = list(llm.stream_llm("ola"))
        assert "".join(pedacos) == "resposta ollama"
