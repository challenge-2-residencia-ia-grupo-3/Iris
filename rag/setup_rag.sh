#!/usr/bin/env bash
set -euo pipefail

# Diretório base do script (pasta rag/)
RAG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACOTE_DIR="${RAG_DIR}/iris-rag/pacote"

echo "============================================================"
echo "  Íris RAG - Bootstrap de Ambiente Local (Engenharia/IA)"
echo "============================================================"

cd "${PACOTE_DIR}"

# Detecta o executor Python (prioriza uv se disponível e permitido, senão python3)
if command -v uv >/dev/null 2>&1 && uv run python -c "import sys" >/dev/null 2>&1; then
    PY_CMD="uv run python"
    echo "[1/3] Ambiente detectado: uv (${PY_CMD})"
elif [ -x "${RAG_DIR}/../.venv/bin/python" ] && "${RAG_DIR}/../.venv/bin/python" -c "import sys" >/dev/null 2>&1; then
    PY_CMD="${RAG_DIR}/../.venv/bin/python"
    echo "[1/3] Ambiente detectado: virtualenv local (${PY_CMD})"
else
    PY_CMD="python3"
    echo "[1/3] Ambiente detectado: Python do sistema (${PY_CMD})"
fi

echo ""
echo "[2/3] Gerando base de trechos (chunks.jsonl) a partir dos documentos disponíveis..."
${PY_CMD} ingestao.py >/dev/null

if [ -f "${PACOTE_DIR}/chunks.jsonl" ]; then
    TOTAL_CHUNKS=$(wc -l < "${PACOTE_DIR}/chunks.jsonl" | tr -d ' ')
    echo "      -> Sucesso: chunks.jsonl gerado com ${TOTAL_CHUNKS} trechos."
else
    echo "      -> Erro: falha ao gerar chunks.jsonl."
    exit 1
fi

echo ""
echo "[3/3] Executando smoke test de busca e demonstração..."
${PY_CMD} -c "
import consultar, demonstrar_resposta
res = consultar.buscar('aluno esquece enunciado longo com várias etapas', metodo='bm25', k=3)
assert len(res) == 3, 'Falha na busca BM25'
itens = demonstrar_resposta.demonstrar(todas=False, ao_vivo=False, caminho=None)
assert len(itens) == 7, 'Falha na demonstração de respostas'
print(f'      -> Smoke test OK: {len(res)} trechos recuperados na busca rápida e {len(itens)} consultas validadas.')
"

echo ""
echo "============================================================"
echo "  Ambiente pronto! Comandos úteis para testar:"
echo "============================================================"
echo "  1. Ver demonstração das 7 consultas principais:"
echo "     cd rag/iris-rag/pacote && ${PY_CMD} demonstrar_resposta.py"
echo ""
echo "  2. Ver todas as 40 consultas avaliadas:"
echo "     cd rag/iris-rag/pacote && ${PY_CMD} demonstrar_resposta.py --todas"
echo ""
echo "  3. Testar geração ao vivo com LLM (Groq ou Ollama):"
echo "     export GROQ_API_KEY=\"sua_chave\""
echo "     cd rag/iris-rag/pacote && ${PY_CMD} demonstrar_resposta.py --ao-vivo"
echo "============================================================"

