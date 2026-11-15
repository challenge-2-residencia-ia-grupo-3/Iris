"""Testes do ataque de dado pessoal ao removedor `sanitize_pii` e do portão (aprovado, aviso, reprovado)
do Benchmark Escolar."""
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

from iris.eval import ataque_pii
from iris.eval import rag_escolar_benchmark as bench
from iris.eval.ataque_pii import (
    CONTROLES,
    NOME_ROTULO,
    POSICOES,
    REPETICOES,
    TIPOS,
    executar_ataque_pii,
    gerar_casos,
    montar_material,
    obter_ataque_pii,
    vazou,
    wilson,
)
from iris.eval.rag_escolar_benchmark import (
    avaliar_portao,
    comparar_com_linha_de_base,
    executar_benchmark_rag_escolar,
)
from iris.main import app
from iris.security.pii_scrubber import sanitize_pii

TOTAL_CASOS = len(TIPOS) * len(NOME_ROTULO) * len(POSICOES) * REPETICOES


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


def _nao_remove_nada(texto: str) -> tuple[str, int]:
    return texto, 0


def _remove_tudo(texto: str) -> tuple[str, int]:
    return "[REMOVIDO]", 1


class TestRegraDeVazamento(unittest.TestCase):
    FUNDO = "Atividade de Ciências\nQuestão 1: explique a evaporação em 2020."

    def test_dado_inteiro_na_saida_vazou_e_dado_trocado_por_marcador_nao(self) -> None:
        self.assertTrue(vazou("Fulano Ficticio", "nome_estudante", "Aluno: Fulano Ficticio", self.FUNDO))
        self.assertFalse(vazou("Fulano Ficticio", "nome_estudante", "Aluno: [ESTUDANTE]", self.FUNDO))

    def test_so_o_sobrenome_ainda_identifica(self) -> None:
        self.assertTrue(vazou("Fulano Ficticio", "nome_estudante", "Aluno: [ESTUDANTE] Ficticio", self.FUNDO))

    def test_acento_e_caixa_nao_escondem_o_nome(self) -> None:
        self.assertTrue(vazou("Tomé Imaginário", "nome_com_acento", "aluno TOME IMAGINARIO", self.FUNDO))

    def test_palavra_que_ja_estava_no_enunciado_nao_conta(self) -> None:
        self.assertFalse(vazou("Atividade Ciências", "nome_estudante", "[ESTUDANTE]\n" + self.FUNDO, self.FUNDO))

    def test_documento_com_outra_pontuacao_ainda_vazou(self) -> None:
        self.assertTrue(vazou("000.123.456-78", "cpf_pontuado", "CPF 00012345678", self.FUNDO))
        self.assertFalse(vazou("000.123.456-78", "cpf_pontuado", "CPF [CPF]", self.FUNDO))

    def test_sobra_curta_de_digitos_nao_identifica(self) -> None:
        self.assertFalse(vazou("00012345678", "cpf_sem_pontuacao", "CPF: 000[TELEFONE]", self.FUNDO))

    def test_telefone_sem_o_ddd_inventado_ainda_vazou(self) -> None:
        self.assertTrue(vazou("(00) 91234-5678", "telefone", "ligar para 91234-5678", self.FUNDO))

    def test_numero_do_proprio_enunciado_nao_conta_como_vazamento(self) -> None:
        # O RG fictício contém, por acaso, os 7 dígitos de um número que já estava no enunciado.
        fundo = "Questão 3: a cidade tem 1250000 habitantes."
        self.assertFalse(vazou("12.500.001-2", "rg", "RG: [REMOVIDO]\n" + fundo, fundo))
        self.assertTrue(vazou("12.500.001-2", "rg", "RG: 12.500.001-2\n" + fundo, fundo))

    def test_email_pelo_nome_antes_da_arroba(self) -> None:
        self.assertTrue(vazou("fulano.teste12@exemplo.test", "email", "contato: fulano.teste12 arroba", self.FUNDO))
        self.assertFalse(vazou("fulano.teste12@exemplo.test", "email", "contato: [EMAIL]", self.FUNDO))


class TestCasosDoAtaque(unittest.TestCase):
    def test_todos_os_cruzamentos_e_a_mesma_semente_da_os_mesmos_casos(self) -> None:
        a, b = gerar_casos(), gerar_casos()
        self.assertEqual(len(a), TOTAL_CASOS)
        self.assertEqual([c["texto"] for c in a], [c["texto"] for c in b])
        self.assertNotEqual([c["texto"] for c in a], [c["texto"] for c in gerar_casos(semente=1)])
        self.assertEqual(len({c["id"] for c in a}), TOTAL_CASOS)

    def test_o_dado_esta_no_material_e_o_enunciado_tambem(self) -> None:
        for caso in gerar_casos():
            self.assertIn(caso["valor"], caso["texto"])
            self.assertIn("ciclo da água", caso["texto"])

    def test_valores_sao_ficticios_por_construcao(self) -> None:
        for caso in gerar_casos():
            if caso["tipo"] == "email":
                self.assertTrue(caso["valor"].endswith("@exemplo.test"))
            if caso["tipo"] == "telefone":
                self.assertTrue(caso["valor"].startswith("(00)"))
            if caso["tipo"].startswith("cpf"):
                self.assertTrue(caso["valor"].replace(".", "").startswith("000"))

    def test_posicao_desconhecida_e_recusada(self) -> None:
        with self.assertRaises(ValueError):
            montar_material("email", "pt", "margem", "x@exemplo.test")


class TestExecucaoDoAtaque(unittest.TestCase):
    def test_removedor_que_nao_remove_nada_vaza_tudo_e_nao_apaga_controle(self) -> None:
        r = executar_ataque_pii(sanitizar=_nao_remove_nada, salvar=False, formatos=())
        self.assertEqual(r["geral"]["vazou"], TOTAL_CASOS)
        self.assertEqual(r["geral"]["taxa_pct"], 100.0)
        self.assertEqual(r["controles"]["apagou_conteudo"], 0)

    def test_removedor_que_apaga_tudo_nao_vaza_nada_mas_apaga_todos_os_controles(self) -> None:
        r = executar_ataque_pii(sanitizar=_remove_tudo, salvar=False, formatos=())
        self.assertEqual(r["geral"]["vazou"], 0)
        self.assertEqual(r["controles"]["apagou_conteudo"], len(CONTROLES))
        self.assertEqual(r["exemplos"], [])

    def test_as_contagens_fecham(self) -> None:
        r = executar_ataque_pii(salvar=False, formatos=())
        self.assertEqual(r["geral"]["total"], TOTAL_CASOS)
        self.assertEqual(r["prometidos"]["total"] + r["nao_prometidos"]["total"], TOTAL_CASOS)
        self.assertEqual(r["prometidos"]["vazou"] + r["nao_prometidos"]["vazou"], r["geral"]["vazou"])
        self.assertEqual(sum(t["vazou"] for t in r["por_tipo"].values()), r["geral"]["vazou"])
        self.assertEqual(sum(x["vazou"] for x in r["por_rotulo"].values()), r["geral"]["vazou"])
        self.assertEqual(sum(x["vazou"] for x in r["por_posicao"].values()), r["geral"]["vazou"])
        for tipo in r["por_tipo"].values():
            self.assertEqual(sum(x["vazou"] for x in tipo["por_rotulo"].values()), tipo["vazou"])

    def test_removedor_do_grupo_cumpre_a_promessa_no_cenario_mais_simples(self) -> None:
        r = executar_ataque_pii(salvar=False, formatos=())
        self.assertEqual(r["prometidos_rotulo_pt"]["vazou"], 0)
        self.assertEqual(r["controles"]["apagou_conteudo"], 0)
        self.assertEqual(r["por_tipo"]["cpf_pontuado"]["vazou"], 0)
        self.assertEqual(r["por_tipo"]["email"]["vazou"], 0)

    def test_removedor_do_grupo_depende_do_rotulo_para_nome_e_matricula(self) -> None:
        r = executar_ataque_pii(salvar=False, formatos=())
        for tipo in ("nome_estudante", "matricula"):
            por_rotulo = r["por_tipo"][tipo]["por_rotulo"]
            self.assertEqual(por_rotulo["pt"]["vazou"], 0)
            self.assertEqual(por_rotulo["sem"]["vazou"], por_rotulo["sem"]["total"])
        self.assertEqual(r["nao_prometidos"]["vazou"], r["nao_prometidos"]["total"])

    def test_repetir_da_o_mesmo_resultado_e_a_mesma_assinatura(self) -> None:
        a, b = executar_ataque_pii(salvar=False, formatos=()), executar_ataque_pii(salvar=False, formatos=())
        self.assertEqual(a["assinatura_casos"], b["assinatura_casos"])
        self.assertEqual(a["geral"], b["geral"])
        self.assertEqual(a["por_tipo"], b["por_tipo"])

    def test_exemplos_nao_repetem_tipo_e_rotulo_e_trazem_so_a_linha(self) -> None:
        r = executar_ataque_pii(salvar=False, formatos=())
        pares = [(e["tipo"], e["rotulo"]) for e in r["exemplos"]]
        self.assertEqual(len(pares), len(set(pares)))
        self.assertTrue(all("\n" not in e["linha_da_saida"] for e in r["exemplos"]))

    def test_grava_e_le_o_ultimo_ataque(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "ataque.json"
            antes = obter_ataque_pii(destino)
            r = executar_ataque_pii(caminho_saida=destino, formatos=())
            depois = obter_ataque_pii(destino)
        self.assertFalse(antes["tem_ataque"])
        self.assertEqual(antes["total_casos"], TOTAL_CASOS)
        self.assertEqual(depois["ataque_id"], r["ataque_id"])

    def test_intervalo_de_wilson(self) -> None:
        self.assertIsNone(wilson(0, 0))
        self.assertEqual(wilson(0, 72)[0], 0.0)
        self.assertGreater(wilson(0, 72)[1], 0.0)
        baixo, alto = wilson(50, 100)
        self.assertTrue(baixo < 50.0 < alto)
        self.assertLess(wilson(500, 1000)[1] - wilson(500, 1000)[0], alto - baixo)

    def test_o_ataque_nao_altera_o_removedor(self) -> None:
        texto = "Aluno: Fulano Ficticio\nCPF: 000.123.456-78"
        antes = sanitize_pii(texto)
        executar_ataque_pii(salvar=False, formatos=())
        self.assertEqual(sanitize_pii(texto), antes)


def _rodada(run_id: str, fidelidades: list[float], **extra: object) -> dict:
    base = {
        "run_id": run_id,
        "timestamp_utc": "2026-11-15T00:00:00+00:00",
        "metodo_efetivo": "bm25",
        "estrategia_query": "contexto_pedagogico",
        "nivel": 2,
        "k": 5,
        "gerar_resposta": True,
        "avaliador_efetivo": "lexico_local",
        "filtros_execucao": {"disciplina": None, "limite": None},
        "procedencia": {"commit": "abc1234", "commit_com_alteracoes_locais": False, "dataset_sha256": "0123456789abcdef"},
        "itens": [
            {
                "id": f"Q{i}",
                "retornou_evidencia": True,
                "n_trechos": 5,
                "score_top1": 10.0,
                "segundos_busca": 0.05,
                "segundos_total": 0.1,
                "llm": "teste:fixo",
                "fidelidade_lexica": f,
                "fidelidade_efetiva": f,
                "relevancia_lexica": 0.5,
                "relevancia_efetiva": 0.5,
                "absteve": False,
            }
            for i, f in enumerate(fidelidades)
        ],
    }
    base.update(extra)
    return base


def _portao(atual: dict, base: dict | None) -> dict:
    return avaliar_portao(atual, comparar_com_linha_de_base(atual, base) if base else None)


class TestPortao(unittest.TestCase):
    BASE = [0.5, 0.6, 0.7, 0.8] * 10

    def test_sem_linha_de_base_nao_aprova_nem_reprova(self) -> None:
        self.assertEqual(_portao(_rodada("a", self.BASE), None)["veredito"], "sem_base")

    def test_a_propria_linha_de_base_e_referencia(self) -> None:
        base = _rodada("base", self.BASE)
        self.assertEqual(_portao(base, base)["veredito"], "referencia")

    def test_rodada_igual_e_aprovada(self) -> None:
        p = _portao(_rodada("nova", self.BASE), _rodada("base", self.BASE))
        self.assertEqual(p["veredito"], "aprovado")

    def test_fidelidade_pior_fora_do_intervalo_reprova(self) -> None:
        p = _portao(_rodada("nova", [0.1] * 40), _rodada("base", self.BASE))
        self.assertEqual(p["veredito"], "reprovado")
        self.assertFalse(p["lacre_rompido"])
        self.assertIn("Fidelidade piorou", p["motivos"][0])

    def test_fidelidade_melhor_e_aprovada(self) -> None:
        self.assertEqual(_portao(_rodada("nova", [0.95] * 40), _rodada("base", self.BASE))["veredito"], "aprovado")

    def test_prova_trocada_rompe_o_lacre_e_reprova(self) -> None:
        nova = _rodada("nova", self.BASE, procedencia={"commit": "abc1234", "dataset_sha256": "f" * 16})
        p = _portao(nova, _rodada("base", self.BASE))
        self.assertEqual(p["veredito"], "reprovado")
        self.assertTrue(p["lacre_rompido"])
        self.assertIn("Lacre rompido", p["motivos"][0])

    def test_outro_filtro_ou_outra_busca_e_aviso_de_nao_comparavel(self) -> None:
        base = _rodada("base", self.BASE)
        outro_filtro = _rodada("nova", self.BASE, filtros_execucao={"disciplina": "Matemática", "limite": None})
        outra_busca = _rodada("nova", self.BASE, metodo_efetivo="hibrido")
        for nova in (outro_filtro, outra_busca):
            p = _portao(nova, base)
            self.assertEqual(p["veredito"], "aviso")
            self.assertIn("Não comparável", p["motivos"][0])

    def test_latencia_90_vezes_maior_so_vira_nota_e_o_portao_aprova(self) -> None:
        nova = _rodada("nova", self.BASE)
        for item in nova["itens"]:
            item["segundos_total"] = 9.0
        base = _rodada("base", self.BASE)
        for i, item in enumerate(base["itens"]):
            item["segundos_total"] = 0.1 + (i % 4) * 0.01
        p = _portao(nova, base)
        self.assertEqual(p["veredito"], "aprovado")
        self.assertTrue(any("Latência total" in n and "mais lenta" in n for n in p["notas"]))
        self.assertFalse(any("Latência" in m for m in p["motivos"]))

    def test_codigo_com_alteracoes_locais_vira_nota_e_nao_aviso(self) -> None:
        nova = _rodada(
            "nova",
            self.BASE,
            procedencia={"commit": "abc1234", "commit_com_alteracoes_locais": True, "dataset_sha256": "0123456789abcdef"},
        )
        p = _portao(nova, _rodada("base", self.BASE))
        self.assertEqual(p["veredito"], "aprovado")
        self.assertIn("alterações locais", p["notas"][0])

    def test_reprovacao_traz_a_nota_de_procedencia_separada(self) -> None:
        nova = _rodada(
            "nova",
            [0.1] * 40,
            procedencia={"commit": "abc1234", "commit_com_alteracoes_locais": True, "dataset_sha256": "0123456789abcdef"},
        )
        p = _portao(nova, _rodada("base", self.BASE))
        self.assertEqual(p["veredito"], "reprovado")
        self.assertEqual(len(p["motivos"]), 1)
        self.assertEqual(len(p["notas"]), 1)

    def test_rodada_real_traz_o_portao_do_registro_a_tela(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            parametros = {
                "metodo": "bm25",
                "k": 3,
                "gerar_resposta": True,
                "avaliador_geracao": "lexico",
                "limite": 6,
                "caminho_runs": Path(tmp) / "runs.jsonl",
                "caminho_base": Path(tmp) / "base.json",
                "progresso": lambda _msg: None,
            }
            with patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "progress.log"):
                primeira = executar_benchmark_rag_escolar(**parametros)
                self.assertEqual(primeira["portao"]["veredito"], "sem_base")
                bench.definir_linha_de_base(
                    primeira["run_info"]["run_id"], caminho_runs=parametros["caminho_runs"], caminho_base=parametros["caminho_base"]
                )
                segunda = executar_benchmark_rag_escolar(**parametros)
                outra = executar_benchmark_rag_escolar(**{**parametros, "limite": 4})
        self.assertIn(segunda["portao"]["veredito"], {"aprovado", "aviso"})
        self.assertFalse(any("piorou" in m and "Latência" not in m for m in segunda["portao"]["motivos"]))
        self.assertEqual(outra["portao"]["veredito"], "aviso")


class TestRotasDoAtaque(unittest.TestCase):
    def test_fastapi_le_roda_e_le_de_novo(self) -> None:
        if app is None:
            self.skipTest("FastAPI não disponível neste interpretador Python")
        from fastapi.testclient import TestClient

        client = TestClient(app)
        with tempfile.TemporaryDirectory() as tmp, patch.object(ataque_pii, "ATAQUE_PII_PADRAO", Path(tmp) / "a.json"):
            antes = client.get("/api/v1/eval/ataque-pii")
            self.assertEqual((antes.status_code, antes.json()["tem_ataque"]), (200, False))
            rodou = client.post("/api/v1/eval/ataque-pii", json={})
            self.assertEqual((rodou.status_code, rodou.json()["geral"]["total"]), (200, TOTAL_CASOS))
            depois = client.get("/api/v1/eval/ataque-pii").json()
            self.assertEqual(depois["ataque_id"], rodou.json()["ataque_id"])

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
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/v1/eval/ataque-pii"
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
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                return err.code, json.loads(err.read().decode("utf-8"))

        try:
            with tempfile.TemporaryDirectory() as tmp, patch.object(ataque_pii, "ATAQUE_PII_PADRAO", Path(tmp) / "a.json"):
                status, antes = chamar(None)
                self.assertEqual((status, antes["tem_ataque"]), (200, False))
                status, rodou = chamar({})
                self.assertEqual((status, rodou["geral"]["total"]), (200, TOTAL_CASOS))
                status, depois = chamar(None)
                self.assertEqual((status, depois["ataque_id"]), (200, rodou["ataque_id"]))
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
