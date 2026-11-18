"""Avaliar uma frase com um clique, às cegas (tela Juízes x pessoas): amostra, cegueira, arquivo que só cresce."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.eval import avaliacao_humana as ah
from iris.main import app

PLAYGROUND = SRC_DIR / "iris" / "static" / "playground.html"

# O texto dos trechos como os juízes leram (base de 1.083) fica fora do git, porque leva trecho de documento sem
# licença aberta. Onde ele não existe (no CI, por exemplo, que monta a base atual, já maior), os testes usam uma base
# de mentira com os mesmos identificadores: amostra, cegueira, arquivo e concordância não dependem do texto. Só o
# teste que confere o texto literal é pulado, dizendo por quê.
_BASE_FALSA: tempfile.TemporaryDirectory | None = None
_PATCH_BASE = None


def _base_julgada_disponivel() -> bool:
    try:
        ah.arquivo_de_trechos()
        return True
    except RuntimeError:
        return False


def setUpModule() -> None:
    global _BASE_FALSA, _PATCH_BASE
    if _base_julgada_disponivel():
        return
    medidas = json.loads(ah.MEDIDAS.read_text(encoding="utf-8"))["geradores"]
    ids = sorted({cid for g in medidas.values() for r in g.values() for cid in (r.get("fontes") or [])})
    _BASE_FALSA = tempfile.TemporaryDirectory()
    falsa = Path(_BASE_FALSA.name) / "chunks_julgados.jsonl"
    falsa.write_text("".join(json.dumps({"chunk_id": c, "texto": f"texto de teste do trecho {c}", "doc_id": "teste"}) + "\n"
                             for c in ids), encoding="utf-8")
    _PATCH_BASE = patch.object(ah, "BASE_JULGADA", falsa)
    _PATCH_BASE.start()
    ah._dados.cache_clear()


def tearDownModule() -> None:
    if _PATCH_BASE is not None:
        _PATCH_BASE.stop()
        ah._dados.cache_clear()
    if _BASE_FALSA is not None:
        _BASE_FALSA.cleanup()


class ComArquivoTemporario(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.arquivo = Path(self._tmp.name) / "rotulos.jsonl"
        self._patch = patch.object(ah, "ROTULOS", self.arquivo)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()


class TestAmostraECegueira(ComArquivoTemporario):
    def test_amostra_tem_os_estratos_esperados(self) -> None:
        a = ah.amostra()
        self.assertEqual(len(a["uids"]), 86)
        self.assertEqual(len(set(a["uids"])), 86)
        e = a["estratos"]
        self.assertEqual((e["dividida"]["na_amostra"], e["dois_contra_um"]["na_amostra"], e["unanime_nao"]["na_amostra"]),
                         (19, 17, 10))
        self.assertEqual((e["unanime_sustenta"]["total"], e["unanime_sustenta"]["na_amostra"]), (316, 40))
        self.assertEqual(ah.amostra()["uids"], a["uids"])  # fixa: semente

    def test_frases_e_trechos_sao_os_que_os_juizes_viram(self) -> None:
        if _BASE_FALSA is not None:
            self.skipTest("sem o texto dos trechos como os juízes leram (chunks_julgados.jsonl, fora do git)")
        passagens = json.loads((ah.PACOTE / "respostas_passagens_v2.json").read_text(encoding="utf-8"))
        textos = ah._dados()["textos"]
        achadas = 0
        for uid, f in ah._dados()["frases"].items():
            p = (passagens.get(f["gerador"], {}).get(f["qid"], {}).get("frases") or {}).get(str(f["n"])) or {}
            if p.get("trecho") and p.get("passagem"):
                cid = f["fontes"][int(p["trecho"]) - 1]
                norm = " ".join(p["passagem"].split()).lower()[:60]
                self.assertIn(norm, " ".join(textos[cid]["texto"].split()).lower(), uid)
                achadas += 1
        self.assertGreater(achadas, 200)

    def test_a_pessoa_nao_ve_o_voto_dos_juizes(self) -> None:
        r = ah.proxima("prof-A")
        texto = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("votos", r)
        for palavra in ("apoiada", "nao_apoiada", '"A"', '"B"', '"X"', "estrato", "dividida"):
            self.assertNotIn(palavra, texto)
        self.assertTrue(r["citacoes"])
        self.assertTrue(all(c["texto"] for c in r["citacoes"]))


class TestArquivoQueSoCresce(ComArquivoTemporario):
    def test_cada_clique_acrescenta_e_nao_muda_o_que_havia(self) -> None:
        primeira = ah.proxima("prof-A")
        ah.registrar(primeira["uid"], "sim", "prof-A", "está no T1")
        conteudo_antes = self.arquivo.read_text(encoding="utf-8")
        segunda = ah.proxima("prof-A")
        self.assertNotEqual(segunda["uid"], primeira["uid"])
        self.assertEqual(segunda["feitas"], 1)
        ah.registrar(segunda["uid"], "nao", "prof-A")
        depois = self.arquivo.read_text(encoding="utf-8")
        self.assertTrue(depois.startswith(conteudo_antes))
        self.assertEqual(len(depois.splitlines()), 2)
        # outra pessoa começa do zero
        self.assertEqual(ah.proxima("prof-B")["feitas"], 0)

    def test_entradas_invalidas(self) -> None:
        uid = ah.proxima("prof-A")["uid"]
        with self.assertRaises(ValueError):
            ah.registrar(uid, "talvez", "prof-A")
        with self.assertRaises(ValueError):
            ah.registrar(uid, "sim", "nome completo com espaço")
        with self.assertRaises(KeyError):
            ah.registrar("haiku-Q99-1", "sim", "prof-A")
        self.assertFalse(self.arquivo.exists())


class TestConcordancia(ComArquivoTemporario):
    def _rotular(self, quem: str, escolha) -> None:
        frases = ah._dados()["frases"]
        for uid in ah.amostra()["uids"][:30]:
            ah.registrar(uid, escolha(frases[uid]), quem)

    def test_abaixo_de_20_diz_quantas_faltam(self) -> None:
        for uid in ah.amostra()["uids"][:5]:
            ah.registrar(uid, "sim", "prof-A")
        r = ah.resumo()
        self.assertEqual(r["faltam"], 15)
        self.assertNotIn("juizes", r)

    def test_pessoa_igual_ao_veredito_final_da_kappa_1(self) -> None:
        self._rotular("prof-A", lambda f: "sim" if f["votos"]["final"] == 1 else "nao")
        r = ah.resumo()
        self.assertEqual(r["juizes"]["final"]["kappa"], 1.0)
        self.assertEqual(r["juizes"]["final"]["erro_caro"]["juiz_aprovou"], 0)

    def test_sabotagem_pessoa_contraria_derruba_a_concordancia(self) -> None:
        self._rotular("prof-A", lambda f: "nao" if f["votos"]["final"] == 1 else "sim")
        r = ah.resumo()
        self.assertLess(r["juizes"]["final"]["kappa"], 0)
        self.assertEqual(r["juizes"]["final"]["iguais"], 0)


class TestRotasEPainel(ComArquivoTemporario):
    def test_rotas_so_no_proprio_computador(self) -> None:
        from fastapi.testclient import TestClient

        local = TestClient(app, client=("127.0.0.1", 50000))
        r = local.get("/api/v1/eval/avaliacao-humana/proxima", params={"avaliador": "prof-A"})
        self.assertEqual(r.status_code, 200)
        uid = r.json()["uid"]
        g = local.post("/api/v1/eval/avaliacao-humana/rotulo", json={"uid": uid, "rotulo": "parcial", "avaliador": "prof-A"})
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["feitas"], 1)
        self.assertEqual(local.post("/api/v1/eval/avaliacao-humana/rotulo",
                                    json={"uid": uid, "rotulo": "x", "avaliador": "prof-A"}).status_code, 422)
        self.assertEqual(local.get("/api/v1/eval/avaliacao-humana/resumo").json()["avaliadas"], 1)
        de_fora = TestClient(app, client=("203.0.113.7", 50000))
        self.assertEqual(de_fora.get("/api/v1/eval/avaliacao-humana/proxima", params={"avaliador": "x"}).status_code, 403)

    def test_caixa_na_tela_juizes_x_pessoas(self) -> None:
        html = PLAYGROUND.read_text(encoding="utf-8")
        self.assertIn('id="aval-bloco"', html)
        self.assertIn("sid === 'q-juiz'", html)


if __name__ == "__main__":
    unittest.main()
