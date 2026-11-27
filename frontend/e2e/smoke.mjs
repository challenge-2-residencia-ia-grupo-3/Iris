import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { chromium } from "playwright";
import { resolveChromeExecutable } from "./wcag-audit.mjs";

const require = createRequire(import.meta.url);

const FRONTEND_URL = (process.env.FRONTEND_URL || "http://127.0.0.1:3000").replace(/\/+$/, "");
const BACKEND_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const ARTIFACTS_DIR = process.env.ARTIFACTS_DIR || path.resolve(process.cwd(), "frontend/e2e/artifacts");

fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });

function assert(cond, message) {
  if (!cond) {
    throw new Error(`E2E Assertion failed: ${message}`);
  }
}

async function runAxeWithContrast(page, label, { strictContrast = true } = {}) {
  const axePath = require.resolve("axe-core/axe.min.js");
  await page.addScriptTag({ path: axePath });
  const results = await page.evaluate(async () => {
    // @ts-ignore - axe injected dynamically
    return await window.axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
    });
  });

  const violations = results.violations || [];
  const passes = results.passes || [];
  const totalRules = passes.length + violations.length;
  const score = totalRules > 0 ? Math.round((passes.length / totalRules) * 100) : 100;

  console.log(
    `[axe ${label}] score ${score}/100 — ${violations.length} violation(s), ${passes.length} pass(es) (WCAG 2.1 AA${
      strictContrast ? " + color-contrast" : ""
    } bloqueia).`
  );
  for (const v of violations) {
    const sample = (v.nodes || []).slice(0, 2).map((n) => n.target.join(" ")).join(", ");
    console.log(`  - [${v.impact}] ${v.id}: ${v.help} (${sample})`);
  }

  const blocking = violations.filter(
    (v) =>
      v.impact === "critical" ||
      v.impact === "serious" ||
      (strictContrast && v.id === "color-contrast")
  );
  assert(
    blocking.length === 0,
    `axe (${label}) encontrou ${blocking.length} violação(ões) bloqueante(s): ${blocking.map((c) => c.id).join(", ")}`
  );
  assert(score >= 95, `axe (${label}) score ${score}/100 abaixo do mínimo 95/100`);
  return violations;
}

async function main() {
  // 1. Healthcheck real do backend
  const healthResp = await fetch(`${BACKEND_URL}/api/v1/health`);
  assert(healthResp.ok, `/api/v1/health retornou HTTP ${healthResp.status}`);
  const health = await healthResp.json();
  assert(health.zero_student_database === true, "zero_student_database deve ser true");
  console.log("[1/5] Backend health OK:", {
    status: health.status,
    zero_student_database: health.zero_student_database,
    rag_backend: health.rag_backend,
  });

  // Verifica se autenticação/histórico com Postgres está ativa nesta branch
  let authEnabled = false;
  try {
    const provResp = await fetch(`${BACKEND_URL}/api/v1/auth/providers`);
    if (provResp.ok) {
      const prov = await provResp.json();
      authEnabled = Boolean(prov.database_online && prov.local_enabled);
      console.log("[info] Auth providers:", prov);
    }
  } catch {
    authEnabled = false;
  }

  const executablePath = resolveChromeExecutable();
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  });
  // reducedMotion: "reduce" garante regressão contínua contra travamento do preloader (PR #143/#145)
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();

  const pageErrors = [];
  const serverErrors = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));
  page.on("response", (resp) => {
    if (resp.status() >= 500) {
      serverErrors.push(`${resp.status()} ${resp.url()}`);
    }
  });

  const teacherEmail = `e2e.${Date.now()}@escola.edu.br`;

  try {
    // 2. Tela inicial (/): preloader sai sozinho + acessibilidade real em Chromium (com color-contrast)
    await page.goto(`${FRONTEND_URL}/`, { waitUntil: "networkidle" });

    const overlay = page.locator('div[role="presentation"][aria-label="Abertura da marca Íris"]');
    if ((await overlay.count()) > 0) {
      await overlay.waitFor({ state: "detached", timeout: 10_000 });
    }
    await page.getByLabel("E-mail").waitFor({ state: "visible", timeout: 10_000 });
    await runAxeWithContrast(page, "login", { strictContrast: true });
    console.log("[2/5] Tela de login & preloader em reduced-motion OK.");

    // 3. Autenticação real (se branch incluir /api/v1/auth com Postgres) ou Modo Convidado
    if (authEnabled) {
      await page.getByRole("button", { name: "Criar conta" }).click();
      await page.getByLabel("Nome de exibição").fill("Profa. E2E Real");
      await page.getByLabel("E-mail").fill(teacherEmail);
      await page.getByLabel(/^Senha/i).fill("SenhaE2EReal#2026");
      await page.locator('form button[type="submit"]').click();

      await page.waitForURL("**/etapa-1", { timeout: 15_000 });

      const storageCheck = await page.evaluate(() => ({
        sessionVal: window.sessionStorage.getItem("iris_teacher_auth_session_v1"),
        localVal: window.localStorage.getItem("iris_teacher_auth_session_v1"),
      }));
      assert(Boolean(storageCheck.sessionVal), "Sessão docente deve estar em sessionStorage");
      assert(storageCheck.localVal === null, "Sessão docente não deve ser gravada em localStorage");

      const headerText = await page.locator("header").innerText();
      assert(headerText.includes(teacherEmail), `Header deve exibir ${teacherEmail}, exibiu: ${headerText}`);
      console.log("[3/5] Cadastro real + sessionStorage + IrisHeader OK.");
    } else {
      await page.goto(`${FRONTEND_URL}/etapa-1`, { waitUntil: "networkidle" });
      console.log("[3/5] Fluxo convidado na Etapa 1 iniciado.");
    }

    // 4. Fluxo completo Etapas 1 -> 2 -> 3 -> 4 -> 5 com backend real + auditoria WCAG 2.1 AA em cada rota
    // Etapa 1: texto com PII real e 2 questões
    const textarea1 = page.locator("#conteudo-principal textarea").first();
    await textarea1.waitFor({ state: "visible", timeout: 10_000 });
    await runAxeWithContrast(page, "etapa-1", { strictContrast: true });
    await textarea1.fill(
      "Escola Municipal Cecília Meireles\n" +
        "Aluno: Gabriel Silva de Oliveira\n" +
        "CPF: 123.456.789-00\n\n" +
        "Questão 1: Leia o texto sobre fotossíntese e explique como os cloroplastos produzem glicose e oxigênio.\n\n" +
        "Questão 2: Cite dois fatores ambientais que alteram a velocidade desse processo."
    );

    const btnValidar = page.getByRole("button", { name: /Validar e Avançar para Etapa 2/i });
    await btnValidar.click();

    // Se houver PII detectado e sanitizado, o sistema pausa para conferência e muda botão para "Avançar para Etapa 2"
    await page.waitForFunction(
      () => {
        const ta = document.querySelector("#conteudo-principal textarea");
        return ta && !(ta instanceof HTMLTextAreaElement ? ta.value : "").includes("123.456.789-00");
      },
      null,
      { timeout: 15_000 }
    );

    if (page.url().includes("/etapa-1")) {
      const btnAvancar2 = page.getByRole("button", { name: /Avançar para Etapa 2/i });
      await btnAvancar2.click();
    }
    await page.waitForURL("**/etapa-2", { timeout: 15_000 });
    console.log("[4/5] Etapa 1 (PII Scrubber real) -> Etapa 2 OK.");

    // Etapa 2: selecionar a primeira característica funcional e avançar
    const firstCheckbox = page.locator('[role="checkbox"]').first();
    await firstCheckbox.waitFor({ state: "visible", timeout: 10_000 });
    await runAxeWithContrast(page, "etapa-2", { strictContrast: true });
    await firstCheckbox.click();
    await page.getByRole("button", { name: /Confirmar e Ir para Etapa 3/i }).first().click();
    await page.waitForURL("**/etapa-3", { timeout: 15_000 });

    // Etapa 3: calibrar andaime e avançar
    const btnEtapa3 = page.getByRole("button", { name: /Confirmar nível e travas/i });
    await btnEtapa3.waitFor({ state: "visible", timeout: 10_000 });
    await runAxeWithContrast(page, "etapa-3", { strictContrast: true });
    await btnEtapa3.click();
    await page.waitForURL("**/etapa-4", { timeout: 15_000 });

    // Etapa 4: executar multiagentes em modo extractive (determinístico) e avançar
    const btnExecutar = page.getByRole("button", { name: /Executar Sistema Multiagentes/i });
    await btnExecutar.waitFor({ state: "visible", timeout: 10_000 });
    await runAxeWithContrast(page, "etapa-4", { strictContrast: true });
    await btnExecutar.click();

    const btnParaEtapa5 = page.getByRole("button", { name: /Avançar para Etapa 5/i });
    await btnParaEtapa5.waitFor({ state: "visible", timeout: 25_000 });
    await btnParaEtapa5.click();
    await page.waitForURL("**/etapa-5", { timeout: 15_000 });

    // Etapa 5: verificar trava HITL real antes e depois da homologação + auditoria WCAG 2.1 AA
    const btnExportarPdf = page.getByRole("button", { name: /Exportar PDF/i });
    await btnExportarPdf.waitFor({ state: "visible", timeout: 15_000 });
    await runAxeWithContrast(page, "etapa-5", { strictContrast: true });
    assert(await btnExportarPdf.isDisabled(), "Exportar PDF deve ficar desabilitado antes da homologação (HITL)");

    const btnAprovarTodas = page.getByRole("button", { name: /Aprovar todas/i });
    if ((await btnAprovarTodas.count()) > 0) {
      await btnAprovarTodas.click();
    } else {
      const botoesQuestao = page.getByRole("button", { name: /^Aprovar questão$/i });
      const total = await botoesQuestao.count();
      assert(total > 0, "Nenhuma questão encontrada para aprovar na Etapa 5");
      for (let i = 0; i < total; i += 1) {
        await botoesQuestao.nth(0).click();
      }
    }
    const btnConfirmarRevisao = page.getByRole("button", { name: /Confirmar revisão final/i });
    await btnConfirmarRevisao.click();

    await page.getByRole("button", { name: /Revisão confirmada/i }).waitFor({ state: "visible", timeout: 10_000 });
    assert(await btnExportarPdf.isEnabled(), "Exportar PDF deve habilitar após confirmar revisão final");
    console.log("[4/5] Etapas 2 -> 3 -> 4 -> 5 (HITL real) OK.");

    // 5. Persistência real no Histórico + Exclusão LGPD (quando authEnabled) + auditoria WCAG em /historico
    if (authEnabled) {
      const btnSalvarHist = page.getByRole("button", { name: /Salvar no Meu Histórico/i });
      await btnSalvarHist.click();
      await page.getByText(/salva no seu histórico|Rascunho salvo/i).waitFor({ state: "visible", timeout: 15_000 });

      await page.goto(`${FRONTEND_URL}/historico`, { waitUntil: "networkidle" });
      await page.getByText(/1 atividade\(s\) encontrada\(s\)/i).waitFor({ state: "visible", timeout: 10_000 });
      await runAxeWithContrast(page, "historico-autenticado", { strictContrast: true });

      await page.getByRole("link", { name: /Revisar \/ Editar/i }).first().click();
      await page.waitForURL("**/etapa-5?historyId=*", { timeout: 15_000 });
      const btnPdfHist = page.getByRole("button", { name: /Exportar PDF/i });
      await btnPdfHist.waitFor({ state: "visible", timeout: 15_000 });
      assert(await btnPdfHist.isEnabled(), "Reabrir atividade homologada do histórico deve manter Exportar PDF habilitado");

      // Atualiza metadado e confirma que a atividade segue homologada no histórico
      await page.locator("#hist-disciplina").fill("Ciências Naturais");
      await page.getByRole("button", { name: /Atualizar no Meu Histórico/i }).click();
      await page.getByText(/Atividade homologada salva no seu histórico/i).waitFor({ state: "visible", timeout: 15_000 });
      assert(await btnPdfHist.isEnabled(), "Atualizar metadados não pode rebaixar atividade homologada");

      // Volta para /historico, confirma atualização persistida e testa exclusão da conta (LGPD)
      await page.goto(`${FRONTEND_URL}/historico`, { waitUntil: "networkidle" });
      await page.getByText(/Ciências Naturais/).first().waitFor({ state: "visible", timeout: 10_000 });
      await page.getByRole("button", { name: /Excluir minha conta e histórico/i }).click();
      await page.getByRole("button", { name: /Confirmar exclusão da conta/i }).click();
      await page.waitForURL(`${FRONTEND_URL}/`, { timeout: 15_000 });
      console.log("[5/5] Histórico no Postgres real + reabertura ?historyId + atualização homologada + exclusão LGPD OK.");
    } else {
      await page.goto(`${FRONTEND_URL}/historico`, { waitUntil: "networkidle" });
      await page.locator("#conteudo-principal h1").waitFor({ state: "visible", timeout: 10_000 });
      await runAxeWithContrast(page, "historico-convidado", { strictContrast: true });
      console.log("[5/5] Histórico docente em modo convidado auditado com WCAG 2.1 AA.");
    }

    assert(pageErrors.length === 0, `Erros de runtime no navegador: ${pageErrors.join(" | ")}`);
    assert(serverErrors.length === 0, `Respostas HTTP >= 500 observadas: ${serverErrors.join(" | ")}`);
    console.log("E2E REAL CONCLUÍDO COM SUCESSO!");
  } catch (err) {
    try {
      await page.screenshot({ path: path.join(ARTIFACTS_DIR, "failure.png"), fullPage: true });
    } catch {
      // Ignora erro ao capturar screenshot
    }
    throw err;
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
