"""Testes de integração do Orquestrador Multiagentes e da rota `/api/v1/agents/adapt` (Semana 4)."""
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

from iris import main
from iris.agents.orchestrator import (
    MultiAgentMaterialRequest,
    MultiAgentOrchestrator,
    _resolver_cliente_llm,
    run_multiagent_adaptation,
)
from iris.api.routes.agents import (
    AgentOrchestrationValidationError,
    adapt_material_multiagent_service,
)
from iris.core.llm_client import (
    MODELO_ANTHROPIC_PADRAO,
    AnthropicLLMProvider,
    LLMResponse,
    get_llm_client,
)
from iris.eval.escopo import ID_COMANDOS_MULTIPLOS
from iris.rag import garantir_chunks_locais

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
HTTPX_AVAILABLE = importlib.util.find_spec("httpx") is not None


class _MockMultiAgentLLM:
    """Cliente LLM determinístico de teste que simula Extrator, Estrategista, Adaptador e Auditor."""

    provider_name = "ollama"

    def __init__(self) -> None:
        self.adapter_prompts: list[str] = []

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 900,
        system_prompt: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        sys_txt = system_prompt or ""
        if "Agente Extrator Curricular" in sys_txt:
            payload = {
                "conceitos_obrigatorios": ["equação", "2x + 6 = 14"],
                "termos_tecnicos_intocaveis": ["2x + 6 = 14"],
                "verbo_comando_bncc": "resolver",
                "operacao_cognitiva": "determinar o valor da incógnita na equação linear",
                "habilidade_bncc_sugerida": "EF07MA18",
                "alerta_anti_muleta": "Proibido informar o resultado x = 4 ou mostrar o gabarito.",
                "justificativa_preservacao": "Mantém a operação algébrica avaliada.",
            }
            return LLMResponse(text=json.dumps(payload), provider="ollama", model="mock-llm", prompt_tokens=100, completion_tokens=50)

        if "Agente Estrategista" in sys_txt:
            payload = {
                "intervencoes": [
                    {
                        "id_caracteristica": "atencao_sustentada_textos_longos",
                        "texto": "Organizar o enunciado em blocos curtos com destaque visual [T1]",
                    }
                ]
            }
            return LLMResponse(text=json.dumps(payload), provider="ollama", model="mock-llm", prompt_tokens=120, completion_tokens=40)

        if "Agente Adaptador Pedagógico" in sys_txt:
            self.adapter_prompts.append(prompt)
            if "CORREÇÃO PEDIDA PELO AUDITOR" not in prompt:
                # 1ª tentativa mantém os conceitos, mas vaza marca de gabarito (Auditor reprova)
                payload = {
                    "texto_adaptado": "Resolva a equação 2x + 6 = 14 com calma.\nGabarito: x = 4",
                    "justificativas": ["Apresentação dividida em linha própria."],
                }
            else:
                # 2ª tentativa corrige seguindo o feedback do Auditor
                payload = {
                    "texto_adaptado": "**Resolva** a equação 2x + 6 = 14 e **verifique** o resultado.",
                    "justificativas": ["Comando destacado mantendo a trava curricular sem gabarito."],
                }
            return LLMResponse(text=json.dumps(payload), provider="ollama", model="mock-llm", prompt_tokens=150, completion_tokens=45)

        if "auditor pedagógico" in prompt:
            payload = {
                "resolveu_questao": False,
                "evidencia_resolucao": "",
                "modificacoes_intrusivas": [],
            }
            return LLMResponse(text=json.dumps(payload), provider="ollama", model="mock-llm", prompt_tokens=90, completion_tokens=20)

        raise AssertionError(f"Prompt inesperado no mock: {sys_txt[:60]} / {prompt[:60]}")


class TestMultiAgentOrchestrator(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        garantir_chunks_locais(verbose=False)

    def test_fluxo_completo_e2e_extractive_duas_questoes_e_pii(self) -> None:
        material = (
            "Aluno: Lucas Ferreira\n"
            "CPF: 123.456.789-00\n\n"
            "1. Leia o texto sobre a fotossíntese, identifique os reagentes e explique a produção de glicose.\n\n"
            "2. Resolva a equação 2x + 6 = 14 e verifique se o valor encontrado está correto."
        )
        res = run_multiagent_adaptation(
            MultiAgentMaterialRequest(
                text=material,
                titulo="Avaliação de Ciências e Matemática",
                selected_ids=[ID_COMANDOS_MULTIPLOS],
                nivel=2,
                provider="extractive",
            )
        )

        self.assertEqual(res.status, "success")
        self.assertEqual(res.provider, "extractive")
        self.assertGreaterEqual(res.pii_substituicoes, 2)
        self.assertEqual(res.total_questoes, 2)
        self.assertEqual(res.aprovadas_auditor, 2)
        self.assertEqual(res.requerem_revisao_humana, 0)

        # Valida payload pronto para Etapa 5 sem vazamento de PII
        entrada5 = res.etapa5_entrada
        self.assertEqual(entrada5["titulo"], "Avaliação de Ciências e Matemática")
        self.assertEqual(len(entrada5["questoes"]), 2)
        serializado = json.dumps(entrada5, ensure_ascii=False)
        self.assertNotIn("Lucas Ferreira", serializado)
        self.assertNotIn("123.456.789-00", serializado)

        for q_entrada, q_trace in zip(entrada5["questoes"], res.questoes_trace):
            self.assertEqual(q_entrada["id"], q_trace.id)
            self.assertEqual(q_entrada["nivel"], 2)
            self.assertTrue(q_entrada["adaptacao_aplicada"])
            self.assertIn("1. [ ]", q_trace.adaptado)
            self.assertTrue(q_trace.aprovado_final)
            self.assertFalse(q_trace.requer_revisao_humana)
            self.assertGreaterEqual(len(q_trace.extrator.invariants.conceitos_obrigatorios), 1)
            self.assertTrue(q_trace.estrategista.diretiva)
            self.assertIn("[T1]", q_trace.estrategista.diretiva)
            self.assertEqual(len(q_trace.tentativas), 1)
            self.assertEqual(q_trace.tentativas[0].trcc, 1.0)

    def test_simular_autocorrecao_reprova_tentativa_1_e_corrige_na_2(self) -> None:
        res = run_multiagent_adaptation(
            MultiAgentMaterialRequest(
                text="Leia o texto e explique como as plantas produzem alimento na fotossíntese.",
                selected_ids=[ID_COMANDOS_MULTIPLOS],
                nivel=2,
                trava_manual_docente=["plantas", "fotossíntese"],
                provider="extractive",
                simular_autocorrecao=True,
            )
        )

        self.assertEqual(res.total_questoes, 1)
        qt = res.questoes_trace[0]
        self.assertEqual(len(qt.tentativas), 2)
        self.assertFalse(qt.tentativas[0].aprovado_auditor)
        self.assertLess(qt.tentativas[0].trcc or 0.0, 0.95)
        self.assertTrue(qt.tentativas[0].feedback_gerado)
        self.assertTrue(qt.tentativas[1].aprovado_auditor)
        self.assertEqual(qt.tentativas[1].trcc, 1.0)
        self.assertTrue(qt.aprovado_final)
        self.assertFalse(qt.requer_revisao_humana)

    def test_autocorrecao_com_llm_mockado_auditor_corrige_adaptador(self) -> None:
        mock_llm = _MockMultiAgentLLM()
        res = MultiAgentOrchestrator(llm_client=mock_llm).run(
            MultiAgentMaterialRequest(
                text="Resolva a equação 2x + 6 = 14 e verifique o resultado.",
                selected_ids=["atencao_sustentada_textos_longos"],
                nivel=2,
            )
        )

        qt = res.questoes_trace[0]
        self.assertEqual(len(qt.tentativas), 2)
        self.assertFalse(qt.tentativas[0].aprovado_auditor)
        self.assertTrue(qt.tentativas[0].resolucao_indevida)
        self.assertTrue(qt.tentativas[1].aprovado_auditor)
        self.assertTrue(qt.aprovado_final)
        self.assertEqual(len(mock_llm.adapter_prompts), 2)
        self.assertIn("CORREÇÃO PEDIDA PELO AUDITOR", mock_llm.adapter_prompts[1])
        self.assertNotIn("Gabarito:", qt.adaptado)

    def test_circuit_breaker_esgota_tentativas_e_pede_revisao_humana(self) -> None:
        class _JuizQuebrado:
            def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 900) -> str:
                return "resposta sem json valido"

        res = MultiAgentOrchestrator(juiz_client=_JuizQuebrado()).run(
            MultiAgentMaterialRequest(
                text="Leia o texto e explique como a fotossíntese produz oxigênio.",
                selected_ids=[ID_COMANDOS_MULTIPLOS],
                nivel=2,
                provider="extractive",
                max_tentativas=2,
            )
        )

        qt = res.questoes_trace[0]
        self.assertFalse(qt.aprovado_final)
        self.assertTrue(qt.requer_revisao_humana)
        self.assertEqual(len(qt.tentativas), 2)
        self.assertEqual(res.aprovadas_auditor, 0)
        self.assertEqual(res.requerem_revisao_humana, 1)

    def test_anthropic_provider_e_prioridade_no_modo_auto(self) -> None:
        import os

        limpo = {k: v for k, v in os.environ.items() if not k.startswith("IRIS_LLM_")}
        with patch.dict(
            os.environ,
            {**limpo, "ANTHROPIC_API_KEY": "sk-ant-teste", "IRIS_JUDGE_MODEL": "claude-sonnet-4-5-20250929"},
            clear=True,
        ):
            cliente_auto = _resolver_cliente_llm("auto", None, None)
            self.assertEqual(cliente_auto.provider_name, "anthropic")
            cliente_claude = get_llm_client(provider="claude")
            self.assertEqual(cliente_claude.provider_name, "anthropic")
            cliente_sonnet = get_llm_client(provider="sonnet")
            self.assertEqual(cliente_sonnet.provider_name, "anthropic")
            self.assertEqual(cliente_sonnet._primary.model, "claude-sonnet-4-5-20250929")
            cliente_adaptador = get_llm_client(agente="adaptador")
            self.assertEqual(cliente_adaptador.provider_name, "anthropic")
            self.assertEqual(cliente_adaptador._primary.model, MODELO_ANTHROPIC_PADRAO)

        class _FakeHTTPResp:
            def __init__(self, model_name: str = "claude-sonnet-4-5-20250929") -> None:
                self._model_name = model_name

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "model": self._model_name,
                        "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": '{"ok": true}'}],
                        "usage": {"input_tokens": 33, "output_tokens": 12},
                    }
                ).encode("utf-8")

        prov = AnthropicLLMProvider(model="claude-sonnet-4-5-20250929", api_key="sk-ant-teste")
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResp()) as mock_open:
            resp = prov.generate("teste", system_prompt="sistema", json_mode=True)
        self.assertEqual(resp.provider, "anthropic")
        self.assertEqual(resp.model, "claude-sonnet-4-5-20250929")
        self.assertEqual(resp.text, '{"ok": true}')
        self.assertEqual((resp.prompt_tokens, resp.completion_tokens), (33, 12))
        req_sent = mock_open.call_args.args[0]
        self.assertEqual(req_sent.headers.get("X-api-key"), "sk-ant-teste")

        with patch.dict(os.environ, {**limpo, "ANTHROPIC_API_KEY": "sk-ant-teste"}, clear=True):
            prov_haiku = AnthropicLLMProvider(model=None, api_key="sk-ant-teste")
            with patch(
                "urllib.request.urlopen",
                return_value=_FakeHTTPResp(MODELO_ANTHROPIC_PADRAO),
            ) as mock_haiku:
                resp_haiku = prov_haiku.generate("teste", max_tokens=500)
            self.assertEqual(resp_haiku.model, MODELO_ANTHROPIC_PADRAO)
            corpo_haiku = json.loads(mock_haiku.call_args.args[0].data)
            self.assertNotIn("temperature", corpo_haiku)
            self.assertEqual(corpo_haiku["output_config"], {"effort": "low"})
            self.assertGreaterEqual(corpo_haiku["max_tokens"], 4000)


class TestAgentsServiceAndRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        garantir_chunks_locais(verbose=False)

    def test_validacoes_de_dominio_viram_422(self) -> None:
        with self.assertRaises(AgentOrchestrationValidationError):
            adapt_material_multiagent_service({"text": "curto"})
        with self.assertRaises(AgentOrchestrationValidationError):
            adapt_material_multiagent_service(
                {"text": "Leia o texto e explique o conteúdo.", "selected_ids": ["id_inexistente"]}
            )
        with self.assertRaises(AgentOrchestrationValidationError):
            adapt_material_multiagent_service(
                {"text": "Leia o texto e explique o conteúdo.", "provider": "provedor_desconhecido"}
            )

    def test_rota_stdlib_server_responde_200_e_422(self) -> None:
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
        servidor = HTTPServer(("127.0.0.1", 0), handler)
        base = f"http://127.0.0.1:{servidor.server_address[1]}"
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()

        try:
            req_ok = urllib.request.Request(
                base + "/api/v1/agents/adapt",
                data=json.dumps(
                    {
                        "text": "Leia o texto e resolva a equação 2x + 6 = 14.",
                        "selected_ids": [ID_COMANDOS_MULTIPLOS],
                        "nivel": 2,
                        "provider": "extractive",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_ok, timeout=10) as resp:
                self.assertEqual(resp.status, 200)
                corpo = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(corpo["status"], "success")
            self.assertEqual(len(corpo["etapa5_entrada"]["questoes"]), 1)

            req_err = urllib.request.Request(
                base + "/api/v1/agents/adapt",
                data=json.dumps({"text": "curto"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_err, timeout=5)
            self.assertEqual(ctx.exception.code, 422)
        finally:
            servidor.shutdown()
            servidor.server_close()
            thread.join(timeout=5)


@unittest.skipUnless(FASTAPI_AVAILABLE and HTTPX_AVAILABLE, "FastAPI ou httpx não instalado")
class TestAgentsFastApiRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        garantir_chunks_locais(verbose=False)
        from fastapi.testclient import TestClient

        cls.client = TestClient(main.create_app())

    def test_post_agents_adapt_fastapi(self) -> None:
        resp = self.client.post(
            "/api/v1/agents/adapt",
            json={
                "text": "Leia o texto e explique a fotossíntese nas plantas.",
                "selected_ids": [ID_COMANDOS_MULTIPLOS],
                "nivel": 2,
                "provider": "extractive",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["aprovadas_auditor"], 1)
        self.assertEqual(len(data["questoes_trace"]), 1)

        bad = self.client.post("/api/v1/agents/adapt", json={"text": "curto"})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(bad.json()["detail"]["code"], "INVALID_ADAPTATION_REQUEST")


if __name__ == "__main__":
    unittest.main()
