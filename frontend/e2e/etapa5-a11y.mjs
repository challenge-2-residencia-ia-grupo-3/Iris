/**
 * Verificação opcional no navegador real (Chromium): responsividade e acessibilidade (WCAG 2.1 AA) da Etapa 5,
 * incluindo CONTRASTE DE COR, que o jsdom dos testes unitários não mede.
 *
 * Pré-requisitos (fora do `npm run test`): backend em :8000 e front em :3000 (`npm run build && npm run start`),
 *   npm i -D playwright && npx playwright install chromium
 * Uso: node e2e/etapa5-a11y.mjs [URL_BASE] [pasta_de_capturas]
 */
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const axeSource = require("fs").readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

const BASE = process.argv[2] ?? "http://127.0.0.1:3000";
const CAPTURAS = process.argv[3] ?? "";
if (CAPTURAS) mkdirSync(CAPTURAS, { recursive: true });
const LARGURAS = [320, 375, 768, 1024, 1280];
const TEMAS = ["claro", "escuro", "alto-contraste"];
let falhas = 0;
const falha = (msg) => { falhas++; console.log("  ✗", msg); };

const browser = await chromium.launch();
for (const tema of TEMAS) {
  for (const largura of LARGURAS) {
    const ctx = await browser.newContext({ viewport: { width: largura, height: 900 }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/etapa-5?demo=1`);
    await page.waitForSelector("textarea");
    if (tema === "escuro") await page.getByRole("button", { name: "Ativar modo escuro" }).click();
    if (tema === "alto-contraste") await page.getByRole("button", { name: "Alto Contraste" }).click();
    for (const b of await page.getByRole("button", { name: /Por que mudou/ }).all()) await b.click();
    console.log(`\n[${tema}] ${largura}px`);

    const m = await page.evaluate(() => {
      const li = document.querySelector("li[aria-label='Questão 1']");
      const [esq, dir] = [li.children[0].getBoundingClientRect(), li.children[1].getBoundingClientRect()];
      return {
        estouro: document.documentElement.scrollWidth > window.innerWidth + 1,
        ladoALado: dir.left > esq.left + 40 && Math.abs(dir.top - esq.top) < 8,
        empilhado: dir.top > esq.bottom - 1,
        menor44: [...document.querySelectorAll("button")].filter((b) => !b.disabled && b.getBoundingClientRect().height < 44).map((b) => b.textContent?.trim().slice(0, 30)),
      };
    });
    if (m.estouro) falha("rolagem horizontal na página");
    if (largura >= 768 && !m.ladoALado) falha("original e adaptada deveriam estar lado a lado");
    if (largura < 768 && !m.empilhado) falha("em tela estreita as colunas deveriam empilhar");
    console.log(`  layout: ${m.ladoALado ? "lado a lado" : "empilhado"}, sem rolagem horizontal: ${!m.estouro}`);
    if (m.menor44.length) console.log("  aviso: botões com menos de 44px:", m.menor44.join(", "));

    await page.evaluate(axeSource);
    const r = await page.evaluate(() => axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } }));
    for (const v of r.violations) falha(`${v.id} (${v.impact}): ${v.nodes.length} elemento(s) — ${v.nodes[0].target.join(" ")} — ${v.nodes[0].any?.[0]?.message ?? v.help}`);
    console.log(`  axe WCAG 2.1 AA: ${r.violations.length} violação(ões), ${r.passes.length} regras ok`);

    if (tema === "claro" && largura === 1280) {
      // teclado: Tab chega ao botão do cartão e Enter o recolhe/abre; o foco fica visível
      await page.evaluate(() => document.activeElement?.blur());
      const alvo = page.getByRole("button", { name: /Por que mudou · questão 1/ });
      await alvo.focus();
      const antes = await alvo.getAttribute("aria-expanded");
      await page.keyboard.press("Enter");
      const depois = await alvo.getAttribute("aria-expanded");
      if (antes === depois) falha("Enter não alternou o cartão");
      const foco = await alvo.evaluate((e) => getComputedStyle(e).outlineStyle !== "none" && parseFloat(getComputedStyle(e).outlineWidth) >= 2);
      if (!foco) falha("foco do teclado sem contorno visível");
      console.log(`  teclado: Enter alterna o cartão (${antes}→${depois}); contorno de foco visível: ${foco}`);
    }
    if (CAPTURAS && (largura === 375 || largura === 1280)) await page.screenshot({ path: `${CAPTURAS}/etapa5-${tema}-${largura}.png`, fullPage: true });
    await ctx.close();
  }
}
await browser.close();
console.log(falhas ? `\n${falhas} problema(s)` : "\nTudo certo.");
process.exit(falhas ? 1 : 0);
