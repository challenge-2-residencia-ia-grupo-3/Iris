"""Testes do Agente Extrator Curricular e Analytics (História 2.1.2 / Issue #17)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from iris.agents.curriculum_extractor import (
    CurriculumExtractorAgent,
    get_curriculum_extractor,
)
from iris.core.llm_client import LLMResponse
from iris.eval.benchmark import GoldenQuestion
from iris.eval.extractor_analytics import (
    carregar_telemetria,
    executar_benchmark_extrator,
    formatar_relatorio_terminal,
    gerar_analytics,
    registrar_telemetria,
)
from iris.schemas.curriculum import (
    CurriculumInvariants,
    ExtractionRequest,
    ExtractionResult,
    classificar_faixa_etaria,
)


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
        self.assertEqual(res.verbo_comando_bncc, "determinar")
        self.assertTrue(any("3x" in c or "equação" in c or "valor" in c for c in res.conceitos_obrigatorios))
        self.assertIsNotNone(res.alerta_anti_muleta)

    def test_provedor_sem_llm_nao_declara_json_valido(self):
        for provedor in ("mock", "extractive", "offline"):
            with self.subTest(provedor=provedor):
                mock_llm = MagicMock()
                mock_llm.provider_name = provedor

                agent = CurriculumExtractorAgent(llm_client=mock_llm)
                res = agent.extract_with_telemetry(
                    ExtractionRequest(enunciado="Explique como ocorre a fotossíntese nas plantas.")
                )

                mock_llm.generate.assert_not_called()
                self.assertTrue(res.telemetry.used_fallback)
                self.assertFalse(res.telemetry.json_valido_direto)

    def test_fallback_cita_o_verbo_no_infinitivo_nos_textos(self):
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = RuntimeError("Conexão com LLM recusada ou timeout")

        agent = CurriculumExtractorAgent(llm_client=mock_llm)
        res = agent.extract(ExtractionRequest(enunciado="Calcule a soma 12 + 30 e depois anote aqui."))

        self.assertEqual(res.verbo_comando_bncc, "calcular")
        self.assertIn("'calcular'", res.alerta_anti_muleta)
        self.assertIn("'calcular'", res.operacao_cognitiva)
        self.assertNotIn("calcule", res.alerta_anti_muleta)
        self.assertNotIn("calcule", res.operacao_cognitiva)

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

    def test_json_embutido_em_thinking_tags_e_contexto_longo(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            text="""<think>Analisando questão de história com texto-base...</think>
            Aqui está a análise solicitada:
            ```json
            {
              "conceitos_obrigatorios": ["Revolução Industrial", "máquina a vapor"],
              "termos_tecnicos_intocaveis": ["Revolução Industrial", "manufatura"],
              "verbo_comando_bncc": "comparar",
              "operacao_cognitiva": "comparar a produção artesanal com a fabril",
              "habilidade_bncc_sugerida": "EF08HI03",
              "alerta_anti_muleta": "Não listar as diferenças pelo estudante."
            }
            ```""",
            provider="ollama",
            model="llama3:latest",
            prompt_tokens=210,
            completion_tokens=85,
            latency_ms=3400.0,
            raw_usage={
                "load_ms": 1200.0,
                "prompt_eval_ms": 400.0,
                "eval_ms": 1800.0,
                "inference_ms": 2200.0,
                "tokens_per_sec": 47.2,
            },
        )

        agent = CurriculumExtractorAgent(llm_client=mock_llm)
        res = agent.extract_with_telemetry(
            ExtractionRequest(
                enunciado="Compare a manufatura artesanal e o sistema fabril na Revolução Industrial.",
                contexto_apoio="Texto histórico de apoio com mais de cem caracteres descrevendo a Inglaterra no século XVIII.",
                disciplina="História",
                ano_escolar="8º",
            ),
            question_id="Q23",
            tema="Revolução Industrial",
            comando_conjugado=False,
        )

        self.assertIsInstance(res, ExtractionResult)
        self.assertEqual(res.invariants.verbo_comando_bncc, "comparar")
        self.assertFalse(res.telemetry.json_valido_direto)
        self.assertEqual(res.telemetry.faixa_etaria, "Fund. II Final (13-14 anos)")
        self.assertEqual(res.telemetry.load_ms, 1200.0)
        self.assertEqual(res.telemetry.inference_ms, 2200.0)
        self.assertEqual(res.telemetry.tokens_per_sec, 47.2)

    def test_zero_hint_nao_vaza_trava_no_prompt_e_calcula_recall(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            text="""{
              "conceitos_obrigatorios": ["fotossíntese", "glicose"],
              "termos_tecnicos_intocaveis": ["cloroplastos"],
              "verbo_comando_bncc": "explicar",
              "operacao_cognitiva": "explicar a produção de glicose na fotossíntese",
              "habilidade_bncc_sugerida": "EF06CI05",
              "alerta_anti_muleta": "Não dê a equação da fotossíntese."
            }""",
            provider="ollama",
            model="llama3:latest",
            prompt_tokens=150,
            completion_tokens=70,
            raw_usage={"load_ms": 0.0, "inference_ms": 1500.0, "tokens_per_sec": 46.6},
        )
        gq = GoldenQuestion(
            id="Q17",
            disciplina="Ciências",
            ano="6º",
            tema="fotossíntese",
            enunciado="Explique o papel dos cloroplastos e da fotossíntese na produção de glicose.",
            comando_conjugado_esperado=False,
            trava_curricular=("fotossíntese", "cloroplastos", "glicose", "luz solar"),
        )

        agent = CurriculumExtractorAgent(llm_client=mock_llm)
        res = agent.extract_golden_with_telemetry(gq, include_trava_hint=False)

        chamada_kwargs = mock_llm.generate.call_args.kwargs
        self.assertNotIn("luz solar", chamada_kwargs["prompt"])
        self.assertNotIn("TRAVAS DO PROFESSOR", chamada_kwargs["prompt"])
        self.assertAlmostEqual(res.telemetry.trava_recall, 0.75)
        self.assertTrue(res.telemetry.json_valido_direto)

    def test_factory_e_classificador_faixa_etaria(self):
        self.assertEqual(classificar_faixa_etaria("5º"), "Fund. I (9-10 anos)")
        self.assertEqual(classificar_faixa_etaria("6º ano"), "Fund. II Inicial (11-12 anos)")
        self.assertEqual(classificar_faixa_etaria("9º"), "Fund. II Final (13-14 anos)")
        self.assertEqual(classificar_faixa_etaria("2ª série Ensino Médio"), "Ensino Médio (15-17 anos)")
        self.assertIsInstance(get_curriculum_extractor(), CurriculumExtractorAgent)


class TestExtractorAnalytics(unittest.TestCase):
    """Testa registro JSONL, filtros dinâmicos e benchmark em lote."""

    def test_analytics_filtros_por_disciplina_faixa_etaria_e_comando(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            text="""{
              "conceitos_obrigatorios": ["equação", "2x+6=14"],
              "termos_tecnicos_intocaveis": ["incógnita"],
              "verbo_comando_bncc": "calcular",
              "operacao_cognitiva": "resolver a igualdade algébrica",
              "alerta_anti_muleta": "Não antecipar o valor de x."
            }""",
            provider="ollama",
            model="llama3:latest",
            prompt_tokens=120,
            completion_tokens=50,
            raw_usage={"load_ms": 0.0, "inference_ms": 1800.0, "tokens_per_sec": 27.8},
        )
        questoes = [
            GoldenQuestion(
                id="Q10",
                disciplina="Matemática",
                ano="7º",
                tema="álgebra",
                enunciado="Resolva a equação 2x + 6 = 14.",
                comando_conjugado_esperado=False,
                trava_curricular=("equação", "2x+6=14"),
            ),
            GoldenQuestion(
                id="Q20",
                disciplina="Português",
                ano="9º",
                tema="interpretação",
                enunciado="Leia o texto e identifique a ironia presente no último parágrafo.",
                comando_conjugado_esperado=True,
                trava_curricular=("ironia",),
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "telemetry.jsonl"
            agent = CurriculumExtractorAgent(llm_client=mock_llm)
            analytics = executar_benchmark_extrator(
                agent,
                questoes,
                caminho_saida=caminho,
                warmup=False,
                progresso=None,
            )

            self.assertEqual(analytics["resumo_geral"]["total_execucoes"], 2)
            self.assertEqual(len(carregar_telemetria(caminho)), 2)

            registros = carregar_telemetria(caminho)
            mat = gerar_analytics(registros, disciplina="Matemática")
            self.assertEqual(mat["resumo_geral"]["total_execucoes"], 1)
            self.assertAlmostEqual(mat["resumo_geral"]["trava_recall_medio"], 1.0)

            conj = gerar_analytics(registros, faixa_etaria="13-14", comando_conjugado=True)
            self.assertEqual(conj["resumo_geral"]["total_execucoes"], 1)
            self.assertIn("Português", conj["por_disciplina"])

            texto_rel = formatar_relatorio_terminal(analytics)
            self.assertIn("ANALYTICS DO AGENTE EXTRATOR CURRICULAR", texto_rel)
            self.assertIn("POR FAIXA ETÁRIA", texto_rel)

    def test_registrar_telemetria_e_handler_api(self):
        from iris.main import _handle_extractor_analytics

        mock_llm = MagicMock()
        mock_llm.provider_name = "extractive"
        agent = CurriculumExtractorAgent(llm_client=mock_llm)
        res = agent.extract_with_telemetry(
            "Calcule a área de um triângulo de base 4 e altura 6.",
            disciplina="Matemática",
            ano_escolar="6º ano",
            question_id="TEST-01",
        )
        self.assertTrue(res.telemetry.used_fallback)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "single.jsonl"
            registrar_telemetria(res.telemetry, caminho=p)
            regs = carregar_telemetria(p)
            self.assertEqual(len(regs), 1)
            self.assertEqual(regs[0]["faixa_etaria"], "Fund. II Inicial (11-12 anos)")

        api_res = _handle_extractor_analytics(disciplina="DisciplinaInexistenteXYZ")
        self.assertEqual(api_res["resumo_geral"]["total_execucoes"], 0)


if __name__ == "__main__":
    unittest.main()

