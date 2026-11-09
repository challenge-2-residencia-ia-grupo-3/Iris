"""Ponto de entrada Backend (FastAPI / HTTP) e Frontend Web inicial da plataforma Íris.

Rotas disponíveis:
- `GET  /`                    -> Interface Web Interativa (Copiloto Docente: Catálogo TDAH + RAG Ao Vivo + Métricas)
- `GET  /api/v1/health`       -> Status operacional, conectividade LLM e trava Zero-Database
- `GET  /api/v1/catalog`      -> Catálogo modular de características funcionais do TDAH (#39)
- `POST /api/v1/rag/search`   -> Busca de evidências científicas filtrada por característica/barreira
- `POST /api/v1/rag/answer`   -> Geração de resposta fundamentada ao vivo (Ollama / Groq / Extractive)
- `GET  /api/v1/eval/metrics` -> Cálculo das 12 métricas do RAG (Relatório Íris + 7 Métricas RAGAS)
"""
from __future__ import annotations

import json
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
  <title>Íris — Copiloto de Adaptação Pedagógica (TDAH & RAG)</title>
  <style>
    :root {
      --bg: #0f172a; --card: #1e293b; --border: #334155;
      --text: #f8fafc; --muted: #94a3b8; --accent: #38bdf8; --accent-dark: #0284c7;
      --ok: #22c55e; --warn: #eab308;
    }
    * { box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }
    body { margin: 0; background: var(--bg); color: var(--text); line-height: 1.5; }
    header {
      padding: 1.25rem 2rem; border-bottom: 1px solid var(--border);
      display: flex; justify-content: space-between; align-items: center; background: #0b1120;
    }
    header h1 { margin: 0; font-size: 1.35rem; color: var(--accent); }
    .badge {
      padding: 0.25rem 0.65rem; border-radius: 999px; font-size: 0.8rem;
      background: #1e3a8a; color: #bae6fd; border: 1px solid #0369a1;
    }
    main { max-width: 1200px; margin: 1.5rem auto; padding: 0 1.5rem; display: grid; gap: 1.5rem; grid-template-columns: 1fr 1fr; }
    .full { grid-column: 1 / -1; }
    .card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: 0.75rem; padding: 1.25rem;
    }
    h2 { margin-top: 0; font-size: 1.1rem; color: #e2e8f0; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }
    label { display: block; font-size: 0.85rem; color: var(--muted); margin: 0.75rem 0 0.25rem; }
    select, input, textarea {
      width: 100%; padding: 0.6rem; border-radius: 0.5rem;
      border: 1px solid var(--border); background: #0f172a; color: var(--text);
    }
    button {
      margin-top: 1rem; padding: 0.65rem 1.2rem; border-radius: 0.5rem; border: none;
      background: var(--accent-dark); color: white; font-weight: 600; cursor: pointer;
    }
    button:hover { background: var(--accent); color: #0f172a; }
    pre {
      background: #0b1120; padding: 1rem; border-radius: 0.5rem; border: 1px solid var(--border);
      overflow-x: auto; white-space: pre-wrap; font-size: 0.85rem; color: #cbd5e1;
    }
    .grid-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem; }
    .metric-box { background: #0b1120; padding: 0.75rem; border-radius: 0.5rem; border: 1px solid var(--border); text-align: center; }
    .metric-val { font-size: 1.4rem; font-weight: 700; color: var(--accent); }
    .metric-lbl { font-size: 0.75rem; color: var(--muted); }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Íris — Plataforma Inteligente de Adaptação Pedagógica</h1>
      <small style="color: var(--muted)">Pilar 1: Características Singulares • Pilar 2: Andaime em 3 Níveis • Pilar 3: Zero-Database (LGPD)</small>
    </div>
    <div id="health-badge" class="badge">Verificando status...</div>
  </header>

  <main>
    <section class="card">
      <h2>1. Parametrização Docente (Catálogo Modular TDAH #39)</h2>
      <label for="carac-select">Barreira Funcional Observada em Sala:</label>
      <select id="carac-select"></select>

      <label for="nivel-select">Nível de Andaime Cognitivo (Scaffolding):</label>
      <select id="nivel-select">
        <option value="1">Nível 1 — Adaptação Leve (Destaque visual / formatação)</option>
        <option value="2" selected>Nível 2 — Adaptação Moderada (Decomposição em checklists)</option>
        <option value="3">Nível 3 — Adaptação Intensiva (Escalonamento passo a passo)</option>
      </select>

      <label for="pergunta-input">Dúvida Docente ou Enunciado da Questão:</label>
      <textarea id="pergunta-input" rows="3">Aluno esquece o enunciado no meio da questão de várias etapas: o que fazer sem dar a resposta?</textarea>

      <div style="display:flex; gap: 0.75rem;">
        <button onclick="buscarPorCaracteristica()">Buscar Diretriz + Evidências RAG</button>
        <button onclick="gerarRespostaAoVivo()" style="background:#15803d;">Gerar Resposta Fundamentada (LLM)</button>
      </div>
    </section>

    <section class="card">
      <h2>2. Auditoria de Métricas do RAG (Relatório Íris + 7 Métricas RAGAS)</h2>
      <div id="metrics-cards" class="grid-metrics"></div>
      <button onclick="carregarMetricas()">Recalcular Métricas Oficiais</button>
    </section>

    <section class="card full">
      <h2>3. Resultado da Consulta / Adaptação Fundamentada e Fontes Citadas [T1..T5]</h2>
      <pre id="output-box">Selecione uma característica acima e clique em "Buscar Diretriz + Evidências RAG" ou "Gerar Resposta Fundamentada".</pre>
    </section>
  </main>

  <script>
    async function init() {
      const h = await fetch('/api/v1/health').then(r => r.json());
      const badge = document.getElementById('health-badge');
      badge.textContent = `LLM: ${h.llm_provider} (${h.llm_model}) | Ollama: ${h.ollama_online ? 'ONLINE' : 'OFFLINE (Fallback ativo)'} | Zero-DB: ${h.zero_student_database}`;

      const cat = await fetch('/api/v1/catalog').then(r => r.json());
      const sel = document.getElementById('carac-select');
      (cat.caracteristicas || []).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id_caracteristica;
        opt.textContent = `${c.nome} [${c.barreira_rag_associada}]`;
        sel.appendChild(opt);
      });
      await carregarMetricas();
    }

    async function buscarPorCaracteristica() {
      const out = document.getElementById('output-box');
      out.textContent = 'Consultando Catálogo TDAH e recuperando trechos científicos do RAG...';
      const payload = {
        id_caracteristica: document.getElementById('carac-select').value,
        nivel: parseInt(document.getElementById('nivel-select').value, 10),
        pergunta: document.getElementById('pergunta-input').value
      };
      const res = await fetch('/api/v1/rag/search', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
      }).then(r => r.json());
      out.textContent = JSON.stringify(res, null, 2);
    }

    async function gerarRespostaAoVivo() {
      const out = document.getElementById('output-box');
      out.textContent = 'Executando RAG + LLM ao vivo (aguarde)...';
      const payload = {
        pergunta: document.getElementById('pergunta-input').value,
        k: 5
      };
      const res = await fetch('/api/v1/rag/answer', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
      }).then(r => r.json());
      out.textContent = JSON.stringify(res, null, 2);
    }

    async function carregarMetricas() {
      const m = await fetch('/api/v1/eval/metrics').then(r => r.json());
      const ir = m.metricas_relatorio_iris;
      const n10 = m.notas_0_a_10;
      const items = [
        ['Recall@5', ir.recall_at_5],
        ['Atendidas (Top-5)', ir.consultas_atendidas_pct + '%'],
        ['MRR', ir.mrr],
        ['Sustentadas', ir.frases_sustentadas_pct + '%'],
        ['Fidelidade (RAGAS)', n10['1_fidelidade'] + '/10'],
        ['Relevância Resp.', n10['2_relevancia_respostas'] + '/10'],
        ['Precisão Ctx.', n10['4_precisao_contexto'] + '/10'],
        ['Correção Geral', n10['7_correcao_respostas'] + '/10']
      ];
      document.getElementById('metrics-cards').innerHTML = items.map(
        ([lbl, val]) => `<div class="metric-box"><div class="metric-val">${val}</div><div class="metric-lbl">${lbl}</div></div>`
      ).join('');
    }

    init();
  </script>
</body>
</html>
"""


def _handle_catalog() -> dict[str, Any]:
    from iris.schemas.catalog import load_official_tdah_catalog

    return load_official_tdah_catalog().to_dict()


def _handle_rag_search(body: dict[str, Any]) -> dict[str, Any]:
    from iris.rag.bridge import buscar_evidencias, buscar_por_caracteristica_atomica

    id_carac = body.get("id_caracteristica")
    nivel = int(body.get("nivel", 2))
    pergunta = body.get("pergunta", "")
    if id_carac:
        return buscar_por_caracteristica_atomica(
            id_caracteristica=id_carac,
            nivel=nivel,
            pergunta_adicional=pergunta,
            k=int(body.get("k", 5)),
        )
    return {
        "pergunta": pergunta,
        "trechos_rag": buscar_evidencias(pergunta=pergunta, k=int(body.get("k", 5))),
    }


def _handle_rag_answer(body: dict[str, Any]) -> dict[str, Any]:
    import os
    from iris.core.llm_client import get_llm_client
    from iris.rag.bridge import responder_fundamentado

    pergunta = body.get("pergunta", "")
    k = int(body.get("k", 5))
    client = get_llm_client(allow_fallback_to_extractive=True)
    if not client.status()["primary_available"]:
        os.environ["RAG_LLM"] = "extractive"
    return responder_fundamentado(pergunta=pergunta, k=k)


def _handle_eval_metrics() -> dict[str, Any]:
    from iris.eval.rag_metrics import avaliar_pipeline_registrado

    return avaliar_pipeline_registrado(gerador="haiku")


def create_app() -> Any:
    """Cria e configura a aplicação FastAPI stateless (com rotas de API e Frontend Web)."""
    from fastapi import Body, FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI(
        title="Íris — Adaptação Inteligente de Materiais Pedagógicos",
        description=(
            "Plataforma copiloto docente para adaptação cirúrgica de materiais didáticos "
            "baseada em evidências (DUA/MEC) e arquitetura Zero-Database (LGPD)."
        ),
        version=__version__,
    )

    @app.get("/", response_class=HTMLResponse, tags=["frontend"])
    def index_page() -> str:
        return FRONTEND_HTML

    @app.get("/api/v1/health", tags=["infra"])
    def health_check() -> dict[str, Any]:
        return get_health_status()

    @app.get("/api/v1/catalog", tags=["catalogo"])
    def get_catalog() -> dict[str, Any]:
        return _handle_catalog()

    @app.post("/api/v1/rag/search", tags=["rag"])
    def rag_search(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return _handle_rag_search(payload)

    @app.post("/api/v1/rag/answer", tags=["rag"])
    def rag_answer(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return _handle_rag_answer(payload)

    @app.get("/api/v1/eval/metrics", tags=["eval"])
    def eval_metrics() -> dict[str, Any]:
        return _handle_eval_metrics()

    return app


try:
    app = create_app()
except Exception:
    app = None


def run_stdlib_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Servidor HTTP nativo de fallback caso `uvicorn`/`fastapi` não estejam ativos no Python atual."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class IrisHandler(BaseHTTPRequestHandler):
        def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/" or self.path.startswith("/index"):
                raw = FRONTEND_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            elif self.path.startswith("/api/v1/health"):
                self._send_json(get_health_status())
            elif self.path.startswith("/api/v1/catalog"):
                self._send_json(_handle_catalog())
            elif self.path.startswith("/api/v1/eval/metrics"):
                self._send_json(_handle_eval_metrics())
            else:
                self._send_json({"error": "Not found", "path": self.path}, status=404)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            body = json.loads(raw_body or "{}")
            if self.path.startswith("/api/v1/rag/search"):
                self._send_json(_handle_rag_search(body))
            elif self.path.startswith("/api/v1/rag/answer"):
                self._send_json(_handle_rag_answer(body))
            else:
                self._send_json({"error": "Not found", "path": self.path}, status=404)

    print(f"============================================================")
    print(f"  Íris Web & API rodando em: http://{host}:{port}")
    print(f"  Healthcheck              : http://{host}:{port}/api/v1/health")
    print(f"============================================================")
    server = HTTPServer((host, port), IrisHandler)
    server.serve_forever()


if __name__ == "__main__":
    settings = get_settings()
    run_stdlib_server(host=settings.host, port=settings.port)
