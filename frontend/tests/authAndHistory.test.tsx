// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/contexts/AuthContext";
import { ThemeProvider } from "../src/contexts/ThemeContext";
import { IrisSidebar } from "../src/components/IrisSidebar";
import { Step5Review } from "../src/components/Step5Review";
import HistoricoPage from "../src/app/historico/page";
import {
  TEACHER_AUTH_STORAGE_KEY,
  buildGoogleOAuthStartUrl,
  clearStoredAuthSession,
  fetchWithTeacherAuth,
  loadStoredAuthSession,
  saveStoredAuthSession,
  type AuthSession,
} from "../src/services/authApi";
import { createHistoryActivity, HistoryApiError, type HistoryActivityDetail } from "../src/services/historyApi";

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
  window.localStorage.clear();
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
    expect(window.sessionStorage.getItem(TEACHER_AUTH_STORAGE_KEY)).toBeTruthy();
    expect(window.localStorage.getItem(TEACHER_AUTH_STORAGE_KEY)).toBeNull();
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

  it("Step5Review preserva homologação e todas as caracteristicas_ids ao reabrir item do histórico", async () => {
    saveStoredAuthSession(SAMPLE_SESSION);

    const historyItem: HistoryActivityDetail = {
      id: "hist-uuid-1",
      titulo: "Atividade de Ciências",
      disciplina: "Ciências",
      ano_escolar: "6º ano",
      nivel_andaime: 2,
      caracteristicas_ids: [
        "sobrecarga_memoria_trabalho_comandos_multiplos",
        "desorganizacao_planejamento_inicio_tarefa",
      ],
      travas_curriculares: {},
      questoes: [
        {
          id: "q1",
          original: "Explique a fotossíntese.",
          adaptado: "1. Explique o papel da luz solar.",
          editada: false,
          aprovada: true,
          justificativas: ["Divisão em etapas."],
        },
      ],
      metricas: {},
      status: "homologada",
      versao_schema: "1.0",
      total_questoes: 1,
      criado_em: "2026-11-20T10:00:00Z",
      atualizado_em: "2026-11-20T10:00:00Z",
    };

    const entrada = {
      titulo: historyItem.titulo,
      questoes: [
        {
          id: "q1",
          original: "Explique a fotossíntese.",
          adaptado: "1. Explique o papel da luz solar.",
          justificativas: ["Divisão em etapas."],
          id_caracteristica: historyItem.caracteristicas_ids[0],
          nivel: 2 as const,
          adaptacao_aplicada: true,
        },
      ],
    };

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/v1/auth/providers")) {
        return new Response(
          JSON.stringify({ local_enabled: true, google_enabled: false, guest_mode_enabled: true, database_online: true }),
          { status: 200 }
        );
      }
      if (url.endsWith("/api/v1/auth/me")) {
        return new Response(JSON.stringify(SAMPLE_SESSION.teacher), { status: 200 });
      }
      if (url.endsWith("/api/v1/sessions") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            id: "sess-reopen-1",
            titulo: historyItem.titulo,
            revisao: 0,
            homologada: false,
            pode_exportar: false,
            pode_homologar: false,
            versao_final: "1. Explique o papel da luz solar.",
            questoes: [
              {
                id: "q1",
                original: "Explique a fotossíntese.",
                adaptado: "1. Explique o papel da luz solar.",
                aprovada: false,
                editada: false,
              },
            ],
          }),
          { status: 201 }
        );
      }
      if (url.endsWith("/api/v1/sessions/sess-reopen-1/review") && init?.method === "PUT") {
        return new Response(
          JSON.stringify({
            id: "sess-reopen-1",
            titulo: historyItem.titulo,
            revisao: 1,
            homologada: true,
            pode_exportar: true,
            pode_homologar: true,
            versao_final: "1. Explique o papel da luz solar.",
            questoes: [
              {
                id: "q1",
                original: "Explique a fotossíntese.",
                adaptado: "1. Explique o papel da luz solar.",
                aprovada: true,
                editada: false,
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.includes("/api/v1/history/hist-uuid-1") && init?.method === "PUT") {
        return new Response(JSON.stringify({ ...historyItem, disciplina: "Ciências Naturais" }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ThemeProvider>
        <AuthProvider>
          <Step5Review entrada={entrada} historyItem={historyItem} />
        </AuthProvider>
      </ThemeProvider>
    );

    const btnPdf = await screen.findByRole("button", { name: /Exportar PDF/i });
    await waitFor(() => {
      expect((btnPdf as HTMLButtonElement).disabled).toBe(false);
    });

    const reviewCall = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/api/v1/sessions/sess-reopen-1/review"));
    expect(reviewCall).toBeTruthy();
    expect(JSON.parse(String(reviewCall?.[1]?.body))).toEqual({
      questoes: [{ id: "q1", aprovada: true }],
      homologar: true,
    });

    const btnAtualizar = screen.getByRole("button", { name: /Atualizar no Meu Histórico/i });
    fireEvent.click(btnAtualizar);

    await waitFor(() => {
      expect(screen.getByText(/Atividade homologada salva no seu histórico/i)).toBeTruthy();
    });

    const putHistoryCall = fetchMock.mock.calls.find(
      ([u, init]) => String(u).includes("/api/v1/history/hist-uuid-1") && init?.method === "PUT"
    );
    expect(putHistoryCall).toBeTruthy();
    const savedPayload = JSON.parse(String(putHistoryCall?.[1]?.body));
    expect(savedPayload.status).toBe("homologada");
    expect(savedPayload.caracteristicas_ids).toEqual(historyItem.caracteristicas_ids);
  });
});
