# Painel de qualidade: comparativo entre o PR 85 e o PR 87

## 1. Objetivo

Este documento registra a integração do painel de qualidade do PR 85 ("bancada") ao painel do PR 87 (playground do
backend) e as decisões, tela a tela, sobre o que permanece. A coluna "Decisão" das tabelas 3 e 4 traz a proposta do
responsável pelo PR 85 (16/11/2026), a confirmar com o responsável pelo PR 87.

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
| Auditoria do Benchmark | existente | linha "Pergunta desta tela" com a origem do número | fica |
| Benchmark Escolar (136) | existente | intervalo de confiança de 95% e linha de base por métrica; commit e hash da prova em cada rodada; métricas garantidas por construção sinalizadas; recusa de rodada sem questões; teste de recusa com 40 perguntas fora da base (intervalo de Wilson); limite do RNF-07 ao lado da latência; aviso quando gerador e juiz são o mesmo modelo; elo em que cada questão parou; repetição da rodada com comparação; portão aprovado, aviso ou reprovado com lacre da prova; variedade da busca | fica |
| Catálogo de Características TDAH | existente | linha "Pergunta desta tela" | fica |
| Consulta RAG ao Vivo | existente | linha "Pergunta desta tela"; mensagem explícita quando o índice do banco foi montado com outra base de trechos | fica |
| Arquitetura (LangGraph) | nova | fluxo dos agentes como grafo, cinco cenários, execução com o material do professor e pausa para decisão | fica (a do PR 85 sai) |
| Grafo do código | nova | módulos, importações, cobertura de testes e funções (GitNexus, quando o arquivo existe) | sai (fica a do PR 85, com o desenho) |
| Ferramentas da API | existente | ataque sintético ao removedor de dado pessoal (416 casos, 9 controles), também em `.docx` e `.pdf` | fica, com o ataque (o do PR 85 sai) |

Correção em código compartilhado: o removedor de dado pessoal (`backend/src/iris/security/pii_scrubber.py`) passou a
reconhecer CPF sem pontuação com dígitos verificadores válidos, deixou de apagar números longos e intervalos de anos e
a contar só substituições efetivas.

## 7. Tabela 4: telas do PR 85

"Equivalente no PR 87" indica a tela do playground que cobre parte do mesmo assunto, depois dos acréscimos da tabela 3.

| Grupo | Tela do PR 85 | Pergunta que responde | Equivalente no PR 87 | Observação | Decisão |
|---|---|---|---|---|---|
| Estado | Visão geral | O último commit verificado está bom? Há algo grave aberto? | nenhum | | fica |
| Estado | Commits e portões | Qual commit passou em cada verificação? | Benchmark Escolar (portão por rodada) | o grafo de commits reflete o repositório onde a página é gerada | fica |
| Estado | PRs e issues | Cada PR aberto melhora ou piora as métricas? | nenhum | dados do retrato de 13/11/2026; atualização depende do GitHub CLI | sai por ora: o dado é um retrato de 13/11; volta quando puder se atualizar sozinho |
| Estado | Achados | O que está quebrado agora, com o caso que reproduz? | nenhum | | fica, medida de novo com o código atual |
| Código | Grafo do código | Quem chama quem, e o que não tem teste? | Grafo do código | o PR 85 tem desenho interativo e fluxos de execução; o PR 87 tem tabela e busca | fica a do PR 85 (desenho e fluxos); sai a aba nova do playground |
| Código | Pipeline inteiro | O que entrou e saiu de cada etapa, e em quanto tempo? | Consulta RAG ao Vivo (parcial) | provedor determinístico: mostra o fluxo, não a qualidade | fica |
| Código | Arquitetura com LangGraph | Como fica o fluxo dos agentes como grafo? | Arquitetura (LangGraph) | duas implementações do mesmo assunto | sai; fica a aba Arquitetura (LangGraph) do playground |
| RAG | Rastro do RAG | O que a busca trouxe, o que a resposta disse, o que os juízes acharam? | Auditoria do Benchmark | | fica |
| RAG | LLM x RAG | O modelo sozinho, só a busca, ou os dois juntos? | nenhum | resultado gravado, medido com modelo | fica |
| RAG | Qualidade por versão | Qual configuração é melhor, com incerteza? | Benchmark Escolar | | fica |
| RAG | Reprodutibilidade e custo | Rodar de novo dá o mesmo? Quanto custa? | Benchmark Escolar (repetição, sem custo) | | fica |
| RAG | Revisão humana | Em que frases os juízes discordam? | Auditoria do Benchmark (votos por frase) | | fica |
| Qualidade | Conjunto de avaliação | Este commit piorou algo nas 166 questões de adaptação? | Benchmark Escolar (lacre nas 136 questões do RAG) | conjuntos diferentes: adaptação no PR 85, RAG no PR 87 | fica |
| Qualidade | RAG: os quatro elos | Em qual elo quebrou? | Benchmark Escolar | o PR 85 usa a biblioteca RAGAS para a precisão do contexto | fica |
| Qualidade | Ataque em massa | Que dado pessoal passa pelo filtro? | Ferramentas da API | 1.916 casos no PR 85; 416 casos e 9 controles no PR 87 | sai; fica o ataque das Ferramentas da API, que mede o removedor atual |
| Qualidade | Juízes x pessoas | Dá para confiar na nota do juiz? | Auditoria do Benchmark (concordância entre juízes) | sem rótulos humanos nos dois | fica; pedido: avaliar uma frase com um clique (ver seção 9) |
| Qualidade | Orçamento RNF-07 | Cada etapa cabe no tempo e nos tokens prometidos? | Benchmark Escolar (tempo, sem tokens) | | fica |
| Qualidade | Produção | O registro em produção guarda só metadados? | nenhum | dados sintéticos | sai: testa uma proposta que ainda não está no produto |
| Testes | Segurança e ablação | Dado pessoal vaza? Cada peça faz diferença? | nenhum | provedor determinístico | fica |
| Testes | Comandos | Como rodar cada verificação? | Benchmark Escolar (botões) | sem execução pela página no playground | sai: o botão Medir de novo sem modelo cobre o que roda pela página |
| Guia | Mapa do painel | Que pergunta cada tela responde? | linha "Pergunta desta tela" em cada aba | | sai: cada aba já abre com a pergunta da tela |
| Guia | Ferramentas | Que ferramenta cada tela usa ou imita? | nenhum | | fica |

## 8. Decisões de 16/11/2026 e o que mudou por causa delas

As decisões da tabela 4 foram tomadas tela a tela pelo responsável pelo PR 85, com a recomendação ao lado, e seguem
para confirmação com o responsável pelo PR 87.

| Decisão | O que mudou |
|---|---|
| 16 telas do PR 85 ficam, 6 saem do menu | as 6 continuam no repositório; a lista e o motivo estão em `FORA_DO_MENU` (`backend/src/iris/eval/bancada_pr85.py`) |
| A aba "Grafo do código" do playground sai | fica a tela do PR 85, que tem o desenho e os fluxos; a rota `/api/v1/eval/mapa-codigo` continua |
| Telas sem modelo acompanham o produto | o botão "Medir de novo sem modelo" roda a bateria sem modelo do PR 85 contra o código atual (cerca de 70 s) e gera a página; as telas medidas com modelo seguem como retrato de 13/11 |
| Só no próprio computador | as rotas `/bancada` e `/api/v1/eval/bancada-pr85` respondem 403 a pedido que não venha de 127.0.0.1 ou que traga cabeçalho de proxy; para quem acessa de fora, o grupo some do menu |
| Tema escolhido por quem usa | botão no rodapé do menu troca o painel inteiro entre claro e escuro; abre no claro e guarda a escolha no navegador; o claro do PR 87 não mudou e o escuro do PR 85 também não |
| Símbolo da Íris no painel | o mesmo `frontend/public/favicon.png` do front, como ícone da aba e ao lado do nome no menu |

## 9. Pendência: avaliar frases com um clique

Pedido: na tela "Juízes x pessoas", mostrar uma frase por vez, sem o voto dos juízes, com três botões (sustentada,
parcial, não sustentada), gravando no `rotulos-humanos.jsonl` e recalculando a concordância. O instrumento existe
(`bancada/calibracao/`: amostra fixa de 82 frases, regra de avaliação às cegas, cálculo do kappa). Falta o dado: as
respostas completas e os votos frase a frase (`17-respostas*.jsonl`, `17-juiz-*.jsonl`) não estão no repositório,
porque levam texto sem licença aberta; sem eles não há como mostrar os trechos que cada frase cita.

## 10. Verificação

| Verificação | Método | Resultado |
|---|---|---|
| Presença das abas | contagem das abas abertas pelo menu do playground | 22 de 22 antes das decisões; 16 depois |
| Igualdade de conteúdo | texto exibido em cada aba comparado, por resumo (hash), com a página gerada de um clone limpo do PR 85 | 21 de 22 idênticas; "Commits e portões" difere apenas no grafo de commits (5 commits no clone do PR 85, 48 no branch de integração), pela razão indicada na tabela 4 |
| Igualdade de dados | dados embutidos nas duas páginas comparados chave a chave | 30 chaves; diferem apenas `commits` (grafo) e `gerado` (data de geração) |
| Telas do PR 87 | abertura das 7 abas após a integração | 7 de 7, uma aba ativa por vez |
| Estouro de página | elementos além da borda, nas 22 abas, em 375, 768 e 1280 px | 0 nas três larguras |
| Erros no navegador | console e requisições ao abrir as 22 abas | apenas `GET /bancada/status.json` com 404, esperado fora da cópia publicada; a consulta para após o primeiro 404 |
| Testes automáticos | `backend/tests/test_bancada_pr85.py` (16 testes), com sabotagem | os cinco defeitos introduzidos foram detectados; suíte do backend: 724 passam, 7 pulados |
| Tema escuro do PR 85 igual ao original | cor calculada de cada elemento das 16 telas, antes e depois da troca das cores por variáveis | 16 de 16 telas idênticas, inclusive os pixels do grafo |
| Contraste do texto (mínimo 4,5:1, WCAG) | razão entre a cor do texto e a do fundo, em cada elemento com texto | tema claro: 0 abaixo em 4.239 elementos das 16 telas do PR 85 e 0 em 2.043 das 6 do PR 87; tema escuro do PR 87: 0; tema escuro original do PR 85: 46 abaixo (herdado, sem mudança) |
| Estouro de página nos dois temas | 375, 768 e 1280 px, 22 telas | 0 |

## 11. Limitações e riscos

1. As telas que dependem de modelo exibem resultados gravados no retrato de 13/11/2026
   (`rag/iris-rag/bancada/referencia`), não medições do commit atual. A própria página informa isso.
2. A página do PR 85 contém trechos de documentos sem licença aberta. A rota `/bancada/` não deve ser exposta em
   implantação pública.
3. O tema escuro das telas do PR 85 difere do tema do PR 87.
4. Telas duplicadas (Arquitetura, Grafo do código, Ataque) precisam de decisão para não manter duas versões do mesmo
   assunto.
