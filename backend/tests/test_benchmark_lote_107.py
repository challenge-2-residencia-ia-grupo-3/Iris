"""Lote #107: questões de fonte pública para características sem cobertura no v1."""

import json
import unittest
from pathlib import Path

from iris.schemas.benchmark import BenchmarkQuestionItem, ids_caracteristicas

DATA = Path(__file__).resolve().parents[2] / "data" / "benchmarks"
LOTE = DATA / "questoes_escolares_lote_107_v1.json"
V1 = DATA / "questoes_escolares_v1.json"

FADIGA = "fadiga_executiva_autorregulacao_provas_extensas"
ABERTAS = "bloqueio_iniciacao_tarefas_abertas"


class TestLote107(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.itens = [BenchmarkQuestionItem(**d) for d in json.loads(LOTE.read_text(encoding="utf-8"))]

    def test_minimos_do_criterio_de_aceite(self):
        # fadiga: critério de aceite (>= 8). abertas: critério de aceite (>= 8).
        self.assertGreaterEqual(sum(1 for i in self.itens if i.id_caracteristica_alvo == FADIGA), 8)
        self.assertGreaterEqual(sum(1 for i in self.itens if i.id_caracteristica_alvo == ABERTAS), 8)

    def test_caracteristicas_existem_no_catalogo(self):
        cat = set(ids_caracteristicas())
        for i in self.itens:
            self.assertIn(i.id_caracteristica_alvo, cat)

    def test_ids_unicos_e_sem_colisao_com_v1(self):
        v1 = {d["id"] for d in json.loads(V1.read_text(encoding="utf-8"))}
        ids = [i.id for i in self.itens]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(v1 & set(ids))

    def test_fonte_publica_e_rascunho(self):
        for i in self.itens:
            self.assertTrue(i.fonte.url.startswith(("https://download.inep.gov.br/", "https://www.obmep.org.br/")))
            self.assertEqual(i.status, "rascunho")

    def test_enunciado_nao_manda_ler_texto_que_nao_esta_no_item(self):
        # Os textos motivadores das redações foram omitidos (direitos de terceiros): o comando não pode mandar lê-los.
        for i in self.itens:
            self.assertNotIn("textos motivadores", i.enunciado_original.lower(), i.id)

    def test_url_aponta_para_a_prova_e_nao_para_a_lista(self):
        # A fonte precisa levar à prova daquela aplicação: o PDF do Inep ou a página do ano na OBMEP.
        # O endereço do ENEM 2018 sem "educacao_basica/" devolvia 404, e "provas.htm" é só a lista geral.
        for i in self.itens:
            url = i.fonte.url
            if url.startswith("https://download.inep.gov.br/"):
                self.assertTrue(url.endswith(".pdf"), (i.id, url))
                if i.id.startswith("ENEM2018"):
                    self.assertIn("/educacao_basica/enem/provas/2018/", url, i.id)
            else:
                self.assertRegex(url, r"/provas-20\d\d\.htm$", i.id)

    def test_abertas_sem_alternativas(self):
        for i in self.itens:
            if i.id_caracteristica_alvo == ABERTAS:
                self.assertIsNone(i.alternativas)

    def test_conceitos_aparecem_no_texto(self):
        import re

        def nz(s):
            return re.sub(r"\s+", " ", s).lower()

        for i in self.itens:
            txt = nz(i.enunciado_original + " " + " ".join(a.texto for a in (i.alternativas or [])))
            for c in i.conceitos_trava_curricular:
                self.assertIn(nz(c), txt, (i.id, c))


if __name__ == "__main__":
    unittest.main()
