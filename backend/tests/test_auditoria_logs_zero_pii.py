"""Testes de auditoria Zero-PII e não-retenção de payloads em logs (História 4.1.4 / Issue #37)."""
from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.agents.adapter_agent import AdapterAgent
from iris.core.llm_client import LLMResponse
from iris.main import create_app
from iris.schemas.adaptation import AdaptationRequest
from iris.schemas.curriculum import CurriculumInvariants
from iris.security.operational_logger import (
    ZeroPiiLogFilter,
    ZeroPiiLogFormatter,
    _ACTIVE_SENTINEL,
    capture_operational_logs,
    reset_operational_metrics,
    sentinel_context,
)


PROVA_COM_PII = (
    "Escola Municipal Cecília Meireles\n"
    "Aluno: Gabriel Silva de Oliveira | CPF: 111.222.333-96\n"
    "Tel: (61) 99876-5432 | E-mail: gabriel.oliveira@escola.br\n\n"
    "1. Leia o texto sobre fotossíntese e explique como os cloroplastos produzem glicose "
    "e liberam oxigênio nas folhas."
)

TERMOS_PROIBIDOS = (
    "gabriel",
    "oliveira",
    "111.222.333-96",
    "cecília meireles",
    "meireles",
    "99876-5432",
    "gabriel.oliveira",
    "cloroplastos",
    "glicose",
    "fotossíntese",
    "oxigênio",
)


class _ClienteFalsoPerdaDePalavra:
    provider_name = "ollama"

    def generate(self, **kwargs) -> LLMResponse:
        # Omitindo propositalmente "cloroplastos", "glicose" e "fotossíntese" para forçar conferente e escopo
        texto = '{"texto_adaptado": "Leia o texto e explique o processo nas folhas.", "justificativas": ["teste"]}'
        return LLMResponse(text=texto, provider="ollama", model="llama3:latest", prompt_tokens=10, completion_tokens=10)


class TestAuditoriaLogsZeroPii(unittest.TestCase):
    """Valida todos os critérios da Issue #37 (RNF-01 e RNF-02 em logs de execução)."""

    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient

        cls.client = TestClient(create_app())

    def test_logs_operacionais_registram_apenas_metricas_sem_conteudo_da_prova(self) -> None:
        with capture_operational_logs() as cap:
            r_text = self.client.post("/api/v1/materials/text", json={"text": PROVA_COM_PII})
            self.assertEqual(r_text.status_code, 200)

            r_decomp = self.client.post("/api/v1/materials/decompose", json={"text": PROVA_COM_PII})
            self.assertEqual(r_decomp.status_code, 200)

            r_adapt = self.client.post(
                "/api/v1/agents/adapt",
                json={
                    "text": PROVA_COM_PII,
                    "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
                    "nivel": 2,
                    "provider": "extractive",
                },
            )
            self.assertEqual(r_adapt.status_code, 200)

        eventos = cap.events
        http_events = [e for e in eventos if e.get("event") == "http_request"]
        agent_events = [e for e in eventos if e.get("event") == "agent_execution"]

        self.assertGreaterEqual(len(http_events), 3)
        self.assertTrue(all(e["status_code"] == 200 and e["latency_s"] >= 0.0 for e in http_events))
        self.assertEqual(len(agent_events), 1)
        ag_ev = agent_events[0]
        self.assertEqual(ag_ev["status_code"], 200)
        self.assertIn("total_tokens", ag_ev)
        self.assertIn("latency_s", ag_ev)
        self.assertIn("trcc_scores", ag_ev)
        self.assertEqual(ag_ev["selected_ids"], ["sobrecarga_memoria_trabalho_comandos_multiplos"])

        log_text_lower = cap.text.casefold()
        for termo in TERMOS_PROIBIDOS:
            self.assertNotIn(termo, log_text_lower, f"Termo sensível vazou no log operacional: {termo!r}")

    def test_logs_em_caso_de_erro_ou_excecao_nao_vazam_payload_nem_pii(self) -> None:
        mensagem_toxica = (
            "Falha ao adaptar prova do Aluno: Gabriel Silva de Oliveira CPF 111.222.333-96 "
            "CID F90.0 metilfenidato — enunciado: cloroplastos produzem glicose"
        )
        with capture_operational_logs() as cap:
            r_422 = self.client.post(
                "/api/v1/materials/text",
                json={"text": "Gabriel 111.222.333-96 cloroplastos"},
            )
            self.assertEqual(r_422.status_code, 422)

            with patch(
                "iris.api.routes.agents.MultiAgentOrchestrator.run",
                side_effect=RuntimeError(mensagem_toxica),
            ):
                r_500 = self.client.post(
                    "/api/v1/agents/adapt",
                    json={
                        "text": PROVA_COM_PII,
                        "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
                        "nivel": 2,
                        "provider": "extractive",
                    },
                )
            self.assertEqual(r_500.status_code, 500)
            self.assertNotIn("Gabriel", r_500.text)
            self.assertNotIn("cloroplastos", r_500.text)
            self.assertNotIn("metilfenidato", r_500.text)

            with sentinel_context(PROVA_COM_PII):
                test_logger = logging.getLogger("iris.teste.auditoria")
                try:
                    raise ValueError(mensagem_toxica)
                except ValueError:
                    test_logger.exception("Erro ao processar %s", {"enunciado": PROVA_COM_PII, "observacao": "F90.0"})

        self.assertEqual(_ACTIVE_SENTINEL.get(), frozenset())
        log_lower = cap.text.casefold()
        for proibido in (*TERMOS_PROIBIDOS, "f90.0", "metilfenidato"):
            self.assertNotIn(proibido, log_lower, f"Dado proibido vazou em log de erro: {proibido!r}")

    def test_filtro_zero_pii_bloqueia_chaves_de_payload_e_sentinela_diretamente(self) -> None:
        flt = ZeroPiiLogFilter()
        fmt = ZeroPiiLogFormatter("%(levelname)s:%(message)s")

        with sentinel_context("Fotossíntese nos cloroplastos gera oxigênio e glicose."):
            rec = logging.LogRecord(
                name="iris.teste",
                level=logging.WARNING,
                pathname=__file__,
                lineno=1,
                msg="Falha na requisição: %s — texto livre: metilfenidato CID-10 Fotossíntese glicose",
                args=({"text": "Enunciado confidencial", "enunciado": "Questão secreta", "anotacoes_pedagogicas": "Nota"},),
                exc_info=None,
            )
            self.assertTrue(flt.filter(rec))
            saida = fmt.format(rec)

        self.assertIn("[PAYLOAD_SUPRIMIDO]", saida)
        self.assertIn("[DADO_CLINICO_SUPRIMIDO]", saida)
        self.assertIn("[CONTEUDO_SUPRIMIDO]", saida)
        for proibido in ("Enunciado confidencial", "Questão secreta", "metilfenidato", "CID-10", "Fotossíntese", "glicose"):
            self.assertNotIn(proibido, saida)
        # Garante que a sentinela foi descartada da memória após sair do bloco
        self.assertEqual(_ACTIVE_SENTINEL.get(), frozenset())

    def test_adapter_agent_nao_ecoa_palavras_do_enunciado_ao_logar_reprovacao(self) -> None:
        agente = AdapterAgent(llm_client=_ClienteFalsoPerdaDePalavra(), comandos_por_regra=False)
        req = AdaptationRequest(
            enunciado=PROVA_COM_PII,
            id_caracteristica="impulsividade_leitura_superficial_negacoes",
            nivel=1,
            invariantes=CurriculumInvariants(
                conceitos_obrigatorios=["cloroplastos", "glicose"],
                verbo_comando_bncc="explicar",
                operacao_cognitiva="Explicar fotossíntese.",
            ),
        )
        with capture_operational_logs() as cap:
            with sentinel_context(PROVA_COM_PII):
                res = agente.adapt(req)
        self.assertEqual(res.telemetry.motivo_fallback, "escopo_reprovado")
        for termo in ("cloroplastos", "glicose", "fotossíntese", "gabriel"):
            self.assertNotIn(termo, cap.text.casefold())

    def test_logger_tardio_propagado_ao_root_handler_e_filtrado(self) -> None:
        import io
        import uuid

        buf = io.StringIO()
        root_handler = logging.StreamHandler(buf)
        root_logger = logging.getLogger()
        root_logger.addHandler(root_handler)
        try:
            create_app()
            tardio = logging.getLogger(f"iris.tardio_{uuid.uuid4().hex[:8]}")
            tardio.warning("Aluno: Gabriel Silva CPF 123.456.789-09 toma metilfenidato")
        finally:
            root_logger.removeHandler(root_handler)

        saida = buf.getvalue()
        self.assertIn("[ESTUDANTE]", saida)
        self.assertIn("[CPF]", saida)
        self.assertIn("[DADO_CLINICO_SUPRIMIDO]", saida)
        for proibido in ("Gabriel", "123.456.789-09", "metilfenidato"):
            self.assertNotIn(proibido, saida)

    def test_trace_id_rag_backend_e_ops_summary_zero_pii(self) -> None:
        reset_operational_metrics()
        with capture_operational_logs() as cap:
            r_adapt = self.client.post(
                "/api/v1/agents/adapt",
                json={
                    "text": PROVA_COM_PII,
                    "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
                    "nivel": 2,
                    "provider": "extractive",
                    "metodo_rag": "bm25",
                },
            )
            self.assertEqual(r_adapt.status_code, 200)
            trace_id = r_adapt.headers.get("X-Trace-Id")
            self.assertTrue(trace_id)

        eventos = cap.events
        http_ev = [e for e in eventos if e.get("event") == "http_request" and e.get("path") == "/api/v1/agents/adapt"][-1]
        agent_ev = [e for e in eventos if e.get("event") == "agent_execution"][-1]

        self.assertEqual(http_ev["trace_id"], trace_id)
        self.assertEqual(agent_ev["trace_id"], trace_id)
        self.assertEqual(agent_ev["rag_backend"], "bm25")
        self.assertEqual(agent_ev["rag_metodo_efetivo"], "bm25")
        self.assertIn("rerank_top1_score", agent_ev)

        r_ops = self.client.get("/api/v1/eval/ops-summary")
        self.assertEqual(r_ops.status_code, 200)
        summary = r_ops.json()
        self.assertEqual(summary["total_executions"], 1)
        self.assertEqual(summary["rag_backends"], {"bm25": 1})
        self.assertIn(trace_id, summary["recent_trace_ids"])

        ops_lower = r_ops.text.casefold()
        for termo in TERMOS_PROIBIDOS:
            self.assertNotIn(termo, ops_lower)

    def test_log_operacional_registra_chamada_externa_sem_vazar_payload(self) -> None:
        from iris.agents.orchestrator import MultiAgentOrchestrator

        class _MockAnthropic:
            provider_name = "anthropic"

            def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 900,
                         system_prompt: str | None = None, json_mode: bool = False) -> LLMResponse:
                sys_txt = system_prompt or ""
                if "Agente Extrator Curricular" in sys_txt:
                    txt = '{"conceitos_obrigatorios":["fotossíntese","cloroplastos","glicose"],"termos_tecnicos_intocaveis":["cloroplastos"],"verbo_comando_bncc":"explicar","operacao_cognitiva":"explicar","habilidade_bncc_sugerida":"EF06CI05","alerta_anti_muleta":"não resolver","justificativa_preservacao":"ok"}'
                elif "Agente Estrategista" in sys_txt:
                    txt = '{"intervencoes":[]}'
                elif "Agente Adaptador Pedagógico" in sys_txt:
                    txt = '{"texto_adaptado":"1. [ ] **Leia** o texto sobre fotossíntese.\\n2. [ ] **Explique** como os cloroplastos produzem glicose e oxigênio nas folhas.","justificativas":["Checklist aplicado."]}'
                else:
                    txt = '{"resolveu_questao":false,"evidencia_resolucao":"","modificacoes_intrusivas":[]}'
                return LLMResponse(text=txt, provider="anthropic", model="claude-haiku-5-5", prompt_tokens=20, completion_tokens=15)

        with capture_operational_logs() as cap:
            res = MultiAgentOrchestrator(llm_client=_MockAnthropic()).run(
                {
                    "text": PROVA_COM_PII,
                    "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
                    "nivel": 2,
                }
            )

        self.assertTrue(res.usa_provedor_externo)
        agent_ev = [e for e in cap.events if e.get("event") == "agent_execution"][-1]
        self.assertTrue(agent_ev["external_llm_used"])
        self.assertEqual(agent_ev["providers_by_agent"]["adaptador"], "anthropic")
        log_lower = cap.text.casefold()
        for termo in TERMOS_PROIBIDOS:
            self.assertNotIn(termo, log_lower, f"Termo sensível vazou em chamada externa: {termo!r}")


if __name__ == "__main__":
    unittest.main()
