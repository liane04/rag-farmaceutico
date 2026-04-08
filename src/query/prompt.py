"""
Templates de prompt para o sistema RAG farmaceutico.

Centraliza todos os prompts usados no pipeline de consulta,
facilitando a manutencao e auditoria (EU AI Act, Art. 13).
"""

SYSTEM_PROMPT = """Es um assistente farmaceutico especializado que responde a questoes
sobre medicamentos com base EXCLUSIVAMENTE na documentacao fornecida.

REGRAS OBRIGATORIAS:
1. Responde APENAS com informacao presente nos excertos fornecidos.
2. Cita SEMPRE a fonte no formato [Fonte: ficheiro, p.X] apos cada afirmacao.
3. Se a informacao nos excertos for insuficiente para responder, diz explicitamente:
   "A documentacao disponivel nao contem informacao suficiente para responder a esta questao."
4. NAO inventes nem complementes com conhecimento externo.
5. Usa linguagem clara e acessivel, adequada a profissionais de saude.
6. Inclui SEMPRE o disclaimer no final da resposta.

DISCLAIMER (incluir sempre no final):
---
AVISO: Esta informacao e gerada automaticamente a partir de documentacao farmaceutica oficial
e destina-se apenas a apoio a decisao. Nao substitui o julgamento clinico do profissional
de saude nem a consulta da documentacao original. Verifique sempre as fontes citadas."""


PROMPT_GERACAO = """Com base EXCLUSIVAMENTE nos seguintes excertos de documentacao farmaceutica,
responde a pergunta do utilizador.

EXCERTOS:
{contexto}

PERGUNTA: {query}

Lembra-te: cita as fontes, nao inventes informacao, e inclui o disclaimer no final."""


PROMPT_CRAG_AVALIACAO = """Avalia se os seguintes excertos de documentacao farmaceutica
contem informacao SUFICIENTE e RELEVANTE para responder a pergunta.

PERGUNTA: {query}

EXCERTOS:
{contexto}

Responde APENAS com um JSON (sem texto adicional):
{{
    "relevante": true/false,
    "confianca": 0.0 a 1.0,
    "razao": "breve justificacao"
}}"""


PROMPT_CRAG_REFORMULACAO = """A pergunta original nao obteve resultados suficientes
na documentacao farmaceutica disponivel.

PERGUNTA ORIGINAL: {query}

Reformula a pergunta de forma a melhorar a recuperacao de informacao.
Tenta usar termos tecnicos farmaceuticos equivalentes, nomes de principios ativos,
ou reformulacoes mais especificas.

Responde APENAS com a pergunta reformulada, sem explicacoes."""
