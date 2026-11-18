"""Testes do protótipo em LangGraph (python -m unittest test_grafo, dentro de bancada/langgraph).

Três perguntas simples:
  1. o laço Auditor -> Adaptador respeita o limite de voltas?
  2. o grafo para mesmo na revisão da professora e só continua quando alguém responde?
  3. algum campo do estado (ou o que o checkpointer guardou) tem o nome ou o CPF plantado no material?
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import logging  # noqa: E402
import unittest  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.simplefilter("ignore")

import grafo_iris as G  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

logging.getLogger("iris").setLevel(logging.ERROR)
ECO = G.T.criar_cliente("eco")
M_FORCADO = G.MATERIAIS_FORCADOS[0]


def rodar(material: dict, modo: str | None = None, limite: int = G.LIMITE_VOLTAS, tid: str = "t"):
    saver = InMemorySaver()
    grafo = G.construir_grafo(limite, saver)
    cliente = G.ClienteForcado(ECO, modo) if modo else ECO
    rodada = G.rodar_material(grafo, material, cliente, tid)
    return grafo, saver, rodada


class TestLaco(unittest.TestCase):
    def test_limite_padrao_vai_para_reserva(self):
        grafo, _, r = rodar(M_FORCADO, "sempre")
        self.assertIsNone(r["erro"])
        final = G.historico(grafo, r["config"])[-1].values
        self.assertEqual(final["voltas_auditor"], G.LIMITE_VOLTAS)
        self.assertEqual(r["contexto"].chamadas["adaptador"], G.LIMITE_VOLTAS + 1)
        self.assertIn("saida_de_reserva", final["caminho"])
        self.assertEqual(final["resultados"][-1]["resultado"], "reserva")

    def test_limite_menor_e_respeitado(self):
        grafo, _, r = rodar(M_FORCADO, "sempre", limite=1)
        final = G.historico(grafo, r["config"])[-1].values
        self.assertEqual(final["voltas_auditor"], 1)
        self.assertEqual(r["contexto"].chamadas["adaptador"], 2)

    def test_uma_volta_basta_quando_o_adaptador_corrige(self):
        grafo, _, r = rodar(M_FORCADO, "uma_vez")
        final = G.historico(grafo, r["config"])[-1].values
        self.assertEqual(final["voltas_auditor"], 1)
        self.assertNotIn("saida_de_reserva", final["caminho"])
        self.assertEqual(final["resultados"][-1]["resultado"], "aprovado")
        self.assertNotIn(G.ClienteForcado.MARCA, final["texto_final"])


class TestPausaProfessora(unittest.TestCase):
    def test_para_na_revisao_e_so_segue_com_resposta(self):
        grafo = G.construir_grafo(G.LIMITE_VOLTAS, InMemorySaver())
        m = G.RP.MATERIAIS[0]
        ctx = G.preparar_contexto(m, ECO)
        cfg = {"configurable": {"thread_id": "pausa"}}
        saida = grafo.invoke({"material_id": m["material_id"], "caracteristica": G.CARACTERISTICA_PADRAO, "nivel": 2},
                             cfg, context=ctx)
        self.assertIn("__interrupt__", saida)
        self.assertEqual(grafo.get_state(cfg).next, ("revisao_professora",))
        self.assertNotIn("decisao_professora", {k for k, v in grafo.get_state(cfg).values.items() if v})
        saida = grafo.invoke(G.Command(resume={"decisao": "aceitou"}), cfg, context=ctx)
        estado = grafo.get_state(cfg).values
        self.assertEqual(estado["resultados"][0]["decisao_professora"], "aceitou")

    def test_toda_questao_passa_pela_professora(self):
        _, _, r = rodar(G.RP.MATERIAIS[2])
        self.assertIsNone(r["erro"])
        self.assertEqual(len(r["pausas"]), 3)
        self.assertTrue(all(p["parado_em"] == ["revisao_professora"] for p in r["pausas"]))


class TestSemDadoPessoal(unittest.TestCase):
    def _sem_pii(self, material: dict, tid: str):
        grafo, saver, r = rodar(material, tid=tid)
        self.assertIsNone(r["erro"])
        plantado = material["pii_plantado"]
        for snap in G.historico(grafo, r["config"]):
            for campo, valor in snap.values.items():
                texto = json.dumps(valor, ensure_ascii=False, default=str).casefold()
                for p in plantado:
                    self.assertNotIn(p.casefold(), texto, f"{p!r} no campo {campo!r} (passo {snap.metadata.get('step')})")
        bruto = G.bytes_do_checkpointer(saver, tid)
        for p in plantado:
            self.assertNotIn(p.encode(), bruto, f"{p!r} guardado no checkpointer")
        saver.delete_thread(tid)
        self.assertEqual(G.bytes_do_checkpointer(saver, tid), b"")

    def test_material_forcado_nome_e_cpf(self):
        self.assertIn("111.111.111-11", M_FORCADO["pii_plantado"])
        self._sem_pii(M_FORCADO, "pii-m4")

    def test_m1_e_m2(self):
        self._sem_pii(G.RP.MATERIAIS[0], "pii-m1")
        self._sem_pii(G.RP.MATERIAIS[1], "pii-m2")

    def test_m3_o_estado_nao_vaza_alem_do_filtro(self):
        # No M3 o filtro do grupo deixa passar um nome (achado das saídas 26 e 35). O teste confere que o
        # que chega ao estado é só o que o filtro deixou passar: o texto bruto nunca entra.
        m = G.RP.MATERIAIS[2]
        grafo, _, r = rodar(m, tid="pii-m3")
        final = G.historico(grafo, r["config"])[-1].values
        _, dados = G.RP.montar_arquivo(m)
        sanitizado, _ = G.sanitize_pii(dados.decode("utf-8"))
        vazou_no_filtro = [p for p in m["pii_plantado"] if p in sanitizado]
        vazou_no_estado = G.pii_em([json.dumps(final, ensure_ascii=False, default=str)], m["pii_plantado"])
        self.assertEqual(sorted(vazou_no_estado), sorted(vazou_no_filtro))
        self.assertFalse(any(k in final for k in ("texto_bruto", "dados", "nome_arquivo")))


if __name__ == "__main__":
    unittest.main()
