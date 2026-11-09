"""Testes unitários para a camada híbrida de LLM (#43) e cálculo das 12 métricas do RAG."""
from __future__ import annotations

import os
import unittest

from iris.core.llm_client import (
    ExtractiveFallbackLLMProvider,
    HybridLLMClient,
    get_llm_client,
    strip_thinking_tags,
)
from iris.eval.rag_metrics import (
    avaliar_pipeline_ao_vivo,
    avaliar_pipeline_registrado,
    calcular_average_precision_at_k,
    calcular_kappa_cohen,
    calcular_mrr,
    calcular_recall_at_k,
    calcular_similaridade_semantica,
)


class TestHybridLLMAndRAGMetrics(unittest.TestCase):
    def test_strip_thinking_tags(self) -> None:
        raw = "<think>\nPensando sobre a pergunta...\n</think>\nA estratégia recomendada é o checklist [T1]."
        self.assertEqual(
            strip_thinking_tags(raw),
            "A estratégia recomendada é o checklist [T1].",
        )

    def test_extractive_fallback_provider_generates_cited_sentences(self) -> None:
        prompt = (
            "Regras...\n\nTRECHOS:\n\n"
            "[T1] Diretrizes DUA (pt-BR)\n"
            "Para reduzir a sobrecarga da memória de trabalho, ofereça checklists explícitos e divida enunciados longos em etapas menores.\n\n"
            "PERGUNTA: Como reduzir a sobrecarga da memória de trabalho em enunciados longos?\n\nRESPOSTA:"
        )
        provider = ExtractiveFallbackLLMProvider()
        resp = provider.generate(prompt)
        self.assertIn("[T1]", resp.text)
        self.assertEqual(resp.provider, "extractive")
        self.assertGreater(resp.prompt_tokens, 0)

    def test_hybrid_client_fallback_when_ollama_offline(self) -> None:
        client = get_llm_client(provider="extractive", allow_fallback_to_extractive=True)
        status = client.status()
        self.assertEqual(status["configured_provider"], "extractive")
        self.assertTrue(status["primary_available"])

    def test_retrieval_metrics_formulas(self) -> None:
        ranking = ["C1", "C2", "C3", "C4", "C5"]
        relevantes = {"C1", "C4"}
        self.assertAlmostEqual(calcular_recall_at_k(ranking, relevantes, k=5), 1.0)
        self.assertAlmostEqual(calcular_mrr(ranking, relevantes), 1.0)
        # C1 na pos 1 (P@1 = 1/1 = 1.0) e C4 na pos 4 (P@4 = 2/4 = 0.5) -> média = (1.0 + 0.5) / 2 = 0.75
        self.assertAlmostEqual(calcular_average_precision_at_k(ranking, relevantes, k=5), 0.75)

    def test_cohen_kappa_calculation(self) -> None:
        pares = [
            ("apoiada", "apoiada"),
            ("apoiada", "apoiada"),
            ("parcial", "parcial"),
            ("apoiada", "parcial"),
        ]
        p_o, kappa = calcular_kappa_cohen(pares)
        self.assertAlmostEqual(p_o, 0.75)
        self.assertGreater(kappa, 0.3)

    def test_avaliar_pipeline_registrado_matches_official_report(self) -> None:
        res = avaliar_pipeline_registrado(gerador="haiku")
        ir = res["metricas_relatorio_iris"]
        mk = res["metricas_mercado_ragas"]

        self.assertAlmostEqual(ir["recall_at_5"], 0.42, places=2)
        self.assertAlmostEqual(ir["consultas_atendidas_pct"], 86.8, places=1)
        self.assertAlmostEqual(ir["frases_sustentadas_pct"], 86.1, places=1)
        self.assertEqual(ir["citacoes_invalidas"], 0)

        # Verifica que todas as 7 métricas de mercado estão no intervalo [0, 1]
        for chave, valor in mk.items():
            self.assertGreaterEqual(valor, 0.0, f"{chave} abaixo de 0")
            self.assertLessEqual(valor, 1.0, f"{chave} acima de 1")

    def test_avaliar_pipeline_ao_vivo_with_extractive_fallback(self) -> None:
        old_llm = os.environ.get("RAG_LLM")
        try:
            os.environ["RAG_LLM"] = "extractive"
            res = avaliar_pipeline_ao_vivo(metodo_busca="bm25", limite_consultas=2, usar_fallback_extrativo=True)
            self.assertEqual(res["modo"], "ao_vivo")
            self.assertEqual(res["n_consultas_avaliadas"], 2)
            self.assertEqual(res["resumo_recuperacao"]["citacoes_invalidas"], 0)
            self.assertIn("1_fidelidade", res["notas_0_a_10"])
        finally:
            if old_llm is None:
                os.environ.pop("RAG_LLM", None)
            else:
                os.environ["RAG_LLM"] = old_llm


if __name__ == "__main__":
    unittest.main()

