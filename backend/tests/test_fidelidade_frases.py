"""Testes da História 2.1.1 (Issue #16): fidelidade (Faithfulness) por frase, sem juiz ao vivo.

Duas camadas:
  1. a conta em casos montados à mão;
  2. a medida nos vereditos versionados: o resultado não muda sem que este teste acuse.

A versão com juiz ao vivo (``iris.eval.faithfulness``) é testada em ``test_benchmark_pipeline.py``.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from typing import ClassVar

# Garante que `backend/src` esteja no sys.path mesmo quando rodado via `python3 -m unittest`
BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.eval.faithfulness import FAITHFULNESS_MIN
from iris.eval.fidelidade_frases import (
    binario,
    carregar_vereditos,
    concordancia,
    fidelidade,
    ic_bootstrap,
    kappa,
    leitura,
    medir,
    veredito_final,
)


def _frase(a: str, b: str, x: str, final: int | None, dividida: bool = False) -> dict:
    return {"A": a, "B": b, "X": x, "O": "sem_veredito", "final": final, "dividida": dividida}


class TestContaDaFidelidade(unittest.TestCase):
    RESPOSTAS: ClassVar[dict[str, list[dict]]] = {
        # 2 de 2 sustentadas; o comentário não entra na conta
        "Q1": [_frase("apoiada", "apoiada", "apoiada", 1), _frase("apoiada", "parcial", "apoiada", 1),
               _frase("comentario_correto", "comentario_correto", "comentario_correto", None)],
        # 1 de 2
        "Q2": [_frase("apoiada", "apoiada", "apoiada", 1), _frase("parcial", "nao_apoiada", "rejeitado", 0)],
    }

    def test_em_parte_e_prova_rejeitada_contam_como_nao_sustentada(self) -> None:
        self.assertEqual([binario(v) for v in ("apoiada", "parcial", "nao_apoiada", "rejeitado")], [1, 0, 0, 0])
        self.assertIsNone(binario("comentario_correto"))
        self.assertIsNone(binario("sem_veredito"))

    def test_media_por_resposta_e_nao_por_frase(self) -> None:
        f = fidelidade(self.RESPOSTAS, "final")
        self.assertAlmostEqual(f["media"], (1.0 + 0.5) / 2)
        self.assertEqual((f["sustentadas"], f["frases_de_conteudo"], f["respostas"]), (3, 4, 2))

    def test_por_avaliador(self) -> None:
        self.assertAlmostEqual(fidelidade(self.RESPOSTAS, "B")["media"], (0.5 + 0.5) / 2)

    def test_kappa(self) -> None:
        self.assertEqual(kappa([(1, 1), (0, 0), (1, 1), (0, 0)]), 1.0)
        self.assertAlmostEqual(kappa([(1, 1), (1, 0), (0, 1), (0, 0)]), 0.0)

    def test_matriz_de_concordancia(self) -> None:
        c = concordancia(self.RESPOSTAS, "A", "B")
        self.assertEqual((c["frases"], c["iguais"]), (4, 3))
        self.assertEqual(c["matriz"], [[2, 1], [0, 1]])

    def test_leitura_usa_o_intervalo(self) -> None:
        self.assertEqual(leitura({"ic95": [0.92, 0.98]}, 0.90), "atinge a meta")
        self.assertEqual(leitura({"ic95": [0.86, 0.95]}, 0.90), "não se distingue da meta")
        self.assertEqual(leitura({"ic95": [0.70, 0.85]}, 0.90), "abaixo da meta")

    def test_entradas_vazias_nao_quebram(self) -> None:
        self.assertEqual(ic_bootstrap([]), (0.0, 0.0))
        self.assertTrue(math.isnan(kappa([])))
        self.assertEqual(
            fidelidade({}, "final"),
            {"media": 0.0, "ic95": [0.0, 0.0], "sustentadas": 0, "frases_de_conteudo": 0, "respostas": 0},
        )


class TestFidelidadeNosVereditosVersionados(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vereditos = carregar_vereditos()
        cls.medida = medir(cls.vereditos)["geradores"]

    def test_reproduz_a_medicao_original(self) -> None:
        esperado = {"haiku": (0.905, 0.858, 0.947, 170, 187, 38), "opus": (0.950, 0.922, 0.978, 166, 175, 35)}
        for gerador, (media, baixo, alto, sustentadas, total, respostas) in esperado.items():
            f = self.medida[gerador]["fidelidade"]["final"]
            with self.subTest(gerador=gerador):
                self.assertEqual((round(f["media"], 3), round(f["ic95"][0], 3), round(f["ic95"][1], 3)), (media, baixo, alto))
                self.assertEqual((f["sustentadas"], f["frases_de_conteudo"], f["respostas"]), (sustentadas, total, respostas))

    def test_mesmo_numero_em_duas_rodadas(self) -> None:
        self.assertEqual(medir(self.vereditos)["geradores"], self.medida)

    def test_leitura_contra_a_meta(self) -> None:
        """Só o intervalo inteiro acima de FAITHFULNESS_MIN conta como meta atingida."""
        self.assertEqual(FAITHFULNESS_MIN, 0.90)
        self.assertEqual(self.medida["opus"]["leitura"], "atinge a meta")
        self.assertEqual(self.medida["haiku"]["leitura"], "não se distingue da meta")

    def test_nenhuma_frase_nao_sustentada_para_os_tres(self) -> None:
        for gerador, g in self.medida.items():
            self.assertEqual(g["nao_sustentadas_para_os_tres"], 0, gerador)

    def test_todo_veredito_final_de_frase_dividida_veio_do_desempate(self) -> None:
        for respostas in self.vereditos.values():
            for frases in respostas.values():
                for f in frases:
                    if f["dividida"] and binario(f["O"]) is not None:
                        self.assertEqual(f["final"], binario(f["O"]))

    def test_veredito_final_calculado_bate_com_todas_as_frases(self) -> None:
        for respostas in self.vereditos.values():
            for frases in respostas.values():
                for f in frases:
                    self.assertEqual(veredito_final(f), f["final"])


if __name__ == "__main__":
    unittest.main()
