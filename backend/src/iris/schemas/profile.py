"""Perfil Pedagógico Portátil e bloqueio de dados clínicos (História 3.1.3 / Issue #28; RF-15, RNF-03).

O perfil guarda SOMENTE barreiras funcionais observadas em sala e o histórico de estratégias
didáticas. É proibido armazenar CID, laudos, diagnósticos formais ou medicação.

Duas camadas, como pede o RNF-03:
  1. schema Pydantic estrito (`extra="forbid"`): atributo não declarado é rejeitado;
  2. validador de conteúdo: varre chaves E valores (recursivamente) atrás de padrões de CID, laudos,
     nomes de transtornos, medicamentos e dosagens, e rejeita com orientação ao docente.

Privacidade: `str(exc)` NUNCA repete o trecho digitado (pode ir para logs); o trecho fica em
`exc.violacoes[i].trecho` e só sai em `to_dict(incluir_trecho=True)`, para a interface.

Limitações assumidas: lista de termos finita (nomes novos de medicamentos/transtornos exigem atualização
das constantes) e sem lematização. Deficiências sensoriais/físicas (ex.: "baixa visão") NÃO são bloqueadas por
serem informação de acessibilidade; o time pode mudar isso nas constantes abaixo.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

CODIGO_BLOQUEIO = "CLINICAL_DATA_BLOCKED"
CODIGO_ESTRUTURA = "INVALID_STRUCTURE"
CODIGO_JSON = "INVALID_JSON"

ORIENTACOES = {
    "cid": (
        "Códigos CID não podem ser guardados no perfil. Descreva o que você observa em sala, por exemplo: "
        "\"perde o fio da meada em textos longos\"."
    ),
    "laudo": (
        "Laudos, atestados e relatórios clínicos não entram no perfil pedagógico. Registre apenas as barreiras "
        "funcionais observadas em sala e as estratégias que funcionaram."
    ),
    "diagnostico": (
        "Diagnósticos formais e nomes de transtornos não entram no perfil. Descreva o comportamento observável, por "
        "exemplo: \"precisa de enunciados curtos e divididos em etapas\"."
    ),
    "medicacao": (
        "Informações sobre medicação, receitas ou doses não entram no perfil. Mantenha apenas observações pedagógicas."
    ),
}


# ---------------------------------------------------------------- detecção

def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t.casefold()).strip()


# CID: aplicado ao texto ORIGINAL (maiúsculas importam: "Q10" de uma questão não é CID).
_PADROES_CID = (
    re.compile(r"\bCID(?:[\s-]*1[01])?\b"),  # sigla em maiúsculas ("Cid" é nome próprio)
    re.compile(r"(?i)\bcid[\s:-]*(?:1[01][\s:-]*)?[a-z]\s?\d{2}"),  # "cid f90", "cid f 90", "cid-10: F84"
    re.compile(r"\b[A-TV-Z]\d{2}\.\d{1,2}\b"),  # F90.0, F84.5
    re.compile(r"\bF\d{2}\b"),  # capítulo F (transtornos mentais): F90, F84
    re.compile(r"\b6[A-E]\d{2}(?:\.\d{1,2})?\b"),  # CID-11: 6A05, 6A02
)
# Siglas que, em minúsculas, são palavras comuns ("toc toc", "tea"): só contam em maiúsculas, com ou sem pontos.
_PADROES_SIGLA = (
    re.compile(r"\b(?:T\.?D\.?A\.?H|T\.?D\.?A|T\.?E\.?A|T\.?O\.?D|T\.?O\.?C|T\.?G\.?D)\b\.?"),
)
# Demais categorias: texto normalizado (sem acento, minúsculas).
_PADROES_NORM: dict[str, tuple[re.Pattern[str], ...]] = {
    "cid": (re.compile(r"\bclassificacao internacional de doencas\b"),),
    "laudo": tuple(re.compile(p) for p in (
        r"\blaud(?:o|os|ar|ado|ada)\b",
        r"\batestados? medic\w+",
        r"\bpareceres? (?:medic|clinic|psiquiatric|neurologic)\w*",
        r"\bprontuarios?\b",
        r"\brece(?:ita|itas) medic\w+|\breceituarios?\b|\breceitas? (?:de|do|dos) (?:remedio|medicamento)s?",
        r"\brelatorios? (?:medic|clinic|neurologic|psiquiatric)\w*",
        r"\bhistoricos? (?:medic|clinic)\w*",
        r"\bexames? (?:medic|clinic|neurologic|de imagem)\w*",
        r"\bencaminhamentos? (?:medic|clinic)\w*",
        r"\bneuropsicologic[oa]s?\b",
    )),
    "diagnostico": tuple(re.compile(p) for p in (
        # "diagnóstico" sozinho é termo pedagógico ("diagnóstico inicial da turma"); só conta com qualificador
        # clínico ou com verbo de posse ("tem diagnóstico").
        r"\bdiagnosticos? (?:medic|clinic|neurologic|psiquiatric|psicologic|formal|fechado|definitivo)\w*",
        r"\b(?:tem|possui|recebeu|recebe|aguarda|aguardando|com|sem|em investigacao de) (?:um |o )?diagnostico\b",
        r"\bdiagnosticad[oa]s?\b|\bdiagnosticou\b",
        r"\bt\.?d\.?a\.?h\b|\btgd\b",
        r"\bautis(?:mo|ta|tas)\b|\basperger\b|\b(?:no|do) espectro\b",
        r"\b(?:dislexia|discalculia|disgrafia|disortografia|dislexic[oa]s?)\b",
        # "transtorno" sozinho é incômodo ("a troca de sala causou transtorno"); clínico vem com complemento.
        r"\btranstornos? (?:de|do|da|dos|das|global|opositor|obsessivo|bipolar|desafiador)\b",
        r"\bsindromes?\b",
        r"\bdeficit de atencao\b|\bhiperatividade\b",
        r"\b(?:bipolar|esquizofreni\w*|epilepsia|convulsa\w+|paralisia cerebral)\b",
    )),
    "medicacao": tuple(re.compile(p) for p in (
        r"\b(?:metilfenidato|ritalina|venvanse|lisdexanfetamina|atomoxetina|strattera|risperidona|"
        r"risperdal|aripiprazol|haloperidol|fluoxetina|sertralina|amitriptilina|imipramina|clonazepam|rivotril|"
        r"diazepam|carbamazepina|valproato|anfetamina)\b",
        # "concerta" também é verbo ("ele concerta os erros"): só conta como remédio após tomar/usar.
        r"\b(?:tom\w*|us[ao]\w*|uso de|medicad\w* com)\s+(?:o |a )?concerta\b",
        r"\bmedica(?:cao|coes|mento|mentos)\b|\bremedios?\b",
        r"\bpsicotropic\w*|\bantidepressiv\w*|\bansiolitic\w*|\bantipsicotic\w*|\banticonvulsiv\w*",
        r"\bpsiquiatr\w*|\bneurologist\w*|\bneuropediatr\w*",
        # "ml" fica de fora: "garrafa de 500 ml" é aula de volume, não dose.
        r"\b\d+(?:[.,]\d+)?\s?(?:mg|mcg|gotas|comprimidos?)\b",
    )),
}
_CHAVES_CID = {"cid", "cid10", "cid11", "cid_10", "cid_11"}
_CHAVES_DIAGNOSTICO = {"diagnostico", "diagnosticos", "transtorno", "transtornos"}


@dataclass(frozen=True)
class ViolacaoClinica:
    campo: str  # caminho no perfil, ex.: "barreiras_observadas[0].observacao"
    categoria: str  # cid | laudo | diagnostico | medicacao
    trecho: str  # o que foi digitado (NÃO vai em str(exc))

    def to_dict(self, incluir_trecho: bool = True) -> dict[str, str]:
        # Sem o trecho, o caminho também é mascarado: um nome de campo não declarado pode ser o próprio dado clínico.
        campo = self.campo if incluir_trecho else _campo_seguro(self.campo)
        d = {"campo": campo, "categoria": self.categoria, "orientacao": ORIENTACOES[self.categoria]}
        if incluir_trecho:
            d["trecho"] = self.trecho
        return d


_RE_SEGMENTO = re.compile(r"\[\d+\]|[^.\[\]]+")


def _campo_seguro(campo: str) -> str:
    """Caminho do campo sem nomes não declarados no schema (que podem conter o dado clínico, ex.: "laudo_tdah")."""
    partes = []
    for seg in _RE_SEGMENTO.findall(campo):
        if seg.startswith("["):
            partes.append(seg)
        else:
            partes.append(("." if partes else "") + (seg if seg in _CAMPOS_DECLARADOS else "<campo não declarado>"))
    return "".join(partes)


def detectar_conteudo_clinico(texto: str, campo: str = "", eh_chave: bool = False) -> list[ViolacaoClinica]:
    achados: list[ViolacaoClinica] = []
    if eh_chave and _norm(texto).replace(" ", "_") in _CHAVES_CID:
        achados.append(ViolacaoClinica(campo, "cid", texto))
    # Como nome de campo, "diagnostico" e "transtorno" não têm sentido pedagógico: contam mesmo sem complemento.
    if eh_chave and _CHAVES_DIAGNOSTICO & set(re.split(r"[\s_-]+", _norm(texto))):
        achados.append(ViolacaoClinica(campo, "diagnostico", texto))
    for p in _PADROES_CID:
        achados += [ViolacaoClinica(campo, "cid", m.group(0)) for m in p.finditer(texto)]
    for p in _PADROES_SIGLA:
        achados += [ViolacaoClinica(campo, "diagnostico", m.group(0)) for m in p.finditer(texto)]
    base = _norm(texto.replace("_", " ") if eh_chave else texto)
    for categoria, padroes in _PADROES_NORM.items():
        for p in padroes:
            achados += [ViolacaoClinica(campo, categoria, m.group(0)) for m in p.finditer(base)]
    vistos, unicos = set(), []
    for v in achados:
        k = (v.campo, v.categoria, _norm(v.trecho))
        if k not in vistos:
            vistos.add(k)
            unicos.append(v)
    return unicos


# Campos de formato fechado, já restritos por padrão no schema: o valor não é texto livre. Um código anônimo
# aleatório como "F12-x9" é válido e seria lido como CID.
_CAMPOS_SEM_VARREDURA = frozenset({"codigo_anonimo", "versao_schema"})


def varrer(obj: Any, caminho: str = "") -> list[ViolacaoClinica]:
    """Percorre dicts/listas/strings; examina chaves e valores."""
    if isinstance(obj, str):
        return detectar_conteudo_clinico(obj, caminho)
    if isinstance(obj, Mapping):
        achados: list[ViolacaoClinica] = []
        for k, v in obj.items():
            sub = f"{caminho}.{k}" if caminho else str(k)
            achados += detectar_conteudo_clinico(str(k), sub, eh_chave=True)
            if not caminho and k in _CAMPOS_SEM_VARREDURA:
                continue
            achados += varrer(v, sub)
        return achados
    if isinstance(obj, (list, tuple)):
        return [x for i, v in enumerate(obj) for x in varrer(v, f"{caminho}[{i}]")]
    return []


class ConteudoClinicoError(ValueError):
    def __init__(self, violacoes: list[ViolacaoClinica]) -> None:
        self.violacoes = tuple(violacoes)
        locais = "; ".join(f"'{_campo_seguro(v.campo) or 'perfil'}' ({v.categoria})" for v in violacoes)
        orient = " ".join(dict.fromkeys(ORIENTACOES[v.categoria] for v in violacoes))
        super().__init__(
            f"Dados clínicos não são permitidos no Perfil Pedagógico Portátil (RNF-03). Encontrado em: {locais}. {orient}"
        )


# ---------------------------------------------------------------- schema

class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _bloquear_clinico(cls, dados: Any) -> Any:
        if isinstance(dados, Mapping):
            achados = varrer(dados)
            if achados:
                raise ConteudoClinicoError(achados)
        return dados


# mesmo padrão de iris.schemas.catalog.RE_ID_ATOMICO
_ID_CARACTERISTICA = r"^[a-z][a-z0-9_]{5,80}$"


class BarreiraObservada(_Base):
    id_caracteristica: str = Field(pattern=_ID_CARACTERISTICA)
    observacao: str | None = Field(default=None, max_length=500)


class RegistroEstrategia(_Base):
    estrategia: str = Field(min_length=3, max_length=300)
    resultado: Literal["eficaz", "ineficaz"]
    id_caracteristica: str | None = Field(default=None, pattern=_ID_CARACTERISTICA)
    observacao: str | None = Field(default=None, max_length=500)


class PerfilPedagogico(_Base):
    versao_schema: Literal["1.0"] = "1.0"
    codigo_anonimo: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{2,39}$")
    barreiras_observadas: list[BarreiraObservada] = Field(default_factory=list, max_length=50)
    historico_estrategias: list[RegistroEstrategia] = Field(default_factory=list, max_length=200)
    anotacoes_pedagogicas: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _tamanho_das_anotacoes(self) -> "PerfilPedagogico":
        if any(len(a) > 1000 for a in self.anotacoes_pedagogicas):
            raise ValueError("Cada anotação pedagógica deve ter no máximo 1000 caracteres.")
        return self


_CAMPOS_DECLARADOS = frozenset(
    nome for modelo in (PerfilPedagogico, BarreiraObservada, RegistroEstrategia) for nome in modelo.model_fields
)


# ---------------------------------------------------------------- validação para importação/API

class PerfilInvalidoError(ValueError):
    def __init__(self, codigo: str, mensagens: list[str], violacoes: tuple[ViolacaoClinica, ...] = ()) -> None:
        super().__init__(" ".join(mensagens))
        self.codigo, self.mensagens, self.violacoes = codigo, list(mensagens), violacoes

    def to_dict(self, incluir_trecho: bool = True) -> dict[str, Any]:
        return {"detail": str(self), "code": self.codigo, "field": "perfil",
                "violacoes": [v.to_dict(incluir_trecho) for v in self.violacoes]}


def _traduzir(exc: ValidationError) -> PerfilInvalidoError:
    msgs, violacoes = [], []
    for e in exc.errors():
        original = (e.get("ctx") or {}).get("error")
        local = ".".join(str(x) for x in e["loc"]) or "perfil"
        if isinstance(original, ConteudoClinicoError):
            violacoes += original.violacoes
            msgs.append(str(original))
        elif e["type"] == "extra_forbidden":
            msgs.append(f"O campo '{local}' não faz parte do Perfil Pedagógico Portátil e foi rejeitado.")
        else:
            msgs.append(f"Campo '{local}': {e['msg']}")
    msgs = list(dict.fromkeys(msgs))
    return PerfilInvalidoError(CODIGO_BLOQUEIO if violacoes else CODIGO_ESTRUTURA, msgs, tuple(violacoes))


def validar_perfil(dados: Mapping[str, Any] | str | bytes) -> PerfilPedagogico:
    """Valida o perfil (JSON em texto ou dict), p.ex. na reimportação (RF-15). Levanta PerfilInvalidoError."""
    if isinstance(dados, (str, bytes)):
        try:
            dados = json.loads(dados)
        except json.JSONDecodeError as exc:
            raise PerfilInvalidoError(CODIGO_JSON, ["O arquivo do perfil não é um JSON válido."]) from exc
    if not isinstance(dados, Mapping):
        raise PerfilInvalidoError(CODIGO_ESTRUTURA, ["O perfil deve ser um objeto JSON."])
    try:
        return PerfilPedagogico.model_validate(dados)
    except ValidationError as exc:
        raise _traduzir(exc) from exc
