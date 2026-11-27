# Auditoria WCAG 2.1 AA e Responsividade — Plataforma Íris (Issue #149 / RNF-09)

- **Executado em:** 2026-11-27T18:11:05.866Z
- **Frontend:** `http://127.0.0.1:3000`
- **Combinações auditadas:** 66 (7 rotas × 3 temas × viewports mobile/desktop)
- **Score médio axe-core (WCAG 2.1 AA):** **100/100** (mínimo observado: **100/100**)
- **Violações WCAG 2.1 AA (incluindo `color-contrast`):** **0**
- **Estouros horizontais (responsividade):** **0**
- **Alvos interativos < 44px:** **0**
- **Falhas de navegação por teclado / foco visível:** **0**
- **Status geral:** **APROVADO**

## Resumo por Rota

| Rota | Temas | Viewports | Violações WCAG | Overflow | Alvos < 44px | Teclado | Score axe-core |
|---|---|---|---:|---:|---:|---|---:|
| `/` | claro, escuro, alto-contraste | 320, 375, 1280px | 0 | 0 | 0 | OK | **100/100** |
| `/etapa-1` | claro, escuro, alto-contraste | 320, 375, 1280px | 0 | 0 | 0 | OK | **100/100** |
| `/etapa-2` | claro, escuro, alto-contraste | 320, 375, 1280px | 0 | 0 | 0 | OK | **100/100** |
| `/etapa-3` | claro, escuro, alto-contraste | 320, 375, 1280px | 0 | 0 | 0 | OK | **100/100** |
| `/etapa-4` | claro, escuro, alto-contraste | 320, 375, 1280px | 0 | 0 | 0 | OK | **100/100** |
| `/etapa-5?demo=1` | claro, escuro, alto-contraste | 320, 375, 768, 1280px | 0 | 0 | 0 | OK | **100/100** |
| `/historico` | claro, escuro, alto-contraste | 320, 375, 1280px | 0 | 0 | 0 | OK | **100/100** |

## Auditoria Google Lighthouse (Accessibility — Meta >= 95/100)

Evidência completa em `reports/lighthouse_a11y_report.json` (executado via `node frontend/e2e/lighthouse-a11y.mjs`):

| Rota | Lighthouse Accessibility | Meta | Status |
|---|---:|---:|---|
| `/` | **100/100** | >= 95 | APROVADO |
| `/etapa-1` | **100/100** | >= 95 | APROVADO |
| `/etapa-2` | **100/100** | >= 95 | APROVADO |
| `/etapa-3` | **100/100** | >= 95 | APROVADO |
| `/etapa-4` | **100/100** | >= 95 | APROVADO |
| `/etapa-5?demo=1` | **100/100** | >= 95 | APROVADO |
| `/historico` | **100/100** | >= 95 | APROVADO |
