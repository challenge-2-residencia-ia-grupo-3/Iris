"""Testes de regressão dos pontos levantados na revisão do PR #91 (exportação do Perfil Pedagógico Portátil)."""
from __future__ import annotations

import unicodedata
import unittest

from iris.exportacao.perfil import exportar_perfil, sem_dado_pessoal
from iris.schemas.portable_profile import validar_perfil

ID = "sobrecarga_memoria_trabalho_comandos_multiplos"
BASE = {
    "versao_schema": "1.0",
    "codigo_anonimo": "aluno-8f7a2c1b",
    "criado_em": "2026-11-13T12:00:00.000Z",
    "caracteristicas_selecionadas": [ID],
    "barreiras_observadas": [],
    "historico_estrategias": [],
    "anotacoes_pedagogicas": [],
}
CPF, TELEFONE, EMAIL = "123.456.789-09", "99999-1234", "responsavel@escola.example"
COM_DADO_PESSOAL = {
    **BASE,
    "barreiras_observadas": [{"id_caracteristica": ID, "observacao": f"Avisar a família pelo {EMAIL}."}],
    "historico_estrategias": [
        {"estrategia": f"Ligar para (61) {TELEFONE} antes da prova", "resultado": "eficaz", "observacao": f"CPF {CPF}"}
    ],
    "anotacoes_pedagogicas": [f"CPF {CPF}, tel (61) {TELEFONE}, {EMAIL}, responde bem a esquemas."],
}


def _texto_do_pdf(conteudo: bytes) -> str:
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    doc = pymupdf.open(stream=conteudo, filetype="pdf")
    # NFKC desfaz as ligaduras do PDF; o split desfaz as quebras de linha, para comparar frases inteiras.
    return " ".join(unicodedata.normalize("NFKC", "\n".join(p.get_text() for p in doc)).split())


class TestDadoPessoalEmTextoLivre(unittest.TestCase):
    def test_pdf_nao_leva_cpf_telefone_nem_email(self):
        texto = _texto_do_pdf(exportar_perfil(COM_DADO_PESSOAL, "pdf").conteudo)
        for dado in (CPF, TELEFONE, EMAIL):
            self.assertNotIn(dado, texto)
        for marcador in ("[CPF]", "[TELEFONE]", "[EMAIL]"):
            self.assertIn(marcador, texto)
        self.assertIn("responde bem a esquemas.", texto)

    def test_json_do_servidor_nao_leva_cpf_telefone_nem_email(self):
        bruto = exportar_perfil(COM_DADO_PESSOAL, "json").conteudo.decode("utf-8")
        for dado in (CPF, TELEFONE, EMAIL):
            self.assertNotIn(dado, bruto)
        self.assertEqual(validar_perfil(bruto).codigo_anonimo, "aluno-8f7a2c1b")

    def test_texto_sem_dado_pessoal_e_campos_fechados_nao_mudam(self):
        dados = {
            **BASE,
            "historico_estrategias": [{"estrategia": "Dividir o enunciado em 3 passos", "resultado": "eficaz"}],
            "anotacoes_pedagogicas": ["Em 2026 passou a usar esquemas visuais nas 4 avaliações do bimestre."],
        }
        original = validar_perfil(dados)
        self.assertEqual(sem_dado_pessoal(original), original)

    def test_marcador_mais_longo_que_o_trecho_no_limite_de_tamanho(self):
        nota = ("x" * 993 + " a@b.co")[:1000]
        arquivo = exportar_perfil({**BASE, "anotacoes_pedagogicas": [nota]}, "pdf")
        self.assertIn("[EMAIL]", _texto_do_pdf(arquivo.conteudo))

    def test_rodape_nao_promete_ausencia_de_nome(self):
        texto = _texto_do_pdf(exportar_perfil(BASE, "pdf").conteudo)
        self.assertNotIn("não contém nome", texto)
        self.assertIn("revise antes de compartilhar", texto)


class TestBarreiraComNomeDoCatalogo(unittest.TestCase):
    def test_barreira_mostra_o_nome_legivel(self):
        dados = {**BASE, "caracteristicas_selecionadas": [],
                 "barreiras_observadas": [{"id_caracteristica": ID, "observacao": "Perde o fio."}]}
        texto = _texto_do_pdf(exportar_perfil(dados, "pdf").conteudo)
        self.assertIn("Múltiplos comandos na mesma questão", texto)
        self.assertNotIn(ID, texto)

    def test_barreira_fora_do_catalogo_mostra_o_proprio_id(self):
        dados = {**BASE, "barreiras_observadas": [{"id_caracteristica": "caracteristica_fora_do_catalogo"}]}
        self.assertIn("caracteristica_fora_do_catalogo", _texto_do_pdf(exportar_perfil(dados, "pdf").conteudo))


if __name__ == "__main__":
    unittest.main()
