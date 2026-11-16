"""As verificações de qualidade (a bancada) dentro do playground: as 22 abas, as rotas nos dois servidores e o que não pode quebrar.

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

from iris.eval import verificacoes_qualidade as verificacoes
from iris.main import app

PLAYGROUND = SRC_DIR / "iris" / "static" / "playground.html"
# as abas do PR 87 (Ian); "codigo" era a aba feita no lote 5 e saiu em 16/11 (fica a da bancada, com o desenho)
ABAS_DO_IAN = ["benchmark", "escolar", "catalogo", "aovivo", "arquitetura", "ferramentas"]


def _ids_das_abas() -> list[str]:
    return [i for _, itens in verificacoes.ABAS for i, _ in itens]


class TestListaDeAbas(unittest.TestCase):
    def test_sao_as_22_abas_do_painel_original_na_mesma_ordem(self) -> None:
        import painel  # rag/iris-rag/pacote/painel.py

        originais = [sid for _, itens in painel.SECOES for sid, _, _ in itens]
        self.assertEqual(len(originais), 22)
        self.assertEqual(_ids_das_abas(), originais)
        nomes = {sid: nome for _, itens in painel.SECOES for sid, nome, _ in itens}
        for _, itens in verificacoes.ABAS:
            for sid, nome in itens:
                self.assertEqual(nome, nomes[sid], sid)

    def test_playground_tem_um_botao_por_aba_e_mantem_as_abas_do_ian(self) -> None:
        html = PLAYGROUND.read_text(encoding="utf-8")
        botoes = re.findall(r'data-tab="b-([a-z0-9-]+)"', html)
        no_menu = [i for _, itens in verificacoes.abas_no_menu() for i, _ in itens]
        self.assertEqual(botoes, no_menu)
        self.assertEqual(len(no_menu) + len(verificacoes.FORA_DO_MENU), 22)
        self.assertTrue(set(verificacoes.FORA_DO_MENU) <= set(_ids_das_abas()))
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
        r = verificacoes.gerar_pagina()
        self.assertTrue(r["ok"], r)
        self.assertIn("achados", r["resumo"])
        pagina = verificacoes.ler_pagina()
        self.assertIn("const DADOS=", pagina)
        self.assertIn("const EMB=", pagina)
        for sid in _ids_das_abas():
            self.assertIn(f"id=sec-{sid}", pagina)

    def test_sem_o_codigo_da_bancada_diz_o_que_falta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            falso = Path(tmp) / "bancada.py"
            with patch.object(verificacoes, "GERADOR", falso), patch.object(verificacoes, "PAGINA", Path(tmp) / "x.html"):
                self.assertFalse(verificacoes.disponivel())
                r = verificacoes.gerar_pagina()
                self.assertFalse(r["ok"])
                self.assertIn("não achei", r["erro"])
                self.assertIn("não foi gerada", verificacoes.ler_pagina())

    def test_descricao_para_o_menu(self) -> None:
        d = verificacoes.descrever()
        self.assertTrue(d["disponivel"])
        self.assertEqual(sum(len(g["abas"]) for g in d["abas"]) + len(d["fora_do_menu"]), 22)


class TestTema(unittest.TestCase):
    """Tema claro e escuro: o escuro da bancada não muda; o claro do playground não muda; o botão existe."""

    def test_cores_viram_variaveis_e_o_escuro_fica_igual(self) -> None:
        import colorsys

        import tema  # rag/iris-rag/pacote/tema.py

        (css, js), bloco = tema.tematizar([".a{color:#A68BFF;box-shadow:0 0 0 1px rgba(0,0,0,.45)}", "x='#fff';"])
        self.assertNotRegex(css + js, r"#[0-9a-fA-F]{3,6}\b")
        self.assertIn("var(--c-A68BFF)", css)
        self.assertIn("var(--c-FFFFFF)", js)
        escuro = bloco.split("html.tema-claro{")[0]
        self.assertIn("--c-A68BFF:#A68BFF", escuro)  # no escuro, cada variável vale a cor original
        self.assertIn("--c-rgba-0-0-0-p45:rgba(0,0,0,.45)", escuro)
        claro = bloco.split("html.tema-claro{")[1]
        self.assertIn("--c-A68BFF:#5A3FC0", claro)  # base: paleta do playground
        # fora da base, inverte a luminosidade e mantém o matiz: vermelho continua vermelho
        h = tema.claro_hex("D9A066")
        hue_antes = colorsys.rgb_to_hls(0xD9 / 255, 0xA0 / 255, 0x66 / 255)[0]
        hue_depois = colorsys.rgb_to_hls(*(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)))[0]
        self.assertAlmostEqual(hue_antes, hue_depois, delta=0.02)

    def test_pagina_gerada_nao_tem_cor_fixa_fora_das_variaveis(self) -> None:
        verificacoes.gerar_pagina()
        pagina = verificacoes.ler_pagina()
        estilo = pagina[pagina.index("<style>"):pagina.index("</style>")]
        estilo = estilo[estilo.rindex("@font-face"):]  # depois das fontes embutidas
        estilo = estilo[:estilo.index(":root{--c-")] + estilo[estilo.index("html.tema-claro body"):]
        self.assertNotRegex(estilo, r"#[0-9a-fA-F]{6}\b")
        self.assertIn("aplicarTema", pagina)

    def test_playground_tem_o_botao_e_o_tema_escuro_sem_mudar_o_claro(self) -> None:
        html = PLAYGROUND.read_text(encoding="utf-8")
        self.assertIn('id="tema-btn"', html)
        self.assertIn('html[data-tema="escuro"]', html)
        raiz = html[html.index(":root {"):html.index("}", html.index(":root {"))]
        # as cores que eram fixas viraram variáveis com o mesmo valor de antes, no tema claro
        for nome, valor in (("--barra-ok", "#1A6B42"), ("--barra-aviso", "#8C5200"), ("--barra-ruim", "#C93E22"),
                            ("--texto-ok", "#0f4f37"), ("--texto-ruim", "#7e2215"), ("--paper", "#eef3f3")):
            self.assertIn(f"{nome}: {valor};", raiz)
        self.assertNotIn("fill: '#1A6B42'", html)


class TestDesenhoIgualAoOriginal(unittest.TestCase):
    """Dentro do playground a tela tem de ficar com o mesmo desenho da bancada aberta sozinha."""

    def test_pontos_de_troca_descem_a_largura_do_menu_e_vh_vira_altura_do_playground(self) -> None:
        pagina = ("<style>@media (max-width:1180px){.c4{grid-column:span 12}}@media (max-width:900px){.a{x:1}}"
                  ".gx{height:calc(100vh - 150px)}.g canvas{height:58vh}</style>"
                  "<script>const DADOS={\"texto\":\"@media (max-width:1180px) 50vh\"};</script><script>x=1</script>")
        e = verificacoes.ajustar_para_embutir(pagina)
        self.assertIn("@media (max-width:936px)", e)  # 1180 - 244
        self.assertIn("@media (max-width:900px)", e)  # 900 e abaixo ficam
        self.assertNotRegex(e.split("<script>const DADOS=")[0], r"\d+vh")
        self.assertIn("calc(var(--vhp, 8px) * 100)", e)
        self.assertIn('"@media (max-width:1180px) 50vh"', e)  # os dados não são tocados

    def test_pagina_servida_embutida_e_solta(self) -> None:
        from fastapi.testclient import TestClient

        cliente = TestClient(app, client=("127.0.0.1", 50000))
        solta = cliente.get("/verificacoes/").text
        embutida = cliente.get("/verificacoes/?embutido=1").text
        self.assertIn("@media (max-width:1180px)", solta)
        self.assertNotIn("@media (max-width:1180px)", embutida)
        self.assertIn("@media (max-width:936px)", embutida)
        self.assertIn("bancadaAltura", embutida)  # a página informa a própria altura ao playground


class TestPresoNoTopo(unittest.TestCase):
    """Dentro do quadro, a faixa do topo e os detalhes ficam presos ao rolar, como na bancada aberta sozinha."""

    def test_os_dois_lados_da_conversa_existem(self) -> None:
        verificacoes.gerar_pagina()
        pagina = verificacoes.ler_pagina(embutido=True)
        self.assertIn("prenderNoTopo", pagina)
        self.assertIn("bancadaRolagem", pagina)
        html = PLAYGROUND.read_text(encoding="utf-8")
        self.assertIn("function informarRolagem", html)
        self.assertIn("bancadaRolagem", html)

    @unittest.skipUnless(shutil.which("node"), "sem node: não dá para conferir a sintaxe do JavaScript")
    def test_scripts_da_pagina_das_verificacoes_tem_sintaxe_valida(self) -> None:
        verificacoes.gerar_pagina()
        pagina = verificacoes.ler_pagina(embutido=True)
        scripts = re.findall(r"<script>(.*?)</script>", pagina, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 3)
        with tempfile.TemporaryDirectory() as tmp:
            for i, codigo in enumerate(scripts):
                arq = Path(tmp) / f"p{i}.js"
                arq.write_text(codigo, encoding="utf-8")
                r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True, check=False)
                self.assertEqual(r.returncode, 0, r.stderr[:500])


class TestPerfilRenomeadoNaoPassaCalado(unittest.TestCase):
    """H2: o rastro do pipeline só chama a etapa do perfil de "não implementada" quando a função não existe."""

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        caminho = REPO_ROOT / "rag" / "iris-rag" / "bancada" / "pipeline" / "rastro_pipeline.py"
        spec = importlib.util.spec_from_file_location("rastro_pipeline_teste", caminho)
        cls.rp = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(cls.rp)  # type: ignore[union-attr]

    def test_acha_a_funcao_no_nome_atual(self) -> None:
        self.assertTrue(callable(self.rp.carregar_validar_perfil()))

    def test_funcao_que_existe_com_outro_nome_de_modulo_vira_erro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "iris" / "perfil").mkdir(parents=True)
            (raiz / "iris" / "perfil" / "novo_nome.py").write_text("def validar_perfil(d):\n    return d\n", encoding="utf-8")
            with (
                patch.object(self.rp, "MODULOS_DO_PERFIL", ("iris.nao_existe_a", "iris.nao_existe_b")),
                self.assertRaises(ImportError) as erro,
            ):
                self.rp.carregar_validar_perfil(raiz)
            self.assertIn("novo_nome.py", str(erro.exception))

    def test_sem_a_funcao_em_lugar_nenhum_e_nao_implementada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(self.rp, "MODULOS_DO_PERFIL", ("iris.nao_existe_a",)):
            self.assertIsNone(self.rp.carregar_validar_perfil(Path(tmp)))


class TestMedirDeNovo(unittest.TestCase):
    def test_roda_o_alvo_verificar_sem_chave_e_com_provedor_deterministico(self) -> None:
        capturado: dict = {}

        def falso_run(cmd, **kw):
            capturado["cmd"], capturado["env"] = cmd, kw["env"]
            return subprocess.CompletedProcess(cmd, 0, stdout="reports/bancada.html: 1 KB, 10 achados (8 graves)\n", stderr="")

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "chave-de-teste"}), patch.object(verificacoes.subprocess, "run", falso_run):
            r = verificacoes.medir_de_novo()
        self.assertTrue(r["ok"])
        self.assertIn("10 achados", r["resumo"])
        self.assertIn("verificar", capturado["cmd"])
        self.assertIn("PROV=eco", capturado["cmd"])
        self.assertNotIn("ANTHROPIC_API_KEY", capturado["env"])

    def test_sem_make_diz_como_fazer(self) -> None:
        with patch("shutil.which", return_value=None):
            r = verificacoes.medir_de_novo()
        self.assertFalse(r["ok"])
        self.assertIn("make", r["erro"])


class TestRotas(unittest.TestCase):
    def test_rotas_fastapi(self) -> None:
        from fastapi.testclient import TestClient

        client = TestClient(app, client=("127.0.0.1", 50000))
        r = client.get("/api/v1/eval/verificacoes-qualidade")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sum(len(g["abas"]) for g in r.json()["abas"]), 16)
        p = client.get("/verificacoes/?embutido=1")
        self.assertEqual(p.status_code, 200)
        self.assertIn("const EMB=", p.text)
        s = client.get("/verificacoes", follow_redirects=False)
        self.assertIn(s.status_code, (302, 307))
        self.assertEqual(s.headers["location"], "/verificacoes/")
        with tempfile.TemporaryDirectory() as tmp:
            st = Path(tmp) / "status.json"
            with patch.object(verificacoes, "STATUS", st):
                self.assertEqual(client.get("/verificacoes/status.json").status_code, 404)
                st.write_text('{"aprovado": true}', encoding="utf-8")
                self.assertEqual(client.get("/verificacoes/status.json").json(), {"aprovado": True})
        g = client.post("/api/v1/eval/verificacoes-qualidade/gerar")
        self.assertEqual(g.status_code, 200)
        self.assertTrue(g.json()["ok"])

    def test_icone_da_iris_e_servido_e_usado_no_menu(self) -> None:
        from fastapi.testclient import TestClient

        r = TestClient(app).get("/favicon.png")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/png")
        self.assertEqual(r.content[:8], b"\x89PNG\r\n\x1a\n")
        html = PLAYGROUND.read_text(encoding="utf-8")
        self.assertIn('rel="icon"', html)
        self.assertIn('class="brand-icone" src="/favicon.png"', html)

    def test_so_o_proprio_computador_ve_as_telas(self) -> None:
        from fastapi.testclient import TestClient

        de_fora = TestClient(app, client=("203.0.113.7", 50000))
        for caminho in ("/verificacoes/", "/verificacoes/status.json", "/api/v1/eval/verificacoes-qualidade"):
            self.assertEqual(de_fora.get(caminho).status_code, 403, caminho)
        self.assertEqual(de_fora.post("/api/v1/eval/verificacoes-qualidade/medir").status_code, 403)
        self.assertEqual(de_fora.get("/api/v1/health").status_code, 200)  # o resto do painel segue aberto
        local = TestClient(app, client=("127.0.0.1", 50000))
        self.assertEqual(local.get("/api/v1/eval/verificacoes-qualidade", headers={"X-Forwarded-For": "203.0.113.7"}).status_code, 403)
        self.assertEqual(local.get("/api/v1/eval/verificacoes-qualidade").status_code, 200)

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
            with urllib.request.urlopen(url + "/api/v1/eval/verificacoes-qualidade", timeout=30) as r:
                self.assertEqual(sum(len(g["abas"]) for g in json.loads(r.read())["abas"]), 16)
            por_proxy = urllib.request.Request(url + "/verificacoes/", headers={"X-Forwarded-For": "203.0.113.7"})
            with self.assertRaises(urllib.error.HTTPError) as erro_proxy:
                urllib.request.urlopen(por_proxy, timeout=30)
            self.assertEqual(erro_proxy.exception.code, 403)
            with urllib.request.urlopen(url + "/verificacoes/?embutido=1", timeout=60) as r:
                self.assertIn("const EMB=", r.read().decode("utf-8"))
            with urllib.request.urlopen(url + "/verificacoes", timeout=60) as r:  # segue o redirecionamento
                self.assertTrue(r.geturl().endswith("/verificacoes/"))
            with tempfile.TemporaryDirectory() as tmp, patch.object(verificacoes, "STATUS", Path(tmp) / "s.json"):
                with self.assertRaises(urllib.error.HTTPError) as erro:
                    urllib.request.urlopen(url + "/verificacoes/status.json", timeout=30)
                self.assertEqual(erro.exception.code, 404)
            pedido = urllib.request.Request(url + "/api/v1/eval/verificacoes-qualidade/gerar", data=b"{}", method="POST",
                                            headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(pedido, timeout=120) as r:
                self.assertTrue(json.loads(r.read())["ok"])
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
