"""Schemas Pydantic e catálogo de engajamento do estudante (História 1.2.2 — Issue #9).

Atende:
- RF-05: Registro de potencialidades, interesses temáticos e canais preferenciais de engajamento.
- RNF-02 / RNF-03: Sanitização preventiva de PII em texto livre e bloqueio de dados clínicos/CID (`extra='forbid'`).
- RNF-06: Vínculo explícito ao Princípio I do DUA (Rede de Engajamento / Múltiplas Formas de Engajamento)
  e regra de não-substituição dos conceitos obrigatórios da Trava Curricular.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from iris.security.pii_scrubber import detect_clinical_reference, sanitize_pedagogical_note

DUA_PRINCIPLE_ID = "principio_1_engajamento"
DUA_PRINCIPLE_LABEL = "Princípio I do DUA — Rede de Engajamento (Múltiplas Formas de Engajamento)"
DUA_PRINCIPLE_REFERENCE = (
    "CAST / DUA — Recrutamento de Interesse (Ponto 7.2: otimizar relevância, valor e autenticidade) "
    "e Sustentação do Esforço"
)
NON_SUBSTITUTION_RULE = (
    "Os interesses temáticos, potencialidades e canais de engajamento atuam exclusivamente como "
    "âncoras motivacionais periféricas (contexto de exemplo, analogia ou formato de apoio). "
    "É estritamente proibido substituir, omitir ou simplificar conceitos obrigatórios, termos técnicos "
    "ou verbos cognitivos exigidos pela Trava Curricular (TRCC >= 95%)."
)

MAX_POTENTIALITIES_CHARS = 500
MAX_CUSTOM_INTERESTS = 5
MAX_CUSTOM_INTEREST_CHARS = 60

THEMATIC_INTERESTS_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "esportes",
        "rotulo": "Esportes e Movimento",
        "descricao": "Exemplos ligados a modalidades esportivas, placares, treinos e trabalho em equipe.",
        "ancora_sugerida": "Contextualizar analogias periféricas usando situações de jogo, regras ou pontuação esportiva.",
    },
    {
        "id": "natureza",
        "rotulo": "Natureza e Meio Ambiente",
        "descricao": "Temáticas de ecossistemas, animais, plantas, clima e sustentabilidade.",
        "ancora_sugerida": "Empregar exemplos ilustrativos ligados a fenômenos naturais, fauna ou observação ambiental.",
    },
    {
        "id": "tecnologia",
        "rotulo": "Tecnologia e Inovação",
        "descricao": "Interesse por dispositivos digitais, robótica, aplicativos, programação e invenções.",
        "ancora_sugerida": "Relacionar cenários introdutórios a ferramentas digitais, lógica de sistemas ou protótipos.",
    },
    {
        "id": "artes_musica",
        "rotulo": "Artes, Música e Cultura",
        "descricao": "Expressões visuais, ritmo, cinema, quadrinhos, teatro e produção cultural.",
        "ancora_sugerida": "Utilizar metáforas visuais, referências rítmicas ou conexões com produções culturais.",
    },
    {
        "id": "jogos_logica",
        "rotulo": "Jogos e Desafios Lógicos",
        "descricao": "Tabuleiros, quebra-cabeças, missões, enigmas e desafios por fases.",
        "ancora_sugerida": "Apresentar instruções introdutórias com senso de missão ou progresso em etapas.",
    },
    {
        "id": "ciencias_praticas",
        "rotulo": "Ciências Práticas e Experimentos",
        "descricao": "Curiosidade por experimentos práticos, culinária científica, astronomia e laboratório.",
        "ancora_sugerida": "Ancorar a motivação em situações de investigação prática ou observação experimental.",
    },
    {
        "id": "narrativa_historica",
        "rotulo": "Narrativas e Histórias",
        "descricao": "Contação de histórias, biografias, mistérios históricos e linhas do tempo.",
        "ancora_sugerida": "Enquadrar o contexto introdutório com sequência narrativa clara e personagens situacionais.",
    },
    {
        "id": "cotidiano_pratico",
        "rotulo": "Cotidiano e Vida Prática",
        "descricao": "Situações reais do dia a dia, compras, transporte, organização pessoal e comunidade.",
        "ancora_sugerida": "Conectar o apoio introdutório a cenários concretos vivenciados fora da escola.",
    },
)

ENGAGEMENT_CHANNELS_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "esquemas_visuais",
        "rotulo": "Esquemas Visuais e Mapas",
        "descricao": "Facilidade com diagramas, tabelas organizadoras, ícones e mapas mentais.",
        "estrategia_apoio": "Priorizar organização visual limpa, marcadores estruturados e quadros-síntese de apoio.",
    },
    {
        "id": "exemplos_concretos",
        "rotulo": "Exemplos Concretos Antes da Abstração",
        "descricao": "Engaja melhor quando visualiza uma situação prática antes da regra abstrata.",
        "estrategia_apoio": "Inserir âncora motivacional concreta na contextualização sem resolver a questão avaliada.",
    },
    {
        "id": "etapas_curtas_gamificadas",
        "rotulo": "Metas Curtas e Progresso Visível",
        "descricao": "Responde bem a checkpoints rápidos e sensação de avanço passo a passo.",
        "estrategia_apoio": "Sinalizar marcos curtos de progressão para sustentar o esforço ao longo da tarefa.",
    },
    {
        "id": "narrativas_contextualizadas",
        "rotulo": "Narrativas Contextualizadas",
        "descricao": "Sustenta atenção quando há fio condutor ou propósito claro na atividade.",
        "estrategia_apoio": "Conectar o enunciado a um contexto motivador breve mantendo 100% do rigor conceitual.",
    },
    {
        "id": "recursos_audiovisuais",
        "rotulo": "Apoio Audiovisual e Oralidade",
        "descricao": "Facilidade ao explicar oralmente ou associar conceitos a recursos multimídia.",
        "estrategia_apoio": "Sugerir roteiros breves de verbalização ou checagem oral como apoio complementar.",
    },
    {
        "id": "mao_na_massa_cinestesico",
        "rotulo": "Exploração Prática / Mão na Massa",
        "descricao": "Maior envolvimento com tarefas ativas, manipuláveis ou simulação prática.",
        "estrategia_apoio": "Sugerir rascunho ativo, sublinhado guiado ou registro manipulável durante a resolução.",
    },
)

THEMATIC_INTERESTS_BY_ID: dict[str, dict[str, str]] = {
    item["id"]: item for item in THEMATIC_INTERESTS_CATALOG
}
ENGAGEMENT_CHANNELS_BY_ID: dict[str, dict[str, str]] = {
    item["id"]: item for item in ENGAGEMENT_CHANNELS_CATALOG
}

ALLOWED_ENGAGEMENT_FIELDS = frozenset(
    {
        "interesses_tematicos",
        "interesses_customizados",
        "potencialidades",
        "canais_engajamento_preferenciais",
    }
)


class EngagementValidationError(ValueError):
    """Erro de validação nos metadados opcionais de potencialidades e engajamento (História 1.2.2)."""

    def __init__(self, message: str, code: str, field: str = "engagement_profile") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field

    def to_dict(self) -> dict[str, str]:
        return {"detail": self.message, "code": self.code, "field": self.field}


def get_engagement_options_catalog() -> dict[str, Any]:
    """Retorna as opções oficiais de interesses temáticos e canais preferenciais (Princípio I DUA)."""
    return {
        "principio_dua": DUA_PRINCIPLE_ID,
        "principio_dua_rotulo": DUA_PRINCIPLE_LABEL,
        "diretriz_dua_referencia": DUA_PRINCIPLE_REFERENCE,
        "obrigatorio": False,
        "exige_laudo_medico": False,
        "aviso_lgpd": (
            "Campos opcionais voltados exclusivamente às potencialidades e interesses temáticos "
            "do estudante (Princípio I do DUA). Não informe nomes próprios, dados civis ou diagnósticos clínicos."
        ),
        "regra_nao_substituicao": NON_SUBSTITUTION_RULE,
        "interesses_tematicos": [dict(item) for item in THEMATIC_INTERESTS_CATALOG],
        "canais_engajamento_preferenciais": [dict(item) for item in ENGAGEMENT_CHANNELS_CATALOG],
    }


@dataclass
class EngagementMetadata:
    """Metadados estruturados de potencialidades e engajamento anexados ao contexto de geração."""

    principio_dua: str
    principio_dua_rotulo: str
    diretriz_dua_referencia: str
    interesses_tematicos: list[dict[str, str]]
    interesses_customizados: list[str]
    potencialidades: str | None
    canais_engajamento_preferenciais: list[dict[str, str]]
    possui_ancoras_motivacionais: bool
    sanitized: bool
    pii_removed_count: int
    regra_nao_substituicao: str = NON_SUBSTITUTION_RULE

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


def _sanitize_and_validate_free_text(raw_text: str, field_name: str, max_len: int) -> tuple[str, int]:
    cleaned = raw_text.strip()
    if len(cleaned) > max_len:
        raise EngagementValidationError(
            message=f"O campo '{field_name}' excede o limite de {max_len} caracteres ({len(cleaned)} informados).",
            code="ENGAGEMENT_TEXT_TOO_LONG",
            field=field_name,
        )

    clinical_term = detect_clinical_reference(cleaned)
    if clinical_term is not None:
        raise EngagementValidationError(
            message=(
                f"Referência clínica ou medicamentosa detectada no campo '{field_name}' ('{clinical_term}'). "
                "Informe apenas potencialidades pedagógicas e interesses observáveis, sem CID, laudo ou medicação (RNF-03)."
            ),
            code="CLINICAL_CONTENT_FORBIDDEN",
            field=field_name,
        )

    sanitized, pii_count = sanitize_pedagogical_note(cleaned)
    return sanitized, pii_count


def _dedupe_str_list(raw_val: Any, field_name: str) -> list[str]:
    if raw_val is None:
        return []
    if not isinstance(raw_val, list):
        raise EngagementValidationError(
            message=f"O campo '{field_name}' deve ser uma lista de textos.",
            code="INVALID_ENGAGEMENT_FIELD_TYPE",
            field=field_name,
        )
    result: list[str] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw_val):
        if not isinstance(item, str):
            raise EngagementValidationError(
                message=f"Item {idx} do campo '{field_name}' deve ser uma string.",
                code="INVALID_ENGAGEMENT_ITEM_TYPE",
                field=field_name,
            )
        norm = item.strip()
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


# Schema Pydantic v2 oficial (com fallback compatível para execução sem dependências externas)
try:
    from pydantic import BaseModel, ConfigDict, Field, field_validator

    class EngagementProfileInput(BaseModel):
        """Contrato Pydantic estrito para potencialidades, interesses e canais preferenciais (Princípio I DUA)."""

        model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

        interesses_tematicos: list[str] = Field(
            default_factory=list,
            description="Identificadores de interesses temáticos selecionados (ex.: esportes, natureza, tecnologia).",
        )
        interesses_customizados: list[str] = Field(
            default_factory=list,
            description="Interesses temáticos complementares opcionais informados pelo docente.",
        )
        potencialidades: str | None = Field(
            default=None,
            description="Potencialidades e facilidades observadas no estudante (ex.: esquemas visuais).",
        )
        canais_engajamento_preferenciais: list[str] = Field(
            default_factory=list,
            description="Canais preferenciais de engajamento alinhados ao Princípio I do DUA.",
        )

        @field_validator("interesses_tematicos")
        @classmethod
        def validate_thematic_interests(cls, values: list[str]) -> list[str]:
            deduped = _dedupe_str_list(values, "interesses_tematicos")
            unknown = [v for v in deduped if v not in THEMATIC_INTERESTS_BY_ID]
            if unknown:
                raise ValueError(
                    f"Interesse(s) temático(s) desconhecido(s): {', '.join(unknown)}. "
                    f"Opções válidas: {', '.join(sorted(THEMATIC_INTERESTS_BY_ID))}."
                )
            return deduped

        @field_validator("canais_engajamento_preferenciais")
        @classmethod
        def validate_channels(cls, values: list[str]) -> list[str]:
            deduped = _dedupe_str_list(values, "canais_engajamento_preferenciais")
            unknown = [v for v in deduped if v not in ENGAGEMENT_CHANNELS_BY_ID]
            if unknown:
                raise ValueError(
                    f"Canal(is) de engajamento desconhecido(s): {', '.join(unknown)}. "
                    f"Opções válidas: {', '.join(sorted(ENGAGEMENT_CHANNELS_BY_ID))}."
                )
            return deduped

        @field_validator("interesses_customizados")
        @classmethod
        def validate_custom_interests(cls, values: list[str]) -> list[str]:
            deduped = _dedupe_str_list(values, "interesses_customizados")
            if len(deduped) > MAX_CUSTOM_INTERESTS:
                raise ValueError(
                    f"Informe no máximo {MAX_CUSTOM_INTERESTS} interesses customizados."
                )
            return deduped

except ImportError:

    class EngagementProfileInput:  # type: ignore[no-redef]
        """Contrato compatível quando Pydantic não estiver instalado no ambiente."""

        def __init__(
            self,
            interesses_tematicos: list[str] | None = None,
            interesses_customizados: list[str] | None = None,
            potencialidades: str | None = None,
            canais_engajamento_preferenciais: list[str] | None = None,
            **extra_kwargs: Any,
        ) -> None:
            if extra_kwargs:
                extras = ", ".join(sorted(extra_kwargs.keys()))
                raise ValueError(f"Campos extras não permitidos (extra='forbid'): {extras}")
            self.interesses_tematicos = _dedupe_str_list(
                interesses_tematicos or [], "interesses_tematicos"
            )
            unknown_int = [v for v in self.interesses_tematicos if v not in THEMATIC_INTERESTS_BY_ID]
            if unknown_int:
                raise ValueError(f"Interesse(s) temático(s) desconhecido(s): {', '.join(unknown_int)}.")

            self.canais_engajamento_preferenciais = _dedupe_str_list(
                canais_engajamento_preferenciais or [], "canais_engajamento_preferenciais"
            )
            unknown_ch = [
                v for v in self.canais_engajamento_preferenciais if v not in ENGAGEMENT_CHANNELS_BY_ID
            ]
            if unknown_ch:
                raise ValueError(f"Canal(is) de engajamento desconhecido(s): {', '.join(unknown_ch)}.")

            self.interesses_customizados = _dedupe_str_list(
                interesses_customizados or [], "interesses_customizados"
            )
            if len(self.interesses_customizados) > MAX_CUSTOM_INTERESTS:
                raise ValueError(f"Informe no máximo {MAX_CUSTOM_INTERESTS} interesses customizados.")

            if potencialidades is not None and not isinstance(potencialidades, str):
                raise ValueError("O campo 'potencialidades' deve ser texto.")
            self.potencialidades = potencialidades.strip() if isinstance(potencialidades, str) else None

        def model_dump(self) -> dict[str, Any]:
            return {
                "interesses_tematicos": list(self.interesses_tematicos),
                "interesses_customizados": list(self.interesses_customizados),
                "potencialidades": self.potencialidades,
                "canais_engajamento_preferenciais": list(self.canais_engajamento_preferenciais),
            }

        def dict(self) -> dict[str, Any]:
            return self.model_dump()


def validate_engagement_profile(payload: dict[str, Any] | None) -> EngagementMetadata:
    """Valida, sanitiza PII e converte a entrada opcional em metadados vinculados ao Princípio I do DUA."""
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise EngagementValidationError(
            message="O campo 'engagement_profile' deve ser um objeto JSON válido.",
            code="INVALID_ENGAGEMENT_PAYLOAD",
            field="engagement_profile",
        )

    extra_fields = set(payload.keys()) - ALLOWED_ENGAGEMENT_FIELDS
    if extra_fields:
        sorted_extras = ", ".join(sorted(extra_fields))
        raise EngagementValidationError(
            message=(
                f"Campos extras ou clínicos não permitidos em potencialidades/engajamento ({sorted_extras}). "
                "A plataforma Íris proíbe armazenamento ou envio de dados clínicos/CID ou identificadores pessoais."
            ),
            code="CLINICAL_OR_EXTRA_FIELD_FORBIDDEN",
            field=sorted(extra_fields)[0],
        )

    try:
        validated = EngagementProfileInput(**payload)
    except Exception as exc:
        raise EngagementValidationError(
            message=str(exc),
            code="INVALID_ENGAGEMENT_DATA",
            field="engagement_profile",
        ) from exc

    total_pii_removed = 0

    sanitized_custom_interests: list[str] = []
    for item in validated.interesses_customizados:
        sanitized_item, pii_cnt = _sanitize_and_validate_free_text(
            item, "interesses_customizados", MAX_CUSTOM_INTEREST_CHARS
        )
        total_pii_removed += pii_cnt
        if sanitized_item and sanitized_item not in sanitized_custom_interests:
            sanitized_custom_interests.append(sanitized_item)

    sanitized_potencialidades: str | None = None
    if validated.potencialidades and validated.potencialidades.strip():
        sanitized_pot, pii_cnt = _sanitize_and_validate_free_text(
            validated.potencialidades, "potencialidades", MAX_POTENTIALITIES_CHARS
        )
        total_pii_removed += pii_cnt
        sanitized_potencialidades = sanitized_pot or None

    interesses_estruturados = [
        {
            "id": THEMATIC_INTERESTS_BY_ID[i]["id"],
            "rotulo": THEMATIC_INTERESTS_BY_ID[i]["rotulo"],
            "ancora_sugerida": THEMATIC_INTERESTS_BY_ID[i]["ancora_sugerida"],
        }
        for i in validated.interesses_tematicos
    ]

    canais_estruturados = [
        {
            "id": ENGAGEMENT_CHANNELS_BY_ID[c]["id"],
            "rotulo": ENGAGEMENT_CHANNELS_BY_ID[c]["rotulo"],
            "estrategia_apoio": ENGAGEMENT_CHANNELS_BY_ID[c]["estrategia_apoio"],
        }
        for c in validated.canais_engajamento_preferenciais
    ]

    has_anchors = bool(
        interesses_estruturados
        or sanitized_custom_interests
        or sanitized_potencialidades
        or canais_estruturados
    )

    return EngagementMetadata(
        principio_dua=DUA_PRINCIPLE_ID,
        principio_dua_rotulo=DUA_PRINCIPLE_LABEL,
        diretriz_dua_referencia=DUA_PRINCIPLE_REFERENCE,
        interesses_tematicos=interesses_estruturados,
        interesses_customizados=sanitized_custom_interests,
        potencialidades=sanitized_potencialidades,
        canais_engajamento_preferenciais=canais_estruturados,
        possui_ancoras_motivacionais=has_anchors,
        sanitized=total_pii_removed > 0,
        pii_removed_count=total_pii_removed,
        regra_nao_substituicao=NON_SUBSTITUTION_RULE,
    )
