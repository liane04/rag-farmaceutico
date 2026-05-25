"""
Registo de auditoria das interacoes com o sistema (RF09, EU AI Act Art. 12).

Cada consulta ao sistema RAG e gravada como uma linha na tabela SQLite
`consultas`. O registo e apenas inserido -- nunca alterado nem apagado --
mantendo o caracter append-only do log de auditoria.

A mesma tabela serve o endpoint /audit (visao global, para administradores)
e o /historico (consultas de um utilizador).
"""

from datetime import datetime, timezone

from src.auth.db import inserir_consulta


def registar_consulta(
    query_original: str,
    query_usada: str,
    contexto_suficiente: bool,
    resposta: str,
    fontes: list[dict],
    num_chunks: int,
    duracao_segundos: float,
    fidelidade: float | None = None,
    ip_cliente: str | None = None,
    session_id: str | None = None,
    utilizador: str | None = None,
    papel: str | None = None,
) -> int:
    """
    Regista uma consulta na tabela de auditoria `consultas`.

    Args:
        query_original: Pergunta original do utilizador.
        query_usada: Query apos possivel reformulacao.
        contexto_suficiente: Flag do CRAG.
        resposta: Texto da resposta gerada.
        fontes: Lista de fontes citadas.
        num_chunks: Numero de chunks usados.
        duracao_segundos: Tempo total do pipeline.
        fidelidade: Score de fidelidade do output guard.
        ip_cliente: IP do cliente (opcional).
        session_id: Identificador da sessao de chat.
        utilizador: Username do utilizador autenticado (None se anonimo).
        papel: Papel do utilizador autenticado (None se anonimo).

    Returns:
        id do registo criado na tabela `consultas`.
    """
    registo = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "utilizador": utilizador,
        "papel": papel,
        "query_original": query_original,
        "query_usada": query_usada,
        "contexto_suficiente": contexto_suficiente,
        "resposta": resposta,
        "fontes": fontes,
        "num_chunks": num_chunks,
        "duracao_segundos": round(duracao_segundos, 2),
        "fidelidade": fidelidade,
        "ip_cliente": ip_cliente,
    }
    return inserir_consulta(registo)
