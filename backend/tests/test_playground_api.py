"""Testes de legibilidade de dados, contratos e rotas do Playground RAG (`http://127.0.0.1:8000`)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
REPO_ROOT = BACKEND_DIR.parent
RAG_PACOTE_DIR = REPO_ROOT / "rag" / "iris-rag" / "pacote"
for p in (str(SRC_DIR), str(BACKEND_DIR), str(RAG_PACOTE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from iris.eval.rag_metrics import obter_consultas_com_textos_e_metricas, obter_opcoes_filtro_gabarito
from iris.main import (
    FRONTEND_HTML,
    _handle_eval_metrics,
    _handle_rag_answer,
    _handle_rag_search,
    _load_playground_html,
    app,
    get_health_status,
)
from iris.rag.bridge import formatar_pagina_trecho, normalizar_trecho_ui


class TestPlaygroundDataContracts(unittest.TestCase):
    """Valida a correção de paginação, metadados ricos e separação de telemetria."""

    def test_formatar_pagina_trecho(self) -> None:
        self.assertIsNone(formatar_pagina_trecho(None, None))
        self.assertEqual(formatar_pagina_trecho(7, 7), "7")
        self.assertEqual(formatar_pagina_trecho(7, 8), "7-8")
        self.assertEqual(formatar_pagina_trecho(12, None), "12")

    def test_normalizar_trecho_ui_identifica_licenca_restrita_e_pagina_inicio(self) -> None:
        meta_paginado = {
            "chunk_id": "DOC#0001",
            "doc_id": "DOC",
            "titulo": "Documento Teste",
            "orgao": "MEC",
            "ano": "2024",
            "url": "https://exemplo.org/doc",
            "idioma": "pt-BR",
            "tipo_evidencia": "diretriz",
            "pagina_inicio": 10,
            "pagina_fim": 11,
            "n_palavras": 120,
            "nao_usar_para": ["numeracao_dua_3_0"],
            "nota_uso": "Usar apenas como exemplo prático.",
            "texto": "Texto científico completo.",
        }
        norm = normalizar_trecho_ui({"chunk_id": "DOC#0001"}, ref="T1", chunk_meta=meta_paginado)
        self.assertEqual(norm["pagina"], "10-11")
        self.assertEqual(norm["orgao"], "MEC")
        self.assertEqual(norm["ano"], "2024")
        self.assertEqual(norm["url"], "https://exemplo.org/doc")
        self.assertEqual(norm["nao_usar_para"], ["numeracao_dua_3_0"])
        self.assertFalse(norm["licenca_restrita"])

        meta_restrito = {
            "chunk_id": "ABDA#0003",
            "n_palavras": 0,
            "texto": "(texto não reproduzido por restrição de licença; consultar o endereço de origem)",
        }
        norm_restr = normalizar_trecho_ui({"chunk_id": "ABDA#0003"}, ref="T2", chunk_meta=meta_restrito)
        self.assertTrue(norm_restr["licenca_restrita"])

    def test_playground_html_tem_abas_e_sem_contagem_hardcoded(self) -> None:
        html = _load_playground_html()
        self.assertEqual(html, FRONTEND_HTML)
        self.assertIn("tab-benchmark", html)
        self.assertIn("tab-catalogo", html)
        self.assertIn("tab-aovivo", html)
        self.assertIn("tab-ferramentas", html)
        self.assertIn("escapeHtml", html)
        self.assertIn("/docs", html)
        self.assertNotIn("1.385 trechos", html)

    def test_health_status_inclui_total_chunks_e_metodos(self) -> None:
        h = get_health_status()
        self.assertEqual(h["status"], "ok")
        self.assertTrue(h["zero_student_database"])
        self.assertGreater(h["total_chunks"], 1000)
        self.assertIsInstance(h["vector_db_online"], bool)
        self.assertIn("bm25", h["available_search_methods"])

    def test_eval_metrics_retorna_paginas_reais_filtros_e_comparativo(self) -> None:
        dados = _handle_eval_metrics(gerador="haiku", limite=7)
        self.assertIn("comparativo_geradores", dados)
        self.assertIn("haiku", dados["comparativo_geradores"])
        self.assertIn("opus", dados["comparativo_geradores"])
        self.assertIn("filtros_gabarito", dados)

        consultas = dados["consultas_com_textos"]
        self.assertEqual(len(consultas), 7)
        tipos_vistos = {c["tipo"] for c in consultas}
        self.assertEqual(len(tipos_vistos), 7)

        q01 = next(c for c in consultas if c["id"] == "Q01")
        t1 = q01["trechos_recuperados"][0]
        self.assertEqual(t1["chunk_id"], "ZERBATO-MENDES-2018-DUA-INCLUSAO-ESCOLAR#0016")
        self.assertEqual(t1["pagina"], "7-8")
        self.assertTrue(t1["url"].startswith("https://"))
        self.assertIn("veredito_detalhado", q01)
        self.assertGreater(len(q01["veredito_detalhado"]["frases"]), 0)

        estrategias = obter_consultas_com_textos_e_metricas(gerador="haiku", limite=0, tipo="estrategia")
        q02 = next(c for c in estrategias if c["id"] == "Q02")
        t1_q02 = q02["trechos_recuperados"][0]
        self.assertTrue(t1_q02["licenca_restrita"])
        self.assertIn("evidencia_de_eficacia", t1_q02["nao_usar_para"])
        self.assertTrue(bool(t1_q02["nota_uso"]))

    def test_filtro_por_tipo_e_limite_zero(self) -> None:
        opcoes = obter_opcoes_filtro_gabarito()
        self.assertEqual(opcoes["total_itens"], 40)
        normas = obter_consultas_com_textos_e_metricas(gerador="haiku", limite=0, tipo="norma")
        self.assertEqual(len(normas), 8)
        self.assertTrue(all(item["tipo"] == "norma" for item in normas))

    def test_rag_search_e_answer_preservam_env_e_telemetria(self) -> None:
        res_search = _handle_rag_search(
            {
                "id_caracteristica": "sobrecarga_memoria_trabalho_comandos_multiplos",
                "nivel": 2,
                "pergunta": "questão com três comandos",
                "metodo": "bm25",
                "k": 3,
            }
        )
        self.assertEqual(res_search["metodo_efetivo"], "bm25")
        self.assertFalse(res_search["fallback_aplicado"])
        self.assertEqual(len(res_search["trechos_recuperados"]), 3)
        self.assertIn("orgao", res_search["trechos_recuperados"][0])

        old_rag_llm = os.environ.get("RAG_LLM")
        try:
            os.environ["RAG_LLM"] = "extractive"
            res_ans = _handle_rag_answer(
                {
                    "pergunta": "Aluno esquece o enunciado no meio da questão de várias etapas",
                    "metodo": "bm25",
                    "k": 3,
                }
            )
            self.assertIn("telemetria_consulta", res_ans)
            tel = res_ans["telemetria_consulta"]
            self.assertEqual(tel["metodo_efetivo"], "bm25")
            self.assertIn("segundos_total", tel)
            self.assertIn("citacoes_invalidas", tel)
            self.assertNotIn("metricas_consulta", res_ans)
            self.assertEqual(os.environ.get("RAG_LLM"), "extractive")
        finally:
            if old_rag_llm is None:
                os.environ.pop("RAG_LLM", None)
            else:
                os.environ["RAG_LLM"] = old_rag_llm

    def test_rag_answer_sincroniza_modelo_e_faz_fallback_se_ollama_falhar(self) -> None:
        import io
        import urllib.error
        from email.message import Message
        from unittest.mock import MagicMock, patch

        fake_primary = MagicMock()
        fake_primary._resolve_model.return_value = "llama3:latest"
        fake_client = MagicMock()
        fake_client._primary = fake_primary
        fake_client.status.return_value = {
            "configured_provider": "ollama",
            "primary_available": True,
        }

        modelos_vistos: list[str | None] = []

        def fake_responder(pergunta: str, metodo: str, k: int = 5):
            modelos_vistos.append(os.environ.get("RAG_LLM_MODELO"))
            if os.environ.get("RAG_LLM") == "ollama":
                raise urllib.error.HTTPError(
                    "http://127.0.0.1:11434/api/generate",
                    404,
                    "Not Found",
                    Message(),
                    io.BytesIO(b"model not found"),
                )
            return {
                "pergunta": pergunta,
                "metodo": "bm25",
                "llm": "extractive:deterministic-bm25-extractive",
                "resposta": "Use checklists explícitos [T1].",
                "trechos_entregues": [
                    {
                        "chunk_id": "ZERBATO-MENDES-2018-DUA-INCLUSAO-ESCOLAR#0016",
                        "doc": "ZERBATO-MENDES-2018-DUA-INCLUSAO-ESCOLAR",
                        "titulo": "DUA",
                        "pagina": "7-8",
                        "secao": "Introdução",
                        "score": 4.2,
                        "idioma": "pt-BR",
                        "parte": "A",
                        "tipo_evidencia": "",
                        "url": "https://exemplo.org",
                        "nao_usar_para": [],
                        "nota_uso": "",
                        "trecho": "Use checklists explícitos para cada etapa.",
                    }
                ],
                "conferencia": {"citacoes_invalidas": [], "frases_sem_citacao": [], "absteve": False, "citou_trecho_com_aviso": []},
                "segundos_busca": 0.01,
                "segundos_total": 0.02,
            }

        old_llm = os.environ.get("RAG_LLM")
        old_modelo = os.environ.get("RAG_LLM_MODELO")
        try:
            with patch("iris.core.llm_client.get_llm_client", return_value=fake_client), patch(
                "iris.rag.bridge.responder_fundamentado", side_effect=fake_responder
            ):
                res = _handle_rag_answer({"pergunta": "como adaptar?", "metodo": "bm25", "k": 1})
            self.assertEqual(modelos_vistos[0], "llama3:latest")
            self.assertTrue(res["telemetria_consulta"]["llm_fallback_aplicado"])
            self.assertIn("404", res["telemetria_consulta"]["llm_erro"])
            self.assertEqual(os.environ.get("RAG_LLM"), old_llm)
            self.assertEqual(os.environ.get("RAG_LLM_MODELO"), old_modelo)
        finally:
            if old_llm is None:
                os.environ.pop("RAG_LLM", None)
            else:
                os.environ["RAG_LLM"] = old_llm
            if old_modelo is None:
                os.environ.pop("RAG_LLM_MODELO", None)
            else:
                os.environ["RAG_LLM_MODELO"] = old_modelo

    def test_fastapi_routes_quando_disponivel(self) -> None:
        if app is None:
            self.skipTest("FastAPI não disponível neste interpretador Python")
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r_root = client.get("/")
        self.assertEqual(r_root.status_code, 200)
        self.assertIn("Bancada de Auditoria RAG", r_root.text)

        r_health = client.get("/api/v1/health")
        self.assertEqual(r_health.status_code, 200)
        self.assertGreater(r_health.json()["total_chunks"], 1000)

        r_metrics = client.get("/api/v1/eval/metrics?gerador=opus&tipo=dua&limite=0")
        self.assertEqual(r_metrics.status_code, 200)
        body = r_metrics.json()
        self.assertEqual(body["metricas_relatorio_iris"]["gerador"], "opus")
        self.assertEqual(len(body["consultas_com_textos"]), 8)


if __name__ == "__main__":
    unittest.main()
