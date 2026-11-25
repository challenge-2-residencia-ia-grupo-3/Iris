"""Recado ao docente fora da questão.

O catálogo lista, no nível 2 de "pressão de tempo", a ação "sinalizar recomendação pedagógica ao docente". A questão
adaptada é o que o aluno lê e o que a exportação imprime; a recomendação vai num campo próprio, com texto fixo do nível
(o modelo não escreve para o docente). Sem modelo: o cliente LLM é
um substituto que devolve respostas fixas.
"""
from __future__ import annotations

import json
import re
import unittest

from iris.agents.adapter_agent import (
    RECOMENDACAO_AO_DOCENTE,
    SYSTEM_PROMPT_ADAPTADOR,
    AdapterAgent,
    recomendacao_ao_docente,
    separar_recado_ao_docente,
)
from iris.schemas.catalog import load_official_tdah_catalog
from iris.core.llm_client import LLMResponse
from iris.schemas.adaptation import AdaptationRequest
from iris.schemas.curriculum import CurriculumInvariants

RITMO = "ritmo_processamento_pressao_temporal"
ENUNCIADO = ("Para despertar a reflexão do leitor, essa campanha faz uma referência irônica a uma expressão do mundo do "
             "trabalho. Essa referência está presente em\nA) Denuncie.\nB) Funcionário do mês.")
QUESTAO = ("Essa campanha faz uma referência irônica a uma expressão do mundo do trabalho, para despertar a reflexão do "
           "leitor.\n\n**Essa referência está presente em**\n\nA) Denuncie.\nB) Funcionário do mês.")
RECADO = "Ofereça tempo flexível para a leitura e organize a aplicação em etapas."      # o que um modelo escreveria
FIXO = RECOMENDACAO_AO_DOCENTE[(RITMO, 2)]                                               # o que o docente recebe
NEGACOES = "impulsividade_leitura_superficial_negacoes"


class _Cliente:
    """Substitui o cliente LLM: devolve os objetos JSON na ordem e guarda os prompts."""

    provider_name = "ollama"

    def __init__(self, *respostas: dict) -> None:
        self.respostas = list(respostas)
        self.prompts: list[str] = []

    def generate(self, prompt: str, **kw) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(text=json.dumps(self.respostas.pop(0)), provider="ollama", model="modelo-de-teste",
                           prompt_tokens=10, completion_tokens=10, raw_usage={})


def _pedido() -> AdaptationRequest:
    return AdaptationRequest(
        enunciado=ENUNCIADO, id_caracteristica=RITMO, nivel=2,
        invariantes=CurriculumInvariants(conceitos_obrigatorios=["referência irônica"], verbo_comando_bncc="identificar",
                                         operacao_cognitiva="Identificar a expressão a que a campanha se refere."),
    )


class TestSepararRecado(unittest.TestCase):
    def test_tira_a_linha_e_devolve_o_recado_sem_o_rotulo(self):
        texto, recado, sobrou = separar_recado_ao_docente(ENUNCIADO, QUESTAO + "\n\nRecomendação pedagógica ao docente: " + RECADO)
        self.assertEqual((texto, recado, sobrou), (QUESTAO, RECADO, False))

    def test_aceita_as_variacoes_de_rotulo(self):
        for linha in ("Recomendação ao docente: " + RECADO, "Orientação ao docente: " + RECADO,
                      "**Nota para o professor:** " + RECADO, "Observação à professora: " + RECADO,
                      "[Recomendação ao docente: " + RECADO + "]", "Recomendações aos professores: " + RECADO,
                      "### Orientação para o(a) professor(a): " + RECADO, "Recomendação pedagógica: " + RECADO):
            with self.subTest(linha=linha[:40]):
                texto, recado, sobrou = separar_recado_ao_docente(ENUNCIADO, f"{QUESTAO}\n\n{linha}")
                self.assertEqual((texto, recado, sobrou), (QUESTAO, RECADO, False))

    def test_questao_sem_recado_fica_igual(self):
        self.assertEqual(separar_recado_ao_docente(ENUNCIADO, QUESTAO), (QUESTAO, None, False))

    def test_o_que_vem_depois_do_recado_fica_na_questao(self):
        # recado seguido de quebra simples: só a linha do recado sai; comando e alternativas ficam
        original = "Leia o texto da campanha. Explique a ironia.\nA) um\nB) dois\nC) tres"
        minuta = "Leia o texto da campanha.\n\nRecomendação ao docente: Ofereça tempo flexível.\n**Explique a ironia.**\nA) um\nB) dois\nC) tres"
        texto, recado, sobrou = separar_recado_ao_docente(original, minuta)
        self.assertEqual(texto, "Leia o texto da campanha.\n\n**Explique a ironia.**\nA) um\nB) dois\nC) tres")
        self.assertEqual((recado, sobrou), ("Ofereça tempo flexível.", False))

    def test_recado_na_ultima_linha_sem_linha_em_branco(self):
        texto, recado, _ = separar_recado_ao_docente("Calcule.\nA) 1\nB) 2", "**Calcule.**\nA) 1\nB) 2\nRecomendação ao docente: " + RECADO)
        self.assertEqual((texto, recado), ("**Calcule.**\nA) 1\nB) 2", RECADO))

    def test_questao_que_fala_de_professor_fica_intacta(self):
        original = "A aluna entregou a redação ao professor. O que ela deve fazer em seguida?"
        self.assertEqual(separar_recado_ao_docente(original, "**" + original + "**"), ("**" + original + "**", None, False))

    def test_texto_base_que_e_um_aviso_a_professora_fica_mesmo_com_negrito(self):
        original = "Aviso à professora: a turma chegará tarde.\n\nQual é a finalidade do texto?"
        adaptada = "**Aviso à professora:** a turma chegará tarde.\n\n**Qual é a finalidade do texto?**"
        self.assertEqual(separar_recado_ao_docente(original, adaptada), (adaptada, None, False))

    def test_fala_de_personagem_professor_no_original_fica(self):
        original = "Professor: bom dia, turma.\nAluno: bom dia.\nQuem fala primeiro?"
        adaptada = "**Professor:** bom dia, turma.\nAluno: bom dia.\n\n**Quem fala primeiro?**"
        self.assertEqual(separar_recado_ao_docente(original, adaptada), (adaptada, None, False))

    def test_rotulo_sozinho_na_linha_nao_e_separado_e_avisa(self):
        minuta = QUESTAO + "\n\n**Recomendação ao docente:**\n\n" + RECADO
        self.assertEqual(separar_recado_ao_docente(ENUNCIADO, minuta), (minuta, None, True))

    def test_vocativo_ao_professor_nao_e_separado_e_avisa(self):
        minuta = QUESTAO + "\n\nProfessor, ofereça tempo flexível ao estudante."
        self.assertEqual(separar_recado_ao_docente(ENUNCIADO, minuta), (minuta, None, True))

    def test_separacao_que_levaria_alternativa_e_desfeita(self):
        # alternativa escrita na mesma linha do recado: tirar a linha levaria a alternativa; a minuta volta inteira
        original = "Calcule.\nA) 1\nB) 2"
        minuta = "**Calcule.**\nA) 1\nRecomendação ao docente: ofereça tempo. B) 2"
        self.assertEqual(separar_recado_ao_docente(original, minuta), (minuta, None, True))

    def test_comando_na_mesma_linha_do_recado_nao_sai(self):
        original = "Leia o texto. Explique a ironia."
        minuta = "Leia o texto.\n\nRecomendação ao docente: Ofereça tempo. Explique a ironia."
        self.assertEqual(separar_recado_ao_docente(original, minuta), (minuta, None, True))

    def test_alternativa_em_texto_na_mesma_linha_do_recado_nao_sai(self):
        original = "Qual é a capital?\nA) um\nB) dois"
        minuta = "**Qual é a capital?**\nA) um\nRecomendação ao docente: Ofereça tempo. B) dois"
        self.assertEqual(separar_recado_ao_docente(original, minuta), (minuta, None, True))

    def test_aviso_do_original_reescrito_em_ordem_direta_fica(self):
        original = "Aviso à professora: a turma chegará tarde por causa da chuva.\n\nQual é a finalidade do texto?"
        adaptada = "**Aviso à professora:** em razão da chuva, a turma chegará tarde.\n\n**Qual é a finalidade do texto?**"
        self.assertEqual(separar_recado_ao_docente(original, adaptada), (adaptada, None, False))

    def test_fala_de_personagem_reescrita_fica(self):
        original = "Professora: Porque são seres vivos, as plantas precisam de água.\nQuem fala?"
        adaptada = "Professora: As plantas precisam de água porque são seres vivos.\n\n**Quem fala?**"
        self.assertEqual(separar_recado_ao_docente(original, adaptada), (adaptada, None, False))

    def test_enumeracao_que_comeca_por_professores_nao_e_recado(self):
        original = "Participaram da reunião professores, alunos e pais. Quem participou?"
        adaptada = "Professores, alunos e pais participaram da reunião.\n\n**Quem participou?**"
        self.assertEqual(separar_recado_ao_docente(original, adaptada), (adaptada, None, False))

    def test_recado_entre_parenteses_sai_sem_o_parentese(self):
        texto, recado, sobrou = separar_recado_ao_docente(ENUNCIADO, QUESTAO + "\n\n(Recomendação ao docente: " + RECADO + ")")
        self.assertEqual((texto, recado, sobrou), (QUESTAO, RECADO, False))

    def test_separacao_que_levaria_numero_do_original_e_desfeita(self):
        original = "A caixa tem 12 lápis. Quantos faltam para 20?"
        minuta = "A caixa tem lápis. **Quantos faltam para 20?**\n\nRecomendação ao docente: lembre que a caixa tem 12 lápis."
        self.assertEqual(separar_recado_ao_docente(original, minuta), (minuta, None, True))


class TestTextoFixoDoNivel(unittest.TestCase):
    def test_todo_nivel_com_acao_ao_docente_tem_texto(self):
        # se o catálogo ganhar outra ação dirigida ao docente, este teste acusa o nível que ficou sem texto
        com_acao = set()
        for c in load_official_tdah_catalog().caracteristicas:
            for chave, diretriz in c.diretrizes_andaime.items():
                if any(re.search(r"(?i)\b(ao|à|aos|para o|para a)\s+(docente|professor)", a) for a in diretriz.acoes_permitidas):
                    com_acao.add((c.id_caracteristica, int(chave[-1])))
        self.assertTrue(com_acao)
        self.assertEqual(com_acao - set(RECOMENDACAO_AO_DOCENTE), set())

    def test_texto_so_onde_o_catalogo_tem_a_acao(self):
        self.assertEqual(recomendacao_ao_docente(RITMO, 2), FIXO)
        self.assertIsNone(recomendacao_ao_docente(RITMO, 1))
        self.assertIsNone(recomendacao_ao_docente(NEGACOES, 2))

    def test_os_textos_nao_comentam_resposta_nem_rotulam_o_aluno(self):
        for texto in RECOMENDACAO_AO_DOCENTE.values():
            self.assertNotRegex(texto.lower(), r"resposta|alternativa correta|gabarito|tdah|transtorno|d[ée]ficit")


class TestAdaptadorComRecado(unittest.TestCase):
    def test_o_pedido_ao_modelo_proibe_recado_na_questao_e_nao_pede_o_campo(self):
        self.assertIn("Nada dirigido ao docente entra em texto_adaptado", SYSTEM_PROMPT_ADAPTADOR)
        self.assertNotIn("recomendacao_docente", SYSTEM_PROMPT_ADAPTADOR)

    def test_o_docente_recebe_o_texto_fixo_e_a_questao_fica_limpa(self):
        cliente = _Cliente({"texto_adaptado": QUESTAO, "justificativas": ["ordem direta"]})
        r = AdapterAgent(llm_client=cliente).adapt(_pedido())
        self.assertEqual(r.texto_adaptado, QUESTAO)
        self.assertEqual(r.recomendacao_docente, FIXO)
        self.assertIsNone(r.telemetry.motivo_fallback)

    def test_o_que_o_modelo_escrever_para_o_docente_nao_chega_a_ninguem(self):
        # nem o campo que o modelo inventar, nem a linha que ele puser na questão: vale o texto fixo
        vazamento = "Observe que a resposta certa é a alternativa B."
        cliente = _Cliente({"texto_adaptado": QUESTAO + "\n\nRecomendação ao docente: " + vazamento,
                            "justificativas": [], "recomendacao_docente": vazamento})
        r = AdapterAgent(llm_client=cliente).adapt(_pedido())
        self.assertEqual(len(cliente.prompts), 1)                       # tirar a linha não custa outra chamada ao modelo
        self.assertEqual(r.texto_adaptado, QUESTAO)
        self.assertEqual(r.recomendacao_docente, FIXO)
        self.assertNotIn("alternativa B", r.recomendacao_docente)

    def test_recado_que_nao_da_para_separar_faz_o_modelo_refazer_uma_vez(self):
        ruim = {"texto_adaptado": QUESTAO + "\n\n**Recomendação ao docente:**\n\n" + RECADO, "justificativas": []}
        cliente = _Cliente(ruim, {"texto_adaptado": QUESTAO, "justificativas": ["ordem direta"]})
        r = AdapterAgent(llm_client=cliente).adapt(_pedido())
        self.assertEqual(len(cliente.prompts), 2)
        self.assertIn("texto dirigido ao docente dentro da questão", cliente.prompts[1])
        self.assertEqual((r.texto_adaptado, r.recomendacao_docente), (QUESTAO, FIXO))
        self.assertIsNone(r.telemetry.motivo_fallback)

    def test_recado_que_nao_da_para_separar_duas_vezes_entrega_o_original(self):
        ruim = {"texto_adaptado": QUESTAO + "\n\nProfessor, ofereça tempo flexível ao estudante.", "justificativas": []}
        cliente = _Cliente(ruim, dict(ruim))
        r = AdapterAgent(llm_client=cliente).adapt(_pedido())
        self.assertEqual(len(cliente.prompts), 2)
        self.assertEqual(r.texto_adaptado, ENUNCIADO)
        self.assertFalse(r.adaptacao_aplicada)
        self.assertEqual(r.telemetry.motivo_fallback, "recado_ao_docente_na_questao")
        self.assertEqual(r.recomendacao_docente, FIXO)      # a orientação de tempo vale com o original mantido

    def test_nivel_sem_acao_ao_docente_nao_tem_recomendacao(self):
        pedido = _pedido().model_copy(update={"id_caracteristica": NEGACOES})
        cliente = _Cliente({"texto_adaptado": "**ATENÇÃO:** leia com cuidado.\n" + ENUNCIADO, "justificativas": [], "recomendacao_docente": RECADO})
        self.assertIsNone(AdapterAgent(llm_client=cliente).adapt(pedido).recomendacao_docente)


class _ModeloDosQuatroAgentes:
    """Substitui o modelo nos quatro agentes do orquestrador; o Adaptador devolve o que o teste escolher."""

    provider_name = "ollama"

    def __init__(self, resposta_do_adaptador: dict) -> None:
        self.resposta_do_adaptador = resposta_do_adaptador

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 900,
                 system_prompt: str | None = None, json_mode: bool = False) -> LLMResponse:
        sistema = system_prompt or ""
        if "Agente Extrator Curricular" in sistema:
            dados = {"conceitos_obrigatorios": ["equação", "2x + 6 = 14"], "termos_tecnicos_intocaveis": ["2x + 6 = 14"],
                     "verbo_comando_bncc": "resolver", "operacao_cognitiva": "determinar o valor da incógnita",
                     "habilidade_bncc_sugerida": "EF07MA18", "alerta_anti_muleta": "", "justificativa_preservacao": "ok"}
        elif "Agente Estrategista" in sistema:
            dados = {"intervencoes": [{"id_caracteristica": RITMO, "texto": "Ordem direta no comando [T1]"}]}
        elif "Agente Adaptador Pedagógico" in sistema:
            dados = self.resposta_do_adaptador
        else:
            dados = {"resolveu_questao": False, "evidencia_resolucao": "", "modificacoes_intrusivas": []}
        return LLMResponse(text=json.dumps(dados), provider="ollama", model="modelo-de-teste", prompt_tokens=10, completion_tokens=10)


class TestCaminhoAteOProfessor(unittest.TestCase):
    """O campo tem que chegar ao rastro da Etapa 4 e aos dados da Etapa 5, e a questão tem que chegar limpa."""

    ORIGINAL = "Resolva a equação 2x + 6 = 14 e verifique o resultado."
    ADAPTADA = "**Resolva** a equação 2x + 6 = 14 e **verifique** o resultado."

    def _rodar(self, resposta_do_adaptador: dict):
        from iris.agents.orchestrator import MultiAgentMaterialRequest, MultiAgentOrchestrator
        return MultiAgentOrchestrator(llm_client=_ModeloDosQuatroAgentes(resposta_do_adaptador)).run(
            MultiAgentMaterialRequest(text=self.ORIGINAL, selected_ids=[RITMO], nivel=2)
        )

    def test_o_texto_fixo_chega_ao_rastro_e_a_etapa_5(self):
        res = self._rodar({"texto_adaptado": self.ADAPTADA, "justificativas": ["destaque"]})
        questao = res.questoes_trace[0]
        self.assertEqual(questao.adaptado, self.ADAPTADA)
        self.assertEqual(questao.recomendacao_docente, FIXO)
        self.assertEqual(res.etapa5_entrada["questoes"][0]["recomendacao_docente"], FIXO)
        self.assertNotIn("docente", res.etapa5_entrada["questoes"][0]["adaptado"])

    def test_recado_escrito_na_questao_nao_chega_ao_aluno_nem_ao_auditor(self):
        res = self._rodar({"texto_adaptado": self.ADAPTADA + "\n\nRecomendação ao docente: " + RECADO, "justificativas": ["destaque"]})
        questao = res.questoes_trace[0]
        self.assertEqual(questao.adaptado, self.ADAPTADA)
        self.assertEqual(questao.recomendacao_docente, FIXO)
        self.assertTrue(all("docente" not in t.texto_minuta for t in questao.tentativas))    # o Auditor julgou o texto limpo

    def test_com_o_original_mantido_a_orientacao_de_tempo_continua(self):
        res = self._rodar({"texto_adaptado": self.ORIGINAL, "justificativas": []})
        self.assertFalse(res.questoes_trace[0].adaptacao_aplicada)
        self.assertEqual(res.questoes_trace[0].recomendacao_docente, FIXO)
        self.assertEqual(res.etapa5_entrada["questoes"][0]["recomendacao_docente"], FIXO)


if __name__ == "__main__":
    unittest.main()
