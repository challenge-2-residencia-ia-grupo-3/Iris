.PHONY: help setup backend frontend dev docs ollama rag-demo rag-live metrics metrics-live readability test db-up db-down

HOST ?= 127.0.0.1
PORT ?= 8000
DOCS_PORT ?= 8001
LLM_MODEL ?= llama3.1:8b
PYTHONPATH := $(CURDIR)/src

# Detecta automaticamente se o uv está funcional ou usa python3 com PYTHONPATH
PYTHON_RUN = PYTHONPATH=$(PYTHONPATH) python3

help:
	@echo "================================================================================"
	@echo "  Íris — Comandos do Makefile (Backend, Frontend, RAG, LLM Local e Métricas)"
	@echo "================================================================================"
	@echo "  make dev           Sobe Backend API + Frontend Web Interativo em http://$(HOST):$(PORT)"
	@echo "  make backend       Sobe o servidor Backend (FastAPI / Uvicorn ou HTTP nativo)"
	@echo "  make frontend      Abre o Frontend Web Interativo no navegador (http://$(HOST):$(PORT))"
	@echo "  make docs          Sobe o portal de documentação MkDocs em http://$(HOST):$(DOCS_PORT)"
	@echo "  make setup         Sincroniza dependências (uv) e gera os 1.385 chunks do RAG"
	@echo "  make ollama        Inicia o Ollama nativo, baixa $(LLM_MODEL) e testa o RAG ao vivo"
	@echo "  make rag-demo      Executa a demonstração reproduzível do RAG (7 consultas)"
	@echo "  make rag-live      Executa o RAG ao vivo gerando respostas no LLM local ($(LLM_MODEL))"
	@echo "  make metrics       Calcula as 12 métricas do RAG (Relatório Íris + 7 Métricas RAGAS)"
	@echo "  make metrics-live  Calcula as 12 métricas do RAG gerando respostas ao vivo no LLM"
	@echo "  make readability   Calcula o baseline Flesch PT-BR do Golden Benchmark (30 questões)"
	@echo "  make test          Executa toda a bateria de 26 testes automatizados"
	@echo "  make db-up         Sobe o banco vetorial PostgreSQL + pgvector via Docker"
	@echo "  make db-down       Para o container do banco vetorial pgvector"
	@echo "================================================================================"

setup:
	@if command -v uv >/dev/null 2>&1; then uv sync --all-groups; fi
	@./rag/setup_rag.sh

backend:
	@if command -v uv >/dev/null 2>&1 && uv run python -c "import uvicorn, fastapi" >/dev/null 2>&1; then \
		PYTHONPATH=$(PYTHONPATH) uv run uvicorn iris.main:app --host $(HOST) --port $(PORT) --reload; \
	else \
		IRIS_HOST=$(HOST) IRIS_PORT=$(PORT) $(PYTHON_RUN) -m iris.main; \
	fi

frontend:
	@echo "Abrindo Frontend Web do Íris em http://$(HOST):$(PORT) ..."
	@(sleep 1 && open "http://$(HOST):$(PORT)" >/dev/null 2>&1 || true) &
	@$(MAKE) backend

dev: frontend

docs:
	@if command -v uv >/dev/null 2>&1; then \
		uv run --group docs mkdocs serve -a $(HOST):$(DOCS_PORT); \
	else \
		mkdocs serve -a $(HOST):$(DOCS_PORT); \
	fi

ollama:
	@./scripts/setup_ollama.sh $(LLM_MODEL)

rag-demo:
	@cd rag/iris-rag/pacote && $(PYTHON_RUN) demonstrar_resposta.py

rag-live:
	@cd rag/iris-rag/pacote && RAG_LLM=ollama RAG_LLM_MODELO=$(LLM_MODEL) $(PYTHON_RUN) demonstrar_resposta.py --ao-vivo

metrics:
	@$(PYTHON_RUN) -m iris.eval.rag_metrics

metrics-live:
	@RAG_LLM=ollama RAG_LLM_MODELO=$(LLM_MODEL) $(PYTHON_RUN) -m iris.eval.rag_metrics --ao-vivo --limite 5

readability:
	@$(PYTHON_RUN) -m iris.eval.readability data/golden_benchmark.json

test:
	@$(PYTHON_RUN) -m unittest discover -s tests -v

db-up:
	docker compose up -d pgvector

db-down:
	docker compose stop pgvector
