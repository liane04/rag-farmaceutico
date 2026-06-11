"""
Geracao de resposta com citacao de fontes.

Recebe os chunks rerankados e gera uma resposta fundamentada
com citacoes explicitas da documentacao (RF08, RF13).
"""

from dataclasses import dataclass
from typing import Iterator

from src.llm_client import chamar_llm, stream_llm
from src.query.prompt import SYSTEM_PROMPT, PROMPT_GERACAO
from src.query.retriever import ChunkRecuperado


@dataclass
class RespostaRAG:
    """Resposta gerada pelo sistema RAG."""
    resposta: str
    query_usada: str          # query original ou reformulada (CRAG)
    contexto_suficiente: bool  # True se CRAG considerou contexto adequado
    chunks_usados: list[ChunkRecuperado]
    fontes: list[dict]         # lista de {ficheiro, pagina, tipo_documento}


def _formatar_contexto(chunks: list[ChunkRecuperado]) -> str:
    """Formata chunks como contexto para o prompt de geracao."""
    partes = []
    for i, chunk in enumerate(chunks, start=1):
        fonte = f"{chunk.metadados.get('ficheiro', '?')} (p.{chunk.metadados.get('pagina', '?')})"
        partes.append(f"[{i}] Fonte: {fonte}\n{chunk.texto}")
    return "\n\n".join(partes)


def _extrair_fontes(chunks: list[ChunkRecuperado]) -> list[dict]:
    """Extrai lista unica de fontes dos chunks usados."""
    fontes_vistas = set()
    fontes = []
    for chunk in chunks:
        chave = (chunk.metadados.get("ficheiro"), chunk.metadados.get("pagina"))
        if chave not in fontes_vistas:
            fontes_vistas.add(chave)
            fontes.append({
                "ficheiro": chunk.metadados.get("ficheiro"),
                "pagina": chunk.metadados.get("pagina"),
                "tipo_documento": chunk.metadados.get("tipo_documento"),
            })
    return fontes


def gerar_resposta(
    query: str,
    chunks: list[ChunkRecuperado],
    contexto_suficiente: bool = True,
    query_usada: str | None = None,
) -> RespostaRAG:
    """
    Gera uma resposta fundamentada a partir dos chunks recuperados.

    Args:
        query: Pergunta original do utilizador.
        chunks: Chunks rerankados (top_n mais relevantes).
        contexto_suficiente: Flag do CRAG indicando se o contexto e adequado.
        query_usada: Query efetivamente usada (original ou reformulada pelo CRAG).

    Returns:
        RespostaRAG com a resposta, fontes e metadados.
    """
    query_usada = query_usada or query

    # Se nao ha chunks, resposta padrao
    if not chunks:
        return RespostaRAG(
            resposta="A documentação disponível não contém informação suficiente "
                     "para responder a esta questão.",
            query_usada=query_usada,
            contexto_suficiente=False,
            chunks_usados=[],
            fontes=[],
        )

    contexto = _formatar_contexto(chunks)
    prompt_user = PROMPT_GERACAO.format(contexto=contexto, query=query_usada)

    texto_resposta = chamar_llm(
        prompt=prompt_user,
        system=SYSTEM_PROMPT,
        max_tokens=1500,
        temperature=0.2,
    )

    # Adicionar aviso se contexto insuficiente (CRAG)
    if not contexto_suficiente:
        aviso = ("\n\nNOTA: O sistema identificou que a documentação disponível "
                 "pode não conter toda a informação necessária para uma resposta completa. "
                 "Consulte a documentação original para confirmação.")
        texto_resposta += aviso

    return RespostaRAG(
        resposta=texto_resposta,
        query_usada=query_usada,
        contexto_suficiente=contexto_suficiente,
        chunks_usados=chunks,
        fontes=_extrair_fontes(chunks),
    )


def gerar_resposta_stream(
    query: str,
    chunks: list[ChunkRecuperado],
    contexto_suficiente: bool = True,
    query_usada: str | None = None,
) -> Iterator[str]:
    """
    Versao streaming de `gerar_resposta`. Faz yield de pedacos de texto a medida
    que o LLM os produz, usando `client.messages.stream()` do SDK Anthropic.

    Nao devolve um `RespostaRAG` — o caller compoe a resposta final ao acumular
    os pedacos. As fontes ja sao conhecidas antes de o stream comecar (vem dos
    chunks rerankados), pelo que o caller pode envia-las imediatamente.

    Args:
        query: Pergunta a responder (ja reformulada se houver historico/CRAG).
        chunks: Chunks rerankados que servem de contexto.
        contexto_suficiente: Flag do CRAG.
        query_usada: Query efectivamente usada (so para coerencia com gerar_resposta).

    Yields:
        Pedacos de texto da resposta a medida que sao gerados.
    """
    query_usada = query_usada or query

    if not chunks:
        yield ("A documentação disponível não contém informação suficiente "
               "para responder a esta questão.")
        return

    contexto = _formatar_contexto(chunks)
    prompt_user = PROMPT_GERACAO.format(contexto=contexto, query=query_usada)

    for texto in stream_llm(
        prompt=prompt_user,
        system=SYSTEM_PROMPT,
        max_tokens=1500,
        temperature=0.2,
    ):
        yield texto

    # Aviso de contexto insuficiente acrescentado no fim (mesmo formato que a
    # versao nao-streaming). Vai como ultimo pedaco apos o LLM ter terminado.
    if not contexto_suficiente:
        yield ("\n\nNOTA: O sistema identificou que a documentação disponível "
               "pode não conter toda a informação necessária para uma resposta completa. "
               "Consulte a documentação original para confirmação.")
