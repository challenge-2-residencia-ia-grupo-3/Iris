/**
 * Cliente da sessão de revisão docente (História 2.2.2 — RF-13). Tudo fica em memória no servidor;
 * aqui não há localStorage, sessionStorage nem cookie.
 */
import type { FormatoMaterial } from "./materialExport";
import type { EstadoRevisao, QuestaoRevisao } from "./reviewState";

export interface SessaoRevisao extends EstadoRevisao {
  id: string;
  titulo: string;
  revisao: number;
  pode_exportar: boolean;
  pode_homologar: boolean;
  versao_final: string;
}

export interface QuestaoParaSessao {
  id?: string;
  original?: string;
  adaptado: string;
}

export interface EdicaoRevisao {
  id: string;
  adaptado?: string;
  aprovada?: boolean;
}

export class SessaoRevisaoError extends Error {
  constructor(message: string, public readonly code: string, public readonly status: number) {
    super(message);
    this.name = "SessaoRevisaoError";
  }
}

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const rotaSessoes = "/api/v1/sessions";
export const rotaSessao = (id: string) => `${rotaSessoes}/${encodeURIComponent(id)}`;
export const rotaRevisao = (id: string) => `${rotaSessao(id)}/review`;
export const rotaExportarSessao = (id: string, formato: FormatoMaterial) => `${rotaSessao(id)}/export?formato=${formato}`;

async function chamar(rota: string, init: RequestInit): Promise<Response> {
  let resposta: Response;
  try {
    resposta = await fetch(`${API_BASE_URL}${rota}`, { ...init, cache: "no-store" });
  } catch {
    throw new SessaoRevisaoError("Não foi possível falar com o servidor. Suas edições ainda estão nesta tela.", "SERVER_UNAVAILABLE", 0);
  }
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    const d = corpo?.detail;
    throw new SessaoRevisaoError(
      typeof d === "object" && d?.detail ? String(d.detail) : "O servidor recusou a operação.",
      typeof d === "object" && d?.code ? String(d.code) : "REJECTED",
      resposta.status
    );
  }
  return resposta;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export async function criarSessao(questoes: QuestaoParaSessao[], titulo?: string): Promise<SessaoRevisao> {
  const r = await chamar(rotaSessoes, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ titulo, questoes }) });
  return (await r.json()) as SessaoRevisao;
}

export async function lerSessao(id: string): Promise<SessaoRevisao> {
  return (await (await chamar(rotaSessao(id), { method: "GET" })).json()) as SessaoRevisao;
}

/** PUT /sessions/{id}/review: grava edições, aprovações e (opcional) a homologação. */
export async function salvarRevisao(
  id: string,
  corpo: { questoes?: EdicaoRevisao[]; homologar?: boolean }
): Promise<SessaoRevisao> {
  const r = await chamar(rotaRevisao(id), { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify(corpo) });
  return (await r.json()) as SessaoRevisao;
}

/** Edições a enviar: texto e aprovação de cada questão que difere do que o servidor já confirmou. */
export function diferencas(local: QuestaoRevisao[], confirmado: QuestaoRevisao[]): EdicaoRevisao[] {
  const base = new Map(confirmado.map((q) => [q.id, q]));
  const saida: EdicaoRevisao[] = [];
  for (const q of local) {
    const b = base.get(q.id);
    if (!b) continue;
    const item: EdicaoRevisao = { id: q.id };
    if (q.adaptado !== b.adaptado) item.adaptado = q.adaptado;
    if (q.aprovada !== b.aprovada || q.adaptado !== b.adaptado) item.aprovada = q.aprovada;
    if (item.adaptado !== undefined || item.aprovada !== undefined) saida.push(item);
  }
  return saida;
}

export async function baixarSessao(id: string, formato: FormatoMaterial): Promise<void> {
  const r = await chamar(rotaExportarSessao(id, formato), { method: "POST" });
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `atividade-adaptada.${formato}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
