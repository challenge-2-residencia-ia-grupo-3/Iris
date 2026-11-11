"""Testes do schema BenchmarkQuestionItem e do dataset questoes_escolares_v1.json."""

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from iris.schemas.benchmark import (
    CAMINHO_PADRAO,
    CATALOGOS_PADRAO,
    MINIMO_QUESTOES,
    BenchmarkQuestionItem,
    carregar_questoes_escolares,
    ids_caracteristicas,
    validar_conjunto,
)


def item(**kw):
    base = dict(
        id="E01",
        disciplina="Matemática",
        ano_escolar="8º ano EF",
        habilidade_bncc="EF08MA06",
        enunciado_original="Resolva a equação 2x + 6 = 14 e indique o valor de x.",
        conceitos_trava_curricular=["2x + 6 = 14", "valor de x"],
        operacao_cognitiva="aplicar",
        id_caracteristica_alvo="CARAC-01",
    )
    base.update(kw)
    return base


class TestBenchmarkQuestionItem(unittest.TestCase):
    def test_item_valido(self):
        q = BenchmarkQuestionItem(**item())
        self.assertEqual(q.status, "rascunho")
        self.assertIsNone(q.alternativas)

    def test_campos_obrigatorios_e_extras_proibidos(self):
        with self.assertRaises(ValidationError):
            BenchmarkQuestionItem(**{k: v for k, v in item().items() if k != "habilidade_bncc"})
        with self.assertRaises(ValidationError):
            BenchmarkQuestionItem(**item(campo_inventado=1))

    def test_bncc_aceita_codigos_reais(self):
        for codigo in ("EF08MA06", "EF67LP28", "EM13MAT101", "EM13LP01"):
            with self.subTest(codigo=codigo):
                self.assertTrue(BenchmarkQuestionItem(**item(habilidade_bncc=codigo)))

    def test_bncc_recusa_codigos_invalidos(self):
        for codigo in ("MA06", "EF8MA6", "ef08ma06", ""):
            with self.subTest(codigo=codigo), self.assertRaises(ValidationError):
                BenchmarkQuestionItem(**item(habilidade_bncc=codigo))

    def test_ano_e_operacao_sao_vocabulario_fechado(self):
        with self.assertRaises(ValidationError):
            BenchmarkQuestionItem(**item(ano_escolar="4º ano EF"))
        with self.assertRaises(ValidationError):
            BenchmarkQuestionItem(**item(operacao_cognitiva="decorar"))

    def test_alternativas(self):
        alts = [{"letra": "A", "texto": "4"}, {"letra": "B", "texto": "8"}]
        q = BenchmarkQuestionItem(**item(alternativas=alts))
        self.assertIn("A) 4", q.texto_completo)
        with self.assertRaises(ValidationError):
            BenchmarkQuestionItem(**item(alternativas=[{"letra": "A", "texto": "4"}]))
        with self.assertRaises(ValidationError):
            BenchmarkQuestionItem(**item(alternativas=[{"letra": "A", "texto": "4"}, {"letra": "A", "texto": "8"}]))

    def test_trava_precisa_estar_no_original_e_pode_estar_nas_alternativas(self):
        with self.assertRaisesRegex(ValidationError, "ausentes"):
            BenchmarkQuestionItem(**item(conceitos_trava_curricular=["equação", "logaritmo"]))
        alts = [{"letra": "A", "texto": "logaritmo"}, {"letra": "B", "texto": "raiz"}]
        self.assertTrue(
            BenchmarkQuestionItem(**item(conceitos_trava_curricular=["equação", "logaritmo"], alternativas=alts))
        )

    def test_trava_vazia_ou_repetida_recusada(self):
        for trava in ([], [" "], ["equação", "equação"]):
            with self.subTest(trava=trava), self.assertRaises(ValidationError):
                BenchmarkQuestionItem(**item(conceitos_trava_curricular=trava))


class TestValidarConjunto(unittest.TestCase):
    def test_validar_conjunto(self):
        itens = [BenchmarkQuestionItem(**item(id=f"E{i:02d}")) for i in range(3)]
        probs = " | ".join(validar_conjunto(itens, minimo=3))
        self.assertIn("sem fonte", probs)
        self.assertNotIn("mínimo", probs)
        self.assertTrue(any("mínimo" in p for p in validar_conjunto(itens, minimo=30, exigir_fonte=False)))
        dup = [itens[0], itens[0]]
        self.assertTrue(any("repetidos" in p for p in validar_conjunto(dup, minimo=1, exigir_fonte=False)))
        self.assertTrue(
            any("catálogo" in p for p in validar_conjunto(itens, 1, catalogo_ids={"X"}, exigir_fonte=False))
        )


class TestCatalogoDeCaracteristicas(unittest.TestCase):
    def test_ids_do_catalogo_lidos_do_disco(self):
        with tempfile.TemporaryDirectory() as pasta:
            (Path(pasta) / "x.json").write_text('[{"id_caracteristica": "abc_def_ghi"}]', encoding="utf-8")
            self.assertEqual(ids_caracteristicas(pasta), {"abc_def_ghi"})

    def test_caminho_padrao_dos_catalogos_existe(self):
        # O catálogo é versionado: caminho inexistente desliga a conferência de id_caracteristica_alvo.
        self.assertTrue(CATALOGOS_PADRAO.is_dir(), f"pasta de catálogos não encontrada: {CATALOGOS_PADRAO}")

    def test_catalogo_real_tem_ids(self):
        self.assertGreaterEqual(len(ids_caracteristicas()), 10)


class TestDatasetV1(unittest.TestCase):
    def test_caminho_padrao_do_dataset_existe(self):
        self.assertTrue(CAMINHO_PADRAO.is_file(), f"dataset não encontrado: {CAMINHO_PADRAO}")

    def test_dataset_v1_valido_e_completo(self):
        itens = carregar_questoes_escolares()
        ids = ids_caracteristicas()
        self.assertTrue(ids, "catálogo de características vazio: a conferência não seria feita")
        self.assertEqual(validar_conjunto(itens, MINIMO_QUESTOES, catalogo_ids=ids), [])


if __name__ == "__main__":
    unittest.main()
