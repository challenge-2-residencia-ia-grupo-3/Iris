"""Gate preventivo Anti-PII e Anti-Clínico para persistência do histórico docente (RNF-01/02/03, ADR-10).

Nenhuma atividade é gravada no PostgreSQL sem antes passar por este módulo:
1. Bloqueia qualquer campo associado a estudante ou perfil portátil (ex.: `codigo_anonimo`, `aluno`, `cpf`, `cid`);
2. Executa `sanitize_pedagogical_note` (`sanitize_pii` + prosa) e `detectar_conteudo_clinico` em título,
   metadados, travas curriculares e em cada questão (`original`, `adaptado`, `justificativas`);
3. Em modo estrito (`auto_sanitizar=False`), recusa a gravação se houver PII ou rótulo clínico;
   com `auto_sanitizar=True`, anonimiza PII irreversivelmente antes de persistir e ainda bloqueia rótulos clínicos.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from iris.schemas.portable_profile import detectar_conteudo_clinico
from iris.security.pii_scrubber import sanitize_pedagogical_note

FORBIDDEN_STUDENT_OR_CLINICAL_KEYS = frozenset(
    {
        "codigo_anonimo",
        "id_anonimo",
        "aluno",
        "aluna",
        "estudante",
        "nome_aluno",
        "nome_estudante",
        "matricula",
        "ra",
        "cpf",
        "rg",
        "turma",
        "escola",
        "laudo",
        "cid",
        "diagnostico",
        "medicacao",
        "prontuario",
    }
)


class ActivityPrivacyViolationError(ValueError):
    """Erro de conformidade LGPD ao tentar salvar material com PII, dado clínico ou vínculo de aluno."""

    def __init__(
        self,
        detail: str,
        *,
        code: str = "PRIVACY_GATE_BLOCKED",
        field: str = "body",
        issues: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.field = field
        self.issues = issues or []
        self.status_code = 422

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "error",
            "code": self.code,
            "field": self.field,
            "detail": str(self),
            "issues": self.issues,
        }


class ActivityQuestionInput(BaseModel):
    """Questão estruturada aceita para persistência no histórico docente."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=64)
    original: str = Field(default="", max_length=10_000)
    adaptado: str = Field(..., min_length=1, max_length=10_000)
    editada: bool = False
    aprovada: bool = False
    justificativas: list[str] = Field(default_factory=list)


class ActivitySavePayload(BaseModel):
    """Contrato validado da atividade antes de passar pelo gate Anti-PII."""

    model_config = ConfigDict(extra="forbid")

    titulo: str = Field(..., min_length=1, max_length=120)
    disciplina: str | None = Field(default=None, max_length=80)
    ano_escolar: str | None = Field(default=None, max_length=60)
    nivel_andaime: int = Field(default=2, ge=1, le=3)
    caracteristicas_ids: list[str] = Field(default_factory=list, max_length=30)
    travas_curriculares: dict[str, Any] = Field(default_factory=dict)
    questoes: list[ActivityQuestionInput] = Field(..., min_length=1, max_length=100)
    metricas: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="rascunho")

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        norm = value.strip().lower()
        if norm not in {"rascunho", "homologada"}:
            raise ValueError("Status deve ser 'rascunho' ou 'homologada'.")
        return norm


@dataclass(frozen=True)
class SanitizedActivityData:
    """Dados da atividade já validados, sanitizados e prontos para gravação no schema `docente`."""

    titulo: str
    disciplina: str | None
    ano_escolar: str | None
    nivel_andaime: int
    caracteristicas_ids: list[str]
    travas_curriculares: dict[str, Any]
    questoes: list[dict[str, Any]]
    metricas: dict[str, Any]
    status: str
    pii_substituicoes: int


def _scan_forbidden_keys(obj: Any, prefix: str = "body") -> None:
    """Rejeita recursivamente chaves proibidas associadas a estudantes ou dados clínicos."""
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            norm = str(key).strip().lower()
            path = f"{prefix}.{key}"
            if norm in FORBIDDEN_STUDENT_OR_CLINICAL_KEYS:
                raise ActivityPrivacyViolationError(
                    f"Campo '{key}' não é permitido no histórico docente: nenhum identificador de estudante ou dado clínico pode ser salvo.",
                    code="FORBIDDEN_STUDENT_OR_CLINICAL_FIELD",
                    field=path,
                )
            _scan_forbidden_keys(value, path)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _scan_forbidden_keys(item, f"{prefix}[{idx}]")


def _process_text(
    text: str,
    field_path: str,
    *,
    auto_sanitizar: bool,
    allow_pii_sanitization: bool,
    issues: list[dict[str, str]],
) -> tuple[str, int]:
    """Verifica PII e termos clínicos em um campo textual."""
    clinicos = detectar_conteudo_clinico(text, field_path)
    if clinicos:
        categorias = sorted({v.categoria for v in clinicos})
        issues.append(
            {
                "field": field_path,
                "type": "clinical",
                "detail": f"Referência clínica detectada ({', '.join(categorias)}). Remova laudos, CIDs ou medicações antes de salvar.",
            }
        )

    sanitized, count = sanitize_pedagogical_note(text)
    if count > 0:
        if not allow_pii_sanitization or not auto_sanitizar:
            issues.append(
                {
                    "field": field_path,
                    "type": "pii",
                    "detail": "Possível dado pessoal identificável detectado. Remova-o ou habilite a sanitização automática.",
                }
            )
            return text, 0
        return sanitized, count
    return text, 0


def _process_nested(
    value: Any,
    field_path: str,
    *,
    auto_sanitizar: bool,
    issues: list[dict[str, str]],
) -> tuple[Any, int]:
    """Percorre estruturas JSON (travas/métricas) garantindo ausência de PII e termos clínicos."""
    if isinstance(value, str):
        return _process_text(
            value,
            field_path,
            auto_sanitizar=auto_sanitizar,
            allow_pii_sanitization=True,
            issues=issues,
        )
    if isinstance(value, list):
        out_list: list[Any] = []
        total = 0
        for idx, item in enumerate(value):
            clean_item, c = _process_nested(item, f"{field_path}[{idx}]", auto_sanitizar=auto_sanitizar, issues=issues)
            out_list.append(clean_item)
            total += c
        return out_list, total
    if isinstance(value, Mapping):
        out_dict: dict[str, Any] = {}
        total = 0
        for k, v in value.items():
            clean_v, c = _process_nested(v, f"{field_path}.{k}", auto_sanitizar=auto_sanitizar, issues=issues)
            out_dict[str(k)] = clean_v
            total += c
        return out_dict, total
    return value, 0


def validate_and_prepare_activity(
    raw_payload: Mapping[str, Any] | ActivitySavePayload,
    *,
    auto_sanitizar: bool = False,
) -> SanitizedActivityData:
    """Valida contrato e aplica o Gate Anti-PII/Anti-Clínico antes de qualquer gravação no PostgreSQL."""
    if isinstance(raw_payload, Mapping):
        _scan_forbidden_keys(raw_payload)
        try:
            model = ActivitySavePayload.model_validate(raw_payload)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            loc = ".".join(str(p) for p in first.get("loc", ())) or "body"
            msg = str(first.get("msg") or "Payload de atividade inválido.")
            raise ActivityPrivacyViolationError(msg, code="INVALID_ACTIVITY_PAYLOAD", field=loc) from exc
    else:
        _scan_forbidden_keys(raw_payload.model_dump())
        model = raw_payload

    issues: list[dict[str, str]] = []
    total_pii = 0

    # Título, disciplina e ano escolar nunca aceitam PII nem termos clínicos (nem via auto_sanitizar)
    titulo_limpo = " ".join(model.titulo.split())
    titulo_limpo, c = _process_text(
        titulo_limpo,
        "titulo",
        auto_sanitizar=False,
        allow_pii_sanitization=False,
        issues=issues,
    )
    total_pii += c

    disciplina_limpa = model.disciplina.strip() if model.disciplina and model.disciplina.strip() else None
    if disciplina_limpa:
        disciplina_limpa, c = _process_text(
            disciplina_limpa,
            "disciplina",
            auto_sanitizar=False,
            allow_pii_sanitization=False,
            issues=issues,
        )
        total_pii += c

    ano_limpo = model.ano_escolar.strip() if model.ano_escolar and model.ano_escolar.strip() else None
    if ano_limpo:
        ano_limpo, c = _process_text(
            ano_limpo,
            "ano_escolar",
            auto_sanitizar=False,
            allow_pii_sanitization=False,
            issues=issues,
        )
        total_pii += c

    travas_limpas, c = _process_nested(
        model.travas_curriculares,
        "travas_curriculares",
        auto_sanitizar=auto_sanitizar,
        issues=issues,
    )
    total_pii += c

    metricas_limpas, c = _process_nested(
        model.metricas,
        "metricas",
        auto_sanitizar=auto_sanitizar,
        issues=issues,
    )
    total_pii += c

    questoes_limpas: list[dict[str, Any]] = []
    for idx, q in enumerate(model.questoes):
        orig_clean, c1 = _process_text(
            q.original,
            f"questoes[{idx}].original",
            auto_sanitizar=auto_sanitizar,
            allow_pii_sanitization=True,
            issues=issues,
        )
        adap_clean, c2 = _process_text(
            q.adaptado,
            f"questoes[{idx}].adaptado",
            auto_sanitizar=auto_sanitizar,
            allow_pii_sanitization=True,
            issues=issues,
        )
        just_clean, c3 = _process_nested(
            q.justificativas,
            f"questoes[{idx}].justificativas",
            auto_sanitizar=auto_sanitizar,
            issues=issues,
        )
        total_pii += c1 + c2 + c3
        questoes_limpas.append(
            {
                "id": q.id,
                "original": orig_clean,
                "adaptado": adap_clean,
                "editada": q.editada,
                "aprovada": q.aprovada,
                "justificativas": just_clean,
            }
        )

    if issues:
        has_clinical = any(item["type"] == "clinical" for item in issues)
        code = "CLINICAL_DATA_BLOCKED" if has_clinical else "PII_DETECTED"
        raise ActivityPrivacyViolationError(
            "A gravação foi bloqueada pelo gate de privacidade: remova dados pessoais ou referências clínicas antes de salvar no histórico.",
            code=code,
            field=issues[0]["field"],
            issues=issues,
        )

    caracteristicas_limpas = list(
        dict.fromkeys(str(item).strip() for item in model.caracteristicas_ids if str(item).strip())
    )

    return SanitizedActivityData(
        titulo=titulo_limpo,
        disciplina=disciplina_limpa,
        ano_escolar=ano_limpo,
        nivel_andaime=model.nivel_andaime,
        caracteristicas_ids=caracteristicas_limpas,
        travas_curriculares=travas_limpas,
        questoes=questoes_limpas,
        metricas=metricas_limpas,
        status=model.status,
        pii_substituicoes=total_pii,
    )
