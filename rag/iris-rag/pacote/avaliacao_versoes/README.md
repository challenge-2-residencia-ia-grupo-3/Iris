# Avaliação: o RAG antigo contra o novo

Protocolo do relatório de 09/11/2026 (40 consultas, gabarito de trechos), acrescido de 25 perguntas fora da base e
das métricas do RAGAS. Roteiro: [`../comparar_versoes.py`](../comparar_versoes.py). Resultado: [`../outputs/40-comparacao-versoes.txt`](../outputs/40-comparacao-versoes.txt).

| Versão | Quem escreve a resposta | Instrução |
|---|---|---|
| antigo | Llama 3.1 8B local (Ollama) | prompt de antes (`RAG_PROMPT_ESCLARECIMENTO=off`) |
| novo | Claude Haiku 5.5, esforço baixo (API da Anthropic) | prompt com pedido de esclarecimento e recusa mais firme |

A busca é a mesma para as duas versões (`qwen3+rerank50`, 5 trechos) e é feita uma vez.

## Arquivos desta pasta

| Arquivo | Conteúdo |
|---|---|
| `busca_ids.jsonl` | por pergunta: o texto, se tem resposta na base, o gabarito e os 5 `chunk_id` entregues |
| `respostas_antigo.jsonl`, `respostas_novo.jsonl` | a resposta de cada versão, o modelo, a conferência mecânica (recusa, citações) e o tempo |
| `ragas_antigo.jsonl`, `ragas_novo.jsonl` | as notas do RAGAS por pergunta (Faithfulness, AnswerRelevancy) e o juiz usado |
| `custo.json` | tokens e dólares do juiz do RAGAS em cada rodada |

O texto dos trechos não é versionado (parte da base não tem licença de distribuição): fica em `../cache/comparar_versoes/`.

## Como reproduzir

Três níveis, do mais barato ao mais caro. Todos a partir de `rag/iris-rag/pacote/`.

**1. Conferir os números a partir dos arquivos guardados** (sem modelo, sem chave, sem a base local; resultado idêntico ao versionado):

```bash
.venv/bin/python comparar_versoes.py relatorio
```

**2. Julgar de novo com o RAGAS** (precisa de `ANTHROPIC_API_KEY`, do pacote `anthropic` com `uv add anthropic`, e da base local para o texto dos trechos; cerca de US$ 0,05 por pergunta com o Sonnet 5.5):

```bash
.venv/bin/python comparar_versoes.py ragas antigo
.venv/bin/python comparar_versoes.py ragas novo
.venv/bin/python comparar_versoes.py relatorio
```

**3. Gerar as respostas de novo** (precisa também do Ollama com `llama3.1:8b` e do banco com a base; apague os arquivos `respostas_*.jsonl` e `ragas_*.jsonl` antes):

```bash
.venv/bin/python comparar_versoes.py gerar antigo
.venv/bin/python comparar_versoes.py gerar novo
```

Nos níveis 2 e 3 os números saem próximos, não idênticos: os modelos não são determinísticos. A diferença esperada fica
dentro dos intervalos de confiança que o relatório imprime.

## Variáveis

| Variável | Padrão | Para quê |
|---|---|---|
| `IRIS_RAGAS_JUIZ` | `claude-sonnet-5-5` | modelo juiz do RAGAS (o mesmo juiz do benchmark do grupo) |
| `IRIS_RAGAS_EMBEDDINGS` | `Qwen/Qwen3-Embedding-0.6B` | vetores locais da AnswerRelevancy |
| `IRIS_RAGAS_TETO_DOLAR` | `8` | o roteiro para se o custo do juiz passar disso |

## Ressalvas

- O juiz é um modelo, sem conferência por pessoa; o gabarito de trechos também foi feito por modelo (relatório de 09/11).
- A segmentação mudou depois de 09/11: 121 dos 139 trechos certos do gabarito existem na base de hoje. O recall@5 desta rodada não é o mesmo número do relatório.
- O RAGAS dá nota 0 a uma recusa (ela não afirma nada). Por isso o relatório mostra as notas com todas as respostas e só onde as duas versões responderam, e conta a recusa à parte.
- O RAGAS pede resposta estruturada por ferramenta forçada, que os modelos Claude 5 recusam; o roteiro usa o modo de JSON da Anthropic no Instructor.
