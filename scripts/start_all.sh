#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST="${IRIS_HOST:-127.0.0.1}"
PORT="${IRIS_PORT:-8000}"
FRONT_PORT="${FRONT_PORT:-3000}"
FRONTEND_PID=""

cleanup() {
    if [ -n "${FRONTEND_PID}" ] && kill -0 "${FRONTEND_PID}" >/dev/null 2>&1; then
        echo ""
        echo "Encerrando Frontend Next.js (PID ${FRONTEND_PID})..."
        kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
        wait "${FRONTEND_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# Detecta automaticamente se já existe um modelo llama3 baixado
DETECTED_MODEL=""
if command -v ollama >/dev/null 2>&1; then
    if ollama list 2>/dev/null | awk '{print $1}' | grep -Eq "^llama3(:latest)?$"; then
        DETECTED_MODEL="llama3:latest"
    elif ollama list 2>/dev/null | awk '{print $1}' | grep -Eq "^llama3\.1"; then
        DETECTED_MODEL="llama3.1:8b"
    fi
fi
MODEL="${LLM_MODEL:-${IRIS_LLM_MODEL:-${RAG_LLM_MODELO:-${DETECTED_MODEL:-llama3:latest}}}}"
OLLAMA_HOST_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"

cd "${REPO_ROOT}"

echo "================================================================================"
echo "  ÍRIS — VERIFICAÇÃO E INICIALIZAÇÃO COMPLETA (PREFLIGHT + BACKEND + FRONTEND)"
echo "================================================================================"

# 1. Dependências Python (.venv / uv)
echo "[1/5] Verificando ambiente Python e dependências do Backend..."
if [ ! -x "${REPO_ROOT}/.venv/bin/python3" ]; then
    if command -v uv >/dev/null 2>&1; then
        echo "      -> .venv não encontrado. Executando 'uv sync'..."
        uv sync
    else
        echo "      -> [ERRO] .venv não encontrado e 'uv' não está instalado."
        exit 1
    fi
fi

PYTHON_BIN="${REPO_ROOT}/.venv/bin/python3"
if [ ! -x "${PYTHON_BIN}" ]; then
    PYTHON_BIN="python3"
fi

if "${PYTHON_BIN}" -c "import fastapi, uvicorn, pydantic, pymupdf, docx" >/dev/null 2>&1; then
    echo "      -> Dependências Python críticas OK (fastapi, uvicorn, pydantic, pymupdf, python-docx)."
elif command -v uv >/dev/null 2>&1; then
    echo "      -> Dependências ausentes no .venv. Sincronizando com 'uv sync'..."
    uv sync
else
    echo "      -> [AVISO] Alguma dependência Python opcional pode estar ausente."
fi

# 2. Base de Conhecimento do RAG (chunks.jsonl + Métricas Iniciais)
echo ""
echo "[2/5] Verificando base de conhecimento do RAG e métricas iniciais..."
"${REPO_ROOT}/rag/setup_rag.sh" --padrao

# 3. Banco Vetorial Opcional (Docker pgvector)
echo ""
echo "[3/5] Verificando banco vetorial (Docker pgvector)..."
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "      -> Docker ativo! Subindo container iris-pgvector na porta 5433..."
    docker compose up -d pgvector || true
else
    echo "      -> Docker desligado ou não utilizado. Buscador operando em modo local BM25."
fi

# 4. LLM Local via Ollama
echo ""
echo "[4/5] Verificando LLM Local via Ollama (${MODEL})..."
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
            echo "      -> Baixando modelo '${MODEL}'..."
            ollama pull "${MODEL}" || echo "      -> [AVISO] Prosseguindo com fallback até o download concluir."
        fi
    else
        echo "      -> [AVISO] Ollama não respondeu em ${OLLAMA_HOST_URL}. Usando fallback extrativo local."
    fi
else
    echo "      -> [AVISO] Binário 'ollama' não encontrado. Usando fallback extrativo local."
fi

# 5. Frontend Next.js (Node.js / npm install / servidor na porta 3000)
echo ""
echo "[5/5] Verificando dependências do Frontend Next.js e iniciando servidores..."
FRONTEND_READY=0
if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    echo "      -> Node $(node -v) / npm $(npm -v) detectados."
    if [ ! -d "${REPO_ROOT}/frontend/node_modules" ] \
        || [ "${REPO_ROOT}/frontend/package.json" -nt "${REPO_ROOT}/frontend/node_modules" ] \
        || [ "${REPO_ROOT}/frontend/package-lock.json" -nt "${REPO_ROOT}/frontend/node_modules" ]; then
        echo "      -> Instalando dependências do Frontend ('npm install' em frontend/)..."
        (cd "${REPO_ROOT}/frontend" && npm install)
        touch "${REPO_ROOT}/frontend/node_modules"
    else
        echo "      -> frontend/node_modules já atualizado."
    fi

    if curl -sSf "http://127.0.0.1:${FRONT_PORT}" >/dev/null 2>&1; then
        echo "      -> Frontend Next.js já está respondendo na porta ${FRONT_PORT}."
        FRONTEND_READY=1
    else
        echo "      -> Subindo Frontend Next.js em http://localhost:${FRONT_PORT} (log: /tmp/iris_frontend.log)..."
        (cd "${REPO_ROOT}/frontend" && PORT="${FRONT_PORT}" npx next dev -p "${FRONT_PORT}" >/tmp/iris_frontend.log 2>&1) &
        FRONTEND_PID=$!
        for _ in $(seq 1 25); do
            if curl -sSf "http://127.0.0.1:${FRONT_PORT}" >/dev/null 2>&1; then
                FRONTEND_READY=1
                break
            fi
            sleep 1
        done
        if [ "${FRONTEND_READY}" -eq 1 ]; then
            echo "      -> Frontend Next.js ONLINE em http://localhost:${FRONT_PORT}!"
        else
            echo "      -> [AVISO] Frontend ainda inicializando em background (veja /tmp/iris_frontend.log)."
        fi
    fi
else
    echo "      -> [AVISO] Node.js/npm não encontrados. Apenas o Backend/Playground FastAPI será iniciado."
fi

echo ""
echo "================================================================================"
echo "  SERVIÇOS PRONTOS:"
if [ "${FRONTEND_READY}" -eq 1 ] || [ -n "${FRONTEND_PID}" ]; then
    echo "  • Aplicação Web Docente (Next.js) : http://localhost:${FRONT_PORT}"
fi
echo "  • Playground RAG & API (FastAPI)  : http://${HOST}:${PORT}"
echo "  • Documentação Interativa Swagger : http://${HOST}:${PORT}/docs"
echo "  (Pressione Ctrl+C neste terminal para encerrar Backend e Frontend juntos)"
echo "================================================================================"

if [ "${FRONTEND_READY}" -eq 1 ]; then
    (sleep 1 && open "http://localhost:${FRONT_PORT}" >/dev/null 2>&1 || true) &
else
    (sleep 1.5 && open "http://${HOST}:${PORT}" >/dev/null 2>&1 || true) &
fi

export IRIS_LLM_PROVIDER=ollama
export IRIS_LLM_MODEL="${MODEL}"
export RAG_LLM=ollama
export RAG_LLM_MODELO="${MODEL}"
export PYTHONPATH="${REPO_ROOT}/backend/src:${REPO_ROOT}/rag/iris-rag/pacote"

if "${PYTHON_BIN}" -c "import uvicorn, fastapi" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m uvicorn iris.main:app --app-dir "${REPO_ROOT}/backend/src" --host "${HOST}" --port "${PORT}" --reload
elif command -v uv >/dev/null 2>&1 && uv run python -c "import uvicorn, fastapi" >/dev/null 2>&1; then
    uv run uvicorn iris.main:app --app-dir "${REPO_ROOT}/backend/src" --host "${HOST}" --port "${PORT}" --reload
else
    IRIS_HOST="${HOST}" IRIS_PORT="${PORT}" "${PYTHON_BIN}" -m iris.main
fi
