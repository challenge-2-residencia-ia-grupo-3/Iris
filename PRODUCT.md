# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary:** Engenheiro de IA / desenvolvedor do projeto Íris auditando o pipeline RAG, comparando recuperadores, geradores (Llama 3 / Ollama, Groq, Claude) e juízes (Claude Sonnet / heurísticas), e inspecionando métricas de fidelidade, relevância e recuperação.

## Product Purpose

Bancada técnica de auditoria RAG e evidências pedagógicas da plataforma Íris (Challenge 2 — Residência em IA), servida diretamente pelo backend FastAPI em `localhost:8000` (`playground.html`). Permite medir, comparar e depurar a qualidade de recuperação e fundamentação científica das adaptações pedagógicas para alunos com TDAH em 5 visões integradas:

1. **Auditoria do Benchmark** (`#tab-benchmark`)
2. **Benchmark Escolar (136)** (`#tab-escolar`)
3. **Catálogo de Características TDAH** (`#tab-catalogo`)
4. **Consulta RAG ao Vivo** (`#tab-aovivo`)
5. **Ferramentas da API** (`#tab-ferramentas`)

## Positioning

Diferente de dashboards genéricos de LLM, a bancada acopla métricas estilo Ragas e auditoria frase a frase do Claude Sonnet diretamente às 39 barreiras funcionais do catálogo TDAH, às 136 questões escolares curadas e às travas de governança científica (rastreabilidade `[T#]`, avisos editoriais e arquitetura Zero-Database / LGPD).

## Operating Context

- Executada localmente durante desenvolvimento e ciclos de avaliação (`make up` / `uvicorn` em `http://127.0.0.1:8000`).
- Uso frequente em sessões de engenharia para rodar baterias filtradas do Benchmark Escolar (136), acompanhar progresso em tempo real, inspecionar vereditos frase a frase e validar mudanças de recuperação/prompt antes de consolidar relatórios.

## Capabilities and Constraints

- **Arquitetura de entrega:** Arquivo único `backend/src/iris/static/playground.html` (HTML/CSS/JS vanilla) servido pelo FastAPI em `GET /`, sem pipeline de build separado para essa superfície.
- **Preservação funcional obrigatória:** Manter todas as 5 abas, todos os contratos/endpoints da API (`/api/v1/health`, `/api/v1/catalog`, `/api/v1/eval/metrics`, `/api/v1/eval/rag-escolar/*`, `/api/v1/benchmarks/escolar*`, `/api/v1/rag/*`), IDs/hooks funcionais usados pelos scripts e testes automatizados, e todos os dados/métricas reais sem alterar a lógica do backend.
- **Governança:** Zero-Database / Privacy by Design (LGPD — sem persistência de dados de alunos), fidelidade a evidências reais e sem métricas ou afirmações inventadas.

## Evidence on Hand

- `backend/src/iris/static/playground.html` (implementação atual da bancada).
- `backend/src/iris/eval/rag_escolar_benchmark.py` e `reports/rag_escolar_runs.jsonl` (136 questões curadas e rodadas reais).
- `backend/src/iris/eval/rag_metrics.py` e `backend/src/iris/eval/sonnet_judge.py` (métricas de auditoria e vereditos frase a frase).

## Product Principles

1. **Clareza operacional acima de ornamento:** Dados de avaliação, latências, scores e vereditos frase a frase devem ser escaneáveis rapidamente durante depuração.
2. **Rastreabilidade explícita:** Toda métrica exibida na tela deve corresponder a um cálculo real do backend (sem números sintéticos ou estados enganosos).
3. **Separar sinal de ruído:** Destacar o avaliador efetivo (`claude_sonnet` vs. léxico), fallbacks (`bm25` vs. `qwen3+rerank50`) e progresso ao vivo sem esconder detalhes diagnósticos.
