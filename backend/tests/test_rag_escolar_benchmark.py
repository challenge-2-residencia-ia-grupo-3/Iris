"""Testes da curadoria e do benchmark contextual do RAG sobre questões escolares (`questoes_escolares_v1.json`)."""
from __future__ import annotations

import os
import sys
import tempfile
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

from iris.eval.rag_escolar_benchmark import (
    ESTRATEGIAS_QUERY,
    avaliar_questao_no_rag,
    buscar_questao_curada_por_id,
    carregar_questoes_curadas,
    curar_dataset_escolar,
    curar_questao,
    executar_benchmark_rag_escolar,
    faixa_etaria_por_ano,
    limpar_enunciado_questao,
    listar_questoes_escolares,
    montar_consulta_rag_questao,
    obter_analytics_rag_escolar,
    porte_texto_por_tamanho,
)
from iris.main import (
    _handle_benchmark_escolar_list,
    _handle_rag_escolar_analytics,
    _handle_rag_test_question,
    _load_playground_html,
    app,
)
from iris.schemas.benchmark import BenchmarkQuestionItem


class TestCuradoriaQuestoesEscolares(unittest.TestCase):
    """Valida limpeza determinística e preservação das travas curriculares."""

    def test_limpeza_remove_disponivel_em_e_abnt(self) -> None:
        bruto = (
            "Texto sobre circulação medieval. Disponível em: www.elpais.com.br. "
            "Acesso em: 18 jun. 2018 (adaptado). Qual a conclusão?"
        )
        limpo, regras = limpar_enunciado_questao(bruto)
        self.assertNotIn("Disponível em:", limpo)
        self.assertNotIn("Acesso em:", limpo)
        self.assertIn("Texto sobre circulação medieval.", limpo)
        self.assertIn("Qual a conclusão?", limpo)
        self.assertIn("remocao_rodape_disponivel_em", regras)

        abnt = (
            "Os sindicatos mudaram no Brasil. DEL PRIORE, M.; VENÂNCIO, R. "
            "Uma história da vida rural no Brasil. Rio de Janeiro: Ediouro, 2006 (adaptado). "
            "Qual o objetivo?"
        )
        limpo_abnt, regras_abnt = limpar_enunciado_questao(abnt)
        self.assertNotIn("DEL PRIORE", limpo_abnt)
        self.assertIn("Qual o objetivo?", limpo_abnt)
        self.assertIn("remocao_referencia_abnt", regras_abnt)

    def test_curar_questao_preserva_original_se_trava_depender_do_trecho(self) -> None:
        item = BenchmarkQuestionItem(
            id="TEST-01",
            disciplina="História",
            ano_escolar="1ª série EM",
            habilidade_bncc="EM13CHS101",
            enunciado_original=(
                "Leia o texto histórico. Disponível em: https://exemplo.org/doc. Acesso em: 10 abr. 2020. "
                "Explique a fonte."
            ),
            conceitos_trava_curricular=["exemplo.org/doc", "fonte"],
            operacao_cognitiva="analisar",
            id_caracteristica_alvo="atencao_sustentada_textos_longos",
        )
        curado, regras = curar_questao(item)
        self.assertEqual(curado.enunciado_original, item.enunciado_original)
        self.assertEqual(regras, ["preservado_original_por_trava"])

    def test_curar_dataset_completo_em_memoria_mantem_136_itens_validos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "curado.json"
            resumo = curar_dataset_escolar(destino=destino, salvar=True)
            self.assertEqual(resumo["total"], 136)
            self.assertGreaterEqual(resumo["modificadas"], 30)
            self.assertTrue(destino.is_file())
            curadas = carregar_questoes_curadas(destino)
            self.assertEqual(len(curadas), 136)
            q = next(x for x in curadas if x.id == "ENEM2023-D1-09")
            self.assertNotIn("Disponível em:", q.enunciado_original)


class TestContextoEEstrategiasRagEscolar(unittest.TestCase):
    """Valida recortes contextuais, estratégias de query e execução no RAG."""

    def test_classificadores_e_listagem_filtrada(self) -> None:
        self.assertEqual(faixa_etaria_por_ano("7º ano EF"), "Ensino Fundamental II")
        self.assertEqual(faixa_etaria_por_ano("3ª série EM"), "Ensino Médio")
        self.assertEqual(porte_texto_por_tamanho("x" * 100), "curto")
        self.assertEqual(porte_texto_por_tamanho("x" * 400), "medio")
        self.assertEqual(porte_texto_por_tamanho("x" * 900), "longo")

        listagem = listar_questoes_escolares(faixa_etaria="Ensino Fundamental II", disciplina="Matemática")
        self.assertEqual(listagem["total_base"], 136)
        self.assertGreater(listagem["total_filtrado"], 0)
        self.assertTrue(all(i["faixa_etaria"] == "Ensino Fundamental II" for i in listagem["itens"]))
        self.assertTrue(all(i["disciplina"] == "Matemática" for i in listagem["itens"]))

    def test_tres_estrategias_de_consulta_produzem_queries_distintas(self) -> None:
        item = buscar_questao_curada_por_id("ENEM2023-D1-09")
        consultas = {
            est: montar_consulta_rag_questao(item, nivel=2, estrategia=est)
            for est in ESTRATEGIAS_QUERY
        }
        self.assertEqual(consultas["barreira"]["pergunta_adicional"], "")
        self.assertIn("Língua Portuguesa", consultas["contexto_pedagogico"]["pergunta_adicional"])
        self.assertNotIn("cavalo", consultas["contexto_pedagogico"]["consulta_composta"])
        self.assertIn("cavalo", consultas["enunciado_completo"]["consulta_composta"])

        with self.assertRaises(ValueError):
            montar_consulta_rag_questao(item, nivel=2, estrategia="inexistente")

    def test_avaliacao_unitaria_e_em_lote_no_rag_bm25(self) -> None:
        item = buscar_questao_curada_por_id("ENEM2023-D1-09")
        av = avaliar_questao_no_rag(
            item,
            nivel=2,
            metodo="bm25",
            k=3,
            estrategia_query="contexto_pedagogico",
            gerar_resposta=False,
        )
        self.assertEqual(av["metodo_efetivo"], "bm25")
        self.assertEqual(len(av["trechos_recuperados"]), 3)
        self.assertGreater(av["metricas"]["score_top1"], 0.0)
        self.assertEqual(av["metricas"]["aderencia_barreira_pct"], 100.0)
        self.assertGreaterEqual(av["metricas"]["texto_util_pct"], 0.0)
        self.assertLessEqual(av["metricas"]["texto_util_pct"], 100.0)
        self.assertGreaterEqual(av["metricas"]["trechos_sem_aviso_pct"], 0.0)

        with tempfile.TemporaryDirectory() as tmp:
            runs_path = Path(tmp) / "runs.jsonl"
            old_llm = os.environ.get("RAG_LLM")
            try:
                os.environ["RAG_LLM"] = "extractive"
                an = executar_benchmark_rag_escolar(
                    metodo="bm25",
                    nivel=2,
                    k=3,
                    estrategia_query="contexto_pedagogico",
                    gerar_resposta=True,
                    avaliador_geracao="lexico",
                    limite=4,
                    caminho_runs=runs_path,
                    salvar=True,
                )
            finally:
                if old_llm is None:
                    os.environ.pop("RAG_LLM", None)
                else:
                    os.environ["RAG_LLM"] = old_llm

            self.assertTrue(an["tem_rodada"])
            self.assertEqual(an["resumo_geral"]["total"], 4)
            self.assertGreater(len(an["por_faixa_etaria"]), 0)
            self.assertGreater(len(an["por_disciplina"]), 0)
            self.assertIsNotNone(an["resumo_geral"]["fidelidade_lexica_media"])

            recarregado = obter_analytics_rag_escolar(
                run_id=an["run_info"]["run_id"],
                caminho_runs=runs_path,
            )
            self.assertEqual(recarregado["resumo_geral"]["total"], 4)


class TestApiEPlaygroundEscolar(unittest.TestCase):
    """Valida handlers, rotas FastAPI e aba `Benchmark Escolar (136)` no HTML."""

    def test_handlers_e_html_escolar(self) -> None:
        html = _load_playground_html()
        self.assertIn("tab-escolar", html)
        self.assertIn("executarBateriaEscolarNoRag", html)

        lista = _handle_benchmark_escolar_list(disciplina="Ciências", limite=5)
        self.assertEqual(len(lista["itens"]), 5)
        self.assertEqual(lista["itens"][0]["disciplina"], "Ciências")

        res_q = _handle_rag_test_question(
            {
                "question_id": "ENEM2023-D1-09",
                "metodo": "bm25",
                "k": 3,
                "estrategia_query": "contexto_pedagogico",
            }
        )
        self.assertEqual(res_q["questao"]["id"], "ENEM2023-D1-09")
        self.assertEqual(len(res_q["trechos_recuperados"]), 3)

        with patch("iris.eval.rag_escolar_benchmark.RUNS_RAG_ESCOLAR_PADRAO", Path("/tmp/nao_existe_iris_runs.jsonl")):
            an = _handle_rag_escolar_analytics()
            self.assertFalse(an["tem_rodada"])

        with patch("iris.rag.bridge.carregar_modulos_rag") as mock_load:
            fake_ing = type("Ing", (), {"carregar_chunks": staticmethod(lambda: [])})()
            fake_ger = object()

            def fake_buscar(**kwargs):
                if kwargs["metodo"] == "qwen3+rerank50":
                    raise ModuleNotFoundError("No module named 'torch'")
                return []

            fake_con = type("Con", (), {"METODO_PADRAO": "bm25", "buscar": staticmethod(fake_buscar)})()
            mock_load.return_value = (fake_ing, fake_con, fake_ger)
            from iris.rag.bridge import buscar_evidencias_com_meta

            fb = buscar_evidencias_com_meta("teste", metodo="qwen3+rerank50")
            self.assertTrue(fb["fallback_aplicado"])
            self.assertEqual(fb["metodo_efetivo"], "bm25")
            self.assertIn("torch", fb["fallback_motivo"])

    def test_rotas_fastapi_escolar_quando_disponivel(self) -> None:
        if app is None:
            self.skipTest("FastAPI não disponível neste interpretador Python")
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r_list = client.get("/api/v1/benchmarks/escolar?disciplina=Matemática&limite=3")
        self.assertEqual(r_list.status_code, 200)
        body = r_list.json()
        self.assertEqual(len(body["itens"]), 3)

        r_one = client.post(
            "/api/v1/rag/test-question",
            json={"question_id": "ENEM2023-D1-09", "metodo": "bm25", "k": 2},
        )
        self.assertEqual(r_one.status_code, 200)
        self.assertEqual(len(r_one.json()["trechos_recuperados"]), 2)

        r_404 = client.post(
            "/api/v1/rag/test-question",
            json={"question_id": "ID-INEXISTENTE", "metodo": "bm25"},
        )
        self.assertEqual(r_404.status_code, 404)

    def test_rotas_stdlib_server_escolar(self) -> None:
        import contextlib
        import io
        import json
        import threading
        import urllib.request
        from http.server import HTTPServer

        from iris import main as iris_main

        capturado = {}

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
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"{base}/api/v1/benchmarks/escolar?faixa_etaria=Ensino+M%C3%A9dio&limite=2", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                dados = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(len(dados["itens"]), 2)
                self.assertEqual(dados["itens"][0]["faixa_etaria"], "Ensino Médio")

            req = urllib.request.Request(
                f"{base}/api/v1/rag/test-question",
                data=json.dumps({"question_id": "ENEM2023-D1-09", "metodo": "bm25", "k": 2}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                one = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(len(one["trechos_recuperados"]), 2)
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


class TestJuizClaudeSonnetV2(unittest.TestCase):
    """Valida o Juiz Claude Sonnet (Regra v2 + conferência literal + cache + leitura de .env)."""

    def test_traducao_ingles_portugues_apoiada_e_conferencia_literal(self) -> None:
        import json
        from iris.eval.sonnet_judge import julgar_resposta_sonnet

        trechos = [
            {
                "ref": "T1",
                "chunk_id": "nceo_2026#01",
                "titulo": "Extended Time: Research (NCEO)",
                "pagina": 4,
                "idioma": "en",
                "tipo_evidencia": "revisao",
                "nao_usar_para": None,
                "trecho": (
                    "Three studies showed the positive effects of extended time for high school "
                    "students with attention-deficit/hyperactivity disorder (ADHD)."
                ),
            }
        ]
        resposta_llama3 = (
            "Três estudos demonstraram efeitos positivos do tempo adicional para estudantes "
            "do ensino médio com TDAH [T1]."
        )

        def fake_sonnet_ok(modelo: str, sistema: str, prompt: str, temperature: float):
            saida = {
                "frases": [
                    {
                        "n": 1,
                        "tipo": "conteudo",
                        "veredito": "apoiada",
                        "trecho": "T1",
                        "citacao": "Three studies showed the positive effects of extended time for high school students",
                        "outro_trecho": None,
                        "rotulo_errado": False,
                        "motivo": "Tradução fiel do trecho em inglês T1.",
                    }
                ],
                "responde": "sim",
                "motivo_responde": "Responde diretamente com base na revisão NCEO.",
                "abstencao": None,
                "trecho_abstencao": None,
                "citacao_abstencao": None,
            }
            return json.dumps(saida, ensure_ascii=False), {"modelo": modelo, "input_tokens": 300, "output_tokens": 80}

        ver = julgar_resposta_sonnet(
            pergunta="Tempo extra funciona para TDAH?",
            trechos=trechos,
            resposta=resposta_llama3,
            usar_cache=False,
            chamar_api_fn=fake_sonnet_ok,
        )
        self.assertEqual(ver["fidelidade_sonnet"], 1.0)
        self.assertEqual(ver["relevancia_sonnet"], 1.0)
        self.assertTrue(ver["frases"][0]["citacao_verificada"])
        self.assertEqual(ver["frases"][0]["comum"], "apoiada")

        # Agora simula uma citação inventada que NÃO existe literalmente em T1 -> deve ser rejeitada mecanicamente
        def fake_sonnet_citacao_falsa(modelo: str, sistema: str, prompt: str, temperature: float):
            saida = {
                "frases": [
                    {
                        "n": 1,
                        "tipo": "conteudo",
                        "veredito": "apoiada",
                        "trecho": "T1",
                        "citacao": "Passagem inventada que nao consta no documento original",
                        "outro_trecho": None,
                        "rotulo_errado": False,
                        "motivo": "Suposta citação.",
                    }
                ],
                "responde": "sim",
                "motivo_responde": "Ok",
                "abstencao": None,
            }
            return json.dumps(saida, ensure_ascii=False), {"modelo": modelo}

        ver_rej = julgar_resposta_sonnet(
            pergunta="Tempo extra funciona para TDAH?",
            trechos=trechos,
            resposta=resposta_llama3,
            usar_cache=False,
            chamar_api_fn=fake_sonnet_citacao_falsa,
        )
        self.assertEqual(ver_rej["frases"][0]["comum"], "rejeitado")
        self.assertFalse(ver_rej["frases"][0]["citacao_verificada"])
        self.assertEqual(ver_rej["fidelidade_sonnet"], 0.0)

    def test_integracao_avaliar_questao_no_rag_com_sonnet_mock(self) -> None:
        item = buscar_questao_curada_por_id("ENEM2023-D1-09")
        fake_veredito = {
            "disponivel": True,
            "avaliador": "claude_sonnet",
            "modelo": "claude-sonnet-4-20250514",
            "n_juizes": 1,
            "cache_hit": True,
            "latencia_ms": 12.0,
            "recusou": False,
            "responde": {"A": "sim", "B": "sim"},
            "motivo_responde": "Atende à barreira funcional da questão.",
            "fidelidade_sonnet": 1.0,
            "fidelidade_sonnet_bruta": 1.0,
            "relevancia_sonnet": 1.0,
            "resumo_frases": {"apoiada": 2, "parcial": 0, "nao_apoiada": 0, "total_conteudo": 2},
            "frases": [],
        }
        old_llm = os.environ.get("RAG_LLM")
        try:
            os.environ["RAG_LLM"] = "extractive"
            with patch("iris.eval.rag_escolar_benchmark.julgar_resposta_sonnet", return_value=fake_veredito):
                av = avaliar_questao_no_rag(
                    item,
                    nivel=2,
                    metodo="bm25",
                    k=3,
                    gerar_resposta=True,
                    avaliador_geracao="sonnet",
                )
        finally:
            if old_llm is None:
                os.environ.pop("RAG_LLM", None)
            else:
                os.environ["RAG_LLM"] = old_llm

        self.assertEqual(av["metricas"]["avaliador_fidelidade"], "claude_sonnet")
        self.assertEqual(av["metricas"]["fidelidade_sonnet"], 1.0)
        self.assertEqual(av["metricas"]["fidelidade_efetiva"], 1.0)
        self.assertIsNotNone(av["juiz_sonnet"])


class TestProgressoRagEscolar(unittest.TestCase):
    def test_on_step_e_arquivo_de_log_progresso(self) -> None:
        from iris.eval import rag_escolar_benchmark as mod

        steps: list[dict[str, Any]] = []
        logs: list[str] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "rag_escolar_progress.log"
            with patch.object(mod, "PROGRESSO_RAG_ESCOLAR_LOG", log_path):
                res = mod.executar_benchmark_rag_escolar(
                    metodo="bm25",
                    nivel=2,
                    k=3,
                    gerar_resposta=False,
                    limite=1,
                    salvar=False,
                    progresso=logs.append,
                    on_step=steps.append,
                )

            self.assertTrue(res["tem_rodada"])
            self.assertGreaterEqual(len(steps), 2)
            self.assertEqual(steps[-1]["atual"], 1)
            self.assertEqual(steps[-1]["total"], 1)
            self.assertEqual(steps[-1]["etapa"], "Concluída questão")
            self.assertGreaterEqual(len(logs), 2)
            self.assertTrue(log_path.exists())
            conteudo_log = log_path.read_text(encoding="utf-8")
            self.assertIn("[1/1]", conteudo_log)

    def test_endpoint_progress_rag_escolar(self) -> None:
        from iris.main import _handle_rag_escolar_progress, create_app

        estado = _handle_rag_escolar_progress()
        for chave in ("running", "atual", "total", "questao_atual", "etapa", "tempo_decorrido_s", "log_linhas"):
            self.assertIn(chave, estado)

        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("FastAPI TestClient não disponível")

        client = TestClient(create_app())
        resp = client.get("/api/v1/eval/rag-escolar/progress")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("running", body)
        self.assertIn("log_linhas", body)


if __name__ == "__main__":
    unittest.main()
