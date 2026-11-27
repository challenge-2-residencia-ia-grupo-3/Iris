// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HomePage from "../src/app/page";
import { AuthProvider } from "../src/contexts/AuthContext";
import { ThemeProvider } from "../src/contexts/ThemeContext";
import { AuthApiError, type AuthSession } from "../src/services/authApi";

const mockPush = vi.fn();
const mockLoginTeacher = vi.fn();
const mockRegisterTeacher = vi.fn();
const mockFetchAuthProviders = vi.fn();

let mockOverlayHandlers: {
  onExitStart?: () => void;
  onFinished?: () => void;
} | null = null;

let autoFinishIntro = true;

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/services/authApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/services/authApi")>();
  return {
    ...actual,
    fetchAuthProviders: (...args: Parameters<typeof actual.fetchAuthProviders>) => mockFetchAuthProviders(...args),
    loginTeacher: (...args: Parameters<typeof actual.loginTeacher>) => mockLoginTeacher(...args),
    registerTeacher: (...args: Parameters<typeof actual.registerTeacher>) => mockRegisterTeacher(...args),
  };
});

vi.mock("@/components/iris-intro/IrisIntroOverlay", () => ({
  IrisIntroOverlay: ({
    onExitStart,
    onFinished,
  }: {
    onExitStart?: () => void;
    onFinished: () => void;
  }) => {
    mockOverlayHandlers = { onExitStart, onFinished };
    React.useEffect(() => {
      if (autoFinishIntro) {
        onExitStart?.();
        onFinished();
      }
    }, [onExitStart, onFinished]);
    return <div data-testid="iris-intro-overlay" role="presentation" />;
  },
}));

const SAMPLE_SESSION: AuthSession = {
  token_type: "bearer",
  access_token: "jwt-token-test",
  refresh_token: "refresh-token-test",
  expires_in: 1800,
  teacher: {
    id: "prof-1",
    email: "docente@escola.edu.br",
    email_verificado: true,
    nome_exibicao: "Profa. Marina",
    possui_senha_local: true,
    oauth_providers: [],
    criado_em: "2026-11-26T12:00:00Z",
  },
};

function renderHome() {
  return render(
    <ThemeProvider>
      <AuthProvider>
        <HomePage />
      </AuthProvider>
    </ThemeProvider>
  );
}

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
  autoFinishIntro = true;
  mockOverlayHandlers = null;
  mockPush.mockClear();
  mockLoginTeacher.mockReset().mockResolvedValue(SAMPLE_SESSION);
  mockRegisterTeacher.mockReset().mockResolvedValue(SAMPLE_SESSION);
  mockFetchAuthProviders.mockReset().mockResolvedValue({
    local_enabled: true,
    google_enabled: false,
    guest_mode_enabled: true,
    database_online: true,
  });
  window.sessionStorage.clear();
  window.localStorage.clear();
  document.documentElement.classList.remove("dark");
});

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  window.localStorage.clear();
  vi.clearAllMocks();
  autoFinishIntro = true;
  mockOverlayHandlers = null;
});

describe("Tela de Login — Íris (Posicionamento, Validações, Autenticação e Acessibilidade)", () => {
  it("posiciona a marca d'água sem bolinha no lado roxo e a logo oficial no lado claro, sem duplicação", () => {
    const { container } = renderHome();

    const asideRoxo = container.querySelector("aside");
    const mainClaro = container.querySelector("main");
    expect(asideRoxo).toBeTruthy();
    expect(mainClaro).toBeTruthy();

    const marcaDagua = screen.getByTestId("marca-dagua-lado-roxo");
    expect(asideRoxo?.contains(marcaDagua)).toBe(true);
    expect(within(asideRoxo as HTMLElement).queryByText("Íris")).toBeNull();

    const logoClaro = screen.getByTestId("logo-lado-claro");
    expect(mainClaro?.contains(logoClaro)).toBe(true);
    expect(within(logoClaro).getByText("Íris")).toBeTruthy();

    const logos = container.querySelectorAll('[data-testid="logo-lado-claro"]');
    expect(logos.length).toBe(1);
  });

  it("renderiza os textos institucionais no lado roxo com hierarquia clara", () => {
    renderHome();

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
    renderHome();

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

  it("NÃO rejeita senha curta preenchida no modo login (remoção da regra de tamanho mínimo < 6)", async () => {
    renderHome();

    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const submitButton = screen.getByRole("button", { name: /^Entrar$/i });

    fireEvent.change(emailInput, { target: { value: "docente@escola.edu.br" } });
    fireEvent.change(passwordInput, { target: { value: "123" } });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.queryByText(/A senha deve conter no mínimo/i)).toBeNull();
      expect(mockLoginTeacher).toHaveBeenCalledWith({
        email: "docente@escola.edu.br",
        senha: "123",
      });
      expect(mockPush).toHaveBeenCalledWith("/etapa-1");
    });
  });

  it("preserva a senha integralmente sem aplicar trim(), inclusive com espaços", async () => {
    renderHome();

    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha") as HTMLInputElement;
    const submitButton = screen.getByRole("button", { name: /^Entrar$/i });

    const senhaComEspacos = "  senha com espacos  ";
    fireEvent.change(emailInput, { target: { value: "docente@escola.edu.br" } });
    fireEvent.change(passwordInput, { target: { value: senhaComEspacos } });

    expect(passwordInput.value).toBe(senhaComEspacos);

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockLoginTeacher).toHaveBeenCalledWith({
        email: "docente@escola.edu.br",
        senha: senhaComEspacos,
      });
      expect(mockPush).toHaveBeenCalledWith("/etapa-1");
    });
  });

  it("normaliza e-mail com trim() aceitando e-mail com espaços ao redor", async () => {
    renderHome();

    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const submitButton = screen.getByRole("button", { name: /^Entrar$/i });

    fireEvent.change(emailInput, { target: { value: "   docente@escola.sp.gov.br   " } });
    fireEvent.change(passwordInput, { target: { value: "senhaValida" } });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockLoginTeacher).toHaveBeenCalledWith({
        email: "docente@escola.sp.gov.br",
        senha: "senhaValida",
      });
      expect(mockPush).toHaveBeenCalledWith("/etapa-1");
    });
  });

  it("rejeita e-mail com formato inválido e exibe alerta de erro", async () => {
    renderHome();

    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const submitButton = screen.getByRole("button", { name: /^Entrar$/i });

    fireEvent.change(emailInput, { target: { value: "email-invalido-sem-arroba" } });
    fireEvent.change(passwordInput, { target: { value: "senhaValida" } });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(
        screen.getByText("Formato de e-mail inválido. Exemplo: docente@escola.edu.br")
      ).toBeTruthy();
    });
    expect(mockLoginTeacher).not.toHaveBeenCalled();
  });

  it("exibe erro do servidor quando as credenciais são inválidas", async () => {
    mockLoginTeacher.mockRejectedValueOnce(
      new AuthApiError("E-mail ou senha inválidos.", "INVALID_CREDENTIALS", 401)
    );
    renderHome();

    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "docente@escola.edu.br" } });
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "errada" } });
    fireEvent.click(screen.getByRole("button", { name: /^Entrar$/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain("E-mail ou senha inválidos.");
    });
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("botão Entrar utiliza #D13B1E, foco ring-2 e motion-reduce no loading", async () => {
    const { container } = renderHome();

    const submitButton = screen.getByRole("button", { name: /^Entrar$/i });
    expect(submitButton.className).toContain("bg-[#D13B1E]");
    expect(submitButton.className).toContain("text-white");
    expect(submitButton.className).toContain("hover:bg-[#B73318]");
    expect(submitButton.className).toContain("focus-visible:ring-2");

    let resolveLogin!: (v: AuthSession) => void;
    mockLoginTeacher.mockImplementationOnce(
      () =>
        new Promise<AuthSession>((resolve) => {
          resolveLogin = resolve;
        })
    );

    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "docente@escola.edu.br" } });
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "senha123" } });
    fireEvent.click(submitButton);

    const loader = container.querySelector(".motion-reduce\\:animate-none");
    expect(loader).toBeTruthy();

    resolveLogin(SAMPLE_SESSION);
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/etapa-1");
    });
  });

  it("alterna para Criar conta, orienta em Esqueci minha senha e permite Modo Convidado", async () => {
    renderHome();

    fireEvent.click(screen.getByRole("button", { name: /Continuar sem conta/i }));
    expect(mockPush).toHaveBeenCalledWith("/etapa-1");

    fireEvent.click(screen.getByRole("button", { name: "Esqueci minha senha" }));
    expect(screen.getByRole("status").textContent).toContain("recuperação automática");

    fireEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    expect(screen.getByText("Crie sua conta docente")).toBeTruthy();
    const nameInput = screen.getByLabelText("Nome de exibição");
    expect(nameInput).toBeTruthy();

    fireEvent.change(nameInput, { target: { value: "Profa. Marina Alves" } });
    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "marina@escola.edu.br" } });
    fireEvent.change(screen.getByLabelText(/^Senha/i), { target: { value: "SenhaForte123" } });
    fireEvent.click(screen.getByRole("button", { name: /^Criar conta$/i }));

    await waitFor(() => {
      expect(mockRegisterTeacher).toHaveBeenCalledWith({
        email: "marina@escola.edu.br",
        nome_exibicao: "Profa. Marina Alves",
        senha: "SenhaForte123",
      });
    });
  });

  it("alterna entre modo claro e escuro comunicando acessibilidade via role=switch", () => {
    renderHome();

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

  it("integra a abertura IrisIntroOverlay com transição suave e acessibilidade (aria-hidden)", async () => {
    autoFinishIntro = false;
    const { container } = renderHome();

    expect(screen.getByTestId("iris-intro-overlay")).toBeTruthy();
    const loginWrapper = container.querySelector(".min-h-screen");
    expect(loginWrapper?.getAttribute("aria-hidden")).toBe("true");

    const formSection = container.querySelector(".max-w-\\[420px\\]");
    expect(formSection?.className).toContain("opacity-0");

    mockOverlayHandlers?.onExitStart?.();
    await waitFor(() => {
      expect(formSection?.className).toContain("opacity-100");
    });

    mockOverlayHandlers?.onFinished?.();
    await waitFor(() => {
      expect(screen.queryByTestId("iris-intro-overlay")).toBeNull();
      expect(loginWrapper?.getAttribute("aria-hidden")).toBe("false");
    });
  });

  it("não possui violações de acessibilidade no axe-core (WCAG 2.1 AA)", async () => {
    const { container } = renderHome();

    const violations = await checkAxeViolations(container);
    expect(violations).toEqual([]);
  });
});
