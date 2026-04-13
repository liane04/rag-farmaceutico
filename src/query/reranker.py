"""
Reranking de chunks com LLM-as-Judge.

Recebe os top_k chunks da recuperacao hibrida e seleciona os top_n
mais relevantes para a query, usando um LLM como juiz de relevancia.

Isto melhora a precisao do contexto enviado ao gerador (RF04).
"""

import json

# [CLAUDE] from anthropic import Anthropic
import google.generativeai as genai

# [CLAUDE] from src.config import ANTHROPIC_API_KEY, GENERATIVE_MODEL, RERANK_TOP_N
from src.config import GOOGLE_API_KEY, GENERATIVE_MODEL, RERANK_TOP_N
from src.query.retriever import ChunkRecuperado


PROMPT_RERANK = """Es um avaliador de relevancia para um sistema farmaceutico.

Dada a pergunta do utilizador e uma lista de excertos de documentos farmaceuticos,
avalia a relevancia de cada excerto numa escala de 0 a 10:
- 0: completamente irrelevante
- 5: parcialmente relevante
- 10: diretamente responde a pergunta

Responde APENAS com um JSON array de objetos, sem texto adicional:
[{{"indice": 0, "score": 8, "razao": "breve justificacao"}}, ...]

PERGUNTA: {query}

EXCERTOS:
{excertos}"""


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
        Lista dos top_n ChunkRecuperado mais relevantes, com score atualizado.
    """
    if not chunks:
        return []

    if len(chunks) <= top_n:
        return chunks

    # Formatar excertos para o prompt
    excertos_texto = ""
    for i, chunk in enumerate(chunks):
        fonte = f"{chunk.metadados.get('ficheiro', '?')} (p.{chunk.metadados.get('pagina', '?')})"
        excertos_texto += f"\n[{i}] Fonte: {fonte}\n{chunk.texto[:1500]}\n"

    prompt = PROMPT_RERANK.format(query=query, excertos=excertos_texto)

    # --- Gemini ---
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel(model_name=GENERATIVE_MODEL)
    resposta = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": 1024},
    )
    texto_resposta = resposta.text.strip()

    # --- [CLAUDE] ---
    # cliente = Anthropic(api_key=ANTHROPIC_API_KEY)
    # resposta = cliente.messages.create(
    #     model=GENERATIVE_MODEL,
    #     max_tokens=1024,
    #     messages=[{"role": "user", "content": prompt}],
    # )
    # texto_resposta = resposta.content[0].text.strip()

    # Parsear resposta
    try:
        # Remover markdown code blocks se presentes
        if texto_resposta.startswith("```"):
            texto_resposta = texto_resposta.split("\n", 1)[1]
            texto_resposta = texto_resposta.rsplit("```", 1)[0]
        avaliacoes = json.loads(texto_resposta)
    except (json.JSONDecodeError, IndexError, KeyError):
        # Fallback: manter a ordem original do retriever
        print("[reranker] AVISO: Falha ao parsear resposta do LLM. A usar ordem original.")
        return chunks[:top_n]

    # Ordenar por score do LLM e selecionar top_n
    avaliacoes_ordenadas = sorted(avaliacoes, key=lambda x: x.get("score", 0), reverse=True)
    resultado = []
    for avaliacao in avaliacoes_ordenadas[:top_n]:
        idx = avaliacao.get("indice", 0)
        if 0 <= idx < len(chunks):
            chunk = chunks[idx]
            # Atualizar score com a avaliacao do LLM (normalizado 0-1)
            chunk.score = avaliacao.get("score", 0) / 10.0
            resultado.append(chunk)

    return resultado
