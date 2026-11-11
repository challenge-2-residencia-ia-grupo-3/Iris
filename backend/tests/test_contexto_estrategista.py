"""Testes da História 2.1.1 (Issue #16): mapeador de contexto do Agente Estrategista.

O mapeador é uma função pura; os testes usam buscas montadas à mão e uma busca real por palavra
(BM25), sem banco, sem modelo e sem LLM.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Garante que `backend/src` esteja no sys.path mesmo quando rodado via `python3 -m unittest`
BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.rag import (
    buscar_por_caracteristica_atomica,
    conferir_citacoes,
    garantir_chunks_locais,
    montar_contexto_estrategista,
)


def _trecho(cid: str, **extra) -> dict:
    base = {"chunk_id": cid, "doc": f"doc_{cid}", "titulo": f"Título {cid}", "pagina": "12",
            "url": f"https://exemplo.org/{cid}", "nao_usar_para": [], "nota_uso": "", "trecho": f"Texto do trecho {cid}."}
    return {**base, **extra}


def _busca(id_carac: str, trechos: list[dict]) -> dict:
    return {
        "id_caracteristica": id_carac,
        "nome_caracteristica": f"Nome de {id_carac}",
        "nivel_selecionado": 2,
        "diretriz_andaime": {"objetivo_andaime": "Objetivo.", "acoes_permitidas": ["Ação A"], "restricoes_escopo": ["Restrição R"]},
        "trechos_rag": trechos,
    }


class TestMapeadorDeContexto(unittest.TestCase):
    def test_numera_os_trechos_e_leva_a_referencia(self) -> None:
        r = montar_contexto_estrategista([_busca("carac_um", [_trecho("a"), _trecho("b")])])
        self.assertEqual([f["rotulo"] for f in r["fontes"]], ["T1", "T2"])
        self.assertIn("[T1] Título a, p. 12. Disponível em: https://exemplo.org/a", r["contexto"])
        self.assertIn("Texto do trecho b.", r["contexto"])
        self.assertIn("Ação A", r["contexto"])
        self.assertIn("Restrição R", r["contexto"])

    def test_trecho_repetido_entra_uma_vez_com_as_duas_caracteristicas(self) -> None:
        r = montar_contexto_estrategista(
            [_busca("carac_um", [_trecho("a"), _trecho("b")]), _busca("carac_dois", [_trecho("b"), _trecho("c")])]
        )
        self.assertEqual([f["chunk_id"] for f in r["fontes"]], ["a", "b", "c"])
        self.assertEqual(r["fontes"][1]["caracteristicas"], ["carac_um", "carac_dois"])
        self.assertEqual(r["contexto"].count("Texto do trecho b."), 1)
        self.assertEqual(r["caracteristicas"], ["carac_um", "carac_dois"])

    def test_aviso_de_uso_acompanha_o_trecho(self) -> None:
        com_aviso = _trecho("a", nao_usar_para=["evidencia_de_eficacia"], nota_uso="Cartilha sem referências.")
        r = montar_contexto_estrategista([_busca("carac_um", [com_aviso, _trecho("b")])])
        self.assertIn("AVISO DE USO: Cartilha sem referências.", r["contexto"])
        self.assertEqual(r["contexto"].count("AVISO DE USO:"), 1)
        self.assertIsNone(r["fontes"][1]["aviso_de_uso"])

    def test_nota_uso_sem_nao_usar_para_e_fallback_sem_nota_acompanham_trecho(self) -> None:
        so_nota = _trecho("a", nao_usar_para=[], nota_uso="Baseia-se na versão 2.0.")
        so_flag = _trecho("b", nao_usar_para=["norma_vigente"], nota_uso="")
        r = montar_contexto_estrategista([_busca("carac_um", [so_nota, so_flag])])
        self.assertEqual(r["fontes"][0]["aviso_de_uso"], "Baseia-se na versão 2.0.")
        self.assertEqual(r["fontes"][1]["aviso_de_uso"], "Não usar para: norma_vigente.")
        self.assertIn("AVISO DE USO: Baseia-se na versão 2.0.", r["contexto"])
        self.assertIn("AVISO DE USO: Não usar para: norma_vigente.", r["contexto"])

    def test_invariantes_entram_so_quando_informados(self) -> None:
        busca = [_busca("carac_um", [_trecho("a")])]
        self.assertNotIn("INVARIANTES", montar_contexto_estrategista(busca)["contexto"])
        self.assertIn("- fotossíntese", montar_contexto_estrategista(busca, ["fotossíntese"])["contexto"])

    def test_sem_evidencia_nao_ha_contexto(self) -> None:
        with self.assertRaises(ValueError):
            montar_contexto_estrategista([])
        with self.assertRaises(ValueError):
            montar_contexto_estrategista([_busca("carac_um", [_trecho("a")]), _busca("carac_dois", [])])

    def test_conferencia_das_citacoes(self) -> None:
        fontes = montar_contexto_estrategista([_busca("carac_um", [_trecho("a"), _trecho("b")])])["fontes"]
        diretiva = "Divida o enunciado em etapas numeradas [T1]. Destaque os verbos de comando [T7]. Reduza o texto pela metade."
        c = conferir_citacoes(diretiva, fontes)
        self.assertEqual(c["citados"], ["T1", "T7"])
        self.assertEqual(c["citacoes_inexistentes"], ["T7"])
        self.assertEqual(c["frases_sem_citacao"], ["Reduza o texto pela metade."])
        self.assertEqual(c["referencias"], ["Título a, p. 12. Disponível em: https://exemplo.org/a"])

    def test_conferencia_das_citacoes_em_lista_com_quebra_de_linha(self) -> None:
        fontes = montar_contexto_estrategista([_busca("carac_um", [_trecho("a")])])["fontes"]
        diretiva = "- Divida o enunciado em etapas [T1]\n- Reduza distrações visuais na margem"
        c = conferir_citacoes(diretiva, fontes)
        self.assertEqual(c["citados"], ["T1"])
        self.assertEqual(c["frases_sem_citacao"], ["- Reduza distrações visuais na margem"])


class TestMapeadorComBuscaReal(unittest.TestCase):
    def test_duas_caracteristicas_do_catalogo(self) -> None:
        garantir_chunks_locais()
        ids = ["atencao_sustentada_textos_longos", "ritmo_processamento_pressao_temporal"]
        buscas = [buscar_por_caracteristica_atomica(i, nivel=2, metodo="bm25") for i in ids]
        r = montar_contexto_estrategista(buscas, ["conceito de fração equivalente"])
        self.assertEqual(r["caracteristicas"], ids)
        self.assertTrue(5 <= len(r["fontes"]) <= 10)
        for f in r["fontes"]:
            self.assertIn(f"[{f['rotulo']}] ", r["contexto"])
            self.assertTrue(f["url"].startswith("http"))
            self.assertTrue(set(f["caracteristicas"]) <= set(ids))


if __name__ == "__main__":
    unittest.main()
