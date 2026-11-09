"""Testes de aceitação preliminares para o Golden Benchmark (História 4.2.5)."""

import unittest
from pathlib import Path

from iris.eval.readability import analyze_question, load_questions, summarize


class TestGoldenBenchmarkAcceptance(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        self.benchmark_path = self.repo_root / "data" / "golden_benchmark.json"

    def test_golden_benchmark_file_exists_and_is_valid_json(self):
        self.assertTrue(
            self.benchmark_path.exists(),
            f"Arquivo {self.benchmark_path} não encontrado.",
        )
        questions = load_questions(self.benchmark_path)
        self.assertGreaterEqual(len(questions), 30)

    def test_golden_benchmark_required_fields(self):
        questions = load_questions(self.benchmark_path)
        disciplinas = set()
        for q in questions:
            self.assertIn("id", q)
            self.assertIn("disciplina", q)
            self.assertIn("ano", q)
            self.assertIn("enunciado", q)
            self.assertIn("comando_conjugado_esperado", q)
            self.assertIsInstance(q["enunciado"], str)
            self.assertTrue(len(q["enunciado"].strip()) > 0)
            disciplinas.add(q["disciplina"])

        # Deve cobrir ao menos 4 disciplinas centrais
        self.assertTrue(
            {"Português", "Matemática", "Ciências", "História"}.issubset(disciplinas)
        )

    def test_golden_benchmark_metrics_computation(self):
        questions = load_questions(self.benchmark_path)
        analyzed = []
        for q in questions:
            stats = analyze_question(q["id"], q["enunciado"])
            row = dict(q)
            row.update(stats.__dict__)
            analyzed.append(row)

        summary = summarize(analyzed)
        self.assertEqual(summary["n_questoes"], len(questions))
        self.assertIsNotNone(summary["flesch_media"])
        self.assertGreater(summary["pct_questoes_com_comando_conjugado"], 0.0)


if __name__ == "__main__":
    unittest.main()
