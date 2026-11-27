/**
 * Auditoria automatizada WCAG 2.1 AA, responsividade, teclado e alvos táteis (>= 44px)
 * para todas as 7 rotas da Plataforma Íris (Issue #149 — RNF-09):
 *   /, /etapa-1, /etapa-2, /etapa-3, /etapa-4, /etapa-5?demo=1, /historico
 *
 * Valida nos 3 temas (claro, escuro, alto-contraste) e viewports mobile/desktop (320, 375, 1280px,
 * além de 768px na Etapa 5 para validar transição empilhado <-> lado a lado):
 *   1. Zero violações bloqueantes WCAG 2.1 AA (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, incluindo `color-contrast`)
 *   2. Zero rolagem horizontal (`scrollWidth <= innerWidth + 1`)
 *   3. Navegação integral por teclado (sem armadilhas de foco e indicador de foco visível)
 *   4. Alvos interativos >= 44px
 *   5. Score axe-core >= 95/100 em todas as combinações
 *
 * Uso:
 *   node frontend/e2e/wcag-audit.mjs
 *
 * Variáveis opcionais:
 *   FRONTEND_URL=http://127.0.0.1:3000
 *   BACKEND_URL=http://127.0.0.1:8000
 *   ARTIFACTS_DIR=frontend/e2e/artifacts
 *   REPORT_PATH=reports/wcag_a11y_audit.json
 *   CHROME_PATH=...
 *   WCAG_ROUTES=/,/etapa-1,...
 *   WCAG_THEMES=claro,escuro,alto-contraste
 *   WCAG_VIEWPORTS=320,375,1280
 *   WCAG_DIAGNOSTIC=1   (não interrompe com exit 1 para listar todas as falhas no diagnóstico)
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const axeSource = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

const FRONTEND_URL = (process.env.FRONTEND_URL || "http://127.0.0.1:3000").replace(/\/+$/, "");
const BACKEND_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const ARTIFACTS_DIR = process.env.ARTIFACTS_DIR || path.resolve(process.cwd(), "frontend/e2e/artifacts");
const REPORT_PATH = process.env.REPORT_PATH || "";
const DIAGNOSTIC_MODE = process.env.WCAG_DIAGNOSTIC === "1";

const DEFAULT_THEMES = ["claro", "escuro", "alto-contraste"];
const DEFAULT_VIEWPORTS = [320, 375, 1280];

const THEMES = process.env.WCAG_THEMES
  ? process.env.WCAG_THEMES.split(",").map((s) => s.trim()).filter(Boolean)
  : DEFAULT_THEMES;

const VIEWPORTS = process.env.WCAG_VIEWPORTS
  ? process.env.WCAG_VIEWPORTS.split(",").map((s) => Number(s.trim())).filter((n) => Number.isFinite(n) && n > 0)
  : DEFAULT_VIEWPORTS;

const SEED_MATERIAL =
  "Avaliação de Ciências — 6º ano\n\n" +
  "Questão 1: Leia o texto sobre fotossíntese e explique como os cloroplastos utilizam luz solar, água e gás carbônico para produzir glicose e oxigênio.\n\n" +
  "Questão 2: Cite dois fatores ambientais que influenciam a velocidade desse processo.";

const SEED_STEP1_STATE = {
  textContent: SEED_MATERIAL,
  metadata: {
    source_type: "text",
    char_count: SEED_MATERIAL.length,
    word_count: SEED_MATERIAL.split(/\s+/).length,
    sanitized: false,
    pii_removed_count: 0,
    estimated_tokens: Math.max(1, Math.round(SEED_MATERIAL.length / 4)),
  },
  selectedFile: null,
  confirmedForStep2: true,
};

const SEED_SURGICAL_SELECTION = {
  status: "ok",
  message: "Seleção cirúrgica validada.",
  selected_ids: [
    "sobrecarga_memoria_trabalho_comandos_multiplos",
    "retencao_dados_intermediarios_problemas_multietapas",
  ],
  selected_count: 2,
  total_catalog_count: 8,
  untouched_dimensions_count: 6,
  untouched_characteristic_ids: [],
  scope_isolation_enforced: true,
  dominant_barriers: ["memoria_de_trabalho"],
  dua_principles: ["acao_e_expressao"],
  selected_characteristics: [],
};

const SEED_SCAFFOLDING = {
  nivel: 2,
  selected_ids: SEED_SURGICAL_SELECTION.selected_ids,
  conceitos_obrigatorios: ["fotossíntese", "cloroplastos", "glicose"],
  objetivo_avaliativo: "Explicar o processo de fotossíntese e fatores ambientais (EF06CI05).",
  invariantes_auditor: {
    blindagem_ativa: true,
    conceitos_obrigatorios: ["fotossíntese", "cloroplastos", "glicose"],
    termos_tecnicos_intocaveis: ["cloroplastos"],
    habilidade_bncc: "EF06CI05",
    alerta_anti_muleta_auditor: "Não fornecer a explicação pronta ao aluno.",
  },
};

const ALL_ROUTES = [
  {
    id: "login",
    path: "/",
    label: "Tela de Acesso (/)",
    waitForReady: async (page) => {
      const overlay = page.locator('div[role="presentation"][aria-label="Abertura da marca Íris"]');
      if ((await overlay.count()) > 0) {
        await overlay.waitFor({ state: "detached", timeout: 15_000 }).catch(() => {});
      }
      await page.locator("#login-email").waitFor({ state: "visible", timeout: 30_000 });
    },
    extraViewports: [],
  },
  {
    id: "etapa-1",
    path: "/etapa-1",
    label: "Etapa 1 (/etapa-1)",
    waitForReady: async (page) => {
      await page.locator("#conteudo-principal textarea").first().waitFor({ state: "visible", timeout: 30_000 });
    },
    extraViewports: [],
  },
  {
    id: "etapa-2",
    path: "/etapa-2",
    label: "Etapa 2 (/etapa-2)",
    seedSession: true,
    waitForReady: async (page) => {
      await page.locator('[role="checkbox"]').first().waitFor({ state: "visible", timeout: 30_000 });
    },
    extraViewports: [],
  },
  {
    id: "etapa-3",
    path: "/etapa-3",
    label: "Etapa 3 (/etapa-3)",
    seedSession: true,
    waitForReady: async (page) => {
      await page.getByRole("button", { name: /Confirmar nível e travas/i }).waitFor({ state: "visible", timeout: 30_000 });
    },
    extraViewports: [],
  },
  {
    id: "etapa-4",
    path: "/etapa-4",
    label: "Etapa 4 (/etapa-4)",
    seedSession: true,
    waitForReady: async (page) => {
      await page.getByRole("button", { name: /Executar Sistema Multiagentes/i }).waitFor({ state: "visible", timeout: 30_000 });
    },
    extraViewports: [],
  },
  {
    id: "etapa-5",
    path: "/etapa-5?demo=1",
    label: "Etapa 5 (/etapa-5?demo=1)",
    seedSession: true,
    waitForReady: async (page) => {
      await page.locator("#conteudo-principal textarea").first().waitFor({ state: "visible", timeout: 30_000 });
      for (const btn of await page.getByRole("button", { name: /Por que mudou/ }).all()) {
        const expanded = await btn.getAttribute("aria-expanded");
        if (expanded === "false") {
          await btn.click();
        }
      }
    },
    extraViewports: [768],
    checkEtapa5Layout: true,
  },
  {
    id: "historico",
    path: "/historico",
    label: "Histórico (/historico)",
    waitForReady: async (page) => {
      await page.locator("#conteudo-principal h1").waitFor({ state: "visible", timeout: 30_000 });
      await page
        .waitForFunction(
          () => !document.body.innerText.includes("Verificando sessão docente"),
          null,
          { timeout: 15_000 }
        )
        .catch(() => {});
    },
    extraViewports: [],
  },
];

const ROUTES = process.env.WCAG_ROUTES
  ? ALL_ROUTES.filter((r) => {
      const wanted = process.env.WCAG_ROUTES.split(",").map((s) => s.trim());
      return wanted.includes(r.path) || wanted.includes(r.id);
    })
  : ALL_ROUTES;

export function resolveChromeExecutable() {
  if (process.env.CHROME_PATH && fs.existsSync(process.env.CHROME_PATH)) {
    return process.env.CHROME_PATH;
  }
  try {
    const bundled = chromium.executablePath();
    if (bundled && fs.existsSync(bundled)) {
      return undefined; // usa Chromium padrão do Playwright
    }
  } catch {
    // fallback abaixo
  }
  const candidates = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return undefined;
}

async function applyThemeAndSeed(context, theme, seedSession) {
  await context.addInitScript(
    ({ themeName, shouldSeed, material, step1, surgical, scaffolding }) => {
      try {
        window.sessionStorage.setItem("iris.theme.dark_mode", themeName === "escuro" ? "true" : "false");
        window.sessionStorage.setItem("iris.theme.high_contrast", themeName === "alto-contraste" ? "true" : "false");
        if (shouldSeed) {
          window.sessionStorage.setItem("iris_step1_material_text", material);
          window.sessionStorage.setItem("iris_step1_state_v1", JSON.stringify(step1));
          window.sessionStorage.setItem("iris_step2_surgical_selection", JSON.stringify(surgical));
          window.sessionStorage.setItem("iris_step3_scaffolding_v1", JSON.stringify(scaffolding));
        }
      } catch {
        // Ignora se storage estiver restrito
      }
    },
    {
      themeName: theme,
      shouldSeed: Boolean(seedSession),
      material: SEED_MATERIAL,
      step1: SEED_STEP1_STATE,
      surgical: SEED_SURGICAL_SELECTION,
      scaffolding: SEED_SCAFFOLDING,
    }
  );
}

async function verifyThemeClasses(page, theme) {
  await page.waitForFunction(
    (expectedTheme) => {
      const cls = document.documentElement.classList;
      if (expectedTheme === "claro") return !cls.contains("dark") && !cls.contains("high-contrast");
      if (expectedTheme === "escuro") return cls.contains("dark") && !cls.contains("high-contrast");
      return cls.contains("dark") && cls.contains("high-contrast");
    },
    theme,
    { timeout: 20_000 }
  );
}

async function runAxeAudit(page) {
  await page.evaluate(axeSource);
  return await page.evaluate(async () => {
    // @ts-ignore - injetado dinamicamente
    return await window.axe.run(document, {
      runOnly: {
        type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
      },
    });
  });
}

async function checkLayoutAndTargets(page, { width, checkEtapa5Layout = false }) {
  return await page.evaluate(
    ({ viewportWidth, checkE5 }) => {
      const overflowPx = Math.max(0, document.documentElement.scrollWidth - window.innerWidth);
      const hasHorizontalOverflow = overflowPx > 1;

      const interactiveSelector = [
        "button",
        "a[href]",
        "input:not([type='hidden'])",
        "select",
        "textarea",
        "[role='button']",
        "[role='checkbox']",
        "[role='switch']",
        "[role='radio']",
        "[role='tab']",
      ].join(", ");

      const smallTargets = [];
      const seen = new Set();

      for (const el of document.querySelectorAll(interactiveSelector)) {
        if (seen.has(el)) continue;
        seen.add(el);

        if (el.closest("[aria-hidden='true']")) continue;
        if ("disabled" in el && el.disabled) continue;
        if (el.getAttribute("aria-disabled") === "true") continue;

        const style = window.getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden" || parseFloat(style.opacity) === 0) continue;

        if (el.classList.contains("sr-only") && document.activeElement !== el) continue;

        const rect = el.getBoundingClientRect();
        if (rect.width < 1 || rect.height < 1) continue;

        let effectiveHeight = rect.height;
        let effectiveWidth = rect.width;
        const tag = el.tagName.toLowerCase();
        const inputType = tag === "input" ? (el.getAttribute("type") || "").toLowerCase() : "";
        if (tag === "input" && (inputType === "checkbox" || inputType === "radio")) {
          const parentLabel = el.closest("label");
          if (parentLabel) {
            const lRect = parentLabel.getBoundingClientRect();
            effectiveHeight = Math.max(effectiveHeight, lRect.height);
            effectiveWidth = Math.max(effectiveWidth, lRect.width);
          }
        }

        const minSize = 43.5;
        if (effectiveHeight < minSize || effectiveWidth < minSize) {
          const text = (
            el.getAttribute("aria-label") ||
            el.textContent ||
            el.getAttribute("title") ||
            el.getAttribute("placeholder") ||
            el.id ||
            tag
          )
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 60);

          smallTargets.push({
            tag,
            text,
            width: Math.round(effectiveWidth * 10) / 10,
            height: Math.round(effectiveHeight * 10) / 10,
          });
        }
      }

      let etapa5Layout = null;
      if (checkE5) {
        const li = document.querySelector("li[aria-label='Questão 1']");
        if (li && li.children.length >= 2) {
          const [esq, dir] = [li.children[0].getBoundingClientRect(), li.children[1].getBoundingClientRect()];
          const ladoALado = dir.left > esq.left + 40 && Math.abs(dir.top - esq.top) < 8;
          const empilhado = dir.top > esq.bottom - 1;
          etapa5Layout = {
            ladoALado,
            empilhado,
            expected: viewportWidth >= 768 ? "lado-a-lado" : "empilhado",
            ok: viewportWidth >= 768 ? ladoALado : empilhado,
          };
        }
      }

      return {
        overflowPx: Math.round(overflowPx),
        hasHorizontalOverflow,
        smallTargets,
        etapa5Layout,
      };
    },
    { viewportWidth: width, checkE5: checkEtapa5Layout }
  );
}

async function checkKeyboardNavigation(page) {
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
    window.scrollTo(0, 0);
  });

  const maxTabs = 20;
  const visited = [];
  const missingFocusRing = [];
  let trapped = false;
  let lastSig = null;
  let shiftTabChecked = false;
  let shiftTabMoved = false;

  const readActiveInfo = async () =>
    await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) {
        return { isBody: true };
      }
      const style = window.getComputedStyle(el);
      const outlineWidth = parseFloat(style.outlineWidth) || 0;
      const hasOutline = style.outlineStyle !== "none" && outlineWidth >= 1.5;
      const hasBoxShadow = Boolean(style.boxShadow && style.boxShadow !== "none");
      const rect = el.getBoundingClientRect();
      const label = (
        el.getAttribute("aria-label") ||
        el.textContent ||
        el.getAttribute("placeholder") ||
        el.id ||
        el.tagName
      )
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 50);

      const sig = `${el.tagName}:${el.id || ""}:${el.getAttribute("name") || ""}:${label}:${Math.round(rect.top)}:${Math.round(rect.left)}`;
      return {
        isBody: false,
        tag: el.tagName.toLowerCase(),
        label,
        sig,
        hasVisibleFocus: hasOutline || hasBoxShadow,
        outlineStyle: style.outlineStyle,
        outlineWidth,
        boxShadow: style.boxShadow,
      };
    });

  for (let step = 0; step < maxTabs; step += 1) {
    await page.keyboard.press("Tab");
    const info = await readActiveInfo();

    if (info.isBody) {
      if (visited.length >= 3) break;
      continue;
    }

    if (lastSig && info.sig === lastSig) {
      trapped = true;
      break;
    }

    // Se deu volta completa para o primeiro elemento visitado, encerra sem erro
    if (visited.length >= 3 && info.sig === visited[0]) {
      break;
    }

    lastSig = info.sig;
    visited.push(info.sig);

    if (!info.hasVisibleFocus) {
      missingFocusRing.push(`${info.tag}("${info.label}")`);
    }

    // Valida navegação reversa (Shift+Tab) assim que alcança o 2º elemento focado real
    if (!shiftTabChecked && visited.length === 2) {
      shiftTabChecked = true;
      await page.keyboard.press("Shift+Tab");
      const backInfo = await readActiveInfo();
      shiftTabMoved = !backInfo.isBody && backInfo.sig !== info.sig;
      await page.keyboard.press("Tab");
    }
  }

  const uniqueVisited = new Set(visited).size;
  if (!shiftTabChecked) {
    shiftTabMoved = uniqueVisited < 2;
  }

  return {
    uniqueVisited,
    trapped,
    shiftTabMoved,
    missingFocusRing: Array.from(new Set(missingFocusRing)),
    ok: !trapped && uniqueVisited >= 3 && missingFocusRing.length === 0 && shiftTabMoved,
  };
}

function buildMarkdownReport(summary) {
  const lines = [];
  lines.push("# Auditoria WCAG 2.1 AA e Responsividade — Plataforma Íris (Issue #149 / RNF-09)");
  lines.push("");
  lines.push(`- **Executado em:** ${summary.generatedAt}`);
  lines.push(`- **Frontend:** \`${summary.frontendUrl}\``);
  lines.push(`- **Combinações auditadas:** ${summary.totals.combinations} (7 rotas × 3 temas × viewports mobile/desktop)`);
  lines.push(`- **Score médio axe-core (WCAG 2.1 AA):** **${summary.totals.averageAxeScore}/100** (mínimo observado: **${summary.totals.minAxeScore}/100**)`);
  lines.push(`- **Violações WCAG 2.1 AA (incluindo \`color-contrast\`):** **${summary.totals.totalViolations}**`);
  lines.push(`- **Estouros horizontais (responsividade):** **${summary.totals.totalOverflows}**`);
  lines.push(`- **Alvos interativos < 44px:** **${summary.totals.totalSmallTargets}**`);
  lines.push(`- **Falhas de navegação por teclado / foco visível:** **${summary.totals.totalKeyboardFailures}**`);
  lines.push(`- **Status geral:** **${summary.passed ? "APROVADO" : "REPROVADO"}**`);
  lines.push("");
  lines.push("## Resumo por Rota");
  lines.push("");
  lines.push("| Rota | Temas | Viewports | Violações WCAG | Overflow | Alvos < 44px | Teclado | Score axe-core |");
  lines.push("|---|---|---|---:|---:|---:|---|---:|");
  for (const r of summary.byRoute) {
    lines.push(
      `| \`${r.path}\` | ${r.themes.join(", ")} | ${r.viewports.join(", ")}px | ${r.violations} | ${r.overflows} | ${r.smallTargets} | ${r.keyboardFailures === 0 ? "OK" : `${r.keyboardFailures} falha(s)`} | **${r.minAxeScore}/100** |`
    );
  }
  lines.push("");
  return lines.join("\n");
}

async function main() {
  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });

  try {
    const resp = await fetch(`${FRONTEND_URL}/`);
    if (!resp.ok) {
      throw new Error(`Frontend retornou HTTP ${resp.status}`);
    }
  } catch (err) {
    throw new Error(
      `Não foi possível acessar o frontend em ${FRONTEND_URL}. Inicie o servidor antes de rodar a auditoria. Detalhe: ${err.message}`
    );
  }

  try {
    const h = await fetch(`${BACKEND_URL}/api/v1/health`);
    if (!h.ok) {
      console.warn(`[aviso] Backend em ${BACKEND_URL}/api/v1/health retornou HTTP ${h.status}`);
    }
  } catch {
    console.warn(`[aviso] Backend em ${BACKEND_URL} não respondeu; rotas que dependem da API podem usar fallback.`);
  }

  const executablePath = resolveChromeExecutable();
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  });

  const results = [];
  const failures = [];

  try {
    for (const route of ROUTES) {
      const routeViewports = Array.from(new Set([...VIEWPORTS, ...(route.extraViewports || [])])).sort((a, b) => a - b);

      for (const theme of THEMES) {
        const context = await browser.newContext({
          viewport: { width: routeViewports[0], height: 900 },
          deviceScaleFactor: 1,
          reducedMotion: "reduce",
        });
        await applyThemeAndSeed(context, theme, route.seedSession);
        const page = await context.newPage();

        const pageErrors = [];
        page.on("pageerror", (err) => pageErrors.push(err.message));

        const url = `${FRONTEND_URL}${route.path}`;
        await page.goto(url, { waitUntil: "domcontentloaded" });
        await route.waitForReady(page);
        await verifyThemeClasses(page, theme);
        await page.evaluate(axeSource);

        for (const width of routeViewports) {
          await page.setViewportSize({ width, height: 900 });
          await page.waitForTimeout(120);

          const axeResult = await page.evaluate(async () => {
            // @ts-ignore - injetado dinamicamente
            return await window.axe.run(document, {
              runOnly: {
                type: "tag",
                values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
              },
            });
          });

          const violations = (axeResult.violations || []).map((v) => ({
            id: v.id,
            impact: v.impact,
            help: v.help,
            nodes: (v.nodes || []).map((n) => ({
              target: n.target.join(" "),
              failureSummary: n.failureSummary,
              html: (n.html || "").slice(0, 140),
            })),
          }));

          const passesCount = (axeResult.passes || []).length;
          const totalRules = passesCount + violations.length;
          const axeScore = totalRules > 0 ? Math.round((passesCount / totalRules) * 100) : 100;

          const layout = await checkLayoutAndTargets(page, {
            width,
            checkEtapa5Layout: Boolean(route.checkEtapa5Layout),
          });

          let keyboard = null;
          if (width === 1280 || width === 375) {
            keyboard = await checkKeyboardNavigation(page);
          }

          const comboTag = `${route.path} [${theme} @ ${width}px]`;
          const comboFailures = [];

          if (pageErrors.length > 0) {
            comboFailures.push(`Erros de runtime JS: ${pageErrors.join(" | ")}`);
          }
          if (violations.length > 0) {
            for (const v of violations) {
              const sample = v.nodes[0]?.target || "";
              const summary = (v.nodes[0]?.failureSummary || v.help || "").replace(/\s+/g, " ").slice(0, 160);
              comboFailures.push(`WCAG ${v.id} (${v.impact}, ${v.nodes.length} nó(s)): ${sample} — ${summary}`);
            }
          }
          if (axeScore < 95) {
            comboFailures.push(`Score axe-core ${axeScore}/100 abaixo do mínimo 95/100`);
          }
          if (layout.hasHorizontalOverflow) {
            comboFailures.push(`Rolagem horizontal detectada (+${layout.overflowPx}px)`);
          }
          if (layout.etapa5Layout && !layout.etapa5Layout.ok) {
            comboFailures.push(`Layout da Etapa 5 deveria estar ${layout.etapa5Layout.expected}`);
          }
          if (layout.smallTargets.length > 0) {
            const sample = layout.smallTargets
              .slice(0, 8)
              .map((t) => `${t.tag}("${t.text}") ${t.width}x${t.height}px`)
              .join("; ");
            comboFailures.push(`${layout.smallTargets.length} alvo(s) interativo(s) < 44px: ${sample}`);
          }
          if (keyboard && !keyboard.ok) {
            const reasons = [];
            if (keyboard.trapped) reasons.push("armadilha de foco detectada");
            if (keyboard.uniqueVisited < 3) reasons.push(`apenas ${keyboard.uniqueVisited} elemento(s) alcançados por Tab`);
            if (!keyboard.shiftTabMoved) reasons.push("Shift+Tab não retornou o foco");
            if (keyboard.missingFocusRing.length > 0) {
              reasons.push(`sem contorno de foco visível em: ${keyboard.missingFocusRing.slice(0, 5).join(", ")}`);
            }
            comboFailures.push(`Teclado: ${reasons.join(" | ")}`);
          }

          const icon = comboFailures.length === 0 ? "OK" : "FALHA";
          console.log(
            `[${icon}] ${comboTag} — axe: ${axeScore}/100 (${violations.length} viol., ${passesCount} ok) | overflow: ${layout.overflowPx}px | <44px: ${layout.smallTargets.length}${
              keyboard ? ` | teclado: ${keyboard.ok ? "OK" : "FALHA"} (${keyboard.uniqueVisited} alvos)` : ""
            }`
          );
          for (const f of comboFailures) {
            console.log(`       -> ${f}`);
            failures.push({ combo: comboTag, detail: f });
          }

          results.push({
            routeId: route.id,
            path: route.path,
            theme,
            width,
            axeScore,
            passesCount,
            violationsCount: violations.length,
            violations,
            overflowPx: layout.overflowPx,
            hasHorizontalOverflow: layout.hasHorizontalOverflow,
            etapa5Layout: layout.etapa5Layout,
            smallTargetsCount: layout.smallTargets.length,
            smallTargets: layout.smallTargets,
            keyboard,
            pageErrors: [...pageErrors],
            passed: comboFailures.length === 0,
          });
        }

        await context.close();
      }
    }
  } finally {
    await browser.close();
  }

  const byRoute = ROUTES.map((route) => {
    const subset = results.filter((r) => r.routeId === route.id);
    return {
      routeId: route.id,
      path: route.path,
      label: route.label,
      themes: Array.from(new Set(subset.map((r) => r.theme))),
      viewports: Array.from(new Set(subset.map((r) => r.width))).sort((a, b) => a - b),
      violations: subset.reduce((acc, r) => acc + r.violationsCount, 0),
      overflows: subset.filter((r) => r.hasHorizontalOverflow).length,
      smallTargets: subset.reduce((acc, r) => acc + r.smallTargetsCount, 0),
      keyboardFailures: subset.filter((r) => r.keyboard && !r.keyboard.ok).length,
      minAxeScore: subset.length > 0 ? Math.min(...subset.map((r) => r.axeScore)) : 0,
      avgAxeScore:
        subset.length > 0 ? Math.round(subset.reduce((acc, r) => acc + r.axeScore, 0) / subset.length) : 0,
    };
  });

  const totals = {
    combinations: results.length,
    passedCombinations: results.filter((r) => r.passed).length,
    failedCombinations: results.filter((r) => !r.passed).length,
    totalViolations: results.reduce((acc, r) => acc + r.violationsCount, 0),
    totalOverflows: results.filter((r) => r.hasHorizontalOverflow).length,
    totalSmallTargets: results.reduce((acc, r) => acc + r.smallTargetsCount, 0),
    totalKeyboardFailures: results.filter((r) => r.keyboard && !r.keyboard.ok).length,
    minAxeScore: results.length > 0 ? Math.min(...results.map((r) => r.axeScore)) : 0,
    averageAxeScore:
      results.length > 0 ? Math.round(results.reduce((acc, r) => acc + r.axeScore, 0) / results.length) : 0,
  };

  const summary = {
    generatedAt: new Date().toISOString(),
    frontendUrl: FRONTEND_URL,
    passed: failures.length === 0 && totals.minAxeScore >= 95,
    totals,
    byRoute,
    failures,
    results,
  };

  const artifactJson = path.join(ARTIFACTS_DIR, "wcag-audit-report.json");
  const artifactMd = path.join(ARTIFACTS_DIR, "wcag-audit-report.md");
  fs.writeFileSync(artifactJson, JSON.stringify(summary, null, 2), "utf8");
  fs.writeFileSync(artifactMd, buildMarkdownReport(summary), "utf8");

  if (REPORT_PATH) {
    fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify(summary, null, 2), "utf8");
    const mdTarget = REPORT_PATH.replace(/\.json$/i, ".md");
    if (mdTarget !== REPORT_PATH) {
      fs.writeFileSync(mdTarget, buildMarkdownReport(summary), "utf8");
    }
  }

  console.log("\n================================================================================");
  console.log(
    `RESUMO WCAG 2.1 AA: ${totals.passedCombinations}/${totals.combinations} combinações aprovadas | ` +
      `score mín: ${totals.minAxeScore}/100 | viol.: ${totals.totalViolations} | ` +
      `overflow: ${totals.totalOverflows} | <44px: ${totals.totalSmallTargets} | teclado: ${totals.totalKeyboardFailures}`
  );
  console.log(`Relatório salvo em: ${artifactJson}`);
  console.log("================================================================================");

  if (!summary.passed && !DIAGNOSTIC_MODE) {
    process.exit(1);
  }
}

const isDirectRun = process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url;
if (isDirectRun) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
