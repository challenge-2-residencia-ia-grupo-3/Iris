"""Testes unitários e de API da História 1.2.1 (Issue #8 — Seleção Cirúrgica de Características Funcionais).

Verifica todos os Critérios de Aceitação BDD:
1. Endpoint `GET /api/v1/catalogs/characteristics` retorna o catálogo oficial de barreiras atômicas sem exigir laudo médico.
2. Seleção de 1 ou mais características atômicas registra exclusivamente as marcadas como escopo permitido (`selected_ids`)
   e mantém todas as demais bloqueadas para intervenção (`blocked_ids`).
3. Impede o avanço caso nenhuma característica funcional seja selecionada (`EMPTY_CHARACTERISTIC_SELECTION`).
4. Rejeita campos extras ou clínicos como `cid_medico` ou `laudo_clinico` (`CLINICAL_OR_EXTRA_FIELD_FORBIDDEN`).
5. Rejeita identificadores de características inexistentes (`UNKNOWN_CHARACTERISTIC_ID`).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent if BACKEND_DIR.name == "backend" else BACKEND_DIR
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from iris.api.routes import catalogs as catalogs_routes
from iris.api.routes.catalogs import (
    get_characteristics_catalog_service,
    select_surgical_characteristics_service,
)
from iris.schemas.catalog import CatalogValidationError, CharacteristicSelectionError

from iris import main

FASTAPI_DISPONIVEL = catalogs_routes.router is not None
HTTPX_DISPONIVEL = importlib.util.find_spec("httpx") is not None


class TestSurgicalCharacteristicsSelection(unittest.TestCase):
    """Bateria de testes para os serviços e contratos da História 1.2.1 (Issue #8)."""

    def test_get_characteristics_catalog_returns_official_atomic_items(self) -> None:
        """O serviço de catálogo deve retornar as 10 características atômicas sem exigir laudo médico."""
        data = get_characteristics_catalog_service()
        self.assertEqual(data["id_catalogo"], "tdah_funcoes_executivas_v1")
        self.assertFalse(data["exige_laudo_medico"])
        self.assertEqual(data["total_caracteristicas"], 10)
        self.assertEqual(len(data["caracteristicas"]), 10)
        self.assertIn("memoria_trabalho", data["barreiras_disponiveis"])
        self.assertIn("acao_e_expressao", data["principios_dua_disponiveis"])

    def test_surgical_selection_single_characteristic_isolates_scope(self) -> None:
        """Selecionar apenas 1 característica deve ativar somente ela e bloquear as outras 9."""
        target_id = "sobrecarga_memoria_trabalho_comandos_multiplos"
        result = select_surgical_characteristics_service({"selected_ids": [target_id]})
        dumped = result.model_dump()

        self.assertEqual(dumped["status"], "success")
        self.assertEqual(dumped["total_catalog_characteristics"], 10)
        self.assertEqual(dumped["selected_count"], 1)
        self.assertEqual(dumped["blocked_count"], 9)
        self.assertEqual(dumped["selected_ids"], [target_id])
        self.assertNotIn(target_id, dumped["blocked_ids"])
        self.assertEqual(len(dumped["active_characteristics"]), 1)
        self.assertEqual(dumped["active_characteristics"][0]["id_caracteristica"], target_id)

    def test_surgical_selection_multiple_characteristics_deduplicates_and_blocks_rest(self) -> None:
        """Selecionar múltiplas características deve preservar a ordem, desduplicar e bloquear as restantes."""
        ids = [
            "atencao_sustentada_textos_longos",
            "impulsividade_leitura_superficial_negacoes",
            "atencao_sustentada_textos_longos",  # duplicata intencional
        ]
        result = select_surgical_characteristics_service({"selected_ids": ids})
        dumped = result.model_dump()

        self.assertEqual(dumped["selected_count"], 2)
        self.assertEqual(dumped["blocked_count"], 8)
        self.assertEqual(
            dumped["selected_ids"],
            [
                "atencao_sustentada_textos_longos",
                "impulsividade_leitura_superficial_negacoes",
            ],
        )
        for active_id in dumped["selected_ids"]:
            self.assertNotIn(active_id, dumped["blocked_ids"])

    def test_empty_selection_blocks_advancement(self) -> None:
        """Nenhuma característica selecionada deve lançar EMPTY_CHARACTERISTIC_SELECTION."""
        with self.assertRaises(CharacteristicSelectionError) as ctx:
            select_surgical_characteristics_service({"selected_ids": []})
        self.assertEqual(ctx.exception.code, "EMPTY_CHARACTERISTIC_SELECTION")
        self.assertEqual(ctx.exception.field, "selected_ids")

    def test_unknown_characteristic_id_rejected(self) -> None:
        """ID de característica inexistente no catálogo deve lançar UNKNOWN_CHARACTERISTIC_ID."""
        with self.assertRaises(CharacteristicSelectionError) as ctx:
            select_surgical_characteristics_service(
                {"selected_ids": ["caracteristica_inexistente_pacote_fechado"]}
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_CHARACTERISTIC_ID")

    def test_rejects_clinical_or_extra_fields_in_selection_payload(self) -> None:
        """Campos extras como 'cid_medico' ou 'laudo_medico' devem ser estritamente bloqueados."""
        with self.assertRaises(CharacteristicSelectionError) as ctx:
            select_surgical_characteristics_service(
                {
                    "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
                    "cid_medico": "F90.0",
                }
            )
        self.assertEqual(ctx.exception.code, "CLINICAL_OR_EXTRA_FIELD_FORBIDDEN")
        self.assertEqual(ctx.exception.field, "cid_medico")

    def test_unknown_catalog_id_rejected(self) -> None:
        """Catálogo inexistente deve lançar CATALOG_NOT_FOUND."""
        with self.assertRaises(CharacteristicSelectionError) as ctx:
            get_characteristics_catalog_service(id_catalogo="catalogo_inexistente_v99")
        self.assertEqual(ctx.exception.code, "CATALOG_NOT_FOUND")

    def test_frontend_step2_component_and_session_persistence_contract(self) -> None:
        """Verifica a existência do componente da Etapa 2, bloqueio acessível e persistência em sessão do cliente."""
        step1_component = REPO_ROOT / "frontend" / "src" / "components" / "Step1MaterialIntake.tsx"
        step2_component = REPO_ROOT / "frontend" / "src" / "components" / "Step2FunctionalProfile.tsx"
        catalogs_api = REPO_ROOT / "frontend" / "src" / "services" / "catalogsApi.ts"
        etapa2_page = REPO_ROOT / "frontend" / "src" / "app" / "etapa-2" / "page.tsx"

        self.assertTrue(step1_component.exists(), "Step1MaterialIntake.tsx deve existir no frontend")
        self.assertTrue(step2_component.exists(), "Step2FunctionalProfile.tsx deve existir no frontend")
        self.assertTrue(catalogs_api.exists(), "catalogsApi.ts deve existir no frontend")
        self.assertTrue(etapa2_page.exists(), "etapa-2/page.tsx deve existir no frontend")

        step1_code = step1_component.read_text(encoding="utf-8")
        comp_code = step2_component.read_text(encoding="utf-8")
        api_code = catalogs_api.read_text(encoding="utf-8")

        # Verifica filtros atômicos desacoplados de rótulo clínico, acessibilidade e bloqueio de avanço
        self.assertIn('role="checkbox"', comp_code)
        self.assertIn("aria-checked={isSelected}", comp_code)
        self.assertIn('role="alert"', comp_code)
        self.assertIn("EMPTY_CHARACTERISTIC_SELECTION", comp_code)
        self.assertIn("disabled={selectedCount === 0 || isSubmitting}", comp_code)

        # Verifica consumo do endpoint oficial, fonte única de fallback e limpeza da sessão
        self.assertIn("/api/v1/catalogs/characteristics", api_code)
        self.assertIn("SURGICAL_VECTOR_STORAGE_KEY", api_code)
        self.assertIn("window.sessionStorage.setItem", api_code)
        self.assertIn("clearSurgicalSelectionFromSession", api_code)
        self.assertIn("removeItem(SURGICAL_VECTOR_STORAGE_KEY)", api_code)
        self.assertIn("tdah_caracteristicas_funcionais.json", api_code)
        self.assertIn("clearSurgicalSelectionFromSession()", comp_code)

        # Verifica persistência e restauração do material da Etapa 1 ao clicar em 'Revisar Material'
        self.assertIn("saveStep1StateToSession", step1_code)
        self.assertIn("loadStep1StateFromSession", step1_code)
        self.assertIn("clearStep1StateFromSession", step1_code)
        self.assertIn("loadStep1StateFromSession", comp_code)


@unittest.skipUnless(FASTAPI_DISPONIVEL and HTTPX_DISPONIVEL, "FastAPI ou httpx não instalado")
class TestCatalogsFastAPIRoutes(unittest.TestCase):
    """Testes HTTP de ponta a ponta sobre o app FastAPI para as rotas da História 1.2.1."""

    @classmethod
    def setUpClass(cls) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from fastapi.testclient import TestClient

            cls.cliente = TestClient(main.create_app(), raise_server_exceptions=False)

    def test_rotas_publicadas_e_contratos_http(self) -> None:
        caminhos = self.cliente.app.openapi()["paths"]
        self.assertIn("/api/v1/catalogs/characteristics", caminhos)
        self.assertIn("get", caminhos["/api/v1/catalogs/characteristics"])
        self.assertIn("/api/v1/catalogs/characteristics/select", caminhos)
        self.assertIn("post", caminhos["/api/v1/catalogs/characteristics/select"])

        resp_get = self.cliente.get("/api/v1/catalogs/characteristics")
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.json()["total_caracteristicas"], 10)

        resp_404 = self.cliente.get("/api/v1/catalogs/characteristics?id_catalogo=inexistente")
        self.assertEqual(resp_404.status_code, 404)
        self.assertEqual(resp_404.json()["detail"]["code"], "CATALOG_NOT_FOUND")

        resp_405 = self.cliente.get("/api/v1/catalogs/characteristics/select")
        self.assertEqual(resp_405.status_code, 405)

        resp_post = self.cliente.post(
            "/api/v1/catalogs/characteristics/select",
            json={"selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"]},
        )
        self.assertEqual(resp_post.status_code, 200)
        self.assertEqual(resp_post.json()["selected_count"], 1)
        self.assertEqual(resp_post.json()["blocked_count"], 9)

        resp_vazio = self.cliente.post("/api/v1/catalogs/characteristics/select", json={"selected_ids": []})
        self.assertEqual(resp_vazio.status_code, 422)
        self.assertEqual(resp_vazio.json()["detail"]["code"], "EMPTY_CHARACTERISTIC_SELECTION")

    def test_post_select_com_erro_de_schema_retorna_500_json_estruturado(self) -> None:
        with patch.object(
            catalogs_routes,
            "select_surgical_characteristics_service",
            side_effect=CatalogValidationError("Catálogo corrompido"),
        ):
            resp = self.cliente.post(
                "/api/v1/catalogs/characteristics/select",
                json={"selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"]},
            )
        self.assertEqual(resp.status_code, 500)
        corpo = resp.json()
        self.assertEqual(corpo["detail"]["code"], "CATALOG_SCHEMA_ERROR")
        self.assertEqual(corpo["detail"]["field"], "catalog")


class TestCatalogsStdlibServerRoutes(unittest.TestCase):
    """Garante paridade de roteamento e tratamento de erros no servidor HTTP de reserva."""

    @classmethod
    def setUpClass(cls) -> None:
        capturado: dict[str, type] = {}

        class ServidorCapturado:
            def __init__(self, endereco, handler):
                capturado["handler"] = handler

            def serve_forever(self) -> None:
                return None

        with patch("http.server.HTTPServer", ServidorCapturado), contextlib.redirect_stdout(io.StringIO()):
            main.run_stdlib_server()

        handler = capturado["handler"]
        handler.log_message = lambda *args, **kwargs: None
        cls.servidor = HTTPServer(("127.0.0.1", 0), handler)
        cls.base = f"http://127.0.0.1:{cls.servidor.server_address[1]}"
        cls.thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.thread.join(timeout=5)

    def _req(self, method: str, path: str, body: bytes | None = None) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"} if body is not None else {}
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            try:
                return err.code, json.loads(err.read().decode("utf-8"))
            finally:
                err.close()

    def test_rotas_exatas_e_metodos_no_servidor_de_reserva(self) -> None:
        status_get, corpo_get = self._req("GET", "/api/v1/catalogs/characteristics")
        self.assertEqual(status_get, 200)
        self.assertEqual(corpo_get["total_caracteristicas"], 10)

        status_405_get, _ = self._req("GET", "/api/v1/catalogs/characteristics/select")
        self.assertEqual(status_405_get, 405)

        for path in ("/api/v1/catalogs/characteristics_outro", "/api/v1/catalogs/outro"):
            with self.subTest(path=path):
                status_404, _ = self._req("GET", path)
                self.assertEqual(status_404, 404)

        status_post, corpo_post = self._req(
            "POST",
            "/api/v1/catalogs/characteristics/select",
            json.dumps({"selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"]}).encode("utf-8"),
        )
        self.assertEqual(status_post, 200)
        self.assertEqual(corpo_post["selected_count"], 1)

        status_405_post, _ = self._req(
            "POST",
            "/api/v1/catalogs/characteristics",
            json.dumps({}).encode("utf-8"),
        )
        self.assertEqual(status_405_post, 405)

        status_404_post, _ = self._req(
            "POST",
            "/api/v1/catalogs/characteristics/select/extra",
            json.dumps({"selected_ids": []}).encode("utf-8"),
        )
        self.assertEqual(status_404_post, 404)

    def test_erros_de_schema_devolvem_500_json_no_servidor_de_reserva(self) -> None:
        with patch(
            "iris.api.routes.catalogs.get_characteristics_catalog_service",
            side_effect=CatalogValidationError("Catálogo corrompido"),
        ):
            status_get, corpo_get = self._req("GET", "/api/v1/catalogs/characteristics")
        self.assertEqual(status_get, 500)
        self.assertEqual(corpo_get["detail"]["code"], "CATALOG_SCHEMA_ERROR")

        with patch(
            "iris.api.routes.catalogs.select_surgical_characteristics_service",
            side_effect=CatalogValidationError("Catálogo corrompido"),
        ):
            status_post, corpo_post = self._req(
                "POST",
                "/api/v1/catalogs/characteristics/select",
                json.dumps({"selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"]}).encode("utf-8"),
            )
        self.assertEqual(status_post, 500)
        self.assertEqual(corpo_post["detail"]["code"], "CATALOG_SCHEMA_ERROR")


if __name__ == "__main__":
    unittest.main()

