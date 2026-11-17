"""Prompt do gerador do RAG: regras de pedir esclarecimento e de recusa mais firme, e a conferência mecânica."""

import os
import unittest
from unittest import mock

from iris.rag.bridge import carregar_modulos_rag

_, _, gerar = carregar_modulos_rag()

TRECHO = {"titulo": "Diretrizes DUA", "pagina": 3, "idioma": "pt", "tipo_evidencia": "orientacao",
          "trecho": "Dividir o enunciado em etapas reduz a carga da memória de trabalho.", "nao_usar_para": None}


def _ambiente(**extra):
    limpo = {k: v for k, v in os.environ.items() if k not in ("RAG_LLM", "RAG_PROMPT_ESCLARECIMENTO")}
    return mock.patch.dict(os.environ, {**limpo, **extra}, clear=True)


class TestRegrasDeEsclarecimento(unittest.TestCase):
    def test_por_padrao_so_com_o_gerador_da_anthropic(self):
        with _ambiente(RAG_LLM="anthropic"):
            self.assertIn("perguntas curtas pedindo o que falta", gerar.montar_prompt("Como adaptar?", [TRECHO]))
        with _ambiente(RAG_LLM="ollama"):
            self.assertNotIn("perguntas curtas pedindo o que falta", gerar.montar_prompt("Como adaptar?", [TRECHO]))

    def test_pode_ser_ligado_ou_desligado_a_mao(self):
        with _ambiente(RAG_LLM="ollama", RAG_PROMPT_ESCLARECIMENTO="on"):
            self.assertTrue(gerar.usar_regras_de_esclarecimento())
        with _ambiente(RAG_LLM="anthropic", RAG_PROMPT_ESCLARECIMENTO="off"):
            self.assertFalse(gerar.usar_regras_de_esclarecimento())

    def test_as_regras_do_grupo_continuam_inteiras(self):
        with _ambiente(RAG_LLM="anthropic"):
            p = gerar.montar_prompt("Como adaptar?", [TRECHO])
        self.assertTrue(p.startswith(gerar.INSTRUCOES))           # as regras 1 a 8 não mudam; as novas vêm depois
        self.assertIn(gerar.FRASE_SEM_RESPOSTA, gerar.REGRAS_ESCLARECIMENTO)
        self.assertIn("PERGUNTA: Como adaptar?", p)


class TestConferenciaComEsclarecimento(unittest.TestCase):
    def test_pergunta_de_volta_nao_e_cobrada_de_citacao(self):
        r = gerar.conferir("Qual é a barreira ou a dificuldade do aluno? E qual é a atividade que você quer adaptar?", [TRECHO])
        self.assertTrue(r["pediu_esclarecimento"])
        self.assertFalse(r["absteve"])
        self.assertEqual(r["frases_sem_citacao"], [])

    def test_resposta_com_citacao_nao_e_pedido_de_esclarecimento(self):
        r = gerar.conferir("Dividir o enunciado em etapas ajuda, não é [T1]? Use também pausas curtas na atividade.", [TRECHO])
        self.assertFalse(r["pediu_esclarecimento"])
        self.assertEqual(len(r["frases_sem_citacao"]), 1)          # a frase sem [Tn] continua sendo acusada

    def test_recusa_nao_e_pedido_de_esclarecimento(self):
        r = gerar.conferir(gerar.FRASE_SEM_RESPOSTA, [TRECHO])
        self.assertTrue(r["absteve"])
        self.assertFalse(r["pediu_esclarecimento"])

    def test_afirmacao_sem_citacao_e_sem_pergunta_continua_acusada(self):
        r = gerar.conferir("A segmentação do enunciado sempre resolve o problema do aluno.", [TRECHO])
        self.assertFalse(r["pediu_esclarecimento"])
        self.assertEqual(len(r["frases_sem_citacao"]), 1)


if __name__ == "__main__":
    unittest.main()
