"""Testes de regressão dos pontos levantados na revisão do PR #57 (Agente Extrator Curricular)."""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

from iris.agents.curriculum_extractor import CurriculumExtractorAgent
from iris.core.llm_client import LLMResponse
from iris.schemas.curriculum import CurriculumInvariants, ExtractionRequest, classificar_faixa_etaria


def _llm_que_responde(texto: str) -> MagicMock:
    llm = MagicMock()
    llm.provider_name = "ollama"
    llm.model = "falso"
    llm.generate.return_value = LLMResponse(
        text=texto, provider="ollama", model="falso", prompt_tokens=1, completion_tokens=1, latency_ms=1.0, raw_usage={}
    )
    return llm


class TestFaixaEtaria(unittest.TestCase):
    def test_em_dentro_de_palavra_nao_vira_ensino_medio(self):
        self.assertEqual(classificar_faixa_etaria("7º ano - 2º semestre"), "Fund. II Inicial (11-12 anos)")
        self.assertEqual(classificar_faixa_etaria("6º ano - Sistema Anglo"), "Fund. II Inicial (11-12 anos)")
        self.assertEqual(classificar_faixa_etaria("9º ano (turma em recuperação)"), "Fund. II Final (13-14 anos)")

    def test_ensino_medio_continua_reconhecido(self):
        for ano in ("1º ano EM", "2ª série", "3º ano do Ensino Médio", "EM"):
            self.assertEqual(classificar_faixa_etaria(ano), "Ensino Médio (15-17 anos)", ano)


class TestVerboNoInfinitivo(unittest.TestCase):
    def test_schema_normaliza_imperativo(self):
        for conjugado, infinitivo in (("determine", "determinar"), ("compare", "comparar"), ("descreva", "descrever"), ("Analise", "analisar")):
            inv = CurriculumInvariants(conceitos_obrigatorios=["x"], verbo_comando_bncc=conjugado, operacao_cognitiva="operação qualquer")
            self.assertEqual(inv.verbo_comando_bncc, infinitivo)

    def test_fallback_devolve_infinitivo(self):
        llm = MagicMock()
        llm.provider_name = "extractive"
        res = CurriculumExtractorAgent(llm_client=llm).extract(
            ExtractionRequest(enunciado="Determine o valor de x na equação 2x + 6 = 14.")
        )
        self.assertEqual(res.verbo_comando_bncc, "determinar")


class TestSemConceitoInventado(unittest.TestCase):
    def test_schema_recusa_lista_vazia(self):
        with self.assertRaises(ValueError):
            CurriculumInvariants(conceitos_obrigatorios=[], verbo_comando_bncc="calcular", operacao_cognitiva="aplicar a fórmula")

    def test_llm_sem_conceitos_cai_no_fallback_e_registra(self):
        resposta = json.dumps({"conceitos_obrigatorios": [], "verbo_comando_bncc": "calcular", "operacao_cognitiva": "aplicar a fórmula"})
        res = CurriculumExtractorAgent(llm_client=_llm_que_responde(resposta)).extract_with_telemetry(
            ExtractionRequest(enunciado="Calcule a área de um triângulo de base 4 cm e altura 3 cm.")
        )
        self.assertNotIn("conceito_geral", res.invariants.conceitos_obrigatorios)
        self.assertTrue(res.telemetry.used_fallback)


class TestLogSemConteudo(unittest.TestCase):
    def test_falha_de_validacao_nao_ecoa_conteudo_no_log(self):
        resposta = json.dumps(
            {"conceitos_obrigatorios": ["x"], "verbo_comando_bncc": "calcular", "operacao_cognitiva": {"eco": "Aluno Fulano, laudo TDAH"}}
        )
        agente = CurriculumExtractorAgent(llm_client=_llm_que_responde(resposta))
        with self.assertLogs("iris.agents.curriculum_extractor", level="WARNING") as captura:
            agente.extract(ExtractionRequest(enunciado="Calcule 2 + 2. Aluno Fulano, laudo TDAH"))
        self.assertNotIn("laudo", "\n".join(captura.output))


if __name__ == "__main__":
    unittest.main()
