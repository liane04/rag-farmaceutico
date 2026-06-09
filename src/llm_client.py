"""
Cliente LLM partilhado, multi-provider (Anthropic / Ollama).

Expoe uma interface unificada para os 4 callsites que precisam de chamar
um LLM (reranker, CRAG, generator, output_guard), abstraindo qual provider
esta ativo. O modo e controlado por uma definicao global persistida em
SQLite (`llm_mode`), alteravel pelo admin via API/UI.

- "online" (default): usa Claude (claude-sonnet-4-6) via Anthropic SDK
- "local": usa Ollama (modelo configuravel via OLLAMA_MODEL) via langchain-ollama

A escolha e re-lida em cada chamada para permitir que o admin troque sem
reiniciar o servico.
"""

from typing import Iterator

from anthropic import Anthropic

from src.config import (
    ANTHROPIC_API_KEY,
    GENERATIVE_MODEL,
    LLM_MODE_DEFAULT,
    OLLAMA_HOST,
    OLLAMA_MODEL,
)


# Chave da definicao na BD que guarda o modo activo.
_CHAVE_MODO = "llm_mode"

# Clientes inicializados preguicosamente; partilhados entre chamadas.
_cliente_anthropic: Anthropic | None = None
_cliente_ollama = None  # ChatOllama, importado preguicosamente


# --- Estado: modo activo ---

def obter_modo_llm() -> str:
    """Devolve "online" ou "local". Le da BD; se nao existir, devolve default."""
    # Import preguicoso para evitar ciclo (db.py importa de config, llm_client importa db).
    from src.auth.db import obter_definicao
    modo = obter_definicao(_CHAVE_MODO, default=LLM_MODE_DEFAULT)
    return modo if modo in ("online", "local") else LLM_MODE_DEFAULT


def definir_modo_llm(modo: str) -> None:
    """Atualiza o modo activo. Aceita apenas "online" ou "local"."""
    if modo not in ("online", "local"):
        raise ValueError(f"Modo LLM invalido: {modo!r}. Use 'online' ou 'local'.")
    from src.auth.db import definir_definicao
    definir_definicao(_CHAVE_MODO, modo)


# --- Clientes: inicializacao preguicosa ---

def _obter_cliente_anthropic() -> Anthropic:
    global _cliente_anthropic
    if _cliente_anthropic is None:
        _cliente_anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _cliente_anthropic


def _obter_cliente_ollama(temperature: float = 0.0):
    """Devolve um ChatOllama configurado. Recria se a temperatura mudar."""
    global _cliente_ollama
    # Import preguicoso para nao obrigar a presenca de langchain-ollama
    # quando o sistema esta em modo online.
    from langchain_ollama import ChatOllama
    # ChatOllama nao permite alterar temperature apos criacao, entao
    # recriamos quando muda. Para callsites com temperatura fixa o cache funciona.
    if _cliente_ollama is None or _cliente_ollama.temperature != temperature:
        _cliente_ollama = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_HOST,
            temperature=temperature,
        )
    return _cliente_ollama


# --- API unificada ---

def chamar_llm(
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> str:
    """
    Chama o LLM activo (Anthropic ou Ollama) e devolve a resposta como texto.

    Args:
        prompt: Mensagem do utilizador.
        system: Mensagem de sistema (opcional).
        max_tokens: Limite de tokens da resposta. (Ollama ignora — usa configuracao do modelo.)
        temperature: Temperatura de amostragem.

    Returns:
        Texto da resposta (strip aplicado).
    """
    modo = obter_modo_llm()

    if modo == "local":
        from langchain_core.messages import HumanMessage, SystemMessage
        cliente = _obter_cliente_ollama(temperature=temperature)
        mensagens = []
        if system:
            mensagens.append(SystemMessage(content=system))
        mensagens.append(HumanMessage(content=prompt))
        resposta = cliente.invoke(mensagens)
        return resposta.content.strip()

    # online (Anthropic Claude)
    cliente = _obter_cliente_anthropic()
    kwargs = {
        "model": GENERATIVE_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    resposta = cliente.messages.create(**kwargs)
    return resposta.content[0].text.strip()


def stream_llm(
    prompt: str,
    system: str = "",
    max_tokens: int = 1500,
    temperature: float = 0.2,
) -> Iterator[str]:
    """
    Versao streaming de `chamar_llm`. Faz yield de pedacos de texto a medida que
    o LLM os produz.

    Args:
        prompt: Mensagem do utilizador.
        system: Mensagem de sistema (opcional).
        max_tokens: Limite de tokens (so Anthropic).
        temperature: Temperatura de amostragem.

    Yields:
        Pedacos de texto da resposta.
    """
    modo = obter_modo_llm()

    if modo == "local":
        from langchain_core.messages import HumanMessage, SystemMessage
        cliente = _obter_cliente_ollama(temperature=temperature)
        mensagens = []
        if system:
            mensagens.append(SystemMessage(content=system))
        mensagens.append(HumanMessage(content=prompt))
        for pedaco in cliente.stream(mensagens):
            texto = pedaco.content
            if texto:
                yield texto
        return

    # online (Anthropic Claude)
    cliente = _obter_cliente_anthropic()
    kwargs = {
        "model": GENERATIVE_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    with cliente.messages.stream(**kwargs) as stream:
        for texto in stream.text_stream:
            if texto:
                yield texto


# --- Compatibilidade retro ---
# Mantem a funcao `obter_cliente()` para qualquer codigo que ainda a use,
# mas marca-a como descontinuada — devolve sempre o cliente Anthropic.
def obter_cliente() -> Anthropic:
    """[DESCONTINUADA] Use chamar_llm/stream_llm em vez do cliente directo."""
    return _obter_cliente_anthropic()
