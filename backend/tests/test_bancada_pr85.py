"""O painel do PR 85 ("bancada") dentro do playground: as 22 abas, as rotas nos dois servidores e o que não pode quebrar.

O que estes testes guardam:
- a lista de abas do playground é a mesma do painel original (``SECOES`` em ``rag/iris-rag/pacote/painel.py``);
- as 7 abas do playground continuam lá (o grupo novo não tira nada);
- a página servida é a gerada pelo ``bancada.py``, com o modo embutido;
- os scripts da página do playground têm sintaxe válida (uma chave a mais derrubava todas as abas).
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import subprocess
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

from iris.eval import bancada_pr85
from iris.main import app

PLAYGROUND = SRC_DIR / "iris" / "static" / "playground.html"
ABAS_DO_IAN = ["benchmark", "escolar", "catalogo", "aovivo", "arquitetura", "codigo", "ferramentas"]


def _ids_das_abas() -> list[str]:
    return [i for _, itens in bancada_pr85.ABAS for i, _ in itens]


class TestListaDeAbas(unittest.TestCase):
    def test_sao_as_22_abas_do_painel_original_na_mesma_ordem(self) -> None:
        import painel  # rag/iris-rag/pacote/painel.py

        originais = [sid for _, itens in painel.SECOES for sid, _, _ in itens]
        self.assertEqual(len(originais), 22)
        self.assertEqual(_ids_das_abas(), originais)
        nomes = {sid: nome for _, itens in painel.SECOES for sid, nome, _ in itens}
        for _, itens in bancada_pr85.ABAS:
            for sid, nome in itens:
                self.assertEqual(nome, nomes[sid], sid)

    def test_playground_tem_um_botao_por_aba_e_mantem_as_abas_do_ian(self) -> None:
        html = PLAYGROUND.read_text(encoding="utf-8")
        botoes = re.findall(r'data-tab="b-([a-z0-9-]+)"', html)
        self.assertEqual(botoes, _ids_das_abas())
        for aba in ABAS_DO_IAN:
            self.assertIn(f'data-tab="{aba}"', html)
            self.assertIn(f'id="tab-{aba}"', html)
        self.assertIn('id="tab-bancada"', html)

    def test_cada_aba_tem_a_pergunta_da_tela(self) -> None:
        html = PLAYGROUND.read_text(encoding="utf-8")
        m = re.search(r"const BANCADA_PERGUNTAS = (\{.*?\});", html)
        self.assertIsNotNone(m)
        perguntas = json.loads(m.group(1))  # type: ignore[union-attr]
        self.assertEqual(sorted(perguntas), sorted(_ids_das_abas()))
        m2 = re.search(r"const BANCADA_EQUIVALENTES = (\{.*?\});", html)
        equivalentes = json.loads(m2.group(1))  # type: ignore[union-attr]
        self.assertTrue(set(equivalentes) <= set(_ids_das_abas()))
        for destino, _ in equivalentes.values():
            self.assertIn(destino, ABAS_DO_IAN)


@unittest.skipUnless(shutil.which("node"), "sem node: não dá para conferir a sintaxe do JavaScript")
class TestSintaxeDoPlayground(unittest.TestCase):
    def test_todos_os_scripts_da_pagina_tem_sintaxe_valida(self) -> None:
        html = PLAYGROUND.read_text(encoding="utf-8")
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertTrue(scripts)
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(scripts):
                arq = Path(tmp) / f"s{i}.js"
                arq.write_text(codigo, encoding="utf-8")
                r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True, check=False)
                self.assertEqual(r.returncode, 0, r.stderr[:500])


class TestGerador(unittest.TestCase):
    def test_gera_a_pagina_com_o_modo_embutido(self) -> None:
        r = bancada_pr85.gerar_pagina()
        self.assertTrue(r["ok"], r)
        self.assertIn("achados", r["resumo"])
        pagina = bancada_pr85.ler_pagina()
        self.assertIn("const DADOS=", pagina)
        self.assertIn("const EMB=", pagina)
        for sid in _ids_das_abas():
            self.assertIn(f"id=sec-{sid}", pagina)

    def test_sem_o_codigo_do_pr85_diz_o_que_falta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            falso = Path(tmp) / "bancada.py"
            with patch.object(bancada_pr85, "GERADOR", falso), patch.object(bancada_pr85, "PAGINA", Path(tmp) / "x.html"):
                self.assertFalse(bancada_pr85.disponivel())
                r = bancada_pr85.gerar_pagina()
                self.assertFalse(r["ok"])
                self.assertIn("não achei", r["erro"])
                self.assertIn("não foi gerada", bancada_pr85.ler_pagina())

    def test_descricao_para_o_menu(self) -> None:
        d = bancada_pr85.descrever()
        self.assertTrue(d["disponivel"])
        self.assertEqual(sum(len(g["abas"]) for g in d["abas"]), 22)


class TestRotas(unittest.TestCase):
    def test_rotas_fastapi(self) -> None:
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/v1/eval/bancada-pr85")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sum(len(g["abas"]) for g in r.json()["abas"]), 22)
        p = client.get("/bancada/?embutido=1")
        self.assertEqual(p.status_code, 200)
        self.assertIn("const EMB=", p.text)
        s = client.get("/bancada", follow_redirects=False)
        self.assertIn(s.status_code, (302, 307))
        self.assertEqual(s.headers["location"], "/bancada/")
        with tempfile.TemporaryDirectory() as tmp:
            st = Path(tmp) / "status.json"
            with patch.object(bancada_pr85, "STATUS", st):
                self.assertEqual(client.get("/bancada/status.json").status_code, 404)
                st.write_text('{"aprovado": true}', encoding="utf-8")
                self.assertEqual(client.get("/bancada/status.json").json(), {"aprovado": True})
        g = client.post("/api/v1/eval/bancada-pr85/gerar")
        self.assertEqual(g.status_code, 200)
        self.assertTrue(g.json()["ok"])

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
            with urllib.request.urlopen(url + "/api/v1/eval/bancada-pr85", timeout=30) as r:
                self.assertEqual(sum(len(g["abas"]) for g in json.loads(r.read())["abas"]), 22)
            with urllib.request.urlopen(url + "/bancada/?embutido=1", timeout=60) as r:
                self.assertIn("const EMB=", r.read().decode("utf-8"))
            with urllib.request.urlopen(url + "/bancada", timeout=60) as r:  # segue o redirecionamento
                self.assertTrue(r.geturl().endswith("/bancada/"))
            with tempfile.TemporaryDirectory() as tmp, patch.object(bancada_pr85, "STATUS", Path(tmp) / "s.json"):
                with self.assertRaises(urllib.error.HTTPError) as erro:
                    urllib.request.urlopen(url + "/bancada/status.json", timeout=30)
                self.assertEqual(erro.exception.code, 404)
            pedido = urllib.request.Request(url + "/api/v1/eval/bancada-pr85/gerar", data=b"{}", method="POST",
                                            headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(pedido, timeout=120) as r:
                self.assertTrue(json.loads(r.read())["ok"])
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
