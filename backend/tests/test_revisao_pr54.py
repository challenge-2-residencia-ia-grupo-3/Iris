"""Casos de regressão levantados na revisão do PR 54 (decomposição estrutural)."""
from __future__ import annotations

import unittest

from iris.api.routes.materials import decompose_material_service
from iris.parsers.structural_decomposer import decompose_material
from iris.schemas.materials import MaterialValidationError


class TestRevisaoDecomposicao(unittest.TestCase):
    def test_linha_iniciada_por_texto_nao_quebra_a_questao(self) -> None:
        res = decompose_material(
            "1. De acordo com o\ntexto acima, qual é a ideia principal?\n"
            "a) A seca\nb) A chuva\nc) O vento\n\n2. Explique com suas palavras.\n"
        )
        self.assertEqual(len(res.context_blocks), 0)
        self.assertIn("ideia principal", res.questions[0].statement)
        self.assertEqual([o.letter for o in res.questions[0].options], ["A", "B", "C"])

    def test_titulo_texto_com_letra_continua_sendo_texto_de_apoio(self) -> None:
        res = decompose_material("Texto A\nA água ferve a 100 graus.\n\n1. A que temperatura a água ferve?\n")
        self.assertEqual(len(res.context_blocks), 1)
        self.assertEqual(res.context_blocks[0].title, "Texto A")

    def test_enunciado_com_lacuna_permanece_no_enunciado(self) -> None:
        res = decompose_material("1. O Brasil foi descoberto em ____ por ____.\n\n2. Explique.\nResposta: ______\n")
        self.assertIn("descoberto em ____", res.questions[0].statement)
        self.assertIsNone(res.questions[0].answer_space)
        self.assertIn("Resposta", res.questions[1].answer_space or "")

    def test_texto_depois_das_alternativas_nao_entra_na_ultima_alternativa(self) -> None:
        res = decompose_material(
            "1. Quanto é 2 + 2?\na) 3\nb) 4\n\nObserve a tirinha abaixo antes de continuar.\n\n2. O que o personagem sente?\n"
        )
        self.assertEqual(res.questions[0].options[1].text, "4")
        self.assertIn("Observe a tirinha abaixo antes de continuar.", res.unclassified_blocks)

    def test_alternativa_longa_em_duas_linhas_continua_unida(self) -> None:
        res = decompose_material("1. Assinale.\na) Primeira parte\nsegunda parte\nb) Outra\n")
        self.assertEqual(res.questions[0].options[0].text, "Primeira parte segunda parte")

    def test_texto_de_apoio_preserva_estrofes(self) -> None:
        res = decompose_material(
            "Texto 1\nNo meio do caminho tinha uma pedra\ntinha uma pedra no meio do caminho\n\n"
            "Nunca me esquecerei desse acontecimento\nna vida de minhas retinas tão fatigadas\n\n1. Qual é o tema do poema?\n"
        )
        self.assertEqual(
            res.context_blocks[0].text,
            "No meio do caminho tinha uma pedra\ntinha uma pedra no meio do caminho\n\n"
            "Nunca me esquecerei desse acontecimento\nna vida de minhas retinas tão fatigadas",
        )

    def test_numeracao_repetida_vincula_pela_posicao(self) -> None:
        res = decompose_material(
            "Texto para as questões 1 e 2\nA água ferve a 100 graus.\n\n1. A que temperatura a água ferve?\n2. Por quê?\n\n"
            "Texto para as questões 1 e 2\nO gelo derrete a 0 grau.\n\n1. A que temperatura o gelo derrete?\n2. Por quê?\n"
        )
        self.assertEqual([q.context_refs for q in res.questions], [["ctx_1"], ["ctx_1"], ["ctx_2"], ["ctx_2"]])

    def test_instrucoes_numeradas_nao_viram_questoes(self) -> None:
        res = decompose_material(
            "Escola Municipal\nInstruções:\n1. Leia com atenção.\n2. Use caneta azul.\n\n"
            "Questão 1: Quanto é 2 + 2?\na) 3\nb) 4\n\nQuestão 2: Quanto é 3 + 3?\na) 5\nb) 6\n"
        )
        self.assertEqual(res.total_questions, 2)
        self.assertEqual(res.header, "Escola Municipal")
        self.assertEqual(res.instructions, "Instruções:\n1. Leia com atenção.\n2. Use caneta azul.")

    def test_servico_aplica_os_limites_de_tamanho(self) -> None:
        with self.assertRaises(MaterialValidationError) as curto:
            decompose_material_service("1. Oi?")
        self.assertEqual(curto.exception.code, "TEXT_TOO_SHORT")
        with self.assertRaises(MaterialValidationError) as longo:
            decompose_material_service("1. " + "abc def ghi jkl\n" * 20_000)
        self.assertEqual(longo.exception.code, "CONTEXT_WINDOW_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
