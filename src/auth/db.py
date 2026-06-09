"""
Acesso a base de dados SQLite (utilizadores e registos de consulta).

Guarda duas tabelas:
- utilizadores: contas de utilizador (username, hash da password, papel)
- consultas: registo de auditoria de cada consulta ao sistema RAG; serve
  tambem o historico por utilizador

Cada operacao abre e fecha a sua propria ligacao -- o SQLite nao permite
partilhar ligacoes entre threads e a API corre multi-thread.
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from src.config import AUTH_DB_PATH
from src.auth.modelos import RegistoConsulta, UtilizadorEmBD


# Colunas da tabela `consultas` (sem o id, gerado automaticamente).
# Conduzem o INSERT e o SELECT de forma consistente.
_COLUNAS_CONSULTA = [
    "session_id", "timestamp", "utilizador", "papel", "query_original",
    "query_usada", "contexto_suficiente", "resposta", "fontes", "num_chunks",
    "duracao_segundos", "fidelidade", "ip_cliente",
]
_SELECT_CONSULTA = "SELECT id, " + ", ".join(_COLUNAS_CONSULTA) + " FROM consultas"


def _ligar() -> sqlite3.Connection:
    """Abre uma ligacao a base de dados SQLite, criando a pasta se necessario."""
    Path(AUTH_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    ligacao = sqlite3.connect(AUTH_DB_PATH)
    ligacao.row_factory = sqlite3.Row  # permite aceder as colunas por nome
    return ligacao


def inicializar_bd() -> None:
    """Cria as tabelas (utilizadores, consultas, definicoes) se ainda nao existirem."""
    with closing(_ligar()) as ligacao:
        ligacao.execute(
            """
            CREATE TABLE IF NOT EXISTS utilizadores (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                papel         TEXT NOT NULL CHECK (papel IN ('farmaceutico', 'admin')),
                criado_em     TEXT NOT NULL
            )
            """
        )
        ligacao.execute(
            """
            CREATE TABLE IF NOT EXISTS consultas (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          TEXT,
                timestamp           TEXT NOT NULL,
                utilizador          TEXT,
                papel               TEXT,
                query_original      TEXT NOT NULL,
                query_usada         TEXT,
                contexto_suficiente INTEGER,
                resposta            TEXT,
                fontes              TEXT,
                num_chunks          INTEGER,
                duracao_segundos    REAL,
                fidelidade          REAL,
                ip_cliente          TEXT
            )
            """
        )
        # Definicoes globais do sistema (key/value).
        # Usado para LLM_MODE (online/local) e potenciais futuras definicoes.
        ligacao.execute(
            """
            CREATE TABLE IF NOT EXISTS definicoes (
                chave   TEXT PRIMARY KEY,
                valor   TEXT NOT NULL,
                alterado_em TEXT NOT NULL
            )
            """
        )
        ligacao.commit()


# --- Definicoes globais (chave/valor) ---

def obter_definicao(chave: str, default: str | None = None) -> str | None:
    """Devolve o valor de uma definicao, ou `default` se nao existir."""
    with closing(_ligar()) as ligacao:
        linha = ligacao.execute(
            "SELECT valor FROM definicoes WHERE chave = ?",
            (chave,),
        ).fetchone()
    return linha["valor"] if linha is not None else default


def definir_definicao(chave: str, valor: str) -> None:
    """Cria ou atualiza uma definicao global."""
    agora = datetime.now(timezone.utc).isoformat()
    with closing(_ligar()) as ligacao:
        ligacao.execute(
            """
            INSERT INTO definicoes (chave, valor, alterado_em)
            VALUES (?, ?, ?)
            ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, alterado_em = excluded.alterado_em
            """,
            (chave, valor, agora),
        )
        ligacao.commit()


# --- Utilizadores ---

def _linha_para_utilizador(linha: sqlite3.Row) -> UtilizadorEmBD:
    """Converte uma linha da tabela `utilizadores` no modelo UtilizadorEmBD."""
    return UtilizadorEmBD(
        id=linha["id"],
        username=linha["username"],
        password_hash=linha["password_hash"],
        papel=linha["papel"],
        criado_em=linha["criado_em"],
    )


def obter_utilizador(username: str) -> UtilizadorEmBD | None:
    """Devolve o utilizador com o username dado, ou None se nao existir."""
    with closing(_ligar()) as ligacao:
        linha = ligacao.execute(
            "SELECT id, username, password_hash, papel, criado_em "
            "FROM utilizadores WHERE username = ?",
            (username,),
        ).fetchone()
    return _linha_para_utilizador(linha) if linha is not None else None


def criar_utilizador(username: str, password_hash: str, papel: str) -> UtilizadorEmBD:
    """
    Insere um novo utilizador na base de dados.

    Levanta ValueError se ja existir um utilizador com o mesmo username.
    """
    criado_em = datetime.now(timezone.utc).isoformat()
    try:
        with closing(_ligar()) as ligacao:
            cursor = ligacao.execute(
                "INSERT INTO utilizadores (username, password_hash, papel, criado_em) "
                "VALUES (?, ?, ?, ?)",
                (username, password_hash, papel, criado_em),
            )
            ligacao.commit()
            novo_id = cursor.lastrowid
    except sqlite3.IntegrityError as erro:
        raise ValueError(f"Ja existe um utilizador com o username '{username}'.") from erro

    return UtilizadorEmBD(
        id=novo_id,
        username=username,
        password_hash=password_hash,
        papel=papel,
        criado_em=criado_em,
    )


def atualizar_password_utilizador(username: str, password_hash: str) -> None:
    """Atualiza o hash da password de um utilizador existente."""
    with closing(_ligar()) as ligacao:
        ligacao.execute(
            "UPDATE utilizadores SET password_hash = ? WHERE username = ?",
            (password_hash, username),
        )
        ligacao.commit()


def listar_utilizadores() -> list[UtilizadorEmBD]:
    """Devolve todos os utilizadores registados, ordenados por id."""
    with closing(_ligar()) as ligacao:
        linhas = ligacao.execute(
            "SELECT id, username, password_hash, papel, criado_em "
            "FROM utilizadores ORDER BY id"
        ).fetchall()
    return [_linha_para_utilizador(linha) for linha in linhas]


# --- Consultas (auditoria / historico) ---

def _linha_para_consulta(linha: sqlite3.Row) -> RegistoConsulta:
    """Converte uma linha da tabela `consultas` no modelo RegistoConsulta."""
    contexto = linha["contexto_suficiente"]
    return RegistoConsulta(
        id=linha["id"],
        session_id=linha["session_id"],
        timestamp=linha["timestamp"],
        utilizador=linha["utilizador"],
        papel=linha["papel"],
        query_original=linha["query_original"],
        query_usada=linha["query_usada"],
        contexto_suficiente=bool(contexto) if contexto is not None else None,
        resposta=linha["resposta"],
        fontes=json.loads(linha["fontes"]) if linha["fontes"] else [],
        num_chunks=linha["num_chunks"],
        duracao_segundos=linha["duracao_segundos"],
        fidelidade=linha["fidelidade"],
        ip_cliente=linha["ip_cliente"],
    )


def inserir_consulta(registo: dict) -> int:
    """
    Insere um registo de consulta na tabela `consultas`.

    `registo` e um dict com as chaves de _COLUNAS_CONSULTA. Devolve o id
    da linha criada.
    """
    valores = []
    for coluna in _COLUNAS_CONSULTA:
        valor = registo.get(coluna)
        if coluna == "fontes":
            valor = json.dumps(valor or [], ensure_ascii=False)
        elif coluna == "contexto_suficiente" and valor is not None:
            valor = int(valor)
        valores.append(valor)

    marcadores = ", ".join(["?"] * len(_COLUNAS_CONSULTA))
    with closing(_ligar()) as ligacao:
        cursor = ligacao.execute(
            f"INSERT INTO consultas ({', '.join(_COLUNAS_CONSULTA)}) VALUES ({marcadores})",
            valores,
        )
        ligacao.commit()
        return cursor.lastrowid


def listar_consultas(limite: int = 200) -> list[RegistoConsulta]:
    """Devolve as consultas mais recentes (de todos), da mais recente para a mais antiga."""
    with closing(_ligar()) as ligacao:
        linhas = ligacao.execute(
            f"{_SELECT_CONSULTA} ORDER BY id DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [_linha_para_consulta(linha) for linha in linhas]


def listar_consultas_por_utilizador(username: str, limite: int = 200) -> list[RegistoConsulta]:
    """Devolve as consultas de um utilizador, da mais recente para a mais antiga."""
    with closing(_ligar()) as ligacao:
        linhas = ligacao.execute(
            f"{_SELECT_CONSULTA} WHERE utilizador = ? ORDER BY id DESC LIMIT ?",
            (username, limite),
        ).fetchall()
    return [_linha_para_consulta(linha) for linha in linhas]
