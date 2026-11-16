"""Schema e serviços de Calibragem de Nível de Andaime Cognitivo (História 1.3.1 — Issue #12).

Atende:
- RF-07: Calibragem do Nível de Andaime Cognitivo (Scaffolding em 3 Níveis: Leve, Moderado, Intensivo).
- RNF-10: Carga Cognitiva Reduzida na Interface do Professor (Etapa 3 do fluxo guiado).
- Pilar 1 & Pilar 2: Intervenção Cirúrgica (atuação exclusiva sobre características ativadas) e
  Blindagem da Trava Curricular (prevenção do efeito muleta).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from iris.schemas.catalog import (
    CharacteristicCatalog,
    CharacteristicSelectionError,
    load_official_tdah_catalog,
)

NIVEL_LEVE: int = 1
NIVEL_MODERADO: int = 2
NIVEL_INTENSIVO: int = 3
NIVEIS_VALIDOS: frozenset[int] = frozenset({NIVEL_LEVE, NIVEL_MODERADO, NIVEL_INTENSIVO})

AVISO_ANTIMULETA_GLOBAL: str = (
    "A calibração do andaime cognitivo ajusta o formato de apresentação, fragmentação e suporte procedimental "
    "da atividade escolar. O sistema é estritamente proibido de fornecer respostas prontas, reduzir conceitos "
    "obrigatórios ou produzir as inferências avaliadas pela questão."
)

NIVEIS_SCAFFOLDING_INFO: dict[int, dict[str, Any]] = {
    NIVEL_LEVE: {
        "nivel": NIVEL_LEVE,
        "rotulo": "Nível 1 — Adaptação Leve (Acessibilidade e Destaque Visual)",
        "nome_curto": "Leve",
        "objetivo_geral": (
            "Ajustes de formatação, organização visual e destaque tipográfico, preservando 100% "
            "da estrutura frasal, sintática e da complexidade original do conteúdo."
        ),
        "foco_pedagogico": "Acessibilidade perceptiva, foco atencional e redução de distratibilidade visual.",
        "transformacoes_estruturais": [
            "Aplicação de negrito em palavras-chave e verbos de comando (ex.: identifique, calcule, explique).",
            "Destaque de conectivos restritivos críticos (ex.: NÃO, EXCETO, APENAS, INCORRETA).",
            "Espaçamento ampliado e respiro visual entre parágrafos e alternativas.",
        ],
        "salvaguardas_antimuleta": [
            "Proibido reescrever enunciados ou simplificar vocabulário conceitual.",
            "Proibido fragmentar a questão em subitens ou alterar a ordem dos elementos.",
            "Preserva integralmente a extensão textual e a complexidade sintática.",
        ],
    },
    NIVEL_MODERADO: {
        "nivel": NIVEL_MODERADO,
        "rotulo": "Nível 2 — Adaptação Moderada (Fragmentação e Checklist de Etapas)",
        "nome_curto": "Moderado",
        "objetivo_geral": (
            "Divisão da atividade em etapas explícitas com checklists de execução (passo a passo), "
            "chunking de blocos textuais extensos e inserção de caixas de apoio/glossário contextual."
        ),
        "foco_pedagogico": "Redução da sobrecarga da memória de trabalho e organização sequencial da resolução.",
        "transformacoes_estruturais": [
            "Fragmentação estruturada (chunking) de parágrafos longos em blocos de leitura direta.",
            "Conversão de múltiplos comandos conjugados em listas sequenciais de checagem ([ ]).",
            "Inserção de caixas de apoio contextual ou glossário terminológico discreto.",
        ],
        "salvaguardas_antimuleta": [
            "Proibido responder ou resolver qualquer etapa pelo estudante.",
            "Proibido sugerir a fórmula, regra ou inferência exigida pela habilidade curricular.",
            "Mantém a totalidade das operações e comandos originais solicitados.",
        ],
    },
    NIVEL_INTENSIVO: {
        "nivel": NIVEL_INTENSIVO,
        "rotulo": "Nível 3 — Adaptação Intensiva (Decomposição Guiada e Pausas Ativas)",
        "nome_curto": "Intensivo",
        "objetivo_geral": (
            "Apresentação guiada de uma etapa por vez com campos de registro dedicados, lembretes "
            "de autorregulação, pausas ativas estratégicas e organizadores visuais gráficos."
        ),
        "foco_pedagogico": (
            "Suporte intensivo à função executiva, iniciação de tarefa e autorregulação em avaliações densas."
        ),
        "transformacoes_estruturais": [
            "Decomposição em subetapas com caixas de resolução exclusivas para cada etapa.",
            "Lembretes de checagem intermediária ('Revise se você concluiu a etapa anterior antes de prosseguir').",
            "Indicação de pausas estratégicas de autorregulação e respiração entre blocos avaliativos.",
            "Inclusão de organizadores visuais/gráficos para suporte à estruturação da resposta.",
        ],
        "salvaguardas_antimuleta": [
            "Proibido o efeito muleta: a IA jamais faz as inferências ou fornece a resolução pelo aluno.",
            "Preservação inegociável dos objetivos de aprendizagem e dos conceitos da Trava Curricular.",
            "Garante a mesma habilidade avaliada, modificando unicamente o formato de demonstração.",
        ],
    },
}


class ScaffoldingValidationError(ValueError):
    """Erro de validação nos parâmetros de calibração de andaime cognitivo."""

    def __init__(self, message: str, code: str, field: str = "nivel") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field

    def to_dict(self) -> dict[str, str]:
        return {
            "detail": self.message,
            "code": self.code,
            "field": self.field,
        }


class CharacteristicScaffoldingDirective(BaseModel):
    """Diretiva estrutural de andaime para uma característica funcional ativada (Pilar 1)."""

    model_config = ConfigDict(extra="forbid")

    id_caracteristica: str = Field(..., description="Identificador da característica ativada.")
    nome_caracteristica: str = Field(..., description="Nome amigável da barreira funcional.")
    nivel: int = Field(..., ge=1, le=3, description="Nível de andaime selecionado (1, 2 ou 3).")
    rotulo: str = Field(..., description="Rótulo da diretriz de andaime.")
    objetivo_andaime: str = Field(..., description="Objetivo psicopedagógico do suporte.")
    acoes_permitidas: list[str] = Field(..., description="Ações de transformação estrutural permitidas.")
    restricoes_escopo: list[str] = Field(..., description="Restrições estritas de salvaguarda anti-muleta.")


class ScaffoldingCalibrationRequest(BaseModel):
    """Payload de entrada para a calibração de nível de andaime (Etapa 3)."""

    model_config = ConfigDict(extra="forbid")

    selected_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Lista de identificadores de características funcionais validadas na Etapa 2.",
    )
    nivel: int = Field(
        ...,
        ge=1,
        le=3,
        description="Nível de suporte desejado: 1 (Leve), 2 (Moderado) ou 3 (Intensivo).",
    )
    id_catalogo: str = Field(
        default="tdah_funcoes_executivas_v1",
        description="Catálogo de referência para extração das diretrizes de andaime.",
    )


class ScaffoldingCalibrationResponse(BaseModel):
    """Resposta com a diretiva de andaime consolidada para a sessão docente."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="success")
    nivel: int = Field(..., ge=1, le=3)
    rotulo_nivel: str
    nome_curto: str
    objetivo_geral: str
    foco_pedagogico: str
    transformacoes_estruturais: list[str]
    salvaguardas_antimuleta: list[str]
    total_caracteristicas_afetadas: int
    caracteristicas_afetadas: list[CharacteristicScaffoldingDirective]
    caracteristicas_bloqueadas_ids: list[str]
    aviso_antimuleta: str = AVISO_ANTIMULETA_GLOBAL


def get_scaffolding_levels_metadata() -> dict[str, Any]:
    """Retorna as especificações informativas oficiais dos 3 níveis de andaime para a UI."""
    return {
        "status": "success",
        "niveis": [NIVEIS_SCAFFOLDING_INFO[1], NIVEIS_SCAFFOLDING_INFO[2], NIVEIS_SCAFFOLDING_INFO[3]],
        "aviso_antimuleta_global": AVISO_ANTIMULETA_GLOBAL,
    }


def calibrate_scaffolding_service(
    payload: dict[str, Any] | ScaffoldingCalibrationRequest,
    catalog: CharacteristicCatalog | None = None,
) -> ScaffoldingCalibrationResponse:
    """Calibra as diretrizes de andaime estritamente para as características funcionais ativadas (RF-07).

    Garante:
    1. Rejeição de níveis inválidos fora de {1, 2, 3}.
    2. Validação obrigatória de ao menos uma característica ativada.
    3. Rejeição de características desconhecidas ou campos extras/clínicos.
    4. Atribuição cirúrgica: apenas as características ativadas recebem diretrizes estruturais;
       todas as demais permanecem isoladas e bloqueadas.
    """
    if isinstance(payload, dict):
        allowed_keys = {"selected_ids", "nivel", "id_catalogo"}
        extra_keys = set(payload.keys()) - allowed_keys
        if extra_keys:
            primeiro_extra = sorted(extra_keys)[0]
            raise ScaffoldingValidationError(
                message=(
                    f"Campo extra '{primeiro_extra}' não permitido na calibragem de andaime. "
                    "A parametrização do nível aceita apenas 'selected_ids', 'nivel' e 'id_catalogo'."
                ),
                code="EXTRA_FIELD_FORBIDDEN",
                field=primeiro_extra,
            )

        nivel_val = payload.get("nivel")
        if nivel_val is None or not isinstance(nivel_val, int) or nivel_val not in NIVEIS_VALIDOS:
            raise ScaffoldingValidationError(
                message=f"Nível de andaime inválido ({nivel_val!r}). Deve ser 1 (Leve), 2 (Moderado) ou 3 (Intensivo).",
                code="INVALID_SCAFFOLDING_LEVEL",
                field="nivel",
            )

        raw_ids = payload.get("selected_ids")
        if not isinstance(raw_ids, list) or len(raw_ids) == 0:
            raise ScaffoldingValidationError(
                message="Selecione ao menos 1 característica funcional na Etapa 2 antes de calibrar o nível de andaime.",
                code="EMPTY_CHARACTERISTIC_SELECTION",
                field="selected_ids",
            )

        req = ScaffoldingCalibrationRequest(
            selected_ids=raw_ids,
            nivel=nivel_val,
            id_catalogo=str(payload.get("id_catalogo", "tdah_funcoes_executivas_v1")),
        )
    else:
        req = payload

    if catalog is None:
        catalog = load_official_tdah_catalog()

    catalog_map = {c.id_caracteristica: c for c in catalog.caracteristicas}
    unique_selected = list(dict.fromkeys(req.selected_ids))

    unknown_ids = [cid for cid in unique_selected if cid not in catalog_map]
    if unknown_ids:
        raise ScaffoldingValidationError(
            message=f"Característica(s) funcional(is) não reconhecida(s) no catálogo: {', '.join(unknown_ids)}.",
            code="UNKNOWN_CHARACTERISTIC_ID",
            field="selected_ids",
        )

    nivel_key = f"nivel_{req.nivel}"
    diretrizes_afetadas: list[CharacteristicScaffoldingDirective] = []

    for cid in unique_selected:
        item = catalog_map[cid]
        guideline = item.diretrizes_andaime[nivel_key]
        diretrizes_afetadas.append(
            CharacteristicScaffoldingDirective(
                id_caracteristica=item.id_caracteristica,
                nome_caracteristica=item.nome,
                nivel=req.nivel,
                rotulo=guideline.rotulo,
                objetivo_andaime=guideline.objetivo_andaime,
                acoes_permitidas=list(guideline.acoes_permitidas),
                restricoes_escopo=list(guideline.restricoes_escopo),
            )
        )

    all_ids = set(catalog_map.keys())
    blocked_ids = sorted(all_ids - set(unique_selected))

    meta_nivel = NIVEIS_SCAFFOLDING_INFO[req.nivel]

    return ScaffoldingCalibrationResponse(
        nivel=req.nivel,
        rotulo_nivel=meta_nivel["rotulo"],
        nome_curto=meta_nivel["nome_curto"],
        objetivo_geral=meta_nivel["objetivo_geral"],
        foco_pedagogico=meta_nivel["foco_pedagogico"],
        transformacoes_estruturais=list(meta_nivel["transformacoes_estruturais"]),
        salvaguardas_antimuleta=list(meta_nivel["salvaguardas_antimuleta"]),
        total_caracteristicas_afetadas=len(diretrizes_afetadas),
        caracteristicas_afetadas=diretrizes_afetadas,
        caracteristicas_bloqueadas_ids=blocked_ids,
        aviso_antimuleta=AVISO_ANTIMULETA_GLOBAL,
    )
