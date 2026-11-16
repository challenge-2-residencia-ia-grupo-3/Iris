// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { JustificativaCard } from "../src/components/JustificativaCard";
import { ReviewEditor } from "../src/components/ReviewEditor";
import catalogoRaw from "../../rag/catalogs/tdah_caracteristicas_funcionais.json";
import type { CharacteristicItem } from "../src/services/catalogsApi";
import { indicadoresAndaime, montarCartao } from "../src/services/comparisonCards";
import { ETAPA5_DEMO } from "../src/services/etapa5Demo";
import type { SessaoRevisao } from "../src/services/sessionReview";

const CATALOGO = catalogoRaw.caracteristicas as unknown as CharacteristicItem[];
afterEach(cleanup);

const sessao: SessaoRevisao = {
  id: "s1",
  titulo: "Aula",
  revisao: 0,
  homologada: false,
  pode_exportar: false,
  pode_homologar: false,
  versao_final: "",
  questoes: ETAPA5_DEMO.questoes.map((q) => ({ id: q.id, original: q.original, adaptado: q.adaptado, aprovada: false, editada: false })),
};

const tela = () => (
  <main>
    <h1>Revisão</h1>
    <ReviewEditor
      sessao={sessao}
      extras={(q, i) => {
        const d = ETAPA5_DEMO.questoes[i];
        return <JustificativaCard numero={i + 1} cartao={montarCartao(d, CATALOGO)} original={q.original} adaptado={q.adaptado} indicadores={indicadoresAndaime(q.adaptado)} />;
      }}
    />
  </main>
);

// jsdom não calcula layout nem cor: contraste e quebra de linha são verificados no navegador real (e2e) e em contraste.test.
async function violacoes(container: HTMLElement) {
  const r = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`);
}

describe("Etapa 5: acessibilidade (WCAG 2.1 AA)", () => {
  it("sem violações do axe com os cartões fechados", async () => {
    const { container } = render(tela());
    expect(await violacoes(container)).toEqual([]);
  });

  it("sem violações do axe com os cartões abertos", async () => {
    const { container } = render(tela());
    for (const b of screen.getAllByRole("button", { name: /Por que mudou/ })) fireEvent.click(b);
    expect(await violacoes(container)).toEqual([]);
  });

  it("cartão retrátil é um disclosure: aria-expanded, aria-controls e região com nome", () => {
    render(tela());
    const botao = screen.getAllByRole("button", { name: /Por que mudou · questão 1/ })[0];
    expect(botao.getAttribute("aria-expanded")).toBe("false");
    const painel = document.getElementById(botao.getAttribute("aria-controls")!)!;
    expect(painel.hasAttribute("hidden")).toBe(true);
    fireEvent.click(botao);
    expect(botao.getAttribute("aria-expanded")).toBe("true");
    expect(painel.hasAttribute("hidden")).toBe(false);
    const regiao = screen.getByRole("region", { name: "Justificativa pedagógica da questão 1" });
    expect(within(regiao).getByText(/Característica funcional tratada/)).toBeTruthy();
    expect(within(regiao).getByText(/DUA I+/)).toBeTruthy();
    fireEvent.click(botao);
    expect(botao.getAttribute("aria-expanded")).toBe("false");
  });

  it("o cartão cita característica funcional e diretriz do DUA", () => {
    render(tela());
    fireEvent.click(screen.getAllByRole("button", { name: /Por que mudou · questão 1/ })[0]);
    const regiao = screen.getByRole("region", { name: "Justificativa pedagógica da questão 1" });
    expect(within(regiao).getAllByText(/Sobrecarga de memória de trabalho/).length).toBeGreaterThan(0);
    expect(regiao.textContent).toMatch(/DUA Diretriz/);
  });

  it("indicadores de andaime têm texto (não dependem só de cor ou ícone)", () => {
    render(tela());
    const lista = screen.getByRole("list", { name: "Andaimes aplicados na questão 1" });
    const itens = within(lista).getAllByRole("listitem");
    expect(itens.length).toBeGreaterThan(0);
    for (const li of itens) expect((li.textContent ?? "").trim().length).toBeGreaterThan(5);
    expect(lista.querySelectorAll("svg[aria-hidden='true']").length).toBe(itens.length);
  });

  it("trecho novo é sublinhado, em negrito e anunciado por leitor de tela", () => {
    render(tela());
    fireEvent.click(screen.getAllByRole("button", { name: /Por que mudou · questão 1/ })[0]);
    const aviso = document.querySelector("ins .sr-only");
    expect(aviso?.textContent).toMatch(/trecho acrescentado/);
    expect(aviso?.closest("ins")?.className).toMatch(/underline/);
    expect(aviso?.closest("ins")?.className).toMatch(/font-bold/);
  });

  it("toda caixa de edição tem rótulo associado e a aprovação expõe aria-pressed", () => {
    render(tela());
    for (const ta of screen.getAllByRole("textbox")) expect(ta.id && document.querySelector(`label[for='${ta.id}']`)).toBeTruthy();
    const aprovar = screen.getAllByRole("button", { name: /Aprovar questão/ })[0];
    expect(aprovar.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(aprovar);
    expect(screen.getAllByRole("button", { name: /Questão aprovada/ })[0].getAttribute("aria-pressed")).toBe("true");
  });

  it("a exportação segue bloqueada na tela até a homologação", () => {
    render(tela());
    for (const b of screen.getAllByRole("button", { name: /Exportar/ })) expect((b as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Confirmar revisão final/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("Etapa 5: responsividade (classes de layout; a medição real fica no e2e)", () => {
  it("cada questão empilha em telas estreitas e vira duas colunas a partir de md", () => {
    render(tela());
    const linhas = screen.getAllByRole("listitem", { name: /^Questão \d$/ });
    expect(linhas).toHaveLength(2);
    for (const li of linhas) {
      expect(li.className).toContain("grid-cols-1");
      expect(li.className).toContain("md:grid-cols-2");
      expect(li.className).toContain("gap-3");
    }
  });

  it("colunas e textos longos não estouram a largura (min-w-0 e quebra de palavra)", () => {
    render(tela());
    const linha = screen.getAllByRole("listitem", { name: "Questão 1" })[0];
    for (const filho of Array.from(linha.children)) expect(filho.className).toContain("min-w-0");
    expect(linha.querySelector("p.break-words")).toBeTruthy();
  });

  it("alvos de toque dos cartões têm pelo menos 44px de altura", () => {
    render(tela());
    for (const b of screen.getAllByRole("button", { name: /Por que mudou/ })) expect(b.className).toContain("min-h-[44px]");
  });
});
