"""
Guardrail de input — validacao de dominio e detecao de prompt injection (RF05).

Valida que a query do utilizador:
1. Esta dentro do dominio farmaceutico
2. Nao contem tentativas de prompt injection
"""

import re

from anthropic import Anthropic

from src.config import ANTHROPIC_API_KEY, GENERATIVE_MODEL


# Padroes suspeitos de prompt injection
PADROES_INJECTION = [
    r"ignor[ae]\s+(todas?\s+)?(as\s+)?instruc",
    r"esquece\s+(tudo|todas?\s+instruc)",
    r"es\s+agora\s+um",
    r"finge\s+que",
    r"novo\s+papel",
    r"override",
    r"system\s*prompt",
    r"jailbreak",
    r"DAN\s+mode",
    r"ignore\s+(all\s+)?previous",
    r"forget\s+(all\s+)?instructions",
    r"you\s+are\s+now",
    r"pretend\s+to\s+be",
]

# Comprimento minimo e maximo da query
MIN_QUERY_LEN = 5
MAX_QUERY_LEN = 2000


def _verificar_injection(query: str) -> tuple[bool, str]:
    """
    Verifica padroes de prompt injection com regex.

    Returns:
        (is_safe, razao)
    """
    query_lower = query.lower()
    for padrao in PADROES_INJECTION:
        if re.search(padrao, query_lower):
            return False, f"Padrao de prompt injection detetado: {padrao}"
    return True, ""


def _verificar_comprimento(query: str) -> tuple[bool, str]:
    """Verifica se o comprimento da query e valido."""
    if len(query.strip()) < MIN_QUERY_LEN:
        return False, "Query demasiado curta. Por favor, elabore a sua questao."
    if len(query.strip()) > MAX_QUERY_LEN:
        return False, "Query demasiado longa. Por favor, simplifique a sua questao."
    return True, ""


def _verificar_dominio(query: str) -> tuple[bool, str]:
    """
    Verifica se a query esta no dominio farmaceutico usando o Claude.

    Returns:
        (is_in_domain, razao)
    """
    prompt = f"""Analisa a seguinte pergunta e determina se esta relacionada com o dominio
farmaceutico (medicamentos, farmacos, principios ativos, efeitos secundarios,
posologia, interacoes medicamentosas, bulas, monografias, guidelines farmaceuticas).

Responde APENAS com "SIM" ou "NAO" seguido de uma breve justificacao.

PERGUNTA: {query}"""

    cliente = Anthropic(api_key=ANTHROPIC_API_KEY)
    resposta = cliente.messages.create(
        model=GENERATIVE_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )

    texto = resposta.content[0].text.strip().upper()
    if texto.startswith("SIM"):
        return True, ""
    else:
        return False, "Esta questao parece estar fora do dominio farmaceutico."


def validar_input(query: str) -> tuple[bool, str]:
    """
    Valida a query do utilizador.

    Executa 3 verificacoes por ordem (da mais barata a mais cara):
    1. Comprimento
    2. Prompt injection (regex)
    3. Dominio farmaceutico (LLM)

    Args:
        query: Texto da pergunta do utilizador.

    Returns:
        Tuplo (valido, mensagem_erro).
        Se valido=True, mensagem_erro e string vazia.
    """
    # 1. Comprimento (instantaneo)
    valido, msg = _verificar_comprimento(query)
    if not valido:
        print(f"[input_guard] Rejeitado (comprimento): {msg}")
        return False, msg

    # 2. Prompt injection (regex, instantaneo)
    valido, msg = _verificar_injection(query)
    if not valido:
        print(f"[input_guard] Rejeitado (injection): {msg}")
        return False, "Pedido invalido. Por favor, reformule a sua questao."

    # 3. Dominio farmaceutico (LLM, mais lento)
    valido, msg = _verificar_dominio(query)
    if not valido:
        print(f"[input_guard] Rejeitado (dominio): {msg}")
        return False, msg

    return True, ""
