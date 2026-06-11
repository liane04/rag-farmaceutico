"""
Reformulacao contextual de queries em conversas multi-turn.

Antes de fazer retrieval, reescreve a ultima pergunta do utilizador
de forma autonoma usando o historico da conversa. Por exemplo:

    Historico:
      user: O que e o brufen?
      assistant: O brufen e um anti-inflamatorio com ibuprofeno...
    Pergunta atual: "e a posologia?"
    Query reformulada: "qual a posologia do brufen?"

Isto e o padrao "history-aware retriever" do RAG conversacional: o retriever
recebe sempre uma query autonoma, independentemente de o utilizador usar
referencias implicitas. O resto do pipeline (retriever, reranker, CRAG,
generator) nao precisa de saber que existe historico.
"""

from src.llm_client import chamar_llm
from src.query.prompt import PROMPT_REFORMULACAO_CONTEXTUAL


def _formatar_historia(historia: list) -> str:
    """Formata o historico como texto para incluir no prompt."""
    linhas = []
    for msg in historia:
        # Aceita tanto objectos Pydantic (Mensagem) como dicts
        role = msg.role if hasattr(msg, "role") else msg["role"]
        conteudo = msg.conteudo if hasattr(msg, "conteudo") else msg["conteudo"]
        etiqueta = "Utilizador" if role == "user" else "Assistente"
        linhas.append(f"{etiqueta}: {conteudo}")
    return "\n".join(linhas)


def reformular_com_historia(query: str, historia: list) -> str:
    """
    Reescreve a query como pergunta autonoma usando o historico da conversa.

    Args:
        query: Ultima pergunta do utilizador (potencialmente com referencias implicitas).
        historia: Lista de mensagens anteriores (Mensagem ou dicts {role, conteudo}).

    Returns:
        Query autonoma pronta para o retriever. Se o historico estiver vazio,
        devolve a query inalterada (early return, sem chamada LLM).
    """
    if not historia:
        return query

    prompt = PROMPT_REFORMULACAO_CONTEXTUAL.format(
        historia=_formatar_historia(historia),
        query=query,
    )

    nova_query = chamar_llm(prompt, max_tokens=300, temperature=0).strip()

    # Defesa: se o LLM falhar em devolver algo razoavel, mantem a query original
    if not nova_query or len(nova_query) > 2000:
        return query

    return nova_query
