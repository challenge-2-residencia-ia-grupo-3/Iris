# Design System — Íris Bancada de Auditoria RAG (`localhost:8000`)

## Visual World: Cartografia de Campo

Interface operacional em modo **Operate** inspirada em pranchas de levantamento técnico e cartografia científica: trilho lateral persistente em verde-ardósia com telemetria contínua dos serviços e área de trabalho ampla em papel mineral claro.

## Color Tokens

- `--rail`: `#143d40` (trilho lateral de navegação e telemetria)
- `--rail-elevated`: `#1b4d50`
- `--rail-active`: `#236165`
- `--rail-ink`: `#edf2f2`
- `--rail-muted`: `#9ec5c7`
- `--paper`: `#eef3f3` (fundo principal da área de trabalho)
- `--surface`: `#ffffff` (folhas/blocos de conteúdo com borda `1px solid #d1dddd`)
- `--wash`: `#e4ecec`
- `--ink`: `#132325`
- `--muted`: `#4b6163`
- `--vermilion`: `#b83523` (ações primárias, foco ativo e alertas críticos)
- `--moss`: `#156f4e` (conformidade, apoio e status saudável)
- `--ochre`: `#9e5b08` (fallback e atenção)

## Typography

- **UI & Tabelas:** `Work Sans` / system sans-serif com `font-variant-numeric: tabular-nums`.
- **Leitura longa (respostas e trechos):** `Iowan Old Style` / `Georgia` / serif até `68ch–70ch`.
- **IDs, scores e logs:** `JetBrains Mono` / monospace.

## Layout & Rules

- Grid principal `.app-shell`: trilho esquerdo fixo (`268px`) + conteúdo fluido (`minmax(0, 1fr)`), colapsando para barra superior abaixo de `1024px`.
- Elevação declarada uma única vez por bordas `1px solid var(--hairline)`, sem sombras deslocadas nem bordas laterais grossas.
- Estados de navegador tematizados (`::selection`, `scrollbar-color`, `caret-color`, `:focus-visible`).
