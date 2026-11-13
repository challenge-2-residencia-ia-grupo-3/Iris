"""Agente Adaptador Pedagógico (História 2.1.3 / Issue #18).

Sem modelo: o cliente LLM é um substituto. Os testes cobrem os quatro caminhos do agente (saída
do modelo aprovada, saída reprovada no isolamento de escopo, falha do modelo e provedor sem
modelo), a telemetria por chamada e por ciclo, e a não-modificação do conteúdo nas 30 questões
do Golden Benchmark.
"""
from __future__ import annotations

import json
import logging
import unittest
from unittest.mock import MagicMock

from iris.agents.adapter_agent import (
    LEMBRETE_DE_CONFERENCIA,
    AdapterAgent,
    CicloComAuditor,
    decompor_em_etapas,
    destacar_comandos,
    resumir_ciclo,
)
from iris.core.llm_client import LLMResponse
from iris.eval.benchmark import carregar_golden_benchmark
from iris.eval.escopo import ID_COMANDOS_MULTIPLOS, localizar_comandos, palavras
from iris.eval.trcc import avaliar_trcc
from iris.schemas.adaptation import LIMITE_LATENCIA_MS, AdaptationRequest
from iris.schemas.curriculum import CurriculumInvariants

ENUNCIADO = "Leia o texto, identifique o sujeito da oração e classifique-o como simples ou composto."
TRAVA = ["sujeito", "simples|composto"]
LISTA = (
    "1. [ ] **Leia** o texto\n"
    "2. [ ] **Identifique** o sujeito da oração\n"
    "3. [ ] **Classifique**-o como simples ou composto."
)


def _pedido(enunciado: str = ENUNCIADO, nivel: int = 2, trava: list[str] | None = None, **campos) -> AdaptationRequest:
    return AdaptationRequest(
        enunciado=enunciado,
        id_caracteristica=campos.pop("id_caracteristica", ID_COMANDOS_MULTIPLOS),
        nivel=nivel,
        invariantes=CurriculumInvariants(
            conceitos_obrigatorios=trava or TRAVA,
            verbo_comando_bncc="identificar",
            operacao_cognitiva="Identificar e classificar o sujeito da oração.",
        ),
        **campos,
    )


def _agente(texto_do_modelo: str | None = None, erro: Exception | None = None, provedor: str = "ollama") -> AdapterAgent:
    llm = MagicMock()
    llm.provider_name = provedor
    if erro is not None:
        llm.generate.side_effect = erro
    else:
        llm.generate.return_value = LLMResponse(
            text=json.dumps({"texto_adaptado": texto_do_modelo, "justificativas": ["Comandos separados."]}),
            provider=provedor,
            model="modelo-de-teste",
            prompt_tokens=420,
            completion_tokens=80,
            raw_usage={"load_ms": 5.0, "tokens_per_sec": 31.0},
        )
    return AdapterAgent(llm_client=llm)


class _SemLog(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)


class TestCaminhosDoAgente(_SemLog):
    def test_saida_do_modelo_aprovada_e_devolvida(self) -> None:
        res = _agente(LISTA).adapt(_pedido())
        self.assertEqual(res.texto_adaptado, LISTA)
        self.assertTrue(res.escopo.aprovado)
        self.assertTrue(res.adaptacao_aplicada)
        self.assertFalse(res.telemetry.used_fallback)
        self.assertEqual(res.justificativas, ["Comandos separados."])

    def test_saida_do_modelo_com_sinonimo_e_trocada_pela_reserva(self) -> None:
        res = _agente(LISTA.replace("oração", "frase")).adapt(_pedido())
        self.assertTrue(res.telemetry.used_fallback)
        self.assertEqual(res.telemetry.motivo_fallback, "escopo_reprovado")
        self.assertEqual(res.texto_adaptado, LISTA)
        self.assertTrue(res.escopo.aprovado)

    def test_saida_do_modelo_com_dica_e_trocada_pela_reserva(self) -> None:
        res = _agente(LISTA + "\nDica: procure quem pratica a ação.").adapt(_pedido())
        self.assertEqual(res.telemetry.motivo_fallback, "escopo_reprovado")
        self.assertNotIn("Dica", res.texto_adaptado)

    def test_falha_do_modelo_leva_a_reserva(self) -> None:
        res = _agente(erro=RuntimeError("LLM indisponível")).adapt(_pedido())
        self.assertEqual(res.telemetry.motivo_fallback, "falha_llm:RuntimeError")
        self.assertEqual(res.texto_adaptado, LISTA)
        self.assertFalse(res.telemetry.json_valido_direto)

    def test_resposta_sem_json_leva_a_reserva(self) -> None:
        agente = _agente(LISTA)
        agente.llm_client.generate.return_value = LLMResponse(text="não sei", provider="ollama", model="m")
        res = agente.adapt(_pedido())
        self.assertTrue(res.telemetry.motivo_fallback.startswith("falha_llm:"))
        self.assertEqual(res.texto_adaptado, LISTA)

    def test_provedor_sem_modelo_nao_chama_o_llm(self) -> None:
        agente = _agente(LISTA, provedor="offline")
        res = agente.adapt(_pedido())
        agente.llm_client.generate.assert_not_called()
        self.assertEqual(res.telemetry.motivo_fallback, "provedor_sem_modelo")
        self.assertEqual(res.telemetry.model, "deterministic-fallback")
        self.assertEqual(res.texto_adaptado, LISTA)

    def test_caracteristica_sem_regra_e_sem_modelo_devolve_o_original(self) -> None:
        res = _agente(provedor="offline").adapt(_pedido(id_caracteristica="dificuldade_decodificacao_leitora"))
        self.assertEqual(res.texto_adaptado, ENUNCIADO)
        self.assertFalse(res.adaptacao_aplicada)
        self.assertFalse(res.escopo.regra_aplicada)

    def test_prompt_leva_diretrizes_do_nivel_trava_e_diretiva(self) -> None:
        agente = _agente(LISTA)
        agente.adapt(_pedido(diretiva_psicopedagogica="Reduzir a carga de memória de trabalho."))
        chamada = agente.llm_client.generate.call_args.kwargs
        prompt = chamada.get("prompt", "") + chamada.get("system_prompt", "")
        self.assertIn("REGRA DE ISOLAMENTO DE ESCOPO", prompt)
        self.assertIn("NÍVEL 2", prompt)
        self.assertIn("AÇÕES PERMITIDAS", prompt)
        self.assertIn("sujeito", prompt)
        self.assertIn("Reduzir a carga de memória de trabalho.", prompt)
        self.assertIn(ENUNCIADO, prompt)


class TestCicloComAuditor(_SemLog):
    """Contrato do ``executar_ciclo`` do Agente Auditor (#19): ``adaptar(feedback, minuta_anterior) -> str``."""

    def _prompts(self, agente: AdapterAgent) -> list[str]:
        return [c.kwargs["prompt"] for c in agente.llm_client.generate.call_args_list]

    def test_primeira_chamada_sem_feedback(self) -> None:
        agente = _agente(LISTA)
        texto = CicloComAuditor(agente, _pedido())(None, None)
        self.assertEqual(texto, LISTA)
        self.assertNotIn("CORREÇÃO PEDIDA PELO AUDITOR", self._prompts(agente)[0])

    def test_feedback_e_minuta_anterior_entram_no_prompt_antes_do_enunciado(self) -> None:
        agente = _agente(LISTA)
        ciclo = CicloComAuditor(agente, _pedido())
        primeira = ciclo(None, None)
        ciclo("Reinclua os conceitos-chave ausentes: sujeito.", primeira)
        prompt = self._prompts(agente)[1]
        self.assertIn("CORREÇÃO PEDIDA PELO AUDITOR", prompt)
        self.assertIn("Reinclua os conceitos-chave ausentes: sujeito.", prompt)
        self.assertIn("MINUTA ANTERIOR REPROVADA", prompt)
        self.assertLess(prompt.index("CORREÇÃO PEDIDA PELO AUDITOR"), prompt.index("ENUNCIADO ORIGINAL"))
        # O enunciado continua sendo o original, não a minuta anterior.
        self.assertTrue(prompt.endswith(ENUNCIADO))

    def test_tentativas_numeradas_e_telemetria_de_cada_uma(self) -> None:
        ciclo = CicloComAuditor(_agente(LISTA), _pedido(nivel=3))
        for feedback in (None, "Remova a dica.", "Remova a dica."):
            ciclo(feedback, None)
        self.assertEqual([t.tentativa for t in ciclo.telemetrias], [1, 2, 3])
        self.assertEqual(resumir_ciclo(ciclo.telemetrias, nivel=3)["chamadas"], 3)

    def test_pedido_original_nao_e_alterado(self) -> None:
        pedido = _pedido()
        CicloComAuditor(_agente(LISTA), pedido)("Remova a dica.", "minuta")
        self.assertIsNone(pedido.feedback_auditor)
        self.assertIsNone(pedido.minuta_anterior)



class TestTelemetria(_SemLog):
    def test_chamada_registra_tokens_latencia_e_limite_do_nivel(self) -> None:
        t = _agente(LISTA).adapt(_pedido(question_id="Q03"), tentativa=2).telemetry
        self.assertEqual((t.prompt_tokens, t.completion_tokens, t.total_tokens), (420, 80, 500))
        self.assertEqual(t.question_id, "Q03")
        self.assertEqual(t.tentativa, 2)
        self.assertEqual(t.nivel, 2)
        self.assertEqual(t.limite_ms, LIMITE_LATENCIA_MS[2])
        self.assertGreaterEqual(t.total_ms, 0.0)
        self.assertTrue(t.dentro_do_limite)
        self.assertTrue(t.escopo_aprovado)
        self.assertEqual(t.model, "modelo-de-teste")
        self.assertTrue(t.timestamp_utc)

    def test_telemetria_nao_guarda_o_texto_da_questao(self) -> None:
        t = _agente(LISTA).adapt(_pedido()).telemetry
        self.assertNotIn("sujeito", t.model_dump_json())
        self.assertEqual(t.tamanho_enunciado_chars, len(ENUNCIADO))

    def test_ciclo_soma_as_chamadas_e_compara_com_o_rnf_07(self) -> None:
        extrator = MagicMock(total_ms=9000.0, prompt_tokens=300, completion_tokens=100, used_fallback=False)
        adaptador = MagicMock(total_ms=8000.0, prompt_tokens=420, completion_tokens=80, used_fallback=True)
        ciclo = resumir_ciclo([extrator, adaptador], nivel=2)
        self.assertEqual(ciclo["chamadas"], 2)
        self.assertEqual(ciclo["chamadas_com_fallback"], 1)
        self.assertEqual(ciclo["total_ms"], 17000.0)
        self.assertEqual(ciclo["total_tokens"], 900)
        self.assertTrue(ciclo["dentro_do_limite"])
        # As mesmas duas chamadas estouram o limite do nível 1 (15 s).
        self.assertFalse(resumir_ciclo([extrator, adaptador], nivel=1)["dentro_do_limite"])


class TestSaidaDeReserva(unittest.TestCase):
    def test_nivel_1_so_acrescenta_negrito(self) -> None:
        saida = destacar_comandos(ENUNCIADO)
        self.assertEqual(saida.replace("**", ""), ENUNCIADO)
        self.assertEqual(saida.count("**"), 6)

    def test_nivel_2_gera_um_item_por_comando(self) -> None:
        self.assertEqual(decompor_em_etapas(ENUNCIADO), LISTA)

    def test_nivel_3_gera_passos_registro_e_lembrete(self) -> None:
        linhas = decompor_em_etapas(ENUNCIADO, com_registro=True).splitlines()
        self.assertEqual([linha for linha in linhas if linha.startswith("**Passo")],
                         ["**Passo 1**", "**Passo 2**", "**Passo 3**"])
        self.assertEqual(sum(linha.startswith("Resposta: ___") for linha in linhas), 2)
        self.assertIn("[ ] **Leia** o texto", linhas)
        self.assertEqual(linhas[-1], LEMBRETE_DE_CONFERENCIA)

    def test_conectivo_sequencial_fica_no_inicio_da_etapa_seguinte(self) -> None:
        saida = decompor_em_etapas("Explique o ciclo da água. Em seguida, cite um exemplo de evaporação.")
        self.assertEqual(
            saida,
            "1. [ ] **Explique** o ciclo da água.\n2. [ ] Em seguida, **cite** um exemplo de evaporação.",
        )

    def test_texto_de_apoio_em_outra_linha_fica_intacto(self) -> None:
        apoio = "Maria e João foram ao mercado."
        saida = decompor_em_etapas(f"Leia a frase e circule o sujeito.\n{apoio}")
        self.assertEqual(saida.splitlines()[-1], apoio)

    def test_enunciado_de_um_comando_so_volta_sem_alteracao_no_nivel_2(self) -> None:
        enunciado = "Calcule a área de um quadrado de lado 5 cm."
        res = _agente(provedor="offline").adapt(_pedido(enunciado, trava=["área"]))
        self.assertEqual(res.texto_adaptado, enunciado)
        self.assertFalse(res.adaptacao_aplicada)


class TestNaoModificacaoNoGoldenBenchmark(unittest.TestCase):
    """Critério de aceite da issue: comandos múltiplos, nível 2, andaime só na separação em etapas."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.questoes = carregar_golden_benchmark()
        cls.agente = _agente(provedor="offline")

    def _adaptar(self, q, nivel: int):
        return self.agente.adapt(_pedido(q.enunciado, nivel=nivel, trava=list(q.trava_curricular), question_id=q.id))

    def test_nivel_2_mantem_todas_as_palavras_na_ordem(self) -> None:
        for q in self.questoes:
            with self.subTest(questao=q.id):
                res = self._adaptar(q, 2)
                original, adaptado = palavras(q.enunciado), palavras(res.texto_adaptado)
                # A única retirada tolerada é o "e" que ligava dois comandos.
                esperado = list(original)
                for _ in range(res.escopo.conectivos_removidos):
                    esperado.remove("e")
                self.assertEqual(sorted(adaptado), sorted(esperado))
                self.assertEqual(res.escopo.palavras_perdidas, [])
                self.assertEqual(res.escopo.palavras_novas, [])
                self.assertFalse(res.escopo.ordem_alterada)

    def test_nivel_2_mantem_a_quantidade_de_comandos(self) -> None:
        for q in self.questoes:
            with self.subTest(questao=q.id):
                res = self._adaptar(q, 2)
                self.assertEqual(len(localizar_comandos(res.texto_adaptado)), len(localizar_comandos(q.enunciado)))

    def test_trava_curricular_nao_cai_em_nenhum_nivel(self) -> None:
        for q in self.questoes:
            trava = list(q.trava_curricular)
            for nivel in (1, 2, 3):
                with self.subTest(questao=q.id, nivel=nivel):
                    res = self._adaptar(q, nivel)
                    self.assertTrue(res.escopo.aprovado, res.escopo.violacoes)
                    self.assertGreaterEqual(
                        avaliar_trcc(trava, res.texto_adaptado).trcc, avaliar_trcc(trava, q.enunciado).trcc
                    )


if __name__ == "__main__":
    unittest.main()
