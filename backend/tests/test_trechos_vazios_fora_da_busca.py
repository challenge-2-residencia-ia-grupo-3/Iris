"""Trecho que é só o aviso de licença não entra na busca (issue #86).

Documento restrito ausente na máquina vira, na ingestão, um "trecho" com o aviso "texto não reproduzido por restrição
de licença". Ele fica no chunks.jsonl para as citações antigas acharem título e endereço, mas não pode ocupar vaga na
busca: na base da dev, 13 dos 20 trechos entregues à organização da escrita eram esse aviso, e o professor via
"fonte científica" numa frase cujo trecho citado não tinha texto.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PACOTE = Path(__file__).resolve().parents[2] / "rag" / "iris-rag" / "pacote"
if str(PACOTE) not in sys.path:
    sys.path.insert(0, str(PACOTE))

import consultar  # noqa: E402
import embeddings as emb  # noqa: E402

AVISO = "(texto não reproduzido por restrição de licença; consultar o endereço de origem)"


def _trecho(cid: str, texto: str, n: int) -> dict:
    return {"chunk_id": cid, "doc_id": cid.split("#")[0], "texto": texto, "texto_indexado": f"Documento: {cid}\n\n{texto}",
            "n_palavras": n, "barreiras": ["organizacao_sequencial"], "parte": "D"}


class TestTrechoVazioForaDaBusca(unittest.TestCase):
    def setUp(self) -> None:
        self.chunks = [
            _trecho("RESTRITO#0001", AVISO + " organização sequencial da escrita roteiro", 0),
            _trecho("ABERTO#0001", "Roteiro de planejamento ajuda a organização sequencial da escrita.", 9),
            _trecho("ABERTO#0002", "Tempo extra em prova para estudantes com TDAH.", 7),
        ]
        bm25 = emb.BuscaBM25([c["texto_indexado"] for c in self.chunks])
        self.base = (self.chunks, {c["chunk_id"]: c for c in self.chunks}, bm25)

    def test_buscavel(self) -> None:
        self.assertFalse(consultar.buscavel(self.chunks[0]))
        self.assertTrue(consultar.buscavel(self.chunks[1]))

    def test_busca_por_palavra_nao_devolve_o_aviso(self) -> None:
        with mock.patch.object(consultar, "_base", return_value=self.base):
            ids = [cid for cid, _ in consultar._ranking_bm25("organização sequencial da escrita roteiro", 3, None)]
            ids_filtro = [cid for cid, _ in consultar._ranking_bm25("organização sequencial", 3, {"barreira": "organizacao_sequencial"})]
        self.assertNotIn("RESTRITO#0001", ids)
        self.assertNotIn("RESTRITO#0001", ids_filtro)
        self.assertEqual(ids[0], "ABERTO#0001")

    def test_busca_no_banco_filtra_trecho_sem_texto(self) -> None:
        import banco_pg

        class Con:
            sql = ""

            def execute(self, sql, params=None):
                Con.sql = Con.sql or sql if "SELECT" in sql else Con.sql
                return self

            def fetchall(self):
                return []
        banco_pg.buscar_denso(Con(), [0.0, 0.0], "qwen3", 5, {"barreira": "organizacao_sequencial"})
        self.assertIn("n_palavras > 0", Con.sql)


if __name__ == "__main__":
    unittest.main()
