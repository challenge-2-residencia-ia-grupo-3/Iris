"""Testes unitários e de integração da História 1.3.1 (Issue #12 — Calibragem de Andaime Cognitivo).

Verifica todos os Critérios de Aceitação BDD:
1. Calibragem dos Níveis 1 (Leve), 2 (Moderado) e 3 (Intensivo) com diretrizes estruturais corretas.
2. Atribuição cirúrgica estrita: apenas as características em `selected_ids` recebem diretivas de andaime.
3. As características não selecionadas são mantidas isoladas em `caracteristicas_bloqueadas_ids`.
4. Rejeição de níveis inválidos fora de {1, 2, 3} com código `INVALID_SCAFFOLDING_LEVEL`.
5. Rejeição de seleção vazia com código `EMPTY_CHARACTERISTIC_SELECTION`.
6. Rejeição de características desconhecidas com código `UNKNOWN_CHARACTERISTIC_ID`.
7. Rejeição de campos extras ou clínicos (Pilar 1 & LGPD).
8. Integração via API FastAPI e servidor HTTP de reserva (stdlib).
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

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from iris import main
from iris.api.routes import scaffolding as scaffolding_routes
from iris.api.routes.scaffolding import (
    calibrate_scaffolding_session_service,
    get_scaffolding_levels_service,
)
from iris.schemas.catalog import load_official_tdah_catalog
from iris.schemas.scaffolding import (
    NIVEL_INTENSIVO,
    NIVEL_LEVE,
    NIVEL_MODERADO,
    ScaffoldingCalibrationRequest,
    ScaffoldingValidationError,
    calibrate_scaffolding_service,
)

FASTAPI_DISPONIVEL = scaffolding_routes.router is not None
HTTPX_DISPONIVEL = importlib.util.find_spec("httpx") is not None


class TestScaffoldingCalibration(unittest.TestCase):
    """Testes unitários para regras de negócio e contratos de calibração de andaime cognitivo."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_official_tdah_catalog()

    def test_get_scaffolding_levels_metadata(self) -> None:
        """Verifica se os metadados dos 3 níveis contêm transformações e salvaguardas."""
        meta = get_scaffolding_levels_service()
        self.assertEqual(meta["status"], "success")
        self.assertEqual(len(meta["niveis"]), 3)
        niveis_map = {n["nivel"]: n for n in meta["niveis"]}

        self.assertIn(1, niveis_map)
        self.assertIn(2, niveis_map)
        self.assertIn(3, niveis_map)

        self.assertIn("negrito", niveis_map[1]["transformacoes_estruturais"][0].lower())
        self.assertIn("chunking", niveis_map[2]["transformacoes_estruturais"][0].lower())
        self.assertIn("decomposição", niveis_map[3]["transformacoes_estruturais"][0].lower())

        self.assertIn("aviso_antimuleta_global", meta)

    def test_calibrate_level_1_light_scaffolding(self) -> None:
        """Nível 1 deve produzir diretivas tipográficas e de acessibilidade visual."""
        selected = ["sobrecarga_memoria_trabalho_comandos_multiplos"]
        resp = calibrate_scaffolding_service(
            payload={"selected_ids": selected, "nivel": NIVEL_LEVE},
            catalog=self.catalog,
        )
        self.assertEqual(resp.nivel, 1)
        self.assertEqual(resp.nome_curto, "Leve")
        self.assertEqual(resp.total_caracteristicas_afetadas, 1)
        self.assertEqual(len(resp.caracteristicas_afetadas), 1)

        directive = resp.caracteristicas_afetadas[0]
        self.assertEqual(directive.id_caracteristica, selected[0])
        self.assertEqual(directive.nivel, 1)
        self.assertIn("negrito", directive.acoes_permitidas[0].lower())

        self.assertNotIn(selected[0], resp.caracteristicas_bloqueadas_ids)
        self.assertEqual(len(resp.caracteristicas_bloqueadas_ids), 9)

    def test_calibrate_level_2_moderate_scaffolding(self) -> None:
        """Nível 2 deve produzir checklists de etapas e fragmentação."""
        selected = ["sobrecarga_memoria_trabalho_comandos_multiplos", "atencao_sustentada_textos_longos"]
        resp = calibrate_scaffolding_service(
            payload={"selected_ids": selected, "nivel": NIVEL_MODERADO},
            catalog=self.catalog,
        )
        self.assertEqual(resp.nivel, 2)
        self.assertEqual(resp.nome_curto, "Moderado")
        self.assertEqual(resp.total_caracteristicas_afetadas, 2)
        self.assertEqual(len(resp.caracteristicas_afetadas), 2)

        ids_afetados = [d.id_caracteristica for d in resp.caracteristicas_afetadas]
        self.assertEqual(ids_afetados, selected)

        for d in resp.caracteristicas_afetadas:
            self.assertEqual(d.nivel, 2)

        self.assertEqual(len(resp.caracteristicas_bloqueadas_ids), 8)

    def test_calibrate_level_3_intensive_scaffolding(self) -> None:
        """Nível 3 deve produzir decomposição guiada e pausas ativas."""
        selected = ["bloqueio_iniciacao_tarefas_abertas"]
        resp = calibrate_scaffolding_service(
            payload={"selected_ids": selected, "nivel": NIVEL_INTENSIVO},
            catalog=self.catalog,
        )
        self.assertEqual(resp.nivel, 3)
        self.assertEqual(resp.nome_curto, "Intensivo")
        self.assertEqual(resp.total_caracteristicas_afetadas, 1)

        directive = resp.caracteristicas_afetadas[0]
        self.assertEqual(directive.nivel, 3)
        self.assertIn("adaptação intensiva", directive.rotulo.lower())

    def test_surgical_isolation_strictly_respects_selected_ids(self) -> None:
        """Garante que características bloqueadas não recebam transformações (Pilar 1)."""
        selected = ["distratibilidade_poluicao_visual_layout"]
        resp = calibrate_scaffolding_service(
            payload={"selected_ids": selected, "nivel": 2},
            catalog=self.catalog,
        )
        ids_afetados = {d.id_caracteristica for d in resp.caracteristicas_afetadas}
        self.assertEqual(ids_afetados, {"distratibilidade_poluicao_visual_layout"})

        for blocked_id in resp.caracteristicas_bloqueadas_ids:
            self.assertNotEqual(blocked_id, "distratibilidade_poluicao_visual_layout")

    def test_reject_invalid_level(self) -> None:
        """Níveis fora de {1, 2, 3} devem ser rejeitados com INVALID_SCAFFOLDING_LEVEL."""
        for invalid in [0, 4, -1, 99]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ScaffoldingValidationError) as ctx:
                    calibrate_scaffolding_service(
                        payload={"selected_ids": ["atencao_sustentada_textos_longos"], "nivel": invalid},
                        catalog=self.catalog,
                    )
                self.assertEqual(ctx.exception.code, "INVALID_SCAFFOLDING_LEVEL")
                self.assertEqual(ctx.exception.field, "nivel")

    def test_reject_empty_selection(self) -> None:
        """Seleção vazia deve ser rejeitada com EMPTY_CHARACTERISTIC_SELECTION."""
        with self.assertRaises(ScaffoldingValidationError) as ctx:
            calibrate_scaffolding_service(
                payload={"selected_ids": [], "nivel": 2},
                catalog=self.catalog,
            )
        self.assertEqual(ctx.exception.code, "EMPTY_CHARACTERISTIC_SELECTION")

    def test_reject_unknown_characteristic_id(self) -> None:
        """ID inexistente no catálogo deve ser rejeitado com UNKNOWN_CHARACTERISTIC_ID."""
        with self.assertRaises(ScaffoldingValidationError) as ctx:
            calibrate_scaffolding_service(
                payload={"selected_ids": ["id_inexistente_qualquer"], "nivel": 1},
                catalog=self.catalog,
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_CHARACTERISTIC_ID")

    def test_reject_extra_or_clinical_fields(self) -> None:
        """Rejeita campos extras como 'cid_medico' ou 'diagnostico' (extra='forbid')."""
        with self.assertRaises(ScaffoldingValidationError) as ctx:
            calibrate_scaffolding_service(
                payload={
                    "selected_ids": ["atencao_sustentada_textos_longos"],
                    "nivel": 2,
                    "cid_medico": "F90.0",
                },
                catalog=self.catalog,
            )
        self.assertEqual(ctx.exception.code, "EXTRA_FIELD_FORBIDDEN")
        self.assertEqual(ctx.exception.field, "cid_medico")


class TestScaffoldingServerApi(unittest.TestCase):
    """Testes de ponta a ponta na API HTTP via servidor de reserva (stdlib)."""

    @classmethod
    def setUpClass(cls) -> None:
        capturado = {}

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

    def _get(self, caminho: str) -> tuple[int, dict]:
        req = urllib.request.Request(self.base + caminho, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode("utf-8"))

    def _post(self, caminho: str, corpo: bytes) -> tuple[int, dict]:
        req = urllib.request.Request(
            self.base + caminho, data=corpo, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode("utf-8"))

    def test_api_get_scaffolding_levels_returns_200(self) -> None:
        status, corpo = self._get("/api/v1/scaffolding/levels")
        self.assertEqual(status, 200)
        self.assertEqual(corpo["status"], "success")
        self.assertEqual(len(corpo["niveis"]), 3)

    def test_api_post_calibrate_valid_returns_200(self) -> None:
        payload = {
            "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
            "nivel": 2,
        }
        status, corpo = self._post("/api/v1/scaffolding/calibrate", json.dumps(payload).encode("utf-8"))
        self.assertEqual(status, 200)
        self.assertEqual(corpo["nivel"], 2)
        self.assertEqual(corpo["total_caracteristicas_afetadas"], 1)
        self.assertEqual(len(corpo["caracteristicas_bloqueadas_ids"]), 9)

    def test_api_post_calibrate_invalid_level_returns_422(self) -> None:
        payload = {
            "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
            "nivel": 5,
        }
        status, corpo = self._post("/api/v1/scaffolding/calibrate", json.dumps(payload).encode("utf-8"))
        self.assertEqual(status, 422)
        self.assertEqual(corpo["detail"]["code"], "INVALID_SCAFFOLDING_LEVEL")


if __name__ == "__main__":
    unittest.main()
