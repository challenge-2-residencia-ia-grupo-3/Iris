# Etapa 5 — Revisão lado a lado (História 2.2.1)

Tela em `/etapa-5`: o material **original à esquerda** e a **versão adaptada à direita**, alinhados questão por questão (em telas estreitas, a adaptada fica logo abaixo do original). A edição, a aprovação e a trava de exportação são da [Revisão e Homologação](revisao_docente.md).

## Cartão "Por que mudou" (retrátil)

Cada questão tem um cartão com:

- **Característica funcional tratada** (nome e descrição observável, do catálogo oficial) e o **princípio do DUA** (I, II ou III);
- **O que foi feito**: as justificativas devolvidas pelo Agente Adaptador;
- **Objetivo do andaime** e rótulo do nível aplicado;
- **Fundamentação (DUA / MEC)**: ponto de verificação do DUA, citação curta e identificador da fonte;
- **O que mudou no texto**: trechos acrescentados ficam **sublinhados e em negrito** (não só cor) e são anunciados por leitores de tela.

Se a característica não estiver no catálogo, o cartão avisa e não cita fundamento. Se nenhuma adaptação foi aplicada, avisa que o texto da direita é o original.

## Indicadores de andaime

Chips com texto e ícone, derivados do **texto adaptado** (se o professor apagar o andaime, o indicador some): verbos de comando em destaque, etapas em lista de verificação, passos com espaço de resposta, caixas de conferência e lembrete de conferência final.

## Entrega da Etapa 4

A tela lê, da `sessionStorage` da aba, a chave `iris_session_step5_adaptacao_v1` com:

```json
{ "titulo": "opcional",
  "questoes": [{ "id": "q1", "original": "...", "adaptado": "...", "justificativas": ["..."],
                 "id_caracteristica": "<id do catálogo>", "nivel": 2, "adaptacao_aplicada": true }] }
```

Formato inválido é ignorado (a tela mostra "ainda não há atividade"). `/etapa-5?demo=1` abre um **exemplo ilustrativo**, com aviso na tela, para ver o layout sem rodar o pipeline.

## Acessibilidade e responsividade (WCAG 2.1 AA)

- Cartão é um *disclosure* (`aria-expanded`, `aria-controls`), operável por teclado; alvos de 44 px; foco visível; hierarquia de títulos h1 → h2 → h3 → h4.
- Contraste das cores desta tela ≥ 4,5:1 (testado por fórmula) e o chip de etapa atual da barra lateral foi escurecido (#C9411F) porque branco sobre #E35336 dava 3,78:1.
- `npm run test` roda axe-core (sem contraste, que o jsdom não mede) e checagens de layout.
- `e2e/etapa5-a11y.mjs` (opcional) mede no Chromium real, em 320, 375, 768, 1024 e 1280 px e nos temas claro, escuro e alto contraste: rolagem horizontal, colunas lado a lado/empilhadas, axe **com contraste** e foco por teclado.
