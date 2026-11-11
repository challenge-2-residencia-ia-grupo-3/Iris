"use client";

import React, { useCallback, useEffect, useId, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  CheckSquare,
  Contrast,
  Filter,
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
import { Stepper5Etapas } from "./Stepper5Etapas";
import {
  BARREIRA_LABELS,
  CharacteristicItem,
  CharacteristicsCatalogResponse,
  FALLBACK_OFFICIAL_CATALOG,
  PRINCIPIO_DUA_LABELS,
  SurgicalSelectionResponse,
  fetchCharacteristicsCatalog,
  loadStep1StateFromSession,
  loadSurgicalSelectionFromSession,
  submitSurgicalCharacteristicSelection,
} from "@/services/catalogsApi";
import { IrisApiError } from "@/services/materialsApi";

interface Step2FunctionalProfileProps {
  teacherEmail?: string;
  materialPreviewText?: string;
  onBackToStep1?: () => void;
  onAdvanceToStep3?: (selection: SurgicalSelectionResponse) => void;
  darkMode: boolean;
  onToggleDarkMode: () => void;
}

/**
 * Componente da Etapa 2 (Issue 1.2.1 — Seleção Cirúrgica de Características Funcionais Atômicas Observadas).
 *
 * Atende estritamente:
 * - RF-04: Seleção atômica de características observáveis em sala de aula, sem exigir laudo médico ou CID.
 * - Isolamento de Escopo (Pilar 1): registra exclusivamente as opções marcadas como escopo permitido
 *   (`selected_ids`) e mantém todas as demais bloqueadas para intervenção (`blocked_ids`).
 * - Bloqueio de avanço com alerta acessível (WCAG 2.1 AA) caso nenhuma característica seja selecionada.
 * - Persistência do vetor cirúrgico no estado da sessão do cliente (`sessionStorage`).
 */
export function Step2FunctionalProfile({
  teacherEmail = "marina.alves@escola.edu.br",
  materialPreviewText,
  onBackToStep1,
  onAdvanceToStep3,
  darkMode,
  onToggleDarkMode,
}: Step2FunctionalProfileProps) {
  const searchInputId = useId();
  const alertRegionId = useId();

  const [highContrast, setHighContrast] = useState(false);
  const [catalog, setCatalog] = useState<CharacteristicsCatalogResponse>(FALLBACK_OFFICIAL_CATALOG);
  const [isLoadingCatalog, setIsLoadingCatalog] = useState<boolean>(true);
  const [loadedFromApi, setLoadedFromApi] = useState<boolean>(false);
  const [sessionMaterialPreview, setSessionMaterialPreview] = useState<string>("");

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [activeBarrierFilter, setActiveBarrierFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

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

  // Carrega o catálogo oficial via GET /api/v1/catalogs/characteristics e restaura seleção da sessão
  useEffect(() => {
    const savedStep1 = loadStep1StateFromSession();
    if (savedStep1?.textContent) {
      setSessionMaterialPreview(savedStep1.textContent);
    }

    let active = true;
    async function initStep2() {
      setIsLoadingCatalog(true);
      const { catalog: fetchedCatalog, fromServer } = await fetchCharacteristicsCatalog();
      if (!active) return;
      setCatalog(fetchedCatalog);
      setLoadedFromApi(fromServer);
      setIsLoadingCatalog(false);

      const saved = loadSurgicalSelectionFromSession();
      if (saved && Array.isArray(saved.selected_ids) && saved.selected_ids.length > 0) {
        const validSet = new Set(fetchedCatalog.caracteristicas.map((c) => c.id_caracteristica));
        const restored = saved.selected_ids.filter((id) => validSet.has(id));
        if (restored.length > 0) {
          setSelectedIds(restored);
          setConfirmedSelection(saved);
        }
      }
    }
    initStep2();
    return () => {
      active = false;
    };
  }, []);

  const effectiveMaterialPreview = materialPreviewText || sessionMaterialPreview;

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const totalCount = catalog.caracteristicas.length;
  const selectedCount = selectedIds.length;
  const blockedCount = totalCount - selectedCount;

  // Características filtradas por barreira e busca textual
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
        ...(BARREIRA_LABELS[item.barreira_rag_associada] ? [BARREIRA_LABELS[item.barreira_rag_associada]] : []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [catalog.caracteristicas, activeBarrierFilter, searchQuery]);

  // Alterna uma característica atômica individualmente
  const handleToggleCharacteristic = useCallback((idCaracteristica: string) => {
    setConfirmedSelection(null);
    setFeedbackBanner(null);
    setSelectedIds((prev) => {
      if (prev.includes(idCaracteristica)) {
        return prev.filter((id) => id !== idCaracteristica);
      }
      setAttemptedEmptySubmit(false);
      return [...prev, idCaracteristica];
    });
  }, []);

  // Exemplo cirúrgico rápido: seleciona apenas 1 característica (comandos múltiplos)
  const handleSelectSingleExample = () => {
    const targetId = "sobrecarga_memoria_trabalho_comandos_multiplos";
    setSelectedIds([targetId]);
    setAttemptedEmptySubmit(false);
    setConfirmedSelection(null);
    setFeedbackBanner({
      type: "info",
      title: "Exemplo de Intervenção Cirúrgica (1 de 10 selecionada)",
      message:
        "Apenas 'Sobrecarga de memória de trabalho em comandos múltiplos conjugados' foi marcada. As outras 9 características permanecem bloqueadas para preservar 100% da autonomia original do estudante.",
    });
  };

  const handleClearSelection = () => {
    setSelectedIds([]);
    setConfirmedSelection(null);
    setAttemptedEmptySubmit(true);
    setFeedbackBanner({
      type: "warning",
      title: "Nenhuma característica funcional selecionada",
      message:
        "O avanço para a Etapa 3 está bloqueado. Selecione pelo menos 1 característica observada em sala de aula.",
      code: "EMPTY_CHARACTERISTIC_SELECTION",
    });
  };

  // Submete o vetor cirúrgico para POST /api/v1/catalogs/characteristics/select
  const handleConfirmAndAdvance = async () => {
    if (selectedIds.length === 0) {
      setAttemptedEmptySubmit(true);
      setFeedbackBanner({
        type: "error",
        title: "Seleção obrigatória para avançar",
        message:
          "Selecione pelo menos uma característica funcional observada em sala de aula antes de prosseguir para a Etapa 3.",
        code: "EMPTY_CHARACTERISTIC_SELECTION",
      });
      return;
    }

    // Se já foi confirmado e o usuário clicou novamente para ir à Etapa 3
    if (confirmedSelection && onAdvanceToStep3) {
      onAdvanceToStep3(confirmedSelection);
      return;
    }

    setIsSubmitting(true);
    setFeedbackBanner(null);

    try {
      const response = await submitSurgicalCharacteristicSelection(selectedIds, catalog);
      setConfirmedSelection(response);
      setFeedbackBanner({
        type: "success",
        title: "Escopo Cirúrgico Registrado na Sessão!",
        message: `${response.message} Vetor cirúrgico salvo na sessão e pronto para a Etapa 3 (Calibragem de Nível e Travas).`,
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

          {/* Controles de Acessibilidade (WCAG 2.1 AA) e Retorno para Etapa 1 */}
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
              onClick={onToggleDarkMode}
              aria-label={darkMode ? "Ativar modo claro" : "Ativar modo escuro"}
              className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white border border-white/15 transition-colors"
              title={darkMode ? "Modo claro" : "Modo escuro"}
            >
              {darkMode ? <Sun className="w-4 h-4 text-[#E35336]" /> : <Moon className="w-4 h-4" />}
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

      {/* Conteúdo Principal */}
      <main id="conteudo-principal" className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-6 space-y-6">
        {/* Stepper Linear de 5 Etapas (Etapa 2 Ativa) */}
        <Stepper5Etapas currentStep={2} />

        {/* Banner Ético Sem Laudo Médico + Pilar 1 (Intervenção Cirúrgica) */}
        <section
          aria-label="Diretriz pedagógica sem exigência de laudo médico"
          className="bg-white dark:bg-[#160A30] border border-[#335C67]/25 dark:border-white/15 rounded-2xl p-5 shadow-sm"
        >
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-[#335C67]/15 text-[#335C67] dark:bg-[#335C67]/30 dark:text-[#9fd0de]">
                  <ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" />
                  Sem Laudo Médico ou CID Obrigatório
                </span>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-[#E35336]/15 text-[#E35336]">
                  <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
                  Pilar 1: Intervenção Cirúrgica por Característica
                </span>
                <span className="text-[11px] font-mono opacity-70">
                  {loadedFromApi ? "• Conectado à API FastAPI" : "• Catálogo Oficial Local"}
                </span>
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold text-[#0D0221] dark:text-white">
                Quais barreiras funcionais você observa no estudante em sala de aula?
              </h1>
              <p className="text-xs sm:text-sm text-[#0D0221]/75 dark:text-white/75 max-w-4xl leading-relaxed">
                Selecione <strong>apenas</strong> as características em que o aluno realmente demonstra dificuldade.
                A IA atuará estritamente nos itens marcados e manterá{" "}
                <strong>bloqueadas para intervenção todas as demais características</strong>, preservando 100% da autonomia
                do estudante onde ele não precisa de ajuda.
              </p>
            </div>

            {/* Ações rápidas de demonstração */}
            <div className="flex flex-wrap items-center gap-2 flex-shrink-0">
              <button
                type="button"
                onClick={handleSelectSingleExample}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-[#335C67] hover:bg-[#274851] text-white transition-colors shadow-sm"
              >
                <Sparkles className="w-3.5 h-3.5 text-[#E35336]" aria-hidden="true" />
                <span>Testar Exemplo (1 de {totalCount})</span>
              </button>

              <button
                type="button"
                onClick={handleClearSelection}
                disabled={selectedIds.length === 0}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-black/5 dark:bg-white/10 hover:bg-red-500/15 hover:text-red-700 dark:hover:text-red-300 disabled:opacity-40 disabled:pointer-events-none transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Limpar Seleção</span>
              </button>
            </div>
          </div>

          {effectiveMaterialPreview && (
            <div className="mt-4 pt-3 border-t border-[#335C67]/15 dark:border-white/10 flex items-center justify-between gap-2 text-xs text-[#0D0221]/70 dark:text-white/70">
              <span className="truncate">
                <strong>Material da Etapa 1 em memória:</strong> {effectiveMaterialPreview.slice(0, 140)}
                {effectiveMaterialPreview.length > 140 ? "..." : ""}
              </span>
              {onBackToStep1 && (
                <button
                  type="button"
                  onClick={onBackToStep1}
                  className="text-xs font-bold text-[#335C67] dark:text-[#9fd0de] underline flex-shrink-0"
                >
                  Revisar Material
                </button>
              )}
            </div>
          )}
        </section>

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

        {/* Barra de Filtros Atômicos (Por Função Executiva e Busca) */}
        <section
          aria-label="Filtros de características funcionais"
          className="bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 rounded-2xl p-4 shadow-sm space-y-3.5"
        >
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs font-bold text-[#335C67] dark:text-[#9fd0de] uppercase tracking-wider">
              <Filter className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
              <span>Filtrar por Dimensão Funcional (Sem Rótulo Clínico)</span>
            </div>

            {/* Busca rápida */}
            <div className="relative w-full md:w-80">
              <Search
                className="w-4 h-4 text-[#0D0221]/45 dark:text-white/50 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none"
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
                placeholder="Buscar ex.: múltiplos comandos, texto longo..."
                className="w-full pl-9 pr-3 py-2 rounded-xl text-xs bg-[#F5EDF0]/70 dark:bg-[#0D0221] border border-[#335C67]/25 dark:border-white/15 text-[#0D0221] dark:text-white focus:border-[#E35336] transition-colors"
              />
            </div>
          </div>

          {/* Pílulas de filtro por barreira */}
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
              const count = catalog.caracteristicas.filter((c) => c.barreira_rag_associada === barreira).length;
              if (count === 0) return null;
              const isSelected = activeBarrierFilter === barreira;
              return (
                <button
                  key={barreira}
                  type="button"
                  onClick={() => setActiveBarrierFilter(barreira)}
                  aria-pressed={isSelected}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                    isSelected
                      ? "bg-[#335C67] text-white shadow-sm"
                      : "bg-[#F5EDF0] dark:bg-white/10 text-[#0D0221]/80 dark:text-white/80 hover:bg-[#335C67]/15"
                  }`}
                >
                  {BARREIRA_LABELS[barreira] || barreira} ({count})
                </button>
              );
            })}
          </div>
        </section>

        {/* Grade de Cartões Selecionáveis das Características Atômicas */}
        <section aria-label="Catálogo de características funcionais observáveis">
          {isLoadingCatalog ? (
            <div className="bg-white dark:bg-[#160A30] rounded-2xl p-12 flex flex-col items-center justify-center gap-3 border border-[#335C67]/20">
              <Loader2 className="w-7 h-7 animate-spin text-[#E35336]" aria-hidden="true" />
              <p className="text-sm font-semibold">Carregando catálogo oficial de características funcionais...</p>
            </div>
          ) : filteredCharacteristics.length === 0 ? (
            <div className="bg-white dark:bg-[#160A30] rounded-2xl p-8 text-center space-y-2 border border-[#335C67]/20">
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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {filteredCharacteristics.map((item: CharacteristicItem) => {
                const isSelected = selectedSet.has(item.id_caracteristica);
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
                    className={`group cursor-pointer rounded-2xl p-5 border-2 transition-all flex flex-col justify-between gap-4 text-left select-none focus:outline-none focus:ring-2 focus:ring-[#E35336] ${
                      isSelected
                        ? "bg-white dark:bg-[#1E0E40] border-[#E35336] shadow-[0_8px_24px_-8px_rgba(227,83,54,0.35)]"
                        : "bg-white/85 dark:bg-[#160A30]/80 border-[#335C67]/20 dark:border-white/10 hover:border-[#335C67]/50"
                    }`}
                  >
                    <div className="space-y-3">
                      {/* Topo do Card: Checkbox + Selo de Status (Escopo Ativo vs. Bloqueado) */}
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-3">
                          <div
                            className={`mt-0.5 flex-shrink-0 w-6 h-6 rounded-lg flex items-center justify-center transition-colors ${
                              isSelected
                                ? "bg-[#E35336] text-white"
                                : "bg-[#F5EDF0] dark:bg-white/10 text-[#335C67] dark:text-white/60 group-hover:bg-[#335C67]/20"
                            }`}
                          >
                            {isSelected ? (
                              <CheckSquare className="w-4 h-4" aria-hidden="true" />
                            ) : (
                              <Square className="w-4 h-4" aria-hidden="true" />
                            )}
                          </div>
                          <div>
                            <h2 className="text-sm sm:text-base font-extrabold text-[#0D0221] dark:text-white leading-snug">
                              {item.nome}
                            </h2>
                          </div>
                        </div>

                        {/* Selo visual do Isolamento de Escopo */}
                        {isSelected ? (
                          <span className="flex-shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-[#E35336]/15 text-[#E35336] border border-[#E35336]/30">
                            <Unlock className="w-3 h-3" aria-hidden="true" />
                            Vai ser adaptado
                          </span>
                        ) : (
                          <span className="flex-shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-black/5 dark:bg-white/10 text-[#0D0221]/65 dark:text-white/65">
                            <Lock className="w-3 h-3" aria-hidden="true" />
                            Bloqueada (100% original)
                          </span>
                        )}
                      </div>

                      {/* Descrição Observável em Sala de Aula */}
                      <p className="text-xs sm:text-sm text-[#0D0221]/80 dark:text-white/80 leading-relaxed">
                        {item.descricao_observavel}
                      </p>

                      {/* Exemplos Práticos do Dia a Dia em Sala */}
                      <div className="rounded-xl bg-[#F5EDF0]/70 dark:bg-black/25 p-3 border border-[#335C67]/15 dark:border-white/10 space-y-1.5">
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
                      </div>
                    </div>

                    {/* Rodapé do Card: Barreira Funcional + DUA + Evidência */}
                    <div className="pt-2 border-t border-[#335C67]/10 dark:border-white/10 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-[#335C67]/15 text-[#335C67] dark:bg-[#335C67]/30 dark:text-[#9fd0de]">
                          {BARREIRA_LABELS[item.barreira_rag_associada] || item.barreira_rag_associada}
                        </span>
                        <span className="px-2.5 py-0.5 rounded-md text-[11px] font-semibold bg-[#0D0221]/5 dark:bg-white/10 text-[#0D0221]/75 dark:text-white/75">
                          {PRINCIPIO_DUA_LABELS[item.principio_dua_primario] || item.principio_dua_primario}
                        </span>
                      </div>

                      {refDoc?.ponto_verificacao_dua && (
                        <span className="inline-flex items-center gap-1 text-[11px] text-[#0D0221]/60 dark:text-white/60">
                          <BookOpen className="w-3 h-3" aria-hidden="true" />
                          {refDoc.ponto_verificacao_dua}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Painel Resumo do Isolamento de Escopo Cirúrgico + Rodapé de Navegação */}
        <section
          aria-label="Resumo do escopo cirúrgico e avanço para Etapa 3"
          className="bg-white dark:bg-[#160A30] border-2 border-[#335C67]/30 dark:border-white/15 rounded-2xl p-5 shadow-md space-y-4"
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
            {/* Contador de Características Ativadas */}
            <div className="rounded-xl p-3.5 bg-[#E35336]/10 dark:bg-[#E35336]/20 border border-[#E35336]/30 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#E35336] text-white font-extrabold text-base flex items-center justify-center flex-shrink-0">
                {selectedCount}
              </div>
              <div>
                <p className="text-xs font-extrabold uppercase tracking-wider text-[#E35336]">
                  Escopo Permitido (Ativadas)
                </p>
                <p className="text-xs text-[#0D0221]/80 dark:text-white/80">
                  {selectedCount === 0
                    ? "Nenhuma característica marcada ainda"
                    : `${selectedCount} de ${totalCount} receberão andaime cognitivo`}
                </p>
              </div>
            </div>

            {/* Contador de Características Bloqueadas */}
            <div className="rounded-xl p-3.5 bg-[#335C67]/10 dark:bg-white/5 border border-[#335C67]/25 dark:border-white/10 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#335C67] text-white font-extrabold text-base flex items-center justify-center flex-shrink-0">
                {blockedCount}
              </div>
              <div>
                <p className="text-xs font-extrabold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de]">
                  Escopo Bloqueado (Intocáveis)
                </p>
                <p className="text-xs text-[#0D0221]/80 dark:text-white/80">
                  {blockedCount} de {totalCount} manterão 100% do formato original
                </p>
              </div>
            </div>

            {/* Status de Validação para Avanço */}
            <div className="flex flex-col justify-center">
              {selectedCount === 0 ? (
                <div
                  role="alert"
                  className="rounded-xl p-3 bg-amber-500/15 border border-amber-500/40 text-amber-950 dark:text-amber-200 flex items-center gap-2.5 text-xs font-bold"
                >
                  <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" aria-hidden="true" />
                  <span>
                    {attemptedEmptySubmit
                      ? "Avanço bloqueado: selecione ao menos 1 característica acima."
                      : "Selecione pelo menos 1 característica observada para liberar a Etapa 3."}
                  </span>
                </div>
              ) : (
                <div className="rounded-xl p-3 bg-emerald-500/15 border border-emerald-500/35 text-emerald-950 dark:text-emerald-200 flex items-center gap-2.5 text-xs font-bold">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" aria-hidden="true" />
                  <span>
                    Isolamento cirúrgico pronto: {selectedCount} ativa(s) e {blockedCount} bloqueada(s).
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Lista compacta dos IDs selecionados quando houver seleção */}
          {selectedCount > 0 && (
            <div className="pt-2 border-t border-[#335C67]/15 dark:border-white/10 flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold text-[#0D0221]/75 dark:text-white/75">
                Características ativas para adaptação:
              </span>
              {selectedIds.map((id) => {
                const item = catalog.caracteristicas.find((c) => c.id_caracteristica === id);
                return (
                  <span
                    key={id}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-[#E35336]/15 text-[#0D0221] dark:text-white border border-[#E35336]/40"
                  >
                    <span>{item?.nome || id}</span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleToggleCharacteristic(id);
                      }}
                      aria-label={`Remover característica ${item?.nome || id}`}
                      className="text-xs font-bold text-[#E35336] hover:underline ml-1"
                    >
                      ×
                    </button>
                  </span>
                );
              })}
            </div>
          )}

          {/* Botões de Ação no Rodapé */}
          <div className="pt-3 border-t border-[#335C67]/15 dark:border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              {onBackToStep1 ? (
                <button
                  type="button"
                  onClick={onBackToStep1}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold bg-[#F5EDF0] dark:bg-white/10 hover:bg-[#335C67]/20 text-[#0D0221] dark:text-white transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" aria-hidden="true" />
                  <span>Voltar para Etapa 1 (Material)</span>
                </button>
              ) : (
                <p className="text-xs text-[#0D0221]/70 dark:text-white/70">
                  O vetor cirúrgico será registrado na sessão sem armazenar dados pessoais de alunos (Zero-Database).
                </p>
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
                  Confirmar Perfil Cirúrgico e Ir para Etapa 3
                  <ArrowRight className="w-4 h-4" aria-hidden="true" />
                </>
              )}
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}
