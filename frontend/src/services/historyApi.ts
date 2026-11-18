/**
 * Cliente HTTP do Histórico de Atividades Docentes no PostgreSQL (ADR-10).
 */
import { fetchWithTeacherAuth } from "./authApi";
import type { FormatoMaterial } from "./materialExport";

export type ActivityStatus = "rascunho" | "homologada";

export interface HistoryQuestionItem {
  id: string;
  original: string;
  adaptado: string;
  editada: boolean;
  aprovada: boolean;
  justificativas: string[];
}

export interface HistoryActivitySummary {
  id: string;
  titulo: string;
  disciplina: string | null;
  ano_escolar: string | null;
  nivel_andaime: 1 | 2 | 3;
  caracteristicas_ids: string[];
  status: ActivityStatus;
  total_questoes: number;
  criado_em: string;
  atualizado_em: string;
}

export interface HistoryActivityDetail extends HistoryActivitySummary {
  travas_curriculares: Record<string, unknown>;
  questoes: HistoryQuestionItem[];
  metricas: Record<string, unknown>;
  versao_schema: string;
}

export interface HistoryListResponse {
  items: HistoryActivitySummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface SaveHistoryPayload {
  titulo: string;
  disciplina?: string | null;
  ano_escolar?: string | null;
  nivel_andaime: 1 | 2 | 3;
  caracteristicas_ids: string[];
  travas_curriculares?: Record<string, unknown>;
  questoes: HistoryQuestionItem[];
  metricas?: Record<string, unknown>;
  status: ActivityStatus;
}

export interface PrivacyGateIssue {
  field: string;
  type: string;
  detail: string;
}

export class HistoryApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
    public readonly issues: PrivacyGateIssue[] = []
  ) {
    super(message);
    this.name = "HistoryApiError";
  }
}

async function parseHistoryError(resp: Response, fallback: string): Promise<HistoryApiError> {
  const body = await resp.json().catch(() => null);
  const d = body?.detail;
  if (d && typeof d === "object") {
    return new HistoryApiError(
      String(d.detail || fallback),
      String(d.code || "HISTORY_ERROR"),
      resp.status,
      Array.isArray(d.issues) ? (d.issues as PrivacyGateIssue[]) : []
    );
  }
  return new HistoryApiError(fallback, "HISTORY_ERROR", resp.status);
}

export async function listHistoryActivities(filters: {
  q?: string;
  disciplina?: string;
  nivel_andaime?: number | null;
  status?: ActivityStatus | "";
  limit?: number;
  offset?: number;
} = {}): Promise<HistoryListResponse> {
  const params = new URLSearchParams();
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.disciplina?.trim()) params.set("disciplina", filters.disciplina.trim());
  if (filters.nivel_andaime) params.set("nivel_andaime", String(filters.nivel_andaime));
  if (filters.status) params.set("status", filters.status);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));

  const qs = params.toString();
  const resp = await fetchWithTeacherAuth(`/api/v1/history${qs ? `?${qs}` : ""}`, { method: "GET" });
  if (!resp.ok) {
    throw await parseHistoryError(resp, "Não foi possível carregar seu histórico.");
  }
  return (await resp.json()) as HistoryListResponse;
}

export async function getHistoryActivity(id: string): Promise<HistoryActivityDetail> {
  const resp = await fetchWithTeacherAuth(`/api/v1/history/${encodeURIComponent(id)}`, { method: "GET" });
  if (!resp.ok) {
    throw await parseHistoryError(resp, "Atividade não encontrada no histórico.");
  }
  return (await resp.json()) as HistoryActivityDetail;
}

export async function createHistoryActivity(
  payload: SaveHistoryPayload,
  autoSanitizar = false
): Promise<HistoryActivityDetail> {
  const qs = autoSanitizar ? "?auto_sanitizar=true" : "";
  const resp = await fetchWithTeacherAuth(`/api/v1/history${qs}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw await parseHistoryError(resp, "Não foi possível salvar a atividade no histórico.");
  }
  return (await resp.json()) as HistoryActivityDetail;
}

export async function updateHistoryActivity(
  id: string,
  payload: SaveHistoryPayload,
  autoSanitizar = false
): Promise<HistoryActivityDetail> {
  const qs = autoSanitizar ? "?auto_sanitizar=true" : "";
  const resp = await fetchWithTeacherAuth(`/api/v1/history/${encodeURIComponent(id)}${qs}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw await parseHistoryError(resp, "Não foi possível atualizar a atividade no histórico.");
  }
  return (await resp.json()) as HistoryActivityDetail;
}

export async function duplicateHistoryActivity(id: string): Promise<HistoryActivityDetail> {
  const resp = await fetchWithTeacherAuth(`/api/v1/history/${encodeURIComponent(id)}/duplicate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!resp.ok) {
    throw await parseHistoryError(resp, "Não foi possível duplicar a atividade.");
  }
  return (await resp.json()) as HistoryActivityDetail;
}

export async function deleteHistoryActivity(id: string): Promise<void> {
  const resp = await fetchWithTeacherAuth(`/api/v1/history/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!resp.ok) {
    throw await parseHistoryError(resp, "Não foi possível excluir a atividade.");
  }
}

export async function downloadHistoryActivity(
  id: string,
  formato: FormatoMaterial,
  tituloSugerido?: string
): Promise<void> {
  const resp = await fetchWithTeacherAuth(
    `/api/v1/history/${encodeURIComponent(id)}/export?formato=${formato}`,
    { method: "POST" }
  );
  if (!resp.ok) {
    throw await parseHistoryError(resp, "Não foi possível exportar o arquivo.");
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const slug = (tituloSugerido || "atividade-adaptada")
    .toLowerCase()
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/(^-|-$)/g, "");
  a.href = url;
  a.download = `${slug || "atividade-adaptada"}.${formato}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
