.PHONY: help up all start setup backend frontend dev docs ollama rag rag-menu rag-criar rag-indexar rag-demo rag-live metrics metrics-live readability test db-up db-down

HOST ?= 127.0.0.1
PORT ?= 8000
DOCS_PORT ?= 8001
LLM_MODEL ?= llama3.1:8b
PYTHONPATH := $(CURDIR)/src

# Detecta automaticamente se o uv está funcional ou usa python3 com PYTHONPATH
PYTHON_RUN = PYTHONPATH=$(PYTHONPATH) python3

help:
	@echo "=========================================================================================="
	@echo "  Íris — Comandos do Makefile (Aplicação Completa, RAG Contextualizado, LLM Local e Web)"
	@echo "=========================================================================================="
	@echo "  🚀 SUBIR APLICAÇÃO INTEIRA (1 COMANDO):"
	@echo "  make up            Sobe TUDO: RAG + Métricas + pgvector + Ollama ($(LLM_MODEL)) + Backend + Frontend"
	@echo "  make all           Alias para 'make up' (executa ./scripts/start_all.sh)"
	@echo ""
	@echo "  🧠 PIPELINE RAG + MÉTRICAS CONTEXTUALIZADAS + TEXTOS DOS CHUNKS (rag/setup_rag.sh):"
	@echo "  make rag-menu      Abre o MENU INTERATIVO do RAG (métricas no começo + criar/indexar/rodar + textos)"
	@echo "  make rag           Executa o fluxo padrão do RAG (métricas no começo + criar chunks + 3 textos)"
	@echo "  make rag-criar     (Re)cria a base de chunks do RAG a partir dos 9 documentos (1.385 chunks)"
	@echo "  make rag-indexar   (Re)cria os chunks e indexa os vetores no PostgreSQL + pgvector"
	@echo "  make rag-demo      Exibe as 12 métricas no começo + 7 consultas com textos completos [T1..T5]"
	@echo "  make rag-live      Exibe as 12 métricas no começo + roda o RAG AO VIVO no Ollama com textos"
	@echo "  make metrics       Exibe as 12 métricas contextualizadas (Tabela 1 Íris + Tabela 2 RAGAS)"
	@echo "  make metrics-live  Calcula as 12 métricas ao vivo no Ollama + textos completos recuperados"
	@echo ""
	@echo "  🌐 SERVIDORES E INFRAESTRUTURA INDIVIDUAL:"
	@echo "  make dev           Sobe Backend API + Frontend Web Interativo em http://$(HOST):$(PORT)"
	@echo "  make backend       Sobe apenas o servidor Backend (FastAPI / Uvicorn ou HTTP nativo)"
	@echo "  make frontend      Abre o Frontend Web Interativo no navegador (http://$(HOST):$(PORT))"
	@echo "  make ollama        Inicia apenas o Ollama nativo e baixa/testa o modelo $(LLM_MODEL)"
	@echo "  make db-up         Sobe o container PostgreSQL + pgvector via Docker"
	@echo "  make db-down       Para o container do banco vetorial pgvector"
	@echo "  make docs          Sobe o portal de documentação MkDocs em http://$(HOST):$(DOCS_PORT)"
	@echo "  make readability   Calcula o baseline Flesch PT-BR do Golden Benchmark (30 questões)"
	@echo "  make test          Executa toda a bateria de testes automatizados"
	@echo "=========================================================================================="

# Sobe a aplicação inteira (RAG + Métricas + pgvector + Ollama + Backend + Frontend Web)
up:
	@IRIS_HOST=$(HOST) IRIS_PORT=$(PORT) LLM_MODEL=$(LLM_MODEL) ./scripts/start_all.sh

all: up

start: up

setup:
	@if command -v uv >/dev/null 2>&1; then uv sync --all-groups; fi
	@./rag/setup_rag.sh --padrao

# Comandos do RAG integrados com métricas contextualizadas e visualização dos textos
rag:
	@./rag/setup_rag.sh --padrao

rag-menu:
	@./rag/setup_rag.sh --menu

rag-criar:
	@./rag/setup_rag.sh --criar

rag-indexar:
	@./rag/setup_rag.sh --indexar

rag-demo:
	@./rag/setup_rag.sh --rodar 7 haiku

rag-live:
	@LLM_MODEL=$(LLM_MODEL) ./rag/setup_rag.sh --ao-vivo 3 bm25

metrics:
	@./rag/setup_rag.sh --metricas haiku 3

metrics-live:
	@RAG_LLM=ollama RAG_LLM_MODELO=$(LLM_MODEL) $(PYTHON_RUN) -m iris.eval.rag_metrics --ao-vivo --limite 3 --ver-textos

# Servidores Web (Backend + Frontend)
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

readability:
	@$(PYTHON_RUN) -m iris.eval.readability data/golden_benchmark.json

test:
	@$(PYTHON_RUN) -m unittest discover -s tests -v

db-up:
	docker compose up -d pgvector

db-down:
	docker compose stop pgvector
