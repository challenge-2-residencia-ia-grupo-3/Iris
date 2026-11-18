"""Testes unitários e de integração do avaliador E2E dos 4 agentes (`iris.eval.multiagentes_ciclo`)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
REPO_ROOT = BACKEND_DIR.parent
RAG_PACOTE_DIR = REPO_ROOT / "rag" / "iris-rag" / "pacote"
for p in (str(SRC_DIR), str(RAG_PACOTE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from iris.eval.benchmark import carregar_golden_benchmark
from iris.eval.multiagentes_ciclo import gerar_relatorio, medir


class TestMultiagentesCiclo(unittest.TestCase):
    def test_medir_com_provedor_eco_gera_telemetria_dos_4_agentes(self) -> None:
        questoes = carregar_golden_benchmark()[:2]
        resultado = medir(questoes, provider="eco", niveis=(1, 2))
        resumo = resultado["resumo"]
        registros = resultado["registros"]

        self.assertEqual(resumo["questoes"], 2)
        self.assertEqual(resumo["ciclos"], 4)
        self.assertEqual(resumo["provedor"], "eco")
        self.assertEqual(set(resumo["por_agente"]), {"extrator", "estrategista", "adaptador", "auditor"})
        self.assertEqual(resumo["por_agente"]["estrategista"]["citacoes_validas_pct"], 100.0)
        self.assertEqual(resumo["por_agente"]["adaptador"]["escopo_aprovado_pct"], 100.0)
        self.assertGreaterEqual(resumo["por_agente"]["auditor"]["trcc_ok_pct"], 95.0)
        self.assertEqual(len(registros), 4)
        for r in registros:
            self.assertIsInstance(r["auditor_aprovado"], bool)
            self.assertGreaterEqual(r["trcc_entregue"], 0.95)
            self.assertNotIn("enunciado", r)

    def test_medir_com_provedor_extractive_registra_fallback_deterministico(self) -> None:
        questoes = carregar_golden_benchmark()[:2]
        resultado = medir(questoes, provider="extractive", niveis=(2,))
        registros = resultado["registros"]

        self.assertEqual(len(registros), 2)
        for r in registros:
            self.assertTrue(r["extrator_fallback"])
            self.assertEqual(r["extrator_motivo_fallback"], "provedor_sem_modelo")
            self.assertTrue(r["estrategista_fallback"])
            self.assertEqual(r["estrategista_motivo_fallback"], "provedor_sem_modelo")
            self.assertTrue(r["adaptador_fallback"])
            self.assertEqual(r["adaptador_motivo_fallback"], "provedor_sem_modelo")
            self.assertTrue(r["escopo_aprovado"])

    def test_gerar_relatorio_escreve_json_e_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gerar_relatorio(pasta=tmp, limite_questoes=2, provider="eco", niveis=(1, 2))
            arq_json = Path(tmp) / "multiagentes_ciclo.json"
            arq_md = Path(tmp) / "multiagentes_ciclo.md"
            self.assertTrue(arq_json.exists())
            self.assertTrue(arq_md.exists())

            dados = json.loads(arq_json.read_text(encoding="utf-8"))
            self.assertEqual(dados["resumo"]["ciclos"], 4)
            md = arq_md.read_text(encoding="utf-8")
            self.assertIn("Saúde e Guardrails por Agente", md)
            self.assertIn("Orçamento RNF-07 / RNF-08 por Nível", md)


if __name__ == "__main__":
    unittest.main()
