/**
 * Importação e restauração da sessão a partir do `.json` do Perfil Pedagógico Portátil
 * (História 3.2.2 — Issue #31, RF-15, RNF-01, RNF-03).
 *
 * O arquivo é lido no navegador do docente. O texto vai ao servidor só para a validação oficial do schema
 * (`POST /api/v1/perfil/importar`, sem estado e com `Cache-Control: no-store`); se o servidor estiver fora do ar,
 * vale a validação local do mesmo schema. O que fica na sessão da aba são apenas os identificadores das
 * características e a sugestão de nível: nada de nome, texto de observação ou conteúdo do arquivo.
 */
import {
  type EficaciaIntervencao,
  historicoOrdenado,
  PADRAO_ID_CARACTERISTICA,
  type PerfilPedagogicoPortatil,
  PerfilPortatilError,
} from "./portableProfile";
import { sanitizarPerfilParaLocalStorage } from "./portableProfileStorage";

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const ROTA_IMPORTAR_PERFIL = "/api/v1/perfil/importar";
export const MAX_BYTES_PERFIL = 1024 * 1024;
export const PERFIL_IMPORTADO_STORAGE_KEY = "iris_session_perfil_importado_v1";

export type NivelAndaime = 1 | 2 | 3;
export const ROTULO_NIVEL_ANDAIME: Record<NivelAndaime, string> = { 1: "Leve", 2: "Moderado", 3: "Intensivo" };

/** O que a sessão guarda do perfil importado: só identificadores e a sugestão, nunca o arquivo. */
export interface PerfilRestaurado {
  codigo_anonimo: string;
  /** Características do perfil, sem filtrar pelo catálogo (a Etapa 2 confere com o catálogo ativo). */
  caracteristicas: string[];
  /** Características com ao menos um registro de eficácia alta. */
  alta_eficacia: string[];
  nivel_andaime: NivelAndaime | null;
  motivo_nivel: string;
}

export interface ResultadoImportacao {
  perfil: PerfilPedagogicoPortatil;
  restaurado: PerfilRestaurado;
  /** `servidor`: validado pela API; `local`: servidor indisponível, validado no navegador. */
  origem: "servidor" | "local";
}

// ------------------------------------------------------------------ leitura do arquivo

function lerTexto(file: File): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(String(leitor.result ?? ""));
    leitor.onerror = () => reject(leitor.error);
    leitor.readAsText(file);
  });
}

/** Confere nome, tamanho e conteúdo do arquivo antes de qualquer envio. */
export async function lerArquivoPerfil(file: File): Promise<string> {
  if (!file.name.toLowerCase().endsWith(".json")) {
    throw new PerfilPortatilError(
      "Envie o arquivo .json do Perfil Pedagógico Portátil. Outros formatos (como o .pdf) não podem ser importados.",
      "UNSUPPORTED_PROFILE_FORMAT"
    );
  }
  if (file.size === 0) {
    throw new PerfilPortatilError("O arquivo está vazio. Escolha o .json exportado pela plataforma.", "EMPTY_FILE");
  }
  if (file.size > MAX_BYTES_PERFIL) {
    throw new PerfilPortatilError(
      "O arquivo é grande demais para ser um Perfil Pedagógico Portátil (máximo 1 MB).",
      "FILE_TOO_LARGE"
    );
  }
  let texto: string;
  try {
    texto = await lerTexto(file);
  } catch {
    throw new PerfilPortatilError("Não foi possível ler o arquivo. Tente selecioná-lo de novo.", "FILE_READ_ERROR");
  }
  if (!texto.trim()) {
    throw new PerfilPortatilError("O arquivo está vazio. Escolha o .json exportado pela plataforma.", "EMPTY_FILE");
  }
  return texto;
}

// ------------------------------------------------------------------ sugestão de nível de andaime

const NIVEL_POR_PALAVRA: Record<string, NivelAndaime> = { "1": 1, leve: 1, "2": 2, moderado: 2, "3": 3, intensivo: 3 };

function semAcento(texto: string): string {
  return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** "nível 2", "nível leve", "andaime moderado"… Só reconhece menção explícita ao nível de andaime. */
export function nivelCitadoNaEstrategia(estrategia: string): NivelAndaime | null {
  const t = semAcento(estrategia);
  const m =
    /\bnivel\s*(?:de\s+andaime\s*)?[:\-]?\s*(1|2|3|leve|moderado|intensivo)\b/.exec(t) ??
    /\bandaime\s+(?:de\s+nivel\s+)?(leve|moderado|intensivo)\b/.exec(t);
  return m ? NIVEL_POR_PALAVRA[m[1]] : null;
}

/**
 * Regra de pré-seleção (História 3.2.2):
 *  - características: as do perfil;
 *  - nível: o nível citado nas estratégias de eficácia ALTA; só é sugerido quando um nível aparece mais vezes
 *    que os demais. Sem menção explícita, ou em caso de empate, não se sugere nenhum e a Etapa 3 segue no padrão.
 */
export function recomendarDoPerfil(perfil: PerfilPedagogicoPortatil): PerfilRestaurado {
  const altas = historicoOrdenado(perfil).filter((r) => r.eficacia === ("alta" satisfies EficaciaIntervencao));
  const altaEficacia = Array.from(new Set(altas.map((r) => r.id_caracteristica)));

  const contagem: Record<NivelAndaime, number> = { 1: 0, 2: 0, 3: 0 };
  for (const r of altas) {
    const nivel = nivelCitadoNaEstrategia(r.estrategia);
    if (nivel) contagem[nivel] += 1;
  }
  const ranking = ([1, 2, 3] as NivelAndaime[]).filter((n) => contagem[n] > 0).sort((a, b) => contagem[b] - contagem[a]);

  let nivel: NivelAndaime | null = null;
  let motivo: string;
  if (ranking.length === 0) {
    motivo =
      altas.length === 0
        ? "O perfil não tem registro de eficácia alta; o nível de andaime segue no padrão da Etapa 3."
        : "As estratégias de eficácia alta do perfil não citam um nível de andaime; o nível segue no padrão da Etapa 3.";
  } else if (ranking.length > 1 && contagem[ranking[0]] === contagem[ranking[1]]) {
    motivo = "O histórico de eficácia alta aponta mais de um nível com o mesmo peso; escolha o nível na Etapa 3.";
  } else {
    nivel = ranking[0];
    const n = contagem[nivel];
    motivo = `Nível ${ROTULO_NIVEL_ANDAIME[nivel]}: citado em ${n} estratégia${n > 1 ? "s" : ""} de eficácia alta do histórico do perfil.`;
  }

  return {
    codigo_anonimo: perfil.codigo_anonimo,
    caracteristicas: [...perfil.caracteristicas_selecionadas],
    alta_eficacia: altaEficacia,
    nivel_andaime: nivel,
    motivo_nivel: motivo,
  };
}

// ------------------------------------------------------------------ validação (servidor e local)

function erroDoServidor(corpo: unknown, padrao: string): PerfilPortatilError {
  const detalhe = (corpo as { detail?: unknown } | null)?.detail;
  if (detalhe && typeof detalhe === "object") {
    const d = detalhe as { detail?: unknown; code?: unknown };
    return new PerfilPortatilError(typeof d.detail === "string" && d.detail ? d.detail : padrao, String(d.code ?? "PROFILE_REJECTED"));
  }
  return new PerfilPortatilError(padrao, "PROFILE_REJECTED");
}

function validarLocalmente(texto: string): PerfilPedagogicoPortatil {
  let bruto: unknown;
  try {
    bruto = JSON.parse(texto.replace(/^﻿/, ""));
  } catch {
    throw new PerfilPortatilError("O arquivo do perfil não é um JSON válido.", "INVALID_JSON");
  }
  try {
    return sanitizarPerfilParaLocalStorage(bruto);
  } catch (e) {
    if (e instanceof PerfilPortatilError) {
      throw new PerfilPortatilError(
        `O arquivo não segue o formato do Perfil Pedagógico Portátil. ${e.message}`,
        e.code === "FORBIDDEN_PERSONAL_DATA" ? "CLINICAL_DATA_BLOCKED" : "INVALID_STRUCTURE"
      );
    }
    throw e;
  }
}

/** Valida o texto do arquivo e devolve o perfil normalizado com a sugestão de pré-seleção. */
export async function importarPerfilDeTexto(texto: string): Promise<ResultadoImportacao> {
  let resposta: Response | null = null;
  try {
    resposta = await fetch(`${API_BASE_URL}${ROTA_IMPORTAR_PERFIL}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ arquivo: texto }),
      cache: "no-store",
    });
  } catch {
    resposta = null; // servidor fora do ar: cai na validação local do mesmo schema
  }

  if (resposta === null) {
    const perfil = validarLocalmente(texto);
    return { perfil, restaurado: recomendarDoPerfil(perfil), origem: "local" };
  }

  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    throw erroDoServidor(corpo, "O servidor recusou o arquivo. Confira se é o .json exportado pela plataforma.");
  }

  const corpo = (await resposta.json().catch(() => null)) as { perfil?: unknown } | null;
  let perfil: PerfilPedagogicoPortatil;
  try {
    perfil = sanitizarPerfilParaLocalStorage(corpo?.perfil);
  } catch {
    throw new PerfilPortatilError("A resposta do servidor não pôde ser lida. Tente importar de novo.", "INVALID_SERVER_RESPONSE");
  }
  return { perfil, restaurado: recomendarDoPerfil(perfil), origem: "servidor" };
}

export async function importarPerfilDeArquivo(file: File): Promise<ResultadoImportacao> {
  return importarPerfilDeTexto(await lerArquivoPerfil(file));
}

// ------------------------------------------------------------------ sessão da aba

export function salvarRestauracaoNaSessao(restaurado: PerfilRestaurado): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(PERFIL_IMPORTADO_STORAGE_KEY, JSON.stringify(restaurado));
  } catch {
    // sessionStorage indisponível: a pré-seleção simplesmente não é aplicada
  }
}

/** Lê e confere o que está na sessão: dado malformado vira "sem perfil importado". */
export function carregarRestauracaoDaSessao(): PerfilRestaurado | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(PERFIL_IMPORTADO_STORAGE_KEY);
    if (!raw) return null;
    const r = JSON.parse(raw) as Partial<PerfilRestaurado> | null;
    if (!r || typeof r !== "object" || typeof r.codigo_anonimo !== "string") return null;
    const ids = (v: unknown): string[] =>
      Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && PADRAO_ID_CARACTERISTICA.test(x)) : [];
    const nivel = r.nivel_andaime === 1 || r.nivel_andaime === 2 || r.nivel_andaime === 3 ? r.nivel_andaime : null;
    return {
      codigo_anonimo: r.codigo_anonimo,
      caracteristicas: ids(r.caracteristicas),
      alta_eficacia: ids(r.alta_eficacia),
      nivel_andaime: nivel,
      motivo_nivel: typeof r.motivo_nivel === "string" ? r.motivo_nivel : "",
    };
  } catch {
    return null;
  }
}

export function limparRestauracaoDaSessao(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(PERFIL_IMPORTADO_STORAGE_KEY);
  } catch {
    // sessionStorage indisponível
  }
}
