"""Protocolo de Métricas Objetivas de Avaliação (Challenge 2 — Histórias 4.2.2 e 4.2.5).

Métricas:
    1. TRCC: Taxa de Retenção de Conceitos-Chave
    2. Flesch PT-BR: Legibilidade adaptada por Martins et al. (1996)
    3. SAEN: Aderência Estrutural ao Nível Solicitado
"""

from __future__ import annotations

from typing import Iterable, Set

from iris.eval.readability import flesch_ptbr


def calcular_trcc(
    conceitos_esperados: Iterable[str],
    texto_adaptado: str,
) -> float:
    """Calcula a Taxa de Retenção de Conceitos-Chave (TRCC).

    TRCC = |Conceitos da Trava Presentes no Adaptado| / |Conceitos da Trava Original|
    Critério inegociável do Challenge: TRCC >= 0.95 (95%).
    """
    esperados: Set[str] = {c.lower().strip() for c in conceitos_esperados if c.strip()}
    if not esperados:
        return 1.0

    texto_lower = texto_adaptado.lower()
    encontrados = sum(1 for c in esperados if c in texto_lower)
    return round(encontrados / len(esperados), 4)


def calcular_flesch(texto: str) -> float | None:
    """Calcula o índice Flesch PT-BR usando a implementação calibrada."""
    return flesch_ptbr(texto)


def verificar_aderencia_nivel(
    nivel_esperado: int,
    texto_adaptado: str,
) -> dict[str, bool | str]:
    """Verifica preliminarmente a Aderência Estrutural ao Nível Solicitado (SAEN).

    Nível 1: Destaque de termos em negrito (markdown `**termo**`).
    Nível 2: Itens em checklist (`[ ]`, `- [ ]`, `1.`, `2.`).
    Nível 3: Passo a passo explícito (`Passo 1`, `Etapa 1`).
    """
    if nivel_esperado == 1:
        tem_negrito = "**" in texto_adaptado
        return {"nivel": "1", "valido": tem_negrito, "criterio": "destaque_visual_negrito"}
    elif nivel_esperado == 2:
        tem_checklist = any(m in texto_adaptado for m in ["[ ]", "- [ ]", "1.", "a)"])
        return {"nivel": "2", "valido": tem_checklist, "criterio": "checklist_decomposicao"}
    elif nivel_esperado == 3:
        tem_passos = any(
            m.lower() in texto_adaptado.lower()
            for m in ["passo 1", "etapa 1", "passo a passo", "1º passo"]
        )
        return {"nivel": "3", "valido": tem_passos, "criterio": "escalonamento_passo_a_passo"}
    return {"nivel": str(nivel_esperado), "valido": False, "criterio": "desconhecido"}
