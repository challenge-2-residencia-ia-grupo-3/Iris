"""Testes da História 2.1.1 (Issue #16): Context Precision (RAGAS) da recuperação do RAG.

Três camadas:
  1. a pontuação do RAGAS por identificador em casos montados à mão (sempre roda);
  2. a medida inteira com um ranqueador falso (sempre roda);
  3. a régua BM25 no gabarito real (pulada se a base local não tem os trechos do gabarito).

A busca padrão (Qwen3 e reranker) precisa de banco vetorial e de modelos baixados; ela é medida por
``python -m iris.eval.precisao_contexto``, e aqui só entra com IRIS_TESTE_BUSCA_PADRAO=1.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Garante que `backend/src` esteja no sys.path mesmo quando rodado via `python3 -m unittest`
BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.config import get_settings
from iris.eval.precisao_contexto import (
    acaso,
    carregar_gabarito,
    conferir_universo,
    medir,
    pontuar_ragas_por_id,
    ranqueador_do_pacote,
)
from iris.rag import garantir_chunks_locais, obter_trechos_base


class TestPontuacaoRagasPorId(unittest.TestCase):
    """A métrica do RAGAS devolve a fração dos trechos recuperados que está na referência."""

    def test_todos_os_recuperados_sao_certos(self) -> None:
        self.assertEqual(pontuar_ragas_por_id(["a", "b"], ["a", "b", "c"]), 1.0)

    def test_dois_de_cinco(self) -> None:
        self.assertAlmostEqual(pontuar_ragas_por_id(["a", "x", "b", "y", "z"], ["a", "b"]), 0.4)

    def test_nenhum_certo(self) -> None:
        self.assertEqual(pontuar_ragas_por_id(["x", "y"], ["a"]), 0.0)


class TestMedirComRanqueadorFalso(unittest.TestCase):
    """A medida inteira, sem base nem modelo: o ranqueador é uma tabela fixa."""

    ITENS = [
        {"id": "T1", "pergunta": "p1", "trechos_relevantes": ["a", "b"]},
        {"id": "T2", "pergunta": "p2", "trechos_relevantes": ["c"]},
    ]
    RANKINGS = {"p1": ["a", "x", "b", "y", "z"], "p2": ["x", "y", "z", "w", "v"]}

    def _medir(self) -> dict:
        return medir(self.ITENS, "falso", lambda pergunta, metodo, n: self.RANKINGS[pergunta][:n])

    def test_precisao_por_pergunta(self) -> None:
        p1, p2 = self._medir()["por_pergunta"]
        self.assertAlmostEqual(p1["precisao_ragas"], 0.4)
        # certo em 1º e em 3º: (1/1 + 2/3) / 2
        self.assertAlmostEqual(p1["precisao_posicao"], (1 + 2 / 3) / 2)
        self.assertEqual((p2["precisao_ragas"], p2["precisao_posicao"]), (0.0, 0.0))

    def test_resumo_e_teto(self) -> None:
        resumo = self._medir()["resumo"]
        self.assertAlmostEqual(resumo["precisao_ragas"]["media"], 0.2)
        self.assertAlmostEqual(resumo["teto_precisao_ragas"], (2 / 5 + 1 / 5) / 2)
        self.assertEqual(resumo["perguntas_sem_acerto"], 1)

    def test_posicao_importa(self) -> None:
        """O mesmo trecho certo vale mais em 1º do que em 5º; a precisão por identificador não muda."""
        item = [{"id": "T", "pergunta": "p", "trechos_relevantes": ["a"]}]
        topo = medir(item, "f", lambda *_: ["a", "x", "y", "z", "w"])["por_pergunta"][0]
        fundo = medir(item, "f", lambda *_: ["x", "y", "z", "w", "a"])["por_pergunta"][0]
        self.assertEqual(topo["precisao_ragas"], fundo["precisao_ragas"])
        self.assertGreater(topo["precisao_posicao"], fundo["precisao_posicao"])

    def test_universo_incompleto_e_acusado(self) -> None:
        self.assertEqual(conferir_universo(self.ITENS, {"a", "c"}), ["b"])
        self.assertEqual(conferir_universo(self.ITENS, {"a", "b", "c", "z"}), [])


def _base_e_gabarito() -> tuple[list[dict], set[str], list[str]]:
    garantir_chunks_locais()
    itens = carregar_gabarito()
    ids_base = {c["chunk_id"] for c in obter_trechos_base()}
    return itens, ids_base, conferir_universo(itens, ids_base)


class TestReguaBm25NoGabaritoReal(unittest.TestCase):
    """A régua (busca por palavra, sem modelo) no gabarito de 38 perguntas."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.itens, cls.ids_base, faltando = _base_e_gabarito()
        if faltando:
            raise unittest.SkipTest(
                f"{len(faltando)} trechos do gabarito fora da base local (documentos sem licença aberta ausentes)"
            )
        cls.ranquear = staticmethod(ranqueador_do_pacote())
        cls.medida = medir(cls.itens, "bm25", cls.ranquear)

    def test_mede_todas_as_perguntas(self) -> None:
        self.assertEqual(self.medida["n_perguntas"], len(self.itens))
        for p in self.medida["por_pergunta"]:
            self.assertEqual(len(p["recuperados"]), 5)
            self.assertTrue(0.0 <= p["precisao_ragas"] <= p["teto_precisao_ragas"])
            self.assertTrue(0.0 <= p["precisao_posicao"] <= 1.0)

    def test_mesmo_numero_em_duas_rodadas(self) -> None:
        outra = medir(self.itens, "bm25", self.ranquear)
        self.assertEqual(self.medida["por_pergunta"], outra["por_pergunta"])

    def test_regua_acima_do_acaso(self) -> None:
        """O intervalo de 95% da régua fica inteiro acima da precisão de 5 trechos sorteados."""
        piso = acaso(self.itens, len(self.ids_base))
        self.assertGreater(self.medida["resumo"]["precisao_ragas"]["ic95"][0], piso)


@unittest.skipUnless(os.environ.get("IRIS_TESTE_BUSCA_PADRAO") == "1", "defina IRIS_TESTE_BUSCA_PADRAO=1 (exige banco e modelos)")
class TestBuscaPadraoContraRegua(unittest.TestCase):
    """A busca padrão não pode entregar contexto menos preciso do que a régua BM25."""

    def test_padrao_nao_perde_da_regua(self) -> None:
        itens, _, faltando = _base_e_gabarito()
        if faltando:
            self.skipTest("base local incompleta")
        ranquear = ranqueador_do_pacote()
        regua = medir(itens, "bm25", ranquear)["resumo"]
        padrao = medir(itens, get_settings().rag_metodo, ranquear)["resumo"]
        for nome in ("precisao_ragas", "precisao_posicao"):
            self.assertGreaterEqual(padrao[nome]["media"], regua[nome]["media"], nome)


if __name__ == "__main__":
    unittest.main()
