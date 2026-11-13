"""Testes do teste de recusa (pergunta fora da base), do limite do RNF-07 ao lado da latência e do
aviso de gerador igual ao juiz no Benchmark Escolar."""
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
    executar_benchmark_rag_escolar,
    executar_teste_de_recusa,
    obter_teste_de_recusa,
    resumir_modelos,
    resumir_rnf07,
)
from iris.main import app
from iris.schemas.adaptation import LIMITE_LATENCIA_MS

FRASE_RECUSA = "Não encontrei nos documentos da base informação suficiente para responder."


@contextlib.contextmanager
def _ambiente_extrativo():
    """Força a geração extrativa determinística: sem modelo, sem chave e sem rede."""
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


def _geracao_fixa(recusa: bool, llm: str = "teste:fixo"):
    """Gerador simulado: sempre recusa ou sempre responde, para testar a contagem sem depender da base."""

    def _fn(*, pergunta: str, metodo: str, k: int, filtro_barreira: str | None) -> dict:
        resposta = FRASE_RECUSA if recusa else "Uma resposta qualquer com citação [T1]."
        return {
            "resposta": resposta,
            "metodo": metodo,
            "llm": llm,
            "trechos_entregues": [{"chunk_id": "c1"}],
            "conferencia": {"absteve": recusa, "trechos_citados": [] if recusa else [1]},
        }

    return _fn


class TestLimiteRnf07(unittest.TestCase):
    def test_limite_muda_com_o_nivel(self) -> None:
        itens = [{"segundos_total": 1.0}, {"segundos_total": 20.0}, {"segundos_total": 50.0}]
        n1 = resumir_rnf07(itens, 1)
        n2 = resumir_rnf07(itens, 2)
        self.assertEqual(n1["limite_ms"], LIMITE_LATENCIA_MS[1])
        self.assertEqual((n1["dentro"], n1["fora"]), (1, 2))
        self.assertEqual(n2["limite_ms"], LIMITE_LATENCIA_MS[2])
        self.assertEqual((n2["dentro"], n2["fora"]), (2, 1))
        self.assertEqual(n2["pct_dentro"], 66.7)
        self.assertEqual(n2["maior_ms"], 50000.0)

    def test_exatamente_no_limite_conta_como_dentro(self) -> None:
        self.assertEqual(resumir_rnf07([{"segundos_total": 15.0}], 1)["dentro"], 1)

    def test_sem_tempo_medido_nao_ha_veredito(self) -> None:
        self.assertIsNone(resumir_rnf07([], 2))
        self.assertIsNone(resumir_rnf07([{"segundos_total": None}], 2))

    def test_nivel_ausente_usa_o_nivel_2(self) -> None:
        self.assertEqual(resumir_rnf07([{"segundos_total": 1.0}], None)["nivel"], 2)


class TestGeradorEJuiz(unittest.TestCase):
    def test_mesmo_modelo_e_contado_mesmo_com_o_provedor_na_frente(self) -> None:
        itens = [
            {"llm": "anthropic:claude-x", "avaliador_fidelidade": "claude_sonnet", "modelo_juiz": "claude-x"},
            {"llm": "anthropic:claude-x", "avaliador_fidelidade": "claude_sonnet", "modelo_juiz": "Claude-X"},
            {"llm": "ollama:llama3.1:8b", "avaliador_fidelidade": "claude_sonnet", "modelo_juiz": "claude-x"},
        ]
        m = resumir_modelos(itens)
        self.assertEqual(m["gerador_igual_ao_juiz"], 2)
        self.assertEqual(m["julgados_por_modelo"], 3)
        self.assertEqual(m["juizes"], ["Claude-X", "claude-x"])
        self.assertEqual(m["geradores"], ["anthropic:claude-x", "ollama:llama3.1:8b"])

    def test_avaliador_lexico_nao_e_juiz_modelo(self) -> None:
        m = resumir_modelos([{"llm": "extractive:x", "avaliador_fidelidade": "lexico_local", "modelo_juiz": None}])
        self.assertEqual((m["julgados_por_modelo"], m["gerador_igual_ao_juiz"]), (0, 0))

    def test_rodada_antiga_sem_modelo_do_juiz_fica_como_desconhecido(self) -> None:
        m = resumir_modelos([{"llm": "anthropic:claude-x", "avaliador_fidelidade": "claude_sonnet"}])
        self.assertEqual((m["juiz_desconhecido"], m["gerador_igual_ao_juiz"]), (1, 0))

    def test_sem_geracao_nao_ha_modelos(self) -> None:
        self.assertIsNone(resumir_modelos([{"id": "Q1"}]))

    def _rodar_com_juiz_simulado(self, tmp: str, modelo_juiz: str) -> dict:
        """Rodada real de busca, com gerador e juiz simulados (nenhuma chamada externa)."""
        geracao_real = bench._executar_geracao_segura

        def geracao(**kw: object) -> dict:
            res = geracao_real(**kw)
            res["llm"] = "anthropic:claude-gerador"
            return res

        veredito = {
            "fidelidade_sonnet": 0.9,
            "fidelidade_sonnet_bruta": 0.9,
            "relevancia_sonnet": 0.8,
            "resumo_frases": {"sem_citacao": 0, "apoiada": 1, "total_conteudo": 1},
        }
        with (
            _ambiente_extrativo(),
            patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"),
            patch.object(bench, "_executar_geracao_segura", geracao),
            patch.object(bench, "julgar_resposta_sonnet", lambda **_kw: dict(veredito)),
            patch.object(bench, "sonnet_judge_status", lambda: {"ready": True, "model": modelo_juiz}),
        ):
            return executar_benchmark_rag_escolar(
                metodo="bm25",
                k=3,
                gerar_resposta=True,
                avaliador_geracao="sonnet",
                limite=3,
                caminho_runs=Path(tmp) / "runs.jsonl",
                caminho_base=Path(tmp) / "base.json",
                salvar=True,
                progresso=lambda _msg: None,
            )

    def test_rodada_com_juiz_igual_ao_gerador_e_acusada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            an = self._rodar_com_juiz_simulado(tmp, "claude-gerador")
            self.assertEqual(an["modelos"]["gerador_igual_ao_juiz"], 3)
            self.assertEqual(an["modelos"]["julgados_por_modelo"], 3)
            self.assertEqual(an["itens"][0]["modelo_juiz"], "claude-gerador")

    def test_rodada_com_juiz_de_outro_modelo_nao_e_acusada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            an = self._rodar_com_juiz_simulado(tmp, "claude-outro")
            self.assertEqual(an["modelos"]["gerador_igual_ao_juiz"], 0)
            self.assertEqual(an["modelos"]["juizes"], ["claude-outro"])

    def test_provedor_extrativo_nao_grava_nome_de_modelo_de_linguagem(self) -> None:
        class ClienteExtrativo:
            def status(self) -> dict:
                return {"primary_available": True, "configured_provider": "extractive"}

        with _ambiente_extrativo(), patch("iris.core.llm_client.get_llm_client", lambda **_kw: ClienteExtrativo()):
            res = bench._executar_geracao_segura(
                pergunta="Como reduzir a carga cognitiva de um enunciado?", metodo="bm25", k=3, filtro_barreira=None
            )
        self.assertEqual(res["llm"], "extractive:deterministic-bm25-extractive")

    def test_rodada_real_traz_limite_e_modelos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            with patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"):
                an = executar_benchmark_rag_escolar(
                    metodo="bm25",
                    nivel=1,
                    k=3,
                    gerar_resposta=True,
                    avaliador_geracao="lexico",
                    limite=4,
                    caminho_runs=Path(tmp) / "runs.jsonl",
                    caminho_base=Path(tmp) / "base.json",
                    salvar=True,
                    progresso=lambda _msg: None,
                )
            self.assertEqual(an["rnf07"]["nivel"], 1)
            self.assertEqual(an["rnf07"]["limite_ms"], 15000.0)
            self.assertEqual(an["rnf07"]["dentro"], 4)
            self.assertEqual(an["modelos"]["julgados_por_modelo"], 0)
            self.assertTrue(all(g.startswith("extractive:") for g in an["modelos"]["geradores"]))


class TestTesteDeRecusa(unittest.TestCase):
    def test_gerador_que_sempre_recusa_tira_100_e_o_que_nunca_recusa_tira_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminhos = {"caminho_saida": Path(tmp) / "recusa.json", "caminho_runs": Path(tmp) / "runs.jsonl"}
            with patch.object(bench, "_executar_geracao_segura", _geracao_fixa(True)):
                sempre = executar_teste_de_recusa(metodo="bm25", **caminhos)
            with patch.object(bench, "_executar_geracao_segura", _geracao_fixa(False)):
                nunca = executar_teste_de_recusa(metodo="bm25", **caminhos)
        self.assertEqual(sempre["resumo"]["taxa_recusa_pct"], 100.0)
        self.assertEqual(sempre["resumo"]["recusou"], sempre["resumo"]["total"])
        self.assertEqual(nunca["resumo"]["taxa_recusa_pct"], 0.0)
        self.assertEqual(nunca["resumo"]["recusou"], 0)
        self.assertEqual(nunca["geradores"], ["teste:fixo"])

    def test_conta_por_tipo_e_grava_a_procedencia(self) -> None:
        def geracao(*, pergunta: str, **kw: object) -> dict:
            return _geracao_fixa("capital" in pergunta)(pergunta=pergunta, **kw)

        with tempfile.TemporaryDirectory() as tmp:
            perguntas = Path(tmp) / "perguntas.json"
            perguntas.write_text(
                json.dumps(
                    {
                        "perguntas": [
                            {"id": "A", "tipo": "longe", "pergunta": "Qual é a capital da Austrália?"},
                            {"id": "B", "tipo": "longe", "pergunta": "Como trocar um pneu?"},
                            {"id": "C", "tipo": "perto", "pergunta": "Qual é o telefone da escola?"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            saida = Path(tmp) / "recusa.json"
            with patch.object(bench, "_executar_geracao_segura", geracao):
                res = executar_teste_de_recusa(
                    metodo="bm25", caminho_perguntas=perguntas, caminho_saida=saida, caminho_runs=Path(tmp) / "r.jsonl"
                )
            gravado = json.loads(saida.read_text(encoding="utf-8"))
        self.assertEqual(res["resumo"]["total"], 3)
        self.assertEqual(res["resumo"]["recusou"], 1)
        self.assertEqual(res["por_tipo"]["longe"]["recusou"], 1)
        self.assertEqual(res["por_tipo"]["perto"]["taxa_recusa_pct"], 0.0)
        self.assertEqual([i["recusou"] for i in res["itens"]], [True, False, False])
        self.assertEqual(res["procedencia"]["dataset_arquivo"], "perguntas.json")
        self.assertEqual(len(res["procedencia"]["dataset_sha256"]), 16)
        self.assertEqual(gravado["teste_id"], res["teste_id"])
        self.assertIsNone(res["dentro_da_base"])

    def test_arquivo_de_perguntas_vazio_nao_roda_nem_grava(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            perguntas = Path(tmp) / "perguntas.json"
            perguntas.write_text('{"perguntas": []}', encoding="utf-8")
            saida = Path(tmp) / "recusa.json"
            with self.assertRaises(ValueError):
                executar_teste_de_recusa(caminho_perguntas=perguntas, caminho_saida=saida)
            self.assertFalse(saida.exists())

    def test_regua_e_a_abstencao_da_ultima_bateria_com_a_mesma_busca(self) -> None:
        def rodada(run_id: str, metodo: str, abstencoes: list[bool]) -> dict:
            return {
                "run_id": run_id,
                "metodo_efetivo": metodo,
                "gerar_resposta": True,
                "itens": [{"id": f"Q{i}", "llm": "teste:fixo", "absteve": a} for i, a in enumerate(abstencoes)],
            }

        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs.jsonl"
            linhas = [
                rodada("antiga", "bm25", [True, True, True, True]),
                rodada("recente", "bm25", [True, False, False, False]),
                rodada("outra-busca", "hibrido", [True, True, True, True]),
            ]
            runs.write_text("\n".join(json.dumps(r) for r in linhas) + "\n", encoding="utf-8")
            with patch.object(bench, "_executar_geracao_segura", _geracao_fixa(True)):
                res = executar_teste_de_recusa(metodo="bm25", caminho_saida=Path(tmp) / "x.json", caminho_runs=runs)
        self.assertEqual(res["dentro_da_base"]["run_id"], "recente")
        self.assertEqual(res["dentro_da_base"]["taxa_abstencao_pct"], 25.0)
        self.assertEqual(res["dentro_da_base"]["total"], 4)

    def test_acusa_inversao_so_quando_os_intervalos_nao_se_tocam(self) -> None:
        def rodada(abstencoes: list[bool]) -> dict:
            return {
                "run_id": "r",
                "metodo_efetivo": "bm25",
                "gerar_resposta": True,
                "itens": [{"id": f"Q{i}", "llm": "teste:fixo", "absteve": a} for i, a in enumerate(abstencoes)],
            }

        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs.jsonl"
            saida = Path(tmp) / "x.json"
            # Dentro da base se abstém em 90%; fora da base nunca recusa: invertido.
            runs.write_text(json.dumps(rodada([True] * 36 + [False] * 4)) + "\n", encoding="utf-8")
            with patch.object(bench, "_executar_geracao_segura", _geracao_fixa(False)):
                invertido = executar_teste_de_recusa(metodo="bm25", caminho_saida=saida, caminho_runs=runs)
            # Fora da base recusa tudo: é o desejado, não acusa.
            with patch.object(bench, "_executar_geracao_segura", _geracao_fixa(True)):
                certo = executar_teste_de_recusa(metodo="bm25", caminho_saida=saida, caminho_runs=runs)
            # Sem bateria dentro da base não há régua, então não acusa.
            with patch.object(bench, "_executar_geracao_segura", _geracao_fixa(False)):
                sem_regua = executar_teste_de_recusa(
                    metodo="bm25", caminho_saida=saida, caminho_runs=Path(tmp) / "vazio.jsonl"
                )
        self.assertTrue(invertido["invertido"])
        self.assertFalse(certo["invertido"])
        self.assertFalse(sem_regua["invertido"])

    def test_rodada_real_extrativa_e_deterministica(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            caminhos = {"caminho_saida": Path(tmp) / "recusa.json", "caminho_runs": Path(tmp) / "runs.jsonl"}
            a = executar_teste_de_recusa(metodo="bm25", **caminhos)
            b = executar_teste_de_recusa(metodo="bm25", **caminhos)
        self.assertEqual(a["resumo"]["total"], 16)
        self.assertEqual({k: v["total"] for k, v in a["por_tipo"].items()}, {"longe": 8, "perto": 8})
        self.assertEqual([i["recusou"] for i in a["itens"]], [i["recusou"] for i in b["itens"]])
        self.assertEqual(a["resumo"]["ic95"], b["resumo"]["ic95"])
        for item in a["itens"]:
            self.assertEqual(item["recusou"], FRASE_RECUSA[:40].lower() in item["resposta"].lower())

    def test_sem_teste_gravado_a_leitura_diz_que_nao_ha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            res = obter_teste_de_recusa(caminho_saida=Path(tmp) / "nao-existe.json")
        self.assertFalse(res["tem_teste"])
        self.assertEqual(res["total_perguntas"], 16)


class TestRotasDoTesteDeRecusa(unittest.TestCase):
    def _caminhos(self, tmp: str):
        return (
            patch.object(bench, "RUNS_RAG_ESCOLAR_PADRAO", Path(tmp) / "runs.jsonl"),
            patch.object(bench, "RECUSA_RAG_ESCOLAR_PADRAO", Path(tmp) / "recusa.json"),
        )

    def test_fastapi_le_roda_e_le_de_novo(self) -> None:
        if app is None:
            self.skipTest("FastAPI não disponível neste interpretador Python")
        from fastapi.testclient import TestClient

        client = TestClient(app)
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as pilha, _ambiente_extrativo():
            for p in self._caminhos(tmp):
                pilha.enter_context(p)
            antes = client.get("/api/v1/eval/rag-escolar/recusa")
            self.assertEqual(antes.status_code, 200)
            self.assertFalse(antes.json()["tem_teste"])

            rodou = client.post("/api/v1/eval/rag-escolar/recusa", json={"metodo": "bm25"})
            self.assertEqual(rodou.status_code, 200)
            self.assertEqual(rodou.json()["resumo"]["total"], 16)

            depois = client.get("/api/v1/eval/rag-escolar/recusa").json()
            self.assertTrue(depois["tem_teste"])
            self.assertEqual(depois["teste_id"], rodou.json()["teste_id"])

            with patch.object(bench, "PERGUNTAS_FORA_DA_BASE_PADRAO", Path(tmp) / "vazio.json"):
                (Path(tmp) / "vazio.json").write_text('{"perguntas": []}', encoding="utf-8")
                vazio = client.post("/api/v1/eval/rag-escolar/recusa", json={})
            self.assertEqual(vazio.status_code, 422)

    def test_servidor_de_reserva_le_roda_e_le_de_novo(self) -> None:
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
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/v1/eval/rag-escolar/recusa"
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()

        def chamar(corpo: dict | None) -> tuple[int, dict]:
            req = urllib.request.Request(
                url,
                data=json.dumps(corpo).encode("utf-8") if corpo is not None else None,
                headers={"Content-Type": "application/json"},
                method="POST" if corpo is not None else "GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                return err.code, json.loads(err.read().decode("utf-8"))

        try:
            with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as pilha, _ambiente_extrativo():
                for p in self._caminhos(tmp):
                    pilha.enter_context(p)
                status, antes = chamar(None)
                self.assertEqual((status, antes["tem_teste"]), (200, False))
                status, rodou = chamar({"metodo": "bm25"})
                self.assertEqual((status, rodou["resumo"]["total"]), (200, 16))
                status, depois = chamar(None)
                self.assertEqual((status, depois["teste_id"]), (200, rodou["teste_id"]))
                with patch.object(bench, "PERGUNTAS_FORA_DA_BASE_PADRAO", Path(tmp) / "vazio.json"):
                    (Path(tmp) / "vazio.json").write_text('{"perguntas": []}', encoding="utf-8")
                    status, _ = chamar({})
                self.assertEqual(status, 422)
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
