# Painel de qualidade: comparativo entre o PR 85 e o PR 87

## 1. Objetivo

Este documento registra a integração do painel de qualidade do PR 85 ("bancada") ao painel do PR 87 (playground do
backend) e serve de base para decidir, tela a tela, o que permanece. A coluna "Decisão" das tabelas 3 e 4 está em
branco de propósito: deve ser preenchida pelos responsáveis pelos dois painéis.

## 2. Escopo e origem

| Item | Referência |
|---|---|
| Painel A (PR 85) | branch `feat/painel-qualidade`, pastas `rag/iris-rag/bancada/` e `rag/iris-rag/pacote/` (gerador `bancada.py`) |
| Painel B (PR 87) | branch `feat/rag-sonnet-progress-ui`, `backend/src/iris/static/playground.html` e rotas em `backend/src/iris/main.py` |
| Integração | branch `feat/qualidade-no-playground`, criado sobre a cabeça do PR 87 (`0e0ac54`) |

## 3. Regras adotadas na integração

1. Nenhuma tela, rota ou função do PR 87 foi removida ou substituída.
2. Alterações no código do PR 87 limitam-se a acréscimos e a correções de defeito identificado e documentado.
3. As telas do PR 85 foram trazidas sem alteração de conteúdo; a única mudança no código delas é o modo de exibição
   embutido (seção 5).
4. Nenhuma verificação exige chave de API ou modelo de linguagem para abrir.

## 4. Estrutura resultante

O menu lateral do playground mantém as 7 abas do PR 87 e recebe um grupo recolhível, "Bancada do PR 85 (em
avaliação)", com as 22 abas do PR 85 nos mesmos 6 grupos do menu original. Cada aba do grupo exibe, acima da tela, a
pergunta que ela responde e a indicação da tela equivalente no PR 87, quando houver.

## 5. Método de integração do PR 85

| Elemento | Solução | Alternativa descartada |
|---|---|---|
| Código | `rag/iris-rag/bancada/` e os 9 arquivos novos de `rag/iris-rag/pacote/` copiados do PR 85; `consultar.py` e `gerar.py` mantidos na versão do PR 87 | reescrever as 22 telas no padrão visual do PR 87, o que alteraria o conteúdo e impediria a comparação direta |
| Exibição | página única gerada por `bancada.py`, servida em `/bancada/`; o playground a abre num quadro, uma aba por vez (`?embutido=1`) | uma aba única com o painel inteiro, que impede decidir tela a tela |
| Rotas | `GET /bancada/`, `GET /bancada/status.json`, `GET /api/v1/eval/bancada-pr85`, `POST /api/v1/eval/bancada-pr85/gerar`, nos dois servidores (FastAPI e biblioteca padrão) | servidor próprio do PR 85 na porta 8777, que exigiria um segundo processo |
| Comandos | a aba "Comandos" é exibida, sem execução pela página | expor a execução de `make` no backend do produto, o que abriria execução de comando por requisição |
| Tema | as telas do PR 85 mantêm o tema escuro original | conversão para o tema claro do PR 87, que altera as cores com significado (dado pessoal, atenção, erro) |

## 6. Tabela 3: telas do PR 87 e acréscimos feitos nelas

| Tela do PR 87 | Situação no PR 87 | Acréscimo na integração | Decisão |
|---|---|---|---|
| Auditoria do Benchmark | existente | linha "Pergunta desta tela" com a origem do número | |
| Benchmark Escolar (136) | existente | intervalo de confiança de 95% e linha de base por métrica; commit e hash da prova em cada rodada; métricas garantidas por construção sinalizadas; recusa de rodada sem questões; teste de recusa com 40 perguntas fora da base (intervalo de Wilson); limite do RNF-07 ao lado da latência; aviso quando gerador e juiz são o mesmo modelo; elo em que cada questão parou; repetição da rodada com comparação; portão aprovado, aviso ou reprovado com lacre da prova; variedade da busca | |
| Catálogo de Características TDAH | existente | linha "Pergunta desta tela" | |
| Consulta RAG ao Vivo | existente | linha "Pergunta desta tela"; mensagem explícita quando o índice do banco foi montado com outra base de trechos | |
| Arquitetura (LangGraph) | nova | fluxo dos agentes como grafo, cinco cenários, execução com o material do professor e pausa para decisão | |
| Grafo do código | nova | módulos, importações, cobertura de testes e funções (GitNexus, quando o arquivo existe) | |
| Ferramentas da API | existente | ataque sintético ao removedor de dado pessoal (416 casos, 9 controles), também em `.docx` e `.pdf` | |

Correção em código compartilhado: o removedor de dado pessoal (`backend/src/iris/security/pii_scrubber.py`) passou a
reconhecer CPF sem pontuação com dígitos verificadores válidos, deixou de apagar números longos e intervalos de anos e
a contar só substituições efetivas.

## 7. Tabela 4: telas do PR 85

"Equivalente no PR 87" indica a tela do playground que cobre parte do mesmo assunto, depois dos acréscimos da tabela 3.

| Grupo | Tela do PR 85 | Pergunta que responde | Equivalente no PR 87 | Observação | Decisão |
|---|---|---|---|---|---|
| Estado | Visão geral | O último commit verificado está bom? Há algo grave aberto? | nenhum | | |
| Estado | Commits e portões | Qual commit passou em cada verificação? | Benchmark Escolar (portão por rodada) | o grafo de commits reflete o repositório onde a página é gerada | |
| Estado | PRs e issues | Cada PR aberto melhora ou piora as métricas? | nenhum | dados do retrato de 13/11/2026; atualização depende do GitHub CLI | |
| Estado | Achados | O que está quebrado agora, com o caso que reproduz? | nenhum | | |
| Código | Grafo do código | Quem chama quem, e o que não tem teste? | Grafo do código | o PR 85 tem desenho interativo e fluxos de execução; o PR 87 tem tabela e busca | |
| Código | Pipeline inteiro | O que entrou e saiu de cada etapa, e em quanto tempo? | Consulta RAG ao Vivo (parcial) | provedor determinístico: mostra o fluxo, não a qualidade | |
| Código | Arquitetura com LangGraph | Como fica o fluxo dos agentes como grafo? | Arquitetura (LangGraph) | duas implementações do mesmo assunto | |
| RAG | Rastro do RAG | O que a busca trouxe, o que a resposta disse, o que os juízes acharam? | Auditoria do Benchmark | | |
| RAG | LLM x RAG | O modelo sozinho, só a busca, ou os dois juntos? | nenhum | resultado gravado, medido com modelo | |
| RAG | Qualidade por versão | Qual configuração é melhor, com incerteza? | Benchmark Escolar | | |
| RAG | Reprodutibilidade e custo | Rodar de novo dá o mesmo? Quanto custa? | Benchmark Escolar (repetição, sem custo) | | |
| RAG | Revisão humana | Em que frases os juízes discordam? | Auditoria do Benchmark (votos por frase) | | |
| Qualidade | Conjunto de avaliação | Este commit piorou algo nas 166 questões de adaptação? | Benchmark Escolar (lacre nas 136 questões do RAG) | conjuntos diferentes: adaptação no PR 85, RAG no PR 87 | |
| Qualidade | RAG: os quatro elos | Em qual elo quebrou? | Benchmark Escolar | o PR 85 usa a biblioteca RAGAS para a precisão do contexto | |
| Qualidade | Ataque em massa | Que dado pessoal passa pelo filtro? | Ferramentas da API | 1.916 casos no PR 85; 416 casos e 9 controles no PR 87 | |
| Qualidade | Juízes x pessoas | Dá para confiar na nota do juiz? | Auditoria do Benchmark (concordância entre juízes) | sem rótulos humanos nos dois | |
| Qualidade | Orçamento RNF-07 | Cada etapa cabe no tempo e nos tokens prometidos? | Benchmark Escolar (tempo, sem tokens) | | |
| Qualidade | Produção | O registro em produção guarda só metadados? | nenhum | dados sintéticos | |
| Testes | Segurança e ablação | Dado pessoal vaza? Cada peça faz diferença? | nenhum | provedor determinístico | |
| Testes | Comandos | Como rodar cada verificação? | Benchmark Escolar (botões) | sem execução pela página no playground | |
| Guia | Mapa do painel | Que pergunta cada tela responde? | linha "Pergunta desta tela" em cada aba | | |
| Guia | Ferramentas | Que ferramenta cada tela usa ou imita? | nenhum | | |

## 8. Verificação

| Verificação | Método | Resultado |
|---|---|---|
| Presença das abas | contagem das abas abertas pelo menu do playground | 22 de 22 |
| Igualdade de conteúdo | texto exibido em cada aba comparado, por resumo (hash), com a página gerada de um clone limpo do PR 85 | 21 de 22 idênticas; "Commits e portões" difere apenas no grafo de commits (5 commits no clone do PR 85, 48 no branch de integração), pela razão indicada na tabela 4 |
| Igualdade de dados | dados embutidos nas duas páginas comparados chave a chave | 30 chaves; diferem apenas `commits` (grafo) e `gerado` (data de geração) |
| Telas do PR 87 | abertura das 7 abas após a integração | 7 de 7, uma aba ativa por vez |
| Estouro de página | elementos além da borda, nas 22 abas, em 375, 768 e 1280 px | 0 nas três larguras |
| Erros no navegador | console e requisições ao abrir as 22 abas | apenas `GET /bancada/status.json` com 404, esperado fora da cópia publicada; a consulta para após o primeiro 404 |
| Testes automáticos | `backend/tests/test_bancada_pr85.py` (9 testes), com sabotagem de três tipos | os três defeitos introduzidos foram detectados |

## 9. Limitações e riscos

1. As telas que dependem de modelo exibem resultados gravados no retrato de 13/11/2026
   (`rag/iris-rag/bancada/referencia`), não medições do commit atual. A própria página informa isso.
2. A página do PR 85 contém trechos de documentos sem licença aberta. A rota `/bancada/` não deve ser exposta em
   implantação pública.
3. O tema escuro das telas do PR 85 difere do tema do PR 87.
4. Telas duplicadas (Arquitetura, Grafo do código, Ataque) precisam de decisão para não manter duas versões do mesmo
   assunto.
