// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Step3ScaffoldingLevel } from "../src/components/Step3ScaffoldingLevel";
import { ThemeProvider } from "../src/contexts/ThemeContext";
import { STEP1_MATERIAL_STORAGE_KEY } from "../src/services/catalogsApi";
import { SCAFFOLDING_STORAGE_KEY } from "../src/services/scaffoldingApi";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

async function violacoes(container: HTMLElement) {
  const r = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`);
}

beforeEach(() => {
  window.sessionStorage.clear();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
});

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("Etapa 3 (Histórias 1.3.1 e 1.3.2): Travas Curriculares, Anti-Muleta e Acessibilidade WCAG 2.1 AA", () => {
  it("extrai automaticamente os conceitos e o objetivo do material da Etapa 1 e passa no axe-core", async () => {
    window.sessionStorage.setItem(
      STEP1_MATERIAL_STORAGE_KEY,
      "Questão 1 (EF06CI05): Explique como os cloroplastos utilizam a luz solar para produzir glicose na fotossíntese."
    );

    const { container } = render(
      <ThemeProvider>
        <Step3ScaffoldingLevel />
      </ThemeProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("cloroplastos")).toBeTruthy();
      expect(screen.getByText("fotossíntese")).toBeTruthy();
    });

    expect(screen.getByText(/Extraído automaticamente do material/i)).toBeTruthy();
    expect(await violacoes(container)).toEqual([]);
  });

  it("permite adicionar e remover conceitos e exibe alerta preventivo anti-muleta em contradição pedagógica", async () => {
    const { container } = render(
      <ThemeProvider>
        <Step3ScaffoldingLevel />
      </ThemeProvider>
    );

    const inputConceito = screen.getByLabelText(/Conceitos e termos obrigatórios/i);
    fireEvent.change(inputConceito, { target: { value: "ironia, sentido figurado" } });
    fireEvent.keyDown(inputConceito, { key: "Enter" });

    expect(screen.getByText("ironia")).toBeTruthy();
    expect(screen.getByText("sentido figurado")).toBeTruthy();

    // Digita objetivo com contradição direta (avalia interpretação de texto + pede resumo interpretativo)
    const inputObjetivo = screen.getByLabelText(/Objetivo avaliativo ou habilidade da BNCC/i);
    fireEvent.change(inputObjetivo, {
      target: {
        value:
          "Avaliar interpretação de texto e inferência na crônica e incluir resumo interpretativo do texto.",
      },
    });

    await waitFor(() => {
      expect(screen.getByTestId("alerta-preventivo-antimuleta")).toBeTruthy();
    });

    const alerta = screen.getByTestId("alerta-preventivo-antimuleta");
    expect(alerta.textContent?.toLowerCase()).toContain("resumo interpretativo");
    expect(await violacoes(container)).toEqual([]);

    // Remove um conceito
    const btnRemover = screen.getByRole("button", { name: /Remover conceito ironia/i });
    fireEvent.click(btnRemover);
    expect(screen.queryByText("ironia")).toBeNull();

    // Verifica persistência na sessão
    const saved = window.sessionStorage.getItem(SCAFFOLDING_STORAGE_KEY);
    expect(saved).toBeTruthy();
  });

  it("limpa sessão e bloqueia avanço quando o backend rejeita a trava com HTTP 422", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          detail: {
            code: "CLINICAL_REFERENCE_FORBIDDEN",
            detail: "Não utilize rótulos clínicos ou CID na trava curricular.",
          },
        }),
      })
    );

    render(
      <ThemeProvider>
        <Step3ScaffoldingLevel />
      </ThemeProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/Erro na validação da Etapa 3/i)).toBeTruthy();
    });

    const confirmBtn = screen.getByRole("button", { name: /Confirmar nível e travas/i }) as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);
    expect(window.sessionStorage.getItem(SCAFFOLDING_STORAGE_KEY)).toBeNull();
  });
});
