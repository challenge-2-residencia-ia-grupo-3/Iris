"""Medição do Agente Adaptador com modelo gerador (História 2.1.3 / Issue #18).

Sem modelo: um cliente substituto devolve, em rodízio, o enunciado sem alteração, o enunciado com
uma dica acrescentada e um texto que não é JSON. Os testes conferem que cada resposta cai no
desfecho certo e que o relatório é gravado.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from iris.core.llm_client import LLMResponse
from iris.eval import adaptador_com_modelo as medicao
from iris.eval.benchmark import carregar_golden_benchmark


class _ModeloEmRodizio:
    provider_name = "ollama"

    def __init__(self) -> None:
        self.chamadas = 0

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        enunciado = prompt.split("ENUNCIADO ORIGINAL:\n", 1)[1]
        modo = self.chamadas % 3
        self.chamadas += 1
        if modo == 0:
            texto = json.dumps({"texto_adaptado": enunciado, "justificativas": []})
        elif modo == 1:
            texto = json.dumps({"texto_adaptado": enunciado + "\nDica: releia o texto.", "justificativas": []})
        else:
            texto = "não sei responder em JSON"
        return LLMResponse(text=texto, provider="ollama", model="substituto", prompt_tokens=100,
                           completion_tokens=50, raw_usage={"load_ms": 0.0, "tokens_per_sec": 25.0})


class TestMedicaoComModelo(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.questoes = carregar_golden_benchmark()[:2]
        cls.medida = medicao.medir(cls.questoes, cliente=_ModeloEmRodizio())

    def test_uma_chamada_por_questao_e_nivel(self) -> None:
        self.assertEqual(len(self.medida["registros"]), 2 * 3)

    def test_cada_resposta_cai_no_desfecho_certo(self) -> None:
        # A chamada 0 é o aquecimento; as medidas começam na chamada 1 do rodízio.
        esperado = ["reprovada no escopo", "falha do modelo", "aprovada sem adaptar"] * 2
        self.assertEqual([r["desfecho"] for r in self.medida["registros"]], esperado)

    def test_reprovacao_traz_o_motivo(self) -> None:
        reprovadas = [r for r in self.medida["registros"] if r["desfecho"] == "reprovada no escopo"]
        self.assertTrue(all(r["motivo"] == "palavra nova" for r in reprovadas))

    def test_reprovada_e_falha_vao_para_a_saida_de_reserva(self) -> None:
        for r in self.medida["registros"]:
            self.assertEqual(r["used_fallback"], r["desfecho"] in {"reprovada no escopo", "falha do modelo"})

    def test_relatorio_e_figura_sao_gravados(self) -> None:
        resumo, registros = self.medida["resumo"], self.medida["registros"]
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "figura.png"
            medicao._figura({**resumo, "_registros": registros}, caminho)
            self.assertGreater(caminho.stat().st_size, 0)
        texto = medicao._texto(resumo, registros)
        self.assertIn("LATÊNCIA POR CHAMADA", texto)
        self.assertIn("palavra nova", texto)


if __name__ == "__main__":
    unittest.main()
