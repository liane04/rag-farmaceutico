"""
Funcoes de seguranca: hashing de passwords e tokens JWT.

- As passwords sao guardadas como hash bcrypt; a password em claro nunca
  e persistida.
- A sessao autenticada e representada por um token JWT assinado (HS256),
  com validade definida em config.JWT_EXPIRA_MINUTOS.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from src.config import JWT_ALGORITHM, JWT_EXPIRA_MINUTOS, JWT_SECRET_KEY
from src.auth.modelos import DadosToken


def gerar_hash_password(password: str) -> str:
    """Devolve o hash bcrypt de uma password."""
    hash_bytes = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hash_bytes.decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    """Verifica se uma password corresponde ao hash bcrypt guardado."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _obter_segredo() -> str:
    """Devolve a chave JWT, levantando RuntimeError se nao estiver configurada."""
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY nao esta definida. Acrescenta-a ao ficheiro .env."
        )
    return JWT_SECRET_KEY


def criar_token(username: str, papel: str) -> str:
    """Cria um token JWT assinado para um utilizador autenticado."""
    expira_em = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRA_MINUTOS)
    payload = {"sub": username, "papel": papel, "exp": expira_em}
    return jwt.encode(payload, _obter_segredo(), algorithm=JWT_ALGORITHM)


def descodificar_token(token: str) -> DadosToken | None:
    """
    Descodifica e valida um token JWT.

    Devolve os dados do token se for valido; devolve None se estiver
    expirado, mal formado ou com assinatura invalida.
    """
    try:
        payload = jwt.decode(token, _obter_segredo(), algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        # InvalidTokenError cobre token expirado, assinatura invalida e formato invalido.
        return None

    username = payload.get("sub")
    papel = payload.get("papel")
    if not username or papel not in ("farmaceutico", "admin"):
        return None
    return DadosToken(username=username, papel=papel)
