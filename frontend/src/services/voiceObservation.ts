/**
 * Observação pedagógica por voz (História 1.2.3 — Issue #10, RF-03/RF-05).
 * Cliente do backend + regras puras (formato de gravação, limites, mesclagem das sugestões na seleção da Etapa 2).
 * O áudio nunca é guardado no navegador (sem localStorage/sessionStorage/IndexedDB): fica só em memória até o envio.
 */
export const MAX_SEGUNDOS = 60;
export const MAX_BYTES = 12 * 1024 * 1024;
export const ROTA_TRANSCREVER = "/api/v1/audio/transcribe";
export const ROTA_SUGERIR = "/api/v1/audio/suggest";

export interface SugestaoVoz {
  id_caracteristica: string;
  nome: string;
  pontuacao: number;
  confianca: "alta" | "media";
  evidencias: string[];
}

export interface AvisoVoz {
  code: string;
  categorias?: string[];
  detail: string;
}

export interface ResultadoVoz {
  status: "ok";
  transcricao: string;
  pii_substituicoes: number;
  avisos: AvisoVoz[];
  id_catalogo: string;
  sugestoes: SugestaoVoz[];
  duracao_segundos?: number;
  formato?: string;
}

export class VoiceError extends Error {
  constructor(message: string, public readonly code: string, public readonly status: number) {
    super(message);
    this.name = "VoiceError";
  }
}

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

const MIMES_PREFERIDOS = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"] as const;

/** Primeiro formato de gravação que o navegador sabe gerar (Chrome/Edge/Firefox: WebM/Ogg; Safari: MP4). */
export function escolherMimeType(suporta: (mime: string) => boolean): string | null {
  for (const m of MIMES_PREFERIDOS) {
    try {
      if (suporta(m)) return m;
    } catch {
      /* navegador antigo: tenta o próximo */
    }
  }
  return null;
}

export function extensaoDoMime(mime: string): string {
  if (mime.includes("webm")) return "webm";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mp4") || mime.includes("m4a") || mime.includes("aac")) return "m4a";
  if (mime.includes("wav")) return "wav";
  return "audio";
}

const EXTENSOES = /\.(wav|webm|ogg|oga|opus|mp4|m4a)$/i;

/** Conferência rápida antes de enviar. O servidor revalida tudo (formato pelo conteúdo e duração real). */
export function validarArquivoLocal(arquivo: { name: string; type: string; size: number }): string | null {
  if (arquivo.size === 0) return "O arquivo está vazio.";
  if (arquivo.size > MAX_BYTES) return `O arquivo passa de ${MAX_BYTES / (1024 * 1024)} MB. O limite é de ${MAX_SEGUNDOS} segundos de áudio.`;
  if (!arquivo.type.startsWith("audio/") && !EXTENSOES.test(arquivo.name)) return "Envie um áudio em WAV, WebM, Ogg ou MP4/M4A.";
  return null;
}

export function formatarTempo(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Soma as sugestões confirmadas à seleção atual, sem repetir e sem tirar nada que o professor já marcou. */
export function mesclarSelecao(atual: readonly string[], confirmadas: readonly string[], validos?: ReadonlySet<string>): string[] {
  const saida = [...atual];
  for (const id of confirmadas) {
    if ((!validos || validos.has(id)) && !saida.includes(id)) saida.push(id);
  }
  return saida;
}

async function chamar(rota: string, init: RequestInit): Promise<ResultadoVoz> {
  let resposta: Response;
  try {
    resposta = await fetch(`${API_BASE_URL}${rota}`, { ...init, cache: "no-store" });
  } catch {
    throw new VoiceError("Não foi possível falar com o servidor. Tente de novo ou selecione as características manualmente.", "SERVER_UNAVAILABLE", 0);
  }
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    const d = corpo?.detail;
    const code = typeof d === "object" && d?.code ? String(d.code) : "REJECTED";
    let msg = typeof d === "object" && d?.detail ? String(d.detail) : "O servidor recusou o áudio.";
    if (resposta.status === 503) msg += " Você ainda pode selecionar as características manualmente.";
    throw new VoiceError(msg, code, resposta.status);
  }
  return (await resposta.json()) as ResultadoVoz;
}

export function transcreverAudio(audio: Blob, nomeArquivo: string): Promise<ResultadoVoz> {
  const form = new FormData();
  form.append("file", audio, nomeArquivo);
  return chamar(ROTA_TRANSCREVER, { method: "POST", body: form });
}

export function sugerirDeTexto(texto: string): Promise<ResultadoVoz> {
  return chamar(ROTA_SUGERIR, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto }) });
}
