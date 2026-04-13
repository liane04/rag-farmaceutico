"""
Guardrail de output — verificacao de fidelidade e disclaimer obrigatorio (RF13, RF14).

Verifica que a resposta gerada:
1. E fiel ao contexto fornecido (nao alucina)
2. Contem o disclaimer obrigatorio
"""

import json

# [CLAUDE] from anthropic import Anthropic
import google.generativeai as genai

# [CLAUDE] from src.config import ANTHROPIC_API_KEY, GENERATIVE_MODEL, FAITHFULNESS_THRESHOLD
from src.config import GOOGLE_API_KEY, GENERATIVE_MODEL, FAITHFULNESS_THRESHOLD
from src.query.retriever import ChunkRecuperado


PROMPT_FIDELIDADE = """Es um avaliador de fidelidade para um sistema farmaceutico.

Compara a RESPOSTA gerada com os EXCERTOS originais da documentacao.
Avalia se TODA a informacao na resposta e suportada pelos excertos.

EXCERTOS ORIGINAIS:
{contexto}

RESPOSTA GERADA:
{resposta}

Responde APENAS com um JSON (sem texto adicional):
{{
    "fidelidade": 0.0 a 1.0,
    "problemas": ["lista de afirmacoes sem suporte nos excertos"],
    "veredicto": "fiel" ou "com_problemas"
}}"""


DISCLAIMER_KEYWORDS = [
    "substitui",
    "julgamento",
    "profissional",
    "documentacao original",
    "documentação original",
    "fontes citadas",
]


def verificar_disclaimer(resposta: str) -> tuple[bool, str]:
    """
    Verifica se a resposta contem o disclaimer obrigatorio.

    Returns:
        (tem_disclaimer, mensagem)
    """
    resposta_lower = resposta.lower()
    keywords_encontradas = sum(1 for kw in DISCLAIMER_KEYWORDS if kw in resposta_lower)

    # Pelo menos 2 das keywords devem estar presentes
    if keywords_encontradas >= 2:
        return True, ""

    return False, "Disclaimer obrigatorio em falta ou incompleto."


def verificar_fidelidade(
    resposta: str,
    chunks: list[ChunkRecuperado],
) -> dict:
    """
    Avalia a fidelidade da resposta ao contexto usando um LLM.

    Args:
        resposta: Texto da resposta gerada.
        chunks: Chunks usados como contexto.

    Returns:
        dict com: fidelidade (float), problemas (list), veredicto (str)
    """
    if not chunks:
        return {"fidelidade": 0.0, "problemas": ["Sem contexto para avaliar."], "veredicto": "com_problemas"}

    contexto = "\n\n".join(
        f"[{i}] {c.texto}" for i, c in enumerate(chunks, start=1)
    )

    prompt = PROMPT_FIDELIDADE.format(contexto=contexto, resposta=resposta)

    # --- Gemini ---
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel(model_name=GENERATIVE_MODEL)
    resp = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": 512},
    )
    texto = resp.text.strip()

    # --- [CLAUDE] ---
    # cliente = Anthropic(api_key=ANTHROPIC_API_KEY)
    # resp = cliente.messages.create(
    #     model=GENERATIVE_MODEL,
    #     max_tokens=512,
    #     messages=[{"role": "user", "content": prompt}],
    # )
    # texto = resp.content[0].text.strip()

    try:
        if texto.startswith("```"):
            texto = texto.split("\n", 1)[1]
            texto = texto.rsplit("```", 1)[0]
        return json.loads(texto)
    except (json.JSONDecodeError, IndexError):
        print("[output_guard] AVISO: Falha ao parsear avaliacao de fidelidade.")
        return {"fidelidade": 0.5, "problemas": ["Falha na avaliacao automatica."], "veredicto": "inconclusivo"}


def validar_output(
    resposta: str,
    chunks: list[ChunkRecuperado],
) -> tuple[bool, str, dict]:
    """
    Valida a resposta gerada antes de a devolver ao utilizador.

    Verificacoes:
    1. Presenca do disclaimer obrigatorio
    2. Fidelidade ao contexto (threshold configuravel)

    Args:
        resposta: Texto da resposta gerada.
        chunks: Chunks usados como contexto.

    Returns:
        Tuplo (valido, resposta_final, detalhes):
        - valido: True se passou todas as verificacoes
        - resposta_final: resposta possivelmente anotada com avisos
        - detalhes: dict com metricas de fidelidade
    """
    resposta_final = resposta
    avisos = []

    # 1. Verificar disclaimer
    tem_disclaimer, msg = verificar_disclaimer(resposta)
    if not tem_disclaimer:
        print(f"[output_guard] {msg} A adicionar automaticamente.")
        disclaimer = ("\n\n---\nAVISO: Esta informacao e gerada automaticamente a partir "
                      "de documentacao farmaceutica oficial e destina-se apenas a apoio "
                      "a decisao. Nao substitui o julgamento clinico do profissional "
                      "de saude nem a consulta da documentacao original.")
        resposta_final += disclaimer

    # 2. Verificar fidelidade
    fidelidade = verificar_fidelidade(resposta, chunks)
    score = fidelidade.get("fidelidade", 0)
    print(f"[output_guard] Fidelidade: {score:.2f} (threshold: {FAITHFULNESS_THRESHOLD})")

    if score < FAITHFULNESS_THRESHOLD:
        avisos.append(f"Fidelidade abaixo do threshold ({score:.2f} < {FAITHFULNESS_THRESHOLD})")
        problemas = fidelidade.get("problemas", [])
        if problemas:
            aviso_fidelidade = ("\n\nNOTA DE QUALIDADE: O sistema detetou que algumas "
                                "afirmacoes nesta resposta podem nao estar totalmente "
                                "suportadas pela documentacao de origem. Consulte as "
                                "fontes originais para confirmacao.")
            resposta_final += aviso_fidelidade

    valido = score >= FAITHFULNESS_THRESHOLD and not avisos
    return valido, resposta_final, fidelidade
