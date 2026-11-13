"""Ponto de entrada Backend (FastAPI / HTTP) e Frontend Web da plataforma Íris.

Rotas disponíveis:
- `GET  /`                    -> Playground RAG & Auditoria (Métricas, Catálogo #39, Consulta Ao Vivo e Ferramentas)
- `GET  /api/v1/health`       -> Status operacional, conectividade LLM/pgvector e trava Zero-Database
- `GET  /api/v1/catalog`      -> Catálogo modular de características funcionais do TDAH (#39)
- `GET  /api/v1/eval/metrics` -> Cálculo das 12 métricas do RAG + consultas com textos e vereditos completos
- `POST /api/v1/rag/build`    -> Verifica / recria a base de chunks do RAG a partir dos documentos
- `POST /api/v1/rag/search`   -> Busca de evidências científicas filtrada por característica/barreira
- `POST /api/v1/rag/answer`   -> Geração de resposta fundamentada ao vivo (Ollama / Groq / Extractive) + textos + telemetria
"""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from iris import __version__
from iris.config import RAG_PACOTE_DIR, get_settings

PLAYGROUND_HTML_PATH = Path(__file__).resolve().parent / "static" / "playground.html"

# O gerador do pacote RAG (gerar.py) lê RAG_LLM e RAG_LLM_MODELO do ambiente do processo no momento da
# geração. A rota de resposta ao vivo ajusta essas variáveis por requisição; a trava impede que duas
# requisições simultâneas troquem o provedor uma da outra ou restaurem um valor alheio.
_RAG_LLM_LOCK = threading.Lock()


def _load_playground_html() -> str:
    """Lê o template estático do Playground RAG servido na rota raiz `/`."""
    return PLAYGROUND_HTML_PATH.read_text(encoding="utf-8")


def _is_pgvector_online(dsn: str) -> bool:
    """Verifica rapidamente via TCP se o PostgreSQL/pgvector está acessível sem bloquear o healthcheck."""
    try:
        parsed = urlparse(dsn)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5432
        with socket.create_connection((host, port), timeout=0.15):
            return True
    except OSError:
        return False


def _count_local_chunks() -> int:
    """Conta os trechos atualmente indexados em `chunks.jsonl` sem carregar todo o índice BM25."""
    chunks_path = RAG_PACOTE_DIR / "chunks.jsonl"
    if not chunks_path.exists():
        return 0
    try:
        with chunks_path.open("r", encoding="utf-8") as fh:
            return sum(1 for ln in fh if ln.strip())
    except OSError:
        return 0


def _resolve_active_model(client: Any, fallback_model: str) -> str:
    """Resolve o modelo efetivamente disponível no provedor ativo (ex.: `llama3:latest`)."""
    primary = getattr(client, "_primary", None)
    resolve_fn = getattr(primary, "_resolve_model", None)
    if callable(resolve_fn):
        try:
            resolved = resolve_fn()
            if resolved:
                return str(resolved)
        except Exception:
            pass
    return str(getattr(primary, "model", None) or fallback_model)


def _check_dense_rag_dependencies() -> tuple[bool, list[str]]:
    """Verifica rapidamente se os pacotes do grupo `rag` (`torch`, `sentence_transformers`, `psycopg`, `pgvector`) estão instalados."""
    import importlib.util

    faltando = [
        pkg
        for pkg in ("torch", "sentence_transformers", "psycopg", "pgvector")
        if importlib.util.find_spec(pkg) is None
    ]
    return len(faltando) == 0, faltando


def get_health_status() -> dict[str, Any]:
    """Retorna o status operacional e guardrails arquiteturais do serviço."""
    settings = get_settings()
    active_model = settings.llm_model
    try:
        from iris.core.llm_client import get_llm_client

        client = get_llm_client()
        llm_info = client.status()
        if llm_info.get("primary_available"):
            active_model = _resolve_active_model(client, settings.llm_model)
    except Exception:
        llm_info = {"ollama_online": False}

    vector_online = _is_pgvector_online(settings.rag_pg_dsn) if settings.rag_banco == "pgvector" else False
    vector_deps_ready, vector_deps_missing = _check_dense_rag_dependencies()
    available_methods = (
        ["bm25", "qwen3+rerank50", "hibrido"] if (vector_online and vector_deps_ready) else ["bm25"]
    )
    sonnet_ready = bool((settings.anthropic_api_key or "").strip())

    return {
        "status": "ok",
        "service": "iris-pedagogical-adapter",
        "version": __version__,
        "environment": settings.env,
        "zero_student_database": settings.zero_student_database,
        "llm_provider": settings.llm_provider,
        "llm_model": active_model,
        "ollama_online": llm_info.get("ollama_online", False),
        "ollama_models": llm_info.get("ollama_installed_models", []),
        "rag_backend": settings.rag_banco,
        "vector_db_online": vector_online,
        "vector_deps_ready": vector_deps_ready,
        "vector_deps_missing": vector_deps_missing,
        "available_search_methods": available_methods,
        "sonnet_judge_ready": sonnet_ready,
        "sonnet_judge_model": settings.judge_model,
        "total_chunks": _count_local_chunks(),
    }


FRONTEND_HTML = _load_playground_html()


def _handle_catalog() -> dict[str, Any]:
    from iris.config import CATALOGS_DIR
    from iris.schemas.catalog import load_catalog_file

    return load_catalog_file(CATALOGS_DIR / "tdah_caracteristicas_funcionais.json").to_dict()


def _handle_rag_build() -> dict[str, Any]:
    from iris.rag.bridge import garantir_chunks_locais, listar_barreiras_rag, obter_trechos_base

    caminho = garantir_chunks_locais(verbose=False)
    chunks = obter_trechos_base()
    return {
        "status": "ok",
        "chunks_path": str(caminho),
        "total_chunks": len(chunks),
        "barreiras": listar_barreiras_rag(),
    }


def _handle_rag_search(body: dict[str, Any]) -> dict[str, Any]:
    from iris.rag.bridge import (
        buscar_evidencias_com_meta,
        buscar_por_caracteristica_atomica,
        normalizar_trecho_ui,
        obter_trechos_base,
    )

    id_carac = body.get("id_caracteristica")
    nivel = int(body.get("nivel", 2))
    pergunta = body.get("pergunta", "")
    metodo = body.get("metodo") or "bm25"
    k = int(body.get("k", 5))
    chunks_map = {c["chunk_id"]: c for c in obter_trechos_base()}

    if id_carac:
        res = buscar_por_caracteristica_atomica(
            id_caracteristica=id_carac,
            nivel=nivel,
            pergunta_adicional=pergunta,
            metodo=metodo,
            k=k,
        )
        res["trechos_recuperados"] = [
            normalizar_trecho_ui(
                t,
                ref=f"T{idx}",
                chunk_meta=chunks_map.get(t.get("chunk_id", ""), {}),
                status_gabarito="Filtrado por Barreira",
            )
            for idx, t in enumerate(res.get("trechos_rag", []), start=1)
        ]
        return res

    busca = buscar_evidencias_com_meta(pergunta=pergunta, metodo=metodo, k=k)
    trechos = busca["trechos"]
    return {
        "pergunta": pergunta,
        "metodo_solicitado": busca["metodo_solicitado"],
        "metodo_efetivo": busca["metodo_efetivo"],
        "fallback_aplicado": busca["fallback_aplicado"],
        "trechos_rag": trechos,
        "trechos_recuperados": [
            normalizar_trecho_ui(
                t,
                ref=f"T{idx}",
                chunk_meta=chunks_map.get(t.get("chunk_id", ""), {}),
                status_gabarito=f"Score: {t.get('score', 0):.3f}",
            )
            for idx, t in enumerate(trechos, start=1)
        ],
    }


def _handle_rag_answer(body: dict[str, Any]) -> dict[str, Any]:
    from iris.core.llm_client import get_llm_client
    from iris.eval.rag_metrics import calcular_similaridade_semantica, verificar_sustentacao_frase_no_trecho
    from iris.rag.bridge import (
        buscar_evidencias,
        normalizar_trecho_ui,
        obter_trechos_base,
        responder_fundamentado,
    )

    pergunta = body.get("pergunta", "")
    metodo_solicitado = body.get("metodo") or "bm25"
    k = int(body.get("k", 5))
    client = get_llm_client(allow_fallback_to_extractive=True)
    status_llm = client.status()
    modelo_resolvido = (
        _resolve_active_model(client, get_settings().llm_model)
        if status_llm["primary_available"]
        else "deterministic-bm25-extractive"
    )

    llm_fallback_aplicado = False
    llm_erro: str | None = None
    with _RAG_LLM_LOCK:
        old_rag_llm = os.environ.get("RAG_LLM")
        old_rag_modelo = os.environ.get("RAG_LLM_MODELO")
        try:
            if status_llm["primary_available"]:
                os.environ["RAG_LLM"] = status_llm["configured_provider"]
                os.environ["RAG_LLM_MODELO"] = modelo_resolvido
                try:
                    res = responder_fundamentado(pergunta=pergunta, metodo=metodo_solicitado, k=k)
                except Exception as exc:
                    llm_fallback_aplicado = True
                    llm_erro = str(exc)
                    os.environ["RAG_LLM"] = "extractive"
                    os.environ["RAG_LLM_MODELO"] = "deterministic-bm25-extractive"
                    res = responder_fundamentado(pergunta=pergunta, metodo=metodo_solicitado, k=k)
            else:
                llm_fallback_aplicado = status_llm["configured_provider"] != "extractive"
                os.environ["RAG_LLM"] = "extractive"
                os.environ["RAG_LLM_MODELO"] = "deterministic-bm25-extractive"
                res = responder_fundamentado(pergunta=pergunta, metodo=metodo_solicitado, k=k)
        finally:
            if old_rag_llm is None:
                os.environ.pop("RAG_LLM", None)
            else:
                os.environ["RAG_LLM"] = old_rag_llm
            if old_rag_modelo is None:
                os.environ.pop("RAG_LLM_MODELO", None)
            else:
                os.environ["RAG_LLM_MODELO"] = old_rag_modelo

    metodo_efetivo = res.get("metodo", metodo_solicitado)
    trechos = res.get("trechos_entregues") or buscar_evidencias(pergunta=pergunta, metodo=metodo_efetivo, k=k)
    resposta_texto = res.get("resposta", "")

    # Calcula a fidelidade lexical frase a frase em tempo real
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", resposta_texto.strip()) if len(f.split()) >= 4]
    pontos = 0.0
    for f in frases:
        nums = [int(n) for n in re.findall(r"\[T(\d+)\]", f) if 1 <= int(n) <= len(trechos)]
        textos_cit = [trechos[n - 1].get("trecho", "") for n in nums]
        ver = verificar_sustentacao_frase_no_trecho(f, textos_cit)
        if ver == "apoiada":
            pontos += 1.0
        elif ver == "parcial":
            pontos += 0.5
    fidelidade = round(pontos / max(len(frases), 1), 3) if frases else 1.0
    relevancia = round(min(1.0, calcular_similaridade_semantica(pergunta, resposta_texto) * 1.8), 3)

    from iris.eval.sonnet_judge import julgar_resposta_sonnet, sonnet_judge_status

    avaliador_solicitado = str(body.get("avaliador_geracao") or "auto").strip().lower()
    sonnet_ready = sonnet_judge_status()["ready"]
    usar_sonnet = avaliador_solicitado == "sonnet" or (avaliador_solicitado == "auto" and sonnet_ready)
    juiz_sonnet_detalhe: dict[str, Any] | None = None
    juiz_sonnet_erro: str | None = None
    fidelidade_sonnet: float | None = None
    relevancia_sonnet: float | None = None
    avaliador_fidelidade = "lexico_local"

    if usar_sonnet:
        try:
            ver_sonnet = julgar_resposta_sonnet(
                pergunta=pergunta,
                trechos=trechos,
                resposta=resposta_texto,
            )
            juiz_sonnet_detalhe = ver_sonnet
            fidelidade_sonnet = ver_sonnet["fidelidade_sonnet"]
            relevancia_sonnet = ver_sonnet["relevancia_sonnet"]
            avaliador_fidelidade = "claude_sonnet"
        except Exception as exc:  # noqa: BLE001
            juiz_sonnet_erro = str(exc)

    fid_exibicao = fidelidade_sonnet if fidelidade_sonnet is not None else fidelidade
    rel_exibicao = relevancia_sonnet if relevancia_sonnet is not None else relevancia
    rotulo_juiz = "Sonnet v2" if avaliador_fidelidade == "claude_sonnet" else "Léxico"

    conf = res.get("conferencia", {})
    citacoes_inv = len(conf.get("citacoes_invalidas", []))
    frases_sem_cit = len(conf.get("frases_sem_citacao", []))

    res["juiz_sonnet"] = juiz_sonnet_detalhe
    res["fidelidade_frase"] = (
        f"{fid_exibicao:.2f} ({rotulo_juiz} | Relevância: {rel_exibicao:.2f} | LLM: {res.get('llm')})"
    )
    res["telemetria_consulta"] = {
        "metodo_solicitado": metodo_solicitado,
        "metodo_efetivo": metodo_efetivo,
        "fallback_aplicado": metodo_efetivo != metodo_solicitado,
        "llm": res.get("llm"),
        "llm_fallback_aplicado": llm_fallback_aplicado,
        "llm_erro": llm_erro,
        "segundos_busca": res.get("segundos_busca", 0),
        "segundos_total": res.get("segundos_total", 0),
        "avaliador_fidelidade": avaliador_fidelidade,
        "fidelidade_efetiva": fid_exibicao,
        "relevancia_efetiva": rel_exibicao,
        "fidelidade_sonnet": fidelidade_sonnet,
        "relevancia_sonnet": relevancia_sonnet,
        "juiz_sonnet_erro": juiz_sonnet_erro,
        "fidelidade_lexica": fidelidade,
        "relevancia_lexica": relevancia,
        "citacoes_invalidas": citacoes_inv,
        "frases_sem_citacao": frases_sem_cit,
        "absteve": bool(conf.get("absteve", False)),
        "citou_trecho_com_aviso": conf.get("citou_trecho_com_aviso", []),
    }

    chunks_map = {c["chunk_id"]: c for c in obter_trechos_base()}
    res["trechos_recuperados"] = [
        normalizar_trecho_ui(
            t,
            ref=f"T{idx}",
            chunk_meta=chunks_map.get(t.get("chunk_id", ""), {}),
            status_gabarito=f"Score: {t.get('score', 0):.3f}",
        )
        for idx, t in enumerate(trechos, start=1)
    ]
    return res


def _handle_eval_metrics(
    gerador: str = "haiku",
    limite: int = 7,
    tipo: str | None = None,
    barreira: str | None = None,
) -> dict[str, Any]:
    from iris.eval.rag_metrics import (
        avaliar_pipeline_registrado,
        obter_consultas_com_textos_e_metricas,
        obter_opcoes_filtro_gabarito,
    )

    dados = avaliar_pipeline_registrado(gerador=gerador)
    dados["consultas_com_textos"] = obter_consultas_com_textos_e_metricas(
        gerador=gerador,
        limite=limite,
        tipo=tipo,
        barreira=barreira,
    )
    dados["filtros_gabarito"] = obter_opcoes_filtro_gabarito()

    outro_gerador = "opus" if gerador == "haiku" else "haiku"
    dados_outro = avaliar_pipeline_registrado(gerador=outro_gerador)
    dados["comparativo_geradores"] = {
        gerador: {
            "iris": dados["metricas_relatorio_iris"],
            "notas_0_a_10": dados["notas_0_a_10"],
        },
        outro_gerador: {
            "iris": dados_outro["metricas_relatorio_iris"],
            "notas_0_a_10": dados_outro["notas_0_a_10"],
        },
    }
    return dados


def _handle_extractor_analytics(
    disciplina: str | None = None,
    faixa_etaria: str | None = None,
    ano_escolar: str | None = None,
    tema: str | None = None,
    comando_conjugado: bool | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    from iris.eval.extractor_analytics import carregar_telemetria, gerar_analytics

    registros = carregar_telemetria()
    return gerar_analytics(
        registros,
        disciplina=disciplina,
        faixa_etaria=faixa_etaria,
        ano_escolar=ano_escolar,
        tema=tema,
        comando_conjugado=comando_conjugado,
        provider=provider,
        model=model,
    )


def _handle_benchmark_escolar_list(
    disciplina: str | None = None,
    ano_escolar: str | None = None,
    faixa_etaria: str | None = None,
    id_caracteristica_alvo: str | None = None,
    operacao_cognitiva: str | None = None,
    porte_texto: str | None = None,
    apenas_oficiais: bool = False,
    q: str | None = None,
    limite: int = 0,
) -> dict[str, Any]:
    from iris.eval.rag_escolar_benchmark import listar_questoes_escolares

    return listar_questoes_escolares(
        disciplina=disciplina,
        ano_escolar=ano_escolar,
        faixa_etaria=faixa_etaria,
        id_caracteristica_alvo=id_caracteristica_alvo,
        operacao_cognitiva=operacao_cognitiva,
        porte_texto=porte_texto,
        apenas_oficiais=apenas_oficiais,
        q=q,
        limite=limite,
    )


def _handle_benchmark_escolar_curar() -> dict[str, Any]:
    from iris.eval.rag_escolar_benchmark import curar_dataset_escolar

    return curar_dataset_escolar(salvar=True)


def _handle_rag_test_question(body: dict[str, Any]) -> dict[str, Any]:
    from iris.eval.rag_escolar_benchmark import avaliar_questao_no_rag, buscar_questao_curada_por_id

    question_id = str(body.get("question_id") or "").strip()
    if not question_id:
        raise ValueError("Informe 'question_id' para testar uma questão escolar no RAG.")
    item = buscar_questao_curada_por_id(question_id)
    return avaliar_questao_no_rag(
        item,
        nivel=int(body.get("nivel", 2)),
        metodo=body.get("metodo") or "bm25",
        k=int(body.get("k", 5)),
        estrategia_query=str(body.get("estrategia_query") or "contexto_pedagogico"),
        gerar_resposta=bool(body.get("gerar_resposta", False)),
        avaliador_geracao=str(body.get("avaliador_geracao") or "auto"),
    )


_RAG_ESCOLAR_LOCK = threading.Lock()
_RAG_ESCOLAR_PROGRESSO: dict[str, Any] = {
    "running": False,
    "atual": 0,
    "total": 0,
    "questao_atual": None,
    "etapa": "idle",
    "inicio_utc": None,
    "inicio_monotonic": None,
    "log_linhas": [],
    "resumo_parcial": None,
}


def _handle_rag_escolar_progress() -> dict[str, Any]:
    """Retorna o estado atual de execução do benchmark RAG escolar para polling na UI."""
    with _RAG_ESCOLAR_LOCK:
        inicio_mono = _RAG_ESCOLAR_PROGRESSO.get("inicio_monotonic")
        tempo_decorrido = round(time.monotonic() - inicio_mono, 1) if inicio_mono is not None else 0.0
        return {
            "running": bool(_RAG_ESCOLAR_PROGRESSO.get("running", False)),
            "atual": int(_RAG_ESCOLAR_PROGRESSO.get("atual", 0)),
            "total": int(_RAG_ESCOLAR_PROGRESSO.get("total", 0)),
            "questao_atual": _RAG_ESCOLAR_PROGRESSO.get("questao_atual"),
            "etapa": str(_RAG_ESCOLAR_PROGRESSO.get("etapa") or "idle"),
            "inicio_utc": _RAG_ESCOLAR_PROGRESSO.get("inicio_utc"),
            "tempo_decorrido_s": tempo_decorrido,
            "log_linhas": list(_RAG_ESCOLAR_PROGRESSO.get("log_linhas") or []),
            "resumo_parcial": _RAG_ESCOLAR_PROGRESSO.get("resumo_parcial"),
        }


def _handle_rag_escolar_run(body: dict[str, Any]) -> dict[str, Any]:
    from iris.eval.rag_escolar_benchmark import executar_benchmark_rag_escolar

    limite_raw = body.get("limite")
    limite = int(limite_raw) if limite_raw not in (None, "", 0, "0") else None

    with _RAG_ESCOLAR_LOCK:
        _RAG_ESCOLAR_PROGRESSO.update(
            {
                "running": True,
                "atual": 0,
                "total": 0,
                "questao_atual": None,
                "etapa": "iniciando",
                "inicio_utc": datetime.now(timezone.utc).isoformat(),
                "inicio_monotonic": time.monotonic(),
                "log_linhas": [],
                "resumo_parcial": None,
            }
        )

    def _on_log(msg: str) -> None:
        print(msg, flush=True)
        with _RAG_ESCOLAR_LOCK:
            linhas = _RAG_ESCOLAR_PROGRESSO["log_linhas"]
            linhas.append(msg)
            if len(linhas) > 50:
                del linhas[:-50]

    def _on_step(step: dict[str, Any]) -> None:
        with _RAG_ESCOLAR_LOCK:
            _RAG_ESCOLAR_PROGRESSO["atual"] = int(step.get("atual", 0))
            _RAG_ESCOLAR_PROGRESSO["total"] = int(step.get("total", 0))
            _RAG_ESCOLAR_PROGRESSO["questao_atual"] = step.get("questao_atual")
            _RAG_ESCOLAR_PROGRESSO["etapa"] = str(step.get("etapa") or "processando")
            if step.get("resumo_parcial") is not None:
                _RAG_ESCOLAR_PROGRESSO["resumo_parcial"] = step["resumo_parcial"]

    try:
        return executar_benchmark_rag_escolar(
            metodo=body.get("metodo") or "bm25",
            nivel=int(body.get("nivel", 2)),
            k=int(body.get("k", 5)),
            estrategia_query=str(body.get("estrategia_query") or "contexto_pedagogico"),
            gerar_resposta=bool(body.get("gerar_resposta", False)),
            avaliador_geracao=str(body.get("avaliador_geracao") or "auto"),
            disciplina=body.get("disciplina") or None,
            ano_escolar=body.get("ano_escolar") or None,
            faixa_etaria=body.get("faixa_etaria") or None,
            id_caracteristica_alvo=body.get("id_caracteristica_alvo") or None,
            operacao_cognitiva=body.get("operacao_cognitiva") or None,
            porte_texto=body.get("porte_texto") or None,
            apenas_oficiais=bool(body.get("apenas_oficiais", False)),
            limite=limite,
            salvar=True,
            progresso=_on_log,
            on_step=_on_step,
        )
    finally:
        with _RAG_ESCOLAR_LOCK:
            _RAG_ESCOLAR_PROGRESSO["running"] = False
            _RAG_ESCOLAR_PROGRESSO["etapa"] = "concluido"


def _handle_rag_escolar_analytics(
    run_id: str | None = None,
    disciplina: str | None = None,
    ano_escolar: str | None = None,
    faixa_etaria: str | None = None,
    id_caracteristica_alvo: str | None = None,
    operacao_cognitiva: str | None = None,
    porte_texto: str | None = None,
) -> dict[str, Any]:
    from iris.eval.rag_escolar_benchmark import obter_analytics_rag_escolar

    return obter_analytics_rag_escolar(
        run_id=run_id,
        disciplina=disciplina,
        ano_escolar=ano_escolar,
        faixa_etaria=faixa_etaria,
        id_caracteristica_alvo=id_caracteristica_alvo,
        operacao_cognitiva=operacao_cognitiva,
        porte_texto=porte_texto,
    )


def create_app() -> Any:
    """Cria e configura a aplicação FastAPI stateless (com rotas de API, Materiais e Frontend Web)."""
    from fastapi import Body, FastAPI, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse

    app = FastAPI(
        title="Íris — Adaptação Inteligente de Materiais Pedagógicos",
        description=(
            "Plataforma copiloto docente para adaptação cirúrgica de materiais didáticos "
            "baseada em evidências (DUA/MEC) e arquitetura Zero-Database (LGPD)."
        ),
        version=__version__,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=HTMLResponse, tags=["frontend"])
    def index_page() -> str:
        return _load_playground_html()

    @app.get("/api/v1/health", tags=["infra"])
    def health_check() -> dict[str, Any]:
        return get_health_status()

    # Registra rotas de materiais didáticos (História 1.1.1 - Issue #4)
    from iris.api.routes.materials import router as materials_router

    if materials_router is not None:
        app.include_router(materials_router, prefix="/api/v1")

    # Registra rotas de catálogo e seleção cirúrgica de características (História 1.2.1 - Issue #8)
    from iris.api.routes.catalogs import router as catalogs_router

    if catalogs_router is not None:
        app.include_router(catalogs_router, prefix="/api/v1")

    @app.get("/api/v1/catalog", tags=["catalogo"])
    def get_catalog() -> dict[str, Any]:
        return _handle_catalog()

    @app.post("/api/v1/rag/build", tags=["rag"])
    def rag_build() -> dict[str, Any]:
        return _handle_rag_build()

    @app.post("/api/v1/rag/search", tags=["rag"])
    def rag_search(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return _handle_rag_search(payload)

    @app.post("/api/v1/rag/answer", tags=["rag"])
    def rag_answer(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return _handle_rag_answer(payload)

    @app.get("/api/v1/eval/metrics", tags=["eval"])
    def eval_metrics(
        gerador: str = Query("haiku", pattern="^(haiku|opus)$"),
        limite: int = Query(7, ge=0, le=100),
        tipo: str | None = Query(None),
        barreira: str | None = Query(None),
    ) -> dict[str, Any]:
        return _handle_eval_metrics(gerador=gerador, limite=limite, tipo=tipo, barreira=barreira)

    @app.get("/api/v1/eval/extractor-analytics", tags=["eval"])
    def eval_extractor_analytics(
        disciplina: str | None = Query(None),
        faixa_etaria: str | None = Query(None),
        ano_escolar: str | None = Query(None),
        tema: str | None = Query(None),
        comando_conjugado: bool | None = Query(None),
        provider: str | None = Query(None),
        model: str | None = Query(None),
    ) -> dict[str, Any]:
        return _handle_extractor_analytics(
            disciplina=disciplina,
            faixa_etaria=faixa_etaria,
            ano_escolar=ano_escolar,
            tema=tema,
            comando_conjugado=comando_conjugado,
            provider=provider,
            model=model,
        )

    @app.get("/api/v1/benchmarks/escolar", tags=["eval"])
    def list_benchmark_escolar(
        disciplina: str | None = Query(None),
        ano_escolar: str | None = Query(None),
        faixa_etaria: str | None = Query(None),
        id_caracteristica_alvo: str | None = Query(None),
        operacao_cognitiva: str | None = Query(None),
        porte_texto: str | None = Query(None),
        apenas_oficiais: bool = Query(False),
        q: str | None = Query(None),
        limite: int = Query(0, ge=0, le=500),
    ) -> dict[str, Any]:
        return _handle_benchmark_escolar_list(
            disciplina=disciplina,
            ano_escolar=ano_escolar,
            faixa_etaria=faixa_etaria,
            id_caracteristica_alvo=id_caracteristica_alvo,
            operacao_cognitiva=operacao_cognitiva,
            porte_texto=porte_texto,
            apenas_oficiais=apenas_oficiais,
            q=q,
            limite=limite,
        )

    @app.post("/api/v1/benchmarks/escolar/curar", tags=["eval"])
    def curar_benchmark_escolar() -> dict[str, Any]:
        return _handle_benchmark_escolar_curar()

    @app.post("/api/v1/rag/test-question", tags=["rag"])
    def rag_test_question(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        from fastapi import HTTPException

        try:
            return _handle_rag_test_question(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/eval/rag-escolar/run", tags=["eval"])
    def run_rag_escolar(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        from fastapi import HTTPException

        try:
            return _handle_rag_escolar_run(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/eval/rag-escolar/progress", tags=["eval"])
    def progress_rag_escolar() -> dict[str, Any]:
        return _handle_rag_escolar_progress()

    @app.get("/api/v1/eval/rag-escolar/analytics", tags=["eval"])
    def analytics_rag_escolar(
        run_id: str | None = Query(None),
        disciplina: str | None = Query(None),
        ano_escolar: str | None = Query(None),
        faixa_etaria: str | None = Query(None),
        id_caracteristica_alvo: str | None = Query(None),
        operacao_cognitiva: str | None = Query(None),
        porte_texto: str | None = Query(None),
    ) -> dict[str, Any]:
        return _handle_rag_escolar_analytics(
            run_id=run_id,
            disciplina=disciplina,
            ano_escolar=ano_escolar,
            faixa_etaria=faixa_etaria,
            id_caracteristica_alvo=id_caracteristica_alvo,
            operacao_cognitiva=operacao_cognitiva,
            porte_texto=porte_texto,
        )

    return app


try:
    app = create_app()
except Exception:
    app = None  # type: ignore


def run_stdlib_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Servidor HTTP nativo de fallback caso `uvicorn`/`fastapi` não estejam ativos no Python atual."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    class IrisHandler(BaseHTTPRequestHandler):
        def _send_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")

        def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._send_cors_headers()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/" or parsed.path.startswith("/index"):
                raw = _load_playground_html().encode("utf-8")
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            elif parsed.path.startswith("/api/v1/health"):
                self._send_json(get_health_status())
            elif parsed.path == "/api/v1/catalogs/characteristics":
                from iris.api.routes.catalogs import get_characteristics_catalog_service
                from iris.schemas.catalog import (
                    CatalogValidationError,
                    CharacteristicSelectionError,
                )

                qs = parse_qs(parsed.query)
                id_catalogo = qs.get("id_catalogo", [None])[0]
                try:
                    self._send_json(get_characteristics_catalog_service(id_catalogo=id_catalogo))
                except CharacteristicSelectionError as err:
                    self._send_json({"detail": err.to_dict()}, status=404)
                except CatalogValidationError as err:
                    self._send_json(
                        {"detail": {"detail": str(err), "code": "CATALOG_SCHEMA_ERROR", "field": "catalog"}},
                        status=500,
                    )
                except Exception as err:  # noqa: BLE001
                    self._send_json(
                        {"detail": {"detail": f"Erro interno ao carregar catálogo: {err}", "code": "INTERNAL_ERROR"}},
                        status=500,
                    )
            elif parsed.path == "/api/v1/catalogs/characteristics/select":
                self._send_json({"detail": "Method Not Allowed"}, status=405)
            elif parsed.path.startswith("/api/v1/catalogs/"):
                self._send_json({"error": "Not found", "path": self.path}, status=404)
            elif parsed.path.startswith("/api/v1/catalog"):
                self._send_json(_handle_catalog())
            elif parsed.path.startswith("/api/v1/eval/metrics"):
                qs = parse_qs(parsed.query)
                gerador = qs.get("gerador", ["haiku"])[0]
                if gerador not in ("haiku", "opus"):
                    gerador = "haiku"
                try:
                    limite = int(qs.get("limite", ["7"])[0])
                except ValueError:
                    limite = 7
                tipo = qs.get("tipo", [None])[0] or None
                barreira = qs.get("barreira", [None])[0] or None
                self._send_json(
                    _handle_eval_metrics(gerador=gerador, limite=limite, tipo=tipo, barreira=barreira)
                )
            elif parsed.path.startswith("/api/v1/eval/extractor-analytics"):
                qs = parse_qs(parsed.query)
                cmd_raw = qs.get("comando_conjugado", [None])[0]
                cmd_bool = True if cmd_raw == "true" else (False if cmd_raw == "false" else None)
                self._send_json(
                    _handle_extractor_analytics(
                        disciplina=qs.get("disciplina", [None])[0],
                        faixa_etaria=qs.get("faixa_etaria", [None])[0],
                        ano_escolar=qs.get("ano_escolar", [None])[0],
                        tema=qs.get("tema", [None])[0],
                        comando_conjugado=cmd_bool,
                        provider=qs.get("provider", [None])[0],
                        model=qs.get("model", [None])[0],
                    )
                )
            elif parsed.path == "/api/v1/benchmarks/escolar":
                qs = parse_qs(parsed.query)
                try:
                    limite = int(qs.get("limite", ["0"])[0])
                except ValueError:
                    limite = 0
                self._send_json(
                    _handle_benchmark_escolar_list(
                        disciplina=qs.get("disciplina", [None])[0],
                        ano_escolar=qs.get("ano_escolar", [None])[0],
                        faixa_etaria=qs.get("faixa_etaria", [None])[0],
                        id_caracteristica_alvo=qs.get("id_caracteristica_alvo", [None])[0],
                        operacao_cognitiva=qs.get("operacao_cognitiva", [None])[0],
                        porte_texto=qs.get("porte_texto", [None])[0],
                        apenas_oficiais=qs.get("apenas_oficiais", ["false"])[0] == "true",
                        q=qs.get("q", [None])[0],
                        limite=limite,
                    )
                )
            elif parsed.path == "/api/v1/eval/rag-escolar/progress":
                self._send_json(_handle_rag_escolar_progress())
            elif parsed.path == "/api/v1/eval/rag-escolar/analytics":
                qs = parse_qs(parsed.query)
                self._send_json(
                    _handle_rag_escolar_analytics(
                        run_id=qs.get("run_id", [None])[0],
                        disciplina=qs.get("disciplina", [None])[0],
                        ano_escolar=qs.get("ano_escolar", [None])[0],
                        faixa_etaria=qs.get("faixa_etaria", [None])[0],
                        id_caracteristica_alvo=qs.get("id_caracteristica_alvo", [None])[0],
                        operacao_cognitiva=qs.get("operacao_cognitiva", [None])[0],
                        porte_texto=qs.get("porte_texto", [None])[0],
                    )
                )
            else:
                self._send_json({"error": "Not found", "path": self.path}, status=404)

        def _handle_upload(self) -> None:
            """Recebe um arquivo em multipart/form-data (campo `file`), como a rota de upload do FastAPI."""
            from email.parser import BytesParser
            from email.policy import HTTP

            from iris.api.routes.materials import process_material_file_service
            from iris.parsers.document_extractor import DocumentParsingError, UnsupportedFileFormatError
            from iris.schemas.materials import MaterialValidationError

            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b""
            # O analisador de e-mail da biblioteca padrão lê multipart a partir do cabeçalho Content-Type
            cabecalho = f"Content-Type: {self.headers.get('Content-Type', '')}\r\n\r\n".encode("latin-1", "replace")
            mensagem = BytesParser(policy=HTTP).parsebytes(cabecalho + raw)
            arquivo = None
            if mensagem.is_multipart():
                for parte in mensagem.iter_parts():
                    if parte.get_param("name", header="content-disposition") == "file":
                        arquivo = parte
                        break
            if arquivo is None:
                self._send_json(
                    {
                        "detail": {
                            "detail": "Envie o arquivo no campo 'file' de um formulário multipart/form-data.",
                            "code": "MISSING_FILE",
                            "field": "file",
                        }
                    },
                    status=422,
                )
                return

            filename = arquivo.get_filename() or "desconhecido"
            try:
                resp = process_material_file_service(filename, arquivo.get_payload(decode=True) or b"")
                self._send_json(resp.model_dump())
            except UnsupportedFileFormatError as err:
                self._send_json({"detail": {"detail": err.message, "code": err.code, "field": "file"}}, status=400)
            except DocumentParsingError as err:
                self._send_json({"detail": {"detail": err.message, "code": err.code, "field": "file"}}, status=422)
            except MaterialValidationError as err:
                self._send_json({"detail": err.to_dict()}, status=422)
            except Exception as err:  # noqa: BLE001 - mesmo tratamento da rota do FastAPI
                self._send_json(
                    {"detail": {"detail": f"Erro interno ao processar arquivo: {err}", "code": "INTERNAL_ERROR"}},
                    status=500,
                )

        def do_POST(self) -> None:  # noqa: N802
            if self.path.startswith("/api/v1/materials/upload"):
                self._handle_upload()
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                body = json.loads(raw_body or "{}")
            except ValueError:  # inclui JSONDecodeError e UnicodeDecodeError
                body = None
            if not isinstance(body, dict):
                self._send_json(
                    {
                        "detail": {
                            "detail": "O corpo da requisição deve ser um objeto JSON válido.",
                            "code": "INVALID_JSON",
                            "field": "body",
                        }
                    },
                    status=400,
                )
                return
            if self.path.startswith("/api/v1/rag/build"):
                self._send_json(_handle_rag_build())
            elif self.path.startswith("/api/v1/rag/search"):
                self._send_json(_handle_rag_search(body))
            elif self.path.startswith("/api/v1/rag/answer"):
                self._send_json(_handle_rag_answer(body))
            elif urlparse(self.path).path == "/api/v1/benchmarks/escolar/curar":
                self._send_json(_handle_benchmark_escolar_curar())
            elif urlparse(self.path).path == "/api/v1/rag/test-question":
                try:
                    self._send_json(_handle_rag_test_question(body))
                except KeyError as err:
                    self._send_json({"detail": str(err)}, status=404)
                except ValueError as err:
                    self._send_json({"detail": str(err)}, status=422)
            elif urlparse(self.path).path == "/api/v1/eval/rag-escolar/run":
                try:
                    self._send_json(_handle_rag_escolar_run(body))
                except ValueError as err:
                    self._send_json({"detail": str(err)}, status=422)
            elif urlparse(self.path).path == "/api/v1/catalogs/characteristics/select":
                from iris.api.routes.catalogs import (
                    select_surgical_characteristics_service,
                )
                from iris.schemas.catalog import (
                    CatalogValidationError,
                    CharacteristicSelectionError,
                )

                try:
                    resp = select_surgical_characteristics_service(body)
                    self._send_json(resp.model_dump())
                except CharacteristicSelectionError as err:
                    self._send_json({"detail": err.to_dict()}, status=422)
                except CatalogValidationError as err:
                    self._send_json(
                        {"detail": {"detail": str(err), "code": "CATALOG_SCHEMA_ERROR", "field": "catalog"}},
                        status=500,
                    )
                except Exception as err:  # noqa: BLE001
                    self._send_json(
                        {"detail": {"detail": f"Erro interno ao validar seleção: {err}", "code": "INTERNAL_ERROR"}},
                        status=500,
                    )
            elif urlparse(self.path).path == "/api/v1/catalogs/characteristics":
                self._send_json({"detail": "Method Not Allowed"}, status=405)
            elif self.path.startswith("/api/v1/materials/text"):
                from iris.api.routes.materials import process_material_text_service
                from iris.schemas.materials import MaterialValidationError

                try:
                    resp = process_material_text_service(body.get("text", ""))
                    self._send_json(resp.model_dump())
                except MaterialValidationError as err:
                    self._send_json({"detail": err.to_dict()}, status=422)
            elif self.path.startswith("/api/v1/materials/decompose"):
                from iris.api.routes.materials import decompose_material_service
                from iris.schemas.materials import MaterialValidationError

                try:
                    resp = decompose_material_service(body.get("text", ""))
                    self._send_json(resp.model_dump())
                except MaterialValidationError as err:
                    self._send_json({"detail": err.to_dict()}, status=422)
            elif self.path.startswith("/api/v1/materials/organize-prose"):
                from iris.api.routes.materials import organize_prose_service
                from iris.schemas.materials import MaterialValidationError

                try:
                    resp = organize_prose_service(body.get("text", ""))
                    self._send_json(resp.model_dump())
                except MaterialValidationError as err:
                    self._send_json({"detail": err.to_dict()}, status=422)
            else:

                self._send_json({"error": "Not found", "path": self.path}, status=404)

    print("================================================================================")
    print(f"  Íris Web & API rodando em: http://{host}:{port}")
    print(f"  Healthcheck              : http://{host}:{port}/api/v1/health")
    print("================================================================================")
    server = HTTPServer((host, port), IrisHandler)
    server.serve_forever()


if __name__ == "__main__":
    settings = get_settings()
    run_stdlib_server(host=settings.host, port=settings.port)
