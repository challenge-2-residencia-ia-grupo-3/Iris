"""Testes da História 2.1.1 (Issue #16): a busca filtra estritamente pela característica selecionada.

Critério de aceitação: "a busca vetorial deve filtrar estritamente os documentos correspondentes às
características selecionadas pelo professor".

Roda com a busca por palavra (BM25), que não exige banco nem modelo; o filtro é aplicado antes do
ranqueamento em todos os métodos (``consultar._passa_filtro`` e a cláusula ``= ANY(barreiras)`` do
PostgreSQL). O caminho do PostgreSQL não é exercitado aqui.

Expectativa escrita antes de rodar (11/11/2026): nas 30 combinações (10 características, 3 níveis),
5 trechos devolvidos e os 150 com a barreira da característica; mudaria a leitura um único trecho
sem a barreira, ou uma característica com menos de 5 trechos etiquetados.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Garante que `backend/src` esteja no sys.path mesmo quando rodado via `python3 -m unittest`
BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.rag import buscar_evidencias, buscar_por_caracteristica_atomica, garantir_chunks_locais, obter_trechos_base
from iris.schemas.catalog import BARREIRAS_RAG_VALIDAS, load_all_catalogs


class TestFiltroEstritoPorCaracteristica(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        garantir_chunks_locais()
        cls.barreiras_do_trecho = {c["chunk_id"]: set(c["barreiras"]) for c in obter_trechos_base()}
        cls.caracteristicas = [c for cat in load_all_catalogs().values() for c in cat.caracteristicas]

    def test_todo_trecho_devolvido_tem_a_barreira_da_caracteristica(self) -> None:
        for carac in self.caracteristicas:
            for nivel in (1, 2, 3):
                with self.subTest(caracteristica=carac.id_caracteristica, nivel=nivel):
                    r = buscar_por_caracteristica_atomica(carac.id_caracteristica, nivel=nivel, metodo="bm25")
                    self.assertEqual(r["barreira_rag_associada"], carac.barreira_rag_associada)
                    self.assertEqual(len(r["trechos_rag"]), 5)
                    for t in r["trechos_rag"]:
                        self.assertIn(carac.barreira_rag_associada, self.barreiras_do_trecho[t["chunk_id"]])

    def test_o_filtro_muda_o_resultado(self) -> None:
        """Sem o filtro a mesma consulta traz trecho de fora da barreira; com ele, nenhum."""
        pergunta = "tempo adicional na prova"
        livre = buscar_evidencias(pergunta, metodo="bm25", k=20)
        self.assertTrue(any("flexibilidade_cognitiva" not in self.barreiras_do_trecho[t["chunk_id"]] for t in livre))
        filtrada = buscar_evidencias(pergunta, metodo="bm25", k=20, filtro_barreira="flexibilidade_cognitiva")
        self.assertTrue(filtrada)
        for t in filtrada:
            self.assertIn("flexibilidade_cognitiva", self.barreiras_do_trecho[t["chunk_id"]])

    def test_trecho_sem_etiqueta_nunca_passa_no_filtro(self) -> None:
        sem_etiqueta = {cid for cid, b in self.barreiras_do_trecho.items() if not b}
        self.assertTrue(sem_etiqueta, "a base deixou de ter trechos sem etiqueta: rever este teste")
        for barreira in sorted(BARREIRAS_RAG_VALIDAS):
            achados = buscar_evidencias("lei decreto resolução", metodo="bm25", k=50, filtro_barreira=barreira)
            self.assertFalse(sem_etiqueta & {t["chunk_id"] for t in achados}, barreira)

    def test_toda_barreira_do_catalogo_tem_trechos_na_base(self) -> None:
        contagem = {b: sum(1 for bs in self.barreiras_do_trecho.values() if b in bs) for b in BARREIRAS_RAG_VALIDAS}
        for carac in self.caracteristicas:
            self.assertGreaterEqual(contagem[carac.barreira_rag_associada], 5, carac.id_caracteristica)

    def test_caracteristica_ou_nivel_inexistente_e_recusado(self) -> None:
        with self.assertRaises(Exception):
            buscar_por_caracteristica_atomica("caracteristica_que_nao_existe", metodo="bm25")
        with self.assertRaises(ValueError):
            buscar_por_caracteristica_atomica(self.caracteristicas[0].id_caracteristica, nivel=4, metodo="bm25")


if __name__ == "__main__":
    unittest.main()
