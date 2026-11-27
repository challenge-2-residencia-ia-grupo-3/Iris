// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/contexts/AuthContext";
import { ThemeProvider } from "../src/contexts/ThemeContext";
import { Step1MaterialIntake } from "../src/components/Step1MaterialIntake";
import { Step2FunctionalProfile } from "../src/components/Step2FunctionalProfile";
import { Step4AgentAdaptation } from "../src/components/Step4AgentAdaptation";
import HistoricoPage from "../src/app/historico/page";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: pushMock }),
  usePathname: () => "/etapa-1",
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

async function runAxeNoViolations(container: HTMLElement) {
  const result = await axe.run(container, {
    runOnly: {
      type: "tag",
      values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
    },
    rules: {
      // jsdom não calcula cores/layout; contraste e alvos reais são validados no Chromium via wcag-audit.mjs
      "color-contrast": { enabled: false },
    },
  });
  return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`);
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
  document.documentElement.classList.remove("dark", "high-contrast");
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
});

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  window.localStorage.clear();
  document.documentElement.classList.remove("dark", "high-contrast");
  vi.unstubAllGlobals();
  pushMock.mockReset();
});

describe("Auditoria WCAG 2.1 AA nas Etapas 1, 2, 4 e /historico (Issue #149 / RNF-09)", () => {
  it("Etapa 1 passa no axe-core sem violações e mantém alvo >= 44px no cabeçalho e importação", async () => {
    const { container } = render(
      <ThemeProvider>
        <AuthProvider>
          <Step1MaterialIntake />
        </AuthProvider>
      </ThemeProvider>
    );

    expect(await runAxeNoViolations(container)).toEqual([]);

    const btnAltoContraste = screen.getByRole("button", { name: /Alternar modo de alto contraste/i });
    expect(btnAltoContraste.className).toContain("min-h-[44px]");
    expect(btnAltoContraste.className).toContain("min-w-[44px]");

    const btnImportar = screen.getByRole("button", { name: /Importar perfil/i });
    expect(btnImportar.className).toContain("min-h-[44px]");
  });

  it("Etapa 2 passa no axe-core sem controles interativos aninhados (nested-interactive)", async () => {
    const { container } = render(
      <ThemeProvider>
        <AuthProvider>
          <Step2FunctionalProfile />
        </AuthProvider>
      </ThemeProvider>
    );

    await waitFor(() => {
      expect(screen.getAllByRole("checkbox").length).toBeGreaterThan(0);
    });

    expect(await runAxeNoViolations(container)).toEqual([]);

    // Garante que nenhum elemento role="checkbox" contém botão clicável aninhado
    const checkboxes = container.querySelectorAll('[role="checkbox"]');
    for (const cb of Array.from(checkboxes)) {
      expect(cb.querySelector("button, a, input, select, textarea")).toBeNull();
    }

    // Garante alternância funcional do modo Alto Contraste e Modo Escuro via cabeçalho
    const btnAltoContraste = screen.getByRole("button", { name: /Alternar modo de alto contraste/i });
    fireEvent.click(btnAltoContraste);
    expect(document.documentElement.classList.contains("high-contrast")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("Etapa 4 passa no axe-core sem violações WCAG 2.1 AA", async () => {
    const { container } = render(
      <ThemeProvider>
        <AuthProvider>
          <Step4AgentAdaptation />
        </AuthProvider>
      </ThemeProvider>
    );

    expect(await runAxeNoViolations(container)).toEqual([]);
  });

  it("Histórico (/historico) passa no axe-core e preserva alvos >= 44px no cabeçalho", async () => {
    const { container } = render(
      <ThemeProvider>
        <AuthProvider>
          <HistoricoPage />
        </AuthProvider>
      </ThemeProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: /Histórico de Atividades Adaptadas/i })).toBeTruthy();
    });

    expect(await runAxeNoViolations(container)).toEqual([]);

    const btnAltoContraste = screen.getByRole("button", { name: /Alternar modo de alto contraste/i });
    expect(btnAltoContraste.className).toContain("min-h-[44px]");
    expect(btnAltoContraste.className).toContain("min-w-[44px]");
  });
});
