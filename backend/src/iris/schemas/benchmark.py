"""Schema do dataset de questões escolares (Golden Benchmark, Épico 4.2).

Arquivo de dados: ``data/benchmarks/questoes_escolares_v1.json`` (lista de objetos).
Cada item é validado por ``BenchmarkQuestionItem``; o conjunto, por ``carregar_questoes_escolares``.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Collection
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from iris.eval.trcc import avaliar_trcc

CAMINHO_PADRAO = Path(__file__).resolve().parents[3] / "data" / "benchmarks" / "questoes_escolares_v1.json"
CATALOGOS_PADRAO = Path(__file__).resolve().parents[3] / "rag" / "catalogs"
MINIMO_QUESTOES = 30

AnoEscolar = Literal[
    "6º ano EF", "7º ano EF", "8º ano EF", "9º ano EF", "1ª série EM", "2ª série EM", "3ª série EM"
]
# Taxonomia de Bloom revisada: o que o enunciado pede ao aluno.
OperacaoCognitiva = Literal["lembrar", "compreender", "aplicar", "analisar", "avaliar", "criar"]

# Ex.: EF06MA01, EF67LP28 (Ensino Fundamental); EM13MAT101, EM13LP01 (Ensino Médio).
_BNCC = r"^(EF\d{2}[A-Z]{2}\d{2}|EM13[A-Z]{2,4}\d{2,3})$"


class Alternativa(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    letra: Literal["A", "B", "C", "D", "E"]
    texto: str = Field(min_length=1)


class FonteQuestao(BaseModel):
    """Origem da questão: sem fonte verificável ela não conta como questão pública."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    origem: str = Field(min_length=2, description='Ex.: "ENEM 2023", "SAEB 2021", "OBMEP 2022"')
    url: str | None = Field(default=None, pattern=r"^https?://")
    referencia: str | None = Field(default=None, description='Ex.: "Caderno azul, questão 112"')


class BenchmarkQuestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    disciplina: str = Field(min_length=2)
    ano_escolar: AnoEscolar
    habilidade_bncc: str = Field(pattern=_BNCC)
    enunciado_original: str = Field(min_length=10)
    alternativas: list[Alternativa] | None = Field(
        default=None, description="Somente em questões objetivas; None nas discursivas."
    )
    conceitos_trava_curricular: list[str] = Field(
        min_length=1,
        description='Termos inegociáveis. "a|b" aceita alternativas (ver iris.eval.trcc).',
    )
    operacao_cognitiva: OperacaoCognitiva
    id_caracteristica_alvo: str = Field(min_length=1, description="Id da característica atômica do catálogo.")
    descritor_saeb: str | None = Field(
        default=None, description='Descritor da matriz do SAEB, ex.: "D6 – Identificar o tema de um texto".'
    )
    fonte: FonteQuestao | None = None
    status: Literal["rascunho", "validado"] = "rascunho"

    @field_validator("conceitos_trava_curricular")
    @classmethod
    def _sem_conceito_vazio(cls, v: list[str]) -> list[str]:
        v = [c.strip() for c in v]
        if any(not c for c in v):
            raise ValueError("conceito vazio na trava curricular")
        if len(set(v)) != len(v):
            raise ValueError("conceitos repetidos na trava curricular")
        return v

    @field_validator("alternativas")
    @classmethod
    def _alternativas_validas(cls, v):
        if v is None:
            return v
        letras = [a.letra for a in v]
        if len(v) < 2 or len(set(letras)) != len(letras):
            raise ValueError("questão objetiva exige >= 2 alternativas com letras distintas")
        return v

    @model_validator(mode="after")
    def _trava_esta_no_material_original(self):
        # O TRCC usa os conceitos do material ORIGINAL como denominador: todos precisam estar nele.
        texto = self.enunciado_original + "\n" + "\n".join(a.texto for a in (self.alternativas or []))
        ausentes = avaliar_trcc(self.conceitos_trava_curricular, texto).ausentes
        if ausentes:
            raise ValueError(f"conceitos da trava ausentes do enunciado/alternativas: {list(ausentes)}")
        return self

    @property
    def texto_completo(self) -> str:
        """Enunciado com as alternativas: é o que o aluno de fato lê e o que o sistema adapta."""
        extra = "\n".join(f"{a.letra}) {a.texto}" for a in (self.alternativas or []))
        return self.enunciado_original + ("\n" + extra if extra else "")


def ids_caracteristicas(pasta: str | Path | None = None) -> set[str]:
    """Ids de todas as características dos catálogos (rag/catalogs/*.json, inclusive TEA/Dislexia futuros)."""
    ids: set[str] = set()
    for arq in sorted(Path(pasta or CATALOGOS_PADRAO).glob("*.json")):
        dados = json.loads(arq.read_text(encoding="utf-8"))
        itens = dados if isinstance(dados, list) else next((v for v in dados.values() if isinstance(v, list)), [])
        ids |= {c["id_caracteristica"] for c in itens if isinstance(c, dict) and "id_caracteristica" in c}
    return ids


def validar_conjunto(
    itens: list[BenchmarkQuestionItem],
    minimo: int = MINIMO_QUESTOES,
    catalogo_ids: Collection[str] | None = None,
    exigir_fonte: bool = True,
) -> list[str]:
    """Problemas do conjunto (lista vazia = ok): tamanho, ids, fonte pública, catálogo."""
    problemas = []
    if len(itens) < minimo:
        problemas.append(f"{len(itens)} questões; o mínimo é {minimo}")
    repetidos = [i for i, n in Counter(q.id for q in itens).items() if n > 1]
    if repetidos:
        problemas.append(f"ids repetidos: {repetidos}")
    if exigir_fonte:
        sem = [q.id for q in itens if q.fonte is None]
        if sem:
            problemas.append(f"questões sem fonte (não contam como públicas): {sem}")
    if catalogo_ids is not None:
        fora = sorted({q.id_caracteristica_alvo for q in itens} - set(catalogo_ids))
        if fora:
            problemas.append(f"id_caracteristica_alvo fora do catálogo: {fora}")
    return problemas


def carregar_questoes_escolares(caminho: str | Path | None = None) -> list[BenchmarkQuestionItem]:
    """Carrega e valida cada item. Erros de item dizem qual questão falhou."""
    p = Path(caminho) if caminho else CAMINHO_PADRAO
    bruto = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(bruto, list):
        raise ValueError("O dataset deve ser uma lista de questões.")
    itens = []
    for i, obj in enumerate(bruto):
        try:
            itens.append(BenchmarkQuestionItem.model_validate(obj))
        except Exception as exc:
            qid = obj.get("id", f"#{i}") if isinstance(obj, dict) else f"#{i}"
            raise ValueError(f"Questão {qid} inválida: {exc}") from exc
    return itens


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Valida o dataset de questões escolares.")
    ap.add_argument("caminho", nargs="?", default=None)
    ap.add_argument("--minimo", type=int, default=MINIMO_QUESTOES)
    args = ap.parse_args(argv)
    itens = carregar_questoes_escolares(args.caminho)
    problemas = validar_conjunto(itens, args.minimo, catalogo_ids=ids_caracteristicas() or None)
    print(f"{len(itens)} questões válidas individualmente.")
    for p in problemas:
        print("PROBLEMA:", p)
    raise SystemExit(1 if problemas else 0)


if __name__ == "__main__":
    main()
