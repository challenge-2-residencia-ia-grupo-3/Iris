/**
 * Cliente HTTP e persistência em sessão para o Catálogo de Características Funcionais Atômicas
 * e Seleção Cirúrgica da Etapa 2 (História 1.2.1 — Issue #8).
 *
 * Endpoints consumidos:
 * - GET  /api/v1/catalogs/characteristics
 * - POST /api/v1/catalogs/characteristics/select
 */

import { IrisApiError, MaterialMetadata } from "./materialsApi";
import officialTdahCatalogRaw from "../../../rag/catalogs/tdah_caracteristicas_funcionais.json";

export interface Step1SelectedFileInfo {
  name: string;
  sizeBytes: number;
  extension: string;
  status: "accepted" | "rejected" | "uploading";
}

export interface Step1SessionState {
  textContent: string;
  metadata: MaterialMetadata | null;
  selectedFile: Step1SelectedFileInfo | null;
  confirmedForStep2: boolean;
}

export interface BibliographicReferenceItem {
  doc_id: string;
  citacao_curta: string;
  tipo_evidencia: string;
  ponto_verificacao_dua?: string | null;
}

export interface ScaffoldingLevelGuidelineItem {
  nivel: 1 | 2 | 3;
  rotulo: string;
  objetivo_andaime: string;
  acoes_permitidas: string[];
  restricoes_escopo: string[];
}

export interface CharacteristicItem {
  id_caracteristica: string;
  nome: string;
  descricao_observavel: string;
  exemplos_manifestacao_sala: string[];
  barreira_rag_associada: string;
  principio_dua_primario: "representacao" | "acao_e_expressao" | "engajamento";
  palavras_chave_busca: string[];
  diretrizes_andaime: {
    nivel_1: ScaffoldingLevelGuidelineItem;
    nivel_2: ScaffoldingLevelGuidelineItem;
    nivel_3: ScaffoldingLevelGuidelineItem;
  };
  referencias_bibliograficas: BibliographicReferenceItem[];
}

export interface CharacteristicsCatalogResponse {
  id_catalogo: string;
  versao_schema: string;
  perfil_referencia: string;
  titulo: string;
  descricao: string;
  aviso_etico_lgpd: string;
  caracteristicas: CharacteristicItem[];
  total_caracteristicas: number;
  exige_laudo_medico: boolean;
  barreiras_disponiveis: string[];
  principios_dua_disponiveis: string[];
}

export interface SurgicalSelectionResponse {
  status: string;
  message: string;
  id_catalogo: string;
  total_catalog_characteristics: number;
  selected_count: number;
  blocked_count: number;
  selected_ids: string[];
  blocked_ids: string[];
  active_characteristics: CharacteristicItem[];
  scope_isolation_rule: string;
}

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const SURGICAL_VECTOR_STORAGE_KEY = "iris_session_surgical_vector_v1";
export const STEP1_MATERIAL_STORAGE_KEY = "iris_session_step1_material_v1";

/**
 * Rótulos amigáveis para as barreiras funcionais do RAG (filtros atômicos desacoplados de rótulo clínico).
 */
export const BARREIRA_LABELS: Record<string, string> = {
  memoria_trabalho: "Memória de Trabalho",
  leitura_texto_longo: "Leitura de Textos Longos",
  sobrecarga_visual: "Poluição e Sobrecarga Visual",
  controle_inibitorio: "Controle Inibitório / Impulsividade",
  organizacao_sequencial: "Organização Sequencial e Escrita",
  atencao_sustentada: "Atenção Sustentada e Fadiga",
  flexibilidade_cognitiva: "Flexibilidade Cognitiva e Transição",
  iniciacao_tarefa: "Iniciação de Tarefas Abertas",
  velocidade_processamento: "Velocidade de Processamento",
};

/**
 * Rótulos amigáveis para os Princípios do DUA (CAST).
 */
export const PRINCIPIO_DUA_LABELS: Record<string, string> = {
  representacao: "DUA I — Representação",
  acao_e_expressao: "DUA II — Ação e Expressão",
  engajamento: "DUA III — Engajamento",
};

/**
 * Catálogo local de contingência derivado diretamente da fonte oficial (`rag/catalogs/tdah_caracteristicas_funcionais.json`)
 * para garantir paridade exata quando o servidor FastAPI estiver offline.
 */
const officialCatalogItems = officialTdahCatalogRaw.caracteristicas as CharacteristicItem[];

export const FALLBACK_OFFICIAL_CATALOG: CharacteristicsCatalogResponse = {
  id_catalogo: officialTdahCatalogRaw.id_catalogo,
  versao_schema: officialTdahCatalogRaw.versao_schema,
  perfil_referencia: officialTdahCatalogRaw.perfil_referencia,
  titulo: officialTdahCatalogRaw.titulo,
  descricao: officialTdahCatalogRaw.descricao,
  aviso_etico_lgpd: officialTdahCatalogRaw.aviso_etico_lgpd,
  caracteristicas: officialCatalogItems,
  total_caracteristicas: officialCatalogItems.length,
  exige_laudo_medico: false,
  barreiras_disponiveis: Array.from(new Set(officialCatalogItems.map((c) => c.barreira_rag_associada))).sort(),
  principios_dua_disponiveis: Array.from(new Set(officialCatalogItems.map((c) => c.principio_dua_primario))).sort(),
};

/**
 * Busca o catálogo oficial de características funcionais atômicas via `GET /api/v1/catalogs/characteristics`.
 * Caso o servidor não esteja acessível, retorna o catálogo oficial local validado.
 */
export async function fetchCharacteristicsCatalog(): Promise<{
  catalog: CharacteristicsCatalogResponse;
  fromServer: boolean;
}> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/catalogs/characteristics`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });

    if (response.ok) {
      const data = (await response.json()) as CharacteristicsCatalogResponse;
      return { catalog: data, fromServer: true };
    }
  } catch {
    // Fallback resiliente para catálogo local
  }
  return { catalog: FALLBACK_OFFICIAL_CATALOG, fromServer: false };
}

/**
 * Calcula localmente o vetor cirúrgico de características ativadas vs. bloqueadas (mesma regra determinística do Backend).
 */
export function buildLocalSurgicalSelection(
  selectedIds: string[],
  catalog: CharacteristicsCatalogResponse = FALLBACK_OFFICIAL_CATALOG
): SurgicalSelectionResponse {
  const uniqueIds = Array.from(new Set(selectedIds.map((id) => id.trim()).filter(Boolean)));
  if (uniqueIds.length === 0) {
    throw new IrisApiError(
      "Selecione pelo menos uma característica funcional observada em sala de aula para definir o escopo permitido de adaptação antes de avançar.",
      "EMPTY_CHARACTERISTIC_SELECTION",
      422,
      "selected_ids"
    );
  }

  const catalogMap = new Map(catalog.caracteristicas.map((c) => [c.id_caracteristica, c]));
  const unknown = uniqueIds.filter((id) => !catalogMap.has(id));
  if (unknown.length > 0) {
    throw new IrisApiError(
      `Característica(s) funcional(is) não reconhecida(s) no catálogo: ${unknown.join(", ")}.`,
      "UNKNOWN_CHARACTERISTIC_ID",
      422,
      "selected_ids"
    );
  }

  const selectedSet = new Set(uniqueIds);
  const activeCharacteristics = uniqueIds.map((id) => catalogMap.get(id)!);
  const blockedIds = catalog.caracteristicas
    .map((c) => c.id_caracteristica)
    .filter((id) => !selectedSet.has(id));

  return {
    status: "success",
    message: `Escopo cirúrgico registrado: ${uniqueIds.length} característica(s) ativada(s) para adaptação e ${blockedIds.length} característica(s) bloqueada(s) para preservar a autonomia do estudante.`,
    id_catalogo: catalog.id_catalogo,
    total_catalog_characteristics: catalog.caracteristicas.length,
    selected_count: uniqueIds.length,
    blocked_count: blockedIds.length,
    selected_ids: uniqueIds,
    blocked_ids: blockedIds,
    active_characteristics: activeCharacteristics,
    scope_isolation_rule:
      "O pipeline de adaptação atuará exclusivamente sobre as características em 'selected_ids'. Todas as dimensões listadas em 'blocked_ids' permanecem bloqueadas para intervenção, preservando 100% da estrutura e autonomia original.",
  };
}

/**
 * Submete a seleção cirúrgica da Etapa 2 para `POST /api/v1/catalogs/characteristics/select`
 * e persiste o vetor cirúrgico validado na sessão do cliente (`sessionStorage`).
 */
export async function submitSurgicalCharacteristicSelection(
  selectedIds: string[],
  catalog: CharacteristicsCatalogResponse = FALLBACK_OFFICIAL_CATALOG
): Promise<SurgicalSelectionResponse> {
  // 1. Validação imediata de seleção vazia no cliente
  if (!Array.isArray(selectedIds) || selectedIds.filter((id) => id.trim().length > 0).length === 0) {
    throw new IrisApiError(
      "Selecione pelo menos uma característica funcional observada em sala de aula para definir o escopo permitido de adaptação antes de avançar.",
      "EMPTY_CHARACTERISTIC_SELECTION",
      422,
      "selected_ids"
    );
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/catalogs/characteristics/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_ids: selectedIds,
        id_catalogo: catalog.id_catalogo,
      }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const detail = body?.detail;
      if (detail && typeof detail === "object") {
        throw new IrisApiError(
          detail.detail || "Falha ao validar a seleção cirúrgica de características.",
          detail.code || "VALIDATION_ERROR",
          response.status,
          detail.field
        );
      }
      throw new IrisApiError(
        "Falha ao validar a seleção cirúrgica de características no servidor.",
        "HTTP_ERROR",
        response.status
      );
    }

    const result = (await response.json()) as SurgicalSelectionResponse;
    saveSurgicalSelectionToSession(result);
    return result;
  } catch (err) {
    if (err instanceof IrisApiError) {
      throw err;
    }
    // Se o backend estiver offline, aplica a validação determinística local e persiste na sessão
    const fallbackResult = buildLocalSurgicalSelection(selectedIds, catalog);
    saveSurgicalSelectionToSession(fallbackResult);
    return fallbackResult;
  }
}

/**
 * Persiste o vetor cirúrgico de seleção na sessão do navegador (Stateless / Zero-Database no servidor).
 */
export function saveSurgicalSelectionToSession(selection: SurgicalSelectionResponse): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(SURGICAL_VECTOR_STORAGE_KEY, JSON.stringify(selection));
  } catch {
    // Ignora caso sessionStorage esteja indisponível
  }
}

/**
 * Recupera o vetor cirúrgico salvo na sessão do navegador.
 */
export function loadSurgicalSelectionFromSession(): SurgicalSelectionResponse | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SURGICAL_VECTOR_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SurgicalSelectionResponse;
  } catch {
    return null;
  }
}

/**
 * Remove o vetor cirúrgico salvo na sessão do navegador ao limpar ou invalidar a seleção.
 */
export function clearSurgicalSelectionFromSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(SURGICAL_VECTOR_STORAGE_KEY);
  } catch {
    // Ignora caso sessionStorage esteja indisponível
  }
}

export const STEP1_STATE_STORAGE_KEY = "iris_session_step1_state_v1";

/**
 * Persiste o material e metadados da Etapa 1 na sessão do navegador para revisão ao voltar da Etapa 2.
 */
export function saveStep1StateToSession(state: Step1SessionState): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STEP1_MATERIAL_STORAGE_KEY, state.textContent);
    window.sessionStorage.setItem(STEP1_STATE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignora caso sessionStorage esteja indisponível
  }
}

/**
 * Recupera o material e metadados da Etapa 1 salvos na sessão do navegador.
 */
export function loadStep1StateFromSession(): Step1SessionState | null {
  if (typeof window === "undefined") return null;
  try {
    const rawState = window.sessionStorage.getItem(STEP1_STATE_STORAGE_KEY);
    if (rawState) {
      return JSON.parse(rawState) as Step1SessionState;
    }
    const rawText = window.sessionStorage.getItem(STEP1_MATERIAL_STORAGE_KEY);
    if (rawText) {
      return {
        textContent: rawText,
        metadata: null,
        selectedFile: null,
        confirmedForStep2: true,
      };
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Remove o material da Etapa 1 da sessão do navegador ao limpar o formulário.
 */
export function clearStep1StateFromSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STEP1_MATERIAL_STORAGE_KEY);
    window.sessionStorage.removeItem(STEP1_STATE_STORAGE_KEY);
  } catch {
    // Ignora caso sessionStorage esteja indisponível
  }
}

