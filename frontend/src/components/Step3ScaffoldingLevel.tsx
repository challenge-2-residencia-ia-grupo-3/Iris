"use client";

import React, { useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Moon,
  RotateCcw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sun,
} from "lucide-react";

import { IrisLogoBanner } from "./IrisLogoBanner";
import { IrisSidebar } from "./IrisSidebar";
import { useTheme } from "@/contexts/ThemeContext";
import {
  BARREIRA_LABELS,
  CharacteristicItem,
  FALLBACK_OFFICIAL_CATALOG,
  SURGICAL_VECTOR_STORAGE_KEY,
  SurgicalSelectionResponse,
} from "@/services/catalogsApi";
import {
  calibrateScaffoldingSession,
  clearScaffoldingFromSession,
  FALLBACK_SCAFFOLDING_LEVELS,
  loadScaffoldingFromSession,
  saveScaffoldingToSession,
  ScaffoldingCalibrationResult,
  ScaffoldingLevel,
  ScaffoldingLevelMeta,
} from "@/services/scaffoldingApi";
import { IrisApiError } from "@/services/materialsApi";

interface Step3ScaffoldingLevelProps {
  teacherEmail?: string;
  initialLevel?: ScaffoldingLevel;
  onBackToStep2?: () => void;
  onAdvanceToNext?: (result: ScaffoldingCalibrationResult) => void;
}

export function Step3ScaffoldingLevel({
  teacherEmail = "marina.alves@escola.edu.br",
  initialLevel = 2,
  onBackToStep2,
  onAdvanceToNext,
}: Step3ScaffoldingLevelProps) {
  const router = useRouter();
  const { darkMode, toggleDarkMode } = useTheme();

  const [selectedLevel, setSelectedLevel] = useState<ScaffoldingLevel>(initialLevel);
  const [selectedCharacteristics, setSelectedCharacteristics] = useState<CharacteristicItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [isLoadingSession, setIsLoadingSession] = useState(true);
  const [isCalibrating, setIsCalibrating] = useState(false);
  const [calibrationResult, setCalibrationResult] = useState<ScaffoldingCalibrationResult | null>(null);
  const [feedbackBanner, setFeedbackBanner] = useState<{
    type: "success" | "error" | "info";
    title: string;
    message: string;
  } | null>(null);
  const [showDetailedGuidelines, setShowDetailedGuidelines] = useState(false);

  // Carrega a seleção cirúrgica da Etapa 2 e a calibração prévia da Etapa 3 (se houver)
  useEffect(() => {
    try {
      let activeIds: string[] = [];

      const rawSurgical = window.sessionStorage.getItem(SURGICAL_VECTOR_STORAGE_KEY);
      if (rawSurgical) {
        const surgicalData = JSON.parse(rawSurgical) as SurgicalSelectionResponse;
        if (Array.isArray(surgicalData.selected_ids) && surgicalData.selected_ids.length > 0) {
          activeIds = surgicalData.selected_ids;
        }
      }

      // Se não houver seleção na sessão, ativa 2 características por padrão para viabilizar testes e visualização direta
      if (activeIds.length === 0) {
        activeIds = [
          "sobrecarga_memoria_trabalho_comandos_multiplos",
          "retencao_dados_intermediarios_problemas_multietapas",
        ];
      }

      setSelectedIds(activeIds);

      const catalogMap = new Map(
        FALLBACK_OFFICIAL_CATALOG.caracteristicas.map((c) => [c.id_caracteristica, c])
      );
      const items = activeIds
        .map((id) => catalogMap.get(id))
        .filter((c): c is CharacteristicItem => Boolean(c));

      setSelectedCharacteristics(items);

      // Carrega calibração prévia salva na sessão
      const savedCalibration = loadScaffoldingFromSession();
      if (savedCalibration && [1, 2, 3].includes(savedCalibration.nivel)) {
        setSelectedLevel(savedCalibration.nivel);
        setCalibrationResult(savedCalibration);
      }
    } catch {
      // Ignora erro de parsing em sessionStorage
    } finally {
      setIsLoadingSession(false);
    }
  }, []);

  // Recalibra sempre que o nível selecionado ou os IDs mudam
  useEffect(() => {
    if (selectedIds.length === 0) return;

    let isMounted = true;
    setIsCalibrating(true);

    calibrateScaffoldingSession({
      selected_ids: selectedIds,
      nivel: selectedLevel,
    })
      .then((res) => {
        if (isMounted) {
          setCalibrationResult(res);
          saveScaffoldingToSession(res);
        }
      })
      .catch((err) => {
        if (isMounted && err instanceof IrisApiError) {
          setFeedbackBanner({
            type: "error",
            title: "Erro ao calibrar andaime",
            message: err.message,
          });
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsCalibrating(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [selectedLevel, selectedIds]);

  useEffect(() => {
    if (!feedbackBanner) return;
    const timer = window.setTimeout(() => {
      setFeedbackBanner(null);
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [feedbackBanner]);

  const activeMeta: ScaffoldingLevelMeta =
    FALLBACK_SCAFFOLDING_LEVELS.find((m) => m.nivel === selectedLevel) ||
    FALLBACK_SCAFFOLDING_LEVELS[1];

  const getCardContentForLevel = (level: ScaffoldingLevel) => {
    const nivelKey = `nivel_${level}` as "nivel_1" | "nivel_2" | "nivel_3";

    if (selectedCharacteristics.length === 1) {
      const item = selectedCharacteristics[0];
      const guideline = item.diretrizes_andaime[nivelKey];
      const title = guideline.rotulo.replace(/^Adaptação (Leve|Moderada|Intensiva)\s*—\s*/i, "");
      const description = guideline.objetivo_andaime;

      return {
        title,
        description,
      };
    }

    if (selectedCharacteristics.length > 1) {
      const title =
        level === 1
          ? "Acessibilidade & Destaque Visual"
          : level === 2
          ? "Fragmentação & Checklists"
          : "Decomposição Guiada & Pausas";

      const description =
        level === 1
          ? `Ajustes visuais e tipográficos para as ${selectedCharacteristics.length} características selecionadas, preservando 100% da estrutura.`
          : level === 2
          ? `Segmentação e listas sequenciais com checklists para as ${selectedCharacteristics.length} características ativadas.`
          : `Decomposição em subetapas, pausas estratégicas e suporte intensivo para as características ativadas.`;

      return {
        title,
        description,
      };
    }

    const defaultMeta = FALLBACK_SCAFFOLDING_LEVELS.find((m) => m.nivel === level)!;
    return {
      title:
        level === 1
          ? "Acessibilidade & Destaque Visual"
          : level === 2
          ? "Fragmentação & Checklists"
          : "Decomposição Guiada & Pausas",
      description: defaultMeta.objetivo_geral,
    };
  };

  const card1 = getCardContentForLevel(1);
  const card2 = getCardContentForLevel(2);
  const card3 = getCardContentForLevel(3);

  const handleLevelSelect = (level: ScaffoldingLevel) => {
    setSelectedLevel(level);
    setFeedbackBanner(null);
  };

  const handleConfirmAndAdvance = () => {
    if (!calibrationResult) return;

    saveScaffoldingToSession(calibrationResult);

    setFeedbackBanner({
      type: "success",
      title: "Calibração de andaime confirmada!",
      message: `Nível ${calibrationResult.nivel} (${calibrationResult.nome_curto}) registrado na sessão. Salvaguardas anti-muleta ativas.`,
    });

    if (onAdvanceToNext) {
      onAdvanceToNext(calibrationResult);
    } else {
      router.push("/etapa-4");
    }
  };

  const handleBackToStep2 = () => {
    if (onBackToStep2) {
      onBackToStep2();
    } else {
      router.push("/etapa-2");
    }
  };

  const radioGroupId = useId();

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
                Etapa 3 de 5 • Calibragem de Nível de Andaime e Travas
              </p>
              <p className="text-xs text-white/75">
                Docente: <span className="font-mono text-white">{teacherEmail}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={toggleDarkMode}
              aria-label={darkMode ? "Ativar modo claro" : "Ativar modo escuro"}
              className="p-2 rounded-xl text-white/80 hover:text-white hover:bg-white/10 transition-colors"
            >
              {darkMode ? <Sun className="w-4 h-4 text-[#E35336]" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </header>

      {/* Conteúdo Principal com Sidebar Lateral */}
      <div className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 flex flex-col lg:flex-row gap-6">
        {/* Sidebar Lateral Modular */}
        <IrisSidebar
          currentStep={3}
          enabledSteps={[1, 2, 3]}
          onNavigateHome={() => router.push("/")}
        />

        {/* Painel Central */}
        <main id="conteudo-principal" className="flex-1 min-w-0 space-y-6">
          {/* Toast / Alerta Flutuante no Canto Superior Direito */}
          {feedbackBanner && (
            <div className="fixed top-20 right-4 sm:right-6 z-50 w-[calc(100vw-2rem)] sm:w-96 max-w-md pointer-events-none">
              <div
                role="alert"
                aria-live="polite"
                className={`pointer-events-auto p-4 rounded-2xl border border-l-4 text-xs sm:text-sm flex items-start gap-3 shadow-[0_12px_32px_-8px_rgba(13,2,33,0.28)] backdrop-blur-md transition-all animate-in fade-in slide-in-from-top-2 duration-200 ${
                  feedbackBanner.type === "success"
                    ? "bg-white/95 dark:bg-[#160A30]/95 border-emerald-200 dark:border-emerald-800/60 border-l-emerald-600 text-emerald-950 dark:text-emerald-100"
                    : feedbackBanner.type === "error"
                    ? "bg-white/95 dark:bg-[#160A30]/95 border-red-200 dark:border-red-800/60 border-l-red-600 text-red-950 dark:text-red-100"
                    : "bg-white/95 dark:bg-[#160A30]/95 border-[#335C67]/25 dark:border-white/15 border-l-[#E35336] text-[#0D0221] dark:text-white"
                }`}
              >
                {feedbackBanner.type === "success" ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 flex-shrink-0 mt-0.5" />
                ) : feedbackBanner.type === "error" ? (
                  <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                ) : (
                  <ShieldCheck className="w-5 h-5 text-[#E35336] flex-shrink-0 mt-0.5" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="font-bold leading-snug">{feedbackBanner.title}</p>
                  <p className="text-xs opacity-85 mt-1 leading-relaxed">{feedbackBanner.message}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setFeedbackBanner(null)}
                  aria-label="Fechar aviso"
                  className="text-xs font-bold opacity-60 hover:opacity-100 px-1.5 py-0.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-opacity flex-shrink-0"
                >
                  ✕
                </button>
              </div>
            </div>
          )}

          {/* Seção 1: Resumo do Escopo Cirúrgico Ativado na Etapa 2 */}
          <section
            aria-labelledby="titulo-escopo-cirurgico"
            className="p-5 sm:p-6 rounded-2xl bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 shadow-sm space-y-3.5"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <h2
                id="titulo-escopo-cirurgico"
                className="text-base sm:text-lg font-bold text-[#0D0221] dark:text-white"
              >
                Características Funcionais Ativadas ({selectedIds.length})
              </h2>

              <button
                type="button"
                onClick={handleBackToStep2}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-[#335C67] dark:text-[#9fd0de] hover:bg-[#335C67]/10 transition-colors self-start sm:self-auto border border-[#335C67]/25"
              >
                <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Modificar Escopo</span>
              </button>
            </div>

            {/* Badges de Características Ativadas */}
            <div className="flex flex-wrap gap-2 pt-1">
              {selectedCharacteristics.length > 0 ? (
                selectedCharacteristics.map((item) => (
                  <span
                    key={item.id_caracteristica}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-[#F5EDF0] dark:bg-white/10 text-[#0D0221] dark:text-white border border-[#335C67]/15 dark:border-white/10"
                  >
                    <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                    <span>{item.nome}</span>
                    <span className="text-[10px] opacity-60 font-mono">
                      ({BARREIRA_LABELS[item.barreira_rag_associada] || item.barreira_rag_associada})
                    </span>
                  </span>
                ))
              ) : (
                <span className="text-xs text-amber-700 dark:text-amber-300 italic">
                  Nenhuma característica identificada na sessão. O sistema utilizará o conjunto padrão para calibração.
                </span>
              )}
            </div>
          </section>

          {/* Seção 2: Seletor dos 3 Níveis de Andaime Cognitivo (RF-07) */}
          <section
            aria-labelledby="titulo-calibragem-andaime"
            className="p-5 sm:p-7 rounded-2xl bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 shadow-sm space-y-6"
          >
            <div>
              <h2
                id="titulo-calibragem-andaime"
                className="text-xl sm:text-2xl font-black text-[#0D0221] dark:text-white tracking-tight"
              >
                Escolha a Intensidade do Suporte Pedagógico
              </h2>
            </div>

            {/* Grid dos 3 Cards de Seleção de Nível */}
            <div
              role="radiogroup"
              aria-labelledby="titulo-calibragem-andaime"
              className="grid grid-cols-1 md:grid-cols-3 gap-4"
            >
              {/* Card Nível 1: Leve */}
              <button
                type="button"
                role="radio"
                aria-checked={selectedLevel === 1}
                onClick={() => handleLevelSelect(1)}
                className={`relative text-left p-5 rounded-2xl border-2 transition-all flex flex-col justify-between gap-4 focus:outline-none focus:ring-2 focus:ring-[#335C67] ${
                  selectedLevel === 1
                    ? "border-[#335C67] bg-[#335C67]/10 dark:bg-[#335C67]/25 shadow-md shadow-[#335C67]/15"
                    : "border-black/10 dark:border-white/10 hover:border-[#335C67]/50 bg-[#F5EDF0]/50 dark:bg-white/5"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-[#335C67] text-white">
                      Nível 1 • Leve
                    </span>
                    <div
                      className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                        selectedLevel === 1
                          ? "border-[#335C67] bg-[#335C67] text-white"
                          : "border-black/25 dark:border-white/25"
                      }`}
                    >
                      {selectedLevel === 1 && <Check className="w-3 h-3" />}
                    </div>
                  </div>

                  <h3 className="font-bold text-sm sm:text-base text-[#0D0221] dark:text-white">
                    {card1.title}
                  </h3>
                  <p className="text-xs text-[#0D0221]/70 dark:text-white/70 mt-1.5 leading-relaxed">
                    {card1.description}
                  </p>
                </div>
              </button>

              {/* Card Nível 2: Moderado */}
              <button
                type="button"
                role="radio"
                aria-checked={selectedLevel === 2}
                onClick={() => handleLevelSelect(2)}
                className={`relative text-left p-5 rounded-2xl border-2 transition-all flex flex-col justify-between gap-4 focus:outline-none focus:ring-2 focus:ring-[#D97706] ${
                  selectedLevel === 2
                    ? "border-[#D97706] bg-[#D97706]/10 dark:bg-[#D97706]/25 shadow-md shadow-[#D97706]/15"
                    : "border-black/10 dark:border-white/10 hover:border-[#D97706]/50 bg-[#F5EDF0]/50 dark:bg-white/5"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-[#D97706] text-white">
                      Nível 2 • Moderado
                    </span>
                    <div
                      className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                        selectedLevel === 2
                          ? "border-[#D97706] bg-[#D97706] text-white"
                          : "border-black/25 dark:border-white/25"
                      }`}
                    >
                      {selectedLevel === 2 && <Check className="w-3 h-3" />}
                    </div>
                  </div>

                  <h3 className="font-bold text-sm sm:text-base text-[#0D0221] dark:text-white">
                    {card2.title}
                  </h3>
                  <p className="text-xs text-[#0D0221]/70 dark:text-white/70 mt-1.5 leading-relaxed">
                    {card2.description}
                  </p>
                </div>
              </button>

              {/* Card Nível 3: Intensivo */}
              <button
                type="button"
                role="radio"
                aria-checked={selectedLevel === 3}
                onClick={() => handleLevelSelect(3)}
                className={`relative text-left p-5 rounded-2xl border-2 transition-all flex flex-col justify-between gap-4 focus:outline-none focus:ring-2 focus:ring-[#E35336] ${
                  selectedLevel === 3
                    ? "border-[#E35336] bg-[#E35336]/10 dark:bg-[#E35336]/25 shadow-md shadow-[#E35336]/15"
                    : "border-black/10 dark:border-white/10 hover:border-[#E35336]/50 bg-[#F5EDF0]/50 dark:bg-white/5"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-[#E35336] text-white">
                      Nível 3 • Intensivo
                    </span>
                    <div
                      className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                        selectedLevel === 3
                          ? "border-[#E35336] bg-[#E35336] text-white"
                          : "border-black/25 dark:border-white/25"
                      }`}
                    >
                      {selectedLevel === 3 && <Check className="w-3 h-3" />}
                    </div>
                  </div>

                  <h3 className="font-bold text-sm sm:text-base text-[#0D0221] dark:text-white">
                    {card3.title}
                  </h3>
                  <p className="text-xs text-[#0D0221]/70 dark:text-white/70 mt-1.5 leading-relaxed">
                    {card3.description}
                  </p>
                </div>
              </button>
            </div>

            {/* Acordeom de Diretrizes de Andaime por Característica Ativada */}
            {calibrationResult && calibrationResult.caracteristicas_afetadas.length > 0 && (
              <div className="rounded-2xl border border-[#335C67]/20 dark:border-white/15 overflow-hidden bg-white dark:bg-[#160A30]">
                <button
                  type="button"
                  onClick={() => setShowDetailedGuidelines(!showDetailedGuidelines)}
                  className="w-full bg-[#F5EDF0] dark:bg-white/5 px-5 py-3.5 flex items-center justify-between text-left hover:bg-[#335C67]/10 transition-colors"
                >
                  <span className="text-xs font-bold text-[#0D0221] dark:text-white flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-[#335C67] dark:text-[#9fd0de]" />
                    <span>
                      Ver diretrizes detalhadas para cada característica ativada ({calibrationResult.caracteristicas_afetadas.length})
                    </span>
                  </span>

                  <div className="flex items-center gap-3">
                    {isCalibrating && (
                      <span className="inline-flex items-center gap-1.5 text-xs text-[#E35336] animate-pulse">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Calibrando...</span>
                      </span>
                    )}
                    {showDetailedGuidelines ? (
                      <ChevronUp className="w-4 h-4 text-[#0D0221]/60 dark:text-white/60" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-[#0D0221]/60 dark:text-white/60" />
                    )}
                  </div>
                </button>

                {showDetailedGuidelines && (
                  <>
                    <div className="p-4 sm:p-5 space-y-4 border-t border-[#335C67]/15 dark:border-white/10">
                      {calibrationResult.caracteristicas_afetadas.map((d) => (
                        <div
                          key={d.id_caracteristica}
                          className="p-4 rounded-xl bg-[#F5EDF0]/40 dark:bg-white/5 border border-black/5 dark:border-white/5 space-y-2.5"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <h5 className="text-xs font-bold text-[#0D0221] dark:text-white">
                              {d.nome_caracteristica}
                            </h5>
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#335C67]/15 dark:bg-[#335C67]/40 text-[#335C67] dark:text-[#9fd0de]">
                              {d.rotulo}
                            </span>
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px] pt-1">
                            <div className="space-y-1.5">
                              <span className="font-semibold text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5">
                                <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                                Ações Permitidas:
                              </span>
                              <ul className="list-disc list-inside text-[#0D0221]/75 dark:text-white/75 space-y-1 pl-1">
                                {d.acoes_permitidas.map((a, i) => (
                                  <li key={i}>{a}</li>
                                ))}
                              </ul>
                            </div>
                            <div className="space-y-1.5">
                              <span className="font-semibold text-[#E35336] flex items-center gap-1.5">
                                <Shield className="w-3.5 h-3.5 text-[#E35336]" />
                                Restrições Estritas:
                              </span>
                              <ul className="list-disc list-inside text-[#0D0221]/75 dark:text-white/75 space-y-1 pl-1">
                                {d.restricoes_escopo.map((r, i) => (
                                  <li key={i}>{r}</li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Garantia Pedagógica Íris */}
                    <div className="px-5 py-3 bg-[#E35336]/10 dark:bg-[#E35336]/20 border-t border-[#E35336]/25 text-[11px] text-[#0D0221]/85 dark:text-white/90 flex items-center gap-2">
                      <ShieldAlert className="w-4 h-4 text-[#E35336] flex-shrink-0" />
                      <span>
                        <strong>Garantia Pedagógica Íris:</strong> O sistema adapta o suporte procedural, mas jamais reduz o rigor cognitivo avaliado pela questão escolar.
                      </span>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Rodapé da Etapa 3 */}
            <div className="pt-4 border-t border-[#335C67]/15 dark:border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <button
                type="button"
                onClick={handleBackToStep2}
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold bg-[#F5EDF0] dark:bg-white/10 hover:bg-[#335C67]/20 text-[#0D0221] dark:text-white transition-colors"
              >
                <ArrowLeft className="w-4 h-4" aria-hidden="true" />
                <span>Voltar para Etapa 2</span>
              </button>

              <button
                type="button"
                disabled={isCalibrating || !calibrationResult}
                onClick={handleConfirmAndAdvance}
                className="inline-flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl font-bold text-sm text-white bg-[#E35336] hover:bg-[#c94429] disabled:opacity-45 disabled:cursor-not-allowed shadow-[0_8px_20px_-4px_rgba(227,83,54,0.45)] transition-all"
              >
                {isCalibrating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                    <span>Calibrando Andaime...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                    <span>Confirmar Nível de Andaime ({activeMeta.nome_curto})</span>
                    <ArrowRight className="w-4 h-4" aria-hidden="true" />
                  </>
                )}
              </button>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
