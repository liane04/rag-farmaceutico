"""
Registo de auditoria para todas as interacoes com o sistema (RF09, EU AI Act Art. 12).

Grava um registo imutavel (append-only) de cada consulta com:
- Timestamp
- Query original e query usada (se reformulada pelo CRAG)
- Chunks recuperados e scores
- Resposta gerada
- Metricas de qualidade (fidelidade, contexto suficiente)
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


AUDIT_DIR = Path(__file__).parent.parent.parent / "data" / "audit"


def _garantir_pasta():
    """Cria a pasta de auditoria se nao existir."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


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
) -> str:
    """
    Regista uma consulta no log de auditoria.

    Args:
        query_original: Pergunta original do utilizador.
        query_usada: Query apos possivel reformulacao CRAG.
        contexto_suficiente: Flag do CRAG.
        resposta: Texto da resposta gerada.
        fontes: Lista de fontes citadas.
        num_chunks: Numero de chunks usados.
        duracao_segundos: Tempo total do pipeline.
        fidelidade: Score de fidelidade do output guard.
        ip_cliente: IP do cliente (opcional).

    Returns:
        ID do registo de auditoria.
    """
    _garantir_pasta()

    timestamp = datetime.now(timezone.utc)
    audit_id = timestamp.strftime("%Y%m%d_%H%M%S_%f")

    registo = {
        "id": audit_id,
        "timestamp": timestamp.isoformat(),
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

    # Append ao ficheiro diario (um ficheiro por dia)
    ficheiro = AUDIT_DIR / f"audit_{timestamp.strftime('%Y-%m-%d')}.jsonl"
    with open(ficheiro, "a", encoding="utf-8") as f:
        f.write(json.dumps(registo, ensure_ascii=False) + "\n")

    return audit_id
