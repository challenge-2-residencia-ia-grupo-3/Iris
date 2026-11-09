#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST="${IRIS_HOST:-127.0.0.1}"
PORT="${IRIS_PORT:-8000}"
MODEL="${IRIS_LLM_MODEL:-${RAG_LLM_MODELO:-llama3.1:8b}}"
OLLAMA_HOST_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"

cd "${REPO_ROOT}"

echo "================================================================================"
echo "  ÍRIS — INICIALIZAÇÃO COMPLETA DA PLATAFORMA (RAG + OLLAMA + BACKEND + FRONTEND)"
echo "================================================================================"

# 1. Dependências e Base de Conhecimento do RAG (chunks.jsonl + Métricas Iniciais)
echo "[1/4] Verificando base de conhecimento do RAG e calculando métricas iniciais..."
"${REPO_ROOT}/rag/setup_rag.sh" --padrao

# 2. Banco Vetorial Opcional (Docker pgvector)
echo ""
echo "[2/4] Verificando banco vetorial (Docker pgvector)..."
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "      -> Docker ativo! Subindo container iris-pgvector na porta 5433..."
    docker compose up -d pgvector || true
else
    echo "      -> Docker desligado ou não utilizado. Buscador operando em modo local BM25 (1.385 chunks)."
fi

# 3. LLM Local via Ollama
echo ""
echo "[3/4] Inicializando LLM Local via Ollama (${MODEL})..."
if command -v ollama >/dev/null 2>&1; then
    if ! curl -sSf "${OLLAMA_HOST_URL}/api/tags" >/dev/null 2>&1; then
        echo "      -> Subindo daemon 'ollama serve' em background..."
        nohup ollama serve >/tmp/iris_ollama.log 2>&1 &
        sleep 2
    fi
    if curl -sSf "${OLLAMA_HOST_URL}/api/tags" >/dev/null 2>&1; then
        echo "      -> Ollama ONLINE em ${OLLAMA_HOST_URL}!"
        if ollama list | awk '{print $1}' | grep -Fxq "${MODEL}"; then
            echo "      -> Modelo '${MODEL}' pronto para uso!"
        else
            echo "      -> Baixando modelo '${MODEL}' em segundo plano (ou aguarde conclusão)..."
            ollama pull "${MODEL}" || echo "      -> [AVISO] Prosseguindo com fallback até o download concluir."
        fi
    else
        echo "      -> [AVISO] Ollama não respondeu em ${OLLAMA_HOST_URL}. Usando fallback extrativo local."
    fi
else
    echo "      -> [AVISO] Binário 'ollama' não encontrado. Usando fallback extrativo local."
fi

# 4. Subir Backend + Frontend Web e abrir no navegador
echo ""
echo "[4/4] Subindo Backend API + Frontend Web Completo em http://${HOST}:${PORT} ..."
(sleep 1.5 && open "http://${HOST}:${PORT}" >/dev/null 2>&1 || true) &

if command -v uv >/dev/null 2>&1 && uv run python -c "import uvicorn, fastapi" >/dev/null 2>&1; then
    IRIS_LLM_PROVIDER=ollama IRIS_LLM_MODEL="${MODEL}" PYTHONPATH="${REPO_ROOT}/src" \
        uv run uvicorn iris.main:app --host "${HOST}" --port "${PORT}" --reload
else
    IRIS_LLM_PROVIDER=ollama IRIS_LLM_MODEL="${MODEL}" IRIS_HOST="${HOST}" IRIS_PORT="${PORT}" \
        PYTHONPATH="${REPO_ROOT}/src" python3 -m iris.main
fi
