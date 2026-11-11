"""Testes de regressão dos pontos levantados na revisão do PR 55 (História 1.1.4, issue #53)."""

from __future__ import annotations

import unittest

from iris.api.routes.materials import organize_prose_service
from iris.parsers.prose_organizer import organize_prose_structure
from iris.schemas.materials import MaterialValidationError


def _tipos(texto: str) -> list[tuple[str, str]]:
    return [(n.element_type, n.content) for n in organize_prose_structure(texto).flatten()]


class TestFrasesNaoViramSecao(unittest.TestCase):
    def test_frase_iniciada_por_parte_ou_unidade_e_paragrafo(self) -> None:
        texto = (
            "A água no planeta\n\n"
            "Parte da água do planeta está nos oceanos e não serve para beber.\n\n"
            "Unidade de medida usada neste texto é o litro."
        )
        tipos = [t for t, _ in _tipos(texto)]
        self.assertEqual(tipos, ["title", "paragraph", "paragraph"])

    def test_secao_nomeada_continua_reconhecida(self) -> None:
        tipos = _tipos("Unidade 2: Frações\n\nUma fração representa partes de um todo.")
        self.assertEqual(tipos[0][0], "section")

    def test_abreviatura_com_ponto_nao_e_numeral_romano(self) -> None:
        texto = (
            "A Independência\n\n"
            "D. Pedro I proclamou a independência em 1822, às margens do Ipiranga.\n\n"
            "O país passou a ser um império."
        )
        self.assertEqual([t for t, _ in _tipos(texto)], ["title", "paragraph", "paragraph"])

    def test_numero_decimal_no_inicio_da_frase_nao_e_subsecao(self) -> None:
        texto = "População\n\n3.5 milhões de pessoas vivem na região metropolitana, segundo o censo."
        self.assertEqual([t for t, _ in _tipos(texto)], ["title", "paragraph"])

    def test_primeira_linha_de_paragrafo_quebrado_nao_e_titulo(self) -> None:
        texto = (
            "A fotossíntese é o processo pelo qual as plantas\n"
            "produzem o próprio alimento usando a luz do sol,\n"
            "a água e o gás carbônico."
        )
        nos = _tipos(texto)
        self.assertEqual([t for t, _ in nos], ["paragraph"])
        self.assertIn("plantas produzem", nos[0][1])

    def test_linha_terminada_em_dois_pontos_nao_e_subtitulo(self) -> None:
        texto = (
            "O ciclo da água\n\n"
            "A água evapora com o calor do sol e sobe para a atmosfera.\n\n"
            "Observe o exemplo:\n\n"
            "A roupa seca no varal porque a água evapora."
        )
        self.assertEqual([t for t, _ in _tipos(texto)], ["title", "paragraph", "paragraph", "paragraph"])


class TestListas(unittest.TestCase):
    def test_lista_numerada_curta_nao_vira_secoes(self) -> None:
        texto = (
            "Ingredientes do experimento:\n1. Água\n2. Sal\n3. Açúcar\n\n"
            "Misture tudo em um copo e observe o resultado por dez minutos."
        )
        estrutura = organize_prose_structure(texto)
        self.assertEqual(estrutura.get_sections(), [])
        listas = estrutura.get_lists()
        self.assertEqual(len(listas), 1)
        self.assertEqual(listas[0].metadata["item_count"], 3)
        # O parágrafo seguinte não fica subordinado ao último item
        paragrafo = [n for n in estrutura.flatten() if n.content.startswith("Misture")][0]
        self.assertNotIn("Açúcar", [n.content for n in estrutura.flatten() if n.id == paragrafo.parent_id])

    def test_lista_preserva_os_marcadores_originais(self) -> None:
        estrutura = organize_prose_structure("Escolha uma opção:\na) Mercúrio\nb) Vênus\nc) Terra")
        lista = estrutura.get_lists()[0]
        self.assertEqual(lista.content, "a) Mercúrio\nb) Vênus\nc) Terra")

    def test_listas_de_tipos_diferentes_nao_se_fundem(self) -> None:
        estrutura = organize_prose_structure(
            "Itens:\n- lápis\n- borracha\n1. primeiro passo.\n2. segundo passo."
        )
        self.assertEqual(
            [(lst.metadata["list_type"], lst.metadata["item_count"]) for lst in estrutura.get_lists()],
            [("unordered", 2), ("ordered", 2)],
        )

    def test_item_em_duas_linhas_permanece_inteiro(self) -> None:
        estrutura = organize_prose_structure(
            "Materiais:\n- régua de trinta centímetros para medir\n  o comprimento da mesa\n- lápis\n- borracha"
        )
        listas = estrutura.get_lists()
        self.assertEqual(len(listas), 1)
        self.assertEqual(listas[0].metadata["item_count"], 3)
        self.assertIn("o comprimento da mesa", listas[0].children[0].content)

    def test_fala_com_travessao_nao_e_item_de_lista(self) -> None:
        estrutura = organize_prose_structure(
            "O encontro\n\nMaria chegou cedo à escola.\n\n— Bom dia, professora!\n— Bom dia, Maria. Sente-se."
        )
        self.assertEqual(estrutura.get_lists(), [])
        self.assertIn("— Bom dia, professora!", " ".join(n.content for n in estrutura.flatten()))

    def test_enunciado_numerado_com_verbo_de_comando_nao_entra_na_lista(self) -> None:
        estrutura = organize_prose_structure(
            "1. Qual é o maior planeta?\nA) Terra\nB) Júpiter\n\n"
            "2. Explique a diferença entre planetas rochosos e gasosos."
        )
        itens = [n.content for n in estrutura.flatten() if n.element_type == "list_item"]
        self.assertEqual(itens, ["Terra", "Júpiter"])


class TestPreservacao(unittest.TestCase):
    def test_versos_mantem_as_quebras_de_linha(self) -> None:
        estrofe = "Minha terra tem palmeiras,\nOnde canta o Sabiá;\nAs aves, que aqui gorjeiam,\nNão gorjeiam como lá."
        estrutura = organize_prose_structure("Canção do Exílio\n\n" + estrofe)
        paragrafo = estrutura.get_paragraphs()[0]
        self.assertEqual(paragrafo.metadata.get("raw_text"), estrofe)

    def test_cabecalho_markdown_define_o_nivel(self) -> None:
        nos = organize_prose_structure("# Fotossíntese\n\n## Etapas\n\n### Fase clara\n\nA planta usa a luz.").flatten()
        self.assertEqual(
            [(n.element_type, n.level, n.content) for n in nos[:3]],
            [("title", 1, "Fotossíntese"), ("section", 2, "Etapas"), ("subsection", 3, "Fase clara")],
        )


class TestServico(unittest.TestCase):
    def test_servico_aplica_os_limites_de_tamanho_da_entrada(self) -> None:
        for texto in ("oi", "a" * 200_000):
            with self.assertRaises(MaterialValidationError):
                organize_prose_service(texto)


if __name__ == "__main__":
    unittest.main()
