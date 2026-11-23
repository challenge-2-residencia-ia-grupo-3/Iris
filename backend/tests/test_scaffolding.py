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

    def test_api_post_curriculum_locks_validate_returns_200_with_invariants(self) -> None:
        payload = {
            "selected_ids": ["atencao_sustentada_textos_longos"],
            "nivel": 1,
            "trava_curricular": {
                "conceitos_obrigatorios": ["fotossíntese", "cloroplastos"],
                "habilidade_bncc": "EF06CI05",
                "verbo_comando_bncc": "explicar",
                "objetivo_avaliativo": "Explicar o papel dos cloroplastos na fotossíntese.",
            },
        }
        status, corpo = self._post(
            "/api/v1/scaffolding/curriculum-locks/validate",
            json.dumps(payload).encode("utf-8"),
        )
        self.assertEqual(status, 200)
        self.assertTrue(corpo["invariantes_auditor"]["blindagem_ativa"])
        self.assertEqual(
            corpo["invariantes_auditor"]["conceitos_obrigatorios"],
            ["fotossíntese", "cloroplastos"],
        )
        self.assertEqual(corpo["invariantes_auditor"]["trcc_minimo_exigido"], 0.95)
        self.assertFalse(corpo["alerta_preventivo_antimuleta"]["emitido"])

    def test_api_post_curriculum_locks_validate_empty_returns_422(self) -> None:
        payload = {
            "selected_ids": ["atencao_sustentada_textos_longos"],
            "nivel": 1,
            "trava_curricular": {
                "conceitos_obrigatorios": [],
            },
        }
        status, corpo = self._post(
            "/api/v1/scaffolding/curriculum-locks/validate",
            json.dumps(payload).encode("utf-8"),
        )
        self.assertEqual(status, 422)
        self.assertEqual(corpo["detail"]["code"], "EMPTY_CURRICULUM_LOCK")


class TestCurriculumLocksAndAntiCrutch(unittest.TestCase):
    """Testes da História 1.3.2 (Issue #13): Travas Curriculares Inegociáveis e Alerta Preventivo Anti-Muleta."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_official_tdah_catalog()

    def test_marks_concepts_as_mandatory_invariants_for_auditor(self) -> None:
        """Critério BDD 1: Conceitos inseridos na Trava Curricular são marcados como invariantes obrigatórios para o Auditor."""
        resp = calibrate_scaffolding_service(
            payload={
                "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
                "nivel": NIVEL_MODERADO,
                "trava_curricular": {
                    "conceitos_obrigatorios": ["equação", "incógnita", "2x + 6 = 14", "equação"],
                    "termos_tecnicos_intocaveis": ["incógnita", "2x + 6 = 14"],
                    "habilidade_bncc": "EF07MA18",
                    "verbo_comando_bncc": "Calcule",
                    "objetivo_avaliativo": "Resolver equações polinomiais do 1º grau.",
                },
            },
            catalog=self.catalog,
        )
        self.assertTrue(resp.invariantes_auditor.blindagem_ativa)
        self.assertEqual(
            resp.invariantes_auditor.conceitos_obrigatorios,
            ["equação", "incógnita", "2x + 6 = 14"],
        )
        self.assertEqual(
            resp.invariantes_auditor.termos_tecnicos_intocaveis,
            ["incógnita", "2x + 6 = 14"],
        )
        self.assertEqual(resp.invariantes_auditor.verbo_comando_bncc, "calcular")
        self.assertEqual(resp.invariantes_auditor.habilidade_bncc, "EF07MA18")
        self.assertEqual(resp.invariantes_auditor.trcc_minimo_exigido, 0.95)
        self.assertFalse(resp.alerta_preventivo_antimuleta.emitido)

    def test_emits_critical_anti_crutch_alert_on_interpretative_summary_in_reading_question(self) -> None:
        """Critério BDD 2: Pedir resumo interpretativo em questão que avalia interpretação de texto emite alerta preventivo anti-muleta."""
        resp = calibrate_scaffolding_service(
            payload={
                "selected_ids": ["atencao_sustentada_textos_longos"],
                "nivel": NIVEL_MODERADO,
                "trava_curricular": {
                    "conceitos_obrigatorios": ["ironia", "intenção do autor"],
                    "habilidade_bncc": "EF67LP08",
                    "verbo_comando_bncc": "interpretar",
                    "objetivo_avaliativo": "Avaliar interpretação de texto e inferência na crônica.",
                    "observacao_adaptacao_docente": "Incluir um resumo interpretativo explicando o texto para o aluno.",
                },
            },
            catalog=self.catalog,
        )
        alerta = resp.alerta_preventivo_antimuleta
        self.assertTrue(alerta.emitido)
        self.assertEqual(alerta.severidade, "critical")
        self.assertEqual(alerta.codigo, "CONTRADICAO_DIRETA_INTERPRETACAO")
        self.assertIn("resumo interpretativo", alerta.mensagem.lower())
        self.assertGreaterEqual(len(alerta.conflitos_detectados), 1)

    def test_emits_critical_anti_crutch_alert_on_ready_formula_in_math_question(self) -> None:
        """Pedir fórmula pronta ou passo resolvido em questão de cálculo/equação emite alerta crítico anti-muleta."""
        resp = calibrate_scaffolding_service(
            payload={
                "selected_ids": ["retencao_dados_intermediarios_problemas_multietapas"],
                "nivel": NIVEL_MODERADO,
                "trava_curricular": {
                    "conceitos_obrigatorios": ["equação", "2x + 6 = 14"],
                    "verbo_comando_bncc": "calcular",
                    "objetivo_avaliativo": "Calcular o valor da incógnita na equação.",
                    "observacao_adaptacao_docente": "Entregar a fórmula pronta e o primeiro passo resolvido.",
                },
            },
            catalog=self.catalog,
        )
        alerta = resp.alerta_preventivo_antimuleta
        self.assertTrue(alerta.emitido)
        self.assertEqual(alerta.severidade, "critical")
        self.assertEqual(alerta.codigo, "CONTRADICAO_DIRETA_CALCULO")

    def test_emits_warning_when_level_3_intensive_used_for_inference_skill(self) -> None:
        """Nível 3 (Intensivo) em questão de inferência/interpretação emite aviso preventivo sugerindo Nível 2."""
        resp = calibrate_scaffolding_service(
            payload={
                "selected_ids": ["bloqueio_iniciacao_tarefas_abertas"],
                "nivel": NIVEL_INTENSIVO,
                "trava_curricular": {
                    "conceitos_obrigatorios": ["sentido implícito", "humor"],
                    "verbo_comando_bncc": "inferir",
                    "objetivo_avaliativo": "Inferir o sentido implícito da tirinha.",
                },
            },
            catalog=self.catalog,
        )
        alerta = resp.alerta_preventivo_antimuleta
        self.assertTrue(alerta.emitido)
        self.assertEqual(alerta.severidade, "warning")
        self.assertEqual(alerta.codigo, "RISCO_NIVEL_INTENSIVO_INFERENCIA")
        self.assertEqual(alerta.nivel_sugerido, NIVEL_MODERADO)

    def test_emits_glossary_caution_when_vocabulary_support_active_with_locked_terms(self) -> None:
        """Suporte intensivo de iniciação/expressão escrita em Nível 3 com termos intocáveis travados emite salvaguarda."""
        resp = calibrate_scaffolding_service(
            payload={
                "selected_ids": ["organizacao_sequencial_expressao_escrita"],
                "nivel": NIVEL_INTENSIVO,
                "trava_curricular": {
                    "conceitos_obrigatorios": ["mitocôndria", "respiração celular"],
                    "termos_tecnicos_intocaveis": ["mitocôndria", "respiração celular"],
                    "verbo_comando_bncc": "explicar",
                },
            },
            catalog=self.catalog,
        )
        alerta = resp.alerta_preventivo_antimuleta
        self.assertTrue(alerta.emitido)
        self.assertEqual(alerta.severidade, "warning")
        self.assertEqual(alerta.codigo, "CAUTELA_GLOSSARIO_TERMOS_TRAVADOS")

    def test_sanitizes_pii_and_rejects_clinical_references_in_curriculum_lock(self) -> None:
        """Garante sanitização de PII (RNF-02) e rejeição de menções clínicas/CID (RNF-03) na trava curricular."""
        resp = calibrate_scaffolding_service(
            payload={
                "selected_ids": ["atencao_sustentada_textos_longos"],
                "nivel": NIVEL_LEVE,
                "trava_curricular": {
                    "conceitos_obrigatorios": ["fotossíntese"],
                    "objetivo_avaliativo": "Avaliar o aluno Gabriel Silva na explicação da fotossíntese.",
                },
            },
            catalog=self.catalog,
        )
        self.assertTrue(resp.pii_removido_automaticamente)
        self.assertNotIn("Gabriel Silva", resp.trava_curricular.objetivo_avaliativo or "")
        self.assertIn("[ESTUDANTE]", resp.trava_curricular.objetivo_avaliativo or "")

        with self.assertRaises(ScaffoldingValidationError) as ctx:
            calibrate_scaffolding_service(
                payload={
                    "selected_ids": ["atencao_sustentada_textos_longos"],
                    "nivel": NIVEL_LEVE,
                    "trava_curricular": {
                        "conceitos_obrigatorios": ["laudo médico CID F90.0"],
                    },
                },
                catalog=self.catalog,
            )
        self.assertEqual(ctx.exception.code, "CLINICAL_REFERENCE_FORBIDDEN")


from iris.schemas.scaffolding import parse_and_sanitize_curriculum_lock  # noqa: E402


class TestRevisaoPR115(unittest.TestCase):
    """Achados da revisão do PR #115: pedido x objetivo, termos clínicos sobre pessoas e cabeçalho do material."""

    @staticmethod
    def _alerta(objetivo: str | None, observacao: str | None = None, nivel: int = NIVEL_LEVE):
        from iris.schemas.scaffolding import evaluate_preventive_anti_crutch, parse_and_sanitize_curriculum_lock

        lock, _ = parse_and_sanitize_curriculum_lock(
            {"objetivo_avaliativo": objetivo, "observacao_adaptacao_docente": observacao}
        )
        return evaluate_preventive_anti_crutch(nivel, [], lock)

    # --- achado 1: o objetivo avaliativo não é um pedido de adaptação
    def test_objetivo_que_cita_a_habilidade_ou_proibe_a_muleta_nao_dispara_alerta(self) -> None:
        for objetivo in (
            "Avaliar se o aluno sabe resumir o texto e identificar a ideia central",
            "Resolver a equação e chegar ao resultado sem consultar o gabarito",
            "Interpretar o poema; não entregar resposta pronta ao aluno",
            "Interpretar o poema sem dar a ideia central pronta",
        ):
            with self.subTest(objetivo=objetivo):
                self.assertFalse(self._alerta(objetivo).emitido)

    def test_pedido_explicito_na_observacao_continua_disparando(self) -> None:
        a = self._alerta("Avaliar interpretação de texto", "Incluir um resumo interpretativo para o aluno.")
        self.assertTrue(a.emitido)
        self.assertEqual(a.codigo, "CONTRADICAO_DIRETA_INTERPRETACAO")
        b = self._alerta("Calcular o valor da incógnita na equação.", "Entregar a fórmula pronta.")
        self.assertEqual(b.codigo, "CONTRADICAO_DIRETA_CALCULO")

    def test_pedido_negado_na_observacao_nao_dispara(self) -> None:
        for obs in ("Não incluir resumo interpretativo.", "Sem resumo interpretativo, apenas destaque visual."):
            with self.subTest(obs=obs):
                self.assertFalse(self._alerta("Avaliar interpretação de texto", obs).emitido)

    def test_pedido_com_verbo_dentro_do_objetivo_ainda_dispara(self) -> None:
        a = self._alerta("Avaliar interpretação de texto. Incluir resumo interpretativo para o aluno.")
        self.assertTrue(a.emitido)

    def test_negacao_so_vale_na_mesma_frase_e_perto_do_termo(self) -> None:
        a = self._alerta("Avaliar interpretação de texto", "Não use cores fortes. Incluir resumo interpretativo.")
        self.assertTrue(a.emitido)

    def test_nivel_3_em_inferencia_continua_gerando_aviso(self) -> None:
        a = self._alerta("Inferir o sentido implícito da tirinha.", None, NIVEL_INTENSIVO)
        self.assertEqual(a.codigo, "RISCO_NIVEL_INTENSIVO_INFERENCIA")

    # --- achado 2: laudo e diagnóstico sobre pessoas
    def test_laudo_e_diagnostico_sobre_pessoa_sao_recusados_na_trava(self) -> None:
        for texto in ("laudo de TDAH do Pedro", "diagnóstico de TEA", "aluno diagnosticado com dislexia", "laudo do Pedro"):
            with self.subTest(texto=texto), self.assertRaises(ScaffoldingValidationError) as ctx:
                parse_and_sanitize_curriculum_lock({"conceitos_obrigatorios": [texto]})
            self.assertEqual(ctx.exception.code, "CLINICAL_REFERENCE_FORBIDDEN")

    def test_conteudo_de_curriculo_parecido_continua_aceito(self) -> None:
        lock, _ = parse_and_sanitize_curriculum_lock(
            {"conceitos_obrigatorios": ["laudo técnico", "síndrome de Down", "medicamentos genéricos", "diagnóstico de rede"]}
        )
        self.assertEqual(len(lock.conceitos_obrigatorios), 4)

    def test_laudo_sobre_pessoa_no_objetivo_tambem_e_recusado(self) -> None:
        with self.assertRaises(ScaffoldingValidationError):
            parse_and_sanitize_curriculum_lock({"objetivo_avaliativo": "Explicar fotossíntese conforme o laudo do aluno"})

    # --- achado 3: cabeçalho do material
    def test_extracao_ignora_cabecalho_da_prova(self) -> None:
        from iris.schemas.scaffolding import extract_curriculum_locks_from_material

        lock = extract_curriculum_locks_from_material(
            "Escola Estadual X. Aluno: Pedro Souza. Leia o texto sobre fotossíntese e explique o papel do cloroplasto."
        )
        self.assertNotIn("estadual", lock.conceitos_obrigatorios)
        self.assertIn("fotossíntese", lock.conceitos_obrigatorios)
        self.assertNotIn("estadual", (lock.objetivo_avaliativo or "").lower())
        self.assertNotIn("Pedro", lock.objetivo_avaliativo or "")

    def test_extracao_nao_perde_o_material_quando_so_ha_cabecalho(self) -> None:
        from iris.schemas.scaffolding import extract_curriculum_locks_from_material

        lock = extract_curriculum_locks_from_material("Escola Municipal Machado de Assis.")
        self.assertIsNotNone(lock.objetivo_avaliativo)

    def test_invariantes_etapa3_propagam_para_o_orquestrador(self) -> None:
        from iris.agents.orchestrator import MultiAgentMaterialRequest, MultiAgentOrchestrator

        res = MultiAgentOrchestrator().run(
            MultiAgentMaterialRequest(
                text="Leia o texto e explique como a fotossíntese ocorre nos cloroplastos.",
                selected_ids=["sobrecarga_memoria_trabalho_comandos_multiplos"],
                nivel=3,
                provider="extractive",
                invariantes_etapa3={
                    "conceitos_obrigatorios": ["fotossíntese", "cloroplastos"],
                    "termos_tecnicos_intocaveis": ["clorofila"],
                    "habilidade_bncc": "EF06CI05",
                    "alerta_anti_muleta_auditor": "Proibido antecipar a conclusão lógica.",
                    "blindagem_ativa": True,
                },
            )
        )
        inv = res.questoes_trace[0].extrator.invariants
        self.assertIn("clorofila", inv.termos_tecnicos_intocaveis)
        self.assertEqual(inv.habilidade_bncc_sugerida, "EF06CI05")
        self.assertIn("Proibido antecipar a conclusão lógica.", inv.alerta_anti_muleta or "")


if __name__ == "__main__":
    unittest.main()
