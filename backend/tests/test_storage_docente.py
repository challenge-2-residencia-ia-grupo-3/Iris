"""Testes da Etapa 2 (ADR-10): Schema docente, Gate Anti-PII/Anti-Clínico e repositórios."""
from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
SRC_DIR = BACKEND_DIR / "src"
SCRIPTS_DIR = REPO_ROOT / "scripts"
for p in (str(SRC_DIR), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import audit_zero_database  # type: ignore[import-not-found]
from iris.storage.database import SCHEMA_DOCENTE_DDL
from iris.storage.privacy_gate import (
    ActivityPrivacyViolationError,
    validate_and_prepare_activity,
)
from iris.storage.repositories import (
    ActivityHistoryRepository,
    StorageConflictError,
    StorageNotFoundError,
    TeacherRepository,
)


def _payload_valido() -> dict[str, Any]:
    return {
        "titulo": "Lista de Ciências — Ciclo da Água",
        "disciplina": "Ciências",
        "ano_escolar": "6º ano",
        "nivel_andaime": 2,
        "caracteristicas_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
        "travas_curriculares": {"conceitos_obrigatorios": ["evaporação", "condensação"]},
        "questoes": [
            {
                "id": "q1",
                "original": "Explique as etapas de evaporação e condensação no ciclo da água.",
                "adaptado": "1. Explique o que é evaporação.\n2. Explique o que é condensação no ciclo da água.",
                "editada": False,
                "aprovada": True,
                "justificativas": ["Divisão de comandos múltiplos em passos numerados."],
            }
        ],
        "metricas": {"trcc": 1.0, "aprovado_auditor": True},
        "status": "homologada",
    }


class _FakeCursor:
    def __init__(self, handler) -> None:
        self._handler = handler
        self._result: list[tuple[Any, ...]] = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self._result, self.rowcount = self._handler(sql, params)

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


class _FakeConnection:
    def __init__(self, handler) -> None:
        self._handler = handler

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._handler)


class _FakeDbManager:
    def __init__(self, handler) -> None:
        self._handler = handler
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    @contextmanager
    def connection(self, *, ensure_ddl: bool = True):
        def _wrapped(sql: str, params: tuple[Any, ...] = ()):
            self.calls.append((sql, params))
            return self._handler(sql, params)

        yield _FakeConnection(_wrapped)


class TestSchemaAndAuditCompliance(unittest.TestCase):
    def test_schema_ddl_only_defines_docente_tables(self) -> None:
        for expected in (
            "CREATE SCHEMA IF NOT EXISTS docente",
            "docente.professores",
            "docente.identidades_oauth",
            "docente.atividades_historico",
            "docente.refresh_tokens",
        ):
            self.assertIn(expected, SCHEMA_DOCENTE_DDL)
        self.assertIsNone(audit_zero_database.FORBIDDEN_STUDENT_TABLE_RE.search(SCHEMA_DOCENTE_DDL))

    def test_repository_with_storage_package_passes_zero_database_audit(self) -> None:
        res = audit_zero_database.run_audit(REPO_ROOT)
        self.assertTrue(res.ok, msg=f"Violações encontradas: {res.violations}")


class TestActivityPrivacyGate(unittest.TestCase):
    def test_accepts_clean_pedagogical_activity(self) -> None:
        clean = validate_and_prepare_activity(_payload_valido())
        self.assertEqual(clean.titulo, "Lista de Ciências — Ciclo da Água")
        self.assertEqual(clean.pii_substituicoes, 0)
        self.assertEqual(len(clean.questoes), 1)

    def test_blocks_forbidden_student_profile_keys(self) -> None:
        payload = _payload_valido()
        payload["codigo_anonimo"] = "aluno-8f7a2c1b"
        with self.assertRaises(ActivityPrivacyViolationError) as ctx:
            validate_and_prepare_activity(payload)
        self.assertEqual(ctx.exception.code, "FORBIDDEN_STUDENT_OR_CLINICAL_FIELD")

        nested_payload = _payload_valido()
        nested_payload["metricas"] = {"aluno": "Gabriel"}
        with self.assertRaises(ActivityPrivacyViolationError) as ctx2:
            validate_and_prepare_activity(nested_payload)
        self.assertEqual(ctx2.exception.code, "FORBIDDEN_STUDENT_OR_CLINICAL_FIELD")

    def test_blocks_pii_in_questions_when_auto_sanitizar_false(self) -> None:
        payload = _payload_valido()
        payload["questoes"][0]["adaptado"] = (
            "Para o aluno Gabriel Silva (CPF 123.456.789-00): explique a evaporação."
        )
        with self.assertRaises(ActivityPrivacyViolationError) as ctx:
            validate_and_prepare_activity(payload, auto_sanitizar=False)
        self.assertEqual(ctx.exception.code, "PII_DETECTED")

    def test_auto_sanitizar_cleans_question_pii_but_still_blocks_title_pii_and_clinical_terms(self) -> None:
        payload = _payload_valido()
        payload["questoes"][0]["adaptado"] = (
            "Para o aluno Gabriel Silva, da Escola Municipal Paulo Freire: explique a evaporação."
        )
        clean = validate_and_prepare_activity(payload, auto_sanitizar=True)
        self.assertGreaterEqual(clean.pii_substituicoes, 1)
        self.assertNotIn("Gabriel Silva", clean.questoes[0]["adaptado"])
        self.assertIn("[ESTUDANTE]", clean.questoes[0]["adaptado"])

        # Título com nome de aluno continua bloqueado mesmo com auto_sanitizar=True
        payload_titulo_pii = _payload_valido()
        payload_titulo_pii["titulo"] = "Prova do Aluno: Gabriel Silva"
        with self.assertRaises(ActivityPrivacyViolationError) as ctx_titulo:
            validate_and_prepare_activity(payload_titulo_pii, auto_sanitizar=True)
        self.assertEqual(ctx_titulo.exception.code, "PII_DETECTED")

        # Termo clínico continua bloqueado mesmo com auto_sanitizar=True
        payload_clinico = _payload_valido()
        payload_clinico["questoes"][0]["adaptado"] = "Atividade adaptada conforme CID F90 e uso de Ritalina."
        with self.assertRaises(ActivityPrivacyViolationError) as ctx_clinico:
            validate_and_prepare_activity(payload_clinico, auto_sanitizar=True)
        self.assertEqual(ctx_clinico.exception.code, "CLINICAL_DATA_BLOCKED")

    def test_validates_and_preserves_recomendacao_docente(self) -> None:
        payload = _payload_valido()
        payload["questoes"][0]["recomendacao_docente"] = "Dar tempo extra de 10 minutos sem penalizar rascunhos."
        clean = validate_and_prepare_activity(payload)
        self.assertEqual(
            clean.questoes[0]["recomendacao_docente"],
            "Dar tempo extra de 10 minutos sem penalizar rascunhos.",
        )

        # Bloqueia PII e termo clínico em recomendacao_docente
        bad_pii = _payload_valido()
        bad_pii["questoes"][0]["recomendacao_docente"] = "Para o aluno Gabriel Silva (CPF 123.456.789-00): dar apoio."
        with self.assertRaises(ActivityPrivacyViolationError) as ctx_pii:
            validate_and_prepare_activity(bad_pii, auto_sanitizar=False)
        self.assertEqual(ctx_pii.exception.code, "PII_DETECTED")

        bad_clinico = _payload_valido()
        bad_clinico["questoes"][0]["recomendacao_docente"] = "Considerar CID F90 durante a aplicação."
        with self.assertRaises(ActivityPrivacyViolationError) as ctx_clin:
            validate_and_prepare_activity(bad_clinico, auto_sanitizar=True)
        self.assertEqual(ctx_clin.exception.code, "CLINICAL_DATA_BLOCKED")


class TestDocenteRepositoriesWithMockedPostgres(unittest.TestCase):
    def test_history_repository_never_runs_sql_when_privacy_gate_blocks(self) -> None:
        db = _FakeDbManager(lambda sql, params: ([], 0))
        repo = ActivityHistoryRepository(db)  # type: ignore[arg-type]

        bad = _payload_valido()
        bad["questoes"][0]["adaptado"] = "Email do aluno: joao@escola.edu.br"
        with self.assertRaises(ActivityPrivacyViolationError):
            repo.create_activity(professor_id="prof-1", payload=bad, auto_sanitizar=False)

        self.assertEqual(len(db.calls), 0)

    def test_history_repository_inserts_sanitized_payload_and_scopes_by_professor(self) -> None:
        now = datetime.now(timezone.utc)

        def handler(sql: str, params: tuple[Any, ...]):
            if "INSERT INTO docente.atividades_historico" in sql:
                return (
                    [
                        (
                            params[0],
                            params[1],
                            params[2],
                            params[3],
                            params[4],
                            params[5],
                            params[6],
                            params[7],
                            params[8],
                            params[9],
                            params[10],
                            "1.0",
                            now,
                            now,
                        )
                    ],
                    1,
                )
            if "WHERE id = %s AND professor_id = %s" in sql:
                return ([], 0)
            return ([], 0)

        db = _FakeDbManager(handler)
        repo = ActivityHistoryRepository(db)  # type: ignore[arg-type]

        payload = _payload_valido()
        payload["questoes"][0]["adaptado"] = "Atividade para o aluno Gabriel Silva explicar a evaporação."
        created = repo.create_activity(professor_id="prof-1", payload=payload, auto_sanitizar=True)
        self.assertEqual(created.professor_id, "prof-1")
        self.assertNotIn("Gabriel Silva", created.questoes[0]["adaptado"])
        self.assertIn("[ESTUDANTE]", created.questoes[0]["adaptado"])

        with self.assertRaises(StorageNotFoundError):
            repo.get_activity(professor_id="prof-2", activity_id=created.id)

    def test_oauth_teacher_rejects_unverified_email_link_and_links_verified(self) -> None:
        now = datetime.now(timezone.utc)

        def unverified_handler(sql: str, params: tuple[Any, ...]):
            if "FROM docente.identidades_oauth" in sql:
                return ([], 0)
            if "FROM docente.professores" in sql and "WHERE email = %s" in sql:
                return ([("prof-1", "ana@escola.br", False, "Ana", "hash", True, now, now)], 1)
            return ([], 0)

        repo_unverified = TeacherRepository(_FakeDbManager(unverified_handler))  # type: ignore[arg-type]
        with self.assertRaises(StorageConflictError) as ctx:
            repo_unverified.find_or_create_oauth_teacher(
                provider="google",
                provider_subject="google-sub-123",
                email="Ana@Escola.br",
                email_verified=False,
                nome_exibicao="Ana",
            )
        self.assertEqual(ctx.exception.code, "OAUTH_EMAIL_NOT_VERIFIED")

        inserted_oauth: list[tuple[Any, ...]] = []

        def verified_handler(sql: str, params: tuple[Any, ...]):
            if "FROM docente.identidades_oauth" in sql:
                return ([], 0)
            if "FROM docente.professores" in sql and "WHERE email = %s" in sql:
                return ([("prof-1", "ana@escola.br", False, "Ana", "hash", True, now, now)], 1)
            if "INSERT INTO docente.identidades_oauth" in sql:
                inserted_oauth.append(params)
                return ([], 1)
            if "WHERE id = %s" in sql:
                return ([("prof-1", "ana@escola.br", True, "Ana", "hash", True, now, now)], 1)
            return ([], 0)

        repo_verified = TeacherRepository(_FakeDbManager(verified_handler))  # type: ignore[arg-type]
        teacher = repo_verified.find_or_create_oauth_teacher(
            provider="google",
            provider_subject="google-sub-123",
            email="Ana@Escola.br",
            email_verified=True,
            nome_exibicao="Ana",
        )
        self.assertEqual(teacher.id, "prof-1")
        self.assertTrue(teacher.email_verificado)
        self.assertEqual(len(inserted_oauth), 1)
        self.assertEqual(inserted_oauth[0][2], "google")


if __name__ == "__main__":
    unittest.main()
