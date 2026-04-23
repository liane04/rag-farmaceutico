"""
Corrective RAG (CRAG) — avaliacao de relevancia e reformulacao de query.

Implementa o mecanismo de auto-correcao do pipeline:
1. Avalia se os chunks recuperados sao suficientes para responder
2. Se insuficientes, reformula a query e faz nova recuperacao
3. Se ainda insuficientes, sinaliza para o gerador recusar (RF06, RF07)
"""

import json

from anthropic import Anthropic
from src.config import ANTHROPIC_API_KEY, GENERATIVE_MODEL, RELEVANCE_THRESHOLD
from src.query.prompt import PROMPT_CRAG_AVALIACAO, PROMPT_CRAG_REFORMULACAO
from src.query.retriever import ChunkRecuperado


MAX_TENTATIVAS = 2  # query original + 1 reformulacao


def _formatar_contexto(chunks: list[ChunkRecuperado]) -> str:
    """Formata chunks como texto para incluir no prompt."""
    partes = []
    for i, chunk in enumerate(chunks, start=1):
        fonte = f"{chunk.metadados.get('ficheiro', '?')} (p.{chunk.metadados.get('pagina', '?')})"
        partes.append(f"[{i}] Fonte: {fonte}\n{chunk.texto}")
    return "\n\n".join(partes)


def _chamar_llm(prompt: str, max_tokens: int = 256) -> str:
    """Chama o LLM e devolve o texto da resposta."""
    cliente = Anthropic(api_key=ANTHROPIC_API_KEY)
    resposta = cliente.messages.create(
        model=GENERATIVE_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resposta.content[0].text.strip()


def avaliar_relevancia(
    query: str,
    chunks: list[ChunkRecuperado],
) -> dict:
    """
    Avalia se os chunks recuperados sao relevantes para a query.

    Returns:
        dict com: relevante (bool), confianca (float), razao (str)
    """
    if not chunks:
        return {"relevante": False, "confianca": 0.0, "razao": "Nenhum chunk recuperado."}

    contexto = _formatar_contexto(chunks)
    prompt = PROMPT_CRAG_AVALIACAO.format(query=query, contexto=contexto)

    try:
        texto = _chamar_llm(prompt, max_tokens=256)
        if texto.startswith("```"):
            texto = texto.split("\n", 1)[1]
            texto = texto.rsplit("```", 1)[0]
        resultado = json.loads(texto)
        return resultado
    except (json.JSONDecodeError, IndexError):
        # Fallback conservador: considera relevante para nao bloquear
        print("[crag] AVISO: Falha ao parsear avaliacao. A assumir relevante.")
        return {"relevante": True, "confianca": 0.5, "razao": "Falha no parsing da avaliacao."}


def reformular_query(query: str) -> str:
    """
    Reformula a query para melhorar a recuperacao.

    Usa o LLM para gerar uma versao alternativa com termos
    tecnicos farmaceuticos que possam melhorar o recall.
    """
    prompt = PROMPT_CRAG_REFORMULACAO.format(query=query)
    nova_query = _chamar_llm(prompt, max_tokens=256)
    print(f"[crag] Query reformulada: '{query}' -> '{nova_query}'")
    return nova_query


def crag_pipeline(
    query: str,
    chunks: list[ChunkRecuperado],
    recuperar_fn=None,
) -> tuple[list[ChunkRecuperado], bool, str]:
    """
    Pipeline CRAG completo: avalia, reformula se necessario, re-recupera.

    Args:
        query: Pergunta original.
        chunks: Chunks ja recuperados e rerankados.
        recuperar_fn: Funcao de recuperacao para re-tentativa (opcional).

    Returns:
        Tuplo com:
        - chunks finais (possivelmente atualizados)
        - contexto_suficiente (bool)
        - query usada (original ou reformulada)
    """
    # Primeira avaliacao
    avaliacao = avaliar_relevancia(query, chunks)
    print(f"[crag] Avaliacao: relevante={avaliacao.get('relevante')}, "
          f"confianca={avaliacao.get('confianca', 0):.2f}")

    if avaliacao.get("relevante") and avaliacao.get("confianca", 0) >= RELEVANCE_THRESHOLD:
        return chunks, True, query

    # Tentar reformulacao se temos funcao de recuperacao
    if recuperar_fn is not None:
        print("[crag] Contexto insuficiente. A reformular query...")
        nova_query = reformular_query(query)

        novos_chunks = recuperar_fn(nova_query)
        nova_avaliacao = avaliar_relevancia(nova_query, novos_chunks)
        print(f"[crag] Re-avaliacao: relevante={nova_avaliacao.get('relevante')}, "
              f"confianca={nova_avaliacao.get('confianca', 0):.2f}")

        if nova_avaliacao.get("relevante") and nova_avaliacao.get("confianca", 0) >= RELEVANCE_THRESHOLD:
            return novos_chunks, True, nova_query

        # Se a reformulacao trouxe melhores resultados, usa-os
        if nova_avaliacao.get("confianca", 0) > avaliacao.get("confianca", 0):
            return novos_chunks, False, nova_query

    # Contexto insuficiente apos todas as tentativas
    return chunks, False, query
