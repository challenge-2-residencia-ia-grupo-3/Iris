/**
 * Cliente HTTP e persistência em sessão para o Sistema Multiagentes da Etapa 4
 * (Issues #15, #16, #17, #18 e #19).
 *
 * Endpoint consumido:
 * - POST /api/v1/agents/adapt
 */

import { STEP5_ADAPTACAO_STORAGE_KEY, Step5Entrada } from "./comparisonCards";
import { IrisApiError } from "./materialsApi";
import { AuditorInvariantsContract, ScaffoldingLevel } from "./scaffoldingApi";

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const STEP4_RESULT_STORAGE_KEY = "iris_session_step4_multiagent_v1";

export type AgentProviderOption = "auto" | "anthropic" | "extractive" | "ollama" | "groq";

export interface MultiAgentAdaptPayload {
  text: string;
  titulo?: string;
  selected_ids: string[];
  nivel: ScaffoldingLevel;
  disciplina?: string;
  ano_escolar?: string;
  trava_manual_docente?: string[];
  invariantes_etapa3?: AuditorInvariantsContract;
  provider?: AgentProviderOption;
  model?: string;
  metodo_rag?: string;
  max_tentativas?: number;
  intrusao_bloqueia?: boolean;
  simular_autocorrecao?: boolean;
}

export interface AuditAttemptTrace {
  tentativa: number;
  texto_minuta: string;
  justificativas: string[];
  escopo_aprovado: boolean;
  violacoes_escopo: string[];
  trcc: number | null;
  conceitos_retidos: string[];
  conceitos_ausentes: string[];
  intocaveis_ausentes: string[];
  resolucao_indevida: boolean;
  intrusoes: string[];
  aprovado_auditor: boolean;
  motivos_auditor: string[];
  feedback_gerado: string | null;
  total_ms: number;
}

export interface ExtractorTrace {
  invariants: {
    conceitos_obrigatorios: string[];
    termos_tecnicos_intocaveis: string[];
    verbo_comando_bncc: string;
    operacao_cognitiva: string;
    habilidade_bncc_sugerida: string | null;
    alerta_anti_muleta: string | null;
    justificativa_preservacao: string;
  };
  telemetry: {
    provider: string;
    model: string;
    used_fallback: boolean;
    total_ms: number;
    prompt_tokens: number;
    completion_tokens: number;
  };
}

export interface StrategistTrace {
  diretiva: string;
  intervencoes: Array<{
    id_caracteristica: string;
    texto: string;
    citacoes: string[];
    origem: "modelo" | "catalogo";
  }>;
  fontes: Array<{
    rotulo: string;
    chunk_id: string;
    doc: string;
    titulo: string;
    pagina: string | null;
    url: string;
    referencia: string;
    caracteristicas: string[];
    aviso_de_uso: string | null;
  }>;
  caracteristicas_sem_evidencia: string[];
  trechos_fora_do_filtro: string[];
  intervencoes_descartadas: Array<{ id_caracteristica?: string; texto?: string; motivo?: string }>;
  telemetry: {
    metodo_solicitado: string;
    metodo_efetivo: string;
    provider: string;
    model: string;
    used_fallback: boolean;
    motivo_fallback: string | null;
    n_trechos: number;
    total_ms: number;
    total_tokens: number;
  };
}

export interface QuestionMultiAgentTrace {
  id: string;
  numero_original: string;
  original: string;
  adaptado: string;
  justificativas: string[];
  id_caracteristica: string;
  caracteristicas_selecionadas: string[];
  nivel: ScaffoldingLevel;
  adaptacao_aplicada: boolean;
  aprovado_final: boolean;
  requer_revisao_humana: boolean;
  extrator: ExtractorTrace;
  estrategista: StrategistTrace;
  tentativas: AuditAttemptTrace[];
  ciclo_resumo: {
    chamadas: number;
    chamadas_com_fallback: number;
    total_ms: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    nivel: number;
    limite_ms: number;
    dentro_do_limite: boolean;
  };
}

export interface MultiAgentMaterialResponse {
  status: string;
  titulo: string;
  provider: string;
  model: string;
  nivel: ScaffoldingLevel;
  selected_ids: string[];
  pii_substituicoes: number;
  total_questoes: number;
  aprovadas_auditor: number;
  requerem_revisao_humana: number;
  total_ms: number;
  total_tokens: number;
  etapa5_entrada: Step5Entrada;
  questoes_trace: QuestionMultiAgentTrace[];
}

export function saveStep5AdaptationToSession(entrada: Step5Entrada): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STEP5_ADAPTACAO_STORAGE_KEY, JSON.stringify(entrada));
  } catch {
    // Ignora restrições de sessionStorage
  }
}

export function saveStep4ResultToSession(result: MultiAgentMaterialResponse): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STEP4_RESULT_STORAGE_KEY, JSON.stringify(result));
    saveStep5AdaptationToSession(result.etapa5_entrada);
  } catch {
    // Ignora restrições de sessionStorage
  }
}

export function loadStep4ResultFromSession(): MultiAgentMaterialResponse | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STEP4_RESULT_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as MultiAgentMaterialResponse;
  } catch {
    return null;
  }
}

export function clearStep4ResultFromSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STEP4_RESULT_STORAGE_KEY);
  } catch {
    // Ignora restrições de sessionStorage
  }
}

export async function runMultiAgentAdaptation(
  payload: MultiAgentAdaptPayload
): Promise<MultiAgentMaterialResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/agents/adapt`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      cache: "no-store",
      body: JSON.stringify(payload),
    });
  } catch {
    throw new IrisApiError(
      "Não foi possível conectar ao backend FastAPI em " +
        `${API_BASE_URL}. Verifique se o servidor está ativo (make backend ou make up).`,
      "SERVER_UNAVAILABLE",
      0
    );
  }

  if (!response.ok) {
    const errorJson = await response.json().catch(() => null);
    const detail = errorJson?.detail;
    if (detail && typeof detail === "object") {
      throw new IrisApiError(
        String(detail.detail || "Falha ao executar o Sistema Multiagentes."),
        String(detail.code || "MULTIAGENT_ERROR"),
        response.status,
        detail.field ? String(detail.field) : undefined
      );
    }
    throw new IrisApiError(
      typeof detail === "string" ? detail : "Erro ao processar a adaptação multiagentes.",
      "HTTP_ERROR",
      response.status
    );
  }

  const data = (await response.json()) as MultiAgentMaterialResponse;
  saveStep4ResultToSession(data);
  return data;
}
