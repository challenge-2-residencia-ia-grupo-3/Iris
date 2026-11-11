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

export interface ThematicInterestOption {
  id: string;
  rotulo: string;
  descricao: string;
  ancora_sugerida: string;
}

export interface EngagementChannelOption {
  id: string;
  rotulo: string;
  descricao: string;
  estrategia_apoio: string;
}

export interface EngagementOptionsResponse {
  principio_dua: string;
  principio_dua_rotulo: string;
  diretriz_dua_referencia: string;
  obrigatorio: boolean;
  exige_laudo_medico: boolean;
  aviso_lgpd: string;
  regra_nao_substituicao: string;
  interesses_tematicos: ThematicInterestOption[];
  canais_engajamento_preferenciais: EngagementChannelOption[];
}

export interface EngagementProfileInput {
  interesses_tematicos: string[];
  interesses_customizados: string[];
  potencialidades: string;
  canais_engajamento_preferenciais: string[];
}

export interface EngagementMetadata {
  principio_dua: string;
  principio_dua_rotulo: string;
  diretriz_dua_referencia: string;
  interesses_tematicos: Array<{ id: string; rotulo: string; ancora_sugerida: string }>;
  interesses_customizados: string[];
  potencialidades: string | null;
  canais_engajamento_preferenciais: Array<{ id: string; rotulo: string; estrategia_apoio: string }>;
  possui_ancoras_motivacionais: boolean;
  sanitized: boolean;
  pii_removed_count: number;
  regra_nao_substituicao: string;
}

export interface MotivationalContext {
  principio_dua: string;
  principio_dua_rotulo: string;
  diretriz_dua_referencia: string;
  possui_ancoras_motivacionais: boolean;
  ancoras_tematicas: string[];
  canais_apoio: string[];
  potencialidades_estudante: string | null;
  diretrizes_prompt: string[];
  conceitos_trava_protegidos: string[];
  regra_nao_substituicao: string;
  prompt_section: string;
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
  engagement_metadata?: EngagementMetadata | null;
  motivational_context?: MotivationalContext | null;
}

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const SURGICAL_VECTOR_STORAGE_KEY = "iris_session_surgical_vector_v1";
export const ENGAGEMENT_PROFILE_STORAGE_KEY = "iris_session_engagement_profile_v1";
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

export const FALLBACK_ENGAGEMENT_OPTIONS: EngagementOptionsResponse = {
  principio_dua: "principio_1_engajamento",
  principio_dua_rotulo: "Princípio I do DUA — Rede de Engajamento (Múltiplas Formas de Engajamento)",
  diretriz_dua_referencia:
    "CAST / DUA — Recrutamento de Interesse (Ponto 7.2: otimizar relevância, valor e autenticidade) e Sustentação do Esforço",
  obrigatorio: false,
  exige_laudo_medico: false,
  aviso_lgpd:
    "Campos opcionais voltados exclusivamente às potencialidades e interesses temáticos do estudante (Princípio I do DUA). Não informe nomes próprios, dados civis ou diagnósticos clínicos.",
  regra_nao_substituicao:
    "Os interesses temáticos, potencialidades e canais de engajamento atuam exclusivamente como âncoras motivacionais periféricas. É estritamente proibido substituir, omitir ou simplificar conceitos obrigatórios da Trava Curricular.",
  interesses_tematicos: [
    {
      id: "esportes",
      rotulo: "Esportes e Movimento",
      descricao: "Exemplos ligados a modalidades esportivas, placares, treinos e trabalho em equipe.",
      ancora_sugerida: "Contextualizar analogias periféricas usando situações de jogo, regras ou pontuação esportiva.",
    },
    {
      id: "natureza",
      rotulo: "Natureza e Meio Ambiente",
      descricao: "Temáticas de ecossistemas, animais, plantas, clima e sustentabilidade.",
      ancora_sugerida: "Empregar exemplos ilustrativos ligados a fenômenos naturais, fauna ou observação ambiental.",
    },
    {
      id: "tecnologia",
      rotulo: "Tecnologia e Inovação",
      descricao: "Interesse por dispositivos digitais, robótica, aplicativos, programação e invenções.",
      ancora_sugerida: "Relacionar cenários introdutórios a ferramentas digitais, lógica de sistemas ou protótipos.",
    },
    {
      id: "artes_musica",
      rotulo: "Artes, Música e Cultura",
      descricao: "Expressões visuais, ritmo, cinema, quadrinhos, teatro e produção cultural.",
      ancora_sugerida: "Utilizar metáforas visuais, referências rítmicas ou conexões com produções culturais.",
    },
    {
      id: "jogos_logica",
      rotulo: "Jogos e Desafios Lógicos",
      descricao: "Tabuleiros, quebra-cabeças, missões, enigmas e desafios por fases.",
      ancora_sugerida: "Apresentar instruções introdutórias com senso de missão ou progresso em etapas.",
    },
    {
      id: "ciencias_praticas",
      rotulo: "Ciências Práticas e Experimentos",
      descricao: "Curiosidade por experimentos práticos, culinária científica, astronomia e laboratório.",
      ancora_sugerida: "Ancorar a motivação em situações de investigação prática ou observação experimental.",
    },
    {
      id: "narrativa_historica",
      rotulo: "Narrativas e Histórias",
      descricao: "Contação de histórias, biografias, mistérios históricos e linhas do tempo.",
      ancora_sugerida: "Enquadrar o contexto introdutório com sequência narrativa clara e personagens situacionais.",
    },
    {
      id: "cotidiano_pratico",
      rotulo: "Cotidiano e Vida Prática",
      descricao: "Situações reais do dia a dia, compras, transporte, organização pessoal e comunidade.",
      ancora_sugerida: "Conectar o apoio introdutório a cenários concretos vivenciados fora da escola.",
    },
  ],
  canais_engajamento_preferenciais: [
    {
      id: "esquemas_visuais",
      rotulo: "Esquemas Visuais e Mapas",
      descricao: "Facilidade com diagramas, tabelas organizadoras, ícones e mapas mentais.",
      estrategia_apoio: "Priorizar organização visual limpa, marcadores estruturados e quadros-síntese de apoio.",
    },
    {
      id: "exemplos_concretos",
      rotulo: "Exemplos Concretos Antes da Abstração",
      descricao: "Engaja melhor quando visualiza uma situação prática antes da regra abstrata.",
      estrategia_apoio: "Inserir âncora motivacional concreta na contextualização sem resolver a questão avaliada.",
    },
    {
      id: "etapas_curtas_gamificadas",
      rotulo: "Metas Curtas e Progresso Visível",
      descricao: "Responde bem a checkpoints rápidos e sensação de avanço passo a passo.",
      estrategia_apoio: "Sinalizar marcos curtos de progressão para sustentar o esforço ao longo da tarefa.",
    },
    {
      id: "narrativas_contextualizadas",
      rotulo: "Narrativas Contextualizadas",
      descricao: "Sustenta atenção quando há fio condutor ou propósito claro na atividade.",
      estrategia_apoio: "Conectar o enunciado a um contexto motivador breve mantendo 100% do rigor conceitual.",
    },
    {
      id: "recursos_audiovisuais",
      rotulo: "Apoio Audiovisual e Oralidade",
      descricao: "Facilidade ao explicar oralmente ou associar conceitos a recursos multimídia.",
      estrategia_apoio: "Sugerir roteiros breves de verbalização ou checagem oral como apoio complementar.",
    },
    {
      id: "mao_na_massa_cinestesico",
      rotulo: "Exploração Prática / Mão na Massa",
      descricao: "Maior envolvimento com tarefas ativas, manipuláveis ou simulação prática.",
      estrategia_apoio: "Sugerir rascunho ativo, sublinhado guiado ou registro manipulável durante a resolução.",
    },
  ],
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
 * Busca opções oficiais de interesses temáticos e canais preferenciais (`GET /api/v1/catalogs/engagement-options`).
 */
export async function fetchEngagementOptions(): Promise<{
  options: EngagementOptionsResponse;
  fromServer: boolean;
}> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/catalogs/engagement-options`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });

    if (response.ok) {
      const data = (await response.json()) as EngagementOptionsResponse;
      return { options: data, fromServer: true };
    }
  } catch {
    // Fallback resiliente para catálogo local
  }
  return { options: FALLBACK_ENGAGEMENT_OPTIONS, fromServer: false };
}

function buildLocalEngagementMetadata(
  profile?: EngagementProfileInput | null,
  options: EngagementOptionsResponse = FALLBACK_ENGAGEMENT_OPTIONS
): EngagementMetadata | null {
  if (!profile) return null;
  const interestMap = new Map(options.interesses_tematicos.map((i) => [i.id, i]));
  const channelMap = new Map(options.canais_engajamento_preferenciais.map((c) => [c.id, c]));

  const interesses = (profile.interesses_tematicos || [])
    .map((id) => interestMap.get(id))
    .filter((item): item is ThematicInterestOption => Boolean(item))
    .map((item) => ({
      id: item.id,
      rotulo: item.rotulo,
      ancora_sugerida: item.ancora_sugerida,
    }));

  const custom = Array.from(
    new Set((profile.interesses_customizados || []).map((s) => s.trim()).filter(Boolean))
  );

  const canais = (profile.canais_engajamento_preferenciais || [])
    .map((id) => channelMap.get(id))
    .filter((item): item is EngagementChannelOption => Boolean(item))
    .map((item) => ({
      id: item.id,
      rotulo: item.rotulo,
      estrategia_apoio: item.estrategia_apoio,
    }));

  const potencialidades = profile.potencialidades?.trim() ? profile.potencialidades.trim() : null;
  const possuiAncoras = Boolean(
    interesses.length > 0 || custom.length > 0 || potencialidades || canais.length > 0
  );

  return {
    principio_dua: options.principio_dua,
    principio_dua_rotulo: options.principio_dua_rotulo,
    diretriz_dua_referencia: options.diretriz_dua_referencia,
    interesses_tematicos: interesses,
    interesses_customizados: custom,
    potencialidades,
    canais_engajamento_preferenciais: canais,
    possui_ancoras_motivacionais: possuiAncoras,
    sanitized: false,
    pii_removed_count: 0,
    regra_nao_substituicao: options.regra_nao_substituicao,
  };
}

/**
 * Calcula localmente o vetor cirúrgico de características ativadas vs. bloqueadas (mesma regra determinística do Backend).
 */
export function buildLocalSurgicalSelection(
  selectedIds: string[],
  catalog: CharacteristicsCatalogResponse = FALLBACK_OFFICIAL_CATALOG,
  engagementProfile?: EngagementProfileInput | null
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

  const engagementMeta = buildLocalEngagementMetadata(engagementProfile);

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
    ...(engagementMeta ? { engagement_metadata: engagementMeta } : {}),
  };
}

/**
 * Submete a seleção cirúrgica + perfil opcional de engajamento da Etapa 2 para
 * `POST /api/v1/catalogs/characteristics/select` e persiste na sessão do cliente (`sessionStorage`).
 */
export async function submitSurgicalCharacteristicSelection(
  selectedIds: string[],
  catalog: CharacteristicsCatalogResponse = FALLBACK_OFFICIAL_CATALOG,
  engagementProfile?: EngagementProfileInput | null
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

  const bodyPayload: Record<string, unknown> = {
    selected_ids: selectedIds,
    id_catalogo: catalog.id_catalogo,
  };
  if (engagementProfile) {
    bodyPayload.engagement_profile = {
      interesses_tematicos: engagementProfile.interesses_tematicos || [],
      interesses_customizados: engagementProfile.interesses_customizados || [],
      potencialidades: engagementProfile.potencialidades || "",
      canais_engajamento_preferenciais: engagementProfile.canais_engajamento_preferenciais || [],
    };
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/catalogs/characteristics/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bodyPayload),
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
    if (engagementProfile) {
      saveEngagementProfileToSession(engagementProfile);
    }
    return result;
  } catch (err) {
    if (err instanceof IrisApiError) {
      throw err;
    }
    // Se o backend estiver offline, aplica a validação determinística local e persiste na sessão
    const fallbackResult = buildLocalSurgicalSelection(selectedIds, catalog, engagementProfile);
    saveSurgicalSelectionToSession(fallbackResult);
    if (engagementProfile) {
      saveEngagementProfileToSession(engagementProfile);
    }
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

/**
 * Persiste os metadados opcionais de potencialidades e interesses na sessão do navegador.
 */
export function saveEngagementProfileToSession(profile: EngagementProfileInput): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(ENGAGEMENT_PROFILE_STORAGE_KEY, JSON.stringify(profile));
  } catch {
    // Ignora caso sessionStorage esteja indisponível
  }
}

/**
 * Recupera o perfil opcional de engajamento salvo na sessão do navegador.
 */
export function loadEngagementProfileFromSession(): EngagementProfileInput | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(ENGAGEMENT_PROFILE_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as EngagementProfileInput;
  } catch {
    return null;
  }
}

/**
 * Limpa os metadados opcionais de engajamento salvos na sessão do navegador.
 */
export function clearEngagementProfileFromSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(ENGAGEMENT_PROFILE_STORAGE_KEY);
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

