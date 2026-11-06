# Íris – Base de conhecimento e protótipo de RAG

Base de conhecimento curada e protótipo de geração aumentada por recuperação (RAG) do Íris, sistema que adapta material didático para estudantes neurodivergentes. O protótipo recebe uma consulta, recupera os trechos mais relevantes da base, gera uma resposta restrita ao conteúdo recuperado e indica a fonte de cada frase.

Entrega do Segundo Desafio (Challenge 2) da Residência em IA, Turma 1 – Grupo 3 – 09/11/2026.

## Conteúdo do pacote

```
rag/
├── README.md                     este arquivo
├── iris-rag/
│   ├── FONTES.md, fontes*.json   catálogo da base: origem, hash, licença, qualidade da extração
│   ├── texto/                    texto extraído dos documentos distribuídos
│   ├── textos_nao_distribuidos.txt   textos de licença restrita, não incluídos
│   ├── scripts/                  extração de texto por formato de origem
│   ├── gabarito/                 conjunto de avaliação: consultas e trechos de referência
│   └── pacote/                   código-fonte, cadernos executados e saídas
└── outputs/                      saídas dos scripts de avaliação
docs/rag/
├── relatorio.md                  relatório técnico
├── arquitetura.md                documentação de arquitetura (modelo arc42)
├── avaliacao.md                  protocolo e resultados da avaliação
├── diagrama_arquitetura.svg      diagrama de arquitetura
└── figuras/                      figuras da avaliação
```

O relatório técnico é entregue em PDF (`relatorio.pdf`), separadamente. A versão em Markdown, de mesmo conteúdo, está em `docs/rag/relatorio.md`.

## Itens do entregável

| Item | Artefato |
|---|---|
| Base de conhecimento curada (mínimo de 20 documentos) | `rag/iris-rag/FONTES.md`, `rag/iris-rag/fontes.json`, `rag/iris-rag/texto/` |
| Estratégia de segmentação (chunking) | `docs/rag/arquitetura.md`, seção 8.1; `rag/iris-rag/pacote/ingestao.py` |
| Estratégia de embeddings | `docs/rag/arquitetura.md`, seção 8.2; `rag/iris-rag/pacote/embeddings.py` |
| Banco vetorial | `rag/iris-rag/pacote/banco_pg.py` |
| Consulta e recuperação dos trechos | `rag/iris-rag/pacote/consultar.py`; caderno `02_consulta_resposta_fonte.ipynb` |
| Resposta fundamentada e evidência das fontes | `rag/iris-rag/pacote/gerar.py`, `demonstrar_resposta.py`; `rag/iris-rag/pacote/outputs/05-consulta-resposta-fonte.txt` |
| Diagrama de arquitetura | `docs/rag/diagrama_arquitetura.svg` |
| Pipeline de ingestão | `docs/rag/arquitetura.md`, seção 6.1; `rag/iris-rag/scripts/`, `rag/iris-rag/pacote/ingestao.py` |
| Avaliação | `docs/rag/avaliacao.md`; `rag/outputs/` |

## Requisitos

- Python 3.11
- Docker, para o PostgreSQL 17 com a extensão pgvector
- Aproximadamente 3 GB de espaço em disco para os modelos, obtidos do Hugging Face na primeira execução
- GPU opcional; a execução em CPU é suportada, com tempo de vetorização superior

## Instalação

Os comandos são executados a partir de `rag/iris-rag/pacote/`.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

docker run -d --name iris-pgvector \
  -e POSTGRES_USER=iris -e POSTGRES_PASSWORD=iris -e POSTGRES_DB=iris \
  -p 127.0.0.1:5433:5432 pgvector/pgvector:pg17
```

As credenciais acima destinam-se exclusivamente ao ambiente local de desenvolvimento.

## Execução

| Etapa | Comando | Resultado |
|---|---|---|
| Ingestão | `python ingestao.py` | `chunks.jsonl`; `rag/outputs/01-chunking.txt` |
| Vetorização e carga no banco | `python banco_pg.py` | tabela `iris_trechos` com trechos, metadados e vetores |
| Demonstração da recuperação | `python consultar.py` | `rag/outputs/03-demonstracao.txt` |
| Demonstração completa, com respostas registradas | `python demonstrar_resposta.py` | `rag/outputs/05-consulta-resposta-fonte.txt` |
| Demonstração completa, com geração pelo modelo configurado | `python demonstrar_resposta.py --ao-vivo` | `rag/outputs/05-consulta-resposta-fonte-ao-vivo.txt` |
| Avaliação da recuperação | `python avaliar_opus.py` | `rag/outputs/16-gabarito-opus.txt` |
| Avaliação do método adotado e de variações | `python medir_variacoes.py ranquear` e `python medir_variacoes.py medir` | `../../outputs/18-variacoes-busca.txt` |

Os cadernos `01_rag_iris.ipynb` e `02_consulta_resposta_fonte.ipynb` são entregues executados e podem ser abertos sem reexecução.

### Condições para a reexecução

A ingestão requer os textos de todos os documentos do índice. Seis documentos do índice têm licença restrita e não são distribuídos (lista em `rag/iris-rag/textos_nao_distribuidos.txt`). Sem esses textos, a ingestão é interrompida com a indicação do arquivo ausente, e as etapas seguintes não são executáveis; os cadernos executados e os arquivos de saída permitem a inspeção dos resultados sem reexecução.

Com os textos nos caminhos indicados, a reexecução foi verificada em 06/11/2026, em diretório extraído deste pacote, fora do repositório de origem, com o banco `RAG_BANCO=chroma`:

| Etapa | Resultado da verificação |
|---|---|
| `python ingestao.py` | Arquivo de trechos idêntico ao original (1.368 trechos; hash SHA-256 igual ao campo `chunking_congelado` de `rag/iris-rag/gabarito/gabarito_rascunho_v0.json`) |
| `python indexar.py` | Vetores recalculados para os 1.368 trechos |
| `python avaliar_opus.py` | Recall@5, recall@10 e MRR iguais aos de `rag/outputs/16-gabarito-opus.txt`, com variação de 0,01 em um limite de intervalo e em uma métrica secundária |
| `python medir_variacoes.py ranquear` e `medir` | Recall@5, intervalos e diferenças pareadas iguais aos de `rag/outputs/18-variacoes-busca.txt` |
| `python demonstrar_resposta.py` | Saída igual à distribuída, exceto as linhas de identificação do banco e de comparação da recuperação |

Tempos de execução dependem do equipamento. Colunas de diagnóstico que dependem do índice aproximado do Chroma ou de dados intermediários não distribuídos podem diferir.

Não foram verificados em instalação limpa: a criação do ambiente Python a partir de `requirements.txt`, a carga no PostgreSQL em contêiner e a reexecução dos cadernos.

A geração de respostas requer credencial do provedor do modelo gerador. A classificação pelos avaliadores automáticos requer acesso a modelo de linguagem externo e depende de dados intermediários não distribuídos; as respostas, as classificações e as passagens verificadas estão registradas em `respostas_medidas.json`, `respostas_vereditos_v2.json` e `respostas_passagens_v2.json`.

## Configuração

| Variável | Padrão | Finalidade |
|---|---|---|
| `RAG_BANCO` | `pgvector` | Banco vetorial; `chroma` seleciona a alternativa local sem contêiner |
| `RAG_PG_DSN` | `postgresql://iris:iris@127.0.0.1:5433/iris` | Conexão com o PostgreSQL |
| `RAG_METODO` | `qwen3+rerank50` | Método de recuperação |
| `RAG_RERANKER` | `mminilm` | Modelo de reordenação; `bge-m3` seleciona a alternativa de maior porte |
| `RAG_LLM` | `groq` | Provedor do modelo gerador; `ollama` seleciona execução local |
| `RAG_LLM_MODELO` | `qwen/qwen3.8-27b` | Modelo gerador |
| `GROQ_API_KEY` | – | Credencial do provedor, necessária para `--ao-vivo` com `RAG_LLM=groq` |

## Resultados

| Indicador | Resultado | Referência |
|---|---|---|
| Recall@5 do método adotado (38 consultas) | 0,42 (IC 95%: 0,32 a 0,52) | 0,28 sem reordenação; 0,004 em seleção aleatória |
| Consultas com ao menos um trecho relevante entre os cinco | 33 de 38 | 26 de 38 sem reordenação |
| Frases com citação de trecho inexistente | 0 de 211 | – |
| Frases de conteúdo sustentadas pelo trecho citado | 161 de 187 (86%) | Nenhuma classificada como não sustentada pelos dois avaliadores |

O protocolo, os resultados completos e as ameaças à validade constam em `docs/rag/avaliacao.md`.

## Limitações conhecidas

- O conjunto de referência da recuperação e os avaliadores das respostas são modelos de linguagem; não houve validação humana.
- As respostas registradas foram geradas por modelos Claude com as instruções do protótipo. O modelo configurado no protótipo (Qwen, via Groq) não foi avaliado, e o modelo gerador do produto não está definido.
- O desempenho é inferior em consultas de prática docente (recall@5 de 0,26).
- O tempo de resposta da reordenação em servidor sem GPU não foi medido para 50 candidatos.

## Licenciamento e restrições de uso

Os documentos da base mantêm a licença de origem, registrada em `rag/iris-rag/FONTES.md`. Dos 38 documentos do índice, o pacote distribui o texto de 32:

| Situação da licença | Documentos |
|---|---|
| Licença Creative Commons | 18 |
| Texto legal ou ato oficial em domínio público | 7 |
| Permissão de reprodução declarada pela fonte | 3 |
| Publicado por órgão governamental, sem licença declarada | 4 |

Os quatro documentos sem licença declarada são a Política Nacional de Educação Especial de 2008, a Nota Técnica MEC/SECADI nº 04/2014, o Protocolo Clínico e Diretrizes Terapêuticas do TDAH e a página do CDC sobre TDAH em sala de aula. A redistribuição desses textos em repositório público deve ser avaliada previamente.

Oito textos não são distribuídos, por direitos reservados ou ausência de licença aberta: três versões das diretrizes do CAST, as diretrizes NICE NG87 e AAP 2019, o guia da ABDA, um artigo de revisão e o Caderno 4 do MEC. O arquivo de trechos (`chunks.jsonl`) também não é distribuído, por conter esses textos; ele é gerado pela ingestão.

Nas cópias de entrega dos cadernos executados e dos arquivos de saída, passagens desses documentos foram substituídas pela indicação `[texto não reproduzido por restrição de licença]`, e identificadores do ambiente de execução (nome de máquina e caminho de diretório) foram omitidos. As demais informações dessas saídas não foram alteradas. O catálogo e as respostas registradas mantêm citações breves, com indicação da fonte.

A base contém somente documentos públicos. Nenhum dado de estudante é armazenado ou processado.
