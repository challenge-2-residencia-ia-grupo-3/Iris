"""Mapeador de contexto motivacional (Princípio I do DUA) para o prompt de adaptação (História 1.2.2).

Responsável por:
1. Traduzir os metadados validados de potencialidades, interesses temáticos e canais preferenciais
   em diretivas motivacionais alinhadas à Rede de Engajamento do DUA.
2. Recuperar opcionalmente evidências científicas do RAG sobre engajamento/iniciação de tarefa (RNF-06).
3. Injetar o bloco motivacional no prompt de adaptação com cláusula rígida de preservação das
   Travas Curriculares (proibição estrita de substituir conceitos obrigatórios).
4. Validar deterministicamente via TRCC (`iris.eval.trcc`) que uma adaptação com âncoras
   motivacionais preservou >= 95% dos conceitos exigidos na avaliação.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from iris.eval.trcc import LIMIAR_PADRAO, avaliar_trcc, parse_trava
from iris.schemas.engagement import (
    DUA_PRINCIPLE_ID,
    DUA_PRINCIPLE_LABEL,
    DUA_PRINCIPLE_REFERENCE,
    NON_SUBSTITUTION_RULE,
    EngagementMetadata,
    validate_engagement_profile,
)


@dataclass
class MotivationalContext:
    """Bloco estruturado de contexto motivacional pronto para injeção no pipeline de adaptação."""

    principio_dua: str
    principio_dua_rotulo: str
    diretriz_dua_referencia: str
    possui_ancoras_motivacionais: bool
    ancoras_tematicas: list[str]
    canais_apoio: list[str]
    potencialidades_estudante: str | None
    diretrizes_prompt: list[str]
    conceitos_trava_protegidos: list[str]
    regra_nao_substituicao: str
    evidencias_rag: list[dict[str, Any]]
    prompt_section: str

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


def _fetch_engagement_rag_evidence(
    engagement: EngagementMetadata,
    k: int = 3,
) -> list[dict[str, Any]]:
    """Consulta evidências do RAG relacionadas ao Princípio de Engajamento do DUA com fallback seguro."""
    try:
        from iris.rag.bridge import buscar_evidencias

        termos = [item["rotulo"] for item in engagement.interesses_tematicos[:2]]
        termos.extend(item["rotulo"] for item in engagement.canais_engajamento_preferenciais[:2])
        query = (
            "DUA engajamento motivação interesses pessoais relevância autenticidade "
            + " ".join(termos)
        ).strip()
        trechos = buscar_evidencias(
            pergunta=query,
            metodo="bm25",
            k=k,
            filtro_barreira="iniciacao_tarefa",
            sinonimos=True,
            fallback_bm25_se_sem_banco=True,
        )
        return [
            {
                "chunk_id": t.get("chunk_id", ""),
                "titulo": t.get("titulo", ""),
                "pagina": t.get("pagina"),
                "score": t.get("score", 0.0),
                "trecho": (t.get("trecho") or "")[:360],
            }
            for t in trechos
        ]
    except Exception:
        return []


def build_motivational_context(
    engagement: EngagementMetadata | dict[str, Any] | None,
    travas_curriculares: str | Iterable[str] | None = None,
    fetch_rag_evidence: bool = False,
) -> MotivationalContext:
    """Constrói o contexto motivacional (Princípio I DUA) garantindo proteção da Trava Curricular."""
    if isinstance(engagement, EngagementMetadata):
        meta = engagement
    else:
        meta = validate_engagement_profile(engagement)

    conceitos_trava = [c.rotulo for c in parse_trava(travas_curriculares)]

    ancoras_tematicas: list[str] = [item["rotulo"] for item in meta.interesses_tematicos]
    ancoras_tematicas.extend(meta.interesses_customizados)

    canais_apoio: list[str] = [item["rotulo"] for item in meta.canais_engajamento_preferenciais]

    diretrizes_prompt: list[str] = []
    for item in meta.interesses_tematicos:
        diretrizes_prompt.append(
            f"[Interesse: {item['rotulo']}] {item['ancora_sugerida']}"
        )
    for custom in meta.interesses_customizados:
        diretrizes_prompt.append(
            f"[Interesse específico: {custom}] Usar apenas como exemplo periférico ou gancho introdutório."
        )
    for canal in meta.canais_engajamento_preferenciais:
        diretrizes_prompt.append(
            f"[Canal preferencial: {canal['rotulo']}] {canal['estrategia_apoio']}"
        )
    if meta.potencialidades:
        diretrizes_prompt.append(
            f"[Potencialidade observada] Apoiar-se em: {meta.potencialidades}"
        )

    evidencias_rag: list[dict[str, Any]] = []
    if meta.possui_ancoras_motivacionais and fetch_rag_evidence:
        evidencias_rag = _fetch_engagement_rag_evidence(meta)

    if not meta.possui_ancoras_motivacionais:
        return MotivationalContext(
            principio_dua=DUA_PRINCIPLE_ID,
            principio_dua_rotulo=DUA_PRINCIPLE_LABEL,
            diretriz_dua_referencia=DUA_PRINCIPLE_REFERENCE,
            possui_ancoras_motivacionais=False,
            ancoras_tematicas=[],
            canais_apoio=[],
            potencialidades_estudante=None,
            diretrizes_prompt=[],
            conceitos_trava_protegidos=conceitos_trava,
            regra_nao_substituicao=NON_SUBSTITUTION_RULE,
            evidencias_rag=[],
            prompt_section="",
        )

    linhas: list[str] = [
        "=== CONTEXTO MOTIVACIONAL E POTENCIALIDADES (PRINCÍPIO I DO DUA — REDE DE ENGAJAMENTO) ===",
        f"Fundamento: {DUA_PRINCIPLE_LABEL} ({DUA_PRINCIPLE_REFERENCE}).",
    ]
    if ancoras_tematicas:
        linhas.append("Interesses temáticos (âncoras periféricas): " + "; ".join(ancoras_tematicas) + ".")
    if meta.potencialidades:
        linhas.append(f"Potencialidades do estudante: {meta.potencialidades}")
    if canais_apoio:
        linhas.append("Canais preferenciais de engajamento: " + "; ".join(canais_apoio) + ".")

    if diretrizes_prompt:
        linhas.append("Diretrizes de engajamento aplicáveis:")
        for d in diretrizes_prompt:
            linhas.append(f"- {d}")

    if evidencias_rag:
        linhas.append("Evidências recuperadas do corpus científico (RAG):")
        for idx, ev in enumerate(evidencias_rag, start=1):
            linhas.append(f"- [DUA-E{idx}] {ev['titulo']}: {ev['trecho']}")

    linhas.append("REGRAS INEGOCIÁVEIS DE PRESERVAÇÃO CURRICULAR (ANTI-SUBSTITUIÇÃO):")
    linhas.append(f"- {NON_SUBSTITUTION_RULE}")
    if conceitos_trava:
        linhas.append(
            "- Conceitos obrigatórios da Trava Curricular que NÃO podem ser substituídos pelos interesses: "
            + ", ".join(conceitos_trava)
            + "."
        )
    linhas.append(
        "- Preserve 100% do isolamento de escopo: não altere dimensões não selecionadas pelo docente."
    )

    return MotivationalContext(
        principio_dua=DUA_PRINCIPLE_ID,
        principio_dua_rotulo=DUA_PRINCIPLE_LABEL,
        diretriz_dua_referencia=DUA_PRINCIPLE_REFERENCE,
        possui_ancoras_motivacionais=True,
        ancoras_tematicas=ancoras_tematicas,
        canais_apoio=canais_apoio,
        potencialidades_estudante=meta.potencialidades,
        diretrizes_prompt=diretrizes_prompt,
        conceitos_trava_protegidos=conceitos_trava,
        regra_nao_substituicao=NON_SUBSTITUTION_RULE,
        evidencias_rag=evidencias_rag,
        prompt_section="\n".join(linhas),
    )


def inject_motivational_context_into_prompt(
    base_prompt: str,
    engagement: EngagementMetadata | dict[str, Any] | None,
    travas_curriculares: str | Iterable[str] | None = None,
    fetch_rag_evidence: bool = False,
) -> str:
    """Anexa o bloco motivacional (Princípio I DUA) ao prompt de adaptação sem alterar o restante do contrato."""
    ctx = build_motivational_context(
        engagement=engagement,
        travas_curriculares=travas_curriculares,
        fetch_rag_evidence=fetch_rag_evidence,
    )
    if not ctx.possui_ancoras_motivacionais or not ctx.prompt_section:
        return base_prompt
    cleaned_base = (base_prompt or "").rstrip()
    if not cleaned_base:
        return ctx.prompt_section
    return f"{cleaned_base}\n\n{ctx.prompt_section}"


def verify_motivational_adaptation_preserves_curriculum(
    adapted_text: str,
    travas_curriculares: str | Iterable[str] | None,
    limiar_trcc: float = LIMIAR_PADRAO,
) -> dict[str, Any]:
    """Valida via TRCC determinístico que o uso de interesses/potencialidades não substituiu a trava curricular."""
    resultado = avaliar_trcc(travas_curriculares, adapted_text)
    if resultado.trcc is None:
        return {
            "status": "sem_trava_definida",
            "preservou_trava": True,
            "trcc": None,
            "n_esperados": 0,
            "n_encontrados": 0,
            "conceitos_encontrados": [],
            "conceitos_ausentes": [],
        }

    aprovado = resultado.aprovado(limiar=limiar_trcc)
    return {
        "status": "aprovado" if aprovado else "violacao_substituicao_curricular",
        "preservou_trava": aprovado,
        "trcc": round(resultado.trcc, 4),
        "n_esperados": resultado.n_esperados,
        "n_encontrados": resultado.n_encontrados,
        "conceitos_encontrados": list(resultado.encontrados),
        "conceitos_ausentes": list(resultado.ausentes),
    }
