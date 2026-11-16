# Bancada do Íris: plano de design (antes do código)

**Superfície:** Monitor (o time abre para ver o estado do sistema depois de um commit), com um modo Inspecionar
(abrir uma pergunta, um material, uma frase). Não é página de venda: nada de hero, nada de cards iguais em grade.

**Pergunta que a primeira tela responde em 3 segundos:** "o último commit está bom, e tem alguma coisa grave aberta?"

## Composição

```
┌ topo fino: Íris · bancada        commit grupo 65e1f09 "título" · verificado há 3 min ┐
├──────────────┬───────────────────────────────────────────────────────────────────────────────────────┤
│ navegação    │ FAIXA DE ALERTA (só se houver): 2 achados graves abertos · último commit reprovado    │
│ lateral      ├───────────────────────────────────────────────────────────────────────────────────────┤
│              │ Visão geral: 4 números de estado (portões, recall atual, fidelidade, PII bloqueado)   │
│ Visão geral  │ + linha do tempo dos commits (pontos verde/vermelho)                                    │
│ Achados  (2) │ + lista de achados graves com o caso que reproduz                                       │
│ Rastro RAG   │                                                                                       │
│ Pipeline     │ (as outras seções ocupam a mesma área; a navegação lateral fica fixa)                 │
│ Qualidade    │                                                                                       │
│ Confiança    │                                                                                       │
│ Revisão (41) │                                                                                       │
│ Segurança    │                                                                                       │
│ Mapa         │                                                                                       │
│ Comandos     │                                                                                       │
└──────────────┴───────────────────────────────────────────────────────────────────────────────────────┘
```

Largura útil até 1480 px; navegação lateral de 220 px que vira barra superior com rolagem no celular.

## Tokens (revisão de 12/11, paleta grafite, violeta e rosa)

Regra de distribuição: dois neutros dão o clima, a cor de destaque fica só para o que pede ação. Teste do olho
semicerrado: borrada a tela, o que sobra deve ser o alerta, não o "passou".

| Papel | Valor | Por quê |
|---|---|---|
| fundo | grafite #18181C; superfícies #1F1F25 / #26262E / #2F2F39 | neutro escuro levemente frio, não preto puro |
| borda | #2F2F38, forte #3E3E4A | |
| texto | #EDEDF2, secundário #B4B4C2, terciário #8A8A9A | contraste AA |
| marca e navegação (aba ativa, foco, botão, gráfico) | violeta #723BFA em preenchimento, #A68BFF em texto e linhas | o violeta puro é escuro demais para texto no grafite; o tom claro mantém contraste |
| passou | azul-esverdeado apagado #6FA3A6 | o normal não chama atenção |
| símbolos na matriz de portões | ✕ no quadrado reprovado, – no sem dado, vazio no não rodou | a leitura não depende só da cor (daltonismo, impressão em preto e branco) |
| atenção | âmbar #E5B443 | |
| **erro** (portão reprovado, regressão, etapa quebrada) | #FF6B6B, fundo #35171B, borda #6B2A33 | só aparece para erro |
| **dados pessoais (LGPD)** | rosa #FF4FA3, fundo #3A1527, borda #7A2650; `<mark>` #4A1530 com contorno #C23A7E; ícone de cadeado nos selos e contadores | cor quente de alerta, distinta do vermelho de erro e do violeta da navegação. O rosa foi descartado: em painel, verde quer dizer "tudo certo" (semáforo), e alerta em verde confunde. Nenhuma outra peça usa rosa (faixas do grafo de commits e comunidades sem rosa) |
| sombra | --sh1 (cartões), --sh2 (cartão sob o mouse) | dá plano aos cartões sem borda pesada |
| tipografia | Space Grotesk (títulos, nomes das seções, números grandes), IBM Plex Sans (texto), IBM Plex Mono (código e valores tabulares); embutidas no HTML (OFL) | o título ganha presença sem mudar o texto corrido |
| escala | 11,5 (rótulo de seção, caixa alta) / 12,5 / 14 / 15,5 (h3) / 17 (título de cartão) / 22 (seção) / 30 (h1 e números) | |
| espaçamento | 4 / 8 / 12 / 16 / 20 / 28 / 40 | |
| raio | 6 (controles), 12 (painéis e cartões) | |

## Sinalização de achado grave

- Faixa no topo da área de conteúdo, vermelho escuro, com o número de achados graves abertos e o link "ver".
- Contador vermelho no item "Achados" da navegação.
- Na aba Segurança, cada caso de dado pessoal que passou fica com fundo de alerta e a parte vazada **marcada dentro do
  texto** (a palavra que passou fica realçada), mais um selo "LGPD".
- Gravidade sai de uma regra escrita (dado pessoal ou clínico que passou = grave; falso positivo que apaga conteúdo =
  atenção; regressão de métrica = grave), não de escolha à mão por tela.

## Movimento (pouco e com função)

- Troca de seção: o título entra primeiro (320 ms), depois os cartões em sequência de 35 ms cada (no máximo 10 passos),
  para o olho seguir a ordem de leitura.
- Cartão sob o mouse sobe 2 a 3 px e ganha sombra mais funda; no Mapa do painel a seta do cartão anda para a direita.
- O rosa aparece forte num lugar só por tela: a faixa de alerta. O cartão de dado pessoal tem só um filete rosa na borda. Nas outras telas a faixa compacta acende uma vez com um halo e para.
- A faixa grave aparece uma vez com um pulso curto na borda.
- Tudo desligado com `prefers-reduced-motion`.

## Revisão contra os padrões genéricos

- Evitado: grade de cards iguais, eyebrow em caixa alta sobre todo título, gradiente, ícone em cima de cada título,
  número gigante enfeitando. Os números da visão geral existem porque respondem à pergunta da primeira tela.
- O que é memorável aqui: a faixa de alerta e a linha do tempo dos commits com o veredito de cada portão. O resto é quieto.

## Revisão de 12/11 (redesenho)

- **Grade de 12 colunas** em toda a área de conteúdo (sem largura máxima: usa os 1440 px). KPIs em 4×3 colunas; visão geral 7+5;
  commits 8+4 (lista + detalhe fixo); tabelas largas ocupam 12. Abaixo de 1180 px tudo vira 12; abaixo de 900 px a navegação vira
  barra superior com rolagem lateral (com esmaecimento na borda indicando que rola).
- **Duas faixas de alerta** separadas pela regra: rosa para dado pessoal que vazou, vermelha para erro grave. Fora da visão geral
  a faixa fica compacta (uma linha) para não empurrar o conteúdo.
- **Commits e portões:** grafo de faixas como o `git log --graph` (cores das faixas sem vermelho nem rosa, para não confundir com
  os significados fixos), matriz de quadrados por portão em toda linha (vazia = sem veredito), detalhe do commit à direita e a
  tendência de cada métrica por rodada do dev, com a primeira rodada tracejada como linha de base. PRs abertos entram como ramos.
- **PRs e issues:** idade, dono, issue que o PR resolve, etapas do pipeline tocadas (pelos arquivos), portões rodados na cabeça do
  PR e a diferença de cada métrica contra o dev (vermelho piora, rosa piora no filtro de dados pessoais). Issues sem dono em âmbar.
- **Grafo do código, no estilo GitNexus:** canvas com d3-force embutido (sem CDN), duas camadas (funções e chamadas pelo GitNexus;
  módulos e imports pelo `make mapa`), cor = comunidade, tamanho = ligações, anel rosa = código de dados pessoais, anel âmbar =
  módulo sem teste. Passar o mouse acende os vizinhos; clicar abre quem chama e quem é chamado; `/` busca; fluxo de execução
  passo a passo numerado; rótulos sem sobreposição (os mais ligados primeiro).
- **Pipeline:** cartões “o que cada etapa faz, por que existe, se falhar o professor vê”, com exemplo real de entrada e saída;
  rastro de cada chamada de agente (prompt, resposta, tokens, tempo) e linha do tempo (cascata) por etapa.
- **Nada externo:** fontes Plex e d3 embutidas a partir de `bancada/vendor` (OFL e ISC), `referrer=no-referrer`.
