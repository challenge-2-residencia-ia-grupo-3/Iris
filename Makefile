.PHONY: help up dev front rag extrator extractor extrator-bench extrator-analytics check test db-up db-down docs setup backend

HOST ?= 127.0.0.1
PORT ?= 8000
FRONT_PORT ?= 3000
DOCS_PORT ?= 8001
LLM_MODEL ?= llama3:latest
PYTHONPATH := $(CURDIR)/backend/src:$(CURDIR)/rag/iris-rag/pacote
VENV_PY := $(CURDIR)/.venv/bin/python3
PYTHON_BIN := $(shell if [ -x "$(VENV_PY)" ]; then echo "$(VENV_PY)"; else echo "python3"; fi)

PYTHON_RUN = PYTHONPATH=$(PYTHONPATH) $(PYTHON_BIN)

help:
	@echo "=========================================================================================="
	@echo "  Íris — Comandos Essenciais do Projeto (Makefile)"
	@echo "=========================================================================================="
	@echo "  make up                  Verifica tudo (uv/npm install/Ollama/RAG) e sobe Backend + Frontend"
	@echo "  make check               Smoke-check rápido de ambiente, catálogo, PII, API, RAG e Extrator"
	@echo "  make test                Executa toda a bateria de testes automatizados em backend/tests"
	@echo "  make dev                 Sobe o Backend API e abre o Playground RAG em http://$(HOST):$(PORT)"
	@echo "  make backend             Sobe apenas o Backend FastAPI na porta $(PORT)"
	@echo "  make front               Verifica npm install e sobe o Frontend Next.js em http://localhost:$(FRONT_PORT)"
	@echo "  make rag                 Abre a Central Interativa do RAG (métricas, Llama 3 ao vivo, busca e chunks)"
	@echo "  make extrator            Abre o Menu Interativo do Agente Extrator (#17) + Benchmark + Analytics"
	@echo "  make extrator-bench      Roda o Benchmark Zero-Hint do Extrator no Golden Benchmark (30 questões)"
	@echo "  make extrator-analytics  Exibe o painel Analytics de latência, tokens e recall por disciplina/idade"
	@echo "  make docs                Sobe o portal de documentação MkDocs em http://$(HOST):$(DOCS_PORT)"
	@echo "  make setup               Sincroniza dependências Python (uv) e Node.js (npm) + base RAG"
	@echo "  make db-up               Sobe o banco vetorial PostgreSQL + pgvector via Docker"
	@echo "  make db-down             Para o container do banco vetorial pgvector"
	@echo "=========================================================================================="

# Verifica ambiente, instala o que faltar e sobe Backend + Frontend Next.js juntos
up:
	@IRIS_HOST=$(HOST) IRIS_PORT=$(PORT) FRONT_PORT=$(FRONT_PORT) LLM_MODEL=$(LLM_MODEL) ./scripts/start_all.sh

# Sobe Backend e abre Playground RAG / API Web
dev:
	@echo "Iniciando Backend e abrindo Painel Web em http://$(HOST):$(PORT) ..."
	@(sleep 1 && open "http://$(HOST):$(PORT)" >/dev/null 2>&1 || true) &
	@$(MAKE) backend

# Sobe o Frontend Next.js (porta 3000) garantindo dependências instaladas
front:
	@echo "Verificando e iniciando Frontend Next.js em http://localhost:$(FRONT_PORT) ..."
	@cd frontend && ( \
		if [ ! -d node_modules ] || [ package.json -nt node_modules ] || [ package-lock.json -nt node_modules ]; then \
			npm install && touch node_modules; \
		fi && \
		PORT=$(FRONT_PORT) npx next dev -p $(FRONT_PORT) \
	)

# Central Interativa do RAG (Menu limpo: métricas, Llama 3 ao vivo, perguntas livres e chunks)
rag:
	@./rag/setup_rag.sh --menu

# Central Interativa do Agente Extrator Curricular (Issue #17)
extrator:
	@$(PYTHON_RUN) scripts/test_curriculum_extractor_cli.py --menu --model $(LLM_MODEL)

extractor: extrator

extrator-bench:
	@$(PYTHON_RUN) scripts/test_curriculum_extractor_cli.py --benchmark --model $(LLM_MODEL)

extrator-analytics:
	@$(PYTHON_RUN) scripts/test_curriculum_extractor_cli.py --analytics

# Smoke-check completo de ambiente, API, PII, RAG e Extrator
check:
	@$(PYTHON_RUN) scripts/smoke_check.py

# Execução de testes automatizados
test:
	@$(PYTHON_RUN) -m unittest discover -s backend/tests -v

# Documentação MkDocs
docs:
	@if $(PYTHON_BIN) -m mkdocs --version >/dev/null 2>&1; then \
		$(PYTHON_BIN) -m mkdocs serve -a $(HOST):$(DOCS_PORT); \
	elif command -v uv >/dev/null 2>&1; then \
		uv run --group docs mkdocs serve -a $(HOST):$(DOCS_PORT); \
	else \
		mkdocs serve -a $(HOST):$(DOCS_PORT); \
	fi

# Banco Vetorial pgvector via Docker
db-up:
	docker compose up -d pgvector

db-down:
	docker compose stop pgvector

# Setup e sincronização de dependências (Python + Node.js + RAG)
setup:
	@if command -v uv >/dev/null 2>&1; then uv sync --all-groups; fi
	@if command -v npm >/dev/null 2>&1; then cd frontend && npm install; fi
	@./rag/setup_rag.sh --padrao

# Servidor Backend individual
backend:
	@if $(PYTHON_BIN) -c "import uvicorn, fastapi" >/dev/null 2>&1; then \
		$(PYTHON_RUN) -m uvicorn iris.main:app --app-dir $(CURDIR)/backend/src --host $(HOST) --port $(PORT) --reload; \
	elif command -v uv >/dev/null 2>&1 && uv run python -c "import uvicorn, fastapi" >/dev/null 2>&1; then \
		PYTHONPATH=$(PYTHONPATH) uv run uvicorn iris.main:app --app-dir $(CURDIR)/backend/src --host $(HOST) --port $(PORT) --reload; \
	else \
		IRIS_HOST=$(HOST) IRIS_PORT=$(PORT) $(PYTHON_RUN) -m iris.main; \
	fi
