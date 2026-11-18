"""A busca que falha e cai na reserva por palavras (BM25) precisa aparecer na bancada, com o motivo.

Caso real que motivou: num ambiente com o banco de vetores de outra base de trechos, a busca `qwen3+rerank50` dava
KeyError no reordenador e tudo rodava em BM25 sem aviso. Aqui a falha é forçada com um método que não existe.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
RAG_PACOTE_DIR = BACKEND_DIR.parent / "rag" / "iris-rag" / "pacote"
for p in (str(SRC_DIR), str(RAG_PACOTE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from iris.eval import rag_escolar_benchmark as rb
from iris.main import app

PLAYGROUND = SRC_DIR / "iris" / "static" / "playground.html"
METODO_QUE_FALHA = "metodo-inexistente"


class TestBuscaNaReserva(unittest.TestCase):
    def setUp(self) -> None:
        self._env = {k: os.environ.get(k) for k in ("RAG_LLM", "IRIS_LLM_PROVIDER")}
        os.environ["RAG_LLM"] = "extractive"
        os.environ["IRIS_LLM_PROVIDER"] = "extractive"
        self.cliente = TestClient(app)

    def tearDown(self) -> None:
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_busca_devolve_o_motivo(self) -> None:
        r = self.cliente.post("/api/v1/rag/search", json={"pergunta": "estudante com TDAH", "metodo": METODO_QUE_FALHA})
        d = r.json()
        self.assertTrue(d["fallback_aplicado"])
        self.assertEqual(d["metodo_efetivo"], "bm25")
        self.assertIn("método desconhecido", d["fallback_motivo"])

    def test_resposta_ao_vivo_devolve_o_motivo(self) -> None:
        r = self.cliente.post("/api/v1/rag/answer", json={"pergunta": "estudante com TDAH", "metodo": METODO_QUE_FALHA,
                                                          "avaliador_geracao": "lexico"})
        tel = r.json()["telemetria_consulta"]
        self.assertTrue(tel["fallback_aplicado"])
        self.assertIn("método desconhecido", tel["fallback_motivo"])

    def test_registro_da_questao_guarda_a_reserva(self) -> None:
        av = {"questao": {k: None for k in ("id", "disciplina", "ano_escolar", "faixa_etaria", "operacao_cognitiva",
                                            "id_caracteristica_alvo", "barreira_rag_associada", "porte_texto",
                                            "fonte_oficial")},
              "metricas": {}, "trechos_recuperados": [], "fallback_aplicado": True, "fallback_motivo": "KeyError: 'x'"}
        reg = rb._compactar_registro_item(av)
        self.assertTrue(reg["fallback_aplicado"])
        self.assertEqual(reg["fallback_motivo"], "KeyError: 'x'")

    def test_tela_usa_o_mesmo_aviso_nos_tres_lugares(self) -> None:
        html = PLAYGROUND.read_text(encoding="utf-8")
        # consulta por característica, consulta ao vivo e inspetor de uma questão
        self.assertEqual(html.count("avisoBuscaNaReserva(") - 1, 3)
        self.assertIn("consultas_na_reserva", html)
        self.assertIn("busca por palavras (reserva)", html)


if __name__ == "__main__":
    unittest.main()
