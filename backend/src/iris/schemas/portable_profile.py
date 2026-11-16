"""Perfil Pedagógico Portátil (Histórias 3.1.1 / #26 e 3.1.3 / #28; RF-15, RNF-01, RNF-03).

Identificação (#26, RNF-01): o perfil é identificado só por um código aleatório (`aluno-8f7a2c1b`), gerado por
`gerar_codigo_anonimo()` sem nenhuma entrada do usuário, logo sem nome nem dado pessoal. Tudo vive em memória: este
módulo não importa banco de dados, não abre arquivos e não usa rede (há testes que verificam isso). Quem recebe o
objeto (ex.: a rota de download) é quem entrega o JSON ao navegador; o servidor não guarda cópia.

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
import uuid
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

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
    texto = texto.replace("_", " ")  # "tdah_formal" e "F90_x": o sublinhado separa palavras
    for p in _PADROES_CID:
        achados += [ViolacaoClinica(campo, "cid", m.group(0)) for m in p.finditer(texto)]
    for p in _PADROES_SIGLA:
        achados += [ViolacaoClinica(campo, "diagnostico", m.group(0)) for m in p.finditer(texto)]
    base = _norm(texto)
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


# Campos de formato fechado, já restritos por padrão no schema: o valor não é texto livre.
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


PREFIXO_CODIGO = "aluno-"
_PADRAO_CODIGO = r"^aluno-[0-9a-f]{8,32}$"
IdCaracteristica = Annotated[str, StringConstraints(pattern=_ID_CARACTERISTICA)]


def gerar_codigo_anonimo(n_hex: int = 8) -> str:
    """Código aleatório (UUID4) sem relação com nome ou dado do estudante, ex.: `aluno-8f7a2c1b`.

    Não recebe nenhum dado do usuário de propósito. Com 8 hex (32 bits) a chance de colisão fica em ~1% perto de
    9 mil perfis; como não há banco para checar unicidade, use `n_hex` maior se isso importar.
    """
    if not 8 <= n_hex <= 32:
        raise ValueError("n_hex deve estar entre 8 e 32.")
    return PREFIXO_CODIGO + uuid.uuid4().hex[:n_hex]


class PerfilPedagogico(_Base):
    versao_schema: Literal["1.0"] = "1.0"
    codigo_anonimo: str = Field(pattern=_PADRAO_CODIGO)
    criado_em: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    caracteristicas_selecionadas: list[IdCaracteristica] = Field(default_factory=list, max_length=50)
    barreiras_observadas: list[BarreiraObservada] = Field(default_factory=list, max_length=50)
    historico_estrategias: list[RegistroEstrategia] = Field(default_factory=list, max_length=200)
    anotacoes_pedagogicas: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _regras_finais(self) -> "PerfilPedagogico":
        if any(len(a) > 1000 for a in self.anotacoes_pedagogicas):
            raise ValueError("Cada anotação pedagógica deve ter no máximo 1000 caracteres.")
        if len(set(self.caracteristicas_selecionadas)) != len(self.caracteristicas_selecionadas):
            raise ValueError("caracteristicas_selecionadas não pode ter itens repetidos.")
        return self

    def para_json(self) -> dict[str, Any]:
        """Estrutura serializável (datas em ISO 8601) para entregar ao navegador. Não grava nada."""
        return self.model_dump(mode="json")


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


def criar_perfil(
    caracteristicas_selecionadas: Iterable[str], ids_validos: Collection[str] | None = None
) -> PerfilPedagogico:
    """Cria um perfil novo EM MEMÓRIA: código aleatório, data (UTC) e características selecionadas (#26).

    `ids_validos` (opcional) é o conjunto de ids do catálogo; se informado, id fora dele é erro. Nada é gravado.
    """
    ids = list(dict.fromkeys(caracteristicas_selecionadas))
    if ids_validos is not None:
        desconhecidos = [i for i in ids if i not in set(ids_validos)]
        if desconhecidos:
            raise PerfilInvalidoError(
                CODIGO_ESTRUTURA, [f"Característica(s) não encontrada(s) no catálogo: {desconhecidos}."]
            )
    return validar_perfil({"codigo_anonimo": gerar_codigo_anonimo(), "caracteristicas_selecionadas": ids})
