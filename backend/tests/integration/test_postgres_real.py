"""Testes de integração reais contra PostgreSQL 16 + pgvector (sem mocks de banco).

Executa somente quando `IRIS_TEST_REAL_PG=1` (ex.: job `integracao-pg` do CI ou local com
`make db-up`). Assim a suíte unitária padrão continua rodando sem exigir Docker ativo.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
import uuid
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
SRC_DIR = BACKEND_DIR / "src"
PACOTE_DIR = REPO_ROOT / "rag" / "iris-rag" / "pacote"

for p in (str(SRC_DIR), str(PACOTE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

REAL_PG_ENABLED = os.environ.get("IRIS_TEST_REAL_PG") == "1"
HAS_DOCENTE_STORAGE = importlib.util.find_spec("iris.storage") is not None


@unittest.skipUnless(REAL_PG_ENABLED, "Defina IRIS_TEST_REAL_PG=1 para rodar contra PostgreSQL real")
class TestPgvectorReal(unittest.TestCase):
    """Valida extensão pgvector, criação de tabela/índice HNSW e filtro SQL n_palavras > 0."""

    def setUp(self) -> None:
        import banco_pg  # type: ignore[import-not-found]

        self.banco_pg = banco_pg
        self.dsn = os.environ.get("RAG_PG_DSN", "postgresql://iris:iris@127.0.0.1:5433/iris")
        self.banco_pg.DSN = self.dsn
        self.con = self.banco_pg.conectar()
        self.suffix = uuid.uuid4().hex[:8]
        self.chunk_ok = f"ci-ok-{self.suffix}"
        self.chunk_placeholder = f"ci-placeholder-{self.suffix}"
        self.banco_pg.criar_tabela(self.con)

    def tearDown(self) -> None:
        if getattr(self, "con", None) is not None:
            self.con.execute(
                f"DELETE FROM {self.banco_pg.TABELA} WHERE chunk_id = ANY(%s)",
                [[self.chunk_ok, self.chunk_placeholder]],
            )
            self.con.close()

    def test_pgvector_busca_denso_ignora_placeholders_sem_palavras(self) -> None:
        vec_consulta = np.zeros(768, dtype=np.float32)
        vec_consulta[0] = 1.0

        vec_proximo = np.zeros(768, dtype=np.float32)
        vec_proximo[0] = 0.99
        vec_proximo[1] = 0.01

        vec_identico = np.zeros(768, dtype=np.float32)
        vec_identico[0] = 1.0

        sql_insert = f"""
            INSERT INTO {self.banco_pg.TABELA} (
                chunk_id, doc_id, parte, idioma, tipo_evidencia, titulo, orgao, ano, url,
                licenca, secao, pagina_inicio, pagina_fim, tema, barreiras, nao_usar_para,
                nota_uso, tipo_corte, n_palavras, texto, texto_indexado, vec_mpnet
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
        """
        self.con.execute(
            sql_insert,
            (
                self.chunk_ok,
                f"doc-{self.suffix}",
                "C",
                "pt",
                "diretriz",
                "Guia DUA CI",
                "MEC",
                "2026",
                "https://exemplo.edu.br/dua",
                "aberta",
                "Seção 1",
                1,
                1,
                ["dua"],
                ["memoria_trabalho"],
                [],
                None,
                "secao",
                25,
                "Dividir comandos múltiplos em passos numerados reduz sobrecarga na memória de trabalho.",
                "Dividir comandos múltiplos em passos numerados reduz sobrecarga na memória de trabalho.",
                vec_proximo,
            ),
        )
        # Placeholder de documento com restrição de licença: vetor idêntico, mas n_palavras = 0
        self.con.execute(
            sql_insert,
            (
                self.chunk_placeholder,
                f"doc-restrito-{self.suffix}",
                "C",
                "pt",
                "diretriz",
                "Manual Restrito CI",
                "Editora",
                "2026",
                "https://exemplo.edu.br/restrito",
                "restrita",
                "Aviso",
                1,
                1,
                ["dua"],
                ["memoria_trabalho"],
                [],
                None,
                "placeholder",
                0,
                "[texto não reproduzido por restrição de licença]",
                "[texto não reproduzido por restrição de licença]",
                vec_identico,
            ),
        )

        resultados = self.banco_pg.buscar_denso(
            self.con,
            vec_consulta,
            "mpnet",
            n=10,
            filtro={"barreira": "memoria_trabalho"},
        )
        ids_retornados = [cid for cid, _ in resultados]
        self.assertIn(self.chunk_ok, ids_retornados)
        self.assertNotIn(self.chunk_placeholder, ids_retornados)


@unittest.skipUnless(
    REAL_PG_ENABLED and HAS_DOCENTE_STORAGE,
    "Requer IRIS_TEST_REAL_PG=1 e módulo iris.storage (ADR-10)",
)
class TestDocenteAuthHistoryRealPostgres(unittest.TestCase):
    """Testa ponta a ponta Auth + Gate Anti-PII + Histórico + LGPD Cascade contra PostgreSQL 16 real."""

    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        from iris.main import create_app
        from iris.storage.database import PostgresConnectionManager

        self.dsn = os.environ.get(
            "IRIS_APP_PG_DSN",
            os.environ.get("RAG_PG_DSN", "postgresql://iris:iris@127.0.0.1:5433/iris"),
        )
        os.environ["IRIS_APP_PG_DSN"] = self.dsn
        os.environ.setdefault("IRIS_JWT_SECRET", "ci-real-postgres-secret-key")

        self.db = PostgresConnectionManager(dsn=self.dsn)
        self.db.ensure_schema(force=True)
        self.client = TestClient(create_app())
        self.created_emails: list[str] = []

    def tearDown(self) -> None:
        if getattr(self, "created_emails", None):
            with self.db.connection(ensure_ddl=False) as con:
                with con.cursor() as cur:
                    cur.execute(
                        "DELETE FROM docente.professores WHERE email = ANY(%s)",
                        (self.created_emails,),
                    )

    def test_schema_docente_sem_tabelas_de_estudantes(self) -> None:
        with self.db.connection(ensure_ddl=False) as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_schema IN ('docente', 'public')
                    """
                )
                rows = cur.fetchall()

        docente_tables = {name for schema, name in rows if schema == "docente"}
        self.assertTrue(
            {"professores", "identidades_oauth", "atividades_historico", "refresh_tokens"}.issubset(docente_tables)
        )
        all_names = {name.lower() for _, name in rows}
        for forbidden in ("alunos", "aluno", "estudantes", "estudante", "students", "laudos"):
            self.assertNotIn(forbidden, all_names)

    def test_fluxo_completo_auth_history_privacy_e_exclusao_lgpd_real(self) -> None:
        tag = uuid.uuid4().hex[:10]
        email_a = f"profa.a.{tag}@escola.edu.br"
        email_b = f"profa.b.{tag}@escola.edu.br"
        self.created_emails.extend([email_a, email_b])

        # 1. Providers com banco online real
        prov = self.client.get("/api/v1/auth/providers")
        self.assertEqual(prov.status_code, 200, prov.text)
        self.assertTrue(prov.json()["database_online"])

        # 2. Cadastro local (Argon2id + JWT + refresh token no Postgres)
        reg_a = self.client.post(
            "/api/v1/auth/register",
            json={"email": email_a, "nome_exibicao": "Profa. Integração A", "senha": "SenhaSegura#2026"},
        )
        self.assertEqual(reg_a.status_code, 201, reg_a.text)
        sess_a = reg_a.json()
        prof_a_id = sess_a["teacher"]["id"]

        # 3. Login real e recusa de senha inválida
        bad_login = self.client.post("/api/v1/auth/login", json={"email": email_a, "senha": "errada"})
        self.assertEqual(bad_login.status_code, 401)
        ok_login = self.client.post("/api/v1/auth/login", json={"email": email_a, "senha": "SenhaSegura#2026"})
        self.assertEqual(ok_login.status_code, 200, ok_login.text)
        refresh_1 = ok_login.json()["refresh_token"]

        # 4. Rotação de refresh token e bloqueio de reuso
        ref = self.client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
        self.assertEqual(ref.status_code, 200, ref.text)
        access_a = ref.json()["access_token"]
        replay = self.client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
        self.assertEqual(replay.status_code, 401)

        headers_a = {"Authorization": f"Bearer {access_a}"}

        # 5. Privacy Gate estrito impede gravação no Postgres quando há PII
        payload_pii = {
            "titulo": "Prova de Ciências",
            "disciplina": "Ciências",
            "ano_escolar": "6º ano",
            "nivel_andaime": 2,
            "caracteristicas_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
            "questoes": [
                {
                    "id": "q1",
                    "original": "Leia e responda sobre o ciclo da água.",
                    "adaptado": "Para o aluno Gabriel Silva (CPF 123.456.789-00): explique a evaporação.",
                    "editada": False,
                    "aprovada": False,
                    "justificativas": ["Divisão em etapas."],
                    "recomendacao_docente": "Oferecer tempo extra sem penalizar rascunhos.",
                }
            ],
            "status": "rascunho",
        }
        blocked = self.client.post("/api/v1/history", json=payload_pii, headers=headers_a)
        self.assertEqual(blocked.status_code, 422, blocked.text)
        self.assertEqual(blocked.json()["detail"]["code"], "PII_DETECTED")

        # 6. Com auto_sanitizar=true, grava sanitizado e preserva recomendacao_docente
        saved = self.client.post("/api/v1/history?auto_sanitizar=true", json=payload_pii, headers=headers_a)
        self.assertEqual(saved.status_code, 201, saved.text)
        item = saved.json()
        activity_id = item["id"]
        self.assertNotIn("Gabriel Silva", item["questoes"][0]["adaptado"])
        self.assertNotIn("123.456.789-00", item["questoes"][0]["adaptado"])
        self.assertEqual(
            item["questoes"][0]["recomendacao_docente"],
            "Oferecer tempo extra sem penalizar rascunhos.",
        )

        # 7. Exportação bloqueada em rascunho (409)
        exp_blocked = self.client.post(f"/api/v1/history/{activity_id}/export?formato=pdf", headers=headers_a)
        self.assertEqual(exp_blocked.status_code, 409)

        # 8. Homologação + exportação PDF real
        payload_homolog = {
            **payload_pii,
            "questoes": [{**item["questoes"][0], "aprovada": True}],
            "status": "homologada",
        }
        upd = self.client.put(f"/api/v1/history/{activity_id}", json=payload_homolog, headers=headers_a)
        self.assertEqual(upd.status_code, 200, upd.text)
        exp_ok = self.client.post(f"/api/v1/history/{activity_id}/export?formato=pdf", headers=headers_a)
        self.assertEqual(exp_ok.status_code, 200)
        self.assertEqual(exp_ok.headers.get("cache-control"), "no-store")
        self.assertTrue(exp_ok.content.startswith(b"%PDF"))

        # 9. Isolamento entre docentes no Postgres real
        reg_b = self.client.post(
            "/api/v1/auth/register",
            json={"email": email_b, "nome_exibicao": "Profa. Integração B", "senha": "OutraSenha#2026"},
        )
        self.assertEqual(reg_b.status_code, 201, reg_b.text)
        headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}
        cross = self.client.get(f"/api/v1/history/{activity_id}", headers=headers_b)
        self.assertEqual(cross.status_code, 404)

        # 10. Exclusão LGPD em cascata no Postgres real
        del_a = self.client.delete("/api/v1/auth/me", headers=headers_a)
        del_b = self.client.delete("/api/v1/auth/me", headers=headers_b)
        self.assertEqual(del_a.status_code, 204)
        self.assertEqual(del_b.status_code, 204)

        with self.db.connection(ensure_ddl=False) as con:
            with con.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM docente.professores WHERE id = %s", (prof_a_id,))
                self.assertEqual(cur.fetchone()[0], 0)
                cur.execute("SELECT COUNT(*) FROM docente.atividades_historico WHERE professor_id = %s", (prof_a_id,))
                self.assertEqual(cur.fetchone()[0], 0)
                cur.execute("SELECT COUNT(*) FROM docente.refresh_tokens WHERE professor_id = %s", (prof_a_id,))
                self.assertEqual(cur.fetchone()[0], 0)
