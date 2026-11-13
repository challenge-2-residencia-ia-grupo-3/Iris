# Mapa do código do Íris

`mapa_codigo.py` lê o clone do repositório do grupo (só leitura) e produz o mapa do código
como dado para o painel: módulos, funções, quem importa e chama quem, que testes cobrem cada
módulo e em que pé está cada etapa do pipeline. Usa só a biblioteca padrão (`ast`, `re`,
`json`); não instala nada, não usa rede e não grava nada no clone.

## Como gerar

```bash
cd challenges/challenge-02-qualidade-de-vida/iris-rag/pacote
nice -n 19 python3 ../bancada/mapa/mapa_codigo.py --repo ../../.. --saida outputs
python3 -m json.tool outputs/27-mapa-codigo.json > /dev/null   # valida o JSON
```

Alvo proposto para o `pacote/Makefile` (não adicionado):

```make
mapa:
	nice -n 19 python3 ../bancada/mapa/mapa_codigo.py --repo $(GRUPO) --saida outputs
```

O mapa vale para o commit em que o clone estiver (`git rev-parse HEAD`), registrado em
`commit_grupo`. Rodar de novo no mesmo commit dá o mesmo arquivo, exceto `gerado_em`
(conferido com três `PYTHONHASHSEED` diferentes).

## O que sai

| Arquivo | Conteúdo |
|---|---|
| `27-mapa-codigo.json` | `modulos` (funções, classes, `importa`, `importado_por`, `testado_por`, `usa_llm`), `arestas` (`import` e `chamada`), `etapas_pipeline`, `sem_teste`, `metricas` |
| `27-mapa-codigo.txt` | resumo: módulos por pasta, mais importados, quem usa LLM, sem teste, etapas com evidência, ciclos de import |
| `27-mapa-codigo.mmd` | dois `flowchart LR`: dependências entre pastas (rótulo = nº de arestas) e etapas coloridas por status |

Escopo: `backend/src/iris` (id `iris.*`), `rag/iris-rag/pacote` (id `rag_pacote.*`, porque o
pacote é importado por nome curto via `sys.path`) e `frontend/src` (id `frontend.*`).

## Como cada campo é obtido

- **importa**: `import`/`from ... import` em qualquer ponto do arquivo, inclusive dentro de
  função; blocos `if TYPE_CHECKING:` são ignorados (só valem para o verificador de tipo).
  Imports de `__init__` que reexportam contam como aresta para o `__init__`.
- **chamada** (aresta entre módulos): nome importado de módulo interno e chamado
  (`f()`, `Classe()`, `modulo.f()`, `Classe.metodo()`), seguindo reexportações de `__init__`
  até o módulo que define o símbolo. O frontend ganha aresta `chamada` para a rota do
  backend quando faz `fetch` para um caminho registrado num `APIRouter`.
- **testado_por**: arquivos `backend/tests/**/test_*.py` que importam o módulo (direto ou via
  reexportação) ou citam o caminho em string, como em `patch("iris.x.y.f")`.
- **usa_llm**: importa `HybridLLMClient`, `get_llm_client`, o módulo `iris.core.llm_client`
  ou um SDK externo de LLM.
- **etapas_pipeline**: sequência lida em `README.md`, `docs/arquitetura.md`,
  `docs/roteiro_testes.md` e `docs/backlog_rastreabilidade.md`. Para cada etapa, o script
  confere se a função existe no código (`ast`) e se ela é alcançável, pelo grafo de chamadas,
  a partir de `iris.main` ou `iris.api.routes.*`.
  - `implementada`: todas as funções existem e a API chega nelas.
  - `parcial`: existe código, mas parte dele não é chamada por nenhuma rota (só por teste ou
    script), ou falta uma peça descrita na arquitetura (o auditor exige um símbolo
    `Auditor`/`max_retries`).
  - `ausente`: nenhuma função da etapa existe.
  - A etapa de métricas não exige estar na API: avaliação roda offline por natureza.

## Limites da análise estática

1. **Aproximada.** Não executa nada. Chamadas por variável, `getattr`, injeção
   (`self.llm_client.generate`), `importlib` e callbacks não aparecem; métodos chamados em
   objetos de outra classe também não. Há falsos negativos; falso positivo é raro.
2. **"Testado" quer dizer "importado por um teste"**, não cobertura de linha. Um teste que
   importa o módulo e testa uma função só conta para o módulo todo.
3. **Status de etapa é sobre o código, não sobre a qualidade.** `implementada` diz que há
   caminho da API até a função; não diz que o resultado está certo.
4. **Etapas e status de issue vêm dos documentos do grupo** (lista fixa em `ETAPAS`). Se a
   arquitetura mudar, a lista precisa ser editada.
5. **TypeScript por regex**: só imports relativos/`@/`, funções `function` e `const ... =>`
   de topo e `fetch` com template literal. Sem classes, sem resolução de tipo.
6. **Arquivo que o Python 3.11 não lê** (no commit 65e1f09, `eval/isolamento_escopo.py`
   usa f-string com barra invertida, sintaxe do 3.12) cai para um esqueleto por regex:
   imports, funções e classes, sem docstring e sem chamadas. O `.txt` lista esses casos.
7. **Scripts fora do pacote** (`scripts/` na raiz) não viram módulos; aparecem só na evidência
   das etapas como consumidores ("só via scripts/...").
