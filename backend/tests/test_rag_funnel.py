"""Testes do Funil Vivo de Causa Raiz do RAG, transparência RAGAS e sincronização de barreiras (#156)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
REPO_ROOT = BACKEND_DIR.parent
RAG_PACOTE_DIR = REPO_ROOT / "rag" / "iris-rag" / "pacote"
for p in (str(SRC_DIR), str(BACKEND_DIR), str(RAG_PACOTE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient

from iris.eval.rag_funnel import executar_funil_rag, formatar_relatorio_texto
from iris.eval.rag_metrics import avaliar_pipeline_registrado
from iris.main import FRONTEND_HTML, create_app
from iris.rag.bridge import sincronizar_barreiras_chunks
from iris.security.operational_logger import reset_operational_metrics


class TestRagFunnelETransparencia(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_funil_4_gavetas_bm25_sem_expor_texto_bruto(self) -> None:
        res = executar_funil_rag(metodo="bm25", incluir_fora_da_base=True)

        self.assertEqual(res["metadados"]["frescor"], "commit_atual")
        self.assertEqual(res["metadados"]["metodo_efetivo"], "bm25")
        gavetas = res["gavetas"]
        self.assertIn("1_corpus_e_filtros", gavetas)
        self.assertIn("2_busca_top50", gavetas)
        self.assertIn("3_reranker_top5", gavetas)
        self.assertIn("4_geracao_e_abstencao", gavetas)

        g1 = gavetas["1_corpus_e_filtros"]
        docs_sem = set(g1["docs_sem_barreira"])
        # Os 5 documentos pedagógicos agora possuem barreiras mapeadas
        for doc_tagueado in (
            "ZERBATO-MENDES-2018-DUA-INCLUSAO-ESCOLAR",
            "NCEO-BRIEF33-ACOMODACAO-MODIFICACAO-2024",
            "DIOGO-2022-ADAPTACAO-CURRICULAR-RBEE",
            "SMALEJACOBSE-2019-DIFERENCIACAO-RS",
            "INEP-CARTILHA-REDACAO-ENEM-2026-DISLEXIA",
        ):
            self.assertNotIn(doc_tagueado, docs_sem)

        # Documentos gerais/neuromitos permanecem sem etiqueta específica
        self.assertIn("DEKKER-2012-NEUROMITOS", docs_sem)
        self.assertIn("SIMOES-2022-NEUROMITOS-BRASIL", docs_sem)
        self.assertEqual(g1["docs_sem_barreira_pedagogicos"], [])
        self.assertTrue(g1["docs_sem_barreira_intencionais"])

        itens_diag = res["diagnostico_prioritario"]
        item_g1 = next(d for d in itens_diag if d["gaveta"] == "1_corpus_e_filtros")
        self.assertEqual(item_g1["severidade"], "info")
        for item in itens_diag:
            self.assertNotIn("`", item["achado"])
            self.assertNotIn("`", item["acao"])

        g2 = gavetas["2_busca_top50"]
        self.assertGreater(g2["n_consultas"], 0)
        self.assertGreater(g2["recall_at_50"], 0.0)
        self.assertTrue(g2["por_tipo"])

        g3 = gavetas["3_reranker_top5"]
        self.assertGreaterEqual(g3["relevantes_no_top50"], g3["relevantes_no_top5"])
        self.assertIsNotNone(g3["scores_top1"]["dentro_da_base"]["mediana"])
        self.assertIsNotNone(g3["scores_top1"]["fora_da_base"]["mediana"])

        # Garante que nenhum texto de chunk restrito vaza no payload do funil
        serializado = json.dumps(res, ensure_ascii=False)
        self.assertNotIn('"texto"', serializado)
        self.assertNotIn('"trecho"', serializado)
        self.assertIn("FUNIL DE CAUSA RAIZ DO RAG", formatar_relatorio_texto(res))

    def test_rag_metrics_informa_frescor_e_metadados_origem(self) -> None:
        reg = avaliar_pipeline_registrado(gerador="haiku")
        self.assertEqual(reg["frescor"], "snapshot_gravado")
        origens = reg["metadados_origem"]
        self.assertEqual(origens["fidelidade"]["rotulo"], "Juiz Snapshot")
        self.assertFalse(origens["fidelidade"]["oficial_ragas"])
        self.assertEqual(origens["precisao_contexto"]["rotulo"], "Fórmula RAGAS")
        self.assertTrue(origens["precisao_contexto"]["oficial_ragas"])
        self.assertIn(origens["similaridade_semantica"]["rotulo"], {"Embeddings (MPNet)", "Heurística léxica"})

        with mock.patch.dict("os.environ", {"IRIS_SEMANTIC_SIM_BACKEND": "lexical"}, clear=False):
            reg_lex = avaliar_pipeline_registrado(gerador="haiku")
            self.assertEqual(reg_lex["metadados_origem"]["similaridade_semantica"]["rotulo"], "Heurística léxica")
            self.assertFalse(reg_lex["metadados_origem"]["similaridade_semantica"]["oficial_ragas"])

    def test_rotas_eval_funnel_e_ops_summary_e_playground(self) -> None:
        reset_operational_metrics()
        r_funnel = self.client.get("/api/v1/eval/rag-funnel?metodo=bm25&refresh=false")
        self.assertEqual(r_funnel.status_code, 200)
        self.assertIn("X-Trace-Id", r_funnel.headers)
        body = r_funnel.json()
        self.assertEqual(body["metadados"]["metodo_efetivo"], "bm25")

        r_invalido = self.client.get("/api/v1/eval/rag-funnel?metodo=inexistente")
        self.assertEqual(r_invalido.status_code, 422)

        r_ops = self.client.get("/api/v1/eval/ops-summary")
        self.assertEqual(r_ops.status_code, 200)
        self.assertEqual(r_ops.json()["total_executions"], 0)

        self.assertIn("rag-funnel-panel", FRONTEND_HTML)
        self.assertIn("carregarFunilRAG", FRONTEND_HTML)
        self.assertIn("carregarResumoOperacional", FRONTEND_HTML)
        self.assertIn("aviso_modo", FRONTEND_HTML)
        self.assertIn("qwen3+rerank50", FRONTEND_HTML)
        self.assertIn("Cache do commit atual", FRONTEND_HTML)

    def test_cache_funil_por_conteudo_miss_hit_e_refresh(self) -> None:
        from iris.eval import rag_funnel

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "rag_funnel_cache.json"
            with mock.patch.object(rag_funnel, "FUNNEL_CACHE_PATH", cache_path):
                miss = executar_funil_rag(metodo="bm25", incluir_fora_da_base=False, usar_cache=True)
                self.assertFalse(miss["metadados"]["origem_cache"])
                self.assertTrue(cache_path.exists())

                hit = executar_funil_rag(metodo="bm25", incluir_fora_da_base=False, usar_cache=True)
                self.assertTrue(hit["metadados"]["origem_cache"])
                self.assertEqual(hit["gavetas"]["2_busca_top50"], miss["gavetas"]["2_busca_top50"])

                refreshed = executar_funil_rag(metodo="bm25", incluir_fora_da_base=False, usar_cache=False)
                self.assertFalse(refreshed["metadados"]["origem_cache"])

    def test_sincronizar_barreiras_preserva_texto_restrito_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            fontes = tmp_dir / "fontes.json"
            chunks = tmp_dir / "chunks.jsonl"
            fontes.write_text(
                json.dumps(
                    {
                        "documentos": [
                            {"id": "DOC-ABERTO", "barreiras": ["memoria_trabalho"]},
                            {"id": "DOC-RESTRITO", "barreiras": ["controle_inibitorio"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            chunks.write_text(
                "\n".join(
                    [
                        json.dumps({"chunk_id": "DOC-ABERTO#0001", "doc_id": "DOC-ABERTO", "barreiras": [], "n_palavras": 5, "texto": "texto aberto"}),
                        json.dumps({"chunk_id": "DOC-RESTRITO#0001", "doc_id": "DOC-RESTRITO", "barreiras": [], "n_palavras": 6, "texto": "texto restrito obtido localmente"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            stats = sincronizar_barreiras_chunks(chunks_path=chunks, fontes_path=fontes)
            self.assertEqual(stats["total_chunks"], 2)
            self.assertEqual(stats["chunks_atualizados"], 2)
            self.assertEqual(stats["chunks_com_barreira"], 2)
            self.assertEqual(stats["chunks_sem_barreira"], 0)

            recarregados = [json.loads(ln) for ln in chunks.read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(recarregados[0]["barreiras"], ["memoria_trabalho"])
            self.assertEqual(recarregados[1]["barreiras"], ["controle_inibitorio"])
            self.assertEqual(recarregados[1]["texto"], "texto restrito obtido localmente")


if __name__ == "__main__":
    unittest.main()
