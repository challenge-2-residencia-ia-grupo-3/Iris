# Painel de qualidade: as Verificações de qualidade dentro do playground

## 1. Objetivo

Este documento registra a integração das **Verificações de qualidade** (a "bancada" de verificação do Íris) ao
**painel do playground** do backend, e as decisões, tela a tela, sobre o que permanece. A coluna "Decisão" das tabelas
3 e 4 traz a proposta do responsável pelas Verificações de qualidade (16/11/2026), a confirmar com o responsável pelo
painel do playground.

## 2. Escopo e origem

| Item | Referência |
|---|---|
| Verificações de qualidade | pastas `rag/iris-rag/bancada/` e `rag/iris-rag/pacote/` (gerador `bancada.py`); vieram do [PR 85](https://github.com/challenge-2-residencia-ia-grupo-3/Iris/pull/85), branch `feat/painel-qualidade` |
| Painel do playground | `backend/src/iris/static/playground.html` e rotas em `backend/src/iris/main.py`; do [PR 87](https://github.com/challenge-2-residencia-ia-grupo-3/Iris/pull/87), branch `feat/rag-sonnet-progress-ui` |
| Integração | branch `feat/qualidade-no-playground`, criado sobre o painel do playground (`0e0ac54`), com o `dev` do grupo de 16/11/2026 juntado |

## 3. Regras adotadas na integração

1. Nenhuma tela, rota ou função do painel do playground foi removida ou substituída.
2. Alterações no código do playground limitam-se a acréscimos e a correções de defeito identificado e documentado.
3. As telas das Verificações de qualidade foram trazidas sem alteração de conteúdo; as mudanças no código delas são o
   modo de exibição embutido, o tema claro e a atualização para o módulo de perfil renomeado pelo grupo.
4. Nenhuma verificação exige chave de API ou modelo de linguagem para abrir.

## 4. Estrutura resultante

O menu lateral do playground mantém as abas dele e recebe um grupo recolhível, **"Verificações de qualidade (em
avaliação)"**, com 16 telas nos mesmos grupos do menu original (Estado, Código, RAG, Qualidade, Testes, Guia). Cada
tela do grupo exibe, acima do conteúdo, a pergunta que responde e a tela equivalente do playground, quando houver.

## 5. Método de integração

| Elemento | Solução | Alternativa descartada |
|---|---|---|
| Código | `rag/iris-rag/bancada/` e os 9 arquivos de `rag/iris-rag/pacote/` trazidos sem mudança de conteúdo; `consultar.py` e `gerar.py` mantidos na versão do playground | reescrever as telas no padrão visual do playground, o que alteraria o conteúdo e impediria a comparação direta |
| Exibição | página única gerada por `bancada.py`, servida em `/verificacoes/`; o playground a abre num quadro, uma tela por vez (`?embutido=1`) | uma aba única com todas as telas, que impede decidir tela a tela |
| Desenho igual ao original | dentro do quadro, os pontos de troca de desenho acima de 900 px descem 244 px (a largura do menu lateral da bancada, que ali não aparece), e o que era medido pela altura da janela usa a altura da janela do playground; o quadro cresce até a altura do conteúdo, sem rolagem interna | quadro de altura fixa, que rolava por dentro e empilhava cartões que no original ficam lado a lado |
| Rotas | `GET /verificacoes/`, `GET /verificacoes/status.json`, `GET /api/v1/eval/verificacoes-qualidade`, `POST .../gerar`, `POST .../medir`, e `/api/v1/eval/avaliacao-humana/{proxima,rotulo,resumo}`, nos dois servidores (FastAPI e biblioteca padrão) | servidor próprio da bancada na porta 8777, que exigiria um segundo processo |
| Acesso | as rotas acima só respondem ao próprio computador (403 para outro endereço ou pedido com cabeçalho de proxy) | rota aberta: a página contém trechos de documentos sem licença aberta |
| Comandos | não há execução de `make` pela página; o botão "Medir de novo sem modelo" roda um comando fixo | expor a execução de comandos escolhidos pela página no backend do produto |
| Tema | botão no rodapé do menu: claro ou escuro no painel inteiro | manter dois temas diferentes lado a lado |

## 6. Tabela 3: telas do playground e acréscimos feitos nelas

| Tela do playground | Situação | Acréscimo na integração | Decisão |
|---|---|---|---|
| Auditoria do Benchmark | existente | linha "Pergunta desta tela" com a origem do número | fica |
| Benchmark Escolar (136) | existente | intervalo de confiança de 95% e linha de base por métrica; commit e hash da prova em cada rodada; métricas garantidas por construção sinalizadas; recusa de rodada sem questões; teste de recusa com 40 perguntas fora da base (intervalo de Wilson); limite do RNF-07 ao lado da latência; aviso quando gerador e juiz são o mesmo modelo; elo em que cada questão parou; repetição da rodada com comparação; portão aprovado, aviso ou reprovado com lacre da prova; variedade da busca | fica |
| Catálogo de Características TDAH | existente | linha "Pergunta desta tela" | fica |
| Consulta RAG ao Vivo | existente | linha "Pergunta desta tela"; mensagem explícita quando o índice do banco foi montado com outra base de trechos | fica |
| Arquitetura (LangGraph) | nova | fluxo dos agentes como grafo, cinco cenários, execução com o material do professor e pausa para decisão | fica (a das Verificações sai) |
| Grafo do código | nova | módulos, importações, cobertura de testes e funções | sai (fica a das Verificações, com o desenho) |
| Ferramentas da API | existente | ataque sintético ao removedor de dado pessoal (416 casos, 9 controles), também em `.docx` e `.pdf` | fica, com o ataque (o das Verificações sai) |

Correção em código compartilhado: o removedor de dado pessoal (`backend/src/iris/security/pii_scrubber.py`) passou a
reconhecer CPF sem pontuação com dígitos verificadores válidos, deixou de apagar números longos e intervalos de anos e
a contar só substituições efetivas.

## 7. Tabela 4: telas das Verificações de qualidade

"Equivalente no playground" indica a tela do playground que cobre parte do mesmo assunto, depois dos acréscimos da
tabela 3.

| Grupo | Tela | Pergunta que responde | Equivalente no playground | Observação | Decisão |
|---|---|---|---|---|---|
| Estado | Visão geral | O último commit verificado está bom? Há algo grave aberto? | nenhum | | fica |
| Estado | Commits e portões | Qual commit passou em cada verificação? | Benchmark Escolar (portão por rodada) | o grafo de commits mostra o repositório onde a página é gerada | fica |
| Estado | PRs e issues | Cada PR aberto melhora ou piora as métricas? | nenhum | dado de 13/11/2026; atualizar depende do GitHub CLI | sai por ora; volta quando puder se atualizar sozinha |
| Estado | Achados | O que está quebrado agora, com o caso que reproduz? | nenhum | | fica, medida com o código atual |
| Código | Grafo do código | Quem chama quem, e o que não tem teste? | Grafo do código | aqui há desenho interativo e fluxos de execução; no playground, tabela e busca | fica (a do playground sai) |
| Código | Pipeline inteiro | O que entrou e saiu de cada etapa, e em quanto tempo? | Consulta RAG ao Vivo (parcial) | provedor determinístico: mostra o fluxo, não a qualidade | fica |
| Código | Arquitetura com LangGraph | Como fica o fluxo dos agentes como grafo? | Arquitetura (LangGraph) | duas implementações do mesmo assunto | sai (fica a do playground) |
| RAG | Rastro do RAG | O que a busca trouxe, o que a resposta disse, o que os juízes acharam? | Auditoria do Benchmark | | fica |
| RAG | LLM x RAG | O modelo sozinho, só a busca, ou os dois juntos? | nenhum | resultado gravado, medido com modelo | fica |
| RAG | Qualidade por versão | Qual configuração é melhor, com incerteza? | Benchmark Escolar | | fica |
| RAG | Reprodutibilidade e custo | Rodar de novo dá o mesmo? Quanto custa? | Benchmark Escolar (repetição, sem custo) | | fica |
| RAG | Revisão humana | Em que frases os juízes discordam? | Auditoria do Benchmark (votos por frase) | | fica |
| Qualidade | Conjunto de avaliação | Este commit piorou algo nas 166 questões de adaptação? | Benchmark Escolar (lacre nas 136 questões do RAG) | conjuntos diferentes: adaptação aqui, RAG no playground | fica |
| Qualidade | RAG: os quatro elos | Em qual elo quebrou? | Benchmark Escolar | usa a biblioteca RAGAS para a precisão do contexto | fica |
| Qualidade | Ataque em massa | Que dado pessoal passa pelo filtro? | Ferramentas da API | 1.916 casos aqui; 416 casos e 9 controles no playground | sai (fica o do playground, que mede o removedor atual) |
| Qualidade | Juízes x pessoas | Dá para confiar na nota do juiz? | Auditoria do Benchmark (concordância entre juízes) | ganhou a avaliação de uma frase com um clique, às cegas (seção 9) | fica |
| Qualidade | Orçamento RNF-07 | Cada etapa cabe no tempo e nos tokens prometidos? | Benchmark Escolar (tempo, sem tokens) | | fica |
| Qualidade | Produção | O registro em produção guarda só metadados? | nenhum | testa uma proposta que ainda não está no produto | sai |
| Testes | Segurança e ablação | Dado pessoal vaza? Cada peça faz diferença? | nenhum | provedor determinístico | fica |
| Testes | Comandos | Como rodar cada verificação? | Benchmark Escolar (botões) | sem execução pela página | sai |
| Guia | Mapa do painel | Que pergunta cada tela responde? | linha "Pergunta desta tela" em cada aba | | sai |
| Guia | Ferramentas | Que ferramenta cada tela usa ou imita? | nenhum | | fica |

## 8. Decisões de 16/11/2026 e o que mudou por causa delas

| Decisão | O que mudou |
|---|---|
| 16 telas ficam, 6 saem do menu | as 6 continuam no repositório; a lista e o motivo estão em `FORA_DO_MENU` (`backend/src/iris/eval/verificacoes_qualidade.py`) |
| A aba "Grafo do código" do playground sai | fica a das Verificações, que tem o desenho e os fluxos; a rota `/api/v1/eval/mapa-codigo` continua |
| Telas sem modelo acompanham o produto | o botão "Medir de novo sem modelo" roda as verificações sem modelo contra o código atual (cerca de 70 s) e gera a página; as telas medidas com modelo seguem como retrato de 13/11 |
| Só no próprio computador | ver seção 5, "Acesso"; para quem acessa de fora, o grupo some do menu |
| Tema escolhido por quem usa | botão no rodapé do menu; abre no claro e guarda a escolha no navegador; o claro do playground não mudou e o escuro das Verificações também não |
| Símbolo da Íris no painel | o mesmo `frontend/public/favicon.png` do front, como ícone da aba e ao lado do nome no menu |
| Nome | "Verificações de qualidade" no lugar do número do PR de origem, na tela, no código e nos documentos |

Depois de juntar o `dev` do grupo: o módulo de perfil passou a se chamar `iris.schemas.portable_profile` e o código
anônimo do aluno passou a ter o formato `aluno-` mais 8 a 32 caracteres hexadecimais. As Verificações foram atualizadas
para os dois; antes disso, uma delas marcava a etapa do perfil como "não implementada" em vez de acusar erro.

## 9. Avaliar uma frase com um clique

Na tela "Juízes x pessoas": uma frase por vez, sem o voto dos juízes, com três botões (sustentada, parcial, não
sustentada) e motivo opcional. Usa as respostas versionadas do grupo (`respostas_medidas.json`, Haiku e Opus, 40
perguntas) e os votos de Sonnet A, Sonnet B e Codex (`respostas_vereditos_cruzado.json`). Amostra fixa de 86 frases:
as 19 divididas, as 17 de dois contra um, as 10 unânimes "não" e 40 sorteadas das 316 unânimes "sustenta". Os rótulos
vão para `rag/iris-rag/bancada/calibracao/rotulos-humanos-grupo.jsonl`, só por acréscimo; a concordância de cada juiz
com as pessoas aparece a partir de 20 frases. Conferido: 284 de 284 passagens citadas pelos juízes estão dentro do
trecho que a tela mostra.

## 10. Verificação

| Verificação | Método | Resultado |
|---|---|---|
| Igualdade de conteúdo | texto exibido em cada tela comparado, por resumo (hash), com a página gerada de um clone limpo da origem | 21 de 22 idênticas; "Commits e portões" difere só no grafo de commits, que mostra o repositório onde a página é gerada |
| Desenho igual ao original | número de cartões lado a lado e de caixas que rolam, em cada tela, na mesma largura de conteúdo | 16 de 16 com os mesmos cartões lado a lado; caixas que rolam iguais em 15 (a outra é o grafo de commits, por ter mais commits) |
| Rolagem dentro do quadro | altura do conteúdo contra a altura do quadro, nas 16 telas, em 375, 768 e 1280 px | 0 telas com rolagem interna; 0 elementos além da borda |
| Telas do playground | abertura das abas do playground após a integração | todas abrem, uma ativa por vez |
| Tema escuro das Verificações igual ao original | cor calculada de cada elemento das 16 telas, antes e depois da troca das cores por variáveis | 16 de 16 idênticas, inclusive os pixels do grafo |
| Contraste do texto (mínimo 4,5:1, WCAG) | razão entre a cor do texto e a do fundo, em cada elemento com texto | tema claro: 0 abaixo em 4.239 elementos das Verificações e 0 em 2.043 do playground; tema escuro do playground: 0; tema escuro original das Verificações: 46 abaixo (herdado, sem mudança) |
| Testes automáticos | suíte do backend, com sabotagens | 813 passam, 7 pulados; todas as sabotagens foram detectadas |

## 11. Limitações e riscos

1. As telas que dependem de modelo mostram resultados gravados em 13/11/2026 (`rag/iris-rag/bancada/referencia`), não
   medições do commit atual. A própria página informa isso.
2. A página das Verificações contém trechos de documentos sem licença aberta; por isso só abre no próprio computador.
3. Dentro do quadro, os elementos que no original ficam presos no topo ao rolar (cabeçalho, detalhes laterais) rolam
   junto com a página.
4. Nenhuma frase foi avaliada por pessoa até esta data.
