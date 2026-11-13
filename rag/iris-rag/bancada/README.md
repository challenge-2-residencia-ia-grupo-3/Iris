# Painel de qualidade do Íris

Um painel no navegador que roda verificações no código deste repositório e mostra onde ele quebra: o pipeline
inteiro etapa por etapa, o filtro de dados pessoais sob ataque, a prova fixa de 166 questões dos benchmarks do grupo,
o orçamento de tempo do RNF-07 e o mapa do código. **Nada sai da sua máquina:** as verificações rodam sem modelo
(provedor `eco`, determinístico), sem chave de API e sem envio de dados. O painel liga só em `127.0.0.1`.

## Rodar (3 passos)

Pré-requisito: o ambiente do projeto (`make setup` na raiz, que você provavelmente já rodou).

```bash
make setup
make qualidade
make qualidade-painel
```

- `make qualidade` roda as verificações (de 5 a 15 minutos, sem GPU) e gera `rag/iris-rag/pacote/reports/bancada.html`.
- `make qualidade-painel` abre o painel em http://127.0.0.1:8777, com um botão para cada verificação e a saída ao vivo.

### Windows sem `make`

No PowerShell, na raiz do repositório:

```powershell
cd rag\iris-rag\pacote
..\..\..\.venv\Scripts\python.exe ..\bancada\local\servidor.py --pyb ..\..\..\.venv\Scripts\python.exe
```

Abra http://127.0.0.1:8777 e clique em cada verificação. O servidor descobre sozinho onde está o código do grupo.

## O que cada verificação responde

| Comando | Pergunta | Saída |
|---|---|---|
| `rastro-pipeline` | O material passa por todas as etapas, do upload à adaptação? Quanto tempo cada uma leva? | `26-rastro-pipeline-resumo.json` |
| `adversarial` | Dado pessoal, injeção de prompt e arquivo estranho: o que passa? | `24-adversarial.txt` |
| `ablacao` | Tirando cada peça, o resultado no Golden Benchmark piora? | `25-ablacao.txt` |
| `ataque` | 1.916 variações sintéticas de dado pessoal e clínico contra o filtro real: o que vaza? | `35-ataque.json` |
| `avaliacao` | A prova fixa (166 questões, lacrada por hash): este commit piorou algo? | `32-avaliacao.json` |
| `orcamento-so` | Cada etapa cabe no tempo do RNF-07? | `36-orcamento.json` |
| `producao` | O registro proposto para produção guarda só metadados, sem texto do aluno? | `37-producao.json` |
| `mapa`, `etapas` | Quais módulos existem, o que cada etapa faz, com exemplo real | `27-*.json`, `31-etapas.json` |
| `portoes` | Lê as saídas acima e diz aprovado, aviso ou reprovado (código 1 se reprovar) | terminal |

Os dados de teste são sintéticos: CPF com dígito verificador errado, DDD 00, e-mails em `@exemplo.test`.

## O que não vem neste repositório

- **Texto de documentos sem licença aberta.** O painel pode mostrar trechos da base; por isso `pacote/reports/` está no
  `.gitignore`. Gere o painel na sua máquina e não o publique.
- **Abas que dependem de modelo** (juízes, RAG com LLM, LLM x RAG): aparecem vazias até alguém rodar as avaliações
  com modelo e gravar as saídas em `pacote/outputs/`.

## Se algo der errado

| Mensagem | O que fazer |
|---|---|
| `No module named ...` | Rode `make setup` na raiz: o `.venv` do projeto já traz tudo (pydantic, pymupdf, python-docx, rank-bm25). |
| `falta chunks.jsonl` | `make setup` monta a base de trechos. |
| aba **PRs e issues** vazia | Precisa do GitHub CLI logado (só leitura): `brew install gh` (Mac) ou `winget install GitHub.cli` (Windows), depois `gh auth login` e `make qualidade` de novo. |
| aba **Arquitetura com LangGraph** vazia | Rode `make setup` (instala o `langgraph`) e `make qualidade` de novo. A primeira vez busca os PRs #74, #80 e #81 do GitHub (só leitura). |
| **Commits e portões** sem quadradinhos verdes | Normal na sua máquina: o veredito por commit vem de uma verificação automática que roda num servidor. O resultado do seu código está na Visão geral e nas abas de Qualidade. |
| porta 8777 ocupada | `make qualidade-painel PORTA=8778` |
| demora demais | Rode uma verificação por vez pelo painel; `ataque` e `ablacao` são as mais longas. |
