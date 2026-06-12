"""
Fixtures partilhadas pelos testes.

`bd_temporaria` redireciona a BD de auth (SQLite) para um ficheiro temporario,
para os testes nunca tocarem na data/auth.db real. `cliente_api` constroi um
TestClient da FastAPI ja apontado a essa BD, com utilizadores de teste criados
diretamente (sem correr o seed nem o lifespan — nao precisa de .env nem Qdrant).
"""

import pytest

import src.auth.db as auth_db
import src.auth.seguranca as seguranca


@pytest.fixture()
def bd_temporaria(tmp_path, monkeypatch):
    """BD SQLite temporaria + segredo JWT fixo (hermetico, sem .env)."""
    caminho = tmp_path / "auth_teste.db"
    monkeypatch.setattr(auth_db, "AUTH_DB_PATH", str(caminho))
    monkeypatch.setattr(
        seguranca, "JWT_SECRET_KEY",
        "segredo-de-teste-nao-usar-em-producao-0123456789abcdef",  # >=32 bytes (RFC 7518)
    )
    auth_db.inicializar_bd()
    return caminho


@pytest.fixture()
def cliente_api(bd_temporaria):
    """
    TestClient da app com dois utilizadores de teste na BD temporaria:
    ('admin_teste', papel admin) e ('farm_teste', papel farmaceutico),
    ambos com a password 'pass-teste'.

    Nota: TestClient SEM context manager nao corre o lifespan — o seed real
    nunca e executado; os utilizadores sao criados aqui diretamente.
    """
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.auth.db import criar_utilizador
    from src.auth.seguranca import gerar_hash_password

    hash_pw = gerar_hash_password("pass-teste")
    criar_utilizador("admin_teste", hash_pw, "admin")
    criar_utilizador("farm_teste", hash_pw, "farmaceutico")

    return TestClient(app)


def obter_token(cliente, username, password="pass-teste"):
    """Faz login e devolve o token JWT (helper para os testes de API)."""
    res = cliente.post(
        "/auth/login",
        data={"username": username, "password": password},
    )
    assert res.status_code == 200, f"login de teste falhou: {res.text}"
    return res.json()["access_token"]
