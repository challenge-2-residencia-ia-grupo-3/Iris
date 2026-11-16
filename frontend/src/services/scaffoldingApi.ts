/**
 * Cliente HTTP e persistência em sessão para a Calibragem do Nível de Andaime Cognitivo (História 1.3.1 — Issue #12).
 *
 * Endpoints consumidos:
 * - GET  /api/v1/scaffolding/levels
 * - POST /api/v1/scaffolding/calibrate
 *
 * Oferece contingência offline / local utilizando o catálogo oficial modular importado,
 * garantindo conformidade com o princípio Zero-Database e alta resiliência.
 */

import { IrisApiError } from "./materialsApi";
import {
  CharacteristicItem,
  FALLBACK_OFFICIAL_CATALOG,
} from "./catalogsApi";

export type ScaffoldingLevel = 1 | 2 | 3;

export interface ScaffoldingLevelMeta {
  nivel: ScaffoldingLevel;
  rotulo: string;
  nome_curto: string;
  objetivo_geral: string;
  foco_pedagogico: string;
  transformacoes_estruturais: string[];
  salvaguardas_antimuleta: string[];
}

export interface CharacteristicScaffoldingDirectiveItem {
  id_caracteristica: string;
  nome_caracteristica: string;
  nivel: ScaffoldingLevel;
  rotulo: string;
  objetivo_andaime: string;
  acoes_permitidas: string[];
  restricoes_escopo: string[];
}

export interface ScaffoldingCalibrationResult {
  status: string;
  nivel: ScaffoldingLevel;
  rotulo_nivel: string;
  nome_curto: string;
  objetivo_geral: string;
  foco_pedagogico: string;
  transformacoes_estruturais: string[];
  salvaguardas_antimuleta: string[];
  total_caracteristicas_afetadas: number;
  caracteristicas_afetadas: CharacteristicScaffoldingDirectiveItem[];
  caracteristicas_bloqueadas_ids: string[];
  aviso_antimuleta: string;
}

export interface ScaffoldingCalibrationPayload {
  selected_ids: string[];
  nivel: ScaffoldingLevel;
  id_catalogo?: string;
}

export const SCAFFOLDING_STORAGE_KEY = "iris_session_scaffolding_v1";

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const AVISO_ANTIMULETA_PADRAO =
  "A calibração do andaime cognitivo ajusta o formato de apresentação, fragmentação e suporte procedimental " +
  "da atividade escolar. O sistema é estritamente proibido de fornecer respostas prontas, reduzir conceitos " +
  "obrigatórios ou produzir as inferências avaliadas pela questão.";

export const FALLBACK_SCAFFOLDING_LEVELS: ScaffoldingLevelMeta[] = [
  {
    nivel: 1,
    rotulo: "Nível 1 — Adaptação Leve (Acessibilidade e Destaque Visual)",
    nome_curto: "Leve",
    objetivo_geral:
      "Ajustes de formatação, organização visual e destaque tipográfico, preservando 100% da estrutura frasal, sintática e da complexidade original do conteúdo.",
    foco_pedagogico: "Acessibilidade perceptiva, foco atencional e redução de distratibilidade visual.",
    transformacoes_estruturais: [
      "Aplicação de negrito em palavras-chave e verbos de comando (ex.: identifique, calcule, explique).",
      "Destaque de conectivos restritivos críticos (ex.: NÃO, EXCETO, APENAS, INCORRETA).",
      "Espaçamento ampliado e respiro visual entre parágrafos e alternativas.",
    ],
    salvaguardas_antimuleta: [
      "Proibido reescrever enunciados ou simplificar vocabulário conceitual.",
      "Proibido fragmentar a questão em subitens ou alterar a ordem dos elementos.",
      "Preserva integralmente a extensão textual e a complexidade sintática.",
    ],
  },
  {
    nivel: 2,
    rotulo: "Nível 2 — Adaptação Moderada (Fragmentação e Checklist de Etapas)",
    nome_curto: "Moderado",
    objetivo_geral:
      "Divisão da atividade em etapas explícitas com checklists de execução (passo a passo), chunking de blocos textuais extensos e inserção de caixas de apoio/glossário contextual.",
    foco_pedagogico: "Redução da sobrecarga da memória de trabalho e organização sequencial da resolução.",
    transformacoes_estruturais: [
      "Fragmentação estruturada (chunking) de parágrafos longos em blocos de leitura direta.",
      "Conversão de múltiplos comandos conjugados em listas sequenciais de checagem ([ ]).",
      "Inserção de caixas de apoio contextual ou glossário terminológico discreto.",
    ],
    salvaguardas_antimuleta: [
      "Proibido responder ou resolver qualquer etapa pelo estudante.",
      "Proibido sugerir a fórmula, regra ou inferência exigida pela habilidade curricular.",
      "Mantém a totalidade das operações e comandos originais solicitados.",
    ],
  },
  {
    nivel: 3,
    rotulo: "Nível 3 — Adaptação Intensiva (Decomposição Guiada e Pausas Ativas)",
    nome_curto: "Intensivo",
    objetivo_geral:
      "Apresentação guiada de uma etapa por vez com campos de registro dedicados, lembretes de autorregulação, pausas ativas estratégicas e organizadores visuais gráficos.",
    foco_pedagogico:
      "Suporte intensivo à função executiva, iniciação de tarefa e autorregulação em avaliações densas.",
    transformacoes_estruturais: [
      "Decomposição em subetapas com caixas de resolução exclusivas para cada etapa.",
      "Lembretes de checagem intermediária ('Revise se você concluiu a etapa anterior antes de prosseguir').",
      "Indicação de pausas estratégicas de autorregulação e respiração entre blocos avaliativos.",
      "Inclusão de organizadores visuais/gráficos para suporte à estruturação da resposta.",
    ],
    salvaguardas_antimuleta: [
      "Proibido o efeito muleta: a IA jamais faz as inferências ou fornece a resolução pelo aluno.",
      "Preservação inegociável dos objetivos de aprendizagem e dos conceitos da Trava Curricular.",
      "Garante a mesma habilidade avaliada, modificando unicamente o formato de demonstração.",
    ],
  },
];

/**
 * Calibração local síncrona / fallback quando o Backend FastAPI estiver indisponível.
 */
export function calibrateScaffoldingLocally(
  selectedIds: string[],
  nivel: ScaffoldingLevel,
  catalog = FALLBACK_OFFICIAL_CATALOG
): ScaffoldingCalibrationResult {
  if (![1, 2, 3].includes(nivel)) {
    throw new IrisApiError(
      `Nível de andaime inválido (${nivel}). Deve ser 1 (Leve), 2 (Moderado) ou 3 (Intensivo).`,
      "INVALID_SCAFFOLDING_LEVEL",
      422,
      "nivel"
    );
  }

  const uniqueIds = Array.from(new Set(selectedIds));
  if (uniqueIds.length === 0) {
    throw new IrisApiError(
      "Selecione ao menos 1 característica funcional na Etapa 2 antes de calibrar o nível de andaime.",
      "EMPTY_CHARACTERISTIC_SELECTION",
      422,
      "selected_ids"
    );
  }

  const catalogMap = new Map<string, CharacteristicItem>(
    catalog.caracteristicas.map((c) => [c.id_caracteristica, c])
  );

  const unknown = uniqueIds.filter((id) => !catalogMap.has(id));
  if (unknown.length > 0) {
    throw new IrisApiError(
      `Característica(s) funcional(is) não reconhecida(s) no catálogo: ${unknown.join(", ")}.`,
      "UNKNOWN_CHARACTERISTIC_ID",
      422,
      "selected_ids"
    );
  }

  const nivelKey = `nivel_${nivel}` as "nivel_1" | "nivel_2" | "nivel_3";
  const diretrizes: CharacteristicScaffoldingDirectiveItem[] = uniqueIds.map((id) => {
    const item = catalogMap.get(id)!;
    const guideline = item.diretrizes_andaime[nivelKey];
    return {
      id_caracteristica: item.id_caracteristica,
      nome_caracteristica: item.nome,
      nivel,
      rotulo: guideline.rotulo,
      objetivo_andaime: guideline.objetivo_andaime,
      acoes_permitidas: [...guideline.acoes_permitidas],
      restricoes_escopo: [...guideline.restricoes_escopo],
    };
  });

  const allIds = catalog.caracteristicas.map((c) => c.id_caracteristica);
  const blockedIds = allIds.filter((id) => !uniqueIds.includes(id)).sort();
  const meta = FALLBACK_SCAFFOLDING_LEVELS.find((m) => m.nivel === nivel)!;

  return {
    status: "success",
    nivel,
    rotulo_nivel: meta.rotulo,
    nome_curto: meta.nome_curto,
    objetivo_geral: meta.objetivo_geral,
    foco_pedagogico: meta.foco_pedagogico,
    transformacoes_estruturais: [...meta.transformacoes_estruturais],
    salvaguardas_antimuleta: [...meta.salvaguardas_antimuleta],
    total_caracteristicas_afetadas: diretrizes.length,
    caracteristicas_afetadas: diretrizes,
    caracteristicas_bloqueadas_ids: blockedIds,
    aviso_antimuleta: AVISO_ANTIMULETA_PADRAO,
  };
}

/**
 * Consulta metadados informativos dos 3 níveis de andaime no Backend, com fallback local.
 */
export async function fetchScaffoldingLevels(): Promise<ScaffoldingLevelMeta[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/scaffolding/levels`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.niveis) && data.niveis.length === 3) {
        return data.niveis as ScaffoldingLevelMeta[];
      }
    }
  } catch {
    // Falha silenciosa para contingência local
  }

  return FALLBACK_SCAFFOLDING_LEVELS;
}

/**
 * Calibra a diretiva de andaime enviando o payload ao Backend FastAPI, com contingência local.
 */
export async function calibrateScaffoldingSession(
  payload: ScaffoldingCalibrationPayload
): Promise<ScaffoldingCalibrationResult> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/scaffolding/calibrate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        selected_ids: payload.selected_ids,
        nivel: payload.nivel,
        id_catalogo: payload.id_catalogo || "tdah_funcoes_executivas_v1",
      }),
    });

    if (res.ok) {
      const data = (await res.json()) as ScaffoldingCalibrationResult;
      return data;
    }

    const errorJson = await res.json().catch(() => null);
    const detail = errorJson?.detail;
    if (detail && typeof detail === "object") {
      throw new IrisApiError(
        detail.detail || "Erro de validação na calibração de andaime.",
        detail.code || "SCAFFOLDING_VALIDATION_ERROR",
        res.status,
        detail.field
      );
    }
  } catch (err) {
    if (err instanceof IrisApiError) {
      throw err;
    }
    // Falha de rede: fallback local determinístico
  }

  return calibrateScaffoldingLocally(payload.selected_ids, payload.nivel);
}

/**
 * Persiste a calibração de andaime aprovada na sessão do navegador (Zero-Database).
 */
export function saveScaffoldingToSession(result: ScaffoldingCalibrationResult): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(SCAFFOLDING_STORAGE_KEY, JSON.stringify(result));
  } catch {
    // Ignora restrições de sessionStorage
  }
}

/**
 * Recupera a calibração de andaime salva na sessão do navegador.
 */
export function loadScaffoldingFromSession(): ScaffoldingCalibrationResult | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SCAFFOLDING_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ScaffoldingCalibrationResult;
  } catch {
    return null;
  }
}

/**
 * Limpa a calibração de andaime da sessão do navegador.
 */
export function clearScaffoldingFromSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(SCAFFOLDING_STORAGE_KEY);
  } catch {
    // Ignora restrições de sessionStorage
  }
}
