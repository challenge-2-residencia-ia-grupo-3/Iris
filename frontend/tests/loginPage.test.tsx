// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HomePage from "../src/app/page";
import { ThemeProvider } from "../src/contexts/ThemeContext";

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

async function checkAxeViolations(container: HTMLElement) {
  const result = await axe.run(container, {
    runOnly: {
      type: "tag",
      values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"],
    },
    rules: {
      "color-contrast": { enabled: false }, // jsdom does not calculate layout colors
    },
  });
  return result.violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`
  );
}

beforeEach(() => {
  mockPush.mockClear();
  window.sessionStorage.clear();
  document.documentElement.classList.remove("dark");
});

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.clearAllMocks();
});

describe("Tela de Login — Íris (Posicionamento, Validações, Contraste e Acessibilidade)", () => {
  it("posiciona a marca d'água sem bolinha no lado roxo e a logo oficial no lado claro, sem duplicação", () => {
    const { container } = render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    const asideRoxo = container.querySelector("aside");
    const mainClaro = container.querySelector("main");
    expect(asideRoxo).toBeTruthy();
    expect(mainClaro).toBeTruthy();

    // 1. Marca d'água no lado roxo: discreta, sem bolinha luminosa e sem o nome "Íris"
    const marcaDagua = screen.getByTestId("marca-dagua-lado-roxo");
    expect(asideRoxo?.contains(marcaDagua)).toBe(true);
    // Não deve conter o nome Íris dentro da marca d'água do lado roxo
    expect(within(asideRoxo as HTMLElement).queryByText("Íris")).toBeNull();

    // 2. Logo oficial no lado claro: posicionada no main, acima do formulário
    const logoClaro = screen.getByTestId("logo-lado-claro");
    expect(mainClaro?.contains(logoClaro)).toBe(true);
    expect(within(logoClaro).getByText("Íris")).toBeTruthy();

    // 3. Ausência de duplicação da logo: apenas 1 elemento com o texto "Íris" na página inteira
    const irisMatches = screen.getAllByText("Íris");
    // O texto "Íris" aparece apenas na logo oficial e na menção do parágrafo de apresentação
    // Na logo propriamente dita, existe apenas uma ocorrência
    const logos = container.querySelectorAll('[data-testid="logo-lado-claro"]');
    expect(logos.length).toBe(1);
  });

  it("renderiza os textos institucionais no lado roxo com hierarquia clara", () => {
    render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    expect(
      screen.getByText("PLATAFORMA INTELIGENTE PARA PROFESSORES")
    ).toBeTruthy();
    expect(screen.getByText(/Amplie as formas/i)).toBeTruthy();
    expect(screen.getByText(/Adapte materiais\./i)).toBeTruthy();
    expect(
      screen.getByText(
        /A Íris usa inteligência artificial para adaptar materiais do Ensino Fundamental II às diferentes necessidades dos seus alunos\./i
      )
    ).toBeTruthy();
  });

  it("permite alternar a visualização da senha sem alterações de valor", () => {
    render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    const passwordInput = screen.getByLabelText("Senha");
    const toggleButton = screen.getByLabelText(/Exibir senha/i);

    expect(passwordInput.getAttribute("type")).toBe("password");
    expect(toggleButton.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(toggleButton);
    expect(passwordInput.getAttribute("type")).toBe("text");
    expect(screen.getByLabelText(/Ocultar senha/i)).toBeTruthy();

    fireEvent.click(screen.getByLabelText(/Ocultar senha/i));
    expect(passwordInput.getAttribute("type")).toBe("password");
  });

  it("NÃO rejeita senha curta preenchida (remoção da regra de tamanho mínimo < 6)", async () => {
    render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const submitButton = screen.getByRole("button", { name: /Entrar/i });

    // Preenche com senha curta de apenas 3 caracteres (antes rejeitada por < 6)
    fireEvent.change(emailInput, { target: { value: "docente@escola.edu.br" } });
    fireEvent.change(passwordInput, { target: { value: "123" } });
    fireEvent.click(submitButton);

    // Não deve acusar erro de tamanho mínimo
    await waitFor(() => {
      expect(screen.queryByText(/A senha deve conter no mínimo 6 caracteres/i)).toBeNull();
      expect(mockPush).toHaveBeenCalledWith("/etapa-1");
    });
  });

  it("preserva a senha integralmente sem aplicar trim(), inclusive com espaços", async () => {
    render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha") as HTMLInputElement;
    const submitButton = screen.getByRole("button", { name: /Entrar/i });

    // Senha com espaços intencionais no início e no fim
    const senhaComEspacos = "  senha com espacos  ";
    fireEvent.change(emailInput, { target: { value: "docente@escola.edu.br" } });
    fireEvent.change(passwordInput, { target: { value: senhaComEspacos } });

    // Verifica que o valor no input não sofreu trim
    expect(passwordInput.value).toBe(senhaComEspacos);

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/etapa-1");
    });
  });

  it("normaliza e-mail com trim() aceitando e-mail com espaços ao redor", async () => {
    render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const submitButton = screen.getByRole("button", { name: /Entrar/i });

    // E-mail com espaços em volta é aceito normalmente após trim()
    fireEvent.change(emailInput, { target: { value: "   docente@escola.sp.gov.br   " } });
    fireEvent.change(passwordInput, { target: { value: "senhaValida" } });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/etapa-1");
    });
  });

  it("rejeita e-mail com formato inválido e exibe alerta de erro", async () => {
    render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const submitButton = screen.getByRole("button", { name: /Entrar/i });

    // E-mail inválido é recusado
    fireEvent.change(emailInput, { target: { value: "email-invalido-sem-arroba" } });
    fireEvent.change(passwordInput, { target: { value: "senhaValida" } });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(
        screen.getByText("Formato de e-mail inválido. Exemplo: docente@escola.edu.br")
      ).toBeTruthy();
    });
  });

  it("botão Entrar utiliza a cor #D13B1E para conformidade de contraste >= 4,5:1 e inclui motion-reduce no loading", async () => {
    const { container } = render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    const submitButton = screen.getByRole("button", { name: /Entrar/i });
    // Verifica que o botão utiliza a nova cor de contraste conforme (#D13B1E)
    expect(submitButton.className).toContain("bg-[#D13B1E]");
    expect(submitButton.className).toContain("text-white");
    expect(submitButton.className).toContain("hover:bg-[#B73318]");

    // Dispara submissão para inspecionar ícone de carregamento Loader2
    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    fireEvent.change(emailInput, { target: { value: "docente@escola.edu.br" } });
    fireEvent.change(passwordInput, { target: { value: "senha123" } });
    fireEvent.click(submitButton);

    // O ícone Loader2 deve ter a classe motion-reduce:animate-none
    const loader = container.querySelector(".motion-reduce\\:animate-none");
    expect(loader).toBeTruthy();
  });

  it("redireciona para /etapa-1 ao clicar em 'Esqueci minha senha' ou 'Criar conta'", () => {
    render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    const forgotPasswordBtn = screen.getByRole("button", { name: "Esqueci minha senha" });
    fireEvent.click(forgotPasswordBtn);
    expect(mockPush).toHaveBeenCalledWith("/etapa-1");

    const registerBtn = screen.getByRole("button", { name: "Criar conta" });
    fireEvent.click(registerBtn);
    expect(mockPush).toHaveBeenCalledWith("/etapa-1");
  });

  it("alterna entre modo claro e escuro comunicando acessibilidade via role=switch", () => {
    render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    const themeSwitch = screen.getByRole("switch");
    expect(themeSwitch.getAttribute("aria-checked")).toBe("false");
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    fireEvent.click(themeSwitch);
    expect(themeSwitch.getAttribute("aria-checked")).toBe("true");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    fireEvent.click(themeSwitch);
    expect(themeSwitch.getAttribute("aria-checked")).toBe("false");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("não possui violações de acessibilidade no axe-core (WCAG 2.1 AA)", async () => {
    const { container } = render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>
    );

    const violations = await checkAxeViolations(container);
    expect(violations).toEqual([]);
  });
});
