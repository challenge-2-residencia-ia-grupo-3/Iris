"""Curadoria e benchmark contextual do RAG sobre questões escolares reais (`questoes_escolares_v1.json`).

Este módulo mantém as questões estritamente como **casos de entrada de teste** (nunca indexadas no
corpus `iris_trechos`) em duas camadas simples de arquivo + histórico opcional de rodadas:

1. Camada curada (`data/benchmarks/questoes_escolares_curado_v1.json`): limpa ruídos de extração
   (ex.: rodapés `Disponível em: ... Acesso em: ...`) e valida travas curriculares no Pydantic.
2. Avaliação contextual no RAG (`executar_benchmark_rag_escolar` / `avaliar_questao_no_rag`):
   consulta o RAG para cada questão e segmenta os resultados por faixa etária (`EF II` vs `EM`),
   ano escolar, disciplina, característica TDAH, operação cognitiva e porte do texto.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from iris.config import BENCHMARKS_DIR, JUIZ_MODELO_PADRAO, RAG_PACOTE_DIR, REPO_ROOT, get_settings
from iris.eval.rag_metrics import (
    calcular_similaridade_semantica,
    verificar_sustentacao_frase_no_trecho,
)
from iris.eval.sonnet_judge import julgar_resposta_sonnet, sonnet_judge_status
from iris.rag import bridge as rag_bridge
from iris.schemas.adaptation import LIMITE_LATENCIA_MS
from iris.schemas.benchmark import BenchmarkQuestionItem, carregar_questoes_escolares
from iris.schemas.catalog import get_characteristic_by_id

CAMINHO_BRUTO_PADRAO = BENCHMARKS_DIR / "questoes_escolares_v1.json"
CAMINHO_CURADO_PADRAO = BENCHMARKS_DIR / "questoes_escolares_curado_v1.json"
RUNS_RAG_ESCOLAR_PADRAO = REPO_ROOT / "reports" / "rag_escolar_runs.jsonl"
PROGRESSO_RAG_ESCOLAR_LOG = REPO_ROOT / "reports" / "rag_escolar_progress.log"

ESTRATEGIAS_QUERY = ("contexto_pedagogico", "barreira", "enunciado_completo")
AVALIADORES_GERACAO = ("auto", "sonnet", "lexico")

BASELINE_RAG_ESCOLAR_PADRAO = REPO_ROOT / "reports" / "rag_escolar_baseline.json"
PERGUNTAS_FORA_DA_BASE_PADRAO = BENCHMARKS_DIR / "perguntas_fora_da_base_v1.json"
RECUSA_RAG_ESCOLAR_PADRAO = REPO_ROOT / "reports" / "rag_escolar_recusa.json"

# Intervalo de confiança de 95% por reamostragem (bootstrap): sorteia as questões com reposição
# IC_N_REAMOSTRAS vezes e guarda a faixa onde ficam 95% das médias. Semente fixa: repetir dá o mesmo intervalo.
IC_N_REAMOSTRAS = 2000
IC_SEMENTE = 20261113

# Métricas que não medem qualidade: o próprio desenho da busca garante o valor.
METRICAS_POR_CONSTRUCAO = {
    "taxa_retorno_pct": (
        "A busca devolve sempre os k trechos mais bem pontuados da barreira; "
        "só cai se a base não tiver nenhum trecho dessa barreira."
    ),
    "aderencia_barreira_pct": (
        "A busca filtra pela barreira antes de ranquear; todo trecho devolvido já pertence a ela."
    ),
}

# Campos que precisam ser iguais para duas rodadas serem comparáveis.
CAMPOS_CONFIG_RODADA = ("metodo_efetivo", "estrategia_query", "nivel", "k", "gerar_resposta", "avaliador_efetivo")

# (chave no resumo, rótulo, sentido). Sentido "neutro": a mudança é informada, sem dizer se é melhor ou pior.
METRICAS_COMPARADAS = (
    ("fidelidade_media", "Fidelidade", "maior_melhor"),
    ("relevancia_media", "Relevância da resposta", "maior_melhor"),
    ("taxa_abstencao_pct", "Taxa de abstenção (%)", "neutro"),
    ("score_top1_medio", "Pontuação do 1º trecho", "neutro"),
    ("latencia_busca_ms", "Latência da busca (ms)", "menor_melhor"),
    ("latencia_total_ms", "Latência total (ms)", "menor_melhor"),
)

METRICAS_DE_TEMPO = {"latencia_busca_ms", "latencia_total_ms"}

# Bloco bibliográfico entre parênteses contendo "Disponível em: ..."
_RE_CITACAO_PARENTETICA = re.compile(
    r"\s*\([^()\n]*Dispon[ií]vel em:[^()\n]*\)\s*\.?",
    re.IGNORECASE,
)
# Rodapé padrão ENEM / SAEB / ENCCEJA / SME-SP: "Disponível em: <url>. Acesso em: <data> [(adaptado)]. [Fragmento.]"
_RE_DISPONIVEL_ACESSO = re.compile(
    r"\s*Dispon[ií]vel em:\s*(?:<[^>]+>|https?://\S+|www\.\S+|\S+\.(?:com|org|gov|edu|br|net)\S*)"
    r"(?:\s*\.?\s*Acesso em:?\s*\d{1,2}\s*(?:[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}|[.\s\w]{1,20}\d{4})\.?)?"
    r"(?:\s*\((?:adaptado|fragmento)\)\.?)?"
    r"(?:\s*(?:Adaptado|Fragmento)\.?)?",
    re.IGNORECASE,
)
# Referência bibliográfica ABNT terminada em "(adaptado)." (ex.: "DEL PRIORE, M.; VENÂNCIO, R. ... 2006 (adaptado).")
_AUTOR_ABNT = (
    r"[A-ZÀ-Ú][A-ZÀ-Ú\-]{2,}(?:\s+[A-ZÀ-Ú][A-ZÀ-Ú\-]{1,})*,\s*"
    r"(?:[A-ZÀ-Ú]\.(?:\s*[A-ZÀ-Ú]\.)*|[A-ZÀ-Ú][a-zà-ú]+(?:\s+d[eao]s?)?(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*\.?)"
)
_RE_BIBLIO_ABNT = re.compile(
    rf"(?:^|(?<=[.!?”\"\n]\s)|(?<=\n))({_AUTOR_ABNT}(?:\s*;\s*{_AUTOR_ABNT})*\s+"
    rf"[^\n]{{8,260}}?\b(?:19|20)\d{{2}}(?:,\s*p\.\s*\d+)?\s*\(adaptado\)\.?)"
)
_RE_ESPACOS_HORIZONTAIS = re.compile(r"[ \t\u00a0]{2,}")
_RE_QUEBRAS_EXCESSIVAS = re.compile(r"\n{3,}")
_RE_ESPACO_ANTES_PONTUACAO = re.compile(r"\s+([,.;!?])")


def limpar_enunciado_questao(texto: str) -> tuple[str, list[str]]:
    """Remove metadados bibliográficos e ruídos tipográficos do enunciado preservando o conteúdo."""
    regras: list[str] = []
    atual = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    if atual != texto:
        regras.append("normalizacao_quebras_nbsp")

    sem_parentetica = _RE_CITACAO_PARENTETICA.sub(" ", atual)
    if sem_parentetica != atual:
        regras.append("remocao_citacao_parentetica")
        atual = sem_parentetica

    sem_rodape = _RE_DISPONIVEL_ACESSO.sub(" ", atual)
    if sem_rodape != atual:
        regras.append("remocao_rodape_disponivel_em")
        atual = sem_rodape

    sem_abnt = _RE_BIBLIO_ABNT.sub(" ", atual)
    if sem_abnt != atual:
        regras.append("remocao_referencia_abnt")
        atual = sem_abnt

    linhas_limpas: list[str] = []
    for linha in atual.split("\n"):
        limpa = _RE_ESPACOS_HORIZONTAIS.sub(" ", linha).strip()
        limpa = _RE_ESPACO_ANTES_PONTUACAO.sub(r"\1", limpa)
        linhas_limpas.append(limpa)

    consolidado = _RE_QUEBRAS_EXCESSIVAS.sub("\n\n", "\n".join(linhas_limpas)).strip()
    if consolidado != texto and not regras:
        regras.append("normalizacao_espacos")
    return consolidado, regras


def curar_questao(item: BenchmarkQuestionItem) -> tuple[BenchmarkQuestionItem, list[str]]:
    """Aplica saneamento em uma questão garantindo preservação das travas curriculares."""
    enunciado_limpo, regras = limpar_enunciado_questao(item.enunciado_original)
    payload = item.model_dump()
    payload["enunciado_original"] = enunciado_limpo
    if payload.get("alternativas"):
        payload["alternativas"] = [
            {"letra": a["letra"], "texto": _RE_ESPACOS_HORIZONTAIS.sub(" ", a["texto"]).strip()}
            for a in payload["alternativas"]
        ]

    try:
        curado = BenchmarkQuestionItem.model_validate(payload)
        return curado, regras
    except Exception:
        # Se a remoção alterar um termo exigido pela trava curricular, preserva o texto original.
        return item, ["preservado_original_por_trava"]


def curar_dataset_escolar(
    origem: str | Path | None = None,
    destino: str | Path | None = None,
    salvar: bool = True,
) -> dict[str, Any]:
    """Gera a camada curada das questões escolares a partir do dataset bruto."""
    caminho_origem = Path(origem) if origem else CAMINHO_BRUTO_PADRAO
    caminho_destino = Path(destino) if destino else CAMINHO_CURADO_PADRAO

    brutas = carregar_questoes_escolares(caminho_origem)
    curadas: list[BenchmarkQuestionItem] = []
    contador_regras: Counter[str] = Counter()
    modificadas = 0

    for item in brutas:
        curado, regras = curar_questao(item)
        curadas.append(curado)
        if curado.enunciado_original != item.enunciado_original:
            modificadas += 1
        contador_regras.update(regras)

    if salvar:
        caminho_destino.parent.mkdir(parents=True, exist_ok=True)
        conteudo = [q.model_dump(mode="json") for q in curadas]
        caminho_destino.write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "origem": str(caminho_origem),
        "destino": str(caminho_destino),
        "salvo": salvar,
        "total": len(curadas),
        "modificadas": modificadas,
        "regras_aplicadas": dict(contador_regras),
    }


def carregar_questoes_curadas(caminho: str | Path | None = None) -> list[BenchmarkQuestionItem]:
    """Carrega a camada curada (ou sanea o arquivo bruto em memória se a camada curada não existir)."""
    if caminho is not None:
        p = Path(caminho)
        itens = carregar_questoes_escolares(p)
        return [curar_questao(i)[0] for i in itens]

    if CAMINHO_CURADO_PADRAO.exists():
        return carregar_questoes_escolares(CAMINHO_CURADO_PADRAO)

    return [curar_questao(i)[0] for i in carregar_questoes_escolares(CAMINHO_BRUTO_PADRAO)]


def faixa_etaria_por_ano(ano_escolar: str) -> str:
    """Agrupa o ano escolar na faixa etária macro utilizada nos painéis analíticos."""
    return "Ensino Fundamental II" if "EF" in ano_escolar else "Ensino Médio"


def porte_texto_por_tamanho(texto: str) -> str:
    """Classifica a extensão do enunciado original para análise por densidade textual."""
    n = len(texto)
    if n < 250:
        return "curto"
    if n <= 800:
        return "medio"
    return "longo"


def fonte_eh_oficial(item: BenchmarkQuestionItem) -> bool:
    """Indica se a questão possui origem de exame/avaliação pública oficial identificada."""
    if item.fonte is None:
        return False
    origem_l = item.fonte.origem.lower()
    return "não oficial" not in origem_l and "05esc" not in origem_l


def _enriquecer_questao(item: BenchmarkQuestionItem) -> dict[str, Any]:
    """Serializa uma questão escolar com metadados contextuais derivados para filtro e UI."""
    carac = get_characteristic_by_id(item.id_caracteristica_alvo)
    data = item.model_dump(mode="json")
    data.update(
        {
            "faixa_etaria": faixa_etaria_por_ano(item.ano_escolar),
            "porte_texto": porte_texto_por_tamanho(item.enunciado_original),
            "char_count": len(item.enunciado_original),
            "word_count": len(item.enunciado_original.split()),
            "tem_alternativas": bool(item.alternativas),
            "fonte_oficial": fonte_eh_oficial(item),
            "nome_caracteristica": carac.nome,
            "barreira_rag_associada": carac.barreira_rag_associada,
            "texto_completo": item.texto_completo,
        }
    )
    return data


def _bate_igual(valor: Any, esperado: str | None) -> bool:
    if not esperado:
        return True
    return str(valor or "").strip().lower() == esperado.strip().lower()


def filtrar_questoes_escolares(
    itens: Iterable[BenchmarkQuestionItem],
    *,
    disciplina: str | None = None,
    ano_escolar: str | None = None,
    faixa_etaria: str | None = None,
    id_caracteristica_alvo: str | None = None,
    operacao_cognitiva: str | None = None,
    porte_texto: str | None = None,
    apenas_oficiais: bool = False,
    q: str | None = None,
) -> list[dict[str, Any]]:
    """Filtra questões curadas pelos recortes contextuais desejados."""
    termo = (q or "").strip().lower()
    filtrados: list[dict[str, Any]] = []
    for item in itens:
        enr = _enriquecer_questao(item)
        if not _bate_igual(enr["disciplina"], disciplina):
            continue
        if not _bate_igual(enr["ano_escolar"], ano_escolar):
            continue
        if not _bate_igual(enr["faixa_etaria"], faixa_etaria):
            continue
        if not _bate_igual(enr["id_caracteristica_alvo"], id_caracteristica_alvo):
            continue
        if not _bate_igual(enr["operacao_cognitiva"], operacao_cognitiva):
            continue
        if not _bate_igual(enr["porte_texto"], porte_texto):
            continue
        if apenas_oficiais and not enr["fonte_oficial"]:
            continue
        if termo and termo not in enr["id"].lower() and termo not in enr["enunciado_original"].lower():
            continue
        filtrados.append(enr)
    return filtrados


def buscar_questao_curada_por_id(
    question_id: str,
    caminho: str | Path | None = None,
) -> BenchmarkQuestionItem:
    """Localiza uma questão pelo `id` na camada curada ou lança `KeyError` se ausente."""
    for item in carregar_questoes_curadas(caminho):
        if item.id == question_id:
            return item
    raise KeyError(f"Questão escolar não encontrada: {question_id!r}")


def listar_questoes_escolares(
    *,
    disciplina: str | None = None,
    ano_escolar: str | None = None,
    faixa_etaria: str | None = None,
    id_caracteristica_alvo: str | None = None,
    operacao_cognitiva: str | None = None,
    porte_texto: str | None = None,
    apenas_oficiais: bool = False,
    q: str | None = None,
    limite: int = 0,
    caminho: str | Path | None = None,
) -> dict[str, Any]:
    """Retorna as questões curadas filtradas junto das facetas disponíveis na base."""
    carregadas = carregar_questoes_curadas(caminho)
    todas = [_enriquecer_questao(i) for i in carregadas]
    filtradas = filtrar_questoes_escolares(
        carregadas,
        disciplina=disciplina,
        ano_escolar=ano_escolar,
        faixa_etaria=faixa_etaria,
        id_caracteristica_alvo=id_caracteristica_alvo,
        operacao_cognitiva=operacao_cognitiva,
        porte_texto=porte_texto,
        apenas_oficiais=apenas_oficiais,
        q=q,
    )
    facetas = {
        "disciplinas": sorted({x["disciplina"] for x in todas}),
        "anos_escolares": sorted({x["ano_escolar"] for x in todas}),
        "faixas_etarias": sorted({x["faixa_etaria"] for x in todas}),
        "caracteristicas": sorted({x["id_caracteristica_alvo"] for x in todas}),
        "operacoes_cognitivas": sorted({x["operacao_cognitiva"] for x in todas}),
        "portes_texto": ["curto", "medio", "longo"],
    }
    itens_saida = filtradas[:limite] if limite and limite > 0 else filtradas
    return {
        "camada_curada_ativa": CAMINHO_CURADO_PADRAO.exists() if caminho is None else True,
        "total_base": len(todas),
        "total_filtrado": len(filtradas),
        "facetas": facetas,
        "itens": itens_saida,
    }


def montar_consulta_rag_questao(
    item: BenchmarkQuestionItem,
    nivel: int = 2,
    estrategia: str = "contexto_pedagogico",
) -> dict[str, Any]:
    """Traduz uma questão escolar em consulta ao RAG segundo a estratégia selecionada."""
    if estrategia not in ESTRATEGIAS_QUERY:
        raise ValueError(f"Estratégia inválida: {estrategia!r}. Use uma de {ESTRATEGIAS_QUERY}.")

    carac = get_characteristic_by_id(item.id_caracteristica_alvo)
    chave_nivel = f"nivel_{nivel}"
    if chave_nivel not in carac.diretrizes_andaime:
        raise ValueError(f"Nível de andaime inválido: {nivel!r}. Use 1, 2 ou 3.")

    diretriz = carac.diretrizes_andaime[chave_nivel]
    faixa = faixa_etaria_por_ano(item.ano_escolar)
    porte = porte_texto_por_tamanho(item.enunciado_original)
    formato = "objetiva com alternativas" if item.alternativas else "discursiva aberta"

    if estrategia == "barreira":
        pergunta_adicional = ""
    elif estrategia == "contexto_pedagogico":
        pergunta_adicional = (
            f"Quais diretrizes pedagógicas fundamentadas nos trechos se aplicam à adaptação de uma atividade de "
            f"{item.disciplina}, {item.ano_escolar} ({faixa}), operação cognitiva {item.operacao_cognitiva}, "
            f"texto {porte}, formato {formato}, sem criar novas questões?"
        )
    else:
        pergunta_adicional = item.texto_completo

    termos_query = " ".join(carac.palavras_chave_busca[:3])
    consulta_composta = (
        f"{carac.nome}. {diretriz.objetivo_andaime}. {termos_query}. {pergunta_adicional}".strip()
    )
    return {
        "id_caracteristica": carac.id_caracteristica,
        "nome_caracteristica": carac.nome,
        "barreira_rag_associada": carac.barreira_rag_associada,
        "nivel": nivel,
        "estrategia_query": estrategia,
        "pergunta_adicional": pergunta_adicional,
        "consulta_composta": consulta_composta,
        "diretriz_andaime": diretriz.to_dict(),
    }


def avaliar_qualidade_geracao_lexica(
    pergunta: str,
    resposta_texto: str,
    trechos: list[dict[str, Any]],
) -> dict[str, float]:
    """Calcula fidelidade frase a frase e relevância léxica sobre os trechos entregues."""
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", resposta_texto.strip()) if len(f.split()) >= 4]
    pontos = 0.0
    for f in frases:
        nums = [int(n) for n in re.findall(r"\[T(\d+)\]", f) if 1 <= int(n) <= len(trechos)]
        textos_cit = [trechos[n - 1].get("trecho") or trechos[n - 1].get("texto", "") for n in nums]
        ver = verificar_sustentacao_frase_no_trecho(f, textos_cit)
        if ver == "apoiada":
            pontos += 1.0
        elif ver == "parcial":
            pontos += 0.5
    fidelidade = round(pontos / max(len(frases), 1), 3) if frases else 1.0
    relevancia = round(min(1.0, calcular_similaridade_semantica(pergunta, resposta_texto) * 1.8), 3)
    return {"fidelidade_lexica": fidelidade, "relevancia_lexica": relevancia}


def _executar_geracao_segura(
    pergunta: str,
    metodo: str,
    k: int,
    filtro_barreira: str | None,
) -> dict[str, Any]:
    """Invoca `responder_fundamentado` com sincronização de provedor e fallback extrativo."""
    from iris.core.llm_client import get_llm_client

    client = get_llm_client(allow_fallback_to_extractive=True)
    status_llm = client.status()
    primary = getattr(client, "_primary", None)
    resolve_fn = getattr(primary, "_resolve_model", None)
    modelo_resolvido = get_settings().llm_model
    if status_llm.get("primary_available") and callable(resolve_fn):
        try:
            modelo_resolvido = str(resolve_fn() or modelo_resolvido)
        except Exception:
            pass

    settings = get_settings()
    api_sonnet = (settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    old_rag_llm = os.environ.get("RAG_LLM")
    old_rag_modelo = os.environ.get("RAG_LLM_MODELO")
    old_api_key = os.environ.get("ANTHROPIC_API_KEY")
    llm_fallback_aplicado = False
    llm_erro: str | None = None
    try:
        if api_sonnet and old_rag_llm not in {"extractive", "mock", "offline"}:
            os.environ["ANTHROPIC_API_KEY"] = api_sonnet
            os.environ["RAG_LLM"] = "anthropic"
            os.environ["RAG_LLM_MODELO"] = settings.judge_model or JUIZ_MODELO_PADRAO
            try:
                res = rag_bridge.responder_fundamentado(
                    pergunta=pergunta,
                    metodo=metodo,
                    k=k,
                    filtro_barreira=filtro_barreira,
                )
            except Exception as exc:  # noqa: BLE001
                llm_fallback_aplicado = True
                llm_erro = str(exc)
                os.environ["RAG_LLM"] = "extractive"
                os.environ["RAG_LLM_MODELO"] = "deterministic-bm25-extractive"
                res = rag_bridge.responder_fundamentado(
                    pergunta=pergunta,
                    metodo=metodo,
                    k=k,
                    filtro_barreira=filtro_barreira,
                )
        elif status_llm.get("primary_available"):
            provedor_cfg = str(status_llm["configured_provider"])
            os.environ["RAG_LLM"] = provedor_cfg
            # Provedor extrativo não chama modelo: gravar o nome do modelo configurado enganaria a procedência.
            os.environ["RAG_LLM_MODELO"] = (
                "deterministic-bm25-extractive" if provedor_cfg in {"extractive", "mock", "offline"} else modelo_resolvido
            )
            try:
                res = rag_bridge.responder_fundamentado(
                    pergunta=pergunta,
                    metodo=metodo,
                    k=k,
                    filtro_barreira=filtro_barreira,
                )
            except Exception as exc:  # noqa: BLE001
                llm_fallback_aplicado = True
                llm_erro = str(exc)
                os.environ["RAG_LLM"] = "extractive"
                os.environ["RAG_LLM_MODELO"] = "deterministic-bm25-extractive"
                res = rag_bridge.responder_fundamentado(
                    pergunta=pergunta,
                    metodo=metodo,
                    k=k,
                    filtro_barreira=filtro_barreira,
                )
        else:
            llm_fallback_aplicado = status_llm.get("configured_provider") != "extractive"
            os.environ["RAG_LLM"] = "extractive"
            os.environ["RAG_LLM_MODELO"] = "deterministic-bm25-extractive"
            res = rag_bridge.responder_fundamentado(
                pergunta=pergunta,
                metodo=metodo,
                k=k,
                filtro_barreira=filtro_barreira,
            )
    finally:
        if old_rag_llm is None:
            os.environ.pop("RAG_LLM", None)
        else:
            os.environ["RAG_LLM"] = old_rag_llm
        if old_rag_modelo is None:
            os.environ.pop("RAG_LLM_MODELO", None)
        else:
            os.environ["RAG_LLM_MODELO"] = old_rag_modelo
        if old_api_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = old_api_key

    res["llm_fallback_aplicado"] = llm_fallback_aplicado
    res["llm_erro"] = llm_erro
    return res


def avaliar_questao_no_rag(
    item: BenchmarkQuestionItem,
    *,
    nivel: int = 2,
    metodo: str | None = None,
    k: int = 5,
    estrategia_query: str = "contexto_pedagogico",
    gerar_resposta: bool = False,
    avaliador_geracao: str = "auto",
    chunks_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Executa uma questão escolar no RAG (busca filtrada e geração opcional) e retorna métricas."""
    t0 = time.perf_counter()
    enr = _enriquecer_questao(item)
    consulta = montar_consulta_rag_questao(item, nivel=nivel, estrategia=estrategia_query)
    barreira = consulta["barreira_rag_associada"]
    mapa_chunks = chunks_map if chunks_map is not None else {
        c["chunk_id"]: c for c in rag_bridge.obter_trechos_base()
    }

    t_busca0 = time.perf_counter()
    busca = rag_bridge.buscar_evidencias_com_meta(
        pergunta=consulta["consulta_composta"],
        metodo=metodo,
        k=k,
        filtro_barreira=barreira,
        sinonimos=True,
    )
    segundos_busca = round(time.perf_counter() - t_busca0, 4)
    trechos = busca["trechos"]
    metodo_efetivo = busca["metodo_efetivo"]

    resposta_texto: str | None = None
    telemetria_geracao: dict[str, Any] | None = None
    juiz_sonnet_detalhe: dict[str, Any] | None = None

    if gerar_resposta:
        res_gen = _executar_geracao_segura(
            pergunta=consulta["consulta_composta"],
            metodo=metodo_efetivo,
            k=k,
            filtro_barreira=barreira,
        )
        trechos = res_gen.get("trechos_entregues") or trechos
        resposta_texto = res_gen.get("resposta", "")
        conf = res_gen.get("conferencia", {})
        lex = avaliar_qualidade_geracao_lexica(consulta["consulta_composta"], resposta_texto, trechos)

        modo_av = (avaliador_geracao or "auto").strip().lower()
        sonnet_ready = sonnet_judge_status()["ready"]
        usar_sonnet = modo_av == "sonnet" or (modo_av == "auto" and sonnet_ready)

        fidelidade_sonnet: float | None = None
        fidelidade_sonnet_bruta: float | None = None
        relevancia_sonnet: float | None = None
        juiz_sonnet_erro: str | None = None
        avaliador_efetivo = "lexico_local"

        if usar_sonnet:
            try:
                ver_sonnet = julgar_resposta_sonnet(
                    pergunta=consulta["consulta_composta"],
                    trechos=trechos,
                    resposta=resposta_texto,
                )
                juiz_sonnet_detalhe = ver_sonnet
                fidelidade_sonnet = ver_sonnet["fidelidade_sonnet"]
                fidelidade_sonnet_bruta = ver_sonnet["fidelidade_sonnet_bruta"]
                relevancia_sonnet = ver_sonnet["relevancia_sonnet"]
                avaliador_efetivo = "claude_sonnet"
            except Exception as exc:  # noqa: BLE001
                juiz_sonnet_erro = str(exc)

        fidelidade_efetiva = fidelidade_sonnet if fidelidade_sonnet is not None else lex["fidelidade_lexica"]
        relevancia_efetiva = relevancia_sonnet if relevancia_sonnet is not None else lex["relevancia_lexica"]

        rf = (juiz_sonnet_detalhe or {}).get("resumo_frases") or {}
        frases_sem_cit = int(rf.get("sem_citacao", len(conf.get("frases_sem_citacao", []))))

        telemetria_geracao = {
            "llm": res_gen.get("llm"),
            "llm_fallback_aplicado": bool(res_gen.get("llm_fallback_aplicado", False)),
            "llm_erro": res_gen.get("llm_erro"),
            "avaliador_solicitado": modo_av,
            "avaliador_fidelidade": avaliador_efetivo,
            "modelo_juiz": sonnet_judge_status()["model"] if avaliador_efetivo == "claude_sonnet" else None,
            "fidelidade_efetiva": fidelidade_efetiva,
            "relevancia_efetiva": relevancia_efetiva,
            "fidelidade_sonnet": fidelidade_sonnet,
            "fidelidade_sonnet_bruta": fidelidade_sonnet_bruta,
            "relevancia_sonnet": relevancia_sonnet,
            "juiz_sonnet_erro": juiz_sonnet_erro,
            "fidelidade_lexica": lex["fidelidade_lexica"],
            "relevancia_lexica": lex["relevancia_lexica"],
            "citacoes_invalidas": len(conf.get("citacoes_invalidas", [])),
            "frases_sem_citacao": frases_sem_cit,
            "frases_apoiadas": int(rf.get("apoiada", 0)) if juiz_sonnet_detalhe else None,
            "frases_parciais": int(rf.get("parcial", 0)) if juiz_sonnet_detalhe else None,
            "frases_nao_apoiadas": int(rf.get("nao_apoiada", 0)) if juiz_sonnet_detalhe else None,
            "frases_rejeitadas": int(rf.get("rejeitado", 0)) if juiz_sonnet_detalhe else None,
            "frases_total": int(rf.get("total_conteudo", 0)) if juiz_sonnet_detalhe else None,
            "absteve": bool(conf.get("absteve", False)),
            "citou_trecho_com_aviso": list(conf.get("citou_trecho_com_aviso", [])),
        }

    trechos_norm = [
        rag_bridge.normalizar_trecho_ui(
            t,
            ref=f"T{idx}",
            chunk_meta=mapa_chunks.get(t.get("chunk_id", ""), {}),
            status_gabarito=f"Score: {float(t.get('score') or 0.0):.3f}",
        )
        for idx, t in enumerate(trechos, start=1)
    ]

    scores = [float(t["score"]) for t in trechos_norm if t.get("score") is not None]
    barreiras_aderentes = sum(
        1
        for t in trechos_norm
        if barreira in (mapa_chunks.get(t["chunk_id"], {}).get("barreiras") or [])
    )
    n_trechos = len(trechos_norm)
    qtd_avisos = sum(1 for t in trechos_norm if t.get("nao_usar_para"))
    qtd_restritos = sum(1 for t in trechos_norm if t.get("licenca_restrita"))

    metricas = {
        "n_trechos": n_trechos,
        "retornou_evidencia": n_trechos > 0,
        "score_top1": round(scores[0], 4) if scores else 0.0,
        "score_medio": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "aderencia_barreira_pct": round((barreiras_aderentes / n_trechos) * 100.0, 1) if n_trechos else 0.0,
        "texto_util_pct": round(((n_trechos - qtd_restritos) / n_trechos) * 100.0, 1) if n_trechos else 0.0,
        "trechos_sem_aviso_pct": round(((n_trechos - qtd_avisos) / n_trechos) * 100.0, 1) if n_trechos else 0.0,
        "qtd_avisos_uso": qtd_avisos,
        "qtd_licenca_restrita": qtd_restritos,
        "segundos_busca": segundos_busca,
        "segundos_total": round(time.perf_counter() - t0, 4),
    }
    if telemetria_geracao is not None:
        metricas.update(telemetria_geracao)

    return {
        "questao": enr,
        "consulta": consulta,
        "metodo_solicitado": busca["metodo_solicitado"],
        "metodo_efetivo": metodo_efetivo,
        "fallback_aplicado": busca["fallback_aplicado"],
        "fallback_motivo": busca.get("fallback_motivo"),
        "gerar_resposta": gerar_resposta,
        "resposta": resposta_texto,
        "juiz_sonnet": juiz_sonnet_detalhe,
        "metricas": metricas,
        "trechos_recuperados": trechos_norm,
    }


def _media_num(valores: list[float | int | None]) -> float | None:
    validos = [float(v) for v in valores if v is not None]
    return round(sum(validos) / len(validos), 4) if validos else None


def intervalo_confianca_media(
    valores: Iterable[float | int | None],
    *,
    n_reamostras: int = IC_N_REAMOSTRAS,
    semente: int = IC_SEMENTE,
) -> list[float] | None:
    """Intervalo de confiança de 95% da média, por reamostragem (bootstrap percentil) com semente fixa.

    Devolve `[limite_inferior, limite_superior]`, ou `None` com menos de 2 valores (não há o que reamostrar).
    """
    validos = [float(v) for v in valores if v is not None]
    n = len(validos)
    if n < 2:
        return None
    rng = random.Random(semente)
    medias = sorted(sum(rng.choices(validos, k=n)) / n for _ in range(n_reamostras))
    return [round(medias[int(0.025 * n_reamostras)], 4), round(medias[int(0.975 * n_reamostras) - 1], 4)]


def _intervalos_do_grupo(itens: list[dict[str, Any]], com_gen: list[dict[str, Any]]) -> dict[str, list[float]]:
    """IC95 das métricas que são média por questão, na mesma unidade em que o resumo as mostra."""
    series: dict[str, list[float | int | None]] = {
        "score_top1_medio": [r.get("score_top1") for r in itens],
        "latencia_busca_ms": [
            float(r["segundos_busca"]) * 1000.0 if r.get("segundos_busca") is not None else None for r in itens
        ],
        "latencia_total_ms": [
            float(r["segundos_total"]) * 1000.0 if r.get("segundos_total") is not None else None for r in itens
        ],
    }
    if com_gen:
        series["fidelidade_media"] = [
            r.get("fidelidade_efetiva") if r.get("fidelidade_efetiva") is not None else r.get("fidelidade_lexica")
            for r in com_gen
        ]
        series["relevancia_media"] = [
            r.get("relevancia_efetiva") if r.get("relevancia_efetiva") is not None else r.get("relevancia_lexica")
            for r in com_gen
        ]
        series["taxa_abstencao_pct"] = [100.0 if r.get("absteve") else 0.0 for r in com_gen]
    saida: dict[str, list[float]] = {}
    for chave, valores in series.items():
        ic = intervalo_confianca_media(valores)
        if ic is not None:
            casas = 1 if chave.endswith(("_ms", "_pct")) else 4
            saida[chave] = [round(ic[0], casas), round(ic[1], casas)]
    return saida


def _resumir_grupo_itens(itens: list[dict[str, Any]], *, com_ic: bool = False) -> dict[str, Any]:
    """Agrega as métricas de recuperação e geração de um grupo de questões avaliadas.

    Com `com_ic=True` acrescenta `ic95`: o intervalo de confiança de cada métrica que é média por questão.
    """
    n = len(itens)
    if n == 0:
        return {
            **({"ic95": {}} if com_ic else {}),
            "total": 0,
            "taxa_retorno_pct": 0.0,
            "media_trechos": 0.0,
            "score_top1_medio": 0.0,
            "score_medio": 0.0,
            "aderencia_barreira_pct": 0.0,
            "texto_util_pct": 0.0,
            "trechos_sem_aviso_pct": 0.0,
            "taxa_com_aviso_uso_pct": 0.0,
            "taxa_licenca_restrita_pct": 0.0,
            "latencia_busca_ms": 0.0,
            "latencia_total_ms": 0.0,
            "com_geracao": 0,
            "avaliador_fidelidade": None,
            "taxa_abstencao_pct": None,
            "fidelidade_media": None,
            "relevancia_media": None,
            "fidelidade_sonnet_media": None,
            "relevancia_sonnet_media": None,
            "fidelidade_lexica_media": None,
            "relevancia_lexica_media": None,
            "citacoes_invalidas_total": 0,
            "frases_total": 0,
            "frases_apoiadas_total": 0,
            "frases_parciais_total": 0,
            "frases_nao_apoiadas_total": 0,
            "frases_rejeitadas_total": 0,
            "frases_sem_citacao_total": 0,
            "frases_sustentadas_pct": None,
            "frases_parciais_pct": None,
        }

    retornaram = sum(1 for r in itens if r.get("retornou_evidencia"))
    com_aviso = sum(1 for r in itens if (r.get("qtd_avisos_uso") or 0) > 0)
    com_restrita = sum(1 for r in itens if (r.get("qtd_licenca_restrita") or 0) > 0)
    total_trechos = sum(int(r.get("n_trechos") or 0) for r in itens)
    total_restritos = sum(int(r.get("qtd_licenca_restrita") or 0) for r in itens)
    total_avisos = sum(int(r.get("qtd_avisos_uso") or 0) for r in itens)
    com_gen = [
        r for r in itens if r.get("fidelidade_lexica") is not None or r.get("fidelidade_efetiva") is not None
    ]
    tem_sonnet = any(r.get("fidelidade_sonnet") is not None for r in com_gen)
    avaliador_fid = "claude_sonnet" if tem_sonnet else ("lexico_local" if com_gen else None)

    frases_total = sum(int(r.get("frases_total") or 0) for r in com_gen)
    frases_apoiadas = sum(int(r.get("frases_apoiadas") or 0) for r in com_gen)
    frases_parciais = sum(int(r.get("frases_parciais") or 0) for r in com_gen)
    frases_nao_apoiadas = sum(int(r.get("frases_nao_apoiadas") or 0) for r in com_gen)
    frases_rejeitadas = sum(int(r.get("frases_rejeitadas") or 0) for r in com_gen)
    frases_sem_citacao = sum(int(r.get("frases_sem_citacao") or 0) for r in com_gen)

    return {
        **({"ic95": _intervalos_do_grupo(itens, com_gen)} if com_ic else {}),
        "total": n,
        # Uma medida de busca que pode falhar: quantos conjuntos diferentes de trechos a rodada devolveu.
        # Se 136 questões recebem só 37 conjuntos, a busca responde à característica, não à questão.
        "conjuntos_distintos_trechos": len({tuple(r.get("chunk_ids") or []) for r in itens}),
        "trechos_distintos": len({cid for r in itens for cid in (r.get("chunk_ids") or [])}),
        "taxa_retorno_pct": round((retornaram / n) * 100.0, 1),
        "media_trechos": round(total_trechos / n, 2),
        "score_top1_medio": _media_num([r.get("score_top1") for r in itens]) or 0.0,
        "score_medio": _media_num([r.get("score_medio") for r in itens]) or 0.0,
        "aderencia_barreira_pct": round(sum(r.get("aderencia_barreira_pct", 0.0) for r in itens) / n, 1),
        "texto_util_pct": round(((total_trechos - total_restritos) / total_trechos) * 100.0, 1) if total_trechos else 0.0,
        "trechos_sem_aviso_pct": round(((total_trechos - total_avisos) / total_trechos) * 100.0, 1) if total_trechos else 0.0,
        "taxa_com_aviso_uso_pct": round((com_aviso / n) * 100.0, 1),
        "taxa_licenca_restrita_pct": round((com_restrita / n) * 100.0, 1),
        "latencia_busca_ms": round((_media_num([r.get("segundos_busca") for r in itens]) or 0.0) * 1000.0, 1),
        "latencia_total_ms": round((_media_num([r.get("segundos_total") for r in itens]) or 0.0) * 1000.0, 1),
        "com_geracao": len(com_gen),
        "avaliador_fidelidade": avaliador_fid,
        "taxa_abstencao_pct": (
            round((sum(1 for r in com_gen if r.get("absteve")) / len(com_gen)) * 100.0, 1)
            if com_gen
            else None
        ),
        "fidelidade_media": _media_num(
            [
                r.get("fidelidade_efetiva") if r.get("fidelidade_efetiva") is not None else r.get("fidelidade_lexica")
                for r in com_gen
            ]
        ),
        "relevancia_media": _media_num(
            [
                r.get("relevancia_efetiva") if r.get("relevancia_efetiva") is not None else r.get("relevancia_lexica")
                for r in com_gen
            ]
        ),
        "fidelidade_sonnet_media": _media_num([r.get("fidelidade_sonnet") for r in com_gen]),
        "relevancia_sonnet_media": _media_num([r.get("relevancia_sonnet") for r in com_gen]),
        "fidelidade_lexica_media": _media_num([r.get("fidelidade_lexica") for r in com_gen]),
        "relevancia_lexica_media": _media_num([r.get("relevancia_lexica") for r in com_gen]),
        "citacoes_invalidas_total": sum(int(r.get("citacoes_invalidas") or 0) for r in com_gen),
        "frases_total": frases_total,
        "frases_apoiadas_total": frases_apoiadas,
        "frases_parciais_total": frases_parciais,
        "frases_nao_apoiadas_total": frases_nao_apoiadas,
        "frases_rejeitadas_total": frases_rejeitadas,
        "frases_sem_citacao_total": frases_sem_citacao,
        "frases_sustentadas_pct": round((frases_apoiadas / frases_total) * 100.0, 1) if frases_total else None,
        "frases_parciais_pct": round((frases_parciais / frases_total) * 100.0, 1) if frases_total else None,
    }


def _agrupar_por_dimensao(itens: list[dict[str, Any]], chave: str) -> dict[str, dict[str, Any]]:
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in itens:
        grupos[str(item.get(chave) or "não informado")].append(item)
    return {
        nome: _resumir_grupo_itens(lista, com_ic=True)
        for nome, lista in sorted(grupos.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    }


def resumir_rnf07(itens: list[dict[str, Any]], nivel: int | None) -> dict[str, Any] | None:
    """Conta quantas questões ficaram dentro do limite de tempo do RNF-07 para o nível da rodada.

    O RNF-07 limita o ciclo inteiro de adaptação (15 s no nível 1, 40 s nos níveis 2 e 3). O benchmark
    escolar mede só a parte do RAG (busca, geração e juiz), então ficar dentro do limite aqui é condição
    necessária, não suficiente: o Extrator, o Adaptador e o Auditor ainda somam tempo por cima.
    """
    tempos = [float(r["segundos_total"]) * 1000.0 for r in itens if r.get("segundos_total") is not None]
    if not tempos:
        return None
    try:
        nivel_int = int(nivel or 2)
    except (TypeError, ValueError):
        nivel_int = 2
    limite_ms = LIMITE_LATENCIA_MS.get(nivel_int, LIMITE_LATENCIA_MS[2])
    dentro = sum(1 for t in tempos if t <= limite_ms)
    return {
        "nivel": nivel_int,
        "limite_ms": limite_ms,
        "total": len(tempos),
        "dentro": dentro,
        "fora": len(tempos) - dentro,
        "pct_dentro": round((dentro / len(tempos)) * 100.0, 1),
        "maior_ms": round(max(tempos), 1),
        "escopo": "busca + geração + juiz do RAG; o ciclo completo de adaptação soma os agentes por cima",
    }


def _modelo_sem_provedor(rotulo: str | None) -> str | None:
    """`anthropic:claude-x` vira `claude-x`; o gerador grava provedor e modelo juntos, o juiz só o modelo."""
    if not rotulo:
        return None
    return str(rotulo).split(":", 1)[-1].strip().lower() or None


def resumir_modelos(itens: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Diz que modelo gerou e que modelo julgou, e em quantas questões os dois eram o mesmo.

    Um juiz que é o mesmo modelo do gerador tende a aprovar o próprio texto; a nota vale como teto, não
    como medida. Rodadas antigas não gravaram o modelo do juiz: nesses itens o campo conta como desconhecido.
    """
    com_gen = [r for r in itens if r.get("llm")]
    if not com_gen:
        return None
    julgados = [r for r in com_gen if r.get("avaliador_fidelidade") == "claude_sonnet"]
    iguais = sum(
        1
        for r in julgados
        if r.get("modelo_juiz") and _modelo_sem_provedor(r.get("llm")) == _modelo_sem_provedor(r.get("modelo_juiz"))
    )
    return {
        "geradores": sorted({str(r["llm"]) for r in com_gen}),
        "juizes": sorted({str(r["modelo_juiz"]) for r in julgados if r.get("modelo_juiz")}),
        "com_geracao": len(com_gen),
        "julgados_por_modelo": len(julgados),
        "juiz_desconhecido": sum(1 for r in julgados if not r.get("modelo_juiz")),
        "gerador_igual_ao_juiz": iguais,
    }


def _resumir_recusa(itens: list[dict[str, Any]]) -> dict[str, Any]:
    valores = [100.0 if r.get("recusou") else 0.0 for r in itens]
    return {
        "total": len(itens),
        "recusou": sum(1 for r in itens if r.get("recusou")),
        "taxa_recusa_pct": round(sum(valores) / len(valores), 1) if valores else None,
        "ic95": intervalo_confianca_media(valores),
    }


def carregar_perguntas_fora_da_base(caminho: str | Path | None = None) -> list[dict[str, str]]:
    """Lê as perguntas que a base não responde (`id`, `tipo`, `pergunta`)."""
    origem = Path(caminho) if caminho else PERGUNTAS_FORA_DA_BASE_PADRAO
    dados = json.loads(origem.read_text(encoding="utf-8"))
    perguntas = dados.get("perguntas", dados) if isinstance(dados, dict) else dados
    return [
        {"id": str(p["id"]), "tipo": str(p.get("tipo") or "sem_tipo"), "pergunta": str(p["pergunta"])}
        for p in perguntas
        if str(p.get("pergunta") or "").strip()
    ]


def _abstencao_dentro_da_base(caminho_runs: str | Path | None, metodo_efetivo: str | None) -> dict[str, Any] | None:
    """Abstenção da rodada mais recente com geração e a mesma busca: a régua do teste de recusa."""
    for rodada in reversed(carregar_rodadas_rag_escolar(caminho_runs)):
        if not rodada.get("gerar_resposta") or rodada.get("metodo_efetivo") != metodo_efetivo:
            continue
        com_gen = [r for r in rodada.get("itens", []) if r.get("llm")]
        if not com_gen:
            continue
        valores = [100.0 if r.get("absteve") else 0.0 for r in com_gen]
        return {
            "run_id": rodada.get("run_id"),
            "total": len(com_gen),
            "taxa_abstencao_pct": round(sum(valores) / len(valores), 1),
            "ic95": intervalo_confianca_media(valores),
            "geradores": sorted({str(r["llm"]) for r in com_gen}),
        }
    return None


def _recusa_invertida(resumo: dict[str, Any] | None, dentro: dict[str, Any] | None) -> bool:
    """Verdadeiro quando o sistema recusa menos fora da base do que se abstém dentro dela.

    Só acusa quando os dois intervalos de 95% não se tocam: o teto da recusa fora da base fica abaixo do
    piso da abstenção dentro da base. É o contrário do desejado, e não depende de limite escolhido.
    """
    ic_fora = (resumo or {}).get("ic95")
    ic_dentro = (dentro or {}).get("ic95")
    if not ic_fora or not ic_dentro:
        return False
    return float(ic_fora[1]) < float(ic_dentro[0])


def obter_teste_de_recusa(
    *, caminho_saida: str | Path | None = None, caminho_runs: str | Path | None = None
) -> dict[str, Any]:
    """Devolve o último teste de recusa gravado, com a abstenção dentro da base ao lado."""
    origem = Path(caminho_saida) if caminho_saida else RECUSA_RAG_ESCOLAR_PADRAO
    try:
        total_perguntas = len(carregar_perguntas_fora_da_base())
    except (OSError, ValueError, KeyError):
        total_perguntas = 0
    if not origem.exists():
        return {"tem_teste": False, "total_perguntas": total_perguntas}
    try:
        teste = json.loads(origem.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tem_teste": False, "total_perguntas": total_perguntas}
    dentro = _abstencao_dentro_da_base(caminho_runs, teste.get("metodo_efetivo"))
    return {
        "tem_teste": True,
        "total_perguntas": total_perguntas,
        **teste,
        "dentro_da_base": dentro,
        "invertido": _recusa_invertida(teste.get("resumo"), dentro),
    }


def executar_teste_de_recusa(
    *,
    metodo: str | None = None,
    k: int = 5,
    caminho_perguntas: str | Path | None = None,
    caminho_saida: str | Path | None = None,
    caminho_runs: str | Path | None = None,
    salvar: bool = True,
) -> dict[str, Any]:
    """Faz ao RAG perguntas que a base não responde e conta em quantas ele recusou.

    Recusar é responder com a frase fixa de "não encontrei" (campo `absteve` da conferência mecânica).
    Sem filtro de barreira: a pergunta entra como o usuário a digitaria. A taxa sozinha engana, porque um
    sistema que recusa tudo tira 100%; por isso a leitura vem com a abstenção dentro da base ao lado.
    """
    origem = Path(caminho_perguntas) if caminho_perguntas else PERGUNTAS_FORA_DA_BASE_PADRAO
    perguntas = carregar_perguntas_fora_da_base(origem)
    if not perguntas:
        raise ValueError("O arquivo de perguntas fora da base está vazio: o teste de recusa não foi executado.")

    t0 = time.perf_counter()
    itens: list[dict[str, Any]] = []
    metodo_efetivo = metodo or "bm25"
    for p in perguntas:
        t_item = time.perf_counter()
        res = _executar_geracao_segura(pergunta=p["pergunta"], metodo=metodo or "bm25", k=k, filtro_barreira=None)
        conf = res.get("conferencia", {})
        trechos = res.get("trechos_entregues") or []
        metodo_efetivo = res.get("metodo") or metodo_efetivo
        itens.append(
            {
                **p,
                "recusou": bool(conf.get("absteve", False)),
                "resposta": res.get("resposta", ""),
                "llm": res.get("llm"),
                "llm_fallback_aplicado": bool(res.get("llm_fallback_aplicado", False)),
                "n_trechos": len(trechos),
                "trechos_citados": list(conf.get("trechos_citados", [])),
                "segundos_total": round(time.perf_counter() - t_item, 4),
            }
        )

    por_tipo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in itens:
        por_tipo[item["tipo"]].append(item)

    teste = {
        "teste_id": f"recusa-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "metodo_solicitado": metodo or metodo_efetivo,
        "metodo_efetivo": metodo_efetivo,
        "k": k,
        "geradores": sorted({str(i["llm"]) for i in itens if i.get("llm")}),
        "duracao_total_s": round(time.perf_counter() - t0, 3),
        "procedencia": obter_procedencia_rodada(origem),
        "resumo": _resumir_recusa(itens),
        "por_tipo": {tipo: _resumir_recusa(grupo) for tipo, grupo in sorted(por_tipo.items())},
        "itens": itens,
    }

    destino = Path(caminho_saida) if caminho_saida else RECUSA_RAG_ESCOLAR_PADRAO
    if salvar:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(teste, ensure_ascii=False, indent=2), encoding="utf-8")
        return obter_teste_de_recusa(caminho_saida=destino, caminho_runs=caminho_runs)
    dentro = _abstencao_dentro_da_base(caminho_runs, metodo_efetivo)
    return {
        "tem_teste": True,
        "total_perguntas": len(perguntas),
        **teste,
        "dentro_da_base": dentro,
        "invertido": _recusa_invertida(teste["resumo"], dentro),
    }


ORDEM_ELOS = ("busca", "abstencao", "citacao", "fidelidade")
DESCRICAO_ELOS = {
    "busca": {
        "pergunta": "A busca devolveu algum trecho?",
        "medida": "contagem de trechos; a prova não tem gabarito de trechos, então não dá para dizer se eram os certos",
    },
    "abstencao": {
        "pergunta": "Com trechos em mãos, o sistema respondeu?",
        "medida": "frase fixa de recusa detectada pelo código; toda questão da prova deveria ter resposta",
    },
    "citacao": {
        "pergunta": "Cada frase diz de que trecho saiu, e o trecho existe?",
        "medida": "contagem de frases sem [Tn] e de [Tn] que apontam para trecho não entregue",
    },
    "fidelidade": {
        "pergunta": "O que foi escrito está no trecho citado?",
        "medida": "juiz Claude Sonnet, frase a frase; quebra com uma frase não apoiada ou rejeitada. Sem juiz, não há medida",
    },
}


def classificar_elos(item: dict[str, Any]) -> dict[str, Any]:
    """Diz em que elo da corrente (busca, abstenção, citação, fidelidade) uma questão quebrou primeiro.

    Estados: `ok`, `quebrou`, `sem_gabarito` (a busca voltou com trechos, mas não há gabarito para conferir),
    `sem_medida` (falta geração ou juiz) e `nao_se_aplica` (o sistema se absteve, então não há frase a conferir).
    Só o elo da fidelidade depende de modelo; os outros três são contados por código.
    """
    n_trechos = int(item.get("n_trechos") or 0)
    tem_geracao = bool(item.get("llm")) or item.get("resposta") is not None
    absteve = bool(item.get("absteve"))

    estados: dict[str, str] = {"busca": "quebrou" if n_trechos == 0 else "sem_gabarito"}
    if not tem_geracao:
        estados.update({"abstencao": "sem_medida", "citacao": "sem_medida", "fidelidade": "sem_medida"})
    elif absteve:
        # Abster-se sem trecho nenhum é coerente: o elo quebrado é a busca.
        estados["abstencao"] = "ok" if n_trechos == 0 else "quebrou"
        estados.update({"citacao": "nao_se_aplica", "fidelidade": "nao_se_aplica"})
    else:
        estados["abstencao"] = "ok"
        sem_citacao = int(item.get("frases_sem_citacao") or 0)
        invalidas = int(item.get("citacoes_invalidas") or 0)
        estados["citacao"] = "quebrou" if (sem_citacao > 0 or invalidas > 0) else "ok"
        julgado = item.get("avaliador_fidelidade") == "claude_sonnet" and int(item.get("frases_total") or 0) > 0
        if julgado:
            ruins = int(item.get("frases_nao_apoiadas") or 0) + int(item.get("frases_rejeitadas") or 0)
            estados["fidelidade"] = "quebrou" if ruins > 0 else "ok"
        else:
            estados["fidelidade"] = "sem_medida"

    primeiro = next((e for e in ORDEM_ELOS if estados[e] == "quebrou"), None)
    return {"estados": estados, "primeiro_elo_quebrado": primeiro}


def resumir_elos(itens: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Conta, por elo, quantas questões pararam ali primeiro e em quantas o elo pôde ser medido."""
    if not itens:
        return None
    classificados = [classificar_elos(r) for r in itens]
    total = len(classificados)
    por_elo: dict[str, dict[str, Any]] = {}
    for elo in ORDEM_ELOS:
        parou = sum(1 for c in classificados if c["primeiro_elo_quebrado"] == elo)
        medido = sum(1 for c in classificados if c["estados"][elo] in {"ok", "quebrou"})
        por_elo[elo] = {
            **DESCRICAO_ELOS[elo],
            "parou_aqui": parou,
            "pct_parou_aqui": round((parou / total) * 100.0, 1),
            "medido_em": medido,
            "quebrou": sum(1 for c in classificados if c["estados"][elo] == "quebrou"),
        }
    sem_quebra = sum(1 for c in classificados if c["primeiro_elo_quebrado"] is None)
    return {
        "total": total,
        "ordem": list(ORDEM_ELOS),
        "por_elo": por_elo,
        "sem_quebra_medida": sem_quebra,
        "pct_sem_quebra_medida": round((sem_quebra / total) * 100.0, 1),
        "elos_sem_medida": [e for e in ORDEM_ELOS if por_elo[e]["medido_em"] == 0],
    }


def _compactar_registro_item(avaliacao: dict[str, Any]) -> dict[str, Any]:
    """Extrai o registro plano persistido em JSONL para analytics rápido sem inflar disco."""
    q = avaliacao["questao"]
    m = avaliacao["metricas"]
    return {
        "id": q["id"],
        "disciplina": q["disciplina"],
        "ano_escolar": q["ano_escolar"],
        "faixa_etaria": q["faixa_etaria"],
        "operacao_cognitiva": q["operacao_cognitiva"],
        "id_caracteristica_alvo": q["id_caracteristica_alvo"],
        "barreira_rag_associada": q["barreira_rag_associada"],
        "porte_texto": q["porte_texto"],
        "fonte_oficial": q["fonte_oficial"],
        "chunk_ids": [t["chunk_id"] for t in avaliacao["trechos_recuperados"]],
        "titulos_top3": [t["titulo"] for t in avaliacao["trechos_recuperados"][:3]],
        "resposta": avaliacao.get("resposta"),
        **m,
    }


def _sha256_arquivo(caminho: Path) -> str | None:
    """Hash sha256 do arquivo (16 primeiros caracteres), ou `None` se ele não existir."""
    try:
        return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]
    except OSError:
        return None


def _git(*args: str) -> str | None:
    """Roda um comando git de leitura na raiz do repositório; `None` se não houver git ou repositório."""
    try:
        res = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def obter_procedencia_rodada(caminho_dataset: str | Path | None = None) -> dict[str, Any]:
    """Diz que código e que arquivos produziram a rodada: commit, hash da prova e hash da base de trechos.

    Sem isso, duas rodadas com números diferentes não deixam saber se mudou o código, a prova ou a base.
    """
    dataset = Path(caminho_dataset) if caminho_dataset else CAMINHO_CURADO_PADRAO
    if not dataset.exists() and caminho_dataset is None:
        dataset = CAMINHO_BRUTO_PADRAO
    commit = _git("rev-parse", "--short", "HEAD")
    alterados = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "commit": commit,
        "commit_com_alteracoes_locais": bool(alterados) if alterados is not None else None,
        "dataset_arquivo": dataset.name,
        "dataset_sha256": _sha256_arquivo(dataset),
        "base_trechos_sha256": _sha256_arquivo(RAG_PACOTE_DIR / "chunks.jsonl"),
    }


def carregar_linha_de_base(caminho_base: str | Path | None = None) -> dict[str, Any] | None:
    """Lê qual rodada foi promovida a linha de base (`reports/rag_escolar_baseline.json`)."""
    origem = Path(caminho_base) if caminho_base else BASELINE_RAG_ESCOLAR_PADRAO
    try:
        dados = json.loads(origem.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dados if isinstance(dados, dict) and dados.get("run_id") else None


def definir_linha_de_base(
    run_id: str | None,
    *,
    caminho_runs: str | Path | None = None,
    caminho_base: str | Path | None = None,
) -> dict[str, Any]:
    """Promove uma rodada registrada a linha de base; `run_id=None` remove a linha de base."""
    destino = Path(caminho_base) if caminho_base else BASELINE_RAG_ESCOLAR_PADRAO
    if not run_id:
        try:
            destino.unlink()
        except FileNotFoundError:
            pass
        return {"linha_de_base": None}
    rodada = next((r for r in carregar_rodadas_rag_escolar(caminho_runs) if r.get("run_id") == run_id), None)
    if rodada is None:
        raise KeyError(f"Rodada {run_id!r} não encontrada no registro.")
    if not rodada.get("itens"):
        raise ValueError("Uma rodada sem questões não pode ser linha de base.")
    registro = {"run_id": run_id, "definida_em_utc": datetime.now(UTC).isoformat()}
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"linha_de_base": registro}


def comparar_com_linha_de_base(atual: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Compara a rodada atual com a linha de base, métrica a métrica.

    Regra: a métrica "mudou" quando a média atual sai do intervalo de confiança de 95% da linha de base.
    Dentro do intervalo, a diferença pode ser só sorteio e o veredito é "igual". As rodadas só são
    comparadas quando têm a mesma configuração, os mesmos filtros e a mesma prova (hash do arquivo).
    """
    info_base = {
        "run_id": base.get("run_id"),
        "timestamp_utc": base.get("timestamp_utc"),
        "commit": (base.get("procedencia") or {}).get("commit"),
        "total_itens": len(base.get("itens", [])),
    }
    if atual.get("run_id") == base.get("run_id"):
        return {"base": info_base, "mesma_rodada": True, "comparavel": True, "motivos": [], "metricas": []}

    motivos = [
        f"{campo}: linha de base {base.get(campo)!r}, esta rodada {atual.get(campo)!r}"
        for campo in CAMPOS_CONFIG_RODADA
        if base.get(campo) != atual.get(campo)
    ]
    if (base.get("filtros_execucao") or {}) != (atual.get("filtros_execucao") or {}):
        motivos.append("filtros de execução diferentes")
    sha_base = (base.get("procedencia") or {}).get("dataset_sha256")
    sha_atual = (atual.get("procedencia") or {}).get("dataset_sha256")
    if sha_base and sha_atual and sha_base != sha_atual:
        motivos.append(f"a prova mudou: hash {sha_base} na linha de base, {sha_atual} nesta rodada")
    if motivos:
        return {"base": info_base, "mesma_rodada": False, "comparavel": False, "motivos": motivos, "metricas": []}

    r_base = _resumir_grupo_itens(base.get("itens", []), com_ic=True)
    r_atual = _resumir_grupo_itens(atual.get("itens", []), com_ic=True)
    metricas: list[dict[str, Any]] = []
    for chave, rotulo, sentido in METRICAS_COMPARADAS:
        v_base, v_atual = r_base.get(chave), r_atual.get(chave)
        if v_base is None or v_atual is None:
            continue
        ic = r_base["ic95"].get(chave)
        if ic is None:
            veredito = "sem_intervalo"
        elif ic[0] <= float(v_atual) <= ic[1]:
            veredito = "igual"
        elif sentido == "neutro":
            veredito = "mudou"
        else:
            subiu = float(v_atual) > ic[1]
            veredito = "melhorou" if subiu == (sentido == "maior_melhor") else "piorou"
            if chave in METRICAS_DE_TEMPO:
                # Tempo depende da máquina e da carga: vira informação, não juízo de qualidade.
                veredito = "mais_lenta" if veredito == "piorou" else "mais_rapida"
        metricas.append(
            {
                "chave": chave,
                "rotulo": rotulo,
                "sentido": sentido,
                "base": v_base,
                "ic95_base": ic,
                "atual": v_atual,
                "diferenca": round(float(v_atual) - float(v_base), 4),
                "veredito": veredito,
            }
        )
    return {"base": info_base, "mesma_rodada": False, "comparavel": True, "motivos": [], "metricas": metricas}


def avaliar_portao(rodada: dict[str, Any], comparacao: dict[str, Any] | None) -> dict[str, Any]:
    """Resume a comparação com a linha de base num veredito: aprovado, aviso ou reprovado.

    Regras, na ordem:
    - sem linha de base: `sem_base` (não há contra o que aprovar);
    - a própria linha de base: `referencia`;
    - a prova mudou desde a linha de base: `reprovado` (lacre rompido; quem troca a prova redefine a base de propósito);
    - outra configuração ou outros filtros: `aviso` (não comparável);
    - métrica de qualidade pior fora do intervalo de 95% da base: `reprovado`;
    - métrica neutra que mudou (abstenção, pontuação do 1º trecho): `aviso`;
    - o resto: `aprovado`.
    `notas` traz o que não é resultado e por isso não muda o veredito: latência mais lenta ou mais rápida (depende
    da máquina; o limite de tempo que vale é o do RNF-07, mostrado à parte), código com alterações locais não
    commitadas e rodada sem hash da prova.
    """
    if not comparacao:
        return {
            "veredito": "sem_base",
            "motivos": ["Nenhuma linha de base definida: não há contra o que aprovar ou reprovar esta rodada."],
            "notas": [],
        }
    if comparacao.get("mesma_rodada"):
        return {"veredito": "referencia", "motivos": ["Esta rodada é a linha de base."], "notas": []}

    sha_base = None
    sha_atual = (rodada.get("procedencia") or {}).get("dataset_sha256")
    for motivo in comparacao.get("motivos") or []:
        if motivo.startswith("a prova mudou"):
            sha_base = motivo
    if sha_base:
        return {
            "veredito": "reprovado",
            "lacre_rompido": True,
            "notas": [],
            "motivos": [
                (
                    f"Lacre rompido: {sha_base}. Uma rodada só é aprovada contra a mesma prova; se a troca foi "
                    "intencional, redefina a linha de base."
                )
            ],
        }
    if not comparacao.get("comparavel"):
        return {
            "veredito": "aviso",
            "motivos": ["Não comparável com a linha de base: " + "; ".join(comparacao.get("motivos") or [])],
            "notas": [],
        }

    reprovam: list[str] = []
    avisam: list[str] = []
    notas: list[str] = []
    for m in comparacao.get("metricas") or []:
        if m["veredito"] == "piorou":
            reprovam.append(f"{m['rotulo']} piorou: {m['base']} na linha de base, {m['atual']} nesta rodada")
        elif m["veredito"] == "mudou":
            avisam.append(f"{m['rotulo']} mudou: {m['base']} na linha de base, {m['atual']} nesta rodada")
        elif m["veredito"] in {"mais_lenta", "mais_rapida"}:
            notas.append(
                f"{m['rotulo']}: {m['base']} na linha de base, {m['atual']} nesta rodada "
                f"({'mais lenta' if m['veredito'] == 'mais_lenta' else 'mais rápida'}; depende da máquina, não entra no veredito)"
            )
    if (rodada.get("procedencia") or {}).get("commit_com_alteracoes_locais"):
        notas.append("Procedência: o código desta rodada tinha alterações locais não commitadas.")
    if not sha_atual:
        notas.append("Procedência: esta rodada não registrou o hash da prova.")

    if reprovam:
        return {"veredito": "reprovado", "lacre_rompido": False, "motivos": reprovam + avisam, "notas": notas}
    if avisam:
        return {"veredito": "aviso", "motivos": avisam, "notas": notas}
    return {
        "veredito": "aprovado",
        "motivos": ["Mesma prova, mesma configuração e nenhuma métrica fora do intervalo de 95% da linha de base."],
        "notas": notas,
    }


def carregar_rodadas_rag_escolar(caminho: str | Path | None = None) -> list[dict[str, Any]]:
    """Lê todas as rodadas registradas em `reports/rag_escolar_runs.jsonl`."""
    origem = Path(caminho) if caminho else RUNS_RAG_ESCOLAR_PADRAO
    if not origem.exists():
        return []
    rodadas: list[dict[str, Any]] = []
    for linha in origem.read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        try:
            rodadas.append(json.loads(linha))
        except json.JSONDecodeError:
            continue
    return rodadas


def resumir_analytics_rag_escolar(
    rodada: dict[str, Any] | None = None,
    *,
    disciplina: str | None = None,
    ano_escolar: str | None = None,
    faixa_etaria: str | None = None,
    id_caracteristica_alvo: str | None = None,
    operacao_cognitiva: str | None = None,
    porte_texto: str | None = None,
    runs_disponiveis: list[dict[str, Any]] | None = None,
    rodada_base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Agrega uma rodada do benchmark escolar por faixa etária, conteúdo, barreira e porte."""
    if rodada is None:
        return {
            "tem_rodada": False,
            "run_info": None,
            "linha_de_base": None,
            "portao": None,
            "metricas_por_construcao": METRICAS_POR_CONSTRUCAO,
            "rnf07": None,
            "modelos": None,
            "elos": None,
            "resumo_geral": _resumir_grupo_itens([], com_ic=True),
            "por_faixa_etaria": {},
            "por_ano_escolar": {},
            "por_disciplina": {},
            "por_caracteristica": {},
            "por_operacao_cognitiva": {},
            "por_porte_texto": {},
            "itens": [],
            "runs_disponiveis": runs_disponiveis or [],
        }

    itens = [
        item
        for item in rodada.get("itens", [])
        if _bate_igual(item.get("disciplina"), disciplina)
        and _bate_igual(item.get("ano_escolar"), ano_escolar)
        and _bate_igual(item.get("faixa_etaria"), faixa_etaria)
        and _bate_igual(item.get("id_caracteristica_alvo"), id_caracteristica_alvo)
        and _bate_igual(item.get("operacao_cognitiva"), operacao_cognitiva)
        and _bate_igual(item.get("porte_texto"), porte_texto)
    ]

    itens = [{**item, **classificar_elos(item)} for item in itens]
    run_info = {k: v for k, v in rodada.items() if k != "itens"}
    comparacao = comparar_com_linha_de_base(rodada, rodada_base) if rodada_base else None
    return {
        "tem_rodada": True,
        "run_info": run_info,
        "linha_de_base": comparacao,
        "portao": avaliar_portao(rodada, comparacao),
        "metricas_por_construcao": METRICAS_POR_CONSTRUCAO,
        "rnf07": resumir_rnf07(itens, rodada.get("nivel")),
        "modelos": resumir_modelos(itens),
        "elos": resumir_elos(itens),
        "resumo_geral": _resumir_grupo_itens(itens, com_ic=True),
        "por_faixa_etaria": _agrupar_por_dimensao(itens, "faixa_etaria"),
        "por_ano_escolar": _agrupar_por_dimensao(itens, "ano_escolar"),
        "por_disciplina": _agrupar_por_dimensao(itens, "disciplina"),
        "por_caracteristica": _agrupar_por_dimensao(itens, "id_caracteristica_alvo"),
        "por_operacao_cognitiva": _agrupar_por_dimensao(itens, "operacao_cognitiva"),
        "por_porte_texto": _agrupar_por_dimensao(itens, "porte_texto"),
        "itens": itens,
        "runs_disponiveis": runs_disponiveis or [],
    }


def obter_analytics_rag_escolar(
    *,
    run_id: str | None = None,
    disciplina: str | None = None,
    ano_escolar: str | None = None,
    faixa_etaria: str | None = None,
    id_caracteristica_alvo: str | None = None,
    operacao_cognitiva: str | None = None,
    porte_texto: str | None = None,
    caminho_runs: str | Path | None = None,
    caminho_base: str | Path | None = None,
) -> dict[str, Any]:
    """Carrega a rodada solicitada (ou a mais recente) e retorna o analytics segmentado."""
    rodadas = carregar_rodadas_rag_escolar(caminho_runs)
    reg_base = carregar_linha_de_base(caminho_base)
    id_base = reg_base["run_id"] if reg_base else None
    rodada_base = next((r for r in rodadas if r.get("run_id") == id_base), None) if id_base else None
    runs_meta = [
        {
            "run_id": r.get("run_id"),
            "commit": (r.get("procedencia") or {}).get("commit"),
            "eh_linha_de_base": bool(id_base) and r.get("run_id") == id_base,
            "timestamp_utc": r.get("timestamp_utc"),
            "metodo_efetivo": r.get("metodo_efetivo"),
            "estrategia_query": r.get("estrategia_query"),
            "nivel": r.get("nivel"),
            "gerar_resposta": r.get("gerar_resposta"),
            "avaliador_geracao": r.get("avaliador_geracao", "auto"),
            "avaliador_efetivo": r.get("avaliador_efetivo"),
            "total_itens": len(r.get("itens", [])),
        }
        for r in reversed(rodadas)
    ]
    alvo = None
    if rodadas:
        if run_id:
            alvo = next((r for r in reversed(rodadas) if r.get("run_id") == run_id), None)
        else:
            alvo = rodadas[-1]

    return resumir_analytics_rag_escolar(
        alvo,
        disciplina=disciplina,
        ano_escolar=ano_escolar,
        faixa_etaria=faixa_etaria,
        id_caracteristica_alvo=id_caracteristica_alvo,
        operacao_cognitiva=operacao_cognitiva,
        porte_texto=porte_texto,
        runs_disponiveis=runs_meta,
        rodada_base=rodada_base,
    )


def executar_benchmark_rag_escolar(
    *,
    metodo: str | None = None,
    nivel: int = 2,
    k: int = 5,
    estrategia_query: str = "contexto_pedagogico",
    gerar_resposta: bool = False,
    avaliador_geracao: str = "auto",
    disciplina: str | None = None,
    ano_escolar: str | None = None,
    faixa_etaria: str | None = None,
    id_caracteristica_alvo: str | None = None,
    operacao_cognitiva: str | None = None,
    porte_texto: str | None = None,
    apenas_oficiais: bool = False,
    limite: int | None = None,
    caminho_dataset: str | Path | None = None,
    caminho_runs: str | Path | None = None,
    caminho_base: str | Path | None = None,
    salvar: bool = True,
    progresso: Callable[[str], None] | None = None,
    on_step: Callable[[dict[str, Any]], None] | None = None,
    registrar_log: bool = True,
) -> dict[str, Any]:
    """Executa o benchmark do RAG sobre as questões escolares filtradas e salva a rodada."""
    t0 = time.perf_counter()
    todas = carregar_questoes_curadas(caminho_dataset)
    filtradas_dicts = filtrar_questoes_escolares(
        todas,
        disciplina=disciplina,
        ano_escolar=ano_escolar,
        faixa_etaria=faixa_etaria,
        id_caracteristica_alvo=id_caracteristica_alvo,
        operacao_cognitiva=operacao_cognitiva,
        porte_texto=porte_texto,
        apenas_oficiais=apenas_oficiais,
    )
    ids_selecionados = {d["id"] for d in (filtradas_dicts[:limite] if limite else filtradas_dicts)}
    itens_exec = [q for q in todas if q.id in ids_selecionados]
    if not itens_exec:
        # Uma rodada sem questões gravaria todas as métricas em zero, como se fosse um resultado.
        raise ValueError(
            "Nenhuma questão corresponde aos filtros escolhidos: a rodada não foi executada nem gravada."
        )

    def _emitir_log(linha: str) -> None:
        ts_local = datetime.now().strftime("%H:%M:%S")
        msg_fmt = f"[{ts_local}] {linha}"
        if progresso:
            progresso(msg_fmt)
        else:
            print(msg_fmt, flush=True)
        if not registrar_log:
            return  # repetição de conferência: não escreve no registro de progresso da bateria
        try:
            PROGRESSO_RAG_ESCOLAR_LOG.parent.mkdir(parents=True, exist_ok=True)
            with PROGRESSO_RAG_ESCOLAR_LOG.open("a", encoding="utf-8") as fh:
                fh.write(msg_fmt + "\n")
        except OSError:
            pass

    if salvar:
        try:
            PROGRESSO_RAG_ESCOLAR_LOG.parent.mkdir(parents=True, exist_ok=True)
            PROGRESSO_RAG_ESCOLAR_LOG.write_text("", encoding="utf-8")
        except OSError:
            pass

    total_itens = len(itens_exec)
    _emitir_log(
        f"Iniciando bateria escolar: {total_itens} questão(ões) | método={metodo or 'bm25'} "
        f"| gerar={gerar_resposta} | avaliador={avaliador_geracao}"
    )

    chunks_map = {c["chunk_id"]: c for c in rag_bridge.obter_trechos_base()}
    registros: list[dict[str, Any]] = []
    metodo_efetivo_final = metodo or "bm25"
    fallback_aplicado_any = False
    fallback_motivo_final: str | None = None
    avaliador_efetivo_final: str | None = None
    juiz_sonnet_erro_final: str | None = None

    for idx, item in enumerate(itens_exec, start=1):
        _emitir_log(f"[{idx}/{total_itens}] Processando {item.id} ({item.disciplina} / {item.ano_escolar})...")
        if on_step:
            on_step(
                {
                    "running": True,
                    "atual": idx - 1,
                    "total": total_itens,
                    "questao_atual": item.id,
                    "etapa": "Executando busca + LLM + juiz..." if gerar_resposta else "Executando busca no RAG...",
                    "mensagem": f"[{idx}/{total_itens}] Processando {item.id} ({item.disciplina} / {item.ano_escolar})...",
                }
            )
        av = avaliar_questao_no_rag(
            item,
            nivel=nivel,
            metodo=metodo,
            k=k,
            estrategia_query=estrategia_query,
            gerar_resposta=gerar_resposta,
            avaliador_geracao=avaliador_geracao,
            chunks_map=chunks_map,
        )
        metodo_efetivo_final = av["metodo_efetivo"]
        fallback_aplicado_any = fallback_aplicado_any or av["fallback_aplicado"]
        if not fallback_motivo_final and av.get("fallback_motivo"):
            fallback_motivo_final = av["fallback_motivo"]
        m_item = av["metricas"]
        if gerar_resposta:
            av_fid = m_item.get("avaliador_fidelidade")
            if av_fid == "claude_sonnet" or avaliador_efetivo_final is None:
                avaliador_efetivo_final = av_fid
            if not juiz_sonnet_erro_final and m_item.get("juiz_sonnet_erro"):
                juiz_sonnet_erro_final = m_item.get("juiz_sonnet_erro")
        registros.append(_compactar_registro_item(av))

        resumo_item = (
            f"[{idx}/{total_itens}] Concluído {item.id} | método={av['metodo_efetivo']} "
            f"| score_top1={m_item.get('score_top1', 0):.3f} | {m_item.get('segundos_total', 0):.1f}s"
        )
        if gerar_resposta:
            fid_val = m_item.get("fidelidade_efetiva")
            fid_str = f"{float(fid_val):.2f}" if fid_val is not None else "-"
            resumo_item += (
                f" | avaliador={m_item.get('avaliador_fidelidade')} | fidelidade={fid_str}"
            )
        _emitir_log(resumo_item)
        if on_step:
            on_step(
                {
                    "running": True,
                    "atual": idx,
                    "total": total_itens,
                    "questao_atual": item.id,
                    "etapa": "Concluída questão",
                    "mensagem": resumo_item,
                    "resumo_parcial": _resumir_grupo_itens(registros),
                }
            )

    rodada = {
        "run_id": f"rag-esc-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "metodo_solicitado": metodo or metodo_efetivo_final,
        "metodo_efetivo": metodo_efetivo_final,
        "fallback_aplicado": fallback_aplicado_any,
        "fallback_motivo": fallback_motivo_final,
        "estrategia_query": estrategia_query,
        "nivel": nivel,
        "k": k,
        "gerar_resposta": gerar_resposta,
        "avaliador_geracao": avaliador_geracao,
        "avaliador_efetivo": avaliador_efetivo_final,
        "juiz_sonnet_erro": juiz_sonnet_erro_final,
        "duracao_total_s": round(time.perf_counter() - t0, 3),
        "procedencia": obter_procedencia_rodada(caminho_dataset),
        "filtros_execucao": {
            "disciplina": disciplina,
            "ano_escolar": ano_escolar,
            "faixa_etaria": faixa_etaria,
            "id_caracteristica_alvo": id_caracteristica_alvo,
            "operacao_cognitiva": operacao_cognitiva,
            "porte_texto": porte_texto,
            "apenas_oficiais": apenas_oficiais,
            "limite": limite,
        },
        "itens": registros,
    }

    if salvar:
        destino = Path(caminho_runs) if caminho_runs else RUNS_RAG_ESCOLAR_PADRAO
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rodada, ensure_ascii=False) + "\n")

    if salvar:
        return obter_analytics_rag_escolar(
            run_id=rodada["run_id"], caminho_runs=caminho_runs, caminho_base=caminho_base
        )
    return resumir_analytics_rag_escolar(rodada)


CAMPOS_FILTRO_RODADA = (
    "disciplina",
    "ano_escolar",
    "faixa_etaria",
    "id_caracteristica_alvo",
    "operacao_cognitiva",
    "porte_texto",
    "apenas_oficiais",
    "limite",
)
MAX_DIVERGENTES_LISTADOS = 20


def repetir_rodada_rag_escolar(
    run_id: str | None = None,
    *,
    caminho_runs: str | Path | None = None,
    caminho_dataset: str | Path | None = None,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Roda de novo uma rodada registrada, com a mesma configuração, e conta em quantas questões deu igual.

    A repetição não é gravada. Compara, questão a questão: os trechos devolvidos (mesmos ids na mesma ordem),
    o texto da resposta e a decisão de se abster. Latência fica de fora, porque varia com a máquina.
    Com gerador que sorteia (modelo de linguagem), a resposta pode mudar sem que isso seja defeito; por isso
    a busca e a geração têm contagens separadas e a diferença de fidelidade vem com intervalo.
    """
    rodadas = carregar_rodadas_rag_escolar(caminho_runs)
    if not rodadas:
        raise ValueError("Nenhuma rodada registrada: não há o que repetir.")
    if run_id:
        ref = next((r for r in rodadas if r.get("run_id") == run_id), None)
        if ref is None:
            raise KeyError(f"Rodada não encontrada: {run_id}")
    else:
        ref = rodadas[-1]

    filtros = {c: (ref.get("filtros_execucao") or {}).get(c) for c in CAMPOS_FILTRO_RODADA}
    filtros["apenas_oficiais"] = bool(filtros.get("apenas_oficiais"))
    nova = executar_benchmark_rag_escolar(
        metodo=ref.get("metodo_solicitado") or ref.get("metodo_efetivo"),
        nivel=int(ref.get("nivel") or 2),
        k=int(ref.get("k") or 5),
        estrategia_query=ref.get("estrategia_query") or "contexto_pedagogico",
        gerar_resposta=bool(ref.get("gerar_resposta")),
        avaliador_geracao=ref.get("avaliador_geracao") or "auto",
        caminho_dataset=caminho_dataset,
        salvar=False,
        registrar_log=False,
        progresso=lambda _msg: None,
        on_step=on_step,
        **filtros,
    )

    antes = {r["id"]: r for r in ref.get("itens", [])}
    depois = {r["id"]: r for r in nova.get("itens", [])}
    comuns = [qid for qid in antes if qid in depois]
    com_geracao = bool(ref.get("gerar_resposta"))

    trechos_iguais = respostas_iguais = abstencao_igual = 0
    diferencas_fid: list[float] = []
    divergentes: list[dict[str, Any]] = []
    for qid in comuns:
        a, d = antes[qid], depois[qid]
        mesmo_trecho = list(a.get("chunk_ids") or []) == list(d.get("chunk_ids") or [])
        mesma_resposta = (a.get("resposta") or "") == (d.get("resposta") or "")
        mesma_abstencao = bool(a.get("absteve")) == bool(d.get("absteve"))
        trechos_iguais += mesmo_trecho
        respostas_iguais += mesma_resposta
        abstencao_igual += mesma_abstencao
        fa, fd = a.get("fidelidade_efetiva"), d.get("fidelidade_efetiva")
        if fa is not None and fd is not None:
            diferencas_fid.append(float(fd) - float(fa))
        mudou = [
            nome
            for nome, igual in (("trechos", mesmo_trecho), ("resposta", mesma_resposta), ("abstenção", mesma_abstencao))
            if not igual and (com_geracao or nome == "trechos")
        ]
        if mudou and len(divergentes) < MAX_DIVERGENTES_LISTADOS:
            divergentes.append({"id": qid, "mudou": mudou})

    proc_ref = ref.get("procedencia") or {}
    proc_agora = (nova.get("run_info") or {}).get("procedencia") or {}
    n = len(comuns)
    mesmas_questoes = set(antes) == set(depois)
    busca_repete = mesmas_questoes and trechos_iguais == n
    geracao_repete = (respostas_iguais == n and abstencao_igual == n) if com_geracao else None
    return {
        "run_id_referencia": ref.get("run_id"),
        "total_referencia": len(antes),
        "total_repeticao": len(depois),
        "comparadas": n,
        "mesmas_questoes": mesmas_questoes,
        "com_geracao": com_geracao,
        "trechos_identicos": trechos_iguais,
        "respostas_identicas": respostas_iguais if com_geracao else None,
        "abstencao_igual": abstencao_igual if com_geracao else None,
        "busca_repete": busca_repete,
        "geracao_repete": geracao_repete,
        "repete": bool(busca_repete and geracao_repete is not False),
        "diferenca_fidelidade": (
            {
                "n": len(diferencas_fid),
                "media": round(sum(diferencas_fid) / len(diferencas_fid), 4),
                "ic95": intervalo_confianca_media(diferencas_fid),
            }
            if diferencas_fid
            else None
        ),
        "divergentes": divergentes,
        "divergentes_total": sum(
            1
            for qid in comuns
            if list(antes[qid].get("chunk_ids") or []) != list(depois[qid].get("chunk_ids") or [])
            or (com_geracao and (antes[qid].get("resposta") or "") != (depois[qid].get("resposta") or ""))
        ),
        "procedencia_referencia": proc_ref,
        "procedencia_agora": proc_agora,
        "mesma_prova": bool(proc_ref) and proc_ref.get("dataset_sha256") == proc_agora.get("dataset_sha256"),
        "mesma_base": bool(proc_ref) and proc_ref.get("base_trechos_sha256") == proc_agora.get("base_trechos_sha256"),
        "mesmo_commit": bool(proc_ref)
        and proc_ref.get("commit") == proc_agora.get("commit")
        and not proc_ref.get("commit_com_alteracoes_locais")
        and not proc_agora.get("commit_com_alteracoes_locais"),
        "duracao_s": (nova.get("run_info") or {}).get("duracao_total_s"),
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--curar", action="store_true", help="Gera a camada curada questoes_escolares_curado_v1.json")
    ap.add_argument("--executar", action="store_true", help="Executa o benchmark do RAG sobre as questões escolares")
    ap.add_argument("--analytics", action="store_true", help="Exibe o analytics da última rodada registrada")
    ap.add_argument("--metodo", default="bm25", help="Método de busca no RAG (bm25, qwen3+rerank50, hibrido)")
    ap.add_argument("--estrategia", default="contexto_pedagogico", choices=ESTRATEGIAS_QUERY)
    ap.add_argument("--nivel", type=int, default=2, choices=[1, 2, 3])
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--gerar", action="store_true", help="Também executa a etapa de geração e mede fidelidade")
    ap.add_argument("--disciplina", default=None)
    ap.add_argument("--faixa-etaria", default=None)
    ap.add_argument("--limite", type=int, default=None)
    args = ap.parse_args(argv)

    if args.curar:
        resumo_cur = curar_dataset_escolar(salvar=True)
        print(json.dumps(resumo_cur, ensure_ascii=False, indent=2))

    if args.executar:
        res_run = executar_benchmark_rag_escolar(
            metodo=args.metodo,
            nivel=args.nivel,
            k=args.k,
            estrategia_query=args.estrategia,
            gerar_resposta=args.gerar,
            disciplina=args.disciplina,
            faixa_etaria=args.faixa_etaria,
            limite=args.limite,
            progresso=print,
        )
        print(json.dumps({k: v for k, v in res_run.items() if k != "itens"}, ensure_ascii=False, indent=2))
    elif args.analytics or not args.curar:
        res_an = obter_analytics_rag_escolar(
            disciplina=args.disciplina,
            faixa_etaria=args.faixa_etaria,
        )
        print(json.dumps({k: v for k, v in res_an.items() if k != "itens"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
