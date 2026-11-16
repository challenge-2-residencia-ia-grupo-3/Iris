.PHONY: qualidade qualidade-painel help up setup install dev front rag extrator extractor extrator-bench extrator-analytics check test db-up db-down docs backend ensure-uv ensure-env

SHELL := /bin/bash
export PATH := $(shell echo "$$HOME/.local/bin:$$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$$PATH")

HOST ?= 127.0.0.1
PORT ?= 8000
FRONT_PORT ?= 3000
DOCS_PORT ?= 8001
LLM_MODEL ?= llama3:latest
PYTHONPATH := $(CURDIR)/backend/src:$(CURDIR)/rag/iris-rag/pacote
VENV_PY := $(CURDIR)/.venv/bin/python3

# Resolve o binário Python em tempo de execução (após ensure-env criar o .venv se necessário)
PYTHON_RUN = PYTHONPATH="$(PYTHONPATH)" $$(if [ -x "$(VENV_PY)" ]; then echo "$(VENV_PY)"; else echo "python3"; fi)

help:
	@echo "=========================================================================================="
	@echo "  Íris — Comandos Essenciais do Projeto (Makefile)"
	@echo "=========================================================================================="
	@echo "  make setup (ou install)  Instala tudo que faltar (uv, .venv, npm, RAG, Ollama) e pula o que já existe"
	@echo "  make up                  Verifica/instala tudo (pulando o que já existe) e sobe Backend + Frontend"
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
	@echo "  make db-up               Sobe o banco vetorial PostgreSQL + pgvector via Docker"
	@echo "  make db-down             Para o container do banco vetorial pgvector"
	@echo "  make qualidade           Roda as verificações de qualidade sem modelo e gera o painel (rag/iris-rag/bancada)"
	@echo "  make qualidade-painel    Abre o painel de qualidade em http://127.0.0.1:8777 com botões para cada verificação"
	@echo "=========================================================================================="

# Garante que o uv está instalado no sistema (pula se já existir)
ensure-uv:
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "==> [INSTALANDO] 'uv' não encontrado. Instalando automaticamente (https://astral.sh/uv)..."; \
		if command -v curl >/dev/null 2>&1; then \
			curl -LsSf https://astral.sh/uv/install.sh | sh; \
		elif command -v wget >/dev/null 2>&1; then \
			wget -qO- https://astral.sh/uv/install.sh | sh; \
		elif command -v brew >/dev/null 2>&1; then \
			brew install uv; \
		else \
			python3 -m pip install --user uv || pip install uv; \
		fi; \
	fi

# Garante silenciosamente que uv + .venv + chunks.jsonl existem antes de qualquer comando avulso
ensure-env:
	@./scripts/start_all.sh --quick-env

# Verifica ambiente completo, instala o que faltar (pulando o que já existe) e sobe Backend + Frontend Next.js juntos
up:
	@IRIS_HOST=$(HOST) IRIS_PORT=$(PORT) FRONT_PORT=$(FRONT_PORT) LLM_MODEL=$(LLM_MODEL) ./scripts/start_all.sh

# Instala/configura tudo que um novo integrante precisa após clonar o repositório (pula etapas já instaladas)
setup:
	@IRIS_HOST=$(HOST) IRIS_PORT=$(PORT) FRONT_PORT=$(FRONT_PORT) LLM_MODEL=$(LLM_MODEL) ./scripts/start_all.sh --setup-only

install: setup

# Sobe Backend e abre Playground RAG / API Web
dev: ensure-env
	@echo "Iniciando Backend e abrindo Painel Web em http://$(HOST):$(PORT) ..."
	@(sleep 1 && open "http://$(HOST):$(PORT)" >/dev/null 2>&1 || true) &
	@$(MAKE) backend

# Sobe o Frontend Next.js (porta 3000) garantindo dependências instaladas (pula npm install se já existir)
front:
	@echo "Verificando e iniciando Frontend Next.js em http://localhost:$(FRONT_PORT) ..."
	@cd frontend && ( \
		if [ ! -d node_modules ] || [ package.json -nt node_modules ] || [ package-lock.json -nt node_modules ]; then \
			echo "      -> [INSTALANDO] Executando npm install..." && npm install && touch node_modules; \
		else \
			echo "      -> [OK] frontend/node_modules já instalado — pulando npm install."; \
		fi && \
		PORT=$(FRONT_PORT) npx next dev -p $(FRONT_PORT) \
	)

# Central Interativa do RAG (Menu limpo: métricas, Llama 3 ao vivo, perguntas livres e chunks)
rag: ensure-env
	@./rag/setup_rag.sh --menu

# Central Interativa do Agente Extrator Curricular (Issue #17)
extrator: ensure-env
	@$(PYTHON_RUN) scripts/test_curriculum_extractor_cli.py --menu --model $(LLM_MODEL)

extractor: extrator

extrator-bench: ensure-env
	@$(PYTHON_RUN) scripts/test_curriculum_extractor_cli.py --benchmark --model $(LLM_MODEL)

extrator-analytics: ensure-env
	@$(PYTHON_RUN) scripts/test_curriculum_extractor_cli.py --analytics

# Smoke-check completo de ambiente, API, PII, RAG e Extrator
check: ensure-env
	@$(PYTHON_RUN) scripts/smoke_check.py

# Execução de testes automatizados
test: ensure-env
	@$(PYTHON_RUN) -m unittest discover -s backend/tests -v

# Documentação MkDocs
docs: ensure-env
	@if $(PYTHON_RUN) -m mkdocs --version >/dev/null 2>&1; then \
		$(PYTHON_RUN) -m mkdocs serve -a $(HOST):$(DOCS_PORT); \
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

# Servidor Backend individual
backend: ensure-env
	@if $(PYTHON_RUN) -c "import uvicorn, fastapi" >/dev/null 2>&1; then \
		$(PYTHON_RUN) -m uvicorn iris.main:app --app-dir $(CURDIR)/backend/src --host $(HOST) --port $(PORT) --reload; \
	elif command -v uv >/dev/null 2>&1 && uv run python -c "import uvicorn, fastapi" >/dev/null 2>&1; then \
		PYTHONPATH=$(PYTHONPATH) uv run uvicorn iris.main:app --app-dir $(CURDIR)/backend/src --host $(HOST) --port $(PORT) --reload; \
	else \
		IRIS_HOST=$(HOST) IRIS_PORT=$(PORT) $(PYTHON_RUN) -m iris.main; \
	fi

# Painel de qualidade (rag/iris-rag/bancada/README.md): verificações sem modelo e painel local em 127.0.0.1
qualidade: ensure-env
	@$(MAKE) -C rag/iris-rag/pacote verificar PYB="$(VENV_PY)" PY="$(VENV_PY)" GRUPO="$(CURDIR)"

qualidade-painel: ensure-env
	@$(MAKE) -C rag/iris-rag/pacote painel PYB="$(VENV_PY)" PY="$(VENV_PY)" GRUPO="$(CURDIR)"
