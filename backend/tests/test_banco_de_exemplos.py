"""Banco de exemplos para o Adaptador (issues #108 e #133): colegas aprovam os exemplos na tela "Juízes x pessoas".

Nenhum teste escreve no arquivo de respostas de verdade: o caminho é trocado por um arquivo temporário.
"""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from iris.eval import avaliacao_humana as ah
from iris.main import app

PLAYGROUND = Path(ah.__file__).resolve().parents[1] / "static" / "playground.html"
SIM = {"aplicou": "sim", "fora": "nao", "conteudo": "sim", "modelo": "sim"}


class ComArquivoTemporario(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.arquivo = Path(self._tmp.name) / "rotulos-exemplos.jsonl"
        self._patch = mock.patch.object(ah, "ROTULOS_EXEMPLOS", self.arquivo)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()


class TestBancoEFila(ComArquivoTemporario):
    def test_banco_tem_os_exemplos_e_as_regras_do_nivel(self) -> None:
        itens = ah.exemplos()
        self.assertEqual(len(itens), 168)
        for item in itens.values():
            self.assertEqual(item["nivel"], 2)
            self.assertTrue(item["acoes"] and item["restricoes"] and item["enunciado"] and item["adaptacao"])

    def test_pessoa_nao_ve_quem_escreveu(self) -> None:
        r = ah.proxima_exemplo("prof-A")
        self.assertFalse(r["acabou"])
        self.assertNotIn("escritor", r)
        self.assertEqual(set(r["perguntas"]), {"aplicou", "fora", "conteudo", "modelo"})

    def test_exige_as_quatro_respostas(self) -> None:
        uid = ah.proxima_exemplo("prof-A")["uid"]
        with self.assertRaises(ValueError):
            ah.registrar_exemplo(uid, {"aplicou": "sim", "fora": "nao", "conteudo": "sim"}, "prof-A")
        with self.assertRaises(KeyError):
            ah.registrar_exemplo("EX-NAO-EXISTE", SIM, "prof-A")

    def test_arquivo_so_cresce_e_a_fila_anda(self) -> None:
        primeiro = ah.proxima_exemplo("prof-A")["uid"]
        r = ah.registrar_exemplo(primeiro, SIM, "prof-A", "ok")
        self.assertEqual(r["feitas"], 1)
        self.assertNotEqual(r["uid"], primeiro)
        ah.registrar_exemplo(r["uid"], SIM, "prof-A")
        self.assertEqual(len(self.arquivo.read_text(encoding="utf-8").splitlines()), 2)

    def test_proxima_prefere_o_exemplo_com_menos_avaliacoes(self) -> None:
        uid = ah.proxima_exemplo("prof-A")["uid"]
        ah.registrar_exemplo(uid, SIM, "prof-A")
        self.assertNotEqual(ah.proxima_exemplo("prof-B")["uid"], uid)


class TestOuro(ComArquivoTemporario):
    def test_vira_ouro_com_duas_aprovacoes_e_nenhuma_reprovacao(self) -> None:
        a, b, c = sorted(ah.exemplos())[:3]
        for pessoa in ("prof-A", "prof-B"):
            ah.registrar_exemplo(a, SIM, pessoa)
        ah.registrar_exemplo(b, SIM, "prof-A")
        ah.registrar_exemplo(b, {**SIM, "modelo": "nao"}, "prof-B")
        ah.registrar_exemplo(c, SIM, "prof-A")
        s = ah.resumo_exemplos()
        self.assertEqual(s["ids_ouro"], [a])
        self.assertEqual(s["reprovados"], 1)
        self.assertEqual(s["avaliados"], 3)
        self.assertEqual(s["pessoas"], 2)

    def test_dica_de_conteudo_reprova_mesmo_dizendo_que_serve_de_modelo(self) -> None:
        self.assertFalse(ah.exemplo_aprovado({"aplicou": True, "fora": True, "conteudo": True, "modelo": True}))
        self.assertTrue(ah.exemplo_aprovado({"aplicou": True, "fora": False, "conteudo": True, "modelo": True}))


class TestRotasETela(ComArquivoTemporario):
    def test_rotas_so_no_proprio_computador(self) -> None:
        local = TestClient(app, client=("127.0.0.1", 50000))
        r = local.get("/api/v1/eval/avaliacao-humana/exemplo/proxima", params={"avaliador": "prof-A"})
        self.assertEqual(r.status_code, 200)
        g = local.post("/api/v1/eval/avaliacao-humana/exemplo/rotulo",
                       json={"uid": r.json()["uid"], "respostas": SIM, "avaliador": "prof-A"})
        self.assertEqual(g.status_code, 200)
        self.assertEqual(local.get("/api/v1/eval/avaliacao-humana/exemplo/resumo").json()["avaliados"], 1)
        self.assertEqual(local.post("/api/v1/eval/avaliacao-humana/exemplo/rotulo",
                                    json={"uid": "EX-NAO-EXISTE", "respostas": SIM, "avaliador": "prof-A"}).status_code, 404)
        de_fora = TestClient(app, client=("203.0.113.7", 50000))
        self.assertEqual(de_fora.get("/api/v1/eval/avaliacao-humana/exemplo/proxima", params={"avaliador": "x"}).status_code, 403)

    def test_botao_na_tela(self) -> None:
        html = PLAYGROUND.read_text(encoding="utf-8")
        self.assertIn('id="avad-btn-exemplos"', html)
        self.assertIn("/api/v1/eval/avaliacao-humana/exemplo", html)


if __name__ == "__main__":
    unittest.main()


# Um exemplo ensina o Adaptador pelo que mostra: o que estiver nele aparece nas adaptações. Duas coisas que o banco
# anterior mostrava nos exemplos de ritmo e que não podem ir para a prova do aluno ficam fixadas aqui.
RECADO_AO_DOCENTE = re.compile(
    r"(?im)^[ \t>*_-]*(recomenda[çc][ãa]o|orienta[çc][ãa]o|nota|observa[çc][ãa]o|aviso|sugest[ãa]o)\s+"
    r"(pedag[óo]gica\s+)?(ao|à|a|para\s+o|para\s+a)\s+(docente|professora?|aplicadora?|mediadora?)\b")
LINHA_NUMERADA = r"(?m)^[ \t>*_]*{n}[.)][ \t*_]+\S"


class BancoSemDefeitoConhecido(unittest.TestCase):
    def test_nenhum_exemplo_traz_recado_ao_docente_dentro_da_questao(self) -> None:
        # a resposta do Adaptador tem um campo só e a exportação não altera o corpo: o recado sairia na prova do aluno
        com = [uid for uid, e in ah.exemplos().items() if RECADO_AO_DOCENTE.search(e["adaptacao"])]
        self.assertEqual(com, [])

    def test_a_regra_acusa_um_recado_plantado(self) -> None:
        self.assertTrue(RECADO_AO_DOCENTE.search("Calcule.\n\nRecomendação pedagógica ao docente: ofereça tempo flexível."))
        self.assertFalse(RECADO_AO_DOCENTE.search("A aluna entregou a redação ao professor."))

    def test_nenhum_exemplo_cria_item_1_sem_item_2(self) -> None:
        soltos = []
        for uid, e in ah.exemplos().items():
            tinha = re.search(LINHA_NUMERADA.format(n=1), e["enunciado"])
            criou_1 = re.search(LINHA_NUMERADA.format(n=1), e["adaptacao"])
            tem_2 = re.search(LINHA_NUMERADA.format(n=2), e["adaptacao"])
            if criou_1 and not tinha and not tem_2:
                soltos.append(uid)
        self.assertEqual(soltos, [])
