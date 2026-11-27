"""Testes do gate determinístico de recusa por nota do reranker e da calibragem (#156)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
REPO_ROOT = BACKEND_DIR.parent
RAG_PACOTE_DIR = REPO_ROOT / "rag" / "iris-rag" / "pacote"
for p in (str(SRC_DIR), str(BACKEND_DIR), str(RAG_PACOTE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import gerar
from iris.eval.calibrar_recusa import avaliar_limiar, calibrar_limiares, executar_calibracao


class TestRerankAbstentionGateECalibragem(unittest.TestCase):
    def _trechos_fake(self, score: float) -> list[dict]:
        return [
            {
                "posicao": 1,
                "chunk_id": "DOC#0001",
                "doc": "DOC",
                "titulo": "Guia DUA",
                "pagina": "10",
                "secao": "Seção 1",
                "score": score,
                "idioma": "pt-BR",
                "parte": "A",
                "tipo_evidencia": "diretriz_dua",
                "url": "https://exemplo.org",
                "nao_usar_para": [],
                "nota_uso": "",
                "trecho": "Use checklists curtos para apoiar a memória de trabalho.",
            }
        ]

    def test_limiar_desligado_por_padrao(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RAG_RERANK_MIN_SCORE", None)
            self.assertIsNone(gerar.limiar_recusa_rerank())

    def test_gate_abstem_sem_chamar_llm_quando_rerank_abaixo_do_limiar(self) -> None:
        with patch.dict(os.environ, {"RAG_RERANK_MIN_SCORE": "2.0"}, clear=False):
            with patch("consultar.buscar", return_value=self._trechos_fake(0.45)), patch(
                "gerar.gerar", side_effect=AssertionError("LLM não deveria ser chamado abaixo do limiar")
            ):
                res = gerar.responder("Qual é a capital da Austrália?", metodo="qwen3+rerank50", k=5)

        self.assertEqual(res["resposta"], gerar.FRASE_SEM_RESPOSTA)
        self.assertTrue(res["conferencia"]["absteve"])
        self.assertEqual(res["motivo_abstencao"], "rerank_abaixo_do_limiar")
        self.assertEqual(res["rerank_top1_score"], 0.45)
        self.assertEqual(res["limiar_recusa_rerank"], 2.0)
        self.assertEqual(res["uso_tokens"]["prompt_tokens"], 0)

    def test_gate_nao_dispara_acima_do_limiar_ou_sem_reranker(self) -> None:
        with patch.dict(os.environ, {"RAG_RERANK_MIN_SCORE": "2.0"}, clear=False):
            with patch("consultar.buscar", return_value=self._trechos_fake(4.2)), patch(
                "gerar.gerar", return_value=("Use checklists explícitos [T1].", {"prompt_tokens": 50, "completion_tokens": 10})
            ) as mock_llm:
                res_alto = gerar.responder("Como apoiar memória de trabalho?", metodo="qwen3+rerank50", k=5)
                self.assertEqual(mock_llm.call_count, 1)
                self.assertIsNone(res_alto["motivo_abstencao"])
                self.assertEqual(res_alto["rerank_top1_score"], 4.2)

            # Em método sem reranker (bm25), a escala de score é outra e o gate de rerank não dispara
            with patch("consultar.buscar", return_value=self._trechos_fake(0.3)), patch(
                "gerar.gerar", return_value=("Use checklists explícitos [T1].", {"prompt_tokens": 50, "completion_tokens": 10})
            ) as mock_bm25:
                res_bm25 = gerar.responder("Como apoiar memória de trabalho?", metodo="bm25", k=5)
                self.assertEqual(mock_bm25.call_count, 1)
                self.assertIsNone(res_bm25["motivo_abstencao"])

    def test_calibrar_limiares_separa_treino_e_validacao(self) -> None:
        dentro = [3.5, 4.1, 4.8, 5.2, 6.0, 3.9, 4.4, 5.5, 4.7, 5.1]
        fora = [-2.0, -1.2, 0.1, 0.4, 0.8, -0.5, 0.2, 0.9, -1.5, 0.3]

        cal = calibrar_limiares(dentro, fora, meta_recusa=0.93, max_falsa_recusa=0.10)
        lim = cal["limiar_recomendado"]
        self.assertGreater(lim, 0.9)
        self.assertLess(lim, 3.5)
        self.assertEqual(cal["validacao"]["recusa_fora_base"], 1.0)
        self.assertEqual(cal["validacao"]["falsa_recusa_dentro_base"], 0.0)

        ev = avaliar_limiar(dentro, fora, lim)
        self.assertEqual(ev["f1_abstencao"], 1.0)

    def test_executar_calibracao_com_ranqueador_injetado_sem_gravar(self) -> None:
        def ranqueador_falso(pergunta: str, metodo: str, n: int) -> list[tuple[str, float]]:
            # Perguntas do gabarito tendem a citar TDAH/DUA/prova/leitura; fora da base citam Austrália/futebol/DF
            p_low = pergunta.lower()
            eh_fora = any(w in p_low for w in ("austrália", "futebol", "bolo", "lua", "brasília", "pneu", "salário"))
            return [("DOC#0001", 0.2 if eh_fora else 4.5)]

        res = executar_calibracao(metodo="qwen3+rerank50", salvar=False, ranqueador=ranqueador_falso)
        self.assertGreater(res["n_dentro"], 10)
        self.assertGreater(res["n_fora"], 10)
        self.assertGreaterEqual(res["limiar_recomendado"], 0.2)
        self.assertLessEqual(res["limiar_recomendado"], 4.5)

    def test_rota_rag_answer_expoe_telemetria_gate_sem_chamar_llm(self) -> None:
        from fastapi.testclient import TestClient
        from iris.main import create_app

        client = TestClient(create_app())
        with patch.dict(os.environ, {"RAG_RERANK_MIN_SCORE": "0.7281"}, clear=False):
            with patch("consultar.buscar", return_value=self._trechos_fake(0.25)), patch(
                "gerar.gerar", side_effect=AssertionError("LLM não deveria rodar no gate")
            ):
                resp = client.post(
                    "/api/v1/rag/answer",
                    json={"pergunta": "Qual a dose de metilfenidato?", "metodo": "qwen3+rerank50", "k": 5},
                )

        self.assertEqual(resp.status_code, 200)
        tel = resp.json()["telemetria_consulta"]
        self.assertEqual(tel["rerank_top1_score"], 0.25)
        self.assertEqual(tel["limiar_recusa_rerank"], 0.7281)
        self.assertEqual(tel["motivo_abstencao"], "rerank_abaixo_do_limiar")
        self.assertTrue(tel["absteve"])
        self.assertEqual(resp.json()["uso_tokens"]["prompt_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
