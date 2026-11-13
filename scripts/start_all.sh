#!/usr/bin/env bash
set -euo pipefail

export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"

# Carrega nvm automaticamente caso node não esteja no PATH padrão
if ! command -v node >/dev/null 2>&1; then
    export NVM_DIR="${HOME}/.nvm"
    if [ -s "${NVM_DIR}/nvm.sh" ]; then
        # shellcheck disable=SC1090
        . "${NVM_DIR}/nvm.sh" >/dev/null 2>&1 || true
    fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST="${IRIS_HOST:-127.0.0.1}"
PORT="${IRIS_PORT:-8000}"
FRONT_PORT="${FRONT_PORT:-3000}"
FRONTEND_PID=""

PREFLIGHT_ONLY=0
QUICK_ENV=0
for arg in "$@"; do
    case "${arg}" in
        --preflight-only|--setup-only)
            PREFLIGHT_ONLY=1
            ;;
        --quick-env)
            QUICK_ENV=1
            PREFLIGHT_ONLY=1
            ;;
    esac
done

cleanup() {
    if [ -n "${FRONTEND_PID}" ] && kill -0 "${FRONTEND_PID}" >/dev/null 2>&1; then
        echo ""
        echo "Encerrando Frontend Next.js (PID ${FRONTEND_PID})..."
        kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
        wait "${FRONTEND_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

garantir_uv() {
    if command -v uv >/dev/null 2>&1; then
        if [ "${QUICK_ENV}" -eq 0 ]; then
            echo "      -> [OK] 'uv' já instalado ($(uv --version)) — pulando instalação."
        fi
        return 0
    fi

    echo "      -> [INSTALANDO] 'uv' não encontrado no sistema. Instalando automaticamente..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    elif command -v brew >/dev/null 2>&1; then
        brew install uv
    elif command -v python3 >/dev/null 2>&1; then
        python3 -m pip install --user uv || python3 -m pip install uv
    elif command -v pip >/dev/null 2>&1; then
        pip install uv
    else
        echo "      -> [ERRO] Não foi possível instalar o 'uv' automaticamente (curl/wget/brew/pip ausentes)."
        echo "      -> Instale manualmente: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
    if ! command -v uv >/dev/null 2>&1; then
        echo "      -> [ERRO] Falha ao localizar 'uv' após tentativa de instalação."
        exit 1
    fi
    echo "      -> [OK] 'uv' instalado com sucesso: $(uv --version)"
}

garantir_node() {
    if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
        echo "      -> [OK] Node.js $(node -v) e npm $(npm -v) já instalados — pulando instalação do Node."
        return 0
    fi

    echo "      -> [INSTALANDO] Node.js/npm não encontrados. Tentando instalar automaticamente..."
    if command -v brew >/dev/null 2>&1; then
        brew install node || true
    elif command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" -eq 0 ]; then
        apt-get update && apt-get install -y nodejs npm || true
    fi

    if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
        echo "      -> [OK] Node.js $(node -v) e npm $(npm -v) instalados com sucesso!"
        return 0
    fi
    return 1
}

garantir_ollama() {
    if command -v ollama >/dev/null 2>&1; then
        echo "      -> [OK] Binário 'ollama' já instalado — pulando instalação."
        return 0
    fi

    echo "      -> [INSTALANDO] 'ollama' não encontrado. Tentando instalar automaticamente..."
    if command -v brew >/dev/null 2>&1; then
        brew install ollama || true
    elif [ "$(uname -s)" = "Linux" ] && command -v curl >/dev/null 2>&1; then
        curl -fsSL https://ollama.com/install.sh | sh || true
    fi

    if command -v ollama >/dev/null 2>&1; then
        echo "      -> [OK] 'ollama' instalado com sucesso!"
        return 0
    fi
    return 1
}

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

if [ "${QUICK_ENV}" -eq 0 ]; then
    echo "================================================================================"
    echo "  ÍRIS — VERIFICAÇÃO E INICIALIZAÇÃO COMPLETA (PREFLIGHT + BACKEND + FRONTEND)"
    echo "================================================================================"
    echo "[1/5] Verificando ambiente Python (uv + .venv + dependências Backend/RAG/Docs)..."
fi

# 1. Dependências Python (uv + .venv + pacotes de todos os grupos)
garantir_uv
SYNC_STAMP="${REPO_ROOT}/.venv/.all_groups_synced"
if [ ! -x "${REPO_ROOT}/.venv/bin/python3" ]; then
    echo "      -> [INSTALANDO] .venv não encontrado. Executando 'uv sync --all-groups'..."
    if uv sync --all-groups; then
        touch "${SYNC_STAMP}"
    else
        echo "      -> [AVISO] 'uv sync --all-groups' falhou; tentando 'uv sync' mínimo..."
        uv sync
    fi
fi

PYTHON_BIN="${REPO_ROOT}/.venv/bin/python3"
if [ ! -x "${PYTHON_BIN}" ]; then
    PYTHON_BIN="python3"
fi

export PYTHONPATH="${REPO_ROOT}/backend/src:${REPO_ROOT}/rag/iris-rag/pacote"

DEPS_PRECISAM_SYNC=0
if ! "${PYTHON_BIN}" -c "import fastapi, uvicorn, pydantic, pymupdf, docx, rank_bm25" >/dev/null 2>&1; then
    DEPS_PRECISAM_SYNC=1
elif [ "${IRIS_SKIP_RAG_DEPS:-0}" != "1" ] && ! "${PYTHON_BIN}" -c "import torch, sentence_transformers, psycopg, pgvector" >/dev/null 2>&1; then
    DEPS_PRECISAM_SYNC=1
elif [ ! -f "${SYNC_STAMP}" ] || [ "${REPO_ROOT}/pyproject.toml" -nt "${SYNC_STAMP}" ] || [ "${REPO_ROOT}/uv.lock" -nt "${SYNC_STAMP}" ]; then
    DEPS_PRECISAM_SYNC=1
fi

if [ "${DEPS_PRECISAM_SYNC}" -eq 1 ] && command -v uv >/dev/null 2>&1; then
    echo "      -> [INSTALANDO] Dependências Python ausentes ou desatualizadas. Rodando 'uv sync --all-groups'..."
    if uv sync --all-groups; then
        touch "${SYNC_STAMP}"
        echo "      -> [OK] Ambiente Python + grupo RAG sincronizados."
    else
        echo "      -> [AVISO] Falha em 'uv sync --all-groups'; tentando 'uv sync' básico..."
        uv sync || true
    fi
elif [ "${QUICK_ENV}" -eq 0 ]; then
    if "${PYTHON_BIN}" -c "import fastapi, uvicorn, pydantic, pymupdf, docx, rank_bm25, torch, sentence_transformers, psycopg, pgvector" >/dev/null 2>&1; then
        echo "      -> [OK] Ambiente .venv e dependências Python (Backend + RAG) já instalados — pulando etapa."
    else
        echo "      -> [OK] Dependências críticas do Backend instaladas (grupo 'rag' opcional ausente; fallback BM25 ativo)."
    fi
fi

# 2. Base de Conhecimento do RAG (chunks.jsonl) + Camada Curada Escolar
if [ "${QUICK_ENV}" -eq 0 ]; then
    echo ""
    echo "[2/5] Verificando base de conhecimento do RAG e camada curada do benchmark..."
fi
CHUNKS_FILE="${REPO_ROOT}/rag/iris-rag/pacote/chunks.jsonl"
FONTES_FILE="${REPO_ROOT}/rag/iris-rag/fontes.json"
INGESTAO_FILE="${REPO_ROOT}/rag/iris-rag/pacote/ingestao.py"
if [ ! -f "${CHUNKS_FILE}" ] || [ "${FONTES_FILE}" -nt "${CHUNKS_FILE}" ] || [ "${INGESTAO_FILE}" -nt "${CHUNKS_FILE}" ]; then
    echo "      -> [INSTALANDO] Base de trechos ausente ou desatualizada. Construindo chunks.jsonl..."
    "${REPO_ROOT}/rag/setup_rag.sh" --criar
elif [ "${QUICK_ENV}" -eq 0 ]; then
    TOTAL_CHUNKS=$(wc -l < "${CHUNKS_FILE}" | tr -d ' ')
    echo "      -> [OK] Base de conhecimento RAG já existe (${TOTAL_CHUNKS} chunks indexados) — pulando etapa."
fi

BENCH_RAW="${REPO_ROOT}/data/benchmarks/questoes_escolares_v1.json"
BENCH_CURATED="${REPO_ROOT}/data/benchmarks/questoes_escolares_curado_v1.json"
BENCH_SCRIPT="${REPO_ROOT}/backend/src/iris/eval/rag_escolar_benchmark.py"
# O gerador da camada curada (rag_escolar_benchmark.py) ainda não está no repositório: sem ele, a etapa é pulada
# em vez de interromper o preparo (set -e) em toda cópia nova.
if [ -f "${BENCH_RAW}" ] && [ ! -f "${BENCH_SCRIPT}" ]; then
    if [ "${QUICK_ENV}" -eq 0 ]; then
        echo "      -> [AVISO] backend/src/iris/eval/rag_escolar_benchmark.py ausente — camada curada do benchmark escolar não gerada."
    fi
elif [ -f "${BENCH_RAW}" ]; then
    if [ ! -f "${BENCH_CURATED}" ] || [ "${BENCH_RAW}" -nt "${BENCH_CURATED}" ] || [ "${BENCH_SCRIPT}" -nt "${BENCH_CURATED}" ]; then
        echo "      -> [INSTALANDO] Gerando camada curada do benchmark escolar..."
        "${PYTHON_BIN}" -m iris.eval.rag_escolar_benchmark --curar >/dev/null
        echo "      -> [OK] Camada curada pronta em data/benchmarks/questoes_escolares_curado_v1.json."
    elif [ "${QUICK_ENV}" -eq 0 ]; then
        echo "      -> [OK] Camada curada do benchmark escolar já atualizada — pulando etapa."
    fi
fi

if [ "${QUICK_ENV}" -eq 1 ]; then
    exit 0
fi

# 3. Banco Vetorial Opcional (Docker pgvector) + Sincronização de Vetores (qwen3)
echo ""
echo "[3/5] Verificando banco vetorial (Docker pgvector) e índice Qwen3..."
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -Fxq "iris-pgvector"; then
        echo "      -> [OK] Container iris-pgvector já está em execução na porta 5433 — pulando subida."
    else
        echo "      -> [INSTALANDO] Docker ativo! Subindo container iris-pgvector na porta 5433..."
        docker compose up -d pgvector || true
    fi
    PG_READY=0
    for _ in $(seq 1 15); do
        if "${PYTHON_BIN}" -c "import socket; s=socket.create_connection(('127.0.0.1', 5433), timeout=0.5); s.close()" >/dev/null 2>&1; then
            PG_READY=1
            break
        fi
        sleep 1
    done
    if [ "${PG_READY}" -eq 1 ] && "${PYTHON_BIN}" -c "import torch, sentence_transformers, psycopg, pgvector" >/dev/null 2>&1; then
        PG_STATUS="$("${PYTHON_BIN}" -c "
import banco_pg, ingestao
chunks = ingestao.carregar_chunks()
con = banco_pg.conectar()
existe = con.execute('SELECT to_regclass(%s)', [banco_pg.TABELA]).fetchone()[0]
if existe is None:
    print('MISSING_TABLE')
else:
    ids_pg = {r[0] for r in con.execute(f'SELECT chunk_id FROM {banco_pg.TABELA}').fetchall()}
    prontos = banco_pg.colunas_prontas(con)
    if ids_pg == {c['chunk_id'] for c in chunks} and 'qwen3' in prontos:
        print(f'SYNCED:{len(chunks)}')
    else:
        print('OUT_OF_SYNC')
" 2>/dev/null || echo "PG_ERR")"
        if [[ "${PG_STATUS}" == SYNCED:* ]]; then
            echo "      -> [OK] pgvector já sincronizado (${PG_STATUS#SYNCED:} trechos e vetores Qwen3 prontos) — pulando indexação."
        elif ls "${REPO_ROOT}/rag/iris-rag/pacote/cache"/vetores-qwen3-*.npy >/dev/null 2>&1 \
            && ! ls "${REPO_ROOT}/rag/iris-rag/pacote/cache"/vetores-qwen3-*.parcial.npy >/dev/null 2>&1; then
            echo "      -> [INSTALANDO] Cache de vetores Qwen3 encontrado. Gravando no pgvector..."
            if (cd "${REPO_ROOT}/rag/iris-rag/pacote" && "${PYTHON_BIN}" banco_pg.py qwen3); then
                echo "      -> [OK] Índice vetorial Qwen3 no pgvector atualizado com sucesso!"
            else
                echo "      -> [AVISO] Falha ao indexar vetores no pgvector; buscador seguirá com fallback BM25."
            fi
        elif pgrep -f "banco_pg.py qwen3" >/dev/null 2>&1; then
            echo "      -> [EM ANDAMENTO] Indexação vetorial Qwen3 já está rodando em segundo plano (log: /tmp/iris_pgvector_qwen3.log)."
        else
            echo "      -> [INSTALANDO] Iniciando geração de vetores Qwen3 (1083 trechos) em background (log: /tmp/iris_pgvector_qwen3.log)..."
            (cd "${REPO_ROOT}/rag/iris-rag/pacote" && nohup "${PYTHON_BIN}" banco_pg.py qwen3 >/tmp/iris_pgvector_qwen3.log 2>&1 &)
            echo "      -> [OK] Indexação Qwen3 iniciada em segundo plano (fallback BM25 ativo até concluir)."
        fi
    elif [ "${PG_READY}" -eq 0 ]; then
        echo "      -> [AVISO] pgvector não respondeu na porta 5433 a tempo. Usando fallback BM25."
    else
        echo "      -> [AVISO] Pacotes densos (torch/sentence-transformers/psycopg) ausentes. Usando fallback BM25."
    fi
else
    echo "      -> Docker desligado ou não utilizado. Buscador operando em modo local BM25."
fi

# 4. LLM Local via Ollama
echo ""
echo "[4/5] Verificando LLM Local via Ollama (${MODEL})..."
if garantir_ollama; then
    if ! curl -sSf "${OLLAMA_HOST_URL}/api/tags" >/dev/null 2>&1; then
        echo "      -> [INSTALANDO] Subindo daemon 'ollama serve' em background..."
        nohup ollama serve >/tmp/iris_ollama.log 2>&1 &
        sleep 2
    else
        echo "      -> [OK] Servidor Ollama já está online em ${OLLAMA_HOST_URL}."
    fi

    if curl -sSf "${OLLAMA_HOST_URL}/api/tags" >/dev/null 2>&1; then
        if ollama list | awk '{print $1}' | grep -Fxq "${MODEL}"; then
            echo "      -> [OK] Modelo '${MODEL}' já está baixado — pulando download."
        else
            echo "      -> [INSTALANDO] Baixando modelo '${MODEL}'..."
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
echo "[5/5] Verificando dependências do Frontend Next.js e servidores..."
FRONTEND_READY=0
if garantir_node; then
    if [ ! -d "${REPO_ROOT}/frontend/node_modules" ] \
        || [ "${REPO_ROOT}/frontend/package.json" -nt "${REPO_ROOT}/frontend/node_modules" ] \
        || [ "${REPO_ROOT}/frontend/package-lock.json" -nt "${REPO_ROOT}/frontend/node_modules" ]; then
        echo "      -> [INSTALANDO] Instalando dependências do Frontend ('npm install' em frontend/)..."
        (cd "${REPO_ROOT}/frontend" && npm install)
        touch "${REPO_ROOT}/frontend/node_modules"
        echo "      -> [OK] frontend/node_modules instalado com sucesso."
    else
        echo "      -> [OK] Dependências do Frontend (frontend/node_modules) já instaladas — pulando npm install."
    fi

    if [ "${PREFLIGHT_ONLY}" -eq 1 ]; then
        echo "      -> Modo setup/preflight concluído (sem subir servidores web)."
    elif curl -sSf "http://127.0.0.1:${FRONT_PORT}" >/dev/null 2>&1; then
        echo "      -> [OK] Frontend Next.js já está respondendo na porta ${FRONT_PORT}."
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
            echo "      -> [OK] Frontend Next.js ONLINE em http://localhost:${FRONT_PORT}!"
        else
            echo "      -> [AVISO] Frontend ainda inicializando em background (veja /tmp/iris_frontend.log)."
        fi
    fi
else
    echo "      -> [AVISO] Node.js/npm não encontrados. Apenas o Backend/Playground FastAPI será iniciado."
fi

if [ "${PREFLIGHT_ONLY}" -eq 1 ]; then
    echo ""
    echo "================================================================================"
    echo "  AMBIENTE 100% PRONTO! Todos os comandos (make up, make rag, make test, etc.)"
    echo "  estão prontos para uso."
    echo "================================================================================"
    exit 0
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
