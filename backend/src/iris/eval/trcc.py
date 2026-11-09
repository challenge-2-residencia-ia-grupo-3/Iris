"""TRCC determinístico: Taxa de Retenção de Conceitos-Chave (RNF-04, RF-12).

    TRCC = |conceitos da trava presentes no material adaptado| / |conceitos da trava|

Regras de comparação (todas determinísticas, sem LLM):
  * ignora maiúsculas/minúsculas e acentos;
  * espaços ao redor de operadores são irrelevantes ("2x + 6 = 14" == "2x+6=14");
  * palavra inteira: "12" não casa com "120" e "pi" não casa com "pipeline";
  * cada conceito pode ter alternativas separadas por "|" ("encontrou|achou"): basta uma.

Limitação assumida: não há lematização. Plurais e flexões diferentes ("animal" x "animais")
precisam ser listados como alternativas na trava.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from statistics import mean

LIMIAR_PADRAO = 0.95
_EPS = 1e-9

_OPERADORES = re.compile(r"\s*([=+\-*/×÷^<>])\s*")
_TRACOS = str.maketrans({"−": "-", "–": "-", "—": "-"})


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos, traços unificados e sem espaços ao redor de operadores."""
    texto = unicodedata.normalize("NFKC", texto).translate(_TRACOS)
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    texto = _OPERADORES.sub(r"\1", texto.casefold())
    return re.sub(r"\s+", " ", texto).strip()


@dataclass(frozen=True)
class Conceito:
    rotulo: str  # como aparece na trava (para relatórios)
    alternativas: tuple[str, ...]  # formas aceitas, já normalizadas


def parse_trava(trava: str | Iterable[str] | None) -> list[Conceito]:
    """Converte a trava em conceitos.

    Aceita None, uma lista de conceitos ou um texto com conceitos separados por ';' ou quebra
    de linha. Um texto NUNCA é percorrido letra a letra.
    """
    if trava is None:
        return []
    itens = re.split(r"[;\n]", trava) if isinstance(trava, str) else [str(c) for c in trava]

    conceitos: dict[tuple[str, ...], Conceito] = {}
    for item in itens:
        alternativas = tuple(dict.fromkeys(a for a in (normalizar(x) for x in item.split("|")) if a))
        if alternativas and alternativas not in conceitos:
            conceitos[alternativas] = Conceito(rotulo=item.strip(), alternativas=alternativas)
    return list(conceitos.values())


def _presente(alternativa: str, texto_normalizado: str) -> bool:
    # Fronteira de palavra só onde a borda do conceito é letra/dígito (símbolos como "+" não têm).
    esq = r"(?<!\w)" if alternativa[0].isalnum() else ""
    dir_ = r"(?!\w)" if alternativa[-1].isalnum() else ""
    return re.search(esq + re.escape(alternativa) + dir_, texto_normalizado) is not None


@dataclass(frozen=True)
class ResultadoTRCC:
    trcc: float | None  # None = trava vazia (não há o que medir; NÃO é 100%)
    n_esperados: int
    encontrados: tuple[str, ...]
    ausentes: tuple[str, ...]

    @property
    def n_encontrados(self) -> int:
        return len(self.encontrados)

    def aprovado(self, limiar: float = LIMIAR_PADRAO) -> bool:
        return self.trcc is not None and self.trcc >= limiar - _EPS


def avaliar_trcc(trava: str | Iterable[str] | None, texto_adaptado: str) -> ResultadoTRCC:
    """TRCC de um texto adaptado contra a trava curricular, com os conceitos que faltaram."""
    conceitos = parse_trava(trava)
    texto = normalizar(texto_adaptado)
    achados = [c.rotulo for c in conceitos if any(_presente(a, texto) for a in c.alternativas)]
    ausentes = [c.rotulo for c in conceitos if c.rotulo not in achados]
    return ResultadoTRCC(
        trcc=len(achados) / len(conceitos) if conceitos else None,
        n_esperados=len(conceitos),
        encontrados=tuple(achados),
        ausentes=tuple(ausentes),
    )


def avaliar_benchmark(
    travas: Mapping[str, str | Iterable[str] | None], adaptados: Mapping[str, str]
) -> dict[str, ResultadoTRCC]:
    """Avalia todas as questões. Falta de texto adaptado é erro, não zero silencioso."""
    faltando = sorted(set(travas) - set(adaptados))
    if faltando:
        raise KeyError(f"Sem texto adaptado para as questões: {faltando}")
    return {qid: avaliar_trcc(trava, adaptados[qid]) for qid, trava in travas.items()}


def agregar(resultados: Mapping[str, ResultadoTRCC], limiar: float = LIMIAR_PADRAO) -> dict:
    """Resumo do benchmark nas duas leituras possíveis do critério de 95%.

    * micro: soma dos conceitos retidos / soma dos conceitos esperados (todo o benchmark);
    * por questão: nenhuma questão fica abaixo do limiar.
    Questões sem trava não entram na média e impedem a aprovação.
    """
    validos = {q: r for q, r in resultados.items() if r.trcc is not None}
    sem_trava = sorted(set(resultados) - set(validos))
    if not validos:
        raise ValueError("Nenhuma questão com trava curricular: não há como agregar o TRCC.")

    micro = sum(r.n_encontrados for r in validos.values()) / sum(r.n_esperados for r in validos.values())
    abaixo = sorted(q for q, r in validos.items() if not r.aprovado(limiar))
    return {
        "n_questoes": len(validos),
        "sem_trava": sem_trava,
        "limiar": limiar,
        "trcc_micro": round(micro, 4),
        "trcc_macro": round(mean(r.trcc for r in validos.values()), 4),
        "pct_questoes_aprovadas": round(100 * (len(validos) - len(abaixo)) / len(validos), 1),
        "questoes_abaixo_do_limiar": abaixo,
        "aprovado_micro": micro >= limiar - _EPS and not sem_trava,
        "aprovado_todas_as_questoes": not abaixo and not sem_trava,
    }
