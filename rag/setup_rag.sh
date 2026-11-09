#!/usr/bin/env bash
set -euo pipefail

# Diretórios absolutos
RAG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${RAG_DIR}/.." && pwd)"
PACOTE_DIR="${RAG_DIR}/iris-rag/pacote"
SRC_DIR="${REPO_ROOT}/src"

# Detecta automaticamente se já existe um modelo llama3 baixado no Ollama
DETECTED_MODEL=""
if command -v ollama >/dev/null 2>&1; then
    if ollama list 2>/dev/null | awk '{print $1}' | grep -Eq "^llama3(:latest)?$"; then
        DETECTED_MODEL="llama3:latest"
    elif ollama list 2>/dev/null | awk '{print $1}' | grep -Eq "^llama3\.1"; then
        DETECTED_MODEL="llama3.1:8b"
    fi
fi
MODEL="${LLM_MODEL:-${IRIS_LLM_MODEL:-${RAG_LLM_MODELO:-${DETECTED_MODEL:-llama3:latest}}}}"

# Detecta o executor Python
if command -v uv >/dev/null 2>&1 && uv run python -c "import sys" >/dev/null 2>&1; then
    PY_CMD="PYTHONPATH=${SRC_DIR} uv run python"
elif [ -x "${REPO_ROOT}/.venv/bin/python" ] && "${REPO_ROOT}/.venv/bin/python" -c "import sys" >/dev/null 2>&1; then
    PY_CMD="PYTHONPATH=${SRC_DIR} ${REPO_ROOT}/.venv/bin/python"
else
    PY_CMD="PYTHONPATH=${SRC_DIR} python3"
fi

garantir_chunks_silencioso() {
    if [ ! -f "${PACOTE_DIR}/chunks.jsonl" ]; then
        cd "${PACOTE_DIR}"
        eval "${PY_CMD} ingestao.py >/dev/null"
    fi
}

criar_chunks() {
    echo ""
    echo "================================================================================"
    echo "  [CRIAR BASE DE CHUNKS] Segmentando documentos da base em chunks.jsonl..."
    echo "================================================================================"
    cd "${PACOTE_DIR}"
    eval "${PY_CMD} ingestao.py"
    TOTAL_CHUNKS=$(wc -l < "${PACOTE_DIR}/chunks.jsonl" | tr -d ' ')
    echo "  -> Concluído: ${TOTAL_CHUNKS} trechos prontos em chunks.jsonl."
}

indexar_pgvector() {
    echo ""
    echo "================================================================================"
    echo "  [INDEXAR PGVECTOR] Gerando embeddings vetoriais no PostgreSQL + pgvector..."
    echo "================================================================================"
    cd "${REPO_ROOT}"
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        docker compose up -d pgvector
        sleep 2
        cd "${PACOTE_DIR}"
        eval "${PY_CMD} indexar.py"
    else
        echo "  [AVISO] Docker não está ativo no momento."
        echo "          O RAG opera normalmente usando o índice local BM25 (1.385 trechos)."
    fi
}

mostrar_tabela_metricas() {
    GERADOR="${1:-haiku}"
    echo ""
    cd "${REPO_ROOT}"
    eval "${PY_CMD} -m iris.eval.rag_metrics --gerador ${GERADOR}"
}

mostrar_metricas_e_textos_gravados() {
    LIMITE="${1:-3}"
    GERADOR="${2:-haiku}"
    echo ""
    cd "${REPO_ROOT}"
    eval "${PY_CMD} -m iris.eval.rag_metrics --gerador ${GERADOR} --ver-textos --limite ${LIMITE}"
}

rodar_rag_ao_vivo() {
    LIMITE="${1:-1}"
    METODO="${2:-bm25}"
    echo ""
    echo "================================================================================"
    echo "  EXECUTANDO RAG AO VIVO NO LLM LOCAL (${MODEL})"
    echo "================================================================================"
    cd "${REPO_ROOT}"
    RAG_LLM="${RAG_LLM:-ollama}" RAG_LLM_MODELO="${MODEL}" \
        eval "${PY_CMD} -m iris.eval.rag_metrics --ao-vivo --ver-textos --metodo ${METODO} --limite ${LIMITE}"
}

responder_pergunta_livre_ao_vivo() {
    echo ""
    read -r -p "Digite sua pergunta pedagógica sobre TDAH: " PERGUNTA
    if [ -z "${PERGUNTA}" ]; then
        echo "Nenhuma pergunta informada. Retornando ao menu."
        return
    fi
    echo ""
    echo "================================================================================"
    echo "  CONSULTA AO VIVO COM LLAMA 3 NO TERMINAL"
    echo "  Pergunta: \"${PERGUNTA}\""
    echo "================================================================================"
    cd "${REPO_ROOT}"
    RAG_LLM=ollama RAG_LLM_MODELO="${MODEL}" eval "${PY_CMD} -c '
from iris.rag.bridge import responder_fundamentado
import json

pergunta = \"\"\"${PERGUNTA}\"\"\"
res = responder_fundamentado(pergunta, metodo=\"bm25\", k=5)
fontes = res.get(\"fontes\", [])
conf = res.get(\"conferencia\", {})
citados = conf.get(\"trechos_citados\", [])

print(f\"\n[RESPOSTA GERADA PELO LLAMA 3 ({res.get(\"llm\", \"local\")} - {res.get(\"segundos_total\", 0):.2f}s)]:\")
print(res[\"resposta\"])
print(\"\n[AUDITORIA DE CITAÇÕES E FONTES]:\")
print(f\"  • Trechos citados no texto : {citados}\")
print(f\"  • Citações inválidas       : {len(conf.get(\"citacoes_invalidas\", []))}\")
print(f\"  • Frases sem citação       : {len(conf.get(\"frases_sem_citacao\", []))}\")
print(\"\n[TRECHOS CIENTÍFICOS/NORMATIVOS RECUPERADOS (TOP-5)]:\")
for i, t in enumerate(fontes, 1):
    pag = f\", p. {t[\"pagina\"]}\" if t.get(\"pagina\") else \"\"
    marca = \" [CITADO PELO LLAMA 3]\" if i in citados else \"\"
    print(f\"  • [T{i}] {t.get(\"chunk_id\")} | {t.get(\"titulo\", \"\")[:75]}{pag}{marca}\")
    txt = \" \".join(t.get(\"trecho\", \"\").split())
    print(f\"    {txt[:260]}...\")
'"
}

menu_interativo() {
    while true; do
        echo ""
        echo "================================================================================"
        echo "  ÍRIS RAG — CENTRAL DE OPERAÇÕES & AUDITORIA"
        echo "================================================================================"
        echo "  1) Ver Painel das 12 Métricas (Tabela 1 Íris + Tabela 2 RAGAS)"
        echo "  2) Rodar RAG AO VIVO no Llama 3 (gera resposta em tempo real + trechos [T1..T5])"
        echo "  3) Fazer uma Pergunta Livre ao Llama 3 (você digita a pergunta no terminal)"
        echo "  4) Inspecionar Consultas Gravadas e Textos Completos dos Trechos [T1..T5]"
        echo "  5) Recriar Base de Chunks do RAG (1.385 trechos a partir dos 9 documentos)"
        echo "  6) Indexar Banco Vetorial Denso no Docker (pgvector + indexar.py)"
        echo "  7) Comparar Geradores Registrados (Claude Haiku vs. Claude Opus)"
        echo "  0) Sair"
        echo "================================================================================"
        read -r -p "Escolha uma opção [0-7]: " OPCAO
        case "${OPCAO}" in
            1)
                mostrar_tabela_metricas haiku
                ;;
            2)
                rodar_rag_ao_vivo 1 bm25
                ;;
            3)
                responder_pergunta_livre_ao_vivo
                ;;
            4)
                mostrar_metricas_e_textos_gravados 3 haiku
                ;;
            5)
                criar_chunks
                ;;
            6)
                indexar_pgvector
                ;;
            7)
                mostrar_tabela_metricas haiku
                echo ""
                mostrar_tabela_metricas opus
                ;;
            0|"")
                echo "Encerrando Central do RAG."
                break
                ;;
            *)
                echo "Opção inválida. Digite um número de 0 a 7."
                ;;
        esac
    done
}

# Tratamento de flags
MODO="${1:---menu}"
garantir_chunks_silencioso

case "${MODO}" in
    --menu)
        menu_interativo
        ;;
    --criar)
        criar_chunks
        ;;
    --indexar)
        criar_chunks
        indexar_pgvector
        ;;
    --metricas)
        mostrar_tabela_metricas "${2:-haiku}"
        ;;
    --rodar|--ver-textos)
        mostrar_metricas_e_textos_gravados "${2:-3}" "${3:-haiku}"
        ;;
    --ao-vivo)
        rodar_rag_ao_vivo "${2:-1}" "${3:-bm25}"
        ;;
    --padrao)
        TOTAL_CHUNKS=$(wc -l < "${PACOTE_DIR}/chunks.jsonl" | tr -d ' ')
        echo "Base de conhecimento RAG pronta: ${TOTAL_CHUNKS} chunks indexados."
        ;;
    *)
        menu_interativo
        ;;
esac
