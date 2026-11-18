"""Conferente por regra depois da minuta do Adaptador.

Sem modelo: o cliente LLM é um substituto que devolve minutas fixas, uma por chamada. Os testes cobrem os caminhos
do conferente: a primeira minuta aprovada, a segunda aprovada, as duas reprovadas (entrega o original), o conferente
desligado, e o nível cujas ações mandam tirar texto (o conferente não se aplica).
"""
from __future__ import annotations

import json
import unittest

from iris.agents.adapter_agent import AdapterAgent, _acoes_tiram_texto
from iris.core.llm_client import LLMResponse
from iris.schemas.adaptation import AdaptationRequest
from iris.schemas.curriculum import CurriculumInvariants

NEGACOES = "impulsividade_leitura_superficial_negacoes"
LEIAUTE = "distratibilidade_poluicao_visual_layout"
ENUNCIADO = "Assinale a alternativa INCORRETA sobre a fotossíntese. a) Ocorre nos cloroplastos. b) Libera gás oxigênio."
COMPLETA = "**ATENÇÃO:** marque a opção **INCORRETA**.\n" + ENUNCIADO
SEM_PALAVRA = "Assinale a alternativa INCORRETA. a) Ocorre nos cloroplastos. b) Libera gás oxigênio."   # perdeu "sobre a fotossíntese"


class _Cliente:
    """Substituto do cliente LLM: devolve as minutas na ordem e guarda os prompts recebidos."""

    provider_name = "ollama"

    def __init__(self, *minutas: str) -> None:
        self.minutas = list(minutas)
        self.prompts: list[str] = []

    def generate(self, prompt: str, **kw) -> LLMResponse:
        self.prompts.append(prompt)
        texto = self.minutas.pop(0)
        return LLMResponse(text=json.dumps({"texto_adaptado": texto, "justificativas": ["teste"]}),
                           provider="ollama", model="modelo-de-teste", prompt_tokens=10, completion_tokens=10, raw_usage={})


def _pedido(id_caracteristica: str = NEGACOES, nivel: int = 1, enunciado: str = ENUNCIADO) -> AdaptationRequest:
    return AdaptationRequest(
        enunciado=enunciado, id_caracteristica=id_caracteristica, nivel=nivel,
        # a trava protege "cloroplastos", que as minutas mantêm: a palavra perdida ("fotossíntese") só o conferente vê
        invariantes=CurriculumInvariants(conceitos_obrigatorios=["cloroplastos"], verbo_comando_bncc="identificar",
                                         operacao_cognitiva="Identificar a afirmação incorreta."),
    )


class TestConferentePorRegra(unittest.TestCase):
    def test_minuta_sem_perda_passa_com_uma_chamada(self):
        cliente = _Cliente(COMPLETA)
        r = AdapterAgent(llm_client=cliente).adapt(_pedido())
        self.assertEqual(len(cliente.prompts), 1)
        self.assertEqual(r.texto_adaptado, COMPLETA)
        self.assertIsNone(r.telemetry.motivo_fallback)

    def test_minuta_que_perde_palavra_e_refeita_uma_vez(self):
        cliente = _Cliente(SEM_PALAVRA, COMPLETA)
        r = AdapterAgent(llm_client=cliente).adapt(_pedido())
        self.assertEqual(len(cliente.prompts), 2)
        self.assertIn("A minuta perdeu palavras do enunciado original", cliente.prompts[1])
        self.assertIn("fotossíntese", cliente.prompts[1].split("ENUNCIADO ORIGINAL")[0])
        self.assertIn(SEM_PALAVRA, cliente.prompts[1])                                  # a minuta reprovada vai junto
        self.assertEqual(r.texto_adaptado, COMPLETA)
        self.assertIsNone(r.telemetry.motivo_fallback)

    def test_duas_perdas_entregam_o_original_com_o_motivo(self):
        cliente = _Cliente(SEM_PALAVRA, SEM_PALAVRA)
        r = AdapterAgent(llm_client=cliente).adapt(_pedido())
        self.assertEqual(len(cliente.prompts), 2)
        self.assertEqual(r.texto_adaptado, ENUNCIADO)
        self.assertFalse(r.adaptacao_aplicada)
        self.assertEqual(r.telemetry.motivo_fallback, "conferente_palavra_perdida")

    def test_conferente_desligado_entrega_a_primeira_minuta(self):
        cliente = _Cliente(SEM_PALAVRA)
        r = AdapterAgent(llm_client=cliente, conferente_por_regra=False).adapt(_pedido())
        self.assertEqual(len(cliente.prompts), 1)
        self.assertEqual(r.texto_adaptado, SEM_PALAVRA)

    def test_nivel_que_manda_tirar_texto_nao_e_conferido(self):
        self.assertTrue(_acoes_tiram_texto(_pedido(LEIAUTE, 1)))        # "Remover ornamentos textuais..."
        self.assertTrue(_acoes_tiram_texto(_pedido(LEIAUTE, 3)))        # "Substituir referências cruzadas..."
        self.assertTrue(_acoes_tiram_texto(_pedido("ritmo_processamento_pressao_temporal", 2)))   # "Converter frases..."
        self.assertFalse(_acoes_tiram_texto(_pedido(LEIAUTE, 2)))
        self.assertFalse(_acoes_tiram_texto(_pedido(NEGACOES, 1)))

    def test_lista_de_niveis_existe_no_catalogo(self):
        # se o catálogo mudar de nome ou de nível, a lista não pode apontar para o vazio
        from iris.agents.adapter_agent import NIVEIS_QUE_REESCREVEM
        from iris.schemas.catalog import get_characteristic_by_id
        for cid, nivel in NIVEIS_QUE_REESCREVEM:
            self.assertIn(f"nivel_{nivel}", get_characteristic_by_id(cid).diretrizes_andaime)

    def test_leiaute_nivel_1_entrega_a_minuta_sem_refazer(self):
        cliente = _Cliente(SEM_PALAVRA)
        r = AdapterAgent(llm_client=cliente).adapt(_pedido(LEIAUTE, 1))
        self.assertEqual(len(cliente.prompts), 1)
        self.assertEqual(r.texto_adaptado, SEM_PALAVRA)


if __name__ == "__main__":
    unittest.main()
