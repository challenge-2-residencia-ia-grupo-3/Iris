/**
 * Auditoria automatizada Google Lighthouse (categoria Accessibility) em todas as 7 rotas
 * da Plataforma Íris (Issue #149 — RNF-09: score >= 95/100).
 *
 * Uso:
 *   node frontend/e2e/lighthouse-a11y.mjs
 *
 * Variáveis opcionais:
 *   FRONTEND_URL=http://127.0.0.1:3000
 *   REPORT_PATH=reports/lighthouse_a11y_report.json
 *   MIN_SCORE=95
 *   CHROME_PATH=...
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { resolveChromeExecutable } from "./wcag-audit.mjs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const FRONTEND_URL = (process.env.FRONTEND_URL || "http://127.0.0.1:3000").replace(/\/+$/, "");
const REPORT_PATH = process.env.REPORT_PATH || path.resolve(process.cwd(), "reports/lighthouse_a11y_report.json");
const MIN_SCORE = Number(process.env.MIN_SCORE || 95);

const ROUTES = [
  { id: "login", path: "/", label: "Tela de Acesso (/)" },
  { id: "etapa-1", path: "/etapa-1", label: "Etapa 1 (/etapa-1)" },
  { id: "etapa-2", path: "/etapa-2", label: "Etapa 2 (/etapa-2)" },
  { id: "etapa-3", path: "/etapa-3", label: "Etapa 3 (/etapa-3)" },
  { id: "etapa-4", path: "/etapa-4", label: "Etapa 4 (/etapa-4)" },
  { id: "etapa-5", path: "/etapa-5?demo=1", label: "Etapa 5 (/etapa-5?demo=1)" },
  { id: "historico", path: "/historico", label: "Histórico (/historico)" },
];

async function main() {
  const { default: lighthouse } = await import("lighthouse");

  const executablePath = resolveChromeExecutable();
  const debugPort = 9222 + Math.floor(Math.random() * 500);

  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
    args: [
      `--remote-debugging-port=${debugPort}`,
      "--no-sandbox",
      "--disable-gpu",
      "--force-prefers-reduced-motion",
    ],
  });

  const routeScores = [];
  let failed = false;

  try {
    for (const route of ROUTES) {
      const url = `${FRONTEND_URL}${route.path}`;
      const runnerResult = await lighthouse(url, {
        port: debugPort,
        output: "json",
        logLevel: "error",
        onlyCategories: ["accessibility"],
        formFactor: "desktop",
        screenEmulation: {
          mobile: false,
          width: 1280,
          height: 900,
          deviceScaleFactor: 1,
          disabled: false,
        },
      });

      const lhr = runnerResult.lhr;
      const rawScore = lhr.categories?.accessibility?.score ?? 0;
      const score = Math.round(rawScore * 100);

      const failedAudits = Object.values(lhr.audits || {})
        .filter(
          (a) =>
            a.score !== null &&
            a.score < 1 &&
            a.scoreDisplayMode !== "notApplicable" &&
            a.scoreDisplayMode !== "manual" &&
            a.scoreDisplayMode !== "informative"
        )
        .map((a) => ({
          id: a.id,
          title: a.title,
          score: a.score,
          items: (a.details?.items || [])
            .slice(0, 5)
            .map((item) => item.node?.selector || item.node?.snippet || ""),
        }));

      const ok = score >= MIN_SCORE;
      if (!ok) failed = true;

      console.log(
        `[${ok ? "OK" : "FALHA"}] Lighthouse Accessibility ${route.path}: ${score}/100 (mínimo: ${MIN_SCORE})` +
          (failedAudits.length > 0 ? ` — auditorias com ressalva: ${failedAudits.map((a) => a.id).join(", ")}` : "")
      );
      for (const a of failedAudits) {
        console.log(`       -> ${a.id}: ${a.title} (${a.items.filter(Boolean).join("; ")})`);
      }

      routeScores.push({
        id: route.id,
        path: route.path,
        label: route.label,
        score,
        passed: ok,
        failedAudits,
      });
    }
  } finally {
    await browser.close();
  }

  const minScore = routeScores.length > 0 ? Math.min(...routeScores.map((r) => r.score)) : 0;
  const avgScore =
    routeScores.length > 0 ? Math.round(routeScores.reduce((acc, r) => acc + r.score, 0) / routeScores.length) : 0;

  const report = {
    generatedAt: new Date().toISOString(),
    frontendUrl: FRONTEND_URL,
    threshold: MIN_SCORE,
    passed: !failed && minScore >= MIN_SCORE,
    minScore,
    averageScore: avgScore,
    routes: routeScores,
  };

  fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");

  console.log("\n================================================================================");
  console.log(`RESUMO LIGHTHOUSE ACCESSIBILITY: mínimo ${minScore}/100 | média ${avgScore}/100 | meta >= ${MIN_SCORE}/100`);
  console.log(`Relatório salvo em: ${REPORT_PATH}`);
  console.log("================================================================================");

  if (!report.passed) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
