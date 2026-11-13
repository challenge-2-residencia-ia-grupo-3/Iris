"""Testes do registrador de produção. Rodar (na pasta bancada/producao):

    python3 -m unittest -v test_rastro_producao

Só biblioteca padrão. O último teste (no código do grupo) só roda com o Python da bancada
(iris-bancada-venv); com o python3 do sistema ele é pulado.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rastro_producao as RP  # noqa: E402

CARAC = "sobrecarga_memoria_trabalho_comandos_multiplos"
# material SINTÉTICO, com dado pessoal falso de propósito
MATERIAL = ("Escola Estadual Ficticia do Teste\nAluna: Fulana Ficticia Teste\nCPF: 111.111.111-11\n"
            "1) Leia o texto e explique como os cloroplastos produzem glicose. Em seguida, cite dois fatores.")


def base(tipo: str = "adaptacao", **kw) -> dict:
    r = {"tipo": tipo, "versao_esquema": 1, "dia": "2026-11-12", "caracteristica": CARAC, "nivel": 2}
    if tipo == "retorno":
        r["decisao"] = "aceitou"
    if tipo == "requisicao":
        r = {"tipo": tipo, "versao_esquema": 1, "dia": "2026-11-12"}
    return r | kw


class TestRecusaTextoDoMaterial(unittest.TestCase):
    def test_enunciado_em_campo_nao_declarado(self):
        with self.assertRaises(RP.CampoRecusado):
            RP.validar_registro(base(enunciado=MATERIAL))

    def test_texto_adaptado_em_campo_nao_declarado(self):
        with self.assertRaises(RP.CampoRecusado):
            RP.validar_registro(base(texto_adaptado="**Leia** o texto e **explique**"))

    def test_texto_do_material_em_campo_de_lista_fechada(self):
        for campo in ("caracteristica", "motivo_reserva", "erro_codigo", "provedor"):
            with self.subTest(campo=campo), self.assertRaises(RP.CampoRecusado):
                RP.validar_registro(base(**{campo: "explique como os cloroplastos produzem glicose"}))

    def test_motivo_de_recusa_digitado_e_recusado(self):
        with self.assertRaises(RP.CampoRecusado):
            RP.validar_registro(base("retorno", decisao="recusou", motivo_recusa="não gostei do negrito"))

    def test_palavra_do_material_em_campo_semiaberto(self):
        sentinela = RP.palavras_sentinela(MATERIAL)
        with self.assertRaises(RP.CampoRecusado) as ctx:
            RP.validar_registro(base(modelo="cloroplastos-v1"), sentinela=sentinela)
        self.assertIn("palavra do material", ctx.exception.motivo)
        # sem a palavra do material, o mesmo campo passa
        limpo, _ = RP.validar_registro(base(modelo="llama3:latest"), sentinela=sentinela)
        self.assertEqual(limpo["modelo"], "llama3:latest")

    def test_texto_dentro_de_lista_de_etapas(self):
        with self.assertRaises(RP.CampoRecusado):
            RP.validar_registro(base(etapas=[{"etapa": "agente_adaptador", "ms": 10, "saida": MATERIAL}]))

    def test_numero_nao_pode_ser_texto(self):
        with self.assertRaises(RP.CampoRecusado):
            RP.validar_registro(base(tokens_entrada="1200 tokens do enunciado sobre glicose"))


class TestRecusaNomesEDadosPessoais(unittest.TestCase):
    def test_nome_completo(self):
        for campo in ("modelo", "erro_codigo", "caracteristica"):
            with self.subTest(campo=campo), self.assertRaises(RP.CampoRecusado):
                RP.validar_registro(base(**{campo: "Fulana Ficticia Teste"}))

    def test_nome_como_chave(self):
        with self.assertRaises(RP.CampoRecusado) as ctx:
            RP.validar_registro(base(**{"Fulana Ficticia Teste": 1}))
        self.assertNotIn("Fulana", str(ctx.exception))

    def test_nome_colado_sem_espaco_no_modelo(self):
        sentinela = RP.palavras_sentinela(MATERIAL)
        with self.assertRaises(RP.CampoRecusado):
            RP.validar_registro(base(modelo="fulana-ficticia"), sentinela=sentinela)

    def test_cpf_telefone_email_cid(self):
        for valor in ("111.111.111-11", "61999990000", "fulana.teste@exemplo.invalid", "CID-10", "F90.0"):
            with self.subTest(valor=valor), self.assertRaises(RP.CampoRecusado):
                RP.validar_registro(base(modelo=valor))

    def test_detector(self):
        self.assertEqual(RP.parece_dado_pessoal("Fulana Ficticia Teste"), "nome_proprio")
        self.assertEqual(RP.parece_dado_pessoal("111.111.111-11"), "cpf")
        self.assertIsNone(RP.parece_dado_pessoal("llama3:latest"))

    def test_mensagem_de_recusa_nao_repete_o_valor(self):
        try:
            RP.validar_registro(base(modelo="Fulana Ficticia Teste"))
        except RP.CampoRecusado as e:
            self.assertNotIn("Fulana", str(e))
            self.assertNotIn("Ficticia", str(e))
        else:
            self.fail("deveria recusar")


class TestModoProducao(unittest.TestCase):
    def test_nao_estrito_descarta_campo_ruim_e_conta(self):
        limpo, n = RP.validar_registro(base(enunciado=MATERIAL, tokens_saida=12), estrito=False)
        self.assertNotIn("enunciado", limpo)
        self.assertEqual(n, 1)
        self.assertEqual(limpo["tokens_saida"], 12)

    def test_requisicao_completa_nao_grava_material_nem_nome(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RP.RegistradorProducao(modo="eventos", pasta=tmp, estrito=False)
            with reg.requisicao(MATERIAL, formato="pdf") as req:
                with req.etapa("filtro_pii"):
                    pass
                req.definir(n_pii_substituidos=3, n_questoes=1, comentario=MATERIAL)  # comentario: recusado
                with req.questao(1, CARAC, 2) as q:
                    with q.etapa("agente_adaptador"):
                        pass
                    q.definir(modelo="Fulana Ficticia Teste", tokens_entrada=100, usou_reserva=False)
            reg.retorno(caracteristica=CARAC, nivel=2, decisao="editou",
                        pct_alterado=RP.pct_alterado("1. [ ] Leia o texto", "1. Leia com atenção o texto"))
            conteudo = "".join(p.read_text(encoding="utf-8") for p in Path(tmp).iterdir())
            for proibido in ("Fulana", "111.111.111", "cloroplastos", "glicose", "Escola Estadual", "Leia"):
                self.assertNotIn(proibido.casefold(), conteudo.casefold(), proibido)
            linhas = [json.loads(l) for l in conteudo.splitlines()]
            self.assertEqual([l["tipo"] for l in linhas], ["requisicao", "adaptacao", "retorno"])
            self.assertEqual(reg.recusas, 2)  # comentario + modelo com nome
            for p in Path(tmp).iterdir():
                self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")

    def test_desligado_nao_grava_nada(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ.pop("IRIS_RASTRO_PRODUCAO", None)
            os.environ["IRIS_RASTRO_DIR"] = tmp
            try:
                reg = RP.RegistradorProducao.do_ambiente()
                with reg.requisicao(MATERIAL) as req:
                    req.definir(n_questoes=1)
                reg.retorno(caracteristica=CARAC, nivel=1, decisao="aceitou")
            finally:
                os.environ.pop("IRIS_RASTRO_DIR", None)
            self.assertFalse(reg.ligado)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_agregado_nao_guarda_id_nem_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RP.RegistradorProducao(modo="agregado", pasta=tmp)
            with reg.requisicao(MATERIAL) as req:
                with req.questao(1, CARAC, 2) as q:
                    q.definir(usou_reserva=False, escopo_aprovado=True)
            reg.retorno(caracteristica=CARAC, nivel=2, decisao="recusou", motivo_recusa="formatacao_quebrada",
                        id_requisicao="a" * 32)
            reg.descarregar()
            conteudo = "".join(p.read_text(encoding="utf-8") for p in Path(tmp).iterdir())
            self.assertNotIn("id_requisicao", conteudo)
            self.assertNotIn("material_hmac", conteudo)
            self.assertIn("formatacao_quebrada", conteudo)

    def test_retencao_apaga_arquivo_velho(self):
        with tempfile.TemporaryDirectory() as tmp:
            velho = Path(tmp) / "eventos-2026-01-01.jsonl"
            velho.write_text("{}\n")
            novo = Path(tmp) / "eventos-2026-11-10.jsonl"
            novo.write_text("{}\n")
            RP.RegistradorProducao(modo="eventos", pasta=tmp, retencao_dias=30,
                                   relogio=lambda: datetime(2026, 11, 12, tzinfo=timezone.utc))
            self.assertFalse(velho.exists())
            self.assertTrue(novo.exists())

    def test_hash_do_material_nao_e_recalculavel(self):
        a = RP.RegistradorProducao(estrito=True)._hmac_material(MATERIAL)
        b = RP.RegistradorProducao(estrito=True)._hmac_material(MATERIAL)
        self.assertNotEqual(a, b)  # chave aleatória por processo e por dia: o sha256 puro não aparece

    def test_pct_alterado_e_coerencia_do_retorno(self):
        self.assertEqual(RP.pct_alterado("abc", "abc"), 0)
        self.assertEqual(RP.pct_alterado("abcdefghij", "") % 5, 0)
        reg = RP.RegistradorProducao(estrito=True)
        r = reg.retorno(caracteristica=CARAC, nivel=2, decisao="aceitou", pct_alterado=40,
                        motivo_recusa="outro")
        self.assertNotIn("pct_alterado", r)
        self.assertNotIn("motivo_recusa", r)

    def test_agregacao_suprime_celula_pequena(self):
        regs = [RP.validar_registro(base("retorno", decisao="aceitou"))[0] for _ in range(3)]
        m = RP.agregar(regs, k_min=5)
        self.assertTrue(m["geral"]["aceite_sem_edicao"]["suprimido"])


class TestNoCodigoDoGrupo(unittest.TestCase):
    """Registrador ligado no pipeline real do grupo (provedor 'eco'): nada do material chega ao rastro."""

    @classmethod
    def setUpClass(cls):
        try:
            import pydantic  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("precisa do Python da bancada (iris-bancada-venv)")

    def test_pipeline_real_nao_vaza(self):
        import exercitar

        r = exercitar.rodar()
        self.assertGreater(r["registros_aceitos"], 0)
        self.assertEqual(r["campos_recusados_no_fluxo_real"], 0)
        self.assertEqual(r["pii_vazado_no_rastro"], 0)
        self.assertEqual(r["trigramas_do_material_no_rastro"], 0)
        self.assertEqual(r["tentativas_recusadas"], r["tentativas_total"])


if __name__ == "__main__":
    unittest.main()
