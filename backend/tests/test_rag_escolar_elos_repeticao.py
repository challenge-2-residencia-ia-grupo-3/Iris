"""Testes de "em que elo cada questão parou", da repetição de uma rodada e da linha "pergunta desta tela"
em cada aba do playground."""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
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
    ORDEM_ELOS,
    classificar_elos,
    executar_benchmark_rag_escolar,
    repetir_rodada_rag_escolar,
    resumir_elos,
)
from iris.main import app

PLAYGROUND = SRC_DIR / "iris" / "static" / "playground.html"


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


def _item(**kw: object) -> dict:
    """Questão respondida, com 5 trechos, todas as frases citadas e sem juiz."""
    base = {
        "id": "Q1",
        "n_trechos": 5,
        "llm": "teste:fixo",
        "resposta": "Uma frase com citação [T1].",
        "absteve": False,
        "frases_sem_citacao": 0,
        "citacoes_invalidas": 0,
        "avaliador_fidelidade": "lexico_local",
    }
    base.update(kw)
    return base


def _julgado(**kw: object) -> dict:
    base = {"avaliador_fidelidade": "claude_sonnet", "frases_total": 3, "frases_nao_apoiadas": 0, "frases_rejeitadas": 0}
    base.update(kw)
    return _item(**base)


def _executar(tmp: str, **kw: object) -> dict:
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
    with patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"):
        return executar_benchmark_rag_escolar(**parametros)


class TestClassificarElos(unittest.TestCase):
    def test_sem_trecho_quebra_na_busca_mesmo_que_tenha_se_abstido(self) -> None:
        c = classificar_elos(_item(n_trechos=0, absteve=True))
        self.assertEqual(c["primeiro_elo_quebrado"], "busca")
        self.assertEqual(c["estados"]["abstencao"], "ok")

    def test_com_trechos_a_busca_fica_sem_gabarito_e_nao_conta_como_certa(self) -> None:
        self.assertEqual(classificar_elos(_item())["estados"]["busca"], "sem_gabarito")

    def test_abstencao_com_trechos_quebra_na_abstencao_e_nao_confere_o_resto(self) -> None:
        c = classificar_elos(_item(absteve=True, frases_sem_citacao=2))
        self.assertEqual(c["primeiro_elo_quebrado"], "abstencao")
        self.assertEqual((c["estados"]["citacao"], c["estados"]["fidelidade"]), ("nao_se_aplica", "nao_se_aplica"))

    def test_frase_sem_citacao_ou_citacao_invalida_quebra_na_citacao(self) -> None:
        self.assertEqual(classificar_elos(_item(frases_sem_citacao=1))["primeiro_elo_quebrado"], "citacao")
        self.assertEqual(classificar_elos(_item(citacoes_invalidas=1))["primeiro_elo_quebrado"], "citacao")

    def test_fidelidade_so_e_medida_com_juiz_e_quebra_com_uma_frase_nao_apoiada(self) -> None:
        self.assertEqual(classificar_elos(_item())["estados"]["fidelidade"], "sem_medida")
        self.assertEqual(classificar_elos(_julgado())["estados"]["fidelidade"], "ok")
        self.assertEqual(classificar_elos(_julgado(frases_nao_apoiadas=1))["primeiro_elo_quebrado"], "fidelidade")
        self.assertEqual(classificar_elos(_julgado(frases_rejeitadas=1))["primeiro_elo_quebrado"], "fidelidade")

    def test_conta_no_primeiro_elo_quando_dois_quebram(self) -> None:
        c = classificar_elos(_julgado(frases_sem_citacao=1, frases_nao_apoiadas=2))
        self.assertEqual(c["primeiro_elo_quebrado"], "citacao")
        self.assertEqual(c["estados"]["fidelidade"], "quebrou")

    def test_rodada_so_de_busca_nao_mede_os_elos_da_resposta(self) -> None:
        c = classificar_elos({"id": "Q1", "n_trechos": 5})
        self.assertIsNone(c["primeiro_elo_quebrado"])
        self.assertEqual([c["estados"][e] for e in ORDEM_ELOS[1:]], ["sem_medida"] * 3)

    def test_questao_inteira_nao_tem_elo_quebrado(self) -> None:
        self.assertIsNone(classificar_elos(_julgado())["primeiro_elo_quebrado"])


class TestResumirElos(unittest.TestCase):
    def test_cada_questao_conta_uma_vez_e_a_soma_fecha(self) -> None:
        itens = [
            _item(n_trechos=0, absteve=True),
            _item(absteve=True),
            _item(absteve=True),
            _item(frases_sem_citacao=1),
            _julgado(frases_nao_apoiadas=1),
            _julgado(),
            _item(),
        ]
        r = resumir_elos(itens)
        parou = {e: r["por_elo"][e]["parou_aqui"] for e in ORDEM_ELOS}
        self.assertEqual(parou, {"busca": 1, "abstencao": 2, "citacao": 1, "fidelidade": 1})
        self.assertEqual(r["sem_quebra_medida"], 2)
        self.assertEqual(sum(parou.values()) + r["sem_quebra_medida"], r["total"])
        self.assertEqual(r["por_elo"]["fidelidade"]["medido_em"], 2)
        self.assertEqual(r["por_elo"]["abstencao"]["pct_parou_aqui"], 28.6)
        self.assertEqual(r["elos_sem_medida"], [])

    def test_sem_juiz_a_fidelidade_aparece_como_sem_medida(self) -> None:
        r = resumir_elos([_item(), _item(absteve=True)])
        self.assertEqual(r["elos_sem_medida"], ["busca", "fidelidade"])

    def test_sem_itens_nao_ha_resumo(self) -> None:
        self.assertIsNone(resumir_elos([]))

    def test_rodada_real_bate_com_a_abstencao_do_resumo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            an = _executar(tmp, limite=12)
        abstencoes = sum(1 for i in an["itens"] if i.get("absteve"))
        self.assertEqual(an["elos"]["total"], 12)
        self.assertEqual(an["elos"]["por_elo"]["abstencao"]["parou_aqui"], abstencoes)
        self.assertEqual(an["elos"]["por_elo"]["busca"]["parou_aqui"], 0)
        self.assertIn("primeiro_elo_quebrado", an["itens"][0])
        self.assertEqual(set(an["itens"][0]["estados"]), set(ORDEM_ELOS))


class TestRepetirRodada(unittest.TestCase):
    def test_rodada_deterministica_repete_inteira_e_nao_e_gravada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            runs = Path(tmp) / "runs.jsonl"
            ref = _executar(tmp, limite=5, disciplina="Matemática")
            antes = runs.read_text(encoding="utf-8")
            with patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"):
                tamanho_log = (Path(tmp) / "progress.log").stat().st_size
                r = repetir_rodada_rag_escolar(caminho_runs=runs)
                self.assertEqual((Path(tmp) / "progress.log").stat().st_size, tamanho_log)
            self.assertEqual(runs.read_text(encoding="utf-8"), antes)
        self.assertEqual(r["run_id_referencia"], ref["run_info"]["run_id"])
        self.assertEqual((r["comparadas"], r["trechos_identicos"], r["respostas_identicas"]), (5, 5, 5))
        self.assertTrue(r["repete"])
        self.assertTrue(r["mesma_prova"] and r["mesma_base"])
        self.assertEqual(r["divergentes"], [])
        self.assertEqual(r["diferenca_fidelidade"]["media"], 0.0)

    def test_repete_com_os_mesmos_filtros_e_a_mesma_configuracao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            _executar(tmp, limite=4, k=3, nivel=1, disciplina="Ciências", estrategia_query="barreira")
            real = bench.executar_benchmark_rag_escolar
            visto: dict = {}

            def espia(**kw: object) -> dict:
                visto.update(kw)
                return real(**kw)

            with patch.object(bench, "executar_benchmark_rag_escolar", espia):
                repetir_rodada_rag_escolar(caminho_runs=Path(tmp) / "runs.jsonl")
        self.assertEqual((visto["limite"], visto["k"], visto["nivel"]), (4, 3, 1))
        self.assertEqual((visto["disciplina"], visto["estrategia_query"]), ("Ciências", "barreira"))
        self.assertFalse(visto["salvar"])
        self.assertTrue(visto["gerar_resposta"])

    def test_busca_que_muda_e_acusada_e_as_questoes_sao_listadas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            runs = Path(tmp) / "runs.jsonl"
            _executar(tmp, limite=4)
            rodada = json.loads(runs.read_text(encoding="utf-8").splitlines()[-1])
            rodada["itens"][0]["chunk_ids"] = list(reversed(rodada["itens"][0]["chunk_ids"]))
            runs.write_text(json.dumps(rodada, ensure_ascii=False) + "\n", encoding="utf-8")
            with patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"):
                r = repetir_rodada_rag_escolar(caminho_runs=runs)
        self.assertEqual(r["trechos_identicos"], 3)
        self.assertFalse(r["busca_repete"])
        self.assertFalse(r["repete"])
        self.assertEqual(r["divergentes"], [{"id": rodada["itens"][0]["id"], "mudou": ["trechos"]}])

    def test_resposta_que_muda_com_a_busca_igual_nao_derruba_a_busca(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            runs = Path(tmp) / "runs.jsonl"
            _executar(tmp, limite=4)
            rodada = json.loads(runs.read_text(encoding="utf-8").splitlines()[-1])
            rodada["itens"][1]["resposta"] = "Outro texto, como um modelo que sorteia escreveria [T1]."
            rodada["itens"][1]["absteve"] = False
            rodada["itens"][1]["fidelidade_efetiva"] = 1.0
            runs.write_text(json.dumps(rodada, ensure_ascii=False) + "\n", encoding="utf-8")
            with patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"):
                r = repetir_rodada_rag_escolar(caminho_runs=runs)
        self.assertTrue(r["busca_repete"])
        self.assertFalse(r["geracao_repete"])
        self.assertFalse(r["repete"])
        self.assertEqual(r["respostas_identicas"], 3)
        self.assertLess(r["diferenca_fidelidade"]["media"], 0.0)
        self.assertIn("resposta", r["divergentes"][0]["mudou"])

    def test_rodada_so_de_busca_nao_compara_resposta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            _executar(tmp, limite=3, gerar_resposta=False)
            with patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"):
                r = repetir_rodada_rag_escolar(caminho_runs=Path(tmp) / "runs.jsonl")
        self.assertTrue(r["repete"])
        self.assertIsNone(r["respostas_identicas"])
        self.assertIsNone(r["geracao_repete"])
        self.assertIsNone(r["diferenca_fidelidade"])

    def test_prova_trocada_desde_a_referencia_vira_ressalva(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            runs = Path(tmp) / "runs.jsonl"
            _executar(tmp, limite=2)
            rodada = json.loads(runs.read_text(encoding="utf-8").splitlines()[-1])
            rodada["procedencia"]["dataset_sha256"] = "0" * 16
            runs.write_text(json.dumps(rodada, ensure_ascii=False) + "\n", encoding="utf-8")
            with patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"):
                r = repetir_rodada_rag_escolar(caminho_runs=runs)
        self.assertFalse(r["mesma_prova"])
        self.assertTrue(r["mesma_base"])

    def test_sem_rodada_ou_com_id_errado_nao_roda(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            with self.assertRaises(ValueError):
                repetir_rodada_rag_escolar(caminho_runs=Path(tmp) / "runs.jsonl")
            _executar(tmp, limite=2)
            with self.assertRaises(KeyError):
                repetir_rodada_rag_escolar("nao-existe", caminho_runs=Path(tmp) / "runs.jsonl")


class TestRotaDeRepeticao(unittest.TestCase):
    def _caminhos(self, tmp: str):
        return (
            patch.object(bench, "RUNS_RAG_ESCOLAR_PADRAO", Path(tmp) / "runs.jsonl"),
            patch.object(bench, "BASELINE_RAG_ESCOLAR_PADRAO", Path(tmp) / "base.json"),
            patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"),
        )

    def test_fastapi_422_sem_rodada_404_id_errado_200_com_rodada(self) -> None:
        if app is None:
            self.skipTest("FastAPI não disponível neste interpretador Python")
        from fastapi.testclient import TestClient

        client = TestClient(app)
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as pilha, _ambiente_extrativo():
            for p in self._caminhos(tmp):
                pilha.enter_context(p)
            pilha.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.assertEqual(client.post("/api/v1/eval/rag-escolar/repetir", json={}).status_code, 422)
            rodada = client.post("/api/v1/eval/rag-escolar/run", json={"metodo": "bm25", "limite": 3})
            run_id = rodada.json()["run_info"]["run_id"]
            self.assertIn("elos", rodada.json())
            self.assertEqual(client.post("/api/v1/eval/rag-escolar/repetir", json={"run_id": "x"}).status_code, 404)
            ok = client.post("/api/v1/eval/rag-escolar/repetir", json={"run_id": run_id})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual((ok.json()["comparadas"], ok.json()["trechos_identicos"]), (3, 3))

    def test_servidor_de_reserva_422_404_e_200(self) -> None:
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
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                return err.code, json.loads(err.read().decode("utf-8"))

        try:
            with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as pilha, _ambiente_extrativo():
                for p in self._caminhos(tmp):
                    pilha.enter_context(p)
                pilha.enter_context(contextlib.redirect_stdout(io.StringIO()))
                self.assertEqual(post("/api/v1/eval/rag-escolar/repetir", {})[0], 422)
                _, rodada = post("/api/v1/eval/rag-escolar/run", {"metodo": "bm25", "limite": 2})
                self.assertEqual(post("/api/v1/eval/rag-escolar/repetir", {"run_id": "x"})[0], 404)
                status, corpo = post("/api/v1/eval/rag-escolar/repetir", {"run_id": rodada["run_info"]["run_id"]})
                self.assertEqual((status, corpo["trechos_identicos"]), (200, 2))
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


class TestPerguntaDeCadaTela(unittest.TestCase):
    """Cada aba abre dizendo que pergunta responde e de onde vem o número."""

    def test_todas_as_abas_abrem_com_a_pergunta_e_a_origem(self) -> None:
        html = PLAYGROUND.read_text(encoding="utf-8")
        abas = re.findall(r'<section id="(tab-[a-z]+)" class="tab-panel[^"]*">\s*(<p class="screen-question">.*?</p>)?', html, flags=re.DOTALL)
        botoes = re.findall(r'class="tab-btn[^"]*" data-tab="([a-z]+)"', html)
        # o grupo "Verificações de qualidade" tem 22 botões (data-tab="b-...") que abrem uma área só, tab-bancada
        if re.search(r'data-tab="b-[a-z0-9-]+"', html):
            botoes.append("bancada")
        self.assertEqual(sorted(a for a, _ in abas), sorted(f"tab-{b}" for b in botoes))
        self.assertGreaterEqual(len(abas), 5)
        for aba, bloco in abas:
            with self.subTest(aba=aba):
                self.assertIn("Pergunta desta tela:", bloco)
                self.assertIn("De onde vem o número:", bloco)
                self.assertIn("?", bloco)


if __name__ == "__main__":
    unittest.main()
