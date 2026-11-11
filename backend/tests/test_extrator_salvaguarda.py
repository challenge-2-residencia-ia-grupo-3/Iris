"""Extração determinística de salvaguarda do Agente Extrator (História 2.1.2).

Quando a chamada ao LLM falha, o agente monta os invariantes curriculares por regras
léxicas. Esse caminho é o que protege o conteúdo quando o modelo está fora do ar, e
por isso é testado aqui sem modelo: o cliente LLM é um substituto que sempre falha.
"""
from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock

from iris.agents.curriculum_extractor import CurriculumExtractorAgent
from iris.schemas.curriculum import ExtractionRequest


def _agente_sem_llm(provedor: str = "ollama") -> CurriculumExtractorAgent:
    llm = MagicMock()
    llm.provider_name = provedor
    llm.generate.side_effect = RuntimeError("LLM indisponível")
    return CurriculumExtractorAgent(llm_client=llm)


class TestExtracaoDeSalvaguarda(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.agente = _agente_sem_llm()

    def _extrair(self, enunciado: str, trava: list[str] | None = None):
        return self.agente.extract(ExtractionRequest(enunciado=enunciado, trava_manual_docente=trava))

    def test_expressao_entre_aspas_vira_conceito_e_termo_intocavel(self) -> None:
        res = self._extrair("Determine o valor de x na equação '3x + 9 = 27'.")
        self.assertEqual(res.verbo_comando_bncc, "determinar")
        self.assertIn("3x + 9 = 27", res.conceitos_obrigatorios)
        self.assertIn("3x + 9 = 27", res.termos_tecnicos_intocaveis)

    def test_conta_sem_aspas_vira_conceito(self) -> None:
        res = self._extrair("Calcule a soma 12 + 30 e depois anote aqui.")
        self.assertEqual(res.verbo_comando_bncc, "calcular")
        self.assertIn("12 + 30", res.conceitos_obrigatorios)

    def test_trava_do_docente_e_preservada(self) -> None:
        res = self._extrair("Explique como ocorre a fotossíntese nas plantas.", trava=["clorofila", "luz"])
        self.assertEqual(res.conceitos_obrigatorios[:2], ["clorofila", "luz"])
        self.assertEqual(res.verbo_comando_bncc, "explicar")

    def test_palavras_de_ligacao_nao_viram_conceito(self) -> None:
        res = self._extrair("Leia o texto abaixo sobre plantas verdes e observe com calma a figura.")
        for palavra in ("texto", "abaixo", "sobre"):
            self.assertNotIn(palavra, res.conceitos_obrigatorios)

    def test_sem_verbo_reconhecido_usa_identificar(self) -> None:
        res = self._extrair("Leia o texto abaixo sobre plantas verdes e observe com calma a figura.")
        self.assertEqual(res.verbo_comando_bncc, "identificar")

    def test_alerta_anti_muleta_proibe_entregar_a_resposta(self) -> None:
        res = self._extrair("Calcule a soma 12 + 30 e depois anote aqui.")
        self.assertIn("Proibido fornecer a resposta pronta", res.alerta_anti_muleta)
        self.assertIsNone(res.habilidade_bncc_sugerida)

    def test_telemetria_registra_o_uso_da_salvaguarda(self) -> None:
        res = self.agente.extract_with_telemetry(
            ExtractionRequest(enunciado="Explique como ocorre a fotossíntese nas plantas.")
        )
        self.assertTrue(res.telemetry.used_fallback)
        self.assertFalse(res.telemetry.json_valido_direto)
        self.assertEqual(res.telemetry.model, "deterministic-fallback")
        self.assertEqual(res.telemetry.completion_tokens, 0)
        self.assertEqual(res.telemetry.provider, "ollama")

    def test_provedor_sem_modelo_nao_chama_o_llm(self) -> None:
        for provedor in ("extractive", "mock", "offline"):
            with self.subTest(provedor=provedor):
                agente = _agente_sem_llm(provedor)
                res = agente.extract_with_telemetry(
                    ExtractionRequest(enunciado="Explique como ocorre a fotossíntese nas plantas.")
                )
                agente.llm_client.generate.assert_not_called()
                self.assertTrue(res.telemetry.used_fallback)
                self.assertEqual(res.telemetry.model, "deterministic-fallback")
                self.assertEqual(res.telemetry.provider, provedor)


if __name__ == "__main__":
    unittest.main()
