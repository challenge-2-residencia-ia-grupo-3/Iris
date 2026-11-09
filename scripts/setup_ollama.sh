#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-${IRIS_LLM_MODEL:-llama3.1:8b}}"
OLLAMA_HOST_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"

echo "============================================================"
echo "  Íris - Setup do LLM Local via Ollama (História 4.2.3 / #43)"
echo "============================================================"
echo "  Modelo alvo : ${MODEL}"
echo "  Endpoint    : ${OLLAMA_HOST_URL}"
echo ""

if ! command -v ollama >/dev/null 2>&1; then
    echo "[ERRO] O binário 'ollama' não foi encontrado no PATH."
    echo "       No macOS, instale com: brew install ollama"
    exit 1
fi

echo "[1/4] Verificando se o servidor Ollama está ativo em ${OLLAMA_HOST_URL}..."
if ! curl -sSf "${OLLAMA_HOST_URL}/api/tags" >/dev/null 2>&1; then
    echo "      -> Servidor não detectado. Iniciando 'ollama serve' em segundo plano..."
    nohup ollama serve >/tmp/iris_ollama.log 2>&1 &
    sleep 3
fi

if curl -sSf "${OLLAMA_HOST_URL}/api/tags" >/dev/null 2>&1; then
    echo "      -> Servidor Ollama online!"
else
    echo "[ERRO] Não foi possível conectar ao Ollama em ${OLLAMA_HOST_URL}."
    echo "       Abra o aplicativo Ollama ou rode 'ollama serve' em outro terminal."
    exit 1
fi

echo ""
echo "[2/4] Verificando disponibilidade do modelo '${MODEL}'..."
if ollama list | awk '{print $1}' | grep -Fxq "${MODEL}"; then
    echo "      -> Modelo '${MODEL}' já está baixado localmente."
else
    echo "      -> Baixando modelo '${MODEL}' (isso pode levar alguns minutos na 1ª vez)..."
    ollama pull "${MODEL}"
fi

echo ""
echo "[3/4] Garantindo que os chunks locais do RAG estejam gerados..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
"${REPO_ROOT}/rag/setup_rag.sh" >/dev/null

echo ""
echo "[4/4] Testando o RAG ao vivo com o LLM local (${MODEL})..."
cd "${REPO_ROOT}"
RAG_LLM=ollama RAG_LLM_MODELO="${MODEL}" PYTHONPATH="${REPO_ROOT}/src" python3 -c "
from iris.rag.bridge import responder_fundamentado
res = responder_fundamentado(
    'Aluno esquece o enunciado no meio da questão de várias etapas: o que fazer sem dar a resposta?',
    metodo='bm25',
    k=3,
)
print('Pergunta :', res['pergunta'])
print('LLM usado:', res['llm'])
print('Tempo    :', res['segundos_total'], 's')
print('Resposta :\n' + res['resposta'])
print('Conferência de citações:', res['conferencia'])
"

echo ""
echo "============================================================"
echo "  LLM Local pronto! Comandos para uso no projeto:"
echo "============================================================"
echo "  • Rodar demonstração ao vivo do RAG:"
echo "    RAG_LLM=ollama RAG_LLM_MODELO=${MODEL} uv run python rag/iris-rag/pacote/demonstrar_resposta.py --ao-vivo"
echo ""
echo "  • Calcular todas as métricas do RAG (modo gravado + diagnóstico):"
echo "    PYTHONPATH=src python3 -m iris.eval.rag_metrics"
echo ""
echo "  • Calcular todas as métricas do RAG gerando respostas ao vivo no Ollama:"
echo "    RAG_LLM=ollama RAG_LLM_MODELO=${MODEL} PYTHONPATH=src python3 -m iris.eval.rag_metrics --ao-vivo --limite 5"
echo "============================================================"
