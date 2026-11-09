"""Testes unitários para o módulo de legibilidade Flesch PT-BR e comandos escolares."""

import unittest

from iris.eval.readability import (
    analyze_question,
    count_conjugated_commands,
    count_syllables,
    find_commands,
    flesch_ptbr,
    split_sentences,
)


class TestReadability(unittest.TestCase):
    def test_syllables(self):
        self.assertEqual(count_syllables("casa"), 2)
        self.assertEqual(count_syllables("aluno"), 3)
        self.assertEqual(count_syllables("o"), 1)

    def test_sentences(self):
        self.assertEqual(len(split_sentences("Leia o texto. Responda! Por quê?")), 3)

    def test_flesch_simple_text_is_easier_than_complex(self):
        simple = "O gato bebe leite. O cão corre no parque."
        complex_ = (
            "A fotossintetização constitui um processo bioquímico extremamente "
            "complexo, desencadeado pela absorção de radiação eletromagnética."
        )
        self.assertGreater(flesch_ptbr(simple), flesch_ptbr(complex_))

    def test_flesch_empty(self):
        self.assertIsNone(flesch_ptbr(""))

    def test_commands_with_accents_and_case(self):
        self.assertEqual(
            find_commands("Leia o texto e Justifique sua resposta."),
            ["leia", "justifique"],
        )

    def test_conjugated_commands(self):
        self.assertEqual(count_conjugated_commands("Leia o texto e responda."), 2)
        self.assertEqual(count_conjugated_commands("Leia o texto. Responda."), 0)
        self.assertEqual(count_conjugated_commands("Analise, compare e justifique."), 3)

    def test_analyze_question(self):
        s = analyze_question("Q01", "Leia o texto e responda. Justifique.")
        self.assertEqual(s.n_commands, 3)
        self.assertEqual(s.n_conjugated_commands, 2)
        self.assertTrue(s.has_conjugated_command)

    def test_commands_with_clitic(self):
        self.assertEqual(
            find_commands("Classifique-o e escreva-a em seguida."),
            ["classifique", "escreva"],
        )


if __name__ == "__main__":
    unittest.main()
