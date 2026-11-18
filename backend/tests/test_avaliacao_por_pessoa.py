"""Avaliação por pessoa (issue #108): a tela abre em qualquer máquina e ganha a amostra de 50 adaptações.

Arquivo próprio, separado de ``test_avaliacao_humana.py`` (que o #114 altera). Nenhum teste escreve nos arquivos de
respostas de verdade: os caminhos são trocados por arquivos temporários.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from iris.eval import avaliacao_humana as ah


def _jsonl(caminho: Path, linhas: list[dict]) -> None:
    caminho.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in linhas), encoding="utf-8")


class TestTextosEmQualquerMaquina(unittest.TestCase):
    """Sem a base julgada e sem cópia dela, a base local entra trecho a trecho, conferida pela impressão digital."""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.imp = self.dir / "impressoes.json"
        self.chunks = self.dir / "chunks.jsonl"
        self.imp.write_text(json.dumps({"trechos": {
            "DOC#0001": ah.impressao("texto que o juiz leu"),
            "DOC#0002": ah.impressao("outro texto julgado"),
            "DOC#0003": ah.impressao("trecho que sumiu"),
        }}), encoding="utf-8")
        self.patches = [
            mock.patch.object(ah, "IMPRESSOES", self.imp),
            mock.patch.object(ah, "CHUNKS", self.chunks),
            mock.patch.object(ah, "arquivo_de_trechos", side_effect=RuntimeError("sem a base julgada")),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()

    def test_trecho_identico_entra_e_o_que_mudou_ou_sumiu_entra_sem_texto(self):
        _jsonl(self.chunks, [
            {"chunk_id": "DOC#0001", "texto": "texto que o juiz leu", "doc_id": "DOC"},
            {"chunk_id": "DOC#0002", "texto": "outro texto julgado, revisado depois", "doc_id": "DOC"},
        ])
        t = ah.textos_julgados()
        self.assertEqual(t["DOC#0001"]["texto"], "texto que o juiz leu")
        self.assertEqual(t["DOC#0002"]["texto"], "")  # nunca mostra um texto diferente do que o juiz viu
        self.assertEqual(t["DOC#0002"]["aviso"], ah.TEXTO_MUDOU)
        self.assertEqual(t["DOC#0003"]["texto"], "")

    def test_sem_impressoes_continua_parando_com_a_explicacao(self):
        self.imp.unlink()
        _jsonl(self.chunks, [{"chunk_id": "DOC#0001", "texto": "texto que o juiz leu"}])
        with self.assertRaises(RuntimeError):
            ah.textos_julgados()


class TestImpressoesVersionadas(unittest.TestCase):
    def test_cobrem_todo_trecho_citado_pelas_respostas_medidas(self):
        imp = json.loads(ah.IMPRESSOES.read_text(encoding="utf-8"))
        self.assertEqual(imp["base_julgada_sha256"], ah.HASH_BASE_JULGADA)
        medidas = json.loads(ah.MEDIDAS.read_text(encoding="utf-8"))["geradores"]
        citados = {c for g in ah.GERADORES for r in medidas[g].values() for c in (r.get("fontes") or []) if c}
        self.assertTrue(citados)
        self.assertEqual(citados - set(imp["trechos"]), set())

    def test_nao_levam_texto_de_trecho(self):
        imp = json.loads(ah.IMPRESSOES.read_text(encoding="utf-8"))
        self.assertTrue(all(len(v) == 16 and all(c in "0123456789abcdef" for c in v) for v in imp["trechos"].values()))


class TestFraseSemTextoParaLer(unittest.TestCase):
    """Frase cujos trechos chegam todos sem texto (licença restrita) sai da fila: a pessoa não teria o que conferir."""

    def test_so_aviso_de_licenca_nao_e_avaliavel(self):
        frase = {"texto": "Frase [T1].", "fontes": ["DOC#0001"]}
        cits = [{"ref": "T1", "chunk_id": "DOC#0001", "doc": "DOC", "aviso": "",
                 "texto": ah.AVISO_LICENCA + "; consultar o endereço de origem)"}]
        with mock.patch.object(ah, "_dados", return_value={"frases": {"u1": frase}}), \
             mock.patch.object(ah, "_citacoes", return_value=cits):
            self.assertFalse(ah.avaliavel("u1"))

    def test_um_trecho_com_texto_basta(self):
        frase = {"texto": "Frase [T1][T2].", "fontes": ["DOC#0001", "DOC#0002"]}
        cits = [{"ref": "T1", "chunk_id": "DOC#0001", "doc": "DOC", "aviso": "", "texto": ah.AVISO_LICENCA + ")"},
                {"ref": "T2", "chunk_id": "DOC#0002", "doc": "DOC", "aviso": "", "texto": "texto aberto"}]
        with mock.patch.object(ah, "_dados", return_value={"frases": {"u1": frase}}), \
             mock.patch.object(ah, "_citacoes", return_value=cits):
            self.assertTrue(ah.avaliavel("u1"))


class TestAmostraDeAdaptacoes(unittest.TestCase):
    def setUp(self) -> None:
        self.rotulos = Path(tempfile.mkdtemp()) / "rotulos.jsonl"
        self.p = mock.patch.object(ah, "ROTULOS_ADAPTACOES", self.rotulos)
        self.p.start()

    def tearDown(self) -> None:
        self.p.stop()

    def test_cinquenta_itens_nos_estratos_escritos_antes_do_sorteio(self):
        dados = json.loads(ah.AMOSTRA_ADAPTACOES.read_text(encoding="utf-8"))
        self.assertEqual(dados["semente"], 20261118)
        self.assertEqual(len(dados["itens"]), 50)
        self.assertEqual(len({i["uid"] for i in dados["itens"]}), 50)
        por_estrato = {e: v["na_amostra"] for e, v in dados["estratos"].items()}
        self.assertEqual(por_estrato["haiku_ruim"] + por_estrato["haiku_boa"], 25)
        self.assertEqual(por_estrato["llama_ruim"], 12)
        self.assertEqual(por_estrato["llama_boa"], 13)
        for i in dados["itens"]:
            self.assertEqual(i["juiz_boa"], ah.boa_adaptacao(i["juiz"]), i["uid"])

    def test_a_pessoa_nao_ve_quem_escreveu_nem_o_juiz(self):
        r = ah.proxima_adaptacao("prof-A")
        self.assertFalse(r["acabou"])
        for k in ah.ESCONDIDO_DA_PESSOA:
            self.assertNotIn(k, r)
        self.assertIn("adaptacao", r)
        self.assertIn("enunciado", r)
        self.assertEqual(set(r["perguntas"]), {"aplicou", "fora", "conteudo"})

    def test_registrar_so_acrescenta_e_avanca_a_fila(self):
        primeira = ah.proxima_adaptacao("prof-A")["uid"]
        r = ah.registrar_adaptacao(primeira, {"aplicou": "sim", "fora": "nao", "conteudo": "sim"}, "prof-A")
        self.assertEqual(r["feitas"], 1)
        self.assertNotEqual(r["uid"], primeira)
        ah.registrar_adaptacao(primeira, {"aplicou": "nao", "fora": "nao", "conteudo": "sim"}, "prof-A", "mudei de ideia")
        linhas = self.rotulos.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(linhas), 2)  # a primeira resposta continua no arquivo
        self.assertEqual(json.loads(linhas[0])["respostas"]["aplicou"], True)

    def test_entradas_invalidas(self):
        uid = ah.proxima_adaptacao("prof-A")["uid"]
        with self.assertRaises(ValueError):
            ah.registrar_adaptacao(uid, {"aplicou": "sim", "fora": "nao"}, "prof-A")
        with self.assertRaises(ValueError):
            ah.registrar_adaptacao(uid, {"aplicou": "talvez", "fora": "nao", "conteudo": "sim"}, "prof-A")
        with self.assertRaises(ValueError):
            ah.registrar_adaptacao(uid, {"aplicou": "sim", "fora": "nao", "conteudo": "sim"}, "nome com espaço")
        with self.assertRaises(KeyError):
            ah.registrar_adaptacao("adapt-99", {"aplicou": "sim", "fora": "nao", "conteudo": "sim"}, "prof-A")
        self.assertFalse(self.rotulos.exists())

    def _responder(self, avaliador: str, n: int, igual_ao_juiz: bool) -> None:
        itens = list(ah.adaptacoes().values())[:n]
        sn = lambda b: "sim" if b else "nao"
        for i in itens:
            j = i["juiz"]
            resp = {k: sn(j[k] if igual_ao_juiz else not j[k]) for k in ("aplicou", "fora", "conteudo")}
            ah.registrar_adaptacao(i["uid"], resp, avaliador)

    def test_concordancia_so_a_partir_de_20(self):
        self._responder("prof-A", 19, True)
        r = ah.resumo_adaptacoes()
        self.assertEqual(r["faltam"], 1)
        self.assertNotIn("medidas", r)

    def test_pessoa_igual_ao_juiz_da_kappa_1_e_nenhum_erro_caro(self):
        self._responder("prof-A", 50, True)
        r = ah.resumo_adaptacoes()
        self.assertEqual(r["medidas"]["boa"]["iguais"], 50)
        self.assertEqual(r["medidas"]["boa"]["kappa"], 1.0)
        self.assertEqual(r["erro_caro"]["juiz_aprovou"], 0)

    def test_sabotagem_pessoa_contraria_derruba_a_concordancia(self):
        self._responder("prof-A", 50, False)
        r = ah.resumo_adaptacoes()
        self.assertLess(r["medidas"]["aplicou"]["kappa"], 0)
        self.assertLess(r["medidas"]["boa"]["iguais"], 50)

    def test_empate_entre_duas_pessoas_vai_para_o_lado_rigido(self):
        itens = list(ah.adaptacoes().values())[:20]
        for i in itens:
            ah.registrar_adaptacao(i["uid"], {"aplicou": "sim", "fora": "nao", "conteudo": "sim"}, "prof-A")
            ah.registrar_adaptacao(i["uid"], {"aplicou": "nao", "fora": "sim", "conteudo": "nao"}, "prof-B")
        r = ah.resumo_adaptacoes()
        self.assertEqual(r["duas_pessoas_ou_mais"], 20)
        m = r["medidas"]["boa"]["matriz"]
        self.assertEqual(m["ambos_sim"] + m["so_pessoa_sim"], 0)  # empate = não boa


class TestRotasNovasSoNoProprioComputador(unittest.TestCase):
    def test_rotas_das_adaptacoes_recusam_quem_nao_e_local(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("requer FastAPI e httpx")
        from iris.main import create_app

        c = TestClient(create_app())  # o cliente de teste não vem de 127.0.0.1
        self.assertEqual(c.get("/api/v1/eval/avaliacao-humana/adaptacao/proxima?avaliador=prof-A").status_code, 403)
        self.assertEqual(c.get("/api/v1/eval/avaliacao-humana/adaptacao/resumo").status_code, 403)
        self.assertEqual(c.post("/api/v1/eval/avaliacao-humana/adaptacao/rotulo", json={}).status_code, 403)

    def test_rotas_das_adaptacoes_respondem_no_proprio_computador(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("requer FastAPI e httpx")
        from iris.main import create_app

        with tempfile.TemporaryDirectory() as d, mock.patch.object(ah, "ROTULOS_ADAPTACOES", Path(d) / "r.jsonl"):
            c = TestClient(create_app(), client=("127.0.0.1", 5000))
            r = c.get("/api/v1/eval/avaliacao-humana/adaptacao/proxima?avaliador=prof-A")
            self.assertEqual(r.status_code, 200, r.text)
            self.assertNotIn("juiz", r.json())
            r = c.post("/api/v1/eval/avaliacao-humana/adaptacao/rotulo",
                       json={"uid": r.json()["uid"], "avaliador": "prof-A",
                             "respostas": {"aplicou": "sim", "fora": "nao", "conteudo": "sim"}})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["feitas"], 1)
            ruim = c.post("/api/v1/eval/avaliacao-humana/adaptacao/rotulo",
                          json={"uid": "adapt-01", "avaliador": "prof-A", "respostas": {"aplicou": "sim"}})
            self.assertEqual(ruim.status_code, 422)


if __name__ == "__main__":
    unittest.main()
