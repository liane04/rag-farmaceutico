"""
Reranking de chunks com LLM-as-Judge.

Recebe os top_k chunks da recuperacao hibrida e seleciona os top_n
mais relevantes para a query, usando um LLM como juiz de relevancia.

Isto melhora a precisao do contexto enviado ao gerador (RF04).
"""

import json
from dataclasses import replace

from src.config import RERANK_TOP_N
from src.llm_client import chamar_llm
from src.query.retriever import ChunkRecuperado


SYSTEM_PROMPT = (
    "Es um avaliador de relevancia para um sistema farmaceutico. "
    "Avalias excertos de documentos farmaceuticos quanto a sua relevancia para "
    "uma pergunta clinica, devolvendo scores estruturados em JSON."
)

PROMPT_RERANK = """Dada a pergunta do utilizador e uma lista de excertos de documentos farmaceuticos,
avalia a relevancia de cada excerto numa escala de 0 a 10:
- 0: completamente irrelevante
- 5: parcialmente relevante
- 10: diretamente responde a pergunta

Responde APENAS com um JSON array de objetos, sem texto adicional:
[{{"indice": 0, "score": 8, "razao": "breve justificacao"}}, ...]

PERGUNTA: {query}

EXCERTOS:
{excertos}"""

# Truncagem por excerto. Os chunks tem CHUNK_SIZE=4000 chars; permitimos
# margem para edge cases do splitter sem inundar o prompt.
MAX_DOC_CHARS = 4000


def _truncar(texto: str) -> str:
    """Trunca o excerto e sinaliza ao LLM que houve corte."""
    if len(texto) <= MAX_DOC_CHARS:
        return texto
    return texto[:MAX_DOC_CHARS] + " [...]"


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

    # Formatar excertos para o prompt
    partes = []
    for i, chunk in enumerate(chunks):
        fonte = f"{chunk.metadados.get('ficheiro', '?')} (p.{chunk.metadados.get('pagina', '?')})"
        partes.append(f"\n[{i}] Fonte: {fonte}\n{_truncar(chunk.texto)}\n")
    excertos_texto = "".join(partes)

    prompt = PROMPT_RERANK.format(query=query, excertos=excertos_texto)

    texto_resposta = chamar_llm(
        prompt=prompt,
        system=SYSTEM_PROMPT,
        max_tokens=1024,
        temperature=0,
    )

    # Parsear resposta
    try:
        if texto_resposta.startswith("```"):
            texto_resposta = texto_resposta.split("\n", 1)[1]
            texto_resposta = texto_resposta.rsplit("```", 1)[0]
        avaliacoes = json.loads(texto_resposta)
    except (json.JSONDecodeError, IndexError, KeyError):
        # Fallback: manter a ordem original do retriever
        print("[reranker] AVISO: Falha ao parsear resposta do LLM. A usar ordem original.")
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
