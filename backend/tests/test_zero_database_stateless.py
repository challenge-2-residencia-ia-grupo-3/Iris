"""Testes da Issue #35 (História 4.1.2 / RNF-01): Arquitetura stateless e Zero-Database."""
from __future__ import annotations

import builtins
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
SRC_DIR = BACKEND_DIR / "src"
SCRIPTS_DIR = REPO_ROOT / "scripts"
for p in (str(SRC_DIR), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import audit_zero_database  # type: ignore[import-not-found]
from iris.config import IrisSettings, validate_zero_database_configuration
from iris.main import create_app, get_health_status

HTTPX_AVAILABLE = importlib.util.find_spec("httpx") is not None
FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


class TestZeroDatabaseConfigurationAndAudit(unittest.TestCase):
    """Valida os guardrails de configuração e o script de auditoria Zero-Database."""

    def test_repository_passes_zero_database_audit(self) -> None:
        result = audit_zero_database.run_audit(REPO_ROOT)
        self.assertTrue(result.ok, msg=f"Violações encontradas: {result.violations}")
        self.assertGreaterEqual(len(result.checks_passed), 4)

    def test_audit_detects_student_orm_model_and_sql_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            (fake_root / "pyproject.toml").write_text(
                '[project]\nname = "fake"\ndependencies = ["sqlalchemy>=2.0"]\n',
                encoding="utf-8",
            )
            api_dir = fake_root / "backend" / "src" / "iris" / "api"
            api_dir.mkdir(parents=True)
            (fake_root / "backend" / "src" / "iris" / "config.py").write_text(
                "zero_student_database: bool = True\nstateless_mode: bool = True\n",
                encoding="utf-8",
            )
            (api_dir / "models.py").write_text(
                "from sqlalchemy.orm import DeclarativeBase\n"
                "class Base(DeclarativeBase):\n    pass\n"
                "class Estudante(Base):\n    __tablename__ = 'alunos'\n",
                encoding="utf-8",
            )
            (fake_root / "rag" / "iris-rag" / "pacote").mkdir(parents=True)
            (fake_root / "rag" / "iris-rag" / "pacote" / "banco_pg.py").write_text(
                'TABELA = "iris_trechos"\n',
                encoding="utf-8",
            )
            res = audit_zero_database.run_audit(fake_root)
            self.assertFalse(res.ok)
            joined = "\n".join(res.violations)
            self.assertIn("sqlalchemy", joined)
            self.assertIn("__tablename__", joined)
            self.assertIn("DeclarativeBase", joined)

    def test_settings_forbid_disabling_zero_database_or_stateless_mode(self) -> None:
        with self.assertRaises(ValueError):
            IrisSettings(zero_student_database=False)
        with self.assertRaises(ValueError):
            IrisSettings(stateless_for_students=False)
        with self.assertRaises(ValueError):
            IrisSettings(stateless_mode=False)
        with self.assertRaises(ValueError):
            IrisSettings(allowed_persistent_stores=("students_db",))

    def test_validate_zero_database_rejects_student_db_env_var(self) -> None:
        with patch.dict(os.environ, {"STUDENT_DATABASE_URL": "postgresql://user:pass@localhost/alunos"}):
            with self.assertRaises(ValueError):
                validate_zero_database_configuration()

    def test_audit_allows_teacher_storage_but_rejects_student_tables_inside_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            (fake_root / "pyproject.toml").write_text('[project]\nname = "fake"\ndependencies = []\n', encoding="utf-8")
            storage_dir = fake_root / "backend" / "src" / "iris" / "storage"
            storage_dir.mkdir(parents=True)
            (fake_root / "backend" / "src" / "iris" / "config.py").write_text(
                "zero_student_database: bool = True\nstateless_mode: bool = True\n",
                encoding="utf-8",
            )
            (fake_root / "rag" / "iris-rag" / "pacote").mkdir(parents=True)
            (fake_root / "rag" / "iris-rag" / "pacote" / "banco_pg.py").write_text(
                'TABELA = "iris_trechos"\n',
                encoding="utf-8",
            )
            (storage_dir / "schema.py").write_text(
                'DDL = "CREATE TABLE IF NOT EXISTS docente.atividades_historico (id uuid PRIMARY KEY)"\n',
                encoding="utf-8",
            )
            ok_res = audit_zero_database.run_audit(fake_root)
            self.assertTrue(ok_res.ok, msg=f"Deveria permitir schema docente: {ok_res.violations}")

            (storage_dir / "bad.py").write_text(
                'BAD = "CREATE TABLE docente.alunos (id uuid PRIMARY KEY)"\n',
                encoding="utf-8",
            )
            bad_res = audit_zero_database.run_audit(fake_root)
            self.assertFalse(bad_res.ok)
            self.assertIn("estudantes", "\n".join(bad_res.violations))

    def test_health_status_reports_stateless_and_allowed_stores(self) -> None:
        health = get_health_status()
        self.assertTrue(health["zero_student_database"])
        self.assertTrue(health["stateless_for_students"])
        self.assertTrue(health["stateless_mode"])
        self.assertEqual(
            health["allowed_persistent_stores"],
            ["rag_vector_readonly", "teacher_activity_history"],
        )


@unittest.skipUnless(FASTAPI_AVAILABLE and HTTPX_AVAILABLE, "FastAPI ou httpx não instalado")
class TestFastApiStatelessLifecycle(unittest.TestCase):
    """Garante que requisições HTTP na API do Íris não gravam em disco nem mantêm sessão."""

    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient

        cls.app = create_app()
        cls.client = TestClient(cls.app)

    def test_app_has_no_session_middleware(self) -> None:
        middleware_names = [getattr(m.cls, "__name__", str(m.cls)) for m in self.app.user_middleware]
        self.assertNotIn("SessionMiddleware", middleware_names)

    def test_api_session_executes_without_disk_writes_or_cookies(self) -> None:
        original_open = builtins.open

        def readonly_open(file, mode="r", *args, **kwargs):
            if any(ch in str(mode) for ch in ("w", "a", "x", "+")):
                raise AssertionError(f"Escrita em disco proibida durante requisição HTTP: {file!r} ({mode})")
            return original_open(file, mode, *args, **kwargs)

        def forbid_temp(*args, **kwargs):
            raise AssertionError("Criação de arquivo temporário proibida em requisição stateless.")

        texto_prova = (
            "Avaliação de Ciências Naturais — 7º Ano\n"
            "1. Explique o papel da fotossíntese no ciclo do carbono e cite dois organismos produtores."
        )

        with (
            patch("builtins.open", side_effect=readonly_open),
            patch("tempfile.NamedTemporaryFile", side_effect=forbid_temp),
            patch("tempfile.mkstemp", side_effect=forbid_temp),
        ):
            r_health = self.client.get("/api/v1/health")
            self.assertEqual(r_health.status_code, 200)
            self.assertEqual(r_health.headers.get("cache-control"), "no-store")
            self.assertNotIn("set-cookie", r_health.headers)

            r_text = self.client.post("/api/v1/materials/text", json={"text": texto_prova})
            self.assertEqual(r_text.status_code, 200)
            self.assertEqual(r_text.headers.get("cache-control"), "no-store")
            self.assertNotIn("set-cookie", r_text.headers)

            r_upload = self.client.post(
                "/api/v1/materials/upload",
                files={"file": ("atividade.txt", texto_prova.encode("utf-8"), "text/plain")},
            )
            self.assertEqual(r_upload.status_code, 200)
            self.assertEqual(r_upload.headers.get("cache-control"), "no-store")

            r_decomp = self.client.post("/api/v1/materials/decompose", json={"text": texto_prova})
            self.assertEqual(r_decomp.status_code, 200)
            self.assertEqual(r_decomp.headers.get("cache-control"), "no-store")

            r_select = self.client.post(
                "/api/v1/catalogs/characteristics/select",
                json={"selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"]},
            )
            self.assertEqual(r_select.status_code, 200)
            self.assertEqual(r_select.headers.get("cache-control"), "no-store")

            perfil_payload = {
                "versao_schema": "1.0",
                "codigo_anonimo": "aluno-8f7a2c1b",
                "criado_em": "2026-11-16T12:00:00.000Z",
                "caracteristicas_selecionadas": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
                "barreiras_observadas": [],
                "historico_estrategias": [],
                "anotacoes_pedagogicas": [],
            }
            r_export = self.client.post("/api/v1/perfil/exportar?formato=json", json=perfil_payload)
            self.assertEqual(r_export.status_code, 200)
            self.assertEqual(r_export.headers.get("cache-control"), "no-store")
            self.assertNotIn("set-cookie", r_export.headers)

    def test_consecutive_requests_do_not_leak_state(self) -> None:
        material_a = "Questão 1: Calcule a área de um triângulo retângulo de base 6 cm e altura 4 cm."
        material_b = "Questão 1: Descreva as camadas da atmosfera terrestre e sua composição principal."

        res_a = self.client.post("/api/v1/materials/text", json={"text": material_a})
        res_b = self.client.post("/api/v1/materials/text", json={"text": material_b})

        self.assertEqual(res_a.status_code, 200)
        self.assertEqual(res_b.status_code, 200)
        self.assertNotIn("triângulo", res_b.json()["raw_text"])
        self.assertNotIn("atmosfera", res_a.json()["raw_text"])


if __name__ == "__main__":
    unittest.main()
