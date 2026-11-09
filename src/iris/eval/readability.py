"""Legibilidade (Flesch PT-BR) e densidade de comandos conjugados.

Usado na EDA 2 (baseline do Golden Benchmark) do Épico 4.2.

Uso rápido:
    uv run python -m iris.eval.readability data/golden_benchmark.json

Formato esperado do JSON: lista de objetos com ao menos `id` e `enunciado`.
    [{"id": "Q01", "disciplina": "Ciências", "ano": "6º", "enunciado": "..."}]
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pyphen

# --------------------------------------------------------------------------
# Flesch adaptado ao português (Martins et al., 1996)
#   IFR = 248.835 - 1.015 * (palavras/sentenças) - 84.6 * (sílabas/palavras)
# --------------------------------------------------------------------------

_WORD_RE = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*", re.UNICODE)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")

# left/right = 1 permite dividir palavras curtas (padrão do pyphen é 2/2).
_HYPHENATOR = pyphen.Pyphen(lang="pt_BR", left=1, right=1)


def split_sentences(text: str) -> list[str]:
    """Divide em sentenças por pontuação final ou quebra de linha."""
    parts = (s.strip() for s in _SENT_SPLIT_RE.split(text))
    return [s for s in parts if s and _WORD_RE.search(s)]


def split_words(text: str) -> list[str]:
    """Extrai palavras (ignora números e pontuação)."""
    return _WORD_RE.findall(text)


@lru_cache(maxsize=50_000)
def count_syllables(word: str) -> int:
    """Conta sílabas via hifenização pt_BR (aproximação; mínimo 1)."""
    return max(1, _HYPHENATOR.inserted(word.lower()).count("-") + 1)


def flesch_ptbr(text: str) -> float | None:
    """Índice Flesch PT-BR. Retorna None se o texto não tiver palavras."""
    words = split_words(text)
    sentences = split_sentences(text)
    if not words or not sentences:
        return None
    syllables = sum(count_syllables(w) for w in words)
    asl = len(words) / len(sentences)
    asw = syllables / len(words)
    return 248.835 - 1.015 * asl - 84.6 * asw


def flesch_band(score: float | None) -> str:
    """Faixa de dificuldade (escala de Martins et al.)."""
    if score is None:
        return "n/d"
    if score >= 75:
        return "muito fácil"
    if score >= 50:
        return "fácil"
    if score >= 25:
        return "difícil"
    return "muito difícil"


# --------------------------------------------------------------------------
# Densidade de comandos (verbos de comando em enunciados escolares)
# --------------------------------------------------------------------------

# Formas imperativas (e infinitivas) comuns em enunciados. Sem acento, minúsculas.
COMMAND_VERBS: frozenset[str] = frozenset(
    """
    leia ler responda responder justifique justificar explique explicar
    compare comparar analise analisar identifique identificar calcule calcular
    descreva descrever cite citar marque marcar assinale assinalar complete
    completar relacione relacionar resolva resolver escreva escrever
    diferencie diferenciar classifique classificar defina definir indique
    indicar mencione mencionar observe observar interprete interpretar
    resuma resumir argumente argumentar discuta discutir apresente apresentar
    elabore elaborar demonstre demonstrar determine determinar encontre
    encontrar ligue ligar circule circular sublinhe sublinhar copie copiar
    ordene ordenar organize organizar reescreva reescrever converta converter
    construa construir desenhe desenhar liste listar enumere enumerar
    comente comentar avalie avaliar proponha propor reflita refletir
    pesquise pesquisar produza produzir formule formular crie criar
    exemplifique exemplificar substitua substituir transcreva transcrever
    verifique verificar sugira sugerir nomeie nomear simplifique
    simplificar
    conclua concluir represente representar monte montar escolha escolher confira conferir
    """.split()
)


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def find_commands(text: str) -> list[str]:
    """Lista, em ordem, os verbos de comando encontrados no texto."""
    found: list[str] = []
    for w in split_words(text):
        norm = _strip_accents(w.lower().split("-")[0])
        if norm in COMMAND_VERBS:
            found.append(norm)
    return found


def count_conjugated_commands(text: str) -> int:
    """Quantidade de comandos em uma mesma sentença com 2+ comandos.

    Um comando "conjugado" é aquele que divide a sentença com outro comando
    (ex.: "Leia o texto e responda"). Retorna a soma dos comandos nessas
    sentenças; sentenças com um único comando contam 0.
    """
    total = 0
    for sent in split_sentences(text):
        n = len(find_commands(sent))
        if n >= 2:
            total += n
    return total


# --------------------------------------------------------------------------
# Análise do Golden Benchmark
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class QuestionStats:
    id: str
    n_words: int
    n_sentences: int
    flesch: float | None
    flesch_band: str
    n_commands: int
    n_conjugated_commands: int
    commands_per_100_words: float
    has_conjugated_command: bool


def analyze_question(qid: str, text: str) -> QuestionStats:
    words = split_words(text)
    n_words = len(words)
    n_cmd = len(find_commands(text))
    n_conj = count_conjugated_commands(text)
    score = flesch_ptbr(text)
    return QuestionStats(
        id=qid,
        n_words=n_words,
        n_sentences=len(split_sentences(text)),
        flesch=None if score is None else round(score, 2),
        flesch_band=flesch_band(score),
        n_commands=n_cmd,
        n_conjugated_commands=n_conj,
        commands_per_100_words=round(100 * n_cmd / n_words, 2) if n_words else 0.0,
        has_conjugated_command=n_conj > 0,
    )


def load_questions(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("O JSON do benchmark deve ser uma lista de questões.")
    for i, q in enumerate(data):
        if "enunciado" not in q:
            raise ValueError(f"Questão {i} sem o campo 'enunciado'.")
    return data


def analyze_benchmark(questions: list[dict]) -> pd.DataFrame:
    """DataFrame com uma linha por questão (metadados + métricas)."""
    rows = []
    for i, q in enumerate(questions):
        qid = str(q.get("id", f"Q{i + 1:02d}"))
        stats = analyze_question(qid, q["enunciado"])
        row = {k: v for k, v in q.items() if k != "enunciado"}
        row.update(stats.__dict__)
        row["id"] = qid
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> dict:
    """Baseline agregado: distribuição do Flesch e da densidade de comandos."""
    flesch = df["flesch"].dropna()
    return {
        "n_questoes": int(len(df)),
        "flesch_media": round(float(flesch.mean()), 2) if len(flesch) else None,
        "flesch_mediana": round(float(flesch.median()), 2) if len(flesch) else None,
        "flesch_desvio": round(float(flesch.std()), 2) if len(flesch) > 1 else None,
        "flesch_faixas": df["flesch_band"].value_counts().to_dict(),
        "comandos_por_questao_media": round(float(df["n_commands"].mean()), 2),
        "comandos_por_100_palavras_media": round(
            float(df["commands_per_100_words"].mean()), 2
        ),
        "pct_questoes_com_comando_conjugado": round(
            100 * float(df["has_conjugated_command"].mean()), 1
        ),
    }


def main(argv: list[str] | None = None) -> None:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    path = args[0] if args else "data/golden_benchmark.json"
    df = analyze_benchmark(load_questions(path))
    print(json.dumps(summarize(df), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()