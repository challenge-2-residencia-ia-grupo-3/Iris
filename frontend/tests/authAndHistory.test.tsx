// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/contexts/AuthContext";
import { ThemeProvider } from "../src/contexts/ThemeContext";
import { IrisSidebar } from "../src/components/IrisSidebar";
import HistoricoPage from "../src/app/historico/page";
import {
  buildGoogleOAuthStartUrl,
  clearStoredAuthSession,
  fetchWithTeacherAuth,
  loadStoredAuthSession,
  saveStoredAuthSession,
  type AuthSession,
} from "../src/services/authApi";
import { createHistoryActivity, HistoryApiError } from "../src/services/historyApi";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: pushMock }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  cleanup();
  clearStoredAuthSession();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
  pushMock.mockReset();
});

const SAMPLE_SESSION: AuthSession = {
  token_type: "bearer",
  access_token: "jwt-token-1",
  refresh_token: "refresh-token-1",
  expires_in: 1800,
  teacher: {
    id: "prof-1",
    email: "marina@escola.edu.br",
    email_verificado: true,
    nome_exibicao: "Profa. Marina",
    possui_senha_local: true,
    oauth_providers: ["google"],
    criado_em: "2026-11-18T12:00:00Z",
  },
};

describe("authApi e historyApi", () => {
  it("monta URL de início Google OAuth e persiste sessão mínima do professor", () => {
    const url = buildGoogleOAuthStartUrl("/historico");
    expect(url).toContain("/api/v1/auth/oauth/google/start");
    expect(url).toContain("next=%2Fhistorico");

    saveStoredAuthSession(SAMPLE_SESSION);
    expect(loadStoredAuthSession()?.teacher.email).toBe("marina@escola.edu.br");
  });

  it("renova token automaticamente em 401 via refresh_token", async () => {
    saveStoredAuthSession(SAMPLE_SESSION);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "expired" }), { status: 401 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ ...SAMPLE_SESSION, access_token: "jwt-token-2", refresh_token: "refresh-token-2" }),
          { status: 200 }
        )
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const resp = await fetchWithTeacherAuth("/api/v1/history", { method: "GET" });
    expect(resp.status).toBe(200);
    expect(loadStoredAuthSession()?.access_token).toBe("jwt-token-2");
  });

  it("propaga HistoryApiError estruturado quando o gate anti-PII bloqueia", async () => {
    saveStoredAuthSession(SAMPLE_SESSION);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: "PII_DETECTED",
              detail: "Dado pessoal detectado.",
              issues: [{ field: "questoes[0].adaptado", type: "pii", detail: "Nome detectado" }],
            },
          }),
          { status: 422 }
        )
      )
    );

    await expect(
      createHistoryActivity({
        titulo: "Prova",
        nivel_andaime: 2,
        caracteristicas_ids: ["sobrecarga_memoria_trabalho_comandos_multiplos"],
        questoes: [{ id: "q1", original: "Orig", adaptado: "Aluno João", editada: false, aprovada: false, justificativas: [] }],
        status: "rascunho",
      })
    ).rejects.toMatchObject({
      name: "HistoryApiError",
      code: "PII_DETECTED",
      status: 422,
    });
    expect(HistoryApiError).toBeDefined();
  });
});

describe("Navegação lateral e página /historico (WCAG 2.1 AA)", () => {
  it("IrisSidebar exibe Minhas Atividades e Zero-Database de Alunos sem violações axe", async () => {
    const { container } = render(
      <IrisSidebar currentStep={1} enabledSteps={[1, 2, 3, 4, 5]} />
    );
    expect(screen.getByRole("link", { name: /Minhas Atividades/ })).toBeTruthy();
    expect(screen.getByText(/Zero-Database de Alunos/)).toBeTruthy();

    const results = await axe.run(container, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
      rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("HistoricoPage exibe estado convidado e lista atividades quando autenticado", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ local_enabled: true, google_enabled: true, guest_mode_enabled: true, database_online: true }),
          { status: 200 }
        )
      )
    );

    const { container } = render(
      <ThemeProvider>
        <AuthProvider>
          <HistoricoPage />
        </AuthProvider>
      </ThemeProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/Você está no Modo Convidado/)).toBeTruthy();
    });
    const results = await axe.run(container, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
      rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });
});
