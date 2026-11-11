"""Verificador de isolamento de escopo (História 2.1.3 / Issue #18).

O verificador compara o enunciado original com o adaptado por contagem de palavras, sem modelo.
Os testes cobrem o que ele tem de aceitar (o andaime de cada nível) e o que tem de acusar
(palavra perdida, palavra nova, ordem trocada, conceito da trava ausente).
"""
from __future__ import annotations

import unittest

from iris.eval.escopo import ID_COMANDOS_MULTIPLOS, localizar_comandos, palavras, verificar_escopo

ORIGINAL = "Leia o texto, identifique o sujeito da oração e classifique-o como simples ou composto."
TRAVA = ["sujeito", "simples|composto"]

NIVEL_1 = "**Leia** o texto, **identifique** o sujeito da oração e **classifique**-o como simples ou composto."
NIVEL_2 = (
    "1. [ ] **Leia** o texto\n"
    "2. [ ] **Identifique** o sujeito da oração\n"
    "3. [ ] **Classifique**-o como simples ou composto."
)
NIVEL_3 = (
    "**Passo 1**\n[ ] **Leia** o texto\n\n"
    "**Passo 2**\n**Identifique** o sujeito da oração\nResposta: ______________\n\n"
    "**Passo 3**\n**Classifique**-o como simples ou composto.\nResposta: ______________\n\n"
    "Revise se você preencheu todos os passos."
)


def _laudo(adaptado: str, nivel: int, caracteristica: str = ID_COMANDOS_MULTIPLOS):
    return verificar_escopo(ORIGINAL, adaptado, caracteristica, nivel, TRAVA)


class TestLocalizarComandos(unittest.TestCase):
    def test_conta_os_verbos_no_imperativo(self) -> None:
        self.assertEqual(len(localizar_comandos(ORIGINAL)), 3)

    def test_substantivo_depois_de_determinante_nao_e_comando(self) -> None:
        self.assertEqual(len(localizar_comandos("Explique a escolha do autor.")), 1)

    def test_infinitivo_em_texto_corrido_nao_e_comando(self) -> None:
        self.assertEqual(localizar_comandos("Para calcular a área, é preciso medir os lados."), [])


class TestPalavras(unittest.TestCase):
    def test_marcacao_de_andaime_nao_conta_como_palavra(self) -> None:
        self.assertEqual(palavras("1. [ ] **Leia** o texto"), ["leia", "o", "texto"])

    def test_numeros_e_operadores_do_enunciado_contam(self) -> None:
        self.assertEqual(palavras("Resolva 24 × 6."), ["resolva", "24", "×", "6"])


class TestAndaimeAceito(unittest.TestCase):
    def test_original_sem_alteracao_e_aprovado_nos_tres_niveis(self) -> None:
        for nivel in (1, 2, 3):
            with self.subTest(nivel=nivel):
                self.assertTrue(_laudo(ORIGINAL, nivel).aprovado)

    def test_nivel_1_aceita_negrito_nos_verbos(self) -> None:
        laudo = _laudo(NIVEL_1, 1)
        self.assertTrue(laudo.aprovado, laudo.violacoes)

    def test_nivel_2_aceita_lista_numerada_e_conta_o_conectivo_retirado(self) -> None:
        laudo = _laudo(NIVEL_2, 2)
        self.assertTrue(laudo.aprovado, laudo.violacoes)
        self.assertEqual(laudo.conectivos_removidos, 1)
        self.assertEqual(laudo.palavras_perdidas, [])

    def test_nivel_3_aceita_passos_linha_de_resposta_e_lembrete(self) -> None:
        laudo = _laudo(NIVEL_3, 3)
        self.assertTrue(laudo.aprovado, laudo.violacoes)
        self.assertEqual(laudo.palavras_novas, [])


class TestViolacoesAcusadas(unittest.TestCase):
    def test_nivel_1_acusa_separacao_em_etapas(self) -> None:
        laudo = _laudo(NIVEL_2, 1)
        self.assertFalse(laudo.aprovado)
        self.assertTrue(laudo.estrutura_alterada)

    def test_nivel_2_acusa_vocabulario_do_nivel_3(self) -> None:
        laudo = _laudo(NIVEL_3, 2)
        self.assertFalse(laudo.aprovado)
        self.assertIn("passo", laudo.palavras_novas)

    def test_acusa_sinonimo(self) -> None:
        laudo = _laudo(NIVEL_2.replace("oração", "frase"), 2)
        self.assertFalse(laudo.aprovado)
        self.assertEqual(laudo.palavras_perdidas, ["oração"])
        self.assertEqual(laudo.palavras_novas, ["frase"])

    def test_acusa_resposta_inserida(self) -> None:
        laudo = _laudo(NIVEL_2 + "\nDica: o sujeito é composto.", 2)
        self.assertFalse(laudo.aprovado)
        self.assertIn("dica", laudo.palavras_novas)

    def test_acusa_comando_retirado(self) -> None:
        laudo = _laudo("1. [ ] **Leia** o texto\n2. [ ] **Classifique**-o como simples ou composto.", 2)
        self.assertFalse(laudo.aprovado)
        self.assertIn("identifique", laudo.palavras_perdidas)

    def test_acusa_etapas_fora_de_ordem(self) -> None:
        trocado = (
            "1. [ ] **Identifique** o sujeito da oração\n"
            "2. [ ] **Leia** o texto\n"
            "3. [ ] **Classifique**-o como simples ou composto."
        )
        laudo = _laudo(trocado, 2)
        self.assertFalse(laudo.aprovado)
        self.assertTrue(laudo.ordem_alterada)
        self.assertEqual(laudo.palavras_perdidas, [])

    def test_acusa_conceito_da_trava_ausente(self) -> None:
        laudo = _laudo(NIVEL_2.replace("sujeito", ""), 2)
        self.assertFalse(laudo.aprovado)
        self.assertEqual(laudo.conceitos_perdidos, ["sujeito"])

    def test_conectivo_que_nao_liga_comandos_nao_pode_ser_retirado(self) -> None:
        original = "Compare Maria e João e explique a diferença."
        adaptado = "1. [ ] **Compare** Maria João\n2. [ ] **Explique** a diferença."
        laudo = verificar_escopo(original, adaptado, ID_COMANDOS_MULTIPLOS, 2)
        self.assertEqual(laudo.conectivos_removidos, 1)
        self.assertEqual(laudo.palavras_perdidas, ["e"])
        self.assertFalse(laudo.aprovado)


class TestCaracteristicaSemRegra(unittest.TestCase):
    def test_so_a_trava_decide_e_as_diferencas_sao_informadas(self) -> None:
        laudo = _laudo(NIVEL_2 + "\nDica: releia com calma.", 2, caracteristica="dificuldade_decodificacao_leitora")
        self.assertFalse(laudo.regra_aplicada)
        self.assertTrue(laudo.aprovado)
        self.assertIn("dica", laudo.palavras_novas)

    def test_conceito_ausente_reprova_mesmo_sem_regra(self) -> None:
        laudo = _laudo(ORIGINAL.replace("sujeito", "termo"), 2, caracteristica="dificuldade_decodificacao_leitora")
        self.assertFalse(laudo.aprovado)


if __name__ == "__main__":
    unittest.main()
