"""Testes da aba "Arquitetura" (grafo dos agentes em LangGraph) e da aba "Grafo do código"
(módulos lidos com ast e camada de funções do grafo próprio)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
REPO_ROOT = BACKEND_DIR.parent
RAG_PACOTE_DIR = REPO_ROOT / "rag" / "iris-rag" / "pacote"
for p in (str(SRC_DIR), str(BACKEND_DIR), str(RAG_PACOTE_DIR), str(REPO_ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from iris.eval import arquitetura_langgraph as arq
from iris.eval import mapa_codigo
from iris.eval.mapa_codigo import carregar_funcoes, mapear_modulos
from iris.main import app

TEM_LANGGRAPH = arq.LANGGRAPH_DISPONIVEL


@contextlib.contextmanager
def _ambiente_extrativo():
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


def _sobrepoe(a: tuple, b: tuple) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@unittest.skipUnless(TEM_LANGGRAPH, "langgraph não instalado")
class TestCenariosDoGrafo(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with _ambiente_extrativo(), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.dados = arq.obter_arquitetura(recalcular=True)
        cls.por_id = {e["id"]: e for e in cls.dados["execucoes"]}

    def test_os_quatro_cenarios_rodam(self) -> None:
        self.assertTrue(self.dados["disponivel"])
        self.assertEqual(
            list(self.por_id), ["normal", "estragada_uma_vez", "estragada_sempre", "frase_de_gabarito", "retomada"]
        )
        for e in self.dados["execucoes"]:
            self.assertEqual(e["questoes"], 2, e["id"])
            self.assertEqual(len(e["pausas"]), 2, e["id"])

    def test_normal_aprova_de_primeira(self) -> None:
        e = self.por_id["normal"]
        self.assertEqual(e["voltas_ao_adaptador"], 0)
        self.assertEqual([r["resultado"] for r in e["resultados"]], ["aprovado", "aprovado"])
        self.assertEqual(e["chamadas_por_no"]["adaptador"], 2)
        self.assertFalse(any(p["com_alerta"] for p in e["pausas"]))

    def test_minuta_ruim_uma_vez_volta_uma_vez_e_aprova(self) -> None:
        e = self.por_id["estragada_uma_vez"]
        self.assertEqual([r["voltas_auditor"] for r in e["resultados"]], [1, 1])
        self.assertEqual([r["tentativas_do_adaptador"] for r in e["resultados"]], [2, 2])
        self.assertEqual([r["resultado"] for r in e["resultados"]], ["aprovado", "aprovado"])

    def test_minuta_ruim_sempre_para_no_limite_e_usa_a_reserva(self) -> None:
        e = self.por_id["estragada_sempre"]
        limite = self.dados["limite_voltas"]
        self.assertEqual([r["voltas_auditor"] for r in e["resultados"]], [limite, limite])
        self.assertEqual([r["tentativas_do_adaptador"] for r in e["resultados"]], [limite + 1, limite + 1])
        self.assertEqual([r["resultado"] for r in e["resultados"]], ["reserva", "reserva"])
        self.assertTrue(all(p["com_alerta"] for p in e["pausas"]))
        self.assertEqual(e["chamadas_por_no"]["saida_de_reserva"], 2)

    def test_frase_de_gabarito_e_barrada_pelo_proprio_adaptador_antes_do_auditor(self) -> None:
        e = self.por_id["frase_de_gabarito"]
        self.assertEqual(e["barradas_pelo_adaptador"], e["questoes"])
        self.assertEqual(e["voltas_ao_adaptador"], 0)  # o Auditor não chegou a ver a frase
        for outro in ("normal", "estragada_uma_vez", "estragada_sempre", "retomada"):
            self.assertEqual(self.por_id[outro]["barradas_pelo_adaptador"], 0, outro)

    def test_retomada_nao_refaz_o_extrator(self) -> None:
        e = self.por_id["retomada"]
        self.assertEqual(e["falha"]["proximo_no_salvo"], ["adaptador"])
        self.assertEqual(e["chamadas_por_no"]["extrator"], e["questoes"])
        self.assertEqual(e["chamadas_por_no"]["adaptador"], e["questoes"] + 1)
        self.assertEqual([r["resultado"] for r in e["resultados"]], ["aprovado", "aprovado"])

    def test_nome_plantado_nao_fica_em_estado_salvo_e_bruto_e_descartado(self) -> None:
        for e in self.dados["execucoes"]:
            self.assertFalse(e["nome_plantado_no_estado_salvo"], e["id"])
            self.assertTrue(e["texto_bruto_descartado"], e["id"])
            self.assertGreaterEqual(e["n_pii_removidos"], 1, e["id"])

    def test_repetir_da_o_mesmo_caminho(self) -> None:
        with _ambiente_extrativo(), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            de_novo = arq.executar_cenarios()
        for a, b in zip(self.dados["execucoes"], de_novo["execucoes"]):
            self.assertEqual([p["no"] for p in a["caminho"]], [p["no"] for p in b["caminho"]], a["id"])


@unittest.skipUnless(TEM_LANGGRAPH, "langgraph não instalado")
class TestDesenhoDoGrafo(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.g = arq.descrever_grafo(arq.construir_grafo())

    def test_todos_os_nos_e_setas_do_langgraph_estao_no_desenho(self) -> None:
        ids = {n["id"] for n in self.g["nos"]}
        self.assertEqual(ids, {n["id"] for n in arq.NOS} | {"__start__", "__end__"})
        self.assertEqual(len(self.g["setas"]), 17)
        self.assertEqual(sum(s["condicional"] for s in self.g["setas"]), 5)
        self.assertEqual(sum(s["volta"] for s in self.g["setas"]), 2)

    def test_nenhuma_caixa_se_sobrepoe_e_todas_cabem(self) -> None:
        for nome, d in self.g["desenhos"].items():
            caixas = [(n["x"], n["y"], n["x"] + n["l"], n["y"] + n["a"]) for n in d["nos"]]
            for i, a in enumerate(caixas):
                self.assertTrue(a[0] >= 0 and a[1] >= 0 and a[2] <= d["largura"] and a[3] <= d["altura"], nome)
                for b in caixas[i + 1 :]:
                    self.assertFalse(_sobrepoe(a, b), (nome, a, b))

    def test_nome_cabe_dentro_da_caixa_nos_dois_desenhos(self) -> None:
        for nome, d in self.g["desenhos"].items():
            m = d["medidas"]
            for n in d["nos"]:
                self.assertLessEqual(len(n["linhas"]), 2, (nome, n["id"]))
                for linha in n["linhas"]:
                    # 0,56 da altura da letra é a largura média de uma letra da fonte do painel
                    self.assertLessEqual(len(linha) * m["fonte_no"] * 0.56, n["l"] - 8, (nome, n["id"], linha))
                altura_texto = len(n["linhas"]) * m["fonte_no"] * 1.15
                self.assertLessEqual(altura_texto, n["a"] - 4, (nome, n["id"]))

    def test_setas_e_rotulos_cabem_e_rotulo_nao_cai_em_caixa(self) -> None:
        for nome, d in self.g["desenhos"].items():
            m = d["medidas"]
            caixas = [(n["x"], n["y"], n["x"] + n["l"], n["y"] + n["a"]) for n in d["nos"]]
            for s in d["setas"]:
                for x, y in s["pontos"]:
                    self.assertTrue(0 <= x <= d["largura"] and 0 <= y <= d["altura"], (nome, s))
                if not s["rotulo"]:
                    continue
                pos, largura = s["rotulo_pos"], len(s["rotulo"]) * m["letra_rotulo"]
                x0 = {"end": pos["x"] - largura, "middle": pos["x"] - largura / 2, "start": pos["x"]}[pos["ancora"]]
                caixa_texto = (x0, pos["y"] - 10, x0 + largura, pos["y"] + 2)
                self.assertGreaterEqual(x0, 0, (nome, s["rotulo"]))
                self.assertLessEqual(x0 + largura, d["largura"], (nome, s["rotulo"]))
                for c in caixas:
                    self.assertFalse(_sobrepoe(caixa_texto, c), (nome, s["rotulo"], c))

    def test_calhas_de_volta_nao_se_cruzam(self) -> None:
        for d in self.g["desenhos"].values():
            calhas = [s["pontos"][1][0] for s in d["setas"] if s["volta"]]
            self.assertEqual(len(set(calhas)), len(calhas))

    def test_desenho_estreito_e_mais_estreito_e_quebra_os_nomes_longos(self) -> None:
        largo, estreito = self.g["desenhos"]["largo"], self.g["desenhos"]["estreito"]
        self.assertLess(estreito["largura"], 0.75 * largo["largura"])
        self.assertTrue(any(len(n["linhas"]) == 2 for n in estreito["nos"]))
        self.assertTrue(all(len(n["linhas"]) == 1 for n in largo["nos"]))

    def test_no_sem_posicao_e_acusado(self) -> None:
        with patch.dict(arq.GRADE, {}, clear=False):
            del arq.GRADE["auditor"]
            with self.assertRaises(ValueError):
                arq.descrever_grafo(arq.construir_grafo())


MATERIAL = (
    "Atividade de Ciências - 6º ano B\nAluno: Fulano Ficticio\nStudent: Beltrana Inventada\n\n"
    "Questão 1: Leia o texto sobre o ciclo da água, identifique suas etapas principais e explique o papel da "
    "evaporação.\n\nQuestão 2: Observe a tabela, calcule a média e justifique a resposta.\n"
)


@unittest.skipUnless(TEM_LANGGRAPH, "langgraph não instalado")
class TestExecucaoComMaterial(unittest.TestCase):
    def _iniciar(self, texto: str = MATERIAL) -> dict:
        with _ambiente_extrativo(), contextlib.redirect_stderr(io.StringIO()):
            return arq.iniciar_execucao(texto)

    def test_para_em_cada_questao_e_guarda_a_decisao(self) -> None:
        r = self._iniciar()
        self.assertEqual((r["estado"], r["pausa"]["numero"], r["pausa"]["de"]), ("pausado", 1, 2))
        with _ambiente_extrativo(), contextlib.redirect_stderr(io.StringIO()):
            r = arq.retomar_execucao(r["thread_id"], "editou", "Texto editado pela professora.")
            self.assertEqual((r["estado"], r["pausa"]["numero"]), ("pausado", 2))
            r = arq.retomar_execucao(r["thread_id"], "aceitou")
        self.assertEqual(r["estado"], "concluido")
        self.assertEqual([x["decisao_professora"] for x in r["resultados"]], ["editou", "aceitou"])
        with self.assertRaises(ValueError):
            arq.retomar_execucao(r["thread_id"], "aceitou")

    def test_nome_com_rotulo_reconhecido_sai_e_o_outro_e_apontado(self) -> None:
        r = self._iniciar()
        self.assertNotIn("Fulano", r["texto_guardado"])
        self.assertIn("Beltrana", r["texto_guardado"])
        self.assertEqual(r["sinais_de_dado_restante"], ["Student: Beltrana Inventada"])
        self.assertTrue(r["texto_bruto_descartado"])

    def test_entrada_invalida(self) -> None:
        with self.assertRaises(ValueError):
            self._iniciar("curto")
        with self.assertRaises(KeyError):
            arq.retomar_execucao("nao-existe", "aceitou")
        r = self._iniciar()
        with self.assertRaises(ValueError):
            arq.retomar_execucao(r["thread_id"], "talvez")
        with self.assertRaises(ValueError):
            arq.retomar_execucao(r["thread_id"], "editou", "   ")

    def test_guarda_no_maximo_as_sessoes_mais_recentes(self) -> None:
        with patch.object(arq, "MAX_SESSOES", 2):
            ids = [self._iniciar()["thread_id"] for _ in range(3)]
        self.assertNotIn(ids[0], arq._SESSOES)
        self.assertIn(ids[2], arq._SESSOES)

    def test_rotas_fastapi(self) -> None:
        if app is None:
            self.skipTest("FastAPI não disponível neste interpretador Python")
        from fastapi.testclient import TestClient

        client = TestClient(app)
        with _ambiente_extrativo(), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(client.post("/api/v1/eval/arquitetura-langgraph/executar", json={"texto": "x"}).status_code, 422)
            r = client.post("/api/v1/eval/arquitetura-langgraph/executar", json={"texto": MATERIAL, "nivel": 1})
            self.assertEqual(r.status_code, 200)
            tid = r.json()["thread_id"]
            self.assertEqual(
                client.post("/api/v1/eval/arquitetura-langgraph/retomar", json={"thread_id": "x", "decisao": "aceitou"}).status_code,
                404,
            )
            ok = client.post("/api/v1/eval/arquitetura-langgraph/retomar", json={"thread_id": tid, "decisao": "aceitou"})
        self.assertEqual((ok.status_code, ok.json()["pausa"]["numero"]), (200, 2))


class TestSemLangGraph(unittest.TestCase):
    def test_sem_a_biblioteca_a_aba_diz_como_instalar(self) -> None:
        with patch.object(arq, "LANGGRAPH_DISPONIVEL", False), patch.object(arq, "ERRO_IMPORTACAO", "No module named 'langgraph'"):
            r = arq.obter_arquitetura(recalcular=True)
            with self.assertRaises(RuntimeError):
                arq.construir_grafo()
        self.assertFalse(r["disponivel"])
        self.assertIn("--group grafo", r["como_instalar"])
        arq._CACHE.clear()


class TestMapaDeModulos(unittest.TestCase):
    def _pacote(self, tmp: Path) -> tuple[Path, Path]:
        raiz = tmp / "src" / "iris"
        (raiz / "sub").mkdir(parents=True)
        (raiz / "security").mkdir()
        testes = tmp / "tests"
        testes.mkdir()
        (raiz / "__init__.py").write_text("", encoding="utf-8")
        (raiz / "sub" / "__init__.py").write_text("", encoding="utf-8")
        (raiz / "security" / "__init__.py").write_text("", encoding="utf-8")
        (raiz / "security" / "pii_scrubber.py").write_text("def sanitize_pii(t):\n    return t, 0\n", encoding="utf-8")
        (raiz / "sub" / "a.py").write_text("from . import b\nfrom iris.security.pii_scrubber import sanitize_pii\n\ndef f():\n    return 1\n", encoding="utf-8")
        (raiz / "sub" / "b.py").write_text("class B:\n    pass\n", encoding="utf-8")
        (raiz / "sub" / "c.py").write_text("def g():\n    import iris.sub.b\n    return 2\n", encoding="utf-8")
        (testes / "test_a.py").write_text("from iris.sub import a\n", encoding="utf-8")
        return raiz, testes

    def test_importacoes_relativas_absolutas_e_dentro_de_funcao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz, testes = self._pacote(Path(tmp))
            m = mapear_modulos(raiz, testes)
        por = {x["id"]: x for x in m["modulos"]}
        self.assertEqual(por["iris.sub.a"]["importa"], ["iris.security.pii_scrubber", "iris.sub.b"])
        self.assertEqual(por["iris.sub.c"]["importa"], ["iris.sub.b"])
        self.assertEqual(por["iris.sub.b"]["importado_por"], ["iris.sub.a", "iris.sub.c"])

    def test_sem_teste_e_dado_pessoal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz, testes = self._pacote(Path(tmp))
            m = mapear_modulos(raiz, testes)
        por = {x["id"]: x for x in m["modulos"]}
        self.assertEqual(por["iris.sub.a"]["testado_por"], ["test_a.py"])
        self.assertIn("iris.sub.c", m["sem_teste"])
        self.assertNotIn("iris.sub.a", m["sem_teste"])
        self.assertNotIn("iris.sub", m["sem_teste"])  # __init__ vazio não conta
        self.assertEqual(por["iris.security.pii_scrubber"]["pii"], "define")
        self.assertEqual(por["iris.sub.a"]["pii"], "usa")
        self.assertIsNone(por["iris.sub.b"]["pii"])

    def test_arquivo_com_erro_de_sintaxe_e_registrado_e_nao_derruba(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz, testes = self._pacote(Path(tmp))
            (raiz / "sub" / "quebrado.py").write_text("def (:\n", encoding="utf-8")
            m = mapear_modulos(raiz, testes)
        self.assertEqual(m["erros_de_leitura"], ["quebrado.py: SyntaxError"])
        self.assertNotIn("iris.sub.quebrado", {x["id"] for x in m["modulos"]})

    def test_codigo_real_do_backend(self) -> None:
        m = mapear_modulos()
        ids = {x["id"] for x in m["modulos"]}
        self.assertIn("iris.security.pii_scrubber", ids)
        self.assertEqual(m["erros_de_leitura"], [])
        self.assertEqual(sum(len(p["modulos"]) for p in m["pacotes"]), len(m["modulos"]))
        por = {x["id"]: x for x in m["modulos"]}
        self.assertEqual(por["iris.security.pii_scrubber"]["pii"], "define")
        self.assertIn("test_ataque_pii_e_portao.py", por["iris.eval.ataque_pii"]["testado_por"])
        self.assertIn("iris.eval.mapa_codigo", por["iris.main"]["importa"])


class TestCamadaDeFuncoes(unittest.TestCase):
    """O grafo de funções próprio (rag/iris-rag/bancada/mapa/grafo_funcoes.py), que substituiu o GitNexus."""

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        caminho = REPO_ROOT / "rag" / "iris-rag" / "bancada" / "mapa" / "grafo_funcoes.py"
        spec = importlib.util.spec_from_file_location("grafo_funcoes_teste", caminho)
        cls.gf = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(cls.gf)  # type: ignore[union-attr]

    def _repo(self, tmp: str) -> Path:
        raiz = Path(tmp)
        pac = raiz / "backend" / "src" / "iris" / "seguranca"
        pac.mkdir(parents=True)
        (raiz / "backend" / "src" / "iris" / "__init__.py").write_text("", encoding="utf-8")
        (pac / "__init__.py").write_text("", encoding="utf-8")
        (pac / "limpa.py").write_text(
            "def limpar(t):\n    return t.strip()\n\n\nclass Auditor:\n    def auditar(self, t):\n"
            "        return self.passo(limpar(t))\n\n    def passo(self, t):\n        return t\n", encoding="utf-8")
        (pac / "usa.py").write_text(
            "from iris.seguranca.limpa import Auditor, limpar\nfrom iris.seguranca import limpa as lp\n\n\n"
            "def preparar(t):\n    return limpar(t)\n\n\n"
            "def entrada(t):\n    a = Auditor()\n    return a.auditar(lp.limpar(preparar(t)))\n", encoding="utf-8")
        testes = raiz / "backend" / "tests"
        testes.mkdir(parents=True)
        (testes / "test_x.py").write_text(
            "from iris.seguranca.usa import entrada\n\n\ndef test_entrada():\n    entrada(' a ')\n", encoding="utf-8")
        return raiz

    def test_funcoes_chamadas_e_teste(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = self.gf.construir(self._repo(tmp))
        nomes = {s["qual"]: i for i, s in enumerate(d["simbolos"])}
        self.assertEqual(set(nomes), {"limpar", "Auditor", "Auditor.auditar", "Auditor.passo", "preparar", "entrada", "test_entrada"})
        ligacoes = {(d["simbolos"][a]["qual"], d["simbolos"][b]["qual"]) for a, b in d["chamadas"]}
        self.assertIn(("entrada", "limpar"), ligacoes)  # modulo.funcao (lp.limpar)
        self.assertIn(("preparar", "limpar"), ligacoes)  # nome importado
        self.assertIn(("entrada", "Auditor"), ligacoes)  # classe importada (construtor)
        self.assertIn(("Auditor.auditar", "Auditor.passo"), ligacoes)  # self.metodo
        self.assertIn(("Auditor.auditar", "limpar"), ligacoes)  # função do mesmo módulo
        self.assertIn(("test_entrada", "entrada"), ligacoes)
        self.assertTrue(d["simbolos"][nomes["test_entrada"]]["teste"])
        self.assertFalse(d["simbolos"][nomes["entrada"]]["teste"])
        self.assertEqual(d["metricas"]["chamadas"], len(d["chamadas"]))

    def test_comunidades_e_fluxos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = self.gf.construir(self._repo(tmp))
        self.assertTrue(d["comunidades"])
        self.assertTrue(all(0 <= c["coesao"] <= 1 for c in d["comunidades"]))
        fluxo = d["processos"][0]
        self.assertEqual(d["simbolos"][fluxo["passos"][0]]["qual"], "entrada")  # teste não é ponto de entrada
        self.assertGreaterEqual(len(fluxo["passos"]), 3)
        self.assertNotIn("GitNexus", d["ferramenta"])

    def test_leitura_pelo_backend_e_sem_arquivo_diz_como_gerar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "g.json"
            arquivo.write_text(json.dumps(self.gf.construir(self._repo(tmp))), encoding="utf-8")
            f = carregar_funcoes(arquivo)
            ausente = carregar_funcoes(Path(tmp) / "nao.json")
            ruim = Path(tmp) / "ruim.json"
            ruim.write_text("{", encoding="utf-8")
            ilegivel = carregar_funcoes(ruim)
        self.assertTrue(f["disponivel"])
        por = {s["nome"]: s for s in f["simbolos"]}
        self.assertGreaterEqual(por["entrada"]["chama"], 2)
        self.assertFalse(ausente["disponivel"])
        self.assertIn("make -C rag/iris-rag/pacote grafo", ausente["como_gerar"])
        self.assertFalse(ilegivel["disponivel"])


class TestRotasNovas(unittest.TestCase):
    def test_fastapi(self) -> None:
        if app is None:
            self.skipTest("FastAPI não disponível neste interpretador Python")
        from fastapi.testclient import TestClient

        client = TestClient(app)
        with tempfile.TemporaryDirectory() as tmp, patch.object(mapa_codigo, "FUNCOES_PADRAO", Path(tmp) / "nao.json"):
            m = client.get("/api/v1/eval/mapa-codigo")
        self.assertEqual(m.status_code, 200)
        self.assertGreater(m.json()["modulos"]["metricas"]["modulos"], 10)
        self.assertFalse(m.json()["funcoes"]["disponivel"])
        with _ambiente_extrativo(), contextlib.redirect_stderr(io.StringIO()):
            a = client.get("/api/v1/eval/arquitetura-langgraph")
        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.json()["disponivel"], TEM_LANGGRAPH)

    def test_servidor_de_reserva(self) -> None:
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
        try:
            with urllib.request.urlopen(url + "/api/v1/eval/mapa-codigo", timeout=60) as r:
                self.assertEqual(r.status, 200)
                self.assertIn("modulos", json.loads(r.read().decode("utf-8")))
            with (
                _ambiente_extrativo(),
                contextlib.redirect_stderr(io.StringIO()),
                urllib.request.urlopen(url + "/api/v1/eval/arquitetura-langgraph", timeout=120) as r,
            ):
                self.assertEqual(r.status, 200)
                self.assertIn("disponivel", json.loads(r.read().decode("utf-8")))
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
