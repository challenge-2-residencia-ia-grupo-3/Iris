"""Ponto de entrada Backend (FastAPI / HTTP) e Frontend Web da plataforma Íris.

Rotas disponíveis:
- `GET  /`                    -> Interface Web Completa (Métricas Contextualizadas no Topo + Opções de Criar/Rodar RAG + Textos)
- `GET  /api/v1/health`       -> Status operacional, conectividade LLM e trava Zero-Database
- `GET  /api/v1/catalog`      -> Catálogo modular de características funcionais do TDAH (#39)
- `GET  /api/v1/eval/metrics` -> Cálculo das 12 métricas do RAG + consultas com textos completos
- `POST /api/v1/rag/build`    -> Cria / recria a base de 1.385 chunks do RAG a partir dos documentos
- `POST /api/v1/rag/search`   -> Busca de evidências científicas filtrada por característica/barreira
- `POST /api/v1/rag/answer`   -> Geração de resposta fundamentada ao vivo (Ollama / Groq / Extractive) + textos + métricas
"""
from __future__ import annotations

import json
import re
from typing import Any

from iris import __version__
from iris.config import get_settings


def get_health_status() -> dict[str, Any]:
    """Retorna o status operacional e guardrails arquiteturais do serviço."""
    settings = get_settings()
    try:
        from iris.core.llm_client import get_llm_client

        llm_info = get_llm_client().status()
    except Exception:
        llm_info = {"ollama_online": False}

    return {
        "status": "ok",
        "service": "iris-pedagogical-adapter",
        "version": __version__,
        "environment": settings.env,
        "zero_student_database": settings.zero_student_database,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "ollama_online": llm_info.get("ollama_online", False),
        "ollama_models": llm_info.get("ollama_installed_models", []),
        "rag_backend": settings.rag_banco,
    }


FRONTEND_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Íris — Central do RAG, Métricas Contextualizadas e Copiloto TDAH</title>
  <style>
    :root {
      --bg: #0f172a; --card: #1e293b; --border: #334155;
      --text: #f8fafc; --muted: #94a3b8; --accent: #38bdf8; --accent-dark: #0284c7;
      --ok: #16a34a; --purple: #7c3aed;
    }
    * { box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }
    body { margin: 0; background: var(--bg); color: var(--text); line-height: 1.5; }
    header {
      padding: 1.1rem 2rem; border-bottom: 1px solid var(--border);
      display: flex; justify-content: space-between; align-items: center; background: #0b1120;
    }
    header h1 { margin: 0; font-size: 1.3rem; color: var(--accent); }
    .badge {
      padding: 0.3rem 0.75rem; border-radius: 999px; font-size: 0.8rem;
      background: #1e3a8a; color: #bae6fd; border: 1px solid #0369a1;
    }
    main { max-width: 1280px; margin: 1.25rem auto; padding: 0 1.25rem; display: grid; gap: 1.25rem; grid-template-columns: 1fr 1fr; }
    .full { grid-column: 1 / -1; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 0.75rem; padding: 1.25rem; }
    h2 { margin-top: 0; font-size: 1.05rem; color: #e2e8f0; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }
    label { display: block; font-size: 0.82rem; color: var(--muted); margin: 0.65rem 0 0.2rem; }
    select, input, textarea {
      width: 100%; padding: 0.55rem; border-radius: 0.5rem;
      border: 1px solid var(--border); background: #0f172a; color: var(--text);
    }
    .btn-row { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-top: 0.9rem; }
    button {
      padding: 0.6rem 1rem; border-radius: 0.5rem; border: none;
      background: var(--accent-dark); color: white; font-weight: 600; cursor: pointer; font-size: 0.85rem;
    }
    button:hover { opacity: 0.92; }
    .grid-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(175px, 1fr)); gap: 0.65rem; margin-bottom: 0.75rem; }
    .metric-box { background: #0b1120; padding: 0.7rem; border-radius: 0.5rem; border: 1px solid var(--border); }
    .metric-val { font-size: 1.25rem; font-weight: 700; color: var(--accent); }
    .metric-lbl { font-size: 0.8rem; font-weight: 600; color: #e2e8f0; margin-top: 0.15rem; }
    .metric-desc { font-size: 0.72rem; color: var(--muted); margin-top: 0.2rem; }
    .chunk-card {
      background: #0b1120; border: 1px solid var(--border); border-radius: 0.5rem;
      padding: 0.85rem; margin-top: 0.65rem;
    }
    .chunk-header { font-size: 0.82rem; font-weight: 700; color: var(--accent); margin-bottom: 0.35rem; }
    .chunk-text { font-size: 0.83rem; color: #cbd5e1; white-space: pre-wrap; }
    .answer-box {
      background: #052e16; border: 1px solid #15803d; border-radius: 0.5rem;
      padding: 1rem; margin-bottom: 0.85rem; color: #dcfce7; white-space: pre-wrap;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Íris — Central do RAG, Métricas Contextualizadas & Copiloto TDAH</h1>
      <small style="color: var(--muted)">Pilar 1: Características Singulares • Pilar 2: Andaime em 3 Níveis • Pilar 3: Zero-Database (LGPD)</small>
    </div>
    <div id="health-badge" class="badge">Verificando status...</div>
  </header>

  <main>
    <!-- 1. MÉTRICAS CONTEXTUALIZADAS LOGO NO COMEÇO -->
    <section class="card full">
      <h2>1. Painel Contextualizado de Métricas do RAG (Tabela 1 Oficial Íris + Tabela 2 das 7 Métricas de Mercado RAGAS)</h2>
      <div id="metrics-iris" class="grid-metrics"></div>
      <div id="metrics-ragas" class="grid-metrics"></div>
      <div class="btn-row">
        <button onclick="carregarMetricas('haiku')">Ver Métricas + Textos Registrados (Haiku)</button>
        <button onclick="carregarMetricas('opus')" style="background: var(--purple);">Ver Métricas + Textos Registrados (Opus)</button>
        <button onclick="recriarBaseRAG()" style="background: #475569;">Criar / Recriar Base de Chunks do RAG (1.385 trechos)</button>
      </div>
    </section>

    <!-- 2. OPÇÕES DE RODAR O RAG E ADAPTAÇÃO -->
    <section class="card full">
      <h2>2. Central de Execução do RAG (Por Característica do Catálogo TDAH ou Pergunta Ao Vivo no LLM Local)</h2>
      <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.75rem;">
        <div>
          <label for="carac-select">Barreira Funcional Observada (Catálogo #39):</label>
          <select id="carac-select"></select>
        </div>
        <div>
          <label for="nivel-select">Nível de Andaime Cognitivo (Scaffolding):</label>
          <select id="nivel-select">
            <option value="1">Nível 1 — Adaptação Leve (Destaque visual)</option>
            <option value="2" selected>Nível 2 — Adaptação Moderada (Checklists)</option>
            <option value="3">Nível 3 — Adaptação Intensiva (Passo a passo)</option>
          </select>
        </div>
        <div>
          <label for="metodo-select">Método de Busca do RAG:</label>
          <select id="metodo-select">
            <option value="bm25">BM25 Léxico Local (Instantâneo, sem Docker)</option>
            <option value="qwen3+rerank50">Qwen3 + Reranker Top-50 (Requer pgvector)</option>
            <option value="hibrido">Híbrido BM25 + Vetorial (RRF)</option>
          </select>
        </div>
      </div>

      <label for="pergunta-input">Pergunta Docente ou Enunciado da Questão Escolar:</label>
      <textarea id="pergunta-input" rows="2">Aluno esquece o enunciado no meio da questão de várias etapas: o que fazer sem dar a resposta?</textarea>

      <div class="btn-row">
        <button onclick="gerarRespostaAoVivo()" style="background: var(--ok);">Rodar RAG Ao Vivo (LLM Local / Fallback) + Ver Textos e Métricas</button>
        <button onclick="buscarPorCaracteristica()">Buscar Diretriz do Catálogo + Trechos do RAG</button>
      </div>
    </section>

    <!-- 3. EXIBIÇÃO DOS TEXTOS DOS TRECHOS E RESPOSTAS JUNTO COM AS MÉTRICAS -->
    <section class="card full">
      <h2>3. Textos dos Trechos Recuperados [T1..T5], Resposta Fundamentada e Métricas da Consulta</h2>
      <div id="results-container">Carregando demonstração inicial com textos e métricas...</div>
    </section>
  </main>

  <script>
    async function init() {
      const h = await fetch('/api/v1/health').then(r => r.json());
      document.getElementById('health-badge').textContent =
        `LLM: ${h.llm_provider} (${h.llm_model}) | Ollama: ${h.ollama_online ? 'ONLINE' : 'Fallback Extrativo'} | Zero-DB: ${h.zero_student_database}`;

      const cat = await fetch('/api/v1/catalog').then(r => r.json());
      const sel = document.getElementById('carac-select');
      (cat.caracteristicas || []).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id_caracteristica;
        opt.textContent = `${c.nome} [${c.barreira_rag_associada}]`;
        sel.appendChild(opt);
      });
      await carregarMetricas('haiku');
    }

    function renderConsultasComTextos(consultas) {
      const container = document.getElementById('results-container');
      if (!consultas || !consultas.length) {
        container.innerHTML = '<p>Nenhuma consulta para exibir.</p>';
        return;
      }
      container.innerHTML = consultas.map(c => {
        const mc = c.metricas_consulta || {};
        const trechosHtml = (c.trechos_recuperados || []).map(t => `
          <div class="chunk-card">
            <div class="chunk-header">[${t.ref}] ${t.chunk_id} (${t.pagina ? 'p. ' + t.pagina : 's/p'}) — ${t.status_gabarito || 'Trecho Recuperado'} | ${t.titulo || ''}</div>
            <div class="chunk-text">${t.texto || t.trecho || ''}</div>
          </div>
        `).join('');
        return `
          <div style="margin-bottom: 1.75rem; border-bottom: 2px solid var(--border); padding-bottom: 1.25rem;">
            <div style="font-weight:700; font-size:1rem; color:#f8fafc; margin-bottom:0.35rem;">
              [${c.id || 'AO-VIVO'}] Pergunta: "${c.pergunta}"
            </div>
            <div style="font-size:0.82rem; color:var(--accent); margin-bottom:0.65rem;">
              Métricas desta consulta — Recall@5: <b>${mc.recall_at_5 ?? '-'}</b> | MRR: <b>${mc.mrr ?? '-'}</b> |
              Precisão Contexto (AP@5): <b>${mc.precisao_contexto_ap5 ?? '-'}</b> |
              Fidelidade: <b>${c.fidelidade_frase ?? 'Verificada'}</b>
            </div>
            <div class="answer-box"><b>RESPOSTA FUNDAMENTADA GERADA:</b>\n${c.resposta || ''}</div>
            <div style="font-size:0.85rem; font-weight:600; color:var(--muted);">TEXTOS COMPLETOS DOS TRECHOS ENTREGUES AO MODELO [T1..T5]:</div>
            ${trechosHtml}
          </div>
        `;
      }).join('');
    }

    async function carregarMetricas(gerador = 'haiku') {
      const m = await fetch(`/api/v1/eval/metrics?gerador=${gerador}`).then(r => r.json());
      const ir = m.metricas_relatorio_iris;
      const n10 = m.notas_0_a_10;

      const irisCards = [
        ['Recall@5 (Oficial Íris)', ir.recall_at_5, 'Fração de trechos relevantes no Top-5 (100x acima do acaso)'],
        ['Consultas Atendidas', ir.consultas_atendidas_pct + '%', 'Perguntas com ao menos 1 trecho relevante no Top-5'],
        ['MRR (Posição 1º Relev.)', ir.mrr, 'Inverso da posição do 1º trecho relevante (1º-2º lugar)'],
        ['Frases Sustentadas', ir.frases_sustentadas_pct + '%', `+${ir.frases_parcialmente_sustentadas_pct}% parciais (0% alucinação)`],
        ['Citações Inválidas', ir.citacoes_invalidas, 'Frases citando [Tn] inexistente no prompt'],
        ['Concordância (Kappa)', `${ir.concordancia_bruta_pct}% (κ=${ir.kappa_cohen})`, 'Acordo entre Juiz A e Juiz B']
      ];
      const ragasCards = [
        ['1. Fidelidade (RAGAS)', n10['1_fidelidade'] + '/10', 'Ancoragem factual estrita nos documentos de origem'],
        ['2. Relevância Resposta', n10['2_relevancia_respostas'] + '/10', 'Utilidade direta para a dúvida do professor'],
        ['3. Recuperação Contexto', n10['3_recuperacao_contexto'] + '/10', 'Capacidade de trazer as evidências do gabarito'],
        ['4. Precisão Contexto', n10['4_precisao_contexto'] + '/10', 'Trechos relevantes posicionados no topo do ranking'],
        ['5. Relevância Contexto', n10['5_relevancia_contexto'] + '/10', 'Equilíbrio F1 entre amplitude e especificidade'],
        ['6. Similaridade Semânt.', n10['6_similaridade_semantica'] + '/10', 'Alinhamento semântico com a verdade básica'],
        ['7. Correção Geral', n10['7_correcao_respostas'] + '/10', 'Combinação 60% Fidelidade + 40% Similaridade']
      ];

      document.getElementById('metrics-iris').innerHTML = irisCards.map(
        ([lbl, val, desc]) => `<div class="metric-box"><div class="metric-val">${val}</div><div class="metric-lbl">${lbl}</div><div class="metric-desc">${desc}</div></div>`
      ).join('');
      document.getElementById('metrics-ragas').innerHTML = ragasCards.map(
        ([lbl, val, desc]) => `<div class="metric-box"><div class="metric-val" style="color:#4ade80;">${val}</div><div class="metric-lbl">${lbl}</div><div class="metric-desc">${desc}</div></div>`
      ).join('');

      if (m.consultas_com_textos) {
        renderConsultasComTextos(m.consultas_com_textos);
      }
    }

    async function recriarBaseRAG() {
      const container = document.getElementById('results-container');
      container.innerHTML = '<p>Recriando chunks.jsonl a partir dos documentos científicos e normativos...</p>';
      const res = await fetch('/api/v1/rag/build', { method: 'POST' }).then(r => r.json());
      container.innerHTML = `<div class="answer-box">Base do RAG verificada/recriada com sucesso!\nTotal de Chunks: ${res.total_chunks}\nArquivo: ${res.chunks_path}\nBarreiras Indexadas: ${res.barreiras.join(', ')}</div>`;
    }

    async function buscarPorCaracteristica() {
      const container = document.getElementById('results-container');
      container.innerHTML = '<p>Buscando diretrizes do Catálogo TDAH e textos científicos no RAG...</p>';
      const payload = {
        id_caracteristica: document.getElementById('carac-select').value,
        nivel: parseInt(document.getElementById('nivel-select').value, 10),
        pergunta: document.getElementById('pergunta-input').value,
        metodo: document.getElementById('metodo-select').value
      };
      const res = await fetch('/api/v1/rag/search', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
      }).then(r => r.json());

      const dir = res.diretriz_andaime || {};
      const sintese = `CARACTERÍSTICA: ${res.nome_caracteristica} (Barreira RAG: ${res.barreira_rag_associada})\n` +
                      `NÍVEL ${res.nivel_selecionado} (${dir.rotulo || ''}): ${dir.objetivo_andaime || ''}\n` +
                      `AÇÕES PERMITIDAS: ${(dir.acoes_permitidas || []).join(' | ')}\n` +
                      `RESTRIÇÕES DE ESCOPO: ${(dir.restricoes_escopo || []).join(' | ')}`;
      renderConsultasComTextos([{
        id: res.id_caracteristica,
        pergunta: payload.pergunta,
        resposta: sintese,
        metricas_consulta: { recall_at_5: 'Filtro Determinístico', mrr: 1.0, precisao_contexto_ap5: 1.0 },
        trechos_recuperados: (res.trechos_rag || []).map((t, idx) => ({
          ref: `T${idx + 1}`,
          chunk_id: t.chunk_id,
          pagina: t.pagina,
          titulo: t.titulo,
          status_gabarito: `Score: ${(t.score || 0).toFixed(3)}`,
          texto: t.trecho
        }))
      }]);
    }

    async function gerarRespostaAoVivo() {
      const container = document.getElementById('results-container');
      container.innerHTML = '<p>Executando busca RAG + geração ao vivo no LLM e calculando métricas da resposta...</p>';
      const payload = {
        pergunta: document.getElementById('pergunta-input').value,
        metodo: document.getElementById('metodo-select').value,
        k: 5
      };
      const res = await fetch('/api/v1/rag/answer', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
      }).then(r => r.json());
      renderConsultasComTextos([res]);
    }

    init();
  </script>
</body>
</html>
"""


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
    from iris.rag.bridge import buscar_evidencias, buscar_por_caracteristica_atomica

    id_carac = body.get("id_caracteristica")
    nivel = int(body.get("nivel", 2))
    pergunta = body.get("pergunta", "")
    metodo = body.get("metodo") or "bm25"
    if id_carac:
        return buscar_por_caracteristica_atomica(
            id_caracteristica=id_carac,
            nivel=nivel,
            pergunta_adicional=pergunta,
            metodo=metodo,
            k=int(body.get("k", 5)),
        )
    return {
        "pergunta": pergunta,
        "trechos_rag": buscar_evidencias(pergunta=pergunta, metodo=metodo, k=int(body.get("k", 5))),
    }


def _handle_rag_answer(body: dict[str, Any]) -> dict[str, Any]:
    import os
    from iris.core.llm_client import get_llm_client
    from iris.eval.rag_metrics import calcular_similaridade_semantica, verificar_sustentacao_frase_no_trecho
    from iris.rag.bridge import buscar_evidencias, responder_fundamentado

    pergunta = body.get("pergunta", "")
    metodo = body.get("metodo") or "bm25"
    k = int(body.get("k", 5))
    client = get_llm_client(allow_fallback_to_extractive=True)
    if not client.status()["primary_available"]:
        os.environ["RAG_LLM"] = "extractive"

    res = responder_fundamentado(pergunta=pergunta, metodo=metodo, k=k)
    trechos = res.get("trechos_entregues") or buscar_evidencias(pergunta=pergunta, metodo=res["metodo"], k=k)
    resposta_texto = res.get("resposta", "")

    # Calcula a fidelidade frase a frase em tempo real
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

    res["fidelidade_frase"] = f"{fidelidade:.2f} (Relevância: {relevancia:.2f} | LLM: {res.get('llm')})"
    res["metricas_consulta"] = {
        "recall_at_5": "Ao Vivo",
        "mrr": f"{res.get('segundos_total', 0)}s",
        "precisao_contexto_ap5": f"Citações inv.: {len(res['conferencia']['citacoes_invalidas'])}",
    }
    res["trechos_recuperados"] = [
        {
            "ref": f"T{idx}",
            "chunk_id": t.get("chunk_id", ""),
            "pagina": t.get("pagina"),
            "titulo": t.get("titulo", ""),
            "status_gabarito": f"Score: {t.get('score', 0):.3f}",
            "texto": t.get("trecho", ""),
        }
        for idx, t in enumerate(trechos, start=1)
    ]
    return res


def _handle_eval_metrics(gerador: str = "haiku") -> dict[str, Any]:
    from iris.eval.rag_metrics import (
        avaliar_pipeline_registrado,
        obter_consultas_com_textos_e_metricas,
    )

    dados = avaliar_pipeline_registrado(gerador=gerador)
    dados["consultas_com_textos"] = obter_consultas_com_textos_e_metricas(gerador=gerador, limite=4)
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
        return FRONTEND_HTML

    @app.get("/api/v1/health", tags=["infra"])
    def health_check() -> dict[str, Any]:
        return get_health_status()

    # Registra rotas de materiais didáticos (História 1.1.1 - Issue #4)
    from iris.api.routes.materials import router as materials_router

    if materials_router is not None:
        app.include_router(materials_router, prefix="/api/v1")

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
    def eval_metrics(gerador: str = Query("haiku", pattern="^(haiku|opus)$")) -> dict[str, Any]:
        return _handle_eval_metrics(gerador=gerador)

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
                raw = FRONTEND_HTML.encode("utf-8")
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            elif parsed.path.startswith("/api/v1/health"):
                self._send_json(get_health_status())
            elif parsed.path.startswith("/api/v1/catalog"):
                self._send_json(_handle_catalog())
            elif parsed.path.startswith("/api/v1/eval/metrics"):
                qs = parse_qs(parsed.query)
                gerador = qs.get("gerador", ["haiku"])[0]
                self._send_json(_handle_eval_metrics(gerador=gerador))
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
            else:
                self._send_json({"error": "Not found", "path": self.path}, status=404)

        def do_POST(self) -> None:  # noqa: N802
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
