"""
Dependencies de autenticacao para a API FastAPI.

- utilizador_atual: extrai e valida o token JWT do header Authorization;
  devolve os dados do utilizador autenticado ou levanta HTTP 401.
- utilizador_atual_query: aceita o token no header OU num query param
  `?token=`. Necessario para abrir ficheiros em <a> ou <iframe>, onde o
  browser nao envia o header Authorization.
- requer_admin: alem de exigir autenticacao, exige o papel 'admin';
  levanta HTTP 403 se o utilizador nao for admin.
"""

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer

from src.auth.modelos import DadosToken
from src.auth.seguranca import descodificar_token


# tokenUrl aponta para o endpoint de login (usado pelo botao "Authorize" do Swagger UI).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def utilizador_atual(token: str = Depends(oauth2_scheme)) -> DadosToken:
    """Valida o token JWT e devolve os dados do utilizador autenticado."""
    dados = descodificar_token(token)
    if dados is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return dados


def utilizador_atual_query(
    request: Request,
    token: str | None = Query(default=None, description="Token JWT alternativo ao header Authorization."),
) -> DadosToken:
    """
    Valida o token JWT vindo do header Authorization OU do query param `token`.

    Usado por endpoints servidos directamente ao browser (PDFs em <a> ou
    <iframe>), onde nao e possivel injectar headers HTTP customizados.
    """
    raw = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        raw = auth_header[7:].strip()
    elif token:
        raw = token

    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nao autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    dados = descodificar_token(raw)
    if dados is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return dados


def requer_admin(utilizador: DadosToken = Depends(utilizador_atual)) -> DadosToken:
    """Exige que o utilizador autenticado tenha o papel 'admin'."""
    if utilizador.papel != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return utilizador
