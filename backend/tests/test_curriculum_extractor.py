"""Testes do Agente Extrator Curricular (História 2.1.2 / Issue #17)."""
import unittest
from unittest.mock import MagicMock

from iris.agents.curriculum_extractor import (
    CurriculumExtractorAgent,
    get_curriculum_extractor,
)
from iris.core.llm_client import LLMResponse
from iris.eval.benchmark import GoldenQuestion
from iris.schemas.curriculum import CurriculumInvariants, ExtractionRequest


class TestCurriculumInvariantsSchema(unittest.TestCase):
    """Testa a validação e sanitização do contrato Pydantic de invariantes."""

    def test_schema_validacao_sucesso(self):
        invariantes = CurriculumInvariants(
            conceitos_obrigatorios=["fotossíntese", "cloroplasto"],
            termos_tecnicos_intocaveis=["glicose", "energia luminosa"],
            verbo_comando_bncc="Explicar",
            operacao_cognitiva="Compreender a conversão energética nos vegetais",
            habilidade_bncc_sugerida="EF06CI05",
            alerta_anti_muleta="Não entregar o processo metabólico resolvido",
        )
        self.assertEqual(len(invariantes.conceitos_obrigatorios), 2)
        self.assertEqual(invariantes.verbo_comando_bncc, "explicar")
        self.assertIn("fotossíntese", invariantes.conceitos_obrigatorios)

    def test_sanitizacao_string_conceitos(self):
        invariantes = CurriculumInvariants(
            conceitos_obrigatorios="equação; incógnita, 2x+6=14",
            verbo_comando_bncc="CALCULAR",
            operacao_cognitiva="Isolar a incógnita para encontrar o valor numérico",
        )
        self.assertEqual(invariantes.verbo_comando_bncc, "calcular")
        self.assertIn("equação", invariantes.conceitos_obrigatorios)
        self.assertIn("incógnita", invariantes.conceitos_obrigatorios)
        self.assertIn("2x+6=14", invariantes.conceitos_obrigatorios)


class TestCurriculumExtractorAgent(unittest.TestCase):
    """Testa a lógica do Agente Extrator com mocks e com extração determinística."""

    def test_extracao_com_mock_llm_json_valido(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            text="""```json
            {
              "conceitos_obrigatorios": ["perímetro", "polígono", "soma dos lados"],
              "termos_tecnicos_intocaveis": ["perímetro", "polígono"],
              "verbo_comando_bncc": "calcular",
              "operacao_cognitiva": "calcular a soma dos comprimentos de todos os lados de um polígono",
              "habilidade_bncc_sugerida": "EF06MA29",
              "alerta_anti_muleta": "Não efetue a soma nem forneça o valor numérico final do perímetro.",
              "justificativa_preservacao": "Preservação do rigor geométrico."
            }
            ```""",
            provider="mock",
            model="mock-model",
            prompt_tokens=100,
            completion_tokens=60,
            latency_ms=10.0,
        )

        agent = CurriculumExtractorAgent(llm_client=mock_llm)
        res = agent.extract(
            ExtractionRequest(
                enunciado="Calcule o perímetro de um retângulo de lados 4 cm e 6 cm.",
                disciplina="Matemática",
                ano_escolar="6º ano",
            )
        )

        self.assertIsInstance(res, CurriculumInvariants)
        self.assertEqual(res.verbo_comando_bncc, "calcular")
        self.assertIn("perímetro", res.conceitos_obrigatorios)
        self.assertIn("polígono", res.termos_tecnicos_intocaveis)
        self.assertIn("Não efetue a soma", res.alerta_anti_muleta)

    def test_preservacao_trava_manual_docente(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            text="""{
              "conceitos_obrigatorios": ["oxigênio", "respiração"],
              "termos_tecnicos_intocaveis": ["alvéolos"],
              "verbo_comando_bncc": "identificar",
              "operacao_cognitiva": "identificar trocas gasosas",
              "habilidade_bncc_sugerida": "EF08CI02",
              "alerta_anti_muleta": "Não resolver",
              "justificativa_preservacao": "Invariante"
            }""",
            provider="mock",
            model="mock-model",
        )

        agent = CurriculumExtractorAgent(llm_client=mock_llm)
        res = agent.extract(
            request="Como ocorrem as trocas gasosas nos pulmões?",
            trava_manual_docente=["hemoglobina", "difusão"],
        )

        self.assertIn("hemoglobina", res.conceitos_obrigatorios)
        self.assertIn("difusão", res.conceitos_obrigatorios)
        self.assertIn("oxigênio", res.conceitos_obrigatorios)

    def test_fallback_deterministico_em_caso_de_erro_llm(self):
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = RuntimeError("Conexão com LLM recusada ou timeout")

        agent = CurriculumExtractorAgent(llm_client=mock_llm)
        res = agent.extract(
            ExtractionRequest(
                enunciado="Determine o valor de x na equação '3x + 9 = 27'.",
                disciplina="Matemática",
            )
        )

        self.assertIsInstance(res, CurriculumInvariants)
        self.assertEqual(res.verbo_comando_bncc, "determine")
        self.assertTrue(any("3x" in c or "equação" in c or "valor" in c for c in res.conceitos_obrigatorios))
        self.assertIsNotNone(res.alerta_anti_muleta)

    def test_extracao_direta_de_golden_question(self):
        gq = GoldenQuestion(
            id="Q01",
            disciplina="Português",
            ano="5º",
            tema="interpretação",
            enunciado="Leia o texto e responda: quem encontrou o cachorro? O menino Pedro encontrou o animal.",
            comando_conjugado_esperado=True,
            trava_curricular=("cachorro", "Pedro", "encontrou"),
        )

        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            text="""{
              "conceitos_obrigatorios": ["Pedro", "cachorro", "encontrou"],
              "termos_tecnicos_intocaveis": ["Pedro"],
              "verbo_comando_bncc": "responder",
              "operacao_cognitiva": "identificar personagem principal e ação causal no texto",
              "habilidade_bncc_sugerida": "EF35LP04",
              "alerta_anti_muleta": "Não dizer quem encontrou o animal",
              "justificativa_preservacao": "Interpretação literal de texto narrativo"
            }""",
            provider="mock",
            model="mock-model",
        )

        agent = CurriculumExtractorAgent(llm_client=mock_llm)
        invariantes = agent.extract_from_golden_question(gq)

        self.assertEqual(invariantes.verbo_comando_bncc, "responder")
        for termo in ("Pedro", "cachorro", "encontrou"):
            self.assertIn(termo, invariantes.conceitos_obrigatorios)


if __name__ == "__main__":
    unittest.main()

