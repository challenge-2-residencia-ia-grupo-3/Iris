#!/usr/bin/env bash
set -euo pipefail

# Diretórios absolutos
RAG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${RAG_DIR}/.." && pwd)"
PACOTE_DIR="${RAG_DIR}/iris-rag/pacote"
SRC_DIR="${REPO_ROOT}/src"
MODEL="${IRIS_LLM_MODEL:-${RAG_LLM_MODELO:-llama3.1:8b}}"

# Detecta o executor Python
if command -v uv >/dev/null 2>&1 && uv run python -c "import sys" >/dev/null 2>&1; then
    PY_CMD="PYTHONPATH=${SRC_DIR} uv run python"
elif [ -x "${REPO_ROOT}/.venv/bin/python" ] && "${REPO_ROOT}/.venv/bin/python" -c "import sys" >/dev/null 2>&1; then
    PY_CMD="PYTHONPATH=${SRC_DIR} ${REPO_ROOT}/.venv/bin/python"
else
    PY_CMD="PYTHONPATH=${SRC_DIR} python3"
fi

criar_chunks() {
    echo "================================================================================"
    echo "  [ETAPA: CRIAR / RECRIAR BASE DO RAG] Segmentando documentos em chunks.jsonl"
    echo "================================================================================"
    cd "${PACOTE_DIR}"
    eval "${PY_CMD} ingestao.py"
    TOTAL_CHUNKS=$(wc -l < "${PACOTE_DIR}/chunks.jsonl" | tr -d ' ')
    echo "  -> Base criada com sucesso: ${TOTAL_CHUNKS} trechos indexáveis em chunks.jsonl."
}

indexar_pgvector() {
    echo "================================================================================"
    echo "  [ETAPA: INDEXAR PGVECTOR] Subindo container e gerando embeddings vetoriais"
    echo "================================================================================"
    cd "${REPO_ROOT}"
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        docker compose up -d pgvector
        sleep 2
        cd "${PACOTE_DIR}"
        eval "${PY_CMD} indexar.py"
    else
        echo "  [AVISO] Docker não está ativo no momento. O RAG usará automaticamente"
        echo "          o índice local BM25 sobre os 1.385 chunks sem precisar de container."
    fi
}

mostrar_metricas_e_textos_gravados() {
    LIMITE="${1:-3}"
    GERADOR="${2:-haiku}"
    cd "${REPO_ROOT}"
    eval "${PY_CMD} -m iris.eval.rag_metrics --gerador ${GERADOR} --ver-textos --limite ${LIMITE}"
}

rodar_rag_ao_vivo_com_metricas_e_textos() {
    LIMITE="${1:-3}"
    METODO="${2:-bm25}"
    cd "${REPO_ROOT}"
    RAG_LLM="${RAG_LLM:-ollama}" RAG_LLM_MODELO="${MODEL}" \
        eval "${PY_CMD} -m iris.eval.rag_metrics --ao-vivo --ver-textos --metodo ${METODO} --limite ${LIMITE}"
}

comparar_metodos_busca() {
    PERGUNTA="${1:-Aluno esquece o enunciado no meio da questão de várias etapas: o que fazer sem dar a resposta?}"
    cd "${REPO_ROOT}"
    eval "${PY_CMD} -m iris.eval.rag_metrics"
    echo ""
    echo "================================================================================"
    echo "  COMPARATIVO DE TRECHOS RECUPERADOS E TEXTOS PARA A CONSULTA:"
    echo "  \"${PERGUNTA}\""
    echo "================================================================================"
    eval "${PY_CMD} -c '
from iris.rag.bridge import buscar_evidencias
pergunta = \"\"\"${PERGUNTA}\"\"\"
trechos = buscar_evidencias(pergunta, metodo=\"bm25\", k=5, sinonimos=True)
for i, t in enumerate(trechos, 1):
    print(f\"\n[T{i}] {t.get(\\\"chunk_id\\\")} | Doc: {t.get(\\\"doc\\\")} | p. {t.get(\\\"pagina\\\") or \\\"-\\\"} | Score: {t.get(\\\"score\\\", 0):.3f}\")
    print(f\"     Título: {t.get(\\\"titulo\\\", \\\"\\\")[:90]}\")
    txt = \" \".join(t.get(\"trecho\", \"\").split())
    print(f\"     Texto : {txt[:420]}...\")
'"
}

garantir_chunks_silencioso() {
    if [ ! -f "${PACOTE_DIR}/chunks.jsonl" ]; then
        cd "${PACOTE_DIR}"
        eval "${PY_CMD} ingestao.py >/dev/null"
    fi
}

menu_interativo() {
    while true; do
        echo ""
        echo "================================================================================"
        echo "  CENTRAL DE OPERAÇÕES DO RAG & MÉTRICAS — PROJETO ÍRIS"
        echo "================================================================================"
        echo "  1) Ver Painel Contextualizado das 12 Métricas + Textos e Respostas (7 consultas)"
        echo "  2) Rodar o RAG AO VIVO (LLM Local: ${MODEL}) + Ver Métricas e Textos dos Trechos"
        echo "  3) Fazer uma Pergunta Livre ao RAG Ao Vivo (vendo Métricas + Textos [T1..T5])"
        echo "  4) Recriar Base de Chunks do RAG (ingestao.py -> 1.385 trechos)"
        echo "  5) Indexar Banco Vetorial Denso no Docker (pgvector + indexar.py)"
        echo "  6) Comparar Geradores Registrados (Claude Haiku vs. Claude Opus) nas 12 Métricas"
        echo "  0) Sair"
        echo "================================================================================"
        read -r -p "Escolha uma opção [0-6]: " OPCAO
        case "${OPCAO}" in
            1)
                mostrar_metricas_e_textos_gravados 7 haiku
                ;;
            2)
                rodar_rag_ao_vivo_com_metricas_e_textos 3 bm25
                ;;
            3)
                read -r -p "Digite a pergunta docente: " PERG_USER
                comparar_metodos_busca "${PERG_USER}"
                ;;
            4)
                criar_chunks
                ;;
            5)
                indexar_pgvector
                ;;
            6)
                cd "${REPO_ROOT}"
                eval "${PY_CMD} -m iris.eval.rag_metrics --gerador haiku"
                echo ""
                eval "${PY_CMD} -m iris.eval.rag_metrics --gerador opus"
                ;;
            0|"")
                echo "Encerrando Central do RAG."
                break
                ;;
            *)
                echo "Opção inválida."
                ;;
        esac
    done
}

# Tratamento de flags de linha de comando
MODO="${1:---padrao}"
garantir_chunks_silencioso

case "${MODO}" in
    --criar)
        criar_chunks
        ;;
    --indexar)
        criar_chunks
        indexar_pgvector
        ;;
    --metricas)
        cd "${REPO_ROOT}"
        eval "${PY_CMD} -m iris.eval.rag_metrics"
        ;;
    --rodar|--ver-textos)
        mostrar_metricas_e_textos_gravados "${2:-7}" "${3:-haiku}"
        ;;
    --ao-vivo)
        rodar_rag_ao_vivo_com_metricas_e_textos "${2:-3}" "${3:-bm25}"
        ;;
    --menu)
        mostrar_metricas_e_textos_gravados 2 haiku
        menu_interativo
        ;;
    --padrao|*)
        echo "================================================================================"
        echo "  Íris RAG - Bootstrap + Métricas Contextualizadas + Demonstração de Textos"
        echo "================================================================================"
        TOTAL_CHUNKS=$(wc -l < "${PACOTE_DIR}/chunks.jsonl" | tr -d ' ')
        echo "  • Base de conhecimento pronta: ${TOTAL_CHUNKS} chunks indexados."
        echo ""
        mostrar_metricas_e_textos_gravados 2 haiku
        ;;
esac
