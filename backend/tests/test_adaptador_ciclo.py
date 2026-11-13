"""Latência do ciclo Extrator + Adaptador (História 2.1.3 / Issue #18).

Sem modelo: o cliente substituto devolve o enunciado sem alteração quando o pedido é do Adaptador e um
texto sem JSON quando é do Extrator, que então usa a extração por regras. Os testes conferem a soma do
ciclo, a contagem das quedas e a gravação do relatório.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from iris.core.llm_client import LLMResponse
from iris.eval import adaptador_ciclo as ciclo
from iris.eval.benchmark import carregar_golden_benchmark


class _ModeloSubstituto:
    provider_name = "ollama"

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        if "ENUNCIADO ORIGINAL:\n" in prompt:
            enunciado = prompt.split("ENUNCIADO ORIGINAL:\n", 1)[1]
            texto = json.dumps({"texto_adaptado": enunciado, "justificativas": []})
        else:
            texto = "sem JSON"
        return LLMResponse(text=texto, provider="ollama", model="substituto", prompt_tokens=100, completion_tokens=50)


class TestCiclo(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.medida = ciclo.medir(carregar_golden_benchmark()[:2], cliente=_ModeloSubstituto())

    def test_um_ciclo_por_questao_e_nivel(self) -> None:
        self.assertEqual(len(self.medida["registros"]), 2 * 3)

    def test_ciclo_soma_extrator_e_adaptador(self) -> None:
        for r in self.medida["registros"]:
            self.assertAlmostEqual(r["ciclo_ms"], r["extrator_ms"] + r["adaptador_ms"], places=1)

    def test_extrator_sem_json_cai_nas_regras(self) -> None:
        self.assertTrue(all(r["extrator_fallback"] for r in self.medida["registros"]))
        self.assertEqual(sum(c["extrator_fallback"] for c in self.medida["resumo"]["por_nivel"].values()), 6)

    def test_texto_igual_ao_original_mantem_o_trcc(self) -> None:
        self.assertTrue(all(r["trcc_entregue"] == r["trcc_original"] for r in self.medida["registros"]))

    def test_relatorio_e_figura_sao_gravados(self) -> None:
        resumo, registros = self.medida["resumo"], self.medida["registros"]
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "figura.png"
            ciclo._figura(resumo, registros, caminho)
            self.assertGreater(caminho.stat().st_size, 0)
        self.assertIn("TEMPO DO CICLO", ciclo._texto(resumo, registros))


if __name__ == "__main__":
    unittest.main()
