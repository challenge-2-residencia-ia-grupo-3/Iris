"""Testes das garantias de qualidade do Benchmark Escolar: intervalo de confiança, procedência da rodada,
linha de base, recusa de rodada vazia e métricas garantidas por construção."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
REPO_ROOT = BACKEND_DIR.parent
RAG_PACOTE_DIR = REPO_ROOT / "rag" / "iris-rag" / "pacote"
for p in (str(SRC_DIR), str(BACKEND_DIR), str(RAG_PACOTE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from iris.eval import rag_escolar_benchmark as bench
from iris.eval.rag_escolar_benchmark import (
    METRICAS_POR_CONSTRUCAO,
    carregar_linha_de_base,
    carregar_rodadas_rag_escolar,
    comparar_com_linha_de_base,
    definir_linha_de_base,
    executar_benchmark_rag_escolar,
    intervalo_confianca_media,
    obter_analytics_rag_escolar,
)
from iris.main import app


def _rodada(run_id: str, fidelidades: tuple[float, ...] | list[float], **extra: object) -> dict:
    """Rodada sintética mínima: uma questão por valor de fidelidade."""
    base = {
        "run_id": run_id,
        "timestamp_utc": "2026-11-13T00:00:00+00:00",
        "metodo_efetivo": "bm25",
        "estrategia_query": "contexto_pedagogico",
        "nivel": 2,
        "k": 5,
        "gerar_resposta": True,
        "avaliador_efetivo": "lexico_local",
        "filtros_execucao": {"disciplina": None, "limite": None},
        "procedencia": {"commit": "abc1234", "dataset_sha256": "0123456789abcdef"},
        "itens": [
            {
                "id": f"Q{i}",
                "retornou_evidencia": True,
                "n_trechos": 5,
                "score_top1": 10.0,
                "segundos_busca": 0.05,
                "segundos_total": 0.1,
                "fidelidade_efetiva": f,
                "fidelidade_lexica": f,
                "relevancia_efetiva": 0.5,
                "relevancia_lexica": 0.5,
                "absteve": False,
            }
            for i, f in enumerate(fidelidades)
        ],
    }
    base.update(extra)
    return base


@contextlib.contextmanager
def _ambiente_extrativo():
    """Garante geração sem modelo e sem chave durante o teste."""
    antigos = {k: os.environ.get(k) for k in ("RAG_LLM", "ANTHROPIC_API_KEY")}
    os.environ["RAG_LLM"] = "extractive"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        yield
    finally:
        for chave, valor in antigos.items():
            if valor is None:
                os.environ.pop(chave, None)
            else:
                os.environ[chave] = valor


class TestIntervaloDeConfianca(unittest.TestCase):
    def test_repetir_da_o_mesmo_intervalo_e_ele_contem_a_media(self) -> None:
        valores = [0.1, 0.4, 0.4, 0.7, 0.9, 1.0, 0.2, 0.6]
        ic1 = intervalo_confianca_media(valores)
        ic2 = intervalo_confianca_media(list(valores))
        self.assertEqual(ic1, ic2)
        media = sum(valores) / len(valores)
        self.assertLess(ic1[0], media)
        self.assertGreater(ic1[1], media)
        self.assertGreaterEqual(ic1[0], min(valores))
        self.assertLessEqual(ic1[1], max(valores))

    def test_valores_iguais_dao_intervalo_de_largura_zero(self) -> None:
        self.assertEqual(intervalo_confianca_media([0.5] * 20), [0.5, 0.5])

    def test_menos_de_dois_valores_nao_tem_intervalo(self) -> None:
        self.assertIsNone(intervalo_confianca_media([]))
        self.assertIsNone(intervalo_confianca_media([0.7]))
        self.assertIsNone(intervalo_confianca_media([None, 0.7, None]))

    def test_mais_questoes_estreitam_o_intervalo(self) -> None:
        poucos = intervalo_confianca_media([0.0, 1.0] * 5)
        muitos = intervalo_confianca_media([0.0, 1.0] * 100)
        self.assertLess(muitos[1] - muitos[0], poucos[1] - poucos[0])


class TestComparacaoComLinhaDeBase(unittest.TestCase):
    BASE = (0.6, 0.7, 0.8, 0.7, 0.6, 0.8, 0.7, 0.7, 0.6, 0.8)

    def _veredito(self, comparacao: dict, chave: str) -> str:
        return next(m["veredito"] for m in comparacao["metricas"] if m["chave"] == chave)

    def test_queda_fora_do_intervalo_e_piora(self) -> None:
        comp = comparar_com_linha_de_base(_rodada("atual", [0.1] * 10), _rodada("base", self.BASE))
        self.assertTrue(comp["comparavel"])
        self.assertEqual(self._veredito(comp, "fidelidade_media"), "piorou")

    def test_subida_fora_do_intervalo_e_melhora(self) -> None:
        comp = comparar_com_linha_de_base(_rodada("atual", [1.0] * 10), _rodada("base", self.BASE))
        self.assertEqual(self._veredito(comp, "fidelidade_media"), "melhorou")

    def test_diferenca_dentro_do_intervalo_e_igual(self) -> None:
        quase = [0.6, 0.7, 0.8, 0.7, 0.6, 0.8, 0.7, 0.7, 0.6, 0.7]
        comp = comparar_com_linha_de_base(_rodada("atual", quase), _rodada("base", self.BASE))
        self.assertEqual(self._veredito(comp, "fidelidade_media"), "igual")
        self.assertEqual(self._veredito(comp, "relevancia_media"), "igual")

    def test_latencia_maior_e_piora_e_abstencao_so_muda(self) -> None:
        atual = _rodada("atual", self.BASE)
        for item in atual["itens"]:
            item["segundos_total"] = 9.0
            item["absteve"] = True
        base = _rodada("base", self.BASE)
        base["itens"][0]["segundos_total"] = 0.2
        comp = comparar_com_linha_de_base(atual, base)
        self.assertEqual(self._veredito(comp, "latencia_total_ms"), "piorou")
        self.assertEqual(self._veredito(comp, "taxa_abstencao_pct"), "mudou")

    def test_configuracao_filtro_ou_prova_diferente_nao_compara(self) -> None:
        base = _rodada("base", self.BASE)
        outra_estrategia = comparar_com_linha_de_base(_rodada("a", self.BASE, estrategia_query="barreira"), base)
        self.assertFalse(outra_estrategia["comparavel"])
        self.assertEqual(outra_estrategia["metricas"], [])
        self.assertIn("estrategia_query", outra_estrategia["motivos"][0])

        outro_filtro = comparar_com_linha_de_base(
            _rodada("a", self.BASE, filtros_execucao={"disciplina": "Matemática", "limite": None}), base
        )
        self.assertFalse(outro_filtro["comparavel"])

        outra_prova = comparar_com_linha_de_base(
            _rodada("a", self.BASE, procedencia={"commit": "abc1234", "dataset_sha256": "ffffffffffffffff"}), base
        )
        self.assertFalse(outra_prova["comparavel"])
        self.assertIn("a prova mudou", outra_prova["motivos"][0])

    def test_rodada_comparada_com_ela_mesma(self) -> None:
        base = _rodada("base", self.BASE)
        comp = comparar_com_linha_de_base(base, base)
        self.assertTrue(comp["mesma_rodada"])
        self.assertEqual(comp["metricas"], [])


class TestRodadaNoRag(unittest.TestCase):
    """Rodadas reais com BM25 e geração extrativa (sem modelo e sem chave)."""

    def _executar(self, tmp: str, **kw: object) -> dict:
        parametros = {
            "metodo": "bm25",
            "k": 3,
            "gerar_resposta": True,
            "avaliador_geracao": "lexico",
            "limite": 6,
            "caminho_runs": Path(tmp) / "runs.jsonl",
            "caminho_base": Path(tmp) / "base.json",
            "salvar": True,
            "progresso": lambda _msg: None,
        }
        parametros.update(kw)
        with _ambiente_extrativo(), patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"):
            return executar_benchmark_rag_escolar(**parametros)

    def test_filtro_sem_questoes_recusa_e_nao_grava(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                self._executar(tmp, disciplina="Disciplina Inexistente")
            self.assertIn("Nenhuma questão", str(ctx.exception))
            self.assertFalse((Path(tmp) / "runs.jsonl").exists())

    def test_rodada_grava_procedencia_e_intervalos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parciais: list[dict] = []
            an = self._executar(tmp, on_step=parciais.append)
            proc = an["run_info"]["procedencia"]
            self.assertRegex(proc["dataset_sha256"], r"^[0-9a-f]{16}$")
            self.assertEqual(proc["dataset_arquivo"], "questoes_escolares_curado_v1.json")
            self.assertIn("commit", proc)
            self.assertIn("commit_com_alteracoes_locais", proc)

            gravada = carregar_rodadas_rag_escolar(Path(tmp) / "runs.jsonl")[-1]
            self.assertEqual(gravada["procedencia"], proc)

            resumo = an["resumo_geral"]
            self.assertEqual(resumo["total"], 6)
            for chave in ("fidelidade_media", "relevancia_media", "latencia_total_ms", "taxa_abstencao_pct"):
                lo, hi = resumo["ic95"][chave]
                self.assertLessEqual(lo, hi)
                self.assertLessEqual(lo, resumo[chave] + 1e-6)
                self.assertGreaterEqual(hi, resumo[chave] - 1e-6)
            for grupo in an["por_disciplina"].values():
                self.assertIn("ic95", grupo)

            # o resumo parcial (ao vivo) não calcula intervalo: é recalculado a cada questão
            com_resumo = [p for p in parciais if p.get("resumo_parcial")]
            self.assertTrue(com_resumo)
            self.assertNotIn("ic95", com_resumo[-1]["resumo_parcial"])

    def test_metricas_por_construcao_sao_declaradas_e_valem_100(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            an = self._executar(tmp, gerar_resposta=False)
            self.assertEqual(set(an["metricas_por_construcao"]), {"taxa_retorno_pct", "aderencia_barreira_pct"})
            self.assertEqual(an["metricas_por_construcao"], METRICAS_POR_CONSTRUCAO)
            self.assertEqual(an["resumo_geral"]["taxa_retorno_pct"], 100.0)
            self.assertEqual(an["resumo_geral"]["aderencia_barreira_pct"], 100.0)
            self.assertNotIn("taxa_retorno_pct", an["resumo_geral"]["ic95"])

    def test_linha_de_base_do_registro_a_comparacao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runs, base = Path(tmp) / "runs.jsonl", Path(tmp) / "base.json"
            primeira = self._executar(tmp)
            self.assertIsNone(primeira["linha_de_base"])
            id_1 = primeira["run_info"]["run_id"]

            with self.assertRaises(KeyError):
                definir_linha_de_base("rodada-que-nao-existe", caminho_runs=runs, caminho_base=base)
            self.assertIsNone(carregar_linha_de_base(base))

            definir_linha_de_base(id_1, caminho_runs=runs, caminho_base=base)
            self.assertEqual(carregar_linha_de_base(base)["run_id"], id_1)

            mesma = obter_analytics_rag_escolar(run_id=id_1, caminho_runs=runs, caminho_base=base)
            self.assertTrue(mesma["linha_de_base"]["mesma_rodada"])
            self.assertTrue(next(r for r in mesma["runs_disponiveis"] if r["run_id"] == id_1)["eh_linha_de_base"])

            segunda = self._executar(tmp)
            comp = segunda["linha_de_base"]
            self.assertTrue(comp["comparavel"])
            self.assertFalse(comp["mesma_rodada"])
            vereditos = {m["chave"]: m["veredito"] for m in comp["metricas"]}
            # mesma busca e mesmo gerador extrativo: fidelidade e relevância repetem exatamente
            self.assertEqual(vereditos["fidelidade_media"], "igual")
            self.assertEqual(vereditos["relevancia_media"], "igual")
            self.assertEqual(vereditos["score_top1_medio"], "igual")

            terceira = self._executar(tmp, estrategia_query="barreira")
            self.assertFalse(terceira["linha_de_base"]["comparavel"])

            definir_linha_de_base(None, caminho_runs=runs, caminho_base=base)
            self.assertIsNone(carregar_linha_de_base(base))
            self.assertFalse(base.exists())


class TestRotas(unittest.TestCase):
    def _caminhos(self, tmp: str):
        return (
            patch.object(bench, "RUNS_RAG_ESCOLAR_PADRAO", Path(tmp) / "runs.jsonl"),
            patch.object(bench, "BASELINE_RAG_ESCOLAR_PADRAO", Path(tmp) / "base.json"),
            patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"),
        )

    def test_fastapi_rodada_vazia_422_e_linha_de_base(self) -> None:
        if app is None:
            self.skipTest("FastAPI não disponível neste interpretador Python")
        from fastapi.testclient import TestClient

        client = TestClient(app)
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as pilha, _ambiente_extrativo():
            for p in self._caminhos(tmp):
                pilha.enter_context(p)
            pilha.enter_context(contextlib.redirect_stdout(io.StringIO()))

            vazia = client.post("/api/v1/eval/rag-escolar/run", json={"metodo": "bm25", "disciplina": "Inexistente"})
            self.assertEqual(vazia.status_code, 422)
            self.assertIn("Nenhuma questão", vazia.json()["detail"])
            self.assertFalse((Path(tmp) / "runs.jsonl").exists())

            rodada = client.post("/api/v1/eval/rag-escolar/run", json={"metodo": "bm25", "limite": 3})
            self.assertEqual(rodada.status_code, 200)
            run_id = rodada.json()["run_info"]["run_id"]

            inexistente = client.post("/api/v1/eval/rag-escolar/baseline", json={"run_id": "nao-existe"})
            self.assertEqual(inexistente.status_code, 404)

            definida = client.post("/api/v1/eval/rag-escolar/baseline", json={"run_id": run_id})
            self.assertEqual(definida.status_code, 200)
            self.assertEqual(definida.json()["linha_de_base"]["run_id"], run_id)

            an = client.get("/api/v1/eval/rag-escolar/analytics").json()
            self.assertTrue(an["linha_de_base"]["mesma_rodada"])

            removida = client.post("/api/v1/eval/rag-escolar/baseline", json={})
            self.assertEqual(removida.status_code, 200)
            self.assertIsNone(removida.json()["linha_de_base"])
            self.assertIsNone(client.get("/api/v1/eval/rag-escolar/analytics").json()["linha_de_base"])

    def test_servidor_de_reserva_rodada_vazia_422_e_linha_de_base(self) -> None:
        from http.server import HTTPServer

        from iris import main as iris_main

        capturado: dict = {}

        class ServidorCapturado:
            def __init__(self, endereco, handler):
                capturado["handler"] = handler

            def serve_forever(self) -> None:
                return None

        with patch("http.server.HTTPServer", ServidorCapturado), contextlib.redirect_stdout(io.StringIO()):
            iris_main.run_stdlib_server()
        handler = capturado["handler"]
        handler.log_message = lambda *args, **kwargs: None
        srv = HTTPServer(("127.0.0.1", 0), handler)
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()

        def post(caminho: str, corpo: dict) -> tuple[int, dict]:
            req = urllib.request.Request(
                url + caminho,
                data=json.dumps(corpo).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                return err.code, json.loads(err.read().decode("utf-8"))

        try:
            with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as pilha, _ambiente_extrativo():
                for p in self._caminhos(tmp):
                    pilha.enter_context(p)
                pilha.enter_context(contextlib.redirect_stdout(io.StringIO()))

                status, corpo = post("/api/v1/eval/rag-escolar/run", {"metodo": "bm25", "disciplina": "Inexistente"})
                self.assertEqual(status, 422)
                self.assertIn("Nenhuma questão", corpo["detail"])

                status, corpo = post("/api/v1/eval/rag-escolar/run", {"metodo": "bm25", "limite": 2})
                self.assertEqual(status, 200)
                run_id = corpo["run_info"]["run_id"]

                status, corpo = post("/api/v1/eval/rag-escolar/baseline", {"run_id": "nao-existe"})
                self.assertEqual(status, 404)
                status, corpo = post("/api/v1/eval/rag-escolar/baseline", {"run_id": run_id})
                self.assertEqual(status, 200)
                self.assertEqual(corpo["linha_de_base"]["run_id"], run_id)
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
