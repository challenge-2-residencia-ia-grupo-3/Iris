"use client";

import React, { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  CheckSquare,
  ChevronDown,
  ChevronUp,
  Compass,
  Contrast,
  Filter,
  HeartHandshake,
  Info,
  Layers,
  Loader2,
  Lock,
  Moon,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Square,
  Sun,
  Unlock,
} from "lucide-react";
import { IrisLogoBanner } from "./IrisLogoBanner";
import { IrisSidebar, Step2SubStep } from "./IrisSidebar";
import { useTheme } from "@/contexts/ThemeContext";
import {
  BARREIRA_LABELS,
  CharacteristicItem,
  CharacteristicsCatalogResponse,
  EngagementOptionsResponse,
  EngagementProfileInput,
  FALLBACK_ENGAGEMENT_OPTIONS,
  FALLBACK_OFFICIAL_CATALOG,
  PRINCIPIO_DUA_LABELS,
  SurgicalSelectionResponse,
  clearEngagementProfileFromSession,
  clearSurgicalSelectionFromSession,
  fetchCharacteristicsCatalog,
  fetchEngagementOptions,
  loadEngagementProfileFromSession,
  loadStep1StateFromSession,
  loadSurgicalSelectionFromSession,
  saveEngagementProfileToSession,
  submitSurgicalCharacteristicSelection,
} from "@/services/catalogsApi";
import { IrisApiError } from "@/services/materialsApi";

interface Step2FunctionalProfileProps {
  teacherEmail?: string;
  materialPreviewText?: string;
  onBackToStep1?: () => void;
  onAdvanceToStep3?: (selection: SurgicalSelectionResponse) => void;
  darkMode?: boolean;
  onToggleDarkMode?: () => void;
}

/**
 * Componente da Etapa 2 (Histórias 1.2.1 e 1.2.2) organizado no fluxo guiado A → B → C:
 * - A) Perfil funcional (Filtrar por Dimensão Funcional + Seleção Cirúrgica de Características — RF-04)
 * - B) Interesses temáticos, Canais preferenciais e Potencialidades observadas (Opcional — Princípio I do DUA / RF-05)
 * - C) Resumo da adaptação e confirmação para a Etapa 3
 */
export function Step2FunctionalProfile({
  teacherEmail = "marina.alves@escola.edu.br",
  materialPreviewText,
  onBackToStep1,
  onAdvanceToStep3,
  darkMode,
  onToggleDarkMode,
}: Step2FunctionalProfileProps) {
  const router = useRouter();
  const { darkMode: contextDarkMode, toggleDarkMode: contextToggleDarkMode } = useTheme();
  const isDarkMode = darkMode ?? contextDarkMode;
  const handleToggleDarkMode = onToggleDarkMode ?? contextToggleDarkMode;

  const searchInputId = useId();
  const alertRegionId = useId();
  const potencialidadesInputId = useId();

  const [highContrast, setHighContrast] = useState(false);
  const [currentSubStep, setCurrentSubStep] = useState<Step2SubStep>("a");

  const [catalog, setCatalog] = useState<CharacteristicsCatalogResponse>(FALLBACK_OFFICIAL_CATALOG);
  const [engagementOptions, setEngagementOptions] = useState<EngagementOptionsResponse>(
    FALLBACK_ENGAGEMENT_OPTIONS
  );
  const [isLoadingCatalog, setIsLoadingCatalog] = useState<boolean>(true);
  const [loadedFromApi, setLoadedFromApi] = useState<boolean>(false);
  const [sessionMaterialPreview, setSessionMaterialPreview] = useState<string>("");

  // Passo (A): Seleção cirúrgica e filtro por dimensão funcional
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [activeBarrierFilter, setActiveBarrierFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [expandedDetails, setExpandedDetails] = useState<Record<string, boolean>>({});

  // Passo (B): Interesses temáticos, canais preferenciais e potencialidades (Princípio I DUA)
  const [selectedInterests, setSelectedInterests] = useState<string[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [potencialidades, setPotencialidades] = useState<string>("");

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [confirmedSelection, setConfirmedSelection] = useState<SurgicalSelectionResponse | null>(null);
  const [attemptedEmptySubmit, setAttemptedEmptySubmit] = useState<boolean>(false);
  const [feedbackBanner, setFeedbackBanner] = useState<{
    type: "success" | "error" | "warning" | "info";
    title: string;
    message: string;
    code?: string;
  } | null>(null);

  useEffect(() => {
    const root = document.documentElement;
    if (highContrast) {
      root.classList.add("high-contrast");
    } else {
      root.classList.remove("high-contrast");
    }
  }, [highContrast]);

  // Carrega catálogos oficiais da Etapa 2 e restaura seleção/engajamento da sessão
  useEffect(() => {
    const savedStep1 = loadStep1StateFromSession();
    if (savedStep1?.textContent) {
      setSessionMaterialPreview(savedStep1.textContent);
    }

    let active = true;
    async function initStep2() {
      setIsLoadingCatalog(true);
      const [{ catalog: fetchedCatalog, fromServer }, { options: fetchedEngagement }] =
        await Promise.all([fetchCharacteristicsCatalog(), fetchEngagementOptions()]);
      if (!active) return;
      setCatalog(fetchedCatalog);
      setEngagementOptions(fetchedEngagement);
      setLoadedFromApi(fromServer);
      setIsLoadingCatalog(false);

      const saved = loadSurgicalSelectionFromSession();
      if (
        saved &&
        saved.id_catalogo === fetchedCatalog.id_catalogo &&
        Array.isArray(saved.selected_ids) &&
        saved.selected_ids.length > 0
      ) {
        const validSet = new Set(fetchedCatalog.caracteristicas.map((c) => c.id_caracteristica));
        const restored = saved.selected_ids.filter((id) => validSet.has(id));
        if (restored.length > 0) {
          setSelectedIds(restored);
          setConfirmedSelection(saved);
        }
      }

      const savedEngagement = loadEngagementProfileFromSession();
      if (savedEngagement) {
        setSelectedInterests(savedEngagement.interesses_tematicos || []);
        setSelectedChannels(savedEngagement.canais_engajamento_preferenciais || []);
        setPotencialidades(savedEngagement.potencialidades || "");
      }
    }
    initStep2();
    return () => {
      active = false;
    };
  }, []);

  const currentEngagementProfile: EngagementProfileInput = useMemo(
    () => ({
      interesses_tematicos: selectedInterests,
      interesses_customizados: [],
      potencialidades,
      canais_engajamento_preferenciais: selectedChannels,
    }),
    [selectedInterests, potencialidades, selectedChannels]
  );

  // Mantém o perfil opcional sincronizado em sessionStorage
  useEffect(() => {
    saveEngagementProfileToSession(currentEngagementProfile);
  }, [currentEngagementProfile]);

  const effectiveMaterialPreview = materialPreviewText || sessionMaterialPreview;

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const totalCount = catalog.caracteristicas.length;
  const selectedCount = selectedIds.length;
  const blockedCount = totalCount - selectedCount;

  const totalInterestsCount = selectedInterests.length;
  const engagementDetailsCount =
    selectedChannels.length + (potencialidades.trim().length > 0 ? 1 : 0);
  const engagementAnchorCount = totalInterestsCount + engagementDetailsCount;

  // Características filtradas por dimensão funcional e busca textual
  const filteredCharacteristics = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return catalog.caracteristicas.filter((item) => {
      if (activeBarrierFilter !== "all" && item.barreira_rag_associada !== activeBarrierFilter) {
        return false;
      }
      if (!q) return true;
      const haystack = [
        item.nome,
        item.descricao_observavel,
        ...item.exemplos_manifestacao_sala,
        ...(BARREIRA_LABELS[item.barreira_rag_associada]
          ? [BARREIRA_LABELS[item.barreira_rag_associada]]
          : []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [catalog.caracteristicas, activeBarrierFilter, searchQuery]);

  const handleToggleCharacteristic = useCallback((idCaracteristica: string) => {
    setConfirmedSelection(null);
    setFeedbackBanner(null);
    setAttemptedEmptySubmit(false);
    clearSurgicalSelectionFromSession();
    setSelectedIds((prev) => {
      if (prev.includes(idCaracteristica)) {
        return prev.filter((id) => id !== idCaracteristica);
      }
      return [...prev, idCaracteristica];
    });
  }, []);

  const handleToggleDetails = (idCaracteristica: string, evt: React.MouseEvent) => {
    evt.stopPropagation();
    setExpandedDetails((prev) => ({
      ...prev,
      [idCaracteristica]: !prev[idCaracteristica],
    }));
  };

  const handleToggleInterest = useCallback((interestId: string) => {
    setConfirmedSelection(null);
    setFeedbackBanner(null);
    setSelectedInterests((prev) =>
      prev.includes(interestId) ? prev.filter((id) => id !== interestId) : [...prev, interestId]
    );
  }, []);

  const handleToggleChannel = useCallback((channelId: string) => {
    setConfirmedSelection(null);
    setFeedbackBanner(null);
    setSelectedChannels((prev) =>
      prev.includes(channelId) ? prev.filter((id) => id !== channelId) : [...prev, channelId]
    );
  }, []);

  const handleClearEngagement = () => {
    setConfirmedSelection(null);
    setSelectedInterests([]);
    setSelectedChannels([]);
    setPotencialidades("");
    clearEngagementProfileFromSession();
  };

  const handleClearSelection = () => {
    setSelectedIds([]);
    setConfirmedSelection(null);
    setCurrentSubStep("a");
    setAttemptedEmptySubmit(true);
    clearSurgicalSelectionFromSession();
    setFeedbackBanner({
      type: "warning",
      title: "Nenhuma característica funcional selecionada",
      message:
        "O avanço para os próximos passos está bloqueado. Selecione pelo menos 1 característica observada em sala de aula.",
      code: "EMPTY_CHARACTERISTIC_SELECTION",
    });
  };

  const navigateToSubStep = (target: Step2SubStep) => {
    if (target !== "a" && selectedIds.length === 0) {
      setAttemptedEmptySubmit(true);
      setFeedbackBanner({
        type: "error",
        title: "Seleção obrigatória para continuar",
        message:
          "Selecione pelo menos uma característica funcional no passo a) Perfil funcional antes de prosseguir.",
        code: "EMPTY_CHARACTERISTIC_SELECTION",
      });
      return;
    }
    setFeedbackBanner(null);
    setCurrentSubStep(target);
  };

  // Submete o vetor cirúrgico + perfil opcional de engajamento para POST /api/v1/catalogs/characteristics/select
  const handleConfirmAndAdvance = async () => {
    if (selectedIds.length === 0) {
      setAttemptedEmptySubmit(true);
      setCurrentSubStep("a");
      setFeedbackBanner({
        type: "error",
        title: "Seleção obrigatória para avançar",
        message:
          "Selecione pelo menos uma característica funcional observada em sala de aula antes de prosseguir para a Etapa 3.",
        code: "EMPTY_CHARACTERISTIC_SELECTION",
      });
      return;
    }

    if (confirmedSelection && onAdvanceToStep3) {
      onAdvanceToStep3(confirmedSelection);
      return;
    }

    setIsSubmitting(true);
    setFeedbackBanner(null);

    try {
      const response = await submitSurgicalCharacteristicSelection(
        selectedIds,
        catalog,
        currentEngagementProfile
      );
      setConfirmedSelection(response);
      const piiInfo =
        response.engagement_metadata && response.engagement_metadata.pii_removed_count > 0
          ? ` (${response.engagement_metadata.pii_removed_count} dado(s) identificável(is) sanitizado(s) automaticamente pela proteção LGPD).`
          : "";
      setFeedbackBanner({
        type: "success",
        title: "Escopo Cirúrgico Registrado na Sessão!",
        message: `${response.message}${piiInfo} Vetor cirúrgico salvo na sessão e pronto para a Etapa 3 (Calibragem de Nível e Travas).`,
      });
      if (onAdvanceToStep3) {
        onAdvanceToStep3(response);
      }
    } catch (err) {
      if (err instanceof IrisApiError) {
        setFeedbackBanner({
          type: "error",
          title: "Não foi possível validar a seleção",
          message: err.message,
          code: err.code,
        });
      } else {
        setFeedbackBanner({
          type: "error",
          title: "Erro inesperado na validação",
          message: "Verifique a seleção de características funcionais e tente novamente.",
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F5EDF0] dark:bg-[#0D0221] text-[#0D0221] dark:text-[#F5EDF0] transition-colors">
      {/* Cabeçalho Institucional da Plataforma Íris */}
      <header className="w-full bg-[#0D0221] text-white border-b border-white/10 px-4 sm:px-8 py-3.5">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <IrisLogoBanner compact />
            <div className="hidden md:block h-7 w-px bg-white/15" aria-hidden="true" />
            <div className="hidden md:block">
              <p className="text-xs font-semibold text-[#E35336] uppercase tracking-wider">
                Etapa 2 de 5 • Mapeamento Funcional Cirúrgico
              </p>
              <p className="text-xs text-white/75">
                Docente: <span className="font-mono text-white">{teacherEmail}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setHighContrast((prev) => !prev)}
              aria-pressed={highContrast}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/10 hover:bg-white/20 text-white border border-white/15 transition-colors"
              title="Alternar Modo de Alto Contraste (WCAG 2.1 AA)"
            >
              <Contrast className="w-3.5 h-3.5 text-[#E35336]" aria-hidden="true" />
              <span>Alto Contraste</span>
            </button>

            <button
              type="button"
              onClick={handleToggleDarkMode}
              aria-label={isDarkMode ? "Ativar modo claro" : "Ativar modo escuro"}
              className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white border border-white/15 transition-colors"
              title={isDarkMode ? "Modo claro" : "Modo escuro"}
            >
              {isDarkMode ? <Sun className="w-4 h-4 text-[#E35336]" /> : <Moon className="w-4 h-4" />}
            </button>

            {onBackToStep1 && (
              <button
                type="button"
                onClick={onBackToStep1}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#335C67] hover:bg-[#335C67]/85 text-white transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Etapa 1</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Estrutura Principal com Sidebar Lateral + Conteúdo */}
      <div className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-6 flex flex-col lg:flex-row gap-6 items-start">
        {/* Sidebar Lateral Modular (reaproveitada entre as etapas) */}
        <IrisSidebar
          currentStep={2}
          enabledSteps={[1, 2]}
          onNavigateStep={(step) => {
            if (step === 1) {
              if (onBackToStep1) onBackToStep1();
              else router.push("/etapa-1");
            }
          }}
          step2SubSteps={{
            currentSubStep,
            onSelectSubStep: navigateToSubStep,
            selectedCharacteristicsCount: selectedCount,
          }}
        />

        {/* Conteúdo Principal */}
        <main id="conteudo-principal" className="flex-1 min-w-0 space-y-5">
          {/* Faixa compacta de contexto ético + material da Etapa 1 */}
          <div className="bg-white/85 dark:bg-[#160A30]/90 border border-[#335C67]/20 dark:border-white/15 rounded-2xl px-4 py-3 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-bold bg-[#335C67]/15 text-[#335C67] dark:bg-[#335C67]/30 dark:text-[#9fd0de]">
                <ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" />
                Sem Laudo Médico ou CID Obrigatório
              </span>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-bold bg-[#E35336]/15 text-[#E35336]">
                <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
                Pilar 1: Intervenção Cirúrgica
              </span>
              <span className="font-mono opacity-65">
                {loadedFromApi ? "• API FastAPI" : "• Catálogo Local"}
              </span>
            </div>

            {effectiveMaterialPreview && (
              <div className="flex items-center gap-2 min-w-0 max-w-xl">
                <span className="truncate text-[#0D0221]/75 dark:text-white/75">
                  <strong>Material:</strong> {effectiveMaterialPreview.slice(0, 110)}
                  {effectiveMaterialPreview.length > 110 ? "..." : ""}
                </span>
                {onBackToStep1 && (
                  <button
                    type="button"
                    onClick={onBackToStep1}
                    className="font-bold text-[#335C67] dark:text-[#9fd0de] underline flex-shrink-0"
                  >
                    Revisar Material
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Região de Feedback / Alertas Acessíveis (ARIA live) */}
          <div id={alertRegionId} aria-live="polite" aria-atomic="true">
            {feedbackBanner && (
              <div
                role={feedbackBanner.type === "error" || feedbackBanner.type === "warning" ? "alert" : "status"}
                className={`rounded-2xl p-4 border flex items-start gap-3.5 shadow-sm ${
                  feedbackBanner.type === "error"
                    ? "bg-red-50 dark:bg-red-950/50 border-red-600 text-red-950 dark:text-red-100"
                    : feedbackBanner.type === "warning"
                    ? "bg-amber-50 dark:bg-amber-950/50 border-amber-600 text-amber-950 dark:text-amber-100"
                    : feedbackBanner.type === "success"
                    ? "bg-emerald-50 dark:bg-emerald-950/50 border-emerald-600 text-emerald-950 dark:text-emerald-100"
                    : "bg-[#335C67]/10 dark:bg-[#335C67]/25 border-[#335C67] text-[#0D0221] dark:text-white"
                }`}
              >
                <div className="flex-shrink-0 mt-0.5">
                  {feedbackBanner.type === "error" || feedbackBanner.type === "warning" ? (
                    <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400" aria-hidden="true" />
                  ) : (
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-bold">{feedbackBanner.title}</p>
                    {feedbackBanner.code && (
                      <span className="px-2 py-0.5 text-[11px] font-mono rounded bg-black/10 dark:bg-white/10">
                        {feedbackBanner.code}
                      </span>
                    )}
                  </div>
                  <p className="text-xs sm:text-sm mt-1 leading-relaxed">{feedbackBanner.message}</p>
                </div>
              </div>
            )}
          </div>

          {/* ======================================================================== */}
          {/* PASSO A: PERFIL FUNCIONAL (Dimensão Funcional + Características Atômicas) */}
          {/* ======================================================================== */}
          {currentSubStep === "a" && (
            <section
              aria-label="Passo A: Perfil funcional e seleção cirúrgica de características"
              className="bg-white dark:bg-[#160A30] border border-[#335C67]/25 dark:border-white/15 rounded-2xl p-5 sm:p-6 shadow-sm space-y-5"
            >
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-[#335C67]/15 dark:border-white/10 pb-4">
                <div className="space-y-1">
                  <h1 className="text-xl sm:text-2xl font-extrabold text-[#0D0221] dark:text-white">
                    Quais barreiras funcionais você observa no estudante?
                  </h1>
                  <p className="text-xs sm:text-sm text-[#0D0221]/75 dark:text-white/75 max-w-3xl">
                    Selecione <strong>apenas</strong> as características em que há dificuldade.
                  </p>
                </div>

              <div className="flex flex-wrap items-center gap-2 flex-shrink-0">
                <button
                  type="button"
                  onClick={handleClearSelection}
                  disabled={selectedIds.length === 0}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-black/5 dark:bg-white/10 hover:bg-red-500/15 hover:text-red-700 dark:hover:text-red-300 disabled:opacity-40 disabled:pointer-events-none transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Limpar</span>
                </button>
              </div>
            </div>

            {/* Filtrar por Dimensão Funcional (Sem Rótulo Clínico) */}
            <div className="space-y-3">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs font-bold text-[#335C67] dark:text-[#9fd0de] uppercase tracking-wider">
                  <Filter className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
                  <span>Filtrar por Dimensão Funcional (Sem Rótulo Clínico)</span>
                </div>

                <div className="relative w-full md:w-72">
                  <Search
                    className="w-4 h-4 text-[#0D0221]/45 dark:text-white/50 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                    aria-hidden="true"
                  />
                  <label htmlFor={searchInputId} className="sr-only">
                    Buscar característica ou manifestação em sala de aula
                  </label>
                  <input
                    id={searchInputId}
                    type="search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Buscar ex.: múltiplos comandos..."
                    className="w-full pl-9 pr-3 py-2 rounded-xl text-xs bg-[#F5EDF0]/70 dark:bg-[#0D0221] border border-[#335C67]/25 dark:border-white/15 text-[#0D0221] dark:text-white focus:border-[#E35336]"
                  />
                </div>
              </div>

              <div className="flex flex-wrap gap-2" role="group" aria-label="Filtro por barreira funcional">
                <button
                  type="button"
                  onClick={() => setActiveBarrierFilter("all")}
                  aria-pressed={activeBarrierFilter === "all"}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                    activeBarrierFilter === "all"
                      ? "bg-[#E35336] text-white shadow-sm"
                      : "bg-[#F5EDF0] dark:bg-white/10 text-[#0D0221]/80 dark:text-white/80 hover:bg-[#335C67]/15"
                  }`}
                >
                  Todas ({totalCount})
                </button>

                {catalog.barreiras_disponiveis.map((barreira) => {
                  const count = catalog.caracteristicas.filter(
                    (c) => c.barreira_rag_associada === barreira
                  ).length;
                  if (count === 0) return null;
                  const isSelectedFilter = activeBarrierFilter === barreira;
                  return (
                    <button
                      key={barreira}
                      type="button"
                      onClick={() => setActiveBarrierFilter(barreira)}
                      aria-pressed={isSelectedFilter}
                      className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                        isSelectedFilter
                          ? "bg-[#335C67] text-white shadow-sm"
                          : "bg-[#F5EDF0] dark:bg-white/10 text-[#0D0221]/80 dark:text-white/80 hover:bg-[#335C67]/15"
                      }`}
                    >
                      {BARREIRA_LABELS[barreira] || barreira} ({count})
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Lista enxuta de características atômicas (inspirada na Imagem 1, com expansão sob demanda) */}
            {isLoadingCatalog ? (
              <div className="rounded-2xl p-10 flex flex-col items-center justify-center gap-3 border border-[#335C67]/20">
                <Loader2 className="w-7 h-7 animate-spin text-[#E35336]" aria-hidden="true" />
                <p className="text-sm font-semibold">
                  Carregando catálogo oficial de características funcionais...
                </p>
              </div>
            ) : filteredCharacteristics.length === 0 ? (
              <div className="rounded-2xl p-8 text-center space-y-2 border border-[#335C67]/20">
                <p className="text-sm font-bold">Nenhuma característica encontrada para o filtro atual.</p>
                <button
                  type="button"
                  onClick={() => {
                    setActiveBarrierFilter("all");
                    setSearchQuery("");
                  }}
                  className="text-xs font-bold text-[#E35336] underline"
                >
                  Mostrar todas as {totalCount} características
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {filteredCharacteristics.map((item: CharacteristicItem) => {
                  const isSelected = selectedSet.has(item.id_caracteristica);
                  const isExpanded = Boolean(expandedDetails[item.id_caracteristica]);
                  const refDoc = item.referencias_bibliograficas?.[0];

                  return (
                    <div
                      key={item.id_caracteristica}
                      role="checkbox"
                      aria-checked={isSelected}
                      tabIndex={0}
                      onClick={() => handleToggleCharacteristic(item.id_caracteristica)}
                      onKeyDown={(e) => {
                        if (e.key === " " || e.key === "Enter") {
                          e.preventDefault();
                          handleToggleCharacteristic(item.id_caracteristica);
                        }
                      }}
                      className={`group cursor-pointer rounded-2xl p-4 border-2 transition-all flex flex-col justify-between gap-3 text-left select-none focus:outline-none focus:ring-2 focus:ring-[#E35336] ${
                        isSelected
                          ? "bg-[#E35336]/[0.04] dark:bg-[#1E0E40] border-[#E35336] shadow-sm"
                          : "bg-[#F5EDF0]/40 dark:bg-[#160A30]/80 border-[#335C67]/20 dark:border-white/10 hover:border-[#335C67]/50"
                      }`}
                    >
                      <div className="space-y-2.5">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-start gap-3">
                            <div
                              className={`mt-0.5 flex-shrink-0 w-6 h-6 rounded-lg flex items-center justify-center transition-colors ${
                                isSelected
                                  ? "bg-[#E35336] text-white"
                                  : "bg-white dark:bg-white/10 border border-[#335C67]/25 text-[#335C67] dark:text-white/60"
                              }`}
                            >
                              {isSelected ? (
                                <CheckSquare className="w-4 h-4" aria-hidden="true" />
                              ) : (
                                <Square className="w-4 h-4" aria-hidden="true" />
                              )}
                            </div>
                            <div className="space-y-1">
                              <h2 className="text-sm font-extrabold text-[#0D0221] dark:text-white leading-snug">
                                {item.nome}
                              </h2>
                              <p className="text-xs text-[#0D0221]/75 dark:text-white/75 leading-relaxed">
                                {item.descricao_observavel}
                              </p>
                            </div>
                          </div>

                          {isSelected ? (
                            <span className="flex-shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-[#E35336]/15 text-[#E35336] border border-[#E35336]/30">
                              <Unlock className="w-3 h-3" aria-hidden="true" />
                              Adaptar
                            </span>
                          ) : (
                            <span className="flex-shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-black/5 dark:bg-white/10 text-[#0D0221]/65 dark:text-white/65">
                              <Lock className="w-3 h-3" aria-hidden="true" />
                              Original
                            </span>
                          )}
                        </div>

                        {isExpanded && (
                          <div className="rounded-xl bg-white dark:bg-black/30 p-3 border border-[#335C67]/15 dark:border-white/10 space-y-2">
                            <p className="text-[11px] font-bold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de]">
                              Como se manifesta na prática em sala:
                            </p>
                            <ul className="space-y-1 text-xs text-[#0D0221]/80 dark:text-white/75 list-disc list-inside">
                              {item.exemplos_manifestacao_sala.map((exemplo, idx) => (
                                <li key={idx} className="leading-snug">
                                  {exemplo}
                                </li>
                              ))}
                            </ul>
                            <div className="pt-1 flex flex-wrap items-center gap-2 text-[11px]">
                              <span className="px-2 py-0.5 rounded bg-[#0D0221]/5 dark:bg-white/10 font-semibold">
                                {PRINCIPIO_DUA_LABELS[item.principio_dua_primario] ||
                                  item.principio_dua_primario}
                              </span>
                              {refDoc?.ponto_verificacao_dua && (
                                <span className="inline-flex items-center gap-1 opacity-75">
                                  <BookOpen className="w-3 h-3" aria-hidden="true" />
                                  {refDoc.ponto_verificacao_dua}
                                </span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="pt-2 border-t border-[#335C67]/10 dark:border-white/10 flex items-center justify-between gap-2">
                        <span className="px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-[#335C67]/15 text-[#335C67] dark:bg-[#335C67]/30 dark:text-[#9fd0de]">
                          {BARREIRA_LABELS[item.barreira_rag_associada] || item.barreira_rag_associada}
                        </span>

                        <button
                          type="button"
                          onClick={(e) => handleToggleDetails(item.id_caracteristica, e)}
                          className="inline-flex items-center gap-1 text-xs font-bold text-[#335C67] dark:text-[#9fd0de] hover:underline"
                        >
                          {isExpanded ? (
                            <>
                              <ChevronUp className="w-3.5 h-3.5" aria-hidden="true" />
                              <span>Ocultar exemplos</span>
                            </>
                          ) : (
                            <>
                              <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />
                              <span>Ver exemplos</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Rodapé do Passo (a) */}
            <div className="pt-4 border-t border-[#335C67]/15 dark:border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                {selectedCount === 0 ? (
                  <div
                    role="alert"
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-950 dark:text-amber-200 text-xs font-bold"
                  >
                    <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" aria-hidden="true" />
                    <span>
                      {attemptedEmptySubmit
                        ? "Avanço bloqueado: selecione ao menos 1 característica acima."
                        : "Selecione ao menos 1 característica observada para continuar."}
                    </span>
                  </div>
                ) : (
                  <p className="inline-flex items-center gap-2 text-xs text-[#0D0221]/75 dark:text-white/75">
                    <Info className="w-4 h-4 text-[#335C67] dark:text-[#9fd0de]" aria-hidden="true" />
                    <span>
                      <strong>{selectedCount}</strong> marcada(s) para adaptação • Você poderá revisar tudo no resumo final.
                    </span>
                  </p>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2.5">
                {selectedCount > 0 && (
                  <button
                    type="button"
                    onClick={() => navigateToSubStep("c")}
                    className="px-4 py-2.5 rounded-xl text-xs font-bold bg-[#F5EDF0] dark:bg-white/10 hover:bg-[#335C67]/20 text-[#0D0221] dark:text-white transition-colors"
                  >
                    Ir direto para Resumo
                  </button>
                )}
                <button
                  type="button"
                  disabled={selectedCount === 0}
                  onClick={() => navigateToSubStep("b")}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs sm:text-sm font-bold text-white bg-[#E35336] hover:bg-[#c94429] disabled:opacity-45 disabled:cursor-not-allowed shadow-sm transition-all"
                >
                  <span>Continuar</span>
                  <ArrowRight className="w-4 h-4" aria-hidden="true" />
                </button>
              </div>
            </div>
          </section>
        )}

        {/* ======================================================================== */}
        {/* PASSO B: INTERESSES TEMÁTICOS, CANAIS E POTENCIALIDADES (Opcional — DUA) */}
        {/* ======================================================================== */}
        {currentSubStep === "b" && (
          <section
            aria-label="Passo B: Potencialidades, interesses temáticos e canais de engajamento (Opcional)"
            className="bg-white dark:bg-[#160A30] border border-[#335C67]/25 dark:border-white/15 rounded-2xl p-5 sm:p-6 shadow-sm space-y-6"
          >
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 border-b border-[#335C67]/15 dark:border-white/10 pb-4">
              <div className="space-y-1.5">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-[#335C67]/15 text-[#335C67] dark:bg-[#335C67]/30 dark:text-[#9fd0de]">
                  <HeartHandshake className="w-3.5 h-3.5" aria-hidden="true" />
                  Princípio I do DUA — Rede de Engajamento • Opcional
                </span>
                <h1 className="text-xl sm:text-2xl font-extrabold text-[#0D0221] dark:text-white">
                  Potencialidades, Interesses e Canais de Engajamento
                </h1>
                <p className="text-xs sm:text-sm text-[#0D0221]/75 dark:text-white/75 max-w-3xl">
                  Escolha temas, canais preferenciais e facilidades do estudante para usar como{" "}
                  <strong>âncoras motivacionais periféricas</strong>, sem substituir os conceitos obrigatórios da avaliação.
                </p>
              </div>

              {engagementAnchorCount > 0 && (
                <button
                  type="button"
                  onClick={handleClearEngagement}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-black/5 dark:bg-white/10 hover:bg-red-500/15 hover:text-red-700 dark:hover:text-red-300 transition-colors self-start flex-shrink-0"
                >
                  <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Limpar Engajamento</span>
                </button>
              )}
            </div>

            {/* 1. Interesses Temáticos */}
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de]">
                <Compass className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
                <span>1. Interesses Temáticos (Opcional)</span>
              </div>

              <div
                className="flex flex-wrap gap-2"
                role="group"
                aria-label="Seletores de interesses temáticos"
              >
                {engagementOptions.interesses_tematicos.map((interest) => {
                  const isActive = selectedInterests.includes(interest.id);
                  return (
                    <button
                      key={interest.id}
                      type="button"
                      aria-pressed={isActive}
                      title={interest.descricao}
                      onClick={() => handleToggleInterest(interest.id)}
                      className={`px-3.5 py-2 rounded-full text-xs sm:text-sm font-bold border transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] ${
                        isActive
                          ? "bg-[#E35336] text-white border-[#E35336] shadow-sm"
                          : "bg-[#F5EDF0]/70 dark:bg-white/5 text-[#0D0221] dark:text-white border-[#335C67]/25 dark:border-white/15 hover:border-[#E35336]/60"
                      }`}
                    >
                      {isActive ? "✓ " : ""}
                      {interest.rotulo}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 2. Canais Preferenciais de Engajamento */}
            <div className="pt-5 border-t border-[#335C67]/15 dark:border-white/10 space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de]">
                <Layers className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
                <span>2. Canais Preferenciais de Engajamento (Opcional)</span>
              </div>

              <div
                className="flex flex-wrap gap-2"
                role="group"
                aria-label="Canais preferenciais de engajamento"
              >
                {engagementOptions.canais_engajamento_preferenciais.map((canal) => {
                  const isActive = selectedChannels.includes(canal.id);
                  return (
                    <button
                      key={canal.id}
                      type="button"
                      aria-pressed={isActive}
                      title={canal.descricao}
                      onClick={() => handleToggleChannel(canal.id)}
                      className={`px-3.5 py-2 rounded-xl text-xs sm:text-sm font-bold border transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] ${
                        isActive
                          ? "bg-[#335C67] text-white border-[#335C67] shadow-sm"
                          : "bg-[#F5EDF0]/70 dark:bg-white/5 text-[#0D0221] dark:text-white border-[#335C67]/25 dark:border-white/15 hover:border-[#335C67]/60"
                      }`}
                    >
                      {isActive ? "✓ " : ""}
                      {canal.rotulo}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 3. Potencialidades e Facilidades Observadas */}
            <div className="pt-5 border-t border-[#335C67]/15 dark:border-white/10 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <label
                  htmlFor={potencialidadesInputId}
                  className="text-xs font-bold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de]"
                >
                  3. Potencialidades e Facilidades Observadas (Opcional)
                </label>
                <span className="text-[11px] font-mono opacity-70">{potencialidades.length}/500</span>
              </div>
              <textarea
                id={potencialidadesInputId}
                rows={2}
                maxLength={500}
                value={potencialidades}
                onChange={(e) => {
                  setConfirmedSelection(null);
                  setPotencialidades(e.target.value);
                }}
                placeholder="Ex.: Boa compreensão com esquemas visuais, facilidade para explicar raciocínios oralmente e engajamento com desafios curtos."
                className="w-full p-3 rounded-xl text-xs sm:text-sm bg-[#F5EDF0]/70 dark:bg-[#0D0221] border border-[#335C67]/25 dark:border-white/15 text-[#0D0221] dark:text-white focus:border-[#E35336] transition-colors"
              />
              <p className="text-[11px] text-[#0D0221]/70 dark:text-white/70">
                <strong>Proteção LGPD:</strong> não insira nome do estudante, dados civis, CID ou laudo clínico. Qualquer dado identificável acidental será descartado antes do processamento.
              </p>
            </div>

            {/* Rodapé do Passo (B) */}
            <div className="pt-4 border-t border-[#335C67]/15 dark:border-white/10 flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => navigateToSubStep("a")}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold bg-[#F5EDF0] dark:bg-white/10 hover:bg-[#335C67]/20 text-[#0D0221] dark:text-white transition-colors"
              >
                <ArrowLeft className="w-4 h-4" aria-hidden="true" />
                <span>Voltar</span>
              </button>

              <button
                type="button"
                onClick={() => navigateToSubStep("c")}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs sm:text-sm font-bold text-white bg-[#E35336] hover:bg-[#c94429] shadow-sm transition-all"
              >
                <span>Continuar para Resumo</span>
                <ArrowRight className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>
          </section>
        )}

        {/* ======================================================================== */}
        {/* PASSO C: RESUMO DA ADAPTAÇÃO E AVANÇO PARA ETAPA 3                       */}
        {/* ======================================================================== */}
        {currentSubStep === "c" && (
          <section
            aria-label="Passo C: Resumo do escopo cirúrgico e avanço para Etapa 3"
            className="bg-white dark:bg-[#160A30] border-2 border-[#335C67]/30 dark:border-white/15 rounded-2xl p-5 sm:p-6 shadow-md space-y-5"
          >
            <div className="border-b border-[#335C67]/15 dark:border-white/10 pb-4">
              <h1 className="text-xl sm:text-2xl font-extrabold text-[#0D0221] dark:text-white">
                Resumo do perfil funcional
              </h1>
              <p className="text-xs sm:text-sm text-[#0D0221]/75 dark:text-white/75 mt-1">
                Confira as informações antes de seguir para a calibragem de nível e travas curriculares (Etapa 3).
              </p>
            </div>

            {/* 3 Cards de Resumo */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Card 1: Adaptar */}
              <div className="rounded-2xl p-4 bg-[#E35336]/10 dark:bg-[#E35336]/20 border border-[#E35336]/35 space-y-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-[#E35336]" aria-hidden="true" />
                    <span className="text-xs font-extrabold uppercase tracking-wider text-[#E35336]">
                      Adaptar
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigateToSubStep("a")}
                    className="text-xs font-bold text-[#E35336] hover:underline"
                  >
                    Editar
                  </button>
                </div>
                <p className="text-lg font-extrabold text-[#0D0221] dark:text-white">
                  {selectedCount} {selectedCount === 1 ? "característica" : "características"}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {selectedIds.map((id) => {
                    const item = catalog.caracteristicas.find((c) => c.id_caracteristica === id);
                    return (
                      <span
                        key={id}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-white dark:bg-[#0D0221] border border-[#E35336]/30"
                      >
                        <span className="truncate max-w-[180px]">{item?.nome || id}</span>
                        <button
                          type="button"
                          onClick={() => handleToggleCharacteristic(id)}
                          aria-label={`Remover característica ${item?.nome || id}`}
                          className="font-bold text-[#E35336] hover:underline"
                        >
                          ×
                        </button>
                      </span>
                    );
                  })}
                </div>
              </div>

              {/* Card 2: Manter */}
              <div className="rounded-2xl p-4 bg-[#335C67]/10 dark:bg-white/5 border border-[#335C67]/25 dark:border-white/15 space-y-2">
                <div className="flex items-center gap-2">
                  <Lock className="w-5 h-5 text-[#335C67] dark:text-[#9fd0de]" aria-hidden="true" />
                  <span className="text-xs font-extrabold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de]">
                    Manter
                  </span>
                </div>
                <p className="text-lg font-extrabold text-[#0D0221] dark:text-white">
                  {blockedCount} {blockedCount === 1 ? "característica" : "características"}
                </p>
                <p className="text-xs text-[#0D0221]/75 dark:text-white/75 leading-relaxed">
                  Demais habilidades preservadas com <strong>100% do formato original</strong>.
                </p>
              </div>

              {/* Card 3: Engajamento (Princípio I DUA) */}
              <div className="rounded-2xl p-4 bg-[#F5EDF0] dark:bg-white/5 border border-[#335C67]/25 dark:border-white/15 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-[#E35336]" aria-hidden="true" />
                    <span className="text-xs font-extrabold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de]">
                      Engajamento
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigateToSubStep("b")}
                    className="text-xs font-bold text-[#335C67] dark:text-[#9fd0de] hover:underline"
                  >
                    Editar
                  </button>
                </div>
                <p className="text-lg font-extrabold text-[#0D0221] dark:text-white">
                  {engagementAnchorCount === 0
                    ? "Opcional (em branco)"
                    : `${engagementAnchorCount} registro(s)`}
                </p>
                <p className="text-xs text-[#0D0221]/75 dark:text-white/75 leading-relaxed">
                  {engagementAnchorCount === 0
                    ? "Nenhuma âncora informada. O avanço segue normalmente."
                    : `${totalInterestsCount} interesse(s), ${selectedChannels.length} canal(is)${
                        potencialidades.trim() ? " + potencialidades descritas" : ""
                      }.`}
                </p>
              </div>
            </div>

            {/* Banner Informativo de Garantia Curricular */}
            <div className="rounded-xl p-3.5 bg-[#335C67]/10 dark:bg-[#335C67]/25 border border-[#335C67]/30 flex items-center gap-3 text-xs text-[#0D0221] dark:text-white">
              <Info className="w-4 h-4 text-[#335C67] dark:text-[#9fd0de] flex-shrink-0" aria-hidden="true" />
              <span>
                O conteúdo será adaptado apenas para as características selecionadas, preservando o restante da atividade. Os interesses do Princípio I do DUA não substituem a Trava Curricular.
              </span>
            </div>

            {/* Alerta caso o usuário remova a última característica aqui no resumo */}
            {selectedCount === 0 && (
              <div
                role="alert"
                className="rounded-xl p-3 bg-amber-500/15 border border-amber-500/40 text-amber-950 dark:text-amber-200 flex items-center gap-2.5 text-xs font-bold"
              >
                <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" aria-hidden="true" />
                <span>
                  Avanço bloqueado: volte ao passo A e selecione ao menos 1 característica.
                </span>
              </div>
            )}

            {/* Rodapé do Passo (C) */}
            <div className="pt-3 border-t border-[#335C67]/15 dark:border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => navigateToSubStep("b")}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold bg-[#F5EDF0] dark:bg-white/10 hover:bg-[#335C67]/20 text-[#0D0221] dark:text-white transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" aria-hidden="true" />
                  <span>Voltar</span>
                </button>
                {onBackToStep1 && (
                  <button
                    type="button"
                    onClick={onBackToStep1}
                    className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold bg-[#F5EDF0] dark:bg-white/10 hover:bg-[#335C67]/20 text-[#0D0221] dark:text-white transition-colors"
                  >
                    <span>Etapa 1 (Material)</span>
                  </button>
                )}
              </div>

              <button
                type="button"
                disabled={selectedCount === 0 || isSubmitting}
                onClick={handleConfirmAndAdvance}
                className="inline-flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl font-bold text-sm text-white bg-[#E35336] hover:bg-[#c94429] disabled:opacity-45 disabled:cursor-not-allowed shadow-[0_8px_20px_-4px_rgba(227,83,54,0.45)] transition-all"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                    Validando Escopo Cirúrgico...
                  </>
                ) : confirmedSelection ? (
                  <>
                    <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                    Escopo Confirmado! Avançar para Etapa 3
                    <ArrowRight className="w-4 h-4" aria-hidden="true" />
                  </>
                ) : (
                  <>
                    Confirmar e Ir para Etapa 3
                    <ArrowRight className="w-4 h-4" aria-hidden="true" />
                  </>
                )}
              </button>
            </div>
          </section>
        )}
        </main>
      </div>
    </div>
  );
}
