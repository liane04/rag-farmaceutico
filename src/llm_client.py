"""
Cliente Anthropic partilhado (singleton com inicializacao preguicosa).

Evita recriar `Anthropic(api_key=...)` em cada chamada LLM (reranker, CRAG,
generator, input_guard, output_guard), poupando o handshake HTTP/TLS repetido
e centralizando a configuracao do cliente.
"""

from anthropic import Anthropic

from src.config import ANTHROPIC_API_KEY


_cliente: Anthropic | None = None


def obter_cliente() -> Anthropic:
    """Devolve a instancia partilhada do cliente Anthropic."""
    global _cliente
    if _cliente is None:
        _cliente = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _cliente
