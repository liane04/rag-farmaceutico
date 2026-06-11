"""
Reranking de chunks com LLM-as-Judge.

Recebe os top_k chunks da recuperacao hibrida e seleciona os top_n
mais relevantes para a query, usando um LLM como juiz de relevancia.

Isto melhora a precisao do contexto enviado ao gerador (RF04).
"""

import json
from dataclasses import replace

from src.config import RERANK_TOP_N
from src.llm_client import chamar_llm, obter_modo_llm
from src.query.retriever import ChunkRecuperado


SYSTEM_PROMPT = (
    "Es um avaliador de relevancia para um sistema farmaceutico. "
    "Avalias excertos de documentos farmaceuticos quanto a sua relevancia para "
    "uma pergunta clinica, devolvendo scores estruturados em JSON."
)

PROMPT_RERANK = """Dada a pergunta do utilizador e uma lista de excertos de documentos farmaceuticos,
avalia a relevancia de CADA excerto numa escala de 0 a 10:
- 0: completamente irrelevante
- 5: parcialmente relevante
- 10: diretamente responde a pergunta

Avalia TODOS os excertos (uma entrada por excerto). Responde APENAS com um JSON
com esta forma exacta, sem texto adicional:
{{"avaliacoes": [{{"indice": 0, "score": 8, "razao": "breve justificacao"}}, {{"indice": 1, "score": 3, "razao": "..."}}]}}

PERGUNTA: {query}

EXCERTOS:
{excertos}"""

# Truncagem por excerto para o prompt do reranker. Online (Claude) aguenta
# margem ampla; em local os modelos pequenos descarrilam com prompts enormes
# (7 chunks x 4000 chars), por isso truncamos muito mais — o inicio do chunk
# chega para julgar relevancia.
MAX_DOC_CHARS = 4000
MAX_DOC_CHARS_LOCAL = 700


def _truncar(texto: str, limite: int = MAX_DOC_CHARS) -> str:
    """Trunca o excerto e sinaliza ao LLM que houve corte."""
    if len(texto) <= limite:
        return texto
    return texto[:limite] + " [...]"


def rerankar(
    query: str,
    chunks: list[ChunkRecuperado],
    top_n: int = RERANK_TOP_N,
) -> list[ChunkRecuperado]:
    """
    Reordena chunks por relevancia usando LLM como juiz.

    Args:
        query: Pergunta original do utilizador.
        chunks: Chunks recuperados pelo retriever (top_k).
        top_n: Numero de chunks a manter apos reranking.

    Returns:
        Lista dos top_n ChunkRecuperado mais relevantes (copias com score
        normalizado em [0, 1] vindo do LLM). Os chunks originais nao sao mutados.
    """
    if not chunks:
        return []

    if len(chunks) <= top_n:
        return chunks

    # Em modo local truncamos os excertos com mais agressividade (modelos
    # pequenos descarrilam com prompts enormes).
    limite_chars = MAX_DOC_CHARS_LOCAL if obter_modo_llm() == "local" else MAX_DOC_CHARS

    # Formatar excertos para o prompt
    partes = []
    for i, chunk in enumerate(chunks):
        fonte = f"{chunk.metadados.get('ficheiro', '?')} (p.{chunk.metadados.get('pagina', '?')})"
        partes.append(f"\n[{i}] Fonte: {fonte}\n{_truncar(chunk.texto, limite_chars)}\n")
    excertos_texto = "".join(partes)

    prompt = PROMPT_RERANK.format(query=query, excertos=excertos_texto)

    texto_resposta = chamar_llm(
        prompt=prompt,
        system=SYSTEM_PROMPT,
        max_tokens=1024,
        temperature=0,
        force_json=True,
    )

    # Parsear resposta
    try:
        if texto_resposta.startswith("```"):
            texto_resposta = texto_resposta.split("\n", 1)[1]
            texto_resposta = texto_resposta.rsplit("```", 1)[0]
        avaliacoes = json.loads(texto_resposta)
        # Em format=json o Ollama tende a devolver um objeto no topo em vez do
        # array pedido (ex.: {"avaliacoes": [...]} ou {"0": {...}}). Normalizar
        # para a lista de objetos de score.
        if isinstance(avaliacoes, dict):
            listas = [v for v in avaliacoes.values() if isinstance(v, list)]
            if listas:
                avaliacoes = listas[0]
            elif "score" in avaliacoes or "indice" in avaliacoes:
                # Objeto unico de score (o modelo so avaliou um excerto).
                avaliacoes = [avaliacoes]
            else:
                avaliacoes = list(avaliacoes.values())
        avaliacoes = [a for a in avaliacoes if isinstance(a, dict)]
        if not avaliacoes:
            raise ValueError("Sem avaliacoes utilizaveis.")
    except (json.JSONDecodeError, IndexError, KeyError, ValueError, TypeError, AttributeError) as e:
        # Fallback: manter a ordem original do retriever
        print(f"[reranker] AVISO: Falha ao parsear resposta do LLM ({type(e).__name__}): "
              f"{texto_resposta[:150]!r}. A usar ordem original.")
        return chunks[:top_n]

    # Ordenar por score e selecionar top_n
    avaliacoes_ordenadas = sorted(avaliacoes, key=lambda x: x.get("score", 0), reverse=True)
    resultado = []
    for avaliacao in avaliacoes_ordenadas[:top_n]:
        idx = avaliacao.get("indice", 0)
        if 0 <= idx < len(chunks):
            # Clamp [0, 10] protege thresholds a jusante contra alucinacoes
            # do LLM (e.g. score=15 daria 1.5, que dispararia skip-CRAG indevidamente).
            score_bruto = float(avaliacao.get("score", 0))
            score_norm = max(0.0, min(10.0, score_bruto)) / 10.0
            resultado.append(replace(chunks[idx], score=score_norm))

    return resultado
