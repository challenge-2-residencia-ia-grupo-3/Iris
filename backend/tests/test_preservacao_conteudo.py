"""Preservação integral do conteúdo na decomposição estrutural (História 1.1.2 / RF-02).

Critério: toda palavra do material enviado pelo docente aparece, o mesmo número de
vezes, em algum campo da estrutura devolvida por `decompose_material` (cabeçalho,
instruções, blocos de contexto, enunciados, alternativas, espaços de resposta ou
blocos não classificados).

A comparação é por multiconjunto de palavras (contagem por palavra), e não por
conjunto: uma palavra que aparece três vezes no original e duas na estrutura conta
como perda. O teste percorre dez formatos de material de sala de aula.
"""
from __future__ import annotations

import re
import unittest
from collections import Counter

from iris.parsers.structural_decomposer import decompose_material
from iris.schemas.materials import MaterialStructure

MATERIAIS = {
    "prova_simples": (
        "Escola Municipal Rui Barbosa\nProva de Ciências - 6º ano\n\n"
        "1. Explique o que é fotossíntese.\n\n2. Cite dois exemplos de seres produtores.\n"
    ),
    "multipla_escolha": (
        "1. Qual é o maior planeta do Sistema Solar?\na) Terra\nb) Júpiter\nc) Marte\nd) Vênus\n\n"
        "2. Quanto é 7 x 8?\n(A) 54\n(B) 56\n(C) 63\n"
    ),
    "texto_de_apoio": (
        "Texto 1: A água\nA água cobre cerca de 70% da superfície do planeta.\n"
        "Apenas uma pequena parte é doce.\n\nLeia o texto para responder às questões 1 e 2.\n\n"
        "1. Que fração da superfície é coberta por água?\n\n"
        "2. Por que a água doce é escassa?\nResposta: ____________\n"
    ),
    "instrucoes": (
        "Colégio Estadual Central\nNome: ____________ Turma: ____\n\n"
        "Instruções: use caneta azul ou preta. Não é permitido o uso de calculadora.\n\n"
        "Questão 1 - Calcule a área de um quadrado de lado 5 cm.\n\n"
        "Questão 2 - Determine o valor de x na equação 2x + 6 = 14.\n"
    ),
    "prosa_pura": (
        "A Revolução Industrial começou na Inglaterra no século XVIII.\n"
        "As fábricas mudaram a vida nas cidades.\n\n"
        "Os trabalhadores enfrentavam jornadas longas e salários baixos.\n"
    ),
    "texto_entre_questoes": (
        "1. Quanto é 2 + 2?\na) 3\nb) 4\n\n"
        "Observe o gráfico abaixo antes de continuar.\nEle mostra a chuva de janeiro a junho.\n\n"
        "2. Em que mês choveu mais?\n"
    ),
    "alternativas_na_mesma_linha": (
        "1. Assinale o antônimo de efêmero.\n"
        "(A) Passageiro   (B) Duradouro   (C) Breve   (D) Rápido\n\n2. Explique sua escolha.\n"
    ),
    "poema": (
        "Texto 1\nNo meio do caminho tinha uma pedra\ntinha uma pedra no meio do caminho\n\n"
        "1. Qual é o tema do poema?\n\n2. Que recurso de repetição o autor usa?\n"
    ),
    "subitens": (
        "1. Observe a tabela e responda:\na) Qual é o maior valor?\nb) Qual é o menor valor?\n"
        "c) Calcule a diferença entre eles.\n\n2. Justifique sua resposta ao item c.\n"
    ),
    "rodape": (
        "1. Explique o ciclo da água.\n\n2. Desenhe o ciclo no espaço abaixo.\n\n"
        "Boa prova!\nProfessora Ana\n"
    ),
}


def contar_palavras(texto: str | None) -> Counter[str]:
    return Counter(re.findall(r"\w+", (texto or "").lower()))


def palavras_da_estrutura(estrutura: MaterialStructure) -> Counter[str]:
    """Soma as palavras de todos os campos de texto da estrutura decomposta."""
    total: Counter[str] = Counter()
    for texto in (estrutura.header, estrutura.instructions, *estrutura.unclassified_blocks):
        total += contar_palavras(texto)
    for bloco in estrutura.context_blocks:
        for texto in (bloco.title, bloco.instruction, bloco.text):
            total += contar_palavras(texto)
    for questao in estrutura.questions:
        for texto in (questao.original_number, questao.statement, questao.answer_space):
            total += contar_palavras(texto)
        for alternativa in questao.options or []:
            total += contar_palavras(alternativa.letter) + contar_palavras(alternativa.text)
    return total


class TestPreservacaoIntegralDoConteudo(unittest.TestCase):
    """Nenhuma palavra do material original pode faltar na estrutura decomposta."""

    def test_nenhuma_palavra_perdida_em_dez_formatos(self) -> None:
        for nome, texto in MATERIAIS.items():
            with self.subTest(material=nome):
                estrutura = decompose_material(texto)
                perdidas = contar_palavras(texto) - palavras_da_estrutura(estrutura)
                self.assertEqual(
                    dict(perdidas),
                    {},
                    f"Palavras do original ausentes da estrutura em '{nome}': {dict(perdidas)}",
                )

    def test_a_comparacao_acusa_uma_palavra_removida(self) -> None:
        """Confere o próprio instrumento: retirar uma palavra da estrutura precisa ser detectado."""
        texto = MATERIAIS["prova_simples"]
        estrutura = decompose_material(texto)
        estrutura.questions[0].statement = estrutura.questions[0].statement.replace("fotossíntese", "")
        perdidas = contar_palavras(texto) - palavras_da_estrutura(estrutura)
        self.assertEqual(dict(perdidas), {"fotossíntese": 1})


if __name__ == "__main__":
    unittest.main()
