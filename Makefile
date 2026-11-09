.PHONY: help up dev rag test db-up db-down docs setup backend

HOST ?= 127.0.0.1
PORT ?= 8000
DOCS_PORT ?= 8001
LLM_MODEL ?= llama3:latest
PYTHONPATH := $(CURDIR)/src

PYTHON_RUN = PYTHONPATH=$(PYTHONPATH) python3

help:
	@echo "=========================================================================================="
	@echo "  Íris — Comandos Essenciais do Projeto (Makefile)"
	@echo "=========================================================================================="
	@echo "  make up       Sobe a aplicação completa (RAG + Ollama $(LLM_MODEL) + Backend + Web UI)"
	@echo "  make dev      Sobe o Backend API e abre o Frontend Web em http://$(HOST):$(PORT)"
	@echo "  make rag      Abre a Central Interativa do RAG (métricas, Llama 3 ao vivo, busca e chunks)"
	@echo "  make test     Executa toda a bateria de testes automatizados (26 testes)"
	@echo "  make docs     Sobe o portal de documentação MkDocs em http://$(HOST):$(DOCS_PORT)"
	@echo "  make db-up    Sobe o banco vetorial PostgreSQL + pgvector via Docker"
	@echo "  make db-down  Para o container do banco vetorial pgvector"
	@echo "=========================================================================================="

# Sobe a aplicação inteira (RAG + pgvector + Ollama + Backend + Frontend Web)
up:
	@IRIS_HOST=$(HOST) IRIS_PORT=$(PORT) LLM_MODEL=$(LLM_MODEL) ./scripts/start_all.sh

# Sobe Backend e abre Frontend Web
dev:
	@echo "Iniciando Backend e abrindo Frontend Web em http://$(HOST):$(PORT) ..."
	@(sleep 1 && open "http://$(HOST):$(PORT)" >/dev/null 2>&1 || true) &
	@$(MAKE) backend

# Central Interativa do RAG (Menu limpo: métricas, Llama 3 ao vivo, perguntas livres e chunks)
rag:
	@./rag/setup_rag.sh --menu

# Execução de testes automatizados
test:
	@$(PYTHON_RUN) -m unittest discover -s tests -v

# Documentação MkDocs
docs:
	@if command -v uv >/dev/null 2>&1; then \
		uv run --group docs mkdocs serve -a $(HOST):$(DOCS_PORT); \
	else \
		mkdocs serve -a $(HOST):$(DOCS_PORT); \
	fi

# Banco Vetorial pgvector via Docker
db-up:
	docker compose up -d pgvector

db-down:
	docker compose stop pgvector

# Setup e sincronização de dependências
setup:
	@if command -v uv >/dev/null 2>&1; then uv sync --all-groups; fi
	@./rag/setup_rag.sh --padrao

# Servidor Backend individual
backend:
	@if command -v uv >/dev/null 2>&1 && uv run python -c "import uvicorn, fastapi" >/dev/null 2>&1; then \
		PYTHONPATH=$(PYTHONPATH) uv run uvicorn iris.main:app --host $(HOST) --port $(PORT) --reload; \
	else \
		IRIS_HOST=$(HOST) IRIS_PORT=$(PORT) $(PYTHON_RUN) -m iris.main; \
	fi
