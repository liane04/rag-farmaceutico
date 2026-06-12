"""
Testes de autenticacao e seguranca (Fase 4 do plano de login — RF15).

Tres camadas, todas hermeticas (BD temporaria, segredo JWT de teste, sem
servicos externos):
1. Primitivas: hashing bcrypt e tokens JWT (criar/validar/expirar/adulterar).
2. Gating da API: 401 sem token, 403 para nao-admin em rotas de admin.
3. Endpoints de ficheiros: defesas contra path traversal no GET e no DELETE.
"""

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from src.auth.seguranca import (
    criar_token,
    descodificar_token,
    gerar_hash_password,
    verificar_password,
)
from tests.conftest import obter_token


# ---------- 1. Primitivas de seguranca ----------

class TestPasswords:
    def test_hash_e_verificacao_correta(self):
        h = gerar_hash_password("password-segura")
        assert h != "password-segura"          # nunca em claro
        assert verificar_password("password-segura", h) is True

    def test_password_errada_falha(self):
        h = gerar_hash_password("password-segura")
        assert verificar_password("password-errada", h) is False

    def test_hashes_diferentes_para_a_mesma_password(self):
        # bcrypt usa salt aleatorio — dois hashes da mesma password diferem.
        assert gerar_hash_password("x") != gerar_hash_password("x")


class TestTokensJWT:
    def test_round_trip_valido(self, bd_temporaria):
        token = criar_token("liane", "admin")
        dados = descodificar_token(token)
        assert dados is not None
        assert dados.username == "liane"
        assert dados.papel == "admin"

    def test_token_expirado_devolve_none(self, bd_temporaria):
        import src.auth.seguranca as seguranca
        payload = {
            "sub": "liane",
            "papel": "admin",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
        token = pyjwt.encode(payload, seguranca.JWT_SECRET_KEY, algorithm="HS256")
        assert descodificar_token(token) is None

    def test_assinatura_invalida_devolve_none(self, bd_temporaria):
        payload = {
            "sub": "liane",
            "papel": "admin",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = pyjwt.encode(payload, "outro-segredo-qualquer-0123456789abcdef", algorithm="HS256")
        assert descodificar_token(token) is None

    def test_token_mal_formado_devolve_none(self, bd_temporaria):
        assert descodificar_token("isto-nao-e-um-jwt") is None

    def test_papel_desconhecido_devolve_none(self, bd_temporaria):
        import src.auth.seguranca as seguranca
        payload = {
            "sub": "liane",
            "papel": "superuser",  # papel fora de farmaceutico/admin
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = pyjwt.encode(payload, seguranca.JWT_SECRET_KEY, algorithm="HS256")
        assert descodificar_token(token) is None


# ---------- 2. Login e gating da API ----------

class TestLogin:
    def test_login_valido_devolve_token(self, cliente_api):
        res = cliente_api.post(
            "/auth/login", data={"username": "admin_teste", "password": "pass-teste"},
        )
        assert res.status_code == 200
        corpo = res.json()
        assert corpo["access_token"]
        dados = descodificar_token(corpo["access_token"])
        assert dados.papel == "admin"

    def test_password_errada_da_401(self, cliente_api):
        res = cliente_api.post(
            "/auth/login", data={"username": "admin_teste", "password": "errada"},
        )
        assert res.status_code == 401

    def test_utilizador_inexistente_da_401(self, cliente_api):
        res = cliente_api.post(
            "/auth/login", data={"username": "fantasma", "password": "x"},
        )
        assert res.status_code == 401

    def test_auth_me_devolve_papel(self, cliente_api):
        token = obter_token(cliente_api, "farm_teste")
        res = cliente_api.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json() == {"username": "farm_teste", "papel": "farmaceutico"}


class TestGating:
    def test_endpoint_protegido_sem_token_da_401(self, cliente_api):
        assert cliente_api.get("/historico").status_code == 401

    def test_token_adulterado_da_401(self, cliente_api):
        res = cliente_api.get(
            "/historico", headers={"Authorization": "Bearer token-invalido"},
        )
        assert res.status_code == 401

    def test_farmaceutico_em_rota_de_admin_da_403(self, cliente_api):
        token = obter_token(cliente_api, "farm_teste")
        for rota in ("/audit", "/admin/llm-mode"):
            res = cliente_api.get(rota, headers={"Authorization": f"Bearer {token}"})
            assert res.status_code == 403, f"{rota} devia dar 403 a farmaceutico"

    def test_admin_acede_a_rota_de_admin(self, cliente_api):
        token = obter_token(cliente_api, "admin_teste")
        res = cliente_api.get("/admin/llm-mode", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["modo"] in ("online", "local")

    def test_llm_mode_invalido_da_400(self, cliente_api):
        token = obter_token(cliente_api, "admin_teste")
        res = cliente_api.post(
            "/admin/llm-mode",
            headers={"Authorization": f"Bearer {token}"},
            json={"modo": "hibrido"},
        )
        assert res.status_code == 400

    def test_historico_farmaceutico_ve_apenas_o_proprio(self, cliente_api):
        token = obter_token(cliente_api, "farm_teste")
        res = cliente_api.get("/historico", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["registos"] == []   # BD temporaria sem consultas


# ---------- 3. Path traversal nos endpoints de ficheiros ----------

class TestPathTraversal:
    def test_get_ficheiro_aceita_token_na_query(self, cliente_api):
        # 404 (ficheiro nao existe) prova que a auth via ?token= passou (nao 401).
        token = obter_token(cliente_api, "farm_teste")
        res = cliente_api.get(f"/ficheiros/bula/inexistente.pdf?token={token}")
        assert res.status_code == 404

    def test_get_ficheiro_tipo_invalido_da_404(self, cliente_api):
        token = obter_token(cliente_api, "farm_teste")
        res = cliente_api.get(f"/ficheiros/segredos/x.pdf?token={token}")
        assert res.status_code == 404

    def test_get_ficheiro_traversal_e_rejeitado(self, cliente_api):
        # Defesa em camadas: o backslash (%5C) chega ao handler e e rejeitado
        # pela nossa validacao (400); o slash (%2F) nem chega — o router do
        # Starlette nao deixa um path param atravessar segmentos (404).
        # Em ambos os casos o ficheiro fora da pasta NUNCA e servido.
        token = obter_token(cliente_api, "farm_teste")
        casos = {
            "..%5C..%5Cauth.db.pdf": 400,   # validacao do endpoint
            "..%2F..%2Fauth.db.pdf": 404,   # router rejeita antes
        }
        for nome, esperado in casos.items():
            res = cliente_api.get(f"/ficheiros/bula/{nome}?token={token}")
            assert res.status_code == esperado, f"{nome}: {res.status_code} != {esperado}"

    def test_get_ficheiro_nao_pdf_da_400(self, cliente_api):
        token = obter_token(cliente_api, "farm_teste")
        res = cliente_api.get(f"/ficheiros/bula/script.exe?token={token}")
        assert res.status_code == 400

    def test_delete_documento_requer_admin(self, cliente_api):
        token = obter_token(cliente_api, "farm_teste")
        res = cliente_api.delete(
            "/documentos/bula/qualquer.pdf", headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403

    def test_delete_documento_traversal_da_400(self, cliente_api):
        token = obter_token(cliente_api, "admin_teste")
        res = cliente_api.delete(
            "/documentos/bula/..%5C..%5Cauth.db.pdf",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400

    def test_delete_documento_tipo_invalido_da_404(self, cliente_api):
        token = obter_token(cliente_api, "admin_teste")
        res = cliente_api.delete(
            "/documentos/segredos/x.pdf", headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404


# ---------- 4. Validacoes do upload (sem tocar no Qdrant) ----------

class TestUploadValidacao:
    def test_upload_requer_admin(self, cliente_api):
        token = obter_token(cliente_api, "farm_teste")
        res = cliente_api.post(
            "/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"ficheiro": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
            data={"tipo_documento": "bula"},
        )
        assert res.status_code == 403

    def test_tipo_invalido_da_400(self, cliente_api):
        token = obter_token(cliente_api, "admin_teste")
        res = cliente_api.post(
            "/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"ficheiro": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
            data={"tipo_documento": "segredos"},
        )
        assert res.status_code == 400

    def test_ficheiro_nao_pdf_da_400(self, cliente_api):
        token = obter_token(cliente_api, "admin_teste")
        res = cliente_api.post(
            "/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"ficheiro": ("script.exe", b"MZ...", "application/octet-stream")},
            data={"tipo_documento": "bula"},
        )
        assert res.status_code == 400
