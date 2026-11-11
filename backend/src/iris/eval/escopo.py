"""Verificador determinístico de isolamento de escopo (História 2.1.3 / Issue #18, RF-04 e RF-11).

Compara o enunciado original com o adaptado, sem LLM, e responde quatro perguntas:

  1. alguma palavra do original foi perdida? (contagem de palavras, com repetições);
  2. entrou palavra que não pertence ao vocabulário do andaime do nível? (ex.: dica, resposta, sinônimo);
  3. a ordem das palavras do original foi mantida? (maior subsequência comum);
  4. algum conceito da trava curricular deixou de aparecer? (TRCC do adaptado contra o do original).

As perguntas 1 a 3 dependem de uma regra por característica e nível (``REGRAS_ESCOPO``). Só a
característica de comandos múltiplos tem regra definida; nas demais, as ações permitidas pelo
catálogo acrescentam ou reescrevem texto de formas que uma lista fixa de palavras não cobre, e o
laudo decide apenas pela trava curricular, informando as diferenças sem julgá-las.

Limitação assumida: a comparação é por palavra, sem semântica. Uma lista de palavras permitidas
não impede que elas sejam recombinadas em uma frase nova.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from iris.eval.readability import COMMAND_VERBS
from iris.eval.trcc import avaliar_trcc
from iris.schemas.adaptation import ScopeReport

ID_COMANDOS_MULTIPLOS = "sobrecarga_memoria_trabalho_comandos_multiplos"

# Formas imperativas de `COMMAND_VERBS` (as infinitivas terminam em "r" e aparecem em texto corrido).
VERBOS_IMPERATIVOS = frozenset(v for v in COMMAND_VERBS if not v.endswith("r"))

# Palavra que, antes de "escolha", "monte" ou "cite", indica substantivo e não comando.
_DETERMINANTES = frozenset("a o as os um uma da do das dos na no nas nos de sua seu suas seus".split())

_RE_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]+")
_RE_NEGRITO = re.compile(r"\*\*|__")
_RE_MARCADOR_DE_LINHA = re.compile(r"^[ \t]*(?:\d+[.)]|[-•])?[ \t]*(?:\[[ xX]?\])?[ \t]*", re.MULTILINE)
_RE_LINHA_DE_RESPOSTA = re.compile(r"_{3,}")
_RE_TOKEN = re.compile(r"[0-9A-Za-zÀ-ÿ²³°]+|[+=×÷−*/<>]")


@dataclass(frozen=True)
class RegraEscopo:
    """O que uma adaptação pode acrescentar ou retirar em uma característica e nível."""

    vocabulario_andaime: frozenset[str] = frozenset()
    # Palavras do andaime que aceitam um número logo depois ("Passo 1").
    aceita_numero_apos: frozenset[str] = frozenset()
    # Nível de destaque: fora o negrito e a caixa das letras, o texto tem de ser idêntico.
    texto_identico: bool = False
    # A lista de etapas torna redundante o "e" que ligava dois comandos.
    tolera_conectivo_antes_de_comando: bool = False


REGRAS_ESCOPO: dict[tuple[str, int], RegraEscopo] = {
    (ID_COMANDOS_MULTIPLOS, 1): RegraEscopo(texto_identico=True),
    (ID_COMANDOS_MULTIPLOS, 2): RegraEscopo(tolera_conectivo_antes_de_comando=True),
    (ID_COMANDOS_MULTIPLOS, 3): RegraEscopo(
        vocabulario_andaime=frozenset("passo passos resposta revise se você preencheu todos os".split()),
        aceita_numero_apos=frozenset({"passo", "passos"}),
        tolera_conectivo_antes_de_comando=True,
    ),
}


def localizar_comandos(texto: str) -> list[tuple[int, int]]:
    """Posições (início, fim) dos verbos de comando no imperativo, na ordem em que aparecem."""
    posicoes: list[tuple[int, int]] = []
    anterior, fim_anterior = "", 0
    for m in _RE_PALAVRA.finditer(texto):
        palavra = m.group().lower()
        # O determinante só vale na mesma linha: "47° O" no fim de um item não antecede o verbo do item seguinte.
        mesma_linha = "\n" not in texto[fim_anterior : m.start()]
        if palavra in VERBOS_IMPERATIVOS and not (mesma_linha and anterior in _DETERMINANTES):
            posicoes.append(m.span())
        anterior, fim_anterior = palavra, m.end()
    return posicoes


def remover_marcacao(texto: str) -> str:
    """Retira o que é só marcação de andaime: negrito, número de item, caixa de seleção e linha de resposta."""
    texto = _RE_NEGRITO.sub("", texto)
    texto = _RE_LINHA_DE_RESPOSTA.sub(" ", texto)
    return _RE_MARCADOR_DE_LINHA.sub("", texto)


def palavras(texto: str) -> list[str]:
    """Palavras, números e operadores do texto, sem marcação e sem distinguir maiúsculas."""
    return [t.casefold() for t in _RE_TOKEN.findall(remover_marcacao(texto))]


def _tamanho_subsequencia_comum(a: list[str], b: list[str]) -> int:
    anterior = [0] * (len(b) + 1)
    for x in a:
        atual = [0]
        for j, y in enumerate(b, 1):
            atual.append(anterior[j - 1] + 1 if x == y else max(anterior[j], atual[j - 1]))
        anterior = atual
    return anterior[-1]


def _linhas(texto: str) -> list[str]:
    return [" ".join(linha.split()).casefold() for linha in texto.strip().splitlines() if linha.strip()]


def verificar_escopo(
    original: str,
    adaptado: str,
    id_caracteristica: str,
    nivel: int,
    trava: str | Iterable[str] | None = None,
) -> ScopeReport:
    """Laudo de isolamento de escopo do texto adaptado contra o original."""
    regra = REGRAS_ESCOPO.get((id_caracteristica, nivel))
    a, b = palavras(original), palavras(adaptado)
    conta_a, conta_b = Counter(a), Counter(b)
    perdidas = conta_a - conta_b
    novas = conta_b - conta_a
    violacoes: list[str] = []

    trava = list(trava) if trava is not None and not isinstance(trava, str) else trava
    ausentes_no_original = set(avaliar_trcc(trava, original).ausentes)
    conceitos_perdidos = [c for c in avaliar_trcc(trava, adaptado).ausentes if c not in ausentes_no_original]
    if conceitos_perdidos:
        violacoes.append(f"conceito da trava curricular ausente: {conceitos_perdidos}")

    if regra is None:
        return ScopeReport(
            aprovado=not violacoes,
            regra_aplicada=False,
            palavras_perdidas=sorted(perdidas.elements()),
            palavras_novas=sorted(novas.elements()),
            conceitos_perdidos=conceitos_perdidos,
            violacoes=violacoes,
        )

    conectivos_removidos = 0
    if regra.tolera_conectivo_antes_de_comando and perdidas["e"]:
        antes_de_comando = sum(
            1 for i in range(len(a) - 1) if a[i] == "e" and a[i + 1] in VERBOS_IMPERATIVOS
        )
        conectivos_removidos = min(perdidas["e"], antes_de_comando)
        perdidas["e"] -= conectivos_removidos
        perdidas = +perdidas

    for palavra in list(novas):
        if palavra in regra.vocabulario_andaime:
            del novas[palavra]
        elif palavra.isdigit():
            justificadas = sum(
                1 for j in range(1, len(b)) if b[j] == palavra and b[j - 1] in regra.aceita_numero_apos
            )
            novas[palavra] -= min(novas[palavra], justificadas)
    novas = +novas

    palavras_perdidas = sorted(perdidas.elements())
    palavras_novas = sorted(novas.elements())
    if palavras_perdidas:
        violacoes.append(f"palavra do original ausente: {palavras_perdidas}")
    if palavras_novas:
        violacoes.append(f"palavra fora do vocabulário do andaime: {palavras_novas}")

    # Se nada se perdeu além do que foi contado, todo o restante do original tem de aparecer na mesma ordem.
    esperado = len(a) - len(palavras_perdidas) - conectivos_removidos
    ordem_alterada = _tamanho_subsequencia_comum(a, b) < esperado
    if ordem_alterada:
        violacoes.append("ordem das palavras do original alterada")

    estrutura_alterada = regra.texto_identico and _linhas(_RE_NEGRITO.sub("", adaptado)) != _linhas(original)
    if estrutura_alterada:
        violacoes.append("texto alterado além do destaque tipográfico")

    return ScopeReport(
        aprovado=not violacoes,
        regra_aplicada=True,
        palavras_perdidas=palavras_perdidas,
        palavras_novas=palavras_novas,
        conectivos_removidos=conectivos_removidos,
        conceitos_perdidos=conceitos_perdidos,
        ordem_alterada=ordem_alterada,
        estrutura_alterada=estrutura_alterada,
        violacoes=violacoes,
    )
