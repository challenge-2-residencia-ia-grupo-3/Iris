/**
 * Cliente HTTP de Autenticação Docente (Cadastro/Login local + Google OAuth PKCE).
 * Guarda apenas os tokens e perfil mínimo do professor (zero dados de estudantes — ADR-10).
 */

export interface TeacherProfile {
  id: string;
  email: string;
  email_verificado: boolean;
  nome_exibicao: string;
  possui_senha_local: boolean;
  oauth_providers: string[];
  criado_em: string;
}

export interface AuthSession {
  token_type: string;
  access_token: string;
  refresh_token: string;
  expires_in: number;
  teacher: TeacherProfile;
}

export interface AuthProvidersStatus {
  local_enabled: boolean;
  google_enabled: boolean;
  guest_mode_enabled: boolean;
  database_online: boolean;
}

export class AuthApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number
  ) {
    super(message);
    this.name = "AuthApiError";
  }
}

export const TEACHER_AUTH_STORAGE_KEY = "iris_teacher_auth_session_v1";

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

function getLocalStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function loadStoredAuthSession(): AuthSession | null {
  const storage = getLocalStorage();
  if (!storage) return null;
  try {
    const raw = storage.getItem(TEACHER_AUTH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (!parsed.access_token || !parsed.refresh_token || !parsed.teacher?.id) {
      return null;
    }
    return parsed as AuthSession;
  } catch {
    return null;
  }
}

export function saveStoredAuthSession(session: AuthSession): void {
  const storage = getLocalStorage();
  if (!storage) return;
  try {
    storage.setItem(TEACHER_AUTH_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Ignora caso localStorage esteja indisponível
  }
}

export function clearStoredAuthSession(): void {
  const storage = getLocalStorage();
  if (!storage) return;
  try {
    storage.removeItem(TEACHER_AUTH_STORAGE_KEY);
  } catch {
    // Ignora caso localStorage esteja indisponível
  }
}

async function parseErrorResponse(resp: Response, fallbackMessage: string): Promise<AuthApiError> {
  const body = await resp.json().catch(() => null);
  const detail = body?.detail;
  if (detail && typeof detail === "object") {
    return new AuthApiError(
      String(detail.detail || fallbackMessage),
      String(detail.code || "AUTH_ERROR"),
      resp.status
    );
  }
  if (typeof detail === "string" && detail) {
    return new AuthApiError(detail, "AUTH_ERROR", resp.status);
  }
  return new AuthApiError(fallbackMessage, "AUTH_ERROR", resp.status);
}

export async function fetchAuthProviders(): Promise<AuthProvidersStatus> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/auth/providers`, { cache: "no-store" });
  if (!resp.ok) {
    throw await parseErrorResponse(resp, "Não foi possível consultar os métodos de login.");
  }
  return (await resp.json()) as AuthProvidersStatus;
}

export async function registerTeacher(input: {
  email: string;
  nome_exibicao: string;
  senha: string;
}): Promise<AuthSession> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(input),
  });
  if (!resp.ok) {
    throw await parseErrorResponse(resp, "Não foi possível concluir o cadastro.");
  }
  const session = (await resp.json()) as AuthSession;
  saveStoredAuthSession(session);
  return session;
}

export async function loginTeacher(input: { email: string; senha: string }): Promise<AuthSession> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(input),
  });
  if (!resp.ok) {
    throw await parseErrorResponse(resp, "E-mail ou senha inválidos.");
  }
  const session = (await resp.json()) as AuthSession;
  saveStoredAuthSession(session);
  return session;
}

export async function refreshTeacherSession(refreshToken: string): Promise<AuthSession> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!resp.ok) {
    clearStoredAuthSession();
    throw await parseErrorResponse(resp, "Sessão expirada. Entre novamente.");
  }
  const session = (await resp.json()) as AuthSession;
  saveStoredAuthSession(session);
  return session;
}

export async function logoutTeacher(refreshToken?: string | null): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify({ refresh_token: refreshToken ?? null }),
    });
  } catch {
    // Mesmo offline, limpa a sessão local
  } finally {
    clearStoredAuthSession();
  }
}

export function buildGoogleOAuthStartUrl(nextPath = "/historico"): string {
  const params = new URLSearchParams({ next: nextPath, mode: "redirect" });
  return `${API_BASE_URL}/api/v1/auth/oauth/google/start?${params.toString()}`;
}

export async function exchangeGoogleOAuthCode(code: string): Promise<AuthSession> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/auth/oauth/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify({ code }),
  });
  if (!resp.ok) {
    throw await parseErrorResponse(resp, "Não foi possível concluir o login com o Google.");
  }
  const session = (await resp.json()) as AuthSession;
  saveStoredAuthSession(session);
  return session;
}

export async function fetchWithTeacherAuth(
  path: string,
  init: RequestInit = {},
  sessionOverride?: AuthSession | null
): Promise<Response> {
  const session = sessionOverride ?? loadStoredAuthSession();
  if (!session?.access_token) {
    throw new AuthApiError("Autenticação necessária.", "NOT_AUTHENTICATED", 401);
  }

  const doFetch = (token: string) => {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${token}`);
    return fetch(`${API_BASE_URL}${path}`, { ...init, headers, cache: "no-store" });
  };

  let resp = await doFetch(session.access_token);
  if (resp.status === 401 && session.refresh_token) {
    try {
      const renewed = await refreshTeacherSession(session.refresh_token);
      resp = await doFetch(renewed.access_token);
    } catch {
      return resp;
    }
  }
  return resp;
}

export async function fetchCurrentTeacher(): Promise<TeacherProfile> {
  const resp = await fetchWithTeacherAuth("/api/v1/auth/me", { method: "GET" });
  if (!resp.ok) {
    throw await parseErrorResponse(resp, "Sessão inválida.");
  }
  return (await resp.json()) as TeacherProfile;
}

export async function deleteTeacherAccount(): Promise<void> {
  const resp = await fetchWithTeacherAuth("/api/v1/auth/me", { method: "DELETE" });
  if (!resp.ok) {
    throw await parseErrorResponse(resp, "Não foi possível excluir a conta.");
  }
  clearStoredAuthSession();
}
