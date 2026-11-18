"""Testes da Etapa 3 (ADR-10): Auth local (Argon2id/JWT), Google OAuth PKCE e API de Histórico."""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
SRC_DIR = BACKEND_DIR / "src"
SCRIPTS_DIR = REPO_ROOT / "scripts"
for p in (str(SRC_DIR), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import audit_zero_database  # type: ignore[import-not-found]
from iris.auth.google_oauth import GoogleOAuthClient
from iris.auth.security import (
    AuthTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from iris.auth.service import AuthService
from iris.config import IrisSettings
from iris.main import create_app
from iris.storage.database import DatabaseUnavailableError
from iris.storage.repositories import ActivityHistoryRepository

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
HTTPX_AVAILABLE = importlib.util.find_spec("httpx") is not None


class _InMemoryPostgresStore:
    """Simula em memória as 4 tabelas do schema `docente` para testar rotas ponta a ponta."""

    def __init__(self) -> None:
        self.professores: dict[str, dict[str, Any]] = {}
        self.identidades: dict[tuple[str, str], str] = {}
        self.refresh_tokens: dict[str, dict[str, Any]] = {}
        self.atividades: dict[str, dict[str, Any]] = {}

    def is_available(self) -> bool:
        return True

    @contextmanager
    def connection(self, *, ensure_ddl: bool = True):
        yield _InMemoryConnection(self)


class _InMemoryCursor:
    def __init__(self, store: _InMemoryPostgresStore) -> None:
        self._store = store
        self._rows: list[tuple[Any, ...]] = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        s = " ".join(sql.split())
        now = datetime.now(timezone.utc)
        self._rows = []
        self.rowcount = 0

        if "SELECT 1 FROM docente.professores WHERE email = %s" in s:
            email = params[0]
            found = [p for p in self._store.professores.values() if p["email"] == email]
            self._rows = [(1,)] if found else []
            return

        if "FROM docente.professores WHERE email = %s" in s:
            email = params[0]
            for p in self._store.professores.values():
                if p["email"] == email:
                    self._rows = [self._teacher_tuple(p)]
                    return
            return

        if s.startswith("DELETE FROM docente.professores WHERE id = %s"):
            pid = params[0]
            if pid in self._store.professores:
                del self._store.professores[pid]
                self._store.identidades = {k: v for k, v in self._store.identidades.items() if v != pid}
                self._store.atividades = {k: v for k, v in self._store.atividades.items() if v["professor_id"] != pid}
                self._store.refresh_tokens = {k: v for k, v in self._store.refresh_tokens.items() if v["professor_id"] != pid}
                self.rowcount = 1
            return

        if "FROM docente.professores WHERE id = %s" in s:
            pid = params[0]
            p = self._store.professores.get(pid)
            if p:
                self._rows = [self._teacher_tuple(p)]
            return

        if "INSERT INTO docente.professores" in s:
            if "VALUES (%s, %s, %s, %s, %s, TRUE)" in s:
                pid, email, ver, nome, shash = params
            else:
                pid, email, ver, nome = params
                shash = None
            rec = {
                "id": pid,
                "email": email,
                "email_verificado": bool(ver),
                "nome_exibicao": nome,
                "senha_hash": shash,
                "ativo": True,
                "criado_em": now,
                "atualizado_em": now,
            }
            self._store.professores[pid] = rec
            self._rows = [self._teacher_tuple(rec)]
            self.rowcount = 1
            return

        if "FROM docente.identidades_oauth io JOIN docente.professores p" in s:
            prov, sub = params
            pid = self._store.identidades.get((prov, sub))
            if pid and pid in self._store.professores:
                self._rows = [self._teacher_tuple(self._store.professores[pid])]
            return

        if "INSERT INTO docente.identidades_oauth" in s:
            _, pid, prov, sub = params
            self._store.identidades[(prov, sub)] = pid
            self.rowcount = 1
            return

        if "SELECT provider FROM docente.identidades_oauth WHERE professor_id = %s" in s:
            pid = params[0]
            provs = sorted(prov for (prov, _), owner in self._store.identidades.items() if owner == pid)
            self._rows = [(p,) for p in provs]
            return

        if "UPDATE docente.professores SET email_verificado = TRUE" in s:
            pid = params[0]
            if pid in self._store.professores:
                self._store.professores[pid]["email_verificado"] = True
                self.rowcount = 1
            return

        if "INSERT INTO docente.refresh_tokens" in s:
            tid, pid, thash, exp = params
            self._store.refresh_tokens[thash] = {
                "id": tid,
                "professor_id": pid,
                "token_hash": thash,
                "expira_em": exp,
                "revogado_em": None,
            }
            self.rowcount = 1
            return

        if "FROM docente.refresh_tokens WHERE token_hash = %s" in s:
            thash = params[0]
            rt = self._store.refresh_tokens.get(thash)
            if rt and rt["revogado_em"] is None and rt["expira_em"] > now:
                self._rows = [(rt["id"], rt["professor_id"], rt["expira_em"], None)]
            return

        if "UPDATE docente.refresh_tokens SET revogado_em = NOW() WHERE token_hash = %s" in s:
            thash = params[0]
            rt = self._store.refresh_tokens.get(thash)
            if rt and rt["revogado_em"] is None:
                rt["revogado_em"] = now
                self.rowcount = 1
            return

        if "UPDATE docente.refresh_tokens SET revogado_em = NOW() WHERE professor_id = %s" in s:
            pid = params[0]
            cnt = 0
            for rt in self._store.refresh_tokens.values():
                if rt["professor_id"] == pid and rt["revogado_em"] is None:
                    rt["revogado_em"] = now
                    cnt += 1
            self.rowcount = cnt
            return

        if "INSERT INTO docente.atividades_historico" in s:
            (aid, pid, titulo, disc, ano, nivel, caracs, travas_j, quest_j, met_j, status_v) = params
            rec = {
                "id": aid,
                "professor_id": pid,
                "titulo": titulo,
                "disciplina": disc,
                "ano_escolar": ano,
                "nivel_andaime": nivel,
                "caracteristicas_ids": list(caracs),
                "travas_curriculares": json.loads(travas_j),
                "questoes": json.loads(quest_j),
                "metricas": json.loads(met_j),
                "status": status_v,
                "versao_schema": "1.0",
                "criado_em": now,
                "atualizado_em": now,
            }
            self._store.atividades[aid] = rec
            self._rows = [self._activity_tuple(rec)]
            self.rowcount = 1
            return

        if "SELECT COUNT(*) FROM docente.atividades_historico WHERE" in s:
            filtered = self._filter_activities(s, params)
            self._rows = [(len(filtered),)]
            return

        if "FROM docente.atividades_historico WHERE" in s and "ORDER BY atualizado_em DESC" in s:
            filter_params = params[:-2]
            limit, offset = int(params[-2]), int(params[-1])
            filtered = self._filter_activities(s, filter_params)
            filtered.sort(key=lambda r: r["atualizado_em"], reverse=True)
            page = filtered[offset : offset + limit]
            self._rows = [
                (
                    r["id"],
                    r["professor_id"],
                    r["titulo"],
                    r["disciplina"],
                    r["ano_escolar"],
                    r["nivel_andaime"],
                    r["caracteristicas_ids"],
                    r["status"],
                    len(r["questoes"]),
                    r["criado_em"],
                    r["atualizado_em"],
                )
                for r in page
            ]
            return

        if s.startswith("DELETE FROM docente.atividades_historico WHERE id = %s AND professor_id = %s"):
            aid, pid = params
            rec = self._store.atividades.get(aid)
            if rec and rec["professor_id"] == pid:
                del self._store.atividades[aid]
                self.rowcount = 1
            return

        if "FROM docente.atividades_historico WHERE id = %s AND professor_id = %s" in s:
            aid, pid = params
            rec = self._store.atividades.get(aid)
            if rec and rec["professor_id"] == pid:
                self._rows = [self._activity_tuple(rec)]
            return

        if "UPDATE docente.atividades_historico SET" in s:
            (titulo, disc, ano, nivel, caracs, travas_j, quest_j, met_j, status_v, aid, pid) = params
            rec = self._store.atividades.get(aid)
            if rec and rec["professor_id"] == pid:
                rec.update(
                    {
                        "titulo": titulo,
                        "disciplina": disc,
                        "ano_escolar": ano,
                        "nivel_andaime": nivel,
                        "caracteristicas_ids": list(caracs),
                        "travas_curriculares": json.loads(travas_j),
                        "questoes": json.loads(quest_j),
                        "metricas": json.loads(met_j),
                        "status": status_v,
                        "atualizado_em": now,
                    }
                )
                self._rows = [self._activity_tuple(rec)]
                self.rowcount = 1
            return
            return

    def _filter_activities(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        idx = 0
        pid = params[idx]
        idx += 1
        items = [r for r in self._store.atividades.values() if r["professor_id"] == pid]
        if "titulo ILIKE %s" in sql:
            needle = params[idx].strip("%").lower()
            idx += 1
            items = [r for r in items if needle in r["titulo"].lower()]
        if "disciplina = %s" in sql:
            disc = params[idx]
            idx += 1
            items = [r for r in items if r["disciplina"] == disc]
        if "nivel_andaime = %s" in sql:
            niv = params[idx]
            idx += 1
            items = [r for r in items if r["nivel_andaime"] == niv]
        if "status = %s" in sql:
            st = params[idx]
            idx += 1
            items = [r for r in items if r["status"] == st]
        return items

    @staticmethod
    def _teacher_tuple(p: dict[str, Any]) -> tuple[Any, ...]:
        return (
            p["id"],
            p["email"],
            p["email_verificado"],
            p["nome_exibicao"],
            p["senha_hash"],
            p["ativo"],
            p["criado_em"],
            p["atualizado_em"],
        )

    @staticmethod
    def _activity_tuple(r: dict[str, Any]) -> tuple[Any, ...]:
        return (
            r["id"],
            r["professor_id"],
            r["titulo"],
            r["disciplina"],
            r["ano_escolar"],
            r["nivel_andaime"],
            r["caracteristicas_ids"],
            r["travas_curriculares"],
            r["questoes"],
            r["metricas"],
            r["status"],
            r["versao_schema"],
            r["criado_em"],
            r["atualizado_em"],
        )

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _InMemoryConnection:
    def __init__(self, store: _InMemoryPostgresStore) -> None:
        self._store = store

    def cursor(self) -> _InMemoryCursor:
        return _InMemoryCursor(self._store)


class _FakeGoogleResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeGoogleHttpClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, data: dict[str, Any]):
        return _FakeGoogleResponse(200, {"access_token": "google-access-token-xyz"})

    def get(self, url: str, headers: dict[str, str]):
        return _FakeGoogleResponse(
            200,
            {
                "sub": "google-sub-999",
                "email": "profa.google@escola.gov.br",
                "email_verified": True,
                "name": "Prof. Google",
            },
        )


class TestSecurityPrimitives(unittest.TestCase):
    def test_argon2_password_hash_and_verify(self) -> None:
        hashed = hash_password("SenhaForte123!")
        self.assertNotEqual(hashed, "SenhaForte123!")
        self.assertTrue(verify_password("SenhaForte123!", hashed))
        self.assertFalse(verify_password("SenhaErrada!", hashed))

    def test_jwt_create_decode_and_tamper_rejection(self) -> None:
        token, ttl = create_access_token(
            professor_id="prof-123",
            email="ana@escola.br",
            nome_exibicao="Ana",
            secret="segredo-teste-32-bytes-seguros",
            ttl_minutes=15,
        )
        self.assertEqual(ttl, 900)
        payload = decode_access_token(token, secret="segredo-teste-32-bytes-seguros")
        self.assertEqual(payload["sub"], "prof-123")
        with self.assertRaises(AuthTokenError):
            decode_access_token(token + "x", secret="segredo-teste-32-bytes-seguros")

    def test_audit_zero_database_passes_with_auth_and_history_routes(self) -> None:
        res = audit_zero_database.run_audit(REPO_ROOT)
        self.assertTrue(res.ok, msg=f"Violações: {res.violations}")


@unittest.skipUnless(FASTAPI_AVAILABLE and HTTPX_AVAILABLE, "FastAPI ou httpx não instalado")
class TestAuthAndHistoryApiEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient
        from iris.api.routes.auth import get_auth_service
        from iris.api.routes.history import get_history_repository

        self.store = _InMemoryPostgresStore()
        self.settings = IrisSettings(
            jwt_secret="chave-secreta-teste-etapa3-iris-2026",
            google_client_id="google-client-id-teste",
            google_client_secret="google-secret-teste",
            google_redirect_uri="http://127.0.0.1:8000/api/v1/auth/oauth/google/callback",
            frontend_url="http://localhost:3000",
        )
        google_client = GoogleOAuthClient(
            settings=self.settings,
            http_client_factory=_FakeGoogleHttpClient,
        )
        self.auth_service = AuthService(
            db=self.store,  # type: ignore[arg-type]
            settings=self.settings,
            google_client=google_client,
        )
        self.history_repo = ActivityHistoryRepository(self.store)  # type: ignore[arg-type]

        self.app = create_app()
        self.app.dependency_overrides[get_auth_service] = lambda: self.auth_service
        self.app.dependency_overrides[get_history_repository] = lambda: self.history_repo
        self.client = TestClient(self.app)

    def _register_and_headers(self, email: str, nome: str = "Prof. Teste") -> tuple[dict[str, str], dict[str, Any]]:
        r = self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "nome_exibicao": nome, "senha": "SenhaSegura123"},
        )
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        return {"Authorization": f"Bearer {body['access_token']}"}, body

    def test_local_auth_lifecycle_refresh_rotation_and_delete(self) -> None:
        prov = self.client.get("/api/v1/auth/providers")
        self.assertEqual(prov.status_code, 200)
        self.assertTrue(prov.json()["local_enabled"])
        self.assertTrue(prov.json()["google_enabled"])
        self.assertTrue(prov.json()["guest_mode_enabled"])

        headers, reg = self._register_and_headers("prof.maria@escola.br", "Profa Maria")
        self.assertNotIn("set-cookie", self.client.get("/api/v1/auth/me", headers=headers).headers)

        dup = self.client.post(
            "/api/v1/auth/register",
            json={"email": "prof.maria@escola.br", "nome_exibicao": "Outra", "senha": "SenhaSegura123"},
        )
        self.assertEqual(dup.status_code, 409)

        bad_login = self.client.post(
            "/api/v1/auth/login",
            json={"email": "prof.maria@escola.br", "senha": "errada"},
        )
        self.assertEqual(bad_login.status_code, 401)

        ok_login = self.client.post(
            "/api/v1/auth/login",
            json={"email": "prof.maria@escola.br", "senha": "SenhaSegura123"},
        )
        self.assertEqual(ok_login.status_code, 200)
        rt1 = ok_login.json()["refresh_token"]

        refreshed = self.client.post("/api/v1/auth/refresh", json={"refresh_token": rt1})
        self.assertEqual(refreshed.status_code, 200)
        rt2 = refreshed.json()["refresh_token"]
        self.assertNotEqual(rt1, rt2)

        # Refresh token antigo foi rotacionado e não pode ser reutilizado
        reuse = self.client.post("/api/v1/auth/refresh", json={"refresh_token": rt1})
        self.assertEqual(reuse.status_code, 401)

        me = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "prof.maria@escola.br")

        deleted = self.client.delete("/api/v1/auth/me", headers=headers)
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=headers).status_code, 401)

    def test_google_oauth_pkce_callback_and_one_time_exchange(self) -> None:
        start = self.client.get("/api/v1/auth/oauth/google/start?mode=json&next=/historico")
        self.assertEqual(start.status_code, 200)
        auth_url = start.json()["authorization_url"]
        parsed = urlparse(auth_url)
        qs = parse_qs(parsed.query)
        self.assertIn("state", qs)
        self.assertIn("code_challenge", qs)
        self.assertEqual(qs["code_challenge_method"], ["S256"])

        cb = self.client.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "google-auth-code-1", "state": qs["state"][0]},
            follow_redirects=False,
        )
        self.assertEqual(cb.status_code, 302)
        loc = cb.headers["location"]
        cb_qs = parse_qs(urlparse(loc).query)
        self.assertEqual(cb_qs["next"], ["/historico"])
        exchange_code = cb_qs["code"][0]

        ex = self.client.post("/api/v1/auth/oauth/exchange", json={"code": exchange_code})
        self.assertEqual(ex.status_code, 200)
        self.assertEqual(ex.json()["teacher"]["email"], "profa.google@escola.gov.br")
        self.assertEqual(ex.json()["teacher"]["oauth_providers"], ["google"])
        self.assertFalse(ex.json()["teacher"]["possui_senha_local"])

        # Código único não pode ser trocado duas vezes
        ex_again = self.client.post("/api/v1/auth/oauth/exchange", json={"code": exchange_code})
        self.assertEqual(ex_again.status_code, 401)

    def test_history_crud_privacy_gate_isolation_export_and_from_session(self) -> None:
        headers_a, _ = self._register_and_headers("prof.a@escola.br", "Prof A")
        headers_b, _ = self._register_and_headers("prof.b@escola.br", "Prof B")

        payload_pii = {
            "titulo": "Atividade de Biologia — Fotossíntese",
            "disciplina": "Biologia",
            "ano_escolar": "7º ano",
            "nivel_andaime": 2,
            "caracteristicas_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
            "travas_curriculares": {"conceitos_obrigatorios": ["clorofila"]},
            "questoes": [
                {
                    "id": "q1",
                    "original": "Explique o papel da clorofila na fotossíntese.",
                    "adaptado": "Para o aluno Gabriel Silva: explique o papel da clorofila.",
                    "editada": True,
                    "aprovada": False,
                    "justificativas": ["Comando simplificado"],
                }
            ],
            "status": "rascunho",
        }

        blocked = self.client.post("/api/v1/history", json=payload_pii, headers=headers_a)
        self.assertEqual(blocked.status_code, 422)
        self.assertEqual(blocked.json()["detail"]["code"], "PII_DETECTED")

        created = self.client.post(
            "/api/v1/history?auto_sanitizar=true",
            json=payload_pii,
            headers=headers_a,
        )
        self.assertEqual(created.status_code, 201, created.text)
        aid = created.json()["id"]
        self.assertIn("[ESTUDANTE]", created.json()["questoes"][0]["adaptado"])

        # Isolamento entre professores
        self.assertEqual(self.client.get(f"/api/v1/history/{aid}", headers=headers_b).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/history/{aid}", headers=headers_b).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/history", headers=headers_b).json()["total"], 0)

        # Exportação bloqueada enquanto rascunho
        exp_blocked = self.client.post(f"/api/v1/history/{aid}/export?formato=pdf", headers=headers_a)
        self.assertEqual(exp_blocked.status_code, 409)
        self.assertEqual(exp_blocked.json()["detail"]["code"], "EXPORT_BLOCKED")

        # Homologar e exportar PDF sob demanda
        payload_homologado = {
            **payload_pii,
            "questoes": [
                {
                    **payload_pii["questoes"][0],
                    "adaptado": "Explique o papel da clorofila na fotossíntese.",
                    "aprovada": True,
                }
            ],
            "status": "homologada",
        }
        upd = self.client.put(f"/api/v1/history/{aid}", json=payload_homologado, headers=headers_a)
        self.assertEqual(upd.status_code, 200)

        exp_ok = self.client.post(f"/api/v1/history/{aid}/export?formato=pdf", headers=headers_a)
        self.assertEqual(exp_ok.status_code, 200)
        self.assertEqual(exp_ok.headers["content-type"], "application/pdf")
        self.assertTrue(exp_ok.content.startswith(b"%PDF"))

        # Duplicação gera novo rascunho
        dup = self.client.post(f"/api/v1/history/{aid}/duplicate", json={}, headers=headers_a)
        self.assertEqual(dup.status_code, 201)
        self.assertEqual(dup.json()["status"], "rascunho")
        self.assertIn("(Cópia)", dup.json()["titulo"])

        # Importar de uma sessão em memória da Etapa 5
        sess_res = self.client.post(
            "/api/v1/sessions",
            json={
                "titulo": "História — Revolução Industrial",
                "questoes": [
                    {
                        "id": "q1",
                        "original": "Cite duas consequências da Revolução Industrial.",
                        "adaptado": "Passo 1: Cite duas consequências da Revolução Industrial.",
                    }
                ],
            },
        )
        self.assertEqual(sess_res.status_code, 201)
        sid = sess_res.json()["id"]
        from_sess = self.client.post(
            f"/api/v1/history/from-session/{sid}",
            json={"disciplina": "História", "ano_escolar": "8º ano", "nivel_andaime": 2},
            headers=headers_a,
        )
        self.assertEqual(from_sess.status_code, 201, from_sess.text)
        self.assertEqual(from_sess.json()["titulo"], "História — Revolução Industrial")

    def test_graceful_503_when_database_offline(self) -> None:
        from fastapi.testclient import TestClient
        from iris.api.routes.auth import get_auth_service

        class _OfflineDb:
            def is_available(self) -> bool:
                return False

            @contextmanager
            def connection(self, *, ensure_ddl: bool = True):
                raise DatabaseUnavailableError("PostgreSQL desligado.")
                yield

        offline_auth = AuthService(db=_OfflineDb(), settings=self.settings)  # type: ignore[arg-type]
        app = create_app()
        app.dependency_overrides[get_auth_service] = lambda: offline_auth
        client = TestClient(app)

        self.assertEqual(client.get("/api/v1/health").status_code, 200)
        res = client.post(
            "/api/v1/auth/login",
            json={"email": "a@b.com", "senha": "Password123"},
        )
        self.assertEqual(res.status_code, 503)


if __name__ == "__main__":
    unittest.main()
