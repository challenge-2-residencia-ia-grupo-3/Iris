"""Schema e serviços de Calibragem de Nível de Andaime Cognitivo e Travas Curriculares (Histórias 1.3.1 e 1.3.2 — Issues #12 e #13).

Atende:
- RF-07: Calibragem do Nível de Andaime Cognitivo (Scaffolding em 3 Níveis: Leve, Moderado, Intensivo).
- RF-08: Definição Explícita de Travas Curriculares Inegociáveis (conceitos obrigatórios, termos técnicos e BNCC).
- RF-09: Validador Preventivo de Perda Cognitiva (Alerta Preventivo Anti-Muleta).
- RNF-02 & RNF-03: Sanitização preventiva de PII e bloqueio de referências clínicas.
- RNF-10: Carga Cognitiva Reduzida na Interface do Professor (Etapa 3 do fluxo guiado).
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from iris.schemas.catalog import (
    CharacteristicCatalog,
    CharacteristicSelectionError,
    load_official_tdah_catalog,
)
from iris.schemas.curriculum import IMPERATIVO_PARA_INFINITIVO
from iris.security.pii_scrubber import detect_clinical_reference, sanitize_pedagogical_note

NIVEL_LEVE: int = 1
NIVEL_MODERADO: int = 2
NIVEL_INTENSIVO: int = 3
NIVEIS_VALIDOS: frozenset[int] = frozenset({NIVEL_LEVE, NIVEL_MODERADO, NIVEL_INTENSIVO})

AVISO_ANTIMULETA_GLOBAL: str = (
    "A calibração do andaime cognitivo ajusta o formato de apresentação, fragmentação e suporte procedimental "
    "da atividade escolar. O sistema é estritamente proibido de fornecer respostas prontas, reduzir conceitos "
    "obrigatórios ou produzir as inferências avaliadas pela questão."
)

EXEMPLOS_TRAVAS_CURRICULARES: list[dict[str, Any]] = [
    {
        "id_exemplo": "lp_interpretacao_inferencia",
        "disciplina": "Língua Portuguesa",
        "rotulo": "Interpretação de Texto e Inferência",
        "conceitos_obrigatorios": ["sentido figurado", "ironia", "intenção do autor"],
        "termos_tecnicos_intocaveis": ["ironia", "metáfora"],
        "habilidade_bncc": "EF67LP08",
        "verbo_comando_bncc": "inferir",
        "objetivo_avaliativo": "Avaliar interpretação de texto e inferência de sentido implícito na crônica.",
    },
    {
        "id_exemplo": "mat_equacao_1grau",
        "disciplina": "Matemática",
        "rotulo": "Equação Polinomial do 1º Grau",
        "conceitos_obrigatorios": ["equação", "incógnita", "2x + 6 = 14"],
        "termos_tecnicos_intocaveis": ["incógnita", "2x + 6 = 14"],
        "habilidade_bncc": "EF07MA18",
        "verbo_comando_bncc": "calcular",
        "objetivo_avaliativo": "Resolver problemas que possam ser representados por equações polinomiais de 1º grau.",
    },
    {
        "id_exemplo": "cie_fotossintese",
        "disciplina": "Ciências",
        "rotulo": "Fotossíntese e Fluxo de Energia",
        "conceitos_obrigatorios": ["fotossíntese", "cloroplastos", "luz solar", "glicose"],
        "termos_tecnicos_intocaveis": ["cloroplastos", "glicose"],
        "habilidade_bncc": "EF06CI05",
        "verbo_comando_bncc": "explicar",
        "objetivo_avaliativo": "Explicar a conversão de energia luminosa em energia química nas células vegetais.",
    },
]

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
            "Inserção de caixas de apoio contextual ou glossário contextual discreto.",
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
    """Erro de validação nos parâmetros de calibração de andaime cognitivo e travas curriculares."""

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


class CurriculumLockInput(BaseModel):
    """Entrada de Trava Curricular Inegociável definida pelo professor na Etapa 3 (História 1.3.2 — RF-08)."""

    model_config = ConfigDict(extra="forbid")

    conceitos_obrigatorios: list[str] = Field(
        default_factory=list,
        description="Conceitos-chave e elementos literais obrigatórios que não podem ser omitidos ou simplificados.",
    )
    termos_tecnicos_intocaveis: list[str] = Field(
        default_factory=list,
        description="Termos técnicos ou dados da disciplina que a IA está proibida de substituir.",
    )
    habilidade_bncc: str | None = Field(
        default=None,
        description="Código ou descrição da habilidade BNCC avaliada (ex.: 'EF06CI05', 'EF67LP08').",
    )
    verbo_comando_bncc: str | None = Field(
        default=None,
        description="Verbo de comando principal avaliado na questão (ex.: 'inferir', 'interpretar', 'calcular').",
    )
    objetivo_avaliativo: str | None = Field(
        default=None,
        description="Objetivo pedagógico central avaliado pela questão.",
    )
    observacao_adaptacao_docente: str | None = Field(
        default=None,
        description="Instrução ou pedido adicional do professor sobre como deseja a adaptação da questão.",
    )


class AuditorInvariantsContract(BaseModel):
    """Contrato de invariantes curriculares marcados para o Agente Auditor e Agente Extrator (RF-08, RF-12)."""

    model_config = ConfigDict(extra="forbid")

    blindagem_ativa: bool = Field(
        default=False,
        description="Indica se há travas curriculares explícitas registradas pelo docente na sessão.",
    )
    conceitos_obrigatorios: list[str] = Field(
        default_factory=list,
        description="Invariantes conceituais obrigatórios exigidos pelo Agente Auditor (TRCC >= 95%).",
    )
    termos_tecnicos_intocaveis: list[str] = Field(
        default_factory=list,
        description="Vocabulário disciplinar protegido contra substituição ou infantilização.",
    )
    verbo_comando_bncc: str = Field(
        default="identificar",
        description="Verbo taxonômico normalizado no infinitivo.",
    )
    habilidade_bncc: str | None = Field(
        default=None,
        description="Habilidade BNCC vinculada à questão.",
    )
    objetivo_avaliativo: str | None = Field(
        default=None,
        description="Objetivo avaliativo protegido.",
    )
    operacao_cognitiva: str = Field(
        default="Executar a operação cognitiva exigida pela questão escolar sem redução de rigor.",
        description="Síntese da operação cognitiva preservada para o Agente Auditor.",
    )
    trcc_minimo_exigido: float = Field(
        default=0.95,
        description="Taxa mínima de retenção de conceitos-chave exigida pelo Agente Auditor.",
    )
    alerta_anti_muleta_auditor: str = Field(
        default=AVISO_ANTIMULETA_GLOBAL,
        description="Diretriz restritiva enviada ao Agente Adaptador e ao Agente Auditor.",
    )


class PreventiveAntiCrutchAlert(BaseModel):
    """Alerta preventivo de perda cognitiva / anti-muleta (História 1.3.2 — RF-09)."""

    model_config = ConfigDict(extra="forbid")

    emitido: bool = Field(
        default=False,
        description="True quando o validador detecta incompatibilidade pedagógica ou risco de efeito muleta.",
    )
    severidade: str = Field(
        default="none",
        description="Severidade do alerta: 'none', 'warning' ou 'critical'.",
    )
    codigo: str = Field(
        default="OK_NO_CONFLICT",
        description="Código identificador da regra preventiva acionada.",
    )
    titulo: str = Field(
        default="Trava curricular compatível com o nível de andaime",
        description="Título objetivo do alerta preventivo.",
    )
    mensagem: str = Field(
        default="Nenhuma contradição pedagógica detectada entre a habilidade avaliada e o suporte configurado.",
        description="Explicação detalhada sobre o risco de perda cognitiva ou confirmação de segurança.",
    )
    conflitos_detectados: list[str] = Field(
        default_factory=list,
        description="Lista de incompatibilidades específicas identificadas pelo validador.",
    )
    recomendacao_pedagogica: str = Field(
        default="A parametrização preserva o rigor cognitivo e os invariantes para o Agente Auditor.",
        description="Orientação prática para o professor ajustar ou confirmar a adaptação.",
    )
    nivel_sugerido: int | None = Field(
        default=None,
        description="Nível de andaime alternativo recomendado quando houver conflito com o nível atual.",
    )


class ScaffoldingCalibrationRequest(BaseModel):
    """Payload de entrada para a calibração de nível de andaime e travas curriculares (Etapa 3)."""

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
    trava_curricular: CurriculumLockInput | None = Field(
        default=None,
        description="Trava curricular inegociável definida pelo professor (História 1.3.2 — RF-08).",
    )


class ScaffoldingCalibrationResponse(BaseModel):
    """Resposta com a diretiva de andaime e travas curriculares consolidadas para a sessão docente."""

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
    trava_curricular: CurriculumLockInput = Field(default_factory=CurriculumLockInput)
    invariantes_auditor: AuditorInvariantsContract = Field(default_factory=AuditorInvariantsContract)
    alerta_preventivo_antimuleta: PreventiveAntiCrutchAlert = Field(default_factory=PreventiveAntiCrutchAlert)
    pii_removido_automaticamente: bool = Field(default=False)


# Padrões léxicos para o Validador Preventivo de Perda Cognitiva (RF-09)
_RE_HABILIDADE_INTERPRETACAO_INFERENCIA = re.compile(
    r"(?i)\b(?:interpreta[cç][aã]o(?:\s+de\s+texto|\s+textual)?|interpretar|infer[eê]ncia|inferir|"
    r"sentido\s+(?:impl[ií]cito|figurado|conotativo)|ideia\s+central|ironia|ambiguidade|"
    r"compreens[aã]o\s+leitora|dedu[cç][aã]o|deduzir|subentendido|hip[oó]tese)\b"
)
_RE_MULETA_INTERPRETACAO = re.compile(
    r"(?i)\b(?:resumo\s+interpretativo|resumir\s+o\s+texto|resumo\s+do\s+texto|resumo\s+explicativo|"
    r"explicar\s+o\s+sentido|explica[cç][aã]o\s+do\s+sentido|entregar\s+a\s+interpreta[cç][aã]o|"
    r"dizer\s+o\s+que\s+o\s+autor\s+quis\s+dizer|explicar\s+a\s+ironia|explicar\s+a\s+met[aá]fora|"
    r"antecipar\s+a\s+infer[eê]ncia|dar\s+a\s+ideia\s+central|s[ií]ntese\s+interpretativa|"
    r"resposta\s+pronta|gabarito|indicar\s+a\s+alternativa\s+correta)\b"
)

_RE_HABILIDADE_CALCULO_ALGEBRA = re.compile(
    r"(?i)\b(?:calcular|c[aá]lculo|resolver\s+a?\s*equa[cç][aã]o|equa[cç][aã]o|inc[oó]gnita|"
    r"opera[cç][aã]o\s+alg[eé]brica|f[oó]rmula|propor[cç][aã]o|regra\s+de\s+tr[eê]s|"
    r"sistema\s+linear|demonstrar|determinar\s+o\s+valor)\b"
)
_RE_MULETA_CALCULO = re.compile(
    r"(?i)\b(?:f[oó]rmula\s+pronta|dar\s+a\s+f[oó]rmula|entregar\s+a\s+f[oó]rmula|"
    r"equa[cç][aã]o\s+montada|montar\s+a\s+equa[cç][aã]o|resolver\s+o\s+primeiro\s+passo|"
    r"passo\s+resolvido|resultado\s+intermedi[aá]rio|isolar\s+a\s+inc[oó]gnita\s+pelo\s+aluno|"
    r"resposta\s+pronta|gabarito|indicar\s+a\s+alternativa\s+correta)\b"
)

_RE_HABILIDADE_CONCEITUAL = re.compile(
    r"(?i)\b(?:definir|defini[cç][aã]o|conceituar|classificar|identificar\s+o\s+conceito|"
    r"diferenciar|nomear|reconhecer\s+a\s+fun[cç][aã]o)\b"
)
_RE_MULETA_DEFINICAO_DIRETA = re.compile(
    r"(?i)\b(?:definir\s+o\s+termo\s+avaliado|dar\s+a\s+defini[cç][aã]o\s+pronta|"
    r"explicar\s+o\s+conceito\s+no\s+enunciado|gloss[aá]rio\s+com\s+a\s+resposta|"
    r"destacar\s+a\s+resposta|indicar\s+a\s+alternativa\s+correta|resposta\s+pronta|gabarito)\b"
)


def _normalizar_lista_termos(raw: Any, field_name: str) -> tuple[list[str], bool]:
    """Normaliza lista ou string delimitada de termos, aplicando sanitização de PII e checagem clínica."""
    if raw is None:
        return [], False
    if isinstance(raw, str):
        candidatos = re.split(r"[;\n,]", raw)
    elif isinstance(raw, list):
        candidatos = []
        for el in raw:
            if not isinstance(el, str):
                raise ScaffoldingValidationError(
                    message=f"Todos os itens de '{field_name}' devem ser textos (strings).",
                    code="INVALID_CURRICULUM_LOCK_FORMAT",
                    field=field_name,
                )
            candidatos.extend(re.split(r"[;\n]", el))
    else:
        raise ScaffoldingValidationError(
            message=f"O campo '{field_name}' deve ser uma lista de termos ou texto separado por vírgulas.",
            code="INVALID_CURRICULUM_LOCK_FORMAT",
            field=field_name,
        )

    vistos: set[str] = set()
    limpos: list[str] = []
    pii_removido = False

    for item in candidatos:
        texto = item.strip()
        if not texto:
            continue
        clinical = detect_clinical_reference(texto)
        if clinical:
            raise ScaffoldingValidationError(
                message=(
                    f"Referência clínica ou médica ('{clinical}') detectada em '{field_name}'. "
                    "A Trava Curricular deve conter apenas conceitos pedagógicos e habilidades da BNCC (RNF-03)."
                ),
                code="CLINICAL_REFERENCE_FORBIDDEN",
                field=field_name,
            )
        sanitizado, count = sanitize_pedagogical_note(texto)
        if count > 0:
            pii_removido = True
        chave = sanitizado.lower()
        if sanitizado and chave not in vistos:
            vistos.add(chave)
            limpos.append(sanitizado)

    return limpos, pii_removido


def _normalizar_texto_opcional(
    raw: Any,
    field_name: str,
    max_len: int = 500,
) -> tuple[str | None, bool]:
    if raw is None:
        return None, False
    if not isinstance(raw, str):
        raise ScaffoldingValidationError(
            message=f"O campo '{field_name}' deve ser um texto (string).",
            code="INVALID_CURRICULUM_LOCK_FORMAT",
            field=field_name,
        )
    texto = raw.strip()
    if not texto:
        return None, False
    if len(texto) > max_len:
        raise ScaffoldingValidationError(
            message=f"O campo '{field_name}' excede o limite máximo de {max_len} caracteres.",
            code="CURRICULUM_LOCK_TOO_LONG",
            field=field_name,
        )
    clinical = detect_clinical_reference(texto)
    if clinical:
        raise ScaffoldingValidationError(
            message=(
                f"Referência clínica ou médica ('{clinical}') detectada em '{field_name}'. "
                "Informe apenas habilidades curriculares e objetivos pedagógicos (RNF-03)."
            ),
            code="CLINICAL_REFERENCE_FORBIDDEN",
            field=field_name,
        )
    sanitizado, count = sanitize_pedagogical_note(texto)
    return sanitizado, count > 0


def parse_and_sanitize_curriculum_lock(
    raw_lock: dict[str, Any] | CurriculumLockInput | None,
    require_non_empty: bool = False,
) -> tuple[CurriculumLockInput, bool]:
    """Valida, normaliza e sanitiza os campos da Trava Curricular Inegociável (RF-08, RNF-02, RNF-03)."""
    if raw_lock is None:
        if require_non_empty:
            raise ScaffoldingValidationError(
                message="Informe ao menos um conceito obrigatório ou objetivo avaliativo na Trava Curricular.",
                code="EMPTY_CURRICULUM_LOCK",
                field="trava_curricular",
            )
        return CurriculumLockInput(), False

    if isinstance(raw_lock, CurriculumLockInput):
        raw_dict = raw_lock.model_dump()
    elif isinstance(raw_lock, dict):
        allowed_lock_keys = {
            "conceitos_obrigatorios",
            "termos_tecnicos_intocaveis",
            "habilidade_bncc",
            "verbo_comando_bncc",
            "objetivo_avaliativo",
            "observacao_adaptacao_docente",
        }
        extra_lock_keys = set(raw_lock.keys()) - allowed_lock_keys
        if extra_lock_keys:
            primeiro = sorted(extra_lock_keys)[0]
            raise ScaffoldingValidationError(
                message=f"Campo extra '{primeiro}' não permitido em 'trava_curricular'.",
                code="EXTRA_FIELD_FORBIDDEN",
                field=f"trava_curricular.{primeiro}",
            )
        raw_dict = raw_lock
    else:
        raise ScaffoldingValidationError(
            message="O campo 'trava_curricular' deve ser um objeto estruturado.",
            code="INVALID_CURRICULUM_LOCK_FORMAT",
            field="trava_curricular",
        )

    conceitos, pii_c = _normalizar_lista_termos(
        raw_dict.get("conceitos_obrigatorios"),
        "conceitos_obrigatorios",
    )
    termos, pii_t = _normalizar_lista_termos(
        raw_dict.get("termos_tecnicos_intocaveis"),
        "termos_tecnicos_intocaveis",
    )
    hab_bncc, pii_h = _normalizar_texto_opcional(
        raw_dict.get("habilidade_bncc"),
        "habilidade_bncc",
        max_len=160,
    )
    verbo_raw, pii_v = _normalizar_texto_opcional(
        raw_dict.get("verbo_comando_bncc"),
        "verbo_comando_bncc",
        max_len=60,
    )
    objetivo, pii_o = _normalizar_texto_opcional(
        raw_dict.get("objetivo_avaliativo"),
        "objetivo_avaliativo",
        max_len=500,
    )
    observacao, pii_obs = _normalizar_texto_opcional(
        raw_dict.get("observacao_adaptacao_docente"),
        "observacao_adaptacao_docente",
        max_len=500,
    )

    if not hab_bncc and objetivo:
        bncc_inline = re.search(r"\b(?:EF\d{2}[A-Z]{2}\d{2}|EM\d{2}[A-Z]{3}\d{3})\b", objetivo)
        if bncc_inline:
            hab_bncc = bncc_inline.group(0)

    if verbo_raw:
        v_low = verbo_raw.lower().strip()
        verbo_norm = IMPERATIVO_PARA_INFINITIVO.get(v_low, v_low)
    elif objetivo:
        verbo_norm = None
        for p in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{3,}", objetivo):
            p_low = p.lower()
            if p_low in IMPERATIVO_PARA_INFINITIVO:
                verbo_norm = IMPERATIVO_PARA_INFINITIVO[p_low]
                break
            if p_low in IMPERATIVO_PARA_INFINITIVO.values():
                verbo_norm = p_low
                break
    else:
        verbo_norm = None

    if require_non_empty and not conceitos and not termos and not objetivo and not hab_bncc:
        raise ScaffoldingValidationError(
            message=(
                "Defina ao menos um conceito-chave obrigatório ou o objetivo avaliativo/BNCC "
                "para registrar a Trava Curricular Inegociável."
            ),
            code="EMPTY_CURRICULUM_LOCK",
            field="conceitos_obrigatorios",
        )

    lock_clean = CurriculumLockInput(
        conceitos_obrigatorios=conceitos,
        termos_tecnicos_intocaveis=termos,
        habilidade_bncc=hab_bncc,
        verbo_comando_bncc=verbo_norm,
        objetivo_avaliativo=objetivo,
        observacao_adaptacao_docente=observacao,
    )
    pii_any = any([pii_c, pii_t, pii_h, pii_v, pii_o, pii_obs])
    return lock_clean, pii_any


def build_auditor_invariants(
    lock: CurriculumLockInput,
    alert: PreventiveAntiCrutchAlert,
) -> AuditorInvariantsContract:
    """Constrói o contrato de invariantes obrigatórios consumido pelo Agente Auditor (RF-08, RF-12)."""
    conceitos_finais = list(dict.fromkeys([*lock.conceitos_obrigatorios, *lock.termos_tecnicos_intocaveis]))
    termos_finais = list(
        dict.fromkeys(lock.termos_tecnicos_intocaveis if lock.termos_tecnicos_intocaveis else lock.conceitos_obrigatorios)
    )
    blindagem_ativa = bool(conceitos_finais or lock.objetivo_avaliativo or lock.habilidade_bncc or lock.verbo_comando_bncc)

    verbo = lock.verbo_comando_bncc or "identificar"
    if not lock.verbo_comando_bncc and lock.objetivo_avaliativo:
        primeira_palavra = re.split(r"\s+", lock.objetivo_avaliativo.strip())[0].lower().strip(".,:;!?")
        if primeira_palavra in IMPERATIVO_PARA_INFINITIVO:
            verbo = IMPERATIVO_PARA_INFINITIVO[primeira_palavra]
        elif primeira_palavra in IMPERATIVO_PARA_INFINITIVO.values():
            verbo = primeira_palavra

    operacao = (
        lock.objetivo_avaliativo
        or (f"Demonstrar a habilidade {lock.habilidade_bncc} preservando {', '.join(conceitos_finais[:4])}." if lock.habilidade_bncc and conceitos_finais else None)
        or (f"Preservar integralmente os conceitos obrigatórios: {', '.join(conceitos_finais[:5])}." if conceitos_finais else None)
        or "Executar a operação cognitiva exigida pela questão escolar sem redução de rigor."
    )

    alerta_auditor = (
        f"{alert.titulo}: {alert.recomendacao_pedagogica}"
        if alert.emitido
        else (
            f"Proibido omitir, substituir ou explicar de forma conclusiva os invariantes: {', '.join(conceitos_finais)}."
            if conceitos_finais
            else AVISO_ANTIMULETA_GLOBAL
        )
    )

    return AuditorInvariantsContract(
        blindagem_ativa=blindagem_ativa,
        conceitos_obrigatorios=conceitos_finais,
        termos_tecnicos_intocaveis=termos_finais,
        verbo_comando_bncc=verbo,
        habilidade_bncc=lock.habilidade_bncc,
        objetivo_avaliativo=lock.objetivo_avaliativo,
        operacao_cognitiva=operacao,
        trcc_minimo_exigido=0.95,
        alerta_anti_muleta_auditor=alerta_auditor,
    )


def evaluate_preventive_anti_crutch(
    nivel: int,
    selected_ids: list[str],
    lock: CurriculumLockInput,
) -> PreventiveAntiCrutchAlert:
    """Validador Preventivo de Perda Cognitiva / Anti-Muleta (História 1.3.2 — RF-09).

    Cruza:
    - O objetivo avaliativo, verbo de comando BNCC e conceitos obrigatórios da Trava Curricular;
    - Eventuais pedidos/observações de adaptação inseridos pelo docente;
    - O nível de andaime cognitivo (1 Leve, 2 Moderado, 3 Intensivo) e características selecionadas.
    """
    texto_habilidade = " ".join(
        filter(
            None,
            [
                lock.objetivo_avaliativo,
                lock.habilidade_bncc,
                lock.verbo_comando_bncc,
                " ".join(lock.conceitos_obrigatorios),
            ],
        )
    )
    texto_pedido_docente = " ".join(
        filter(
            None,
            [
                lock.observacao_adaptacao_docente,
                lock.objetivo_avaliativo,
            ],
        )
    )

    conflitos: list[str] = []

    avalia_interpretacao = bool(_RE_HABILIDADE_INTERPRETACAO_INFERENCIA.search(texto_habilidade))
    pede_muleta_interpretacao = bool(_RE_MULETA_INTERPRETACAO.search(texto_pedido_docente))

    avalia_calculo = bool(_RE_HABILIDADE_CALCULO_ALGEBRA.search(texto_habilidade))
    pede_muleta_calculo = bool(_RE_MULETA_CALCULO.search(texto_pedido_docente))

    avalia_conceito = bool(_RE_HABILIDADE_CONCEITUAL.search(texto_habilidade)) or len(lock.conceitos_obrigatorios) > 0
    pede_muleta_definicao = bool(_RE_MULETA_DEFINICAO_DIRETA.search(texto_pedido_docente))

    # 1. Contradição direta explícita entre o pedido de adaptação e a habilidade avaliada (Ex.: Critério BDD da 1.3.2)
    if avalia_interpretacao and pede_muleta_interpretacao:
        match_muleta = _RE_MULETA_INTERPRETACAO.search(texto_pedido_docente)
        termo_conflito = match_muleta.group(0) if match_muleta else "resumo interpretativo"
        conflitos.append(
            f"Solicitação de '{termo_conflito}' contradiz diretamente a habilidade avaliada de interpretação/inferência textual."
        )
        return PreventiveAntiCrutchAlert(
            emitido=True,
            severidade="critical",
            codigo="CONTRADICAO_DIRETA_INTERPRETACAO",
            titulo="Alerta Preventivo Anti-Muleta: Risco Crítico de Perda Cognitiva",
            mensagem=(
                f"A questão avalia interpretação/inferência textual, mas foi solicitado '{termo_conflito}'. "
                "Fornecer resumo interpretativo ou explicar o sentido implícito entrega a resposta pronta ao aluno "
                "e invalida o objetivo avaliativo da BNCC."
            ),
            conflitos_detectados=conflitos,
            recomendacao_pedagogica=(
                "Remova o pedido de resumo interpretativo/explicação de sentido e utilize destaque tipográfico (Nível 1) "
                "ou fragmentação da leitura em blocos sem antecipar a inferência (Nível 2)."
            ),
            nivel_sugerido=NIVEL_MODERADO if nivel == NIVEL_INTENSIVO else nivel,
        )

    if avalia_calculo and pede_muleta_calculo:
        match_muleta = _RE_MULETA_CALCULO.search(texto_pedido_docente)
        termo_conflito = match_muleta.group(0) if match_muleta else "fórmula/passo resolvido"
        conflitos.append(
            f"Solicitação de '{termo_conflito}' contradiz a habilidade avaliada de resolução matemática/algébrica."
        )
        return PreventiveAntiCrutchAlert(
            emitido=True,
            severidade="critical",
            codigo="CONTRADICAO_DIRETA_CALCULO",
            titulo="Alerta Preventivo Anti-Muleta: Antecipação Indevida de Resolução",
            mensagem=(
                f"A questão avalia resolução matemática ou algébrica, mas foi solicitado '{termo_conflito}'. "
                "Entregar a equação montada ou etapas resolvidas elimina o raciocínio avaliado."
            ),
            conflitos_detectados=conflitos,
            recomendacao_pedagogica=(
                "Substitua a entrega da fórmula/cálculo pronto por um checklist de verificação procedural (Nível 2) "
                "preservando intactos os dados numéricos e a incógnita."
            ),
            nivel_sugerido=NIVEL_MODERADO if nivel == NIVEL_INTENSIVO else nivel,
        )

    if avalia_conceito and pede_muleta_definicao:
        match_muleta = _RE_MULETA_DEFINICAO_DIRETA.search(texto_pedido_docente)
        termo_conflito = match_muleta.group(0) if match_muleta else "definição pronta da resposta"
        conflitos.append(
            f"Solicitação de '{termo_conflito}' entrega diretamente o conceito que é objeto de avaliação."
        )
        return PreventiveAntiCrutchAlert(
            emitido=True,
            severidade="critical",
            codigo="CONTRADICAO_DIRETA_CONCEITO",
            titulo="Alerta Preventivo Anti-Muleta: Exposição da Resposta Conceitual",
            mensagem=(
                f"A adaptação solicitada ('{termo_conflito}') antecipa a definição ou alternativa avaliada pela questão."
            ),
            conflitos_detectados=conflitos,
            recomendacao_pedagogica=(
                "Mantenha os conceitos obrigatórios protegidos na Trava Curricular e limite o suporte ao destaque "
                "dos verbos de comando e organização visual."
            ),
            nivel_sugerido=NIVEL_LEVE,
        )

    # 2. Tensão entre Nível 3 (Intensivo — decomposição guiada passo a passo) e habilidade de inferência/interpretação autônoma
    if nivel == NIVEL_INTENSIVO and avalia_interpretacao:
        conflitos.append(
            "Nível 3 (Adaptação Intensiva com decomposição guiada em subetapas) selecionado para questão que avalia interpretação/inferência."
        )
        return PreventiveAntiCrutchAlert(
            emitido=True,
            severidade="warning",
            codigo="RISCO_NIVEL_INTENSIVO_INFERENCIA",
            titulo="Atenção Anti-Muleta: Decomposição Intensiva em Questão de Inferência",
            mensagem=(
                "Você selecionou o Nível 3 (Intensivo) para uma atividade cujo objetivo avaliativo envolve "
                "interpretação textual ou inferência de sentido. Decompor uma questão inferencial em subetapas "
                "muito guiadas pode induzir a conclusão lógica pelo estudante."
            ),
            conflitos_detectados=conflitos,
            recomendacao_pedagogica=(
                "Considere calibrar para o Nível 2 (Moderado) ou Nível 1 (Leve). Caso mantenha o Nível 3, "
                "o Agente Adaptador e o Agente Auditor aplicarão trava estrita proibindo dicas sobre o sentido implícito."
            ),
            nivel_sugerido=NIVEL_MODERADO,
        )

    # 3. Cautela quando suporte estrutural intensivo (bloqueio_iniciacao_tarefas_abertas ou organizacao_sequencial_expressao_escrita em Nível 3) convive com termos técnicos intocáveis explícitos
    if (
        nivel == NIVEL_INTENSIVO
        and any(
            cid in selected_ids
            for cid in (
                "bloqueio_iniciacao_tarefas_abertas",
                "organizacao_sequencial_expressao_escrita",
            )
        )
        and len(lock.termos_tecnicos_intocaveis) > 0
    ):
        termos_protegidos = ", ".join(lock.termos_tecnicos_intocaveis[:4])
        conflitos.append(
            f"Suporte intensivo de iniciação/expressão escrita ativo no Nível {nivel} com termos técnicos intocáveis ({termos_protegidos})."
        )
        return PreventiveAntiCrutchAlert(
            emitido=True,
            severidade="warning",
            codigo="CAUTELA_GLOSSARIO_TERMOS_TRAVADOS",
            titulo="Salvaguarda Anti-Muleta: Termos Técnicos Protegidos no Suporte Guiado",
            mensagem=(
                f"O suporte guiado de iniciação/expressão escrita está ativo no Nível {nivel}, porém os termos [{termos_protegidos}] "
                "foram marcados como Trava Curricular Inegociável."
            ),
            conflitos_detectados=conflitos,
            recomendacao_pedagogica=(
                "Os organizadores e pistas de iniciação estruturarão apenas a forma da resposta, ficando estritamente proibidos "
                "de definir, substituir ou antecipar o emprego dos termos técnicos travados."
            ),
            nivel_sugerido=None,
        )

    return PreventiveAntiCrutchAlert()


def get_scaffolding_levels_metadata() -> dict[str, Any]:
    """Retorna as especificações informativas oficiais dos 3 níveis de andaime e exemplos de travas para a UI."""
    return {
        "status": "success",
        "niveis": [NIVEIS_SCAFFOLDING_INFO[1], NIVEIS_SCAFFOLDING_INFO[2], NIVEIS_SCAFFOLDING_INFO[3]],
        "aviso_antimuleta_global": AVISO_ANTIMULETA_GLOBAL,
        "exemplos_travas_curriculares": EXEMPLOS_TRAVAS_CURRICULARES,
    }


def calibrate_scaffolding_service(
    payload: dict[str, Any] | ScaffoldingCalibrationRequest,
    catalog: CharacteristicCatalog | None = None,
    require_curriculum_lock: bool = False,
) -> ScaffoldingCalibrationResponse:
    """Calibra as diretrizes de andaime (RF-07) e valida as Travas Curriculares e alerta anti-muleta (RF-08, RF-09).

    Garante:
    1. Rejeição de níveis inválidos fora de {1, 2, 3}.
    2. Validação obrigatória de ao menos uma característica ativada.
    3. Rejeição de características desconhecidas ou campos extras/clínicos.
    4. Atribuição cirúrgica: apenas as características ativadas recebem diretrizes estruturais.
    5. Marcação dos conceitos da Trava Curricular como invariantes obrigatórios para o Agente Auditor.
    6. Emissão de alerta preventivo anti-muleta quando houver contradição com a habilidade avaliada.
    """
    pii_removido = False

    if isinstance(payload, dict):
        allowed_keys = {"selected_ids", "nivel", "id_catalogo", "trava_curricular"}
        extra_keys = set(payload.keys()) - allowed_keys
        if extra_keys:
            primeiro_extra = sorted(extra_keys)[0]
            raise ScaffoldingValidationError(
                message=(
                    f"Campo extra '{primeiro_extra}' não permitido na calibragem de andaime. "
                    "A parametrização aceita apenas 'selected_ids', 'nivel', 'id_catalogo' e 'trava_curricular'."
                ),
                code="EXTRA_FIELD_FORBIDDEN",
                field=primeiro_extra,
            )

        nivel_val = payload.get("nivel")
        if nivel_val is None or not isinstance(nivel_val, int) or isinstance(nivel_val, bool) or nivel_val not in NIVEIS_VALIDOS:
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

        lock_clean, pii_removido = parse_and_sanitize_curriculum_lock(
            payload.get("trava_curricular"),
            require_non_empty=require_curriculum_lock,
        )

        req = ScaffoldingCalibrationRequest(
            selected_ids=raw_ids,
            nivel=nivel_val,
            id_catalogo=str(payload.get("id_catalogo", "tdah_funcoes_executivas_v1")),
            trava_curricular=lock_clean,
        )
    else:
        lock_clean, pii_removido = parse_and_sanitize_curriculum_lock(
            payload.trava_curricular,
            require_non_empty=require_curriculum_lock,
        )
        req = ScaffoldingCalibrationRequest(
            selected_ids=payload.selected_ids,
            nivel=payload.nivel,
            id_catalogo=payload.id_catalogo,
            trava_curricular=lock_clean,
        )

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
    active_lock = req.trava_curricular or CurriculumLockInput()
    alerta_preventivo = evaluate_preventive_anti_crutch(
        nivel=req.nivel,
        selected_ids=unique_selected,
        lock=active_lock,
    )
    invariantes_auditor = build_auditor_invariants(lock=active_lock, alert=alerta_preventivo)

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
        trava_curricular=active_lock,
        invariantes_auditor=invariantes_auditor,
        alerta_preventivo_antimuleta=alerta_preventivo,
        pii_removido_automaticamente=pii_removido,
    )


def validate_curriculum_locks_service(
    payload: dict[str, Any] | ScaffoldingCalibrationRequest,
    catalog: CharacteristicCatalog | None = None,
) -> ScaffoldingCalibrationResponse:
    """Valida obrigatoriamente a Trava Curricular Inegociável e executa o validador anti-muleta (História 1.3.2)."""
    return calibrate_scaffolding_service(
        payload=payload,
        catalog=catalog,
        require_curriculum_lock=True,
    )


_STOPWORDS_EXTRACAO: frozenset[str] = frozenset({
    "para", "como", "qual", "quais", "onde", "quando", "sobre", "texto", "abaixo",
    "leia", "responda", "questao", "questão", "alternativa", "correta", "incorreta",
    "assinale", "marque", "seguinte", "seguintes", "entre", "pelo", "pela", "pelos",
    "pelas", "esse", "essa", "este", "esta", "isso", "aquilo", "muito", "mais",
    "menos", "cada", "todo", "toda", "todos", "todas", "outro", "outra", "mesmo",
    "mesma", "apenas", "somente", "então", "porque", "pois", "assim", "durante",
    "depois", "antes", "através", "acordo", "segundo", "aluno", "estudante",
    "escola", "professor", "atividade", "exercício", "exercicio", "enunciado",
})


def extract_curriculum_locks_from_material(material_text: str) -> CurriculumLockInput:
    """Extrai automaticamente conceitos-chave, código BNCC, verbo de comando e objetivo avaliativo do material da Etapa 1."""
    if not material_text or not material_text.strip():
        return CurriculumLockInput()

    sanitized, _ = sanitize_pedagogical_note(material_text)

    # 1. Código BNCC explícito no texto (ex.: EF06CI05, EF67LP08, EM13CNT101)
    bncc_match = re.search(r"\b(?:EF\d{2}[A-Z]{2}\d{2}|EM\d{2}[A-Z]{3}\d{3})\b", sanitized)
    hab_bncc = bncc_match.group(0) if bncc_match else None

    # 2. Verbo de comando BNCC
    palavras_raw = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{3,}", sanitized)
    verbo_encontrado: str | None = None
    for p in palavras_raw:
        p_low = p.lower()
        if p_low in IMPERATIVO_PARA_INFINITIVO:
            verbo_encontrado = IMPERATIVO_PARA_INFINITIVO[p_low]
            break
        if p_low in IMPERATIVO_PARA_INFINITIVO.values():
            verbo_encontrado = p_low
            break

    # 3. Expressões matemáticas/equações e termos entre aspas
    conceitos: list[str] = []
    vistos: set[str] = set()

    def _add(termo: str) -> None:
        t = termo.strip(".,:;!?()[]{}\"' ")
        if len(t) < 3 or t.startswith("["):
            return
        k = t.lower()
        if k not in vistos and k not in _STOPWORDS_EXTRACAO:
            vistos.add(k)
            conceitos.append(t)

    for eq in re.findall(r"\b\d*[a-zA-Z]\s*[+\-]\s*\d+\s*=\s*\d+\b", sanitized):
        _add(eq)
    for quoted in re.findall(r'"([^"]{3,45})"|“([^”]{3,45})”', sanitized):
        _add(quoted[0] or quoted[1])

    # 4. Termos técnicos e substantivos relevantes do material
    for p in palavras_raw:
        p_low = p.lower()
        if (
            len(p) >= 6
            and p_low not in _STOPWORDS_EXTRACAO
            and p_low not in IMPERATIVO_PARA_INFINITIVO
            and p_low not in IMPERATIVO_PARA_INFINITIVO.values()
        ):
            _add(p_low)
        if len(conceitos) >= 6:
            break

    verbo_obj = (verbo_encontrado or "compreender").capitalize()
    resumo_conceitos = ", ".join(conceitos[:4]) if conceitos else "os conceitos centrais da atividade"
    objetivo = (
        f"{verbo_obj} {resumo_conceitos}"
        + (f" ({hab_bncc})." if hab_bncc else ".")
    )

    return CurriculumLockInput(
        conceitos_obrigatorios=conceitos[:6],
        termos_tecnicos_intocaveis=conceitos[:6],
        habilidade_bncc=hab_bncc,
        verbo_comando_bncc=verbo_encontrado or "identificar",
        objetivo_avaliativo=objetivo,
    )

