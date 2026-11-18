"use client";

import React, { useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Lock,
  Plus,
  RotateCcw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  X,
} from "lucide-react";

import { IrisHeader } from "./IrisHeader";
import { IrisSidebar } from "./IrisSidebar";
import { useTheme } from "@/contexts/ThemeContext";
import {
  BARREIRA_LABELS,
  CharacteristicItem,
  FALLBACK_OFFICIAL_CATALOG,
  STEP1_MATERIAL_STORAGE_KEY,
  SURGICAL_VECTOR_STORAGE_KEY,
  SurgicalSelectionResponse,
} from "@/services/catalogsApi";
import {
  calibrateScaffoldingSession,
  CurriculumLockInput,
  extractCurriculumLocksFromMaterialLocally,
  FALLBACK_SCAFFOLDING_LEVELS,
  loadScaffoldingFromSession,
  saveScaffoldingToSession,
  ScaffoldingCalibrationResult,
  ScaffoldingLevel,
  ScaffoldingLevelMeta,
  validateCurriculumLocksSession,
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

  const [highContrast, setHighContrast] = useState(false);
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

  // Estados simplificados da Trava Curricular Inegociável (História 1.3.2 — RF-08 e RF-09)
  const [conceitosObrigatorios, setConceitosObrigatorios] = useState<string[]>([]);
  const [conceitoInput, setConceitoInput] = useState("");
  const [objetivoAvaliativo, setObjetivoAvaliativo] = useState("");
  const [extractedFromStep1, setExtractedFromStep1] = useState(false);
  const [hasStep1Material, setHasStep1Material] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    if (highContrast) {
      root.classList.add("high-contrast");
    } else {
      root.classList.remove("high-contrast");
    }
  }, [highContrast]);

  // Carrega a seleção cirúrgica da Etapa 2, o material da Etapa 1 e a calibração prévia da Etapa 3
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

      const rawStep1Text = window.sessionStorage.getItem(STEP1_MATERIAL_STORAGE_KEY) || "";
      const step1Available = rawStep1Text.trim().length > 0;
      setHasStep1Material(step1Available);

      const savedCalibration = loadScaffoldingFromSession();
      const savedLock = savedCalibration?.trava_curricular;
      const hasSavedLock =
        Boolean(savedLock?.conceitos_obrigatorios && savedLock.conceitos_obrigatorios.length > 0) ||
        Boolean(savedLock?.objetivo_avaliativo && savedLock.objetivo_avaliativo.trim());

      if (savedCalibration && [1, 2, 3].includes(savedCalibration.nivel)) {
        setSelectedLevel(savedCalibration.nivel);
        setCalibrationResult(savedCalibration);
      }

      if (hasSavedLock && savedLock) {
        setConceitosObrigatorios(savedLock.conceitos_obrigatorios || []);
        setObjetivoAvaliativo(savedLock.objetivo_avaliativo || "");
      } else if (step1Available) {
        // Extrai automaticamente os conceitos e objetivo diretamente do material anexado na Etapa 1
        const autoExtracted = extractCurriculumLocksFromMaterialLocally(rawStep1Text);
        setConceitosObrigatorios(autoExtracted.conceitos_obrigatorios || []);
        setObjetivoAvaliativo(autoExtracted.objetivo_avaliativo || "");
        setExtractedFromStep1(true);
      }
    } catch {
      // Ignora erro de parsing em sessionStorage
    } finally {
      setIsLoadingSession(false);
    }
  }, []);

  const currentLockPayload: CurriculumLockInput = React.useMemo(
    () => ({
      conceitos_obrigatorios: conceitosObrigatorios,
      termos_tecnicos_intocaveis: conceitosObrigatorios,
      objetivo_avaliativo: objetivoAvaliativo.trim() || null,
    }),
    [conceitosObrigatorios, objetivoAvaliativo]
  );

  // Recalibra sempre que o nível selecionado, os IDs ou a trava curricular mudam
  useEffect(() => {
    if (selectedIds.length === 0) return;

    let isMounted = true;
    setIsCalibrating(true);

    calibrateScaffoldingSession({
      selected_ids: selectedIds,
      nivel: selectedLevel,
      trava_curricular: currentLockPayload,
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
            title: "Erro na validação da Etapa 3",
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
  }, [selectedLevel, selectedIds, currentLockPayload]);

  useEffect(() => {
    if (!feedbackBanner) return;
    const timer = window.setTimeout(() => {
      setFeedbackBanner(null);
    }, 4500);
    return () => window.clearTimeout(timer);
  }, [feedbackBanner]);

  const handleAddConceito = () => {
    const raw = conceitoInput.trim();
    if (!raw) return;
    const novos = raw
      .split(/[;,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (novos.length === 0) return;

    setConceitosObrigatorios((prev) => {
      const lowerSet = new Set(prev.map((item) => item.toLowerCase()));
      const adicionados = [...prev];
      for (const n of novos) {
        if (!lowerSet.has(n.toLowerCase())) {
          lowerSet.add(n.toLowerCase());
          adicionados.push(n);
        }
      }
      return adicionados;
    });
    setConceitoInput("");
  };

  const handleRemoveConceito = (termo: string) => {
    setConceitosObrigatorios((prev) => prev.filter((c) => c !== termo));
  };

  const handleReextractFromStep1 = () => {
    try {
      const rawStep1Text = window.sessionStorage.getItem(STEP1_MATERIAL_STORAGE_KEY) || "";
      if (!rawStep1Text.trim()) return;
      const autoExtracted = extractCurriculumLocksFromMaterialLocally(rawStep1Text);
      setConceitosObrigatorios(autoExtracted.conceitos_obrigatorios || []);
      setObjetivoAvaliativo(autoExtracted.objetivo_avaliativo || "");
      setExtractedFromStep1(true);
      setFeedbackBanner({
        type: "info",
        title: "Conceitos extraídos do material",
        message: "Os conceitos-chave e o objetivo foram atualizados a partir do material da Etapa 1.",
      });
    } catch {
      // Ignora erro de leitura
    }
  };

  const handleValidateLocksExplicitly = async () => {
    try {
      setIsCalibrating(true);
      const res = await validateCurriculumLocksSession({
        selected_ids: selectedIds,
        nivel: selectedLevel,
        trava_curricular: currentLockPayload,
      });
      setCalibrationResult(res);
      saveScaffoldingToSession(res);

      if (res.alerta_preventivo_antimuleta?.emitido) {
        setFeedbackBanner({
          type: "error",
          title: res.alerta_preventivo_antimuleta.titulo,
          message: res.alerta_preventivo_antimuleta.recomendacao_pedagogica,
        });
      } else {
        setFeedbackBanner({
          type: "success",
          title: "Trava Curricular validada!",
          message: `${res.invariantes_auditor?.conceitos_obrigatorios.length || 0} invariante(s) obrigatório(s) registrado(s) para o Agente Auditor.`,
        });
      }
    } catch (err) {
      if (err instanceof IrisApiError) {
        setFeedbackBanner({
          type: "error",
          title: "Trava Curricular incompleta ou inválida",
          message: err.message,
        });
      }
    } finally {
      setIsCalibrating(false);
    }
  };

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
    <div className="min-h-screen flex flex-col bg-[#F5EDF0] dark:bg-[#0D0221] text-[#0D0221] dark:text-[#F5EDF0] transition-colors hc-surface">
      <IrisHeader
        currentStep={3}
        stepTitle="Calibragem de suporte e travas"
        teacherEmail={teacherEmail}
        highContrast={highContrast}
        onToggleHighContrast={() => setHighContrast((prev) => !prev)}
        darkMode={darkMode}
        onToggleDarkMode={toggleDarkMode}
      />

      {/* Conteúdo Principal com Sidebar Lateral */}
      <div className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-6 sm:py-8 flex flex-col lg:flex-row gap-6 items-start">
        {/* Sidebar Lateral Modular */}
        <IrisSidebar
          currentStep={3}
          enabledSteps={[1, 2, 3, 4]}
          onNavigateHome={() => router.push("/")}
        />

        {/* Painel Central */}
        <main id="conteudo-principal" className="flex-1 min-w-0 space-y-5">
          {/* Toast / Alerta Flutuante no Canto Superior Direito */}
          {feedbackBanner && (
            <div className="fixed top-20 right-4 sm:right-6 z-50 w-[calc(100vw-2rem)] sm:w-96 max-w-md pointer-events-none">
              <div
                role="alert"
                aria-live="polite"
                className={`pointer-events-auto p-4 rounded-xl border border-l-4 text-xs sm:text-sm flex items-start gap-3 shadow-lg backdrop-blur-md transition-all ${
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
                  <p className="font-semibold leading-snug">{feedbackBanner.title}</p>
                  <p className="text-xs opacity-85 mt-1 leading-relaxed">{feedbackBanner.message}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setFeedbackBanner(null)}
                  aria-label="Fechar aviso"
                  className="text-xs font-semibold opacity-60 hover:opacity-100 px-1.5 py-0.5 rounded hover:bg-black/5 dark:hover:bg-white/10 transition-opacity flex-shrink-0"
                >
                  ✕
                </button>
              </div>
            </div>
          )}

          {/* Seção 1: Resumo do Escopo Cirúrgico Ativado na Etapa 2 */}
          <section
            aria-labelledby="titulo-escopo-cirurgico"
            className="p-5 rounded-xl bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 space-y-3 hc-surface"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <h2
                id="titulo-escopo-cirurgico"
                className="text-sm font-bold text-[#0D0221] dark:text-white"
              >
                Características funcionais ativadas ({selectedIds.length})
              </h2>

              <button
                type="button"
                onClick={handleBackToStep2}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-[#335C67] dark:text-[#9fd0de] hover:bg-[#335C67]/10 transition-colors self-start sm:self-auto border border-[#335C67]/25"
              >
                <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Modificar escopo</span>
              </button>
            </div>

            {/* Badges de Características Ativadas */}
            <div className="flex flex-wrap gap-2 pt-0.5">
              {selectedCharacteristics.length > 0 ? (
                selectedCharacteristics.map((item) => (
                  <span
                    key={item.id_caracteristica}
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium bg-[#FAF7F8] dark:bg-white/10 text-[#0D0221] dark:text-white border border-[#335C67]/15 dark:border-white/10"
                  >
                    <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                    <span className="font-semibold">{item.nome}</span>
                    <span className="text-[11px] opacity-65">
                      — {BARREIRA_LABELS[item.barreira_rag_associada] || item.barreira_rag_associada}
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
            className="p-5 sm:p-6 rounded-xl bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 space-y-6 hc-surface"
          >
            <div className="space-y-1 border-b border-[#335C67]/15 dark:border-white/10 pb-4">
              <h1
                id="titulo-calibragem-andaime"
                className="font-display text-xl sm:text-2xl font-semibold text-[#0D0221] dark:text-white tracking-tight"
              >
                Escolha a intensidade do suporte pedagógico
              </h1>
              <p className="text-xs sm:text-sm text-[#0D0221]/70 dark:text-white/70 max-w-2xl">
                Calibre o grau de mediação aplicado às características selecionadas, preservando o objetivo avaliativo da questão.
              </p>
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
                className={`relative text-left p-5 rounded-xl border transition-colors flex flex-col justify-between gap-4 focus:outline-none focus:ring-2 focus:ring-[#335C67] ${
                  selectedLevel === 1
                    ? "border-[#335C67] bg-[#335C67]/[0.07] dark:bg-[#335C67]/25"
                    : "border-[#335C67]/20 dark:border-white/10 hover:border-[#335C67]/50 bg-[#FAF7F8] dark:bg-white/[0.03]"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-[#335C67] text-white">
                        Nível 1 — Leve
                      </span>
                      <div className="flex items-center gap-1" aria-hidden="true">
                        <span className="w-2 h-1.5 rounded-sm bg-[#335C67]" />
                        <span className="w-2 h-1.5 rounded-sm bg-black/15 dark:bg-white/15" />
                        <span className="w-2 h-1.5 rounded-sm bg-black/15 dark:bg-white/15" />
                      </div>
                    </div>
                    <div
                      className={`w-5 h-5 rounded-full border flex items-center justify-center transition-colors ${
                        selectedLevel === 1
                          ? "border-[#335C67] bg-[#335C67] text-white"
                          : "border-black/25 dark:border-white/25"
                      }`}
                    >
                      {selectedLevel === 1 && <Check className="w-3 h-3" />}
                    </div>
                  </div>

                  <h2 className="font-display font-semibold text-base text-[#0D0221] dark:text-white">
                    {card1.title}
                  </h2>
                  <p className="text-xs text-[#0D0221]/75 dark:text-white/75 mt-1.5 leading-relaxed">
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
                className={`relative text-left p-5 rounded-xl border transition-colors flex flex-col justify-between gap-4 focus:outline-none focus:ring-2 focus:ring-[#D97706] ${
                  selectedLevel === 2
                    ? "border-[#D97706] bg-[#D97706]/[0.07] dark:bg-[#D97706]/20"
                    : "border-[#335C67]/20 dark:border-white/10 hover:border-[#D97706]/50 bg-[#FAF7F8] dark:bg-white/[0.03]"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-[#D97706] text-white">
                        Nível 2 — Moderado
                      </span>
                      <div className="flex items-center gap-1" aria-hidden="true">
                        <span className="w-2 h-1.5 rounded-sm bg-[#D97706]" />
                        <span className="w-2 h-1.5 rounded-sm bg-[#D97706]" />
                        <span className="w-2 h-1.5 rounded-sm bg-black/15 dark:bg-white/15" />
                      </div>
                    </div>
                    <div
                      className={`w-5 h-5 rounded-full border flex items-center justify-center transition-colors ${
                        selectedLevel === 2
                          ? "border-[#D97706] bg-[#D97706] text-white"
                          : "border-black/25 dark:border-white/25"
                      }`}
                    >
                      {selectedLevel === 2 && <Check className="w-3 h-3" />}
                    </div>
                  </div>

                  <h2 className="font-display font-semibold text-base text-[#0D0221] dark:text-white">
                    {card2.title}
                  </h2>
                  <p className="text-xs text-[#0D0221]/75 dark:text-white/75 mt-1.5 leading-relaxed">
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
                className={`relative text-left p-5 rounded-xl border transition-colors flex flex-col justify-between gap-4 focus:outline-none focus:ring-2 focus:ring-[#E35336] ${
                  selectedLevel === 3
                    ? "border-[#E35336] bg-[#E35336]/[0.07] dark:bg-[#E35336]/20"
                    : "border-[#335C67]/20 dark:border-white/10 hover:border-[#E35336]/50 bg-[#FAF7F8] dark:bg-white/[0.03]"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-[#E35336] text-white">
                        Nível 3 — Intensivo
                      </span>
                      <div className="flex items-center gap-1" aria-hidden="true">
                        <span className="w-2 h-1.5 rounded-sm bg-[#E35336]" />
                        <span className="w-2 h-1.5 rounded-sm bg-[#E35336]" />
                        <span className="w-2 h-1.5 rounded-sm bg-[#E35336]" />
                      </div>
                    </div>
                    <div
                      className={`w-5 h-5 rounded-full border flex items-center justify-center transition-colors ${
                        selectedLevel === 3
                          ? "border-[#E35336] bg-[#E35336] text-white"
                          : "border-black/25 dark:border-white/25"
                      }`}
                    >
                      {selectedLevel === 3 && <Check className="w-3 h-3" />}
                    </div>
                  </div>

                  <h2 className="font-display font-semibold text-base text-[#0D0221] dark:text-white">
                    {card3.title}
                  </h2>
                  <p className="text-xs text-[#0D0221]/75 dark:text-white/75 mt-1.5 leading-relaxed">
                    {card3.description}
                  </p>
                </div>
              </button>
            </div>

            {/* Acordeom de Diretrizes de Andaime por Característica Ativada */}
            {calibrationResult && calibrationResult.caracteristicas_afetadas.length > 0 && (
              <div className="rounded-xl border border-[#335C67]/20 dark:border-white/15 overflow-hidden bg-white dark:bg-[#160A30]">
                <button
                  type="button"
                  onClick={() => setShowDetailedGuidelines(!showDetailedGuidelines)}
                  className="w-full bg-[#FAF7F8] dark:bg-white/5 px-5 py-3.5 flex items-center justify-between text-left hover:bg-[#335C67]/10 transition-colors"
                >
                  <span className="text-xs font-semibold text-[#0D0221] dark:text-white flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-[#335C67] dark:text-[#9fd0de]" />
                    <span>
                      Ver diretrizes detalhadas por característica ativada ({calibrationResult.caracteristicas_afetadas.length})
                    </span>
                  </span>

                  <div className="flex items-center gap-3">
                    {isCalibrating && (
                      <span className="inline-flex items-center gap-1.5 text-xs text-[#E35336]">
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
                          className="p-4 rounded-lg bg-[#FAF7F8] dark:bg-white/5 border border-[#335C67]/15 dark:border-white/10 space-y-2.5"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <h3 className="text-xs font-bold text-[#0D0221] dark:text-white">
                              {d.nome_caracteristica}
                            </h3>
                            <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-[#335C67]/12 dark:bg-[#335C67]/40 text-[#335C67] dark:text-[#9fd0de]">
                              {d.rotulo}
                            </span>
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs pt-1">
                            <div className="space-y-1.5">
                              <span className="font-semibold text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5">
                                <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                                <span>Ações permitidas</span>
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
                                <span>Restrições de escopo</span>
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
                    <div className="px-5 py-3 bg-[#E35336]/10 dark:bg-[#E35336]/20 border-t border-[#E35336]/25 text-xs text-[#0D0221]/85 dark:text-white/90 flex items-center gap-2">
                      <ShieldAlert className="w-4 h-4 text-[#E35336] flex-shrink-0" />
                      <span>
                        <strong>Garantia pedagógica Íris:</strong> o sistema adapta o suporte procedural, mas jamais reduz o rigor cognitivo avaliado pela questão escolar.
                      </span>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Seção 3: Definição de Travas Curriculares Inegociáveis e Alerta Preventivo Anti-Muleta (História 1.3.2 — RF-08, RF-09) */}
            <div
              aria-labelledby="titulo-trava-curricular"
              className="pt-6 border-t border-[#335C67]/15 dark:border-white/10 space-y-4"
            >
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2
                      id="titulo-trava-curricular"
                      className="font-display text-lg sm:text-xl font-semibold text-[#0D0221] dark:text-white flex items-center gap-2"
                    >
                      <Lock className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
                      <span>Travas Curriculares Inegociáveis</span>
                    </h2>
                    {extractedFromStep1 && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-semibold bg-emerald-500/15 text-emerald-800 dark:text-emerald-200 border border-emerald-500/25">
                        <Sparkles className="w-3 h-3" aria-hidden="true" />
                        <span>Extraído automaticamente do material (Etapa 1)</span>
                      </span>
                    )}
                  </div>
                  <p className="text-xs sm:text-sm text-[#0D0221]/70 dark:text-white/70 max-w-2xl">
                    Os conceitos abaixo foram extraídos do seu material e marcados como <strong>invariantes obrigatórios para o Agente Auditor</strong>. Você pode remover ou adicionar termos conforme o foco da avaliação.
                  </p>
                </div>

                {hasStep1Material && (
                  <button
                    type="button"
                    onClick={handleReextractFromStep1}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-[#335C67] dark:text-[#9fd0de] hover:bg-[#335C67]/10 border border-[#335C67]/25 transition-colors self-start flex-shrink-0"
                  >
                    <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                    <span>Reextrair do material</span>
                  </button>
                )}
              </div>

              {/* Bloco Único Enxuto: 1) Conceitos Obrigatórios + 2) Objetivo Avaliativo */}
              <div className="p-4 sm:p-5 rounded-xl bg-[#FAF7F8] dark:bg-white/[0.03] border border-[#335C67]/20 dark:border-white/15 space-y-4">
                {/* Campo 1: Conceitos e termos obrigatórios */}
                <div className="space-y-2">
                  <label
                    htmlFor="input-conceito-trava"
                    className="block text-xs sm:text-sm font-bold text-[#0D0221] dark:text-white"
                  >
                    1. Conceitos e termos obrigatórios (Invariantes do Auditor)
                  </label>

                  {conceitosObrigatorios.length > 0 ? (
                    <div
                      aria-label="Conceitos marcados como invariantes obrigatórios"
                      className="flex flex-wrap gap-2 py-1"
                    >
                      {conceitosObrigatorios.map((termo) => (
                        <span
                          key={termo}
                          className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-white dark:bg-[#160A30] text-[#0D0221] dark:text-white border border-[#335C67]/30 dark:border-white/20 shadow-sm"
                        >
                          <Lock className="w-3 h-3 text-[#E35336]" aria-hidden="true" />
                          <span>{termo}</span>
                          <button
                            type="button"
                            onClick={() => handleRemoveConceito(termo)}
                            aria-label={`Remover conceito ${termo}`}
                            className="ml-1 p-0.5 rounded hover:bg-red-500/15 text-[#0D0221]/60 dark:text-white/60 hover:text-red-600 dark:hover:text-red-300 transition-colors"
                          >
                            <X className="w-3 h-3" aria-hidden="true" />
                          </button>
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-[#0D0221]/55 dark:text-white/55 italic">
                      Nenhum conceito listado ainda. Adicione abaixo os termos que não podem ser omitidos.
                    </p>
                  )}

                  <div className="flex flex-col sm:flex-row gap-2">
                    <input
                      id="input-conceito-trava"
                      type="text"
                      value={conceitoInput}
                      onChange={(e) => setConceitoInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleAddConceito();
                        }
                      }}
                      placeholder="Adicionar outro conceito ou termo intocável (pressione Enter)..."
                      className="flex-1 rounded-lg bg-white dark:bg-[#0D0221] border border-[#335C67]/30 dark:border-white/20 px-3.5 py-2 text-xs sm:text-sm text-[#0D0221] dark:text-white placeholder:text-[#0D0221]/40 dark:placeholder:text-white/40 focus:outline-none focus:border-[#E35336]"
                    />
                    <button
                      type="button"
                      onClick={handleAddConceito}
                      className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-[#335C67] hover:bg-[#26464f] text-white transition-colors flex-shrink-0"
                    >
                      <Plus className="w-4 h-4" aria-hidden="true" />
                      <span>Adicionar</span>
                    </button>
                  </div>
                </div>

                {/* Campo 2: Objetivo avaliativo / Habilidade da BNCC */}
                <div className="space-y-1.5 pt-2 border-t border-[#335C67]/15 dark:border-white/10">
                  <label
                    htmlFor="input-objetivo-avaliativo"
                    className="block text-xs sm:text-sm font-bold text-[#0D0221] dark:text-white"
                  >
                    2. Objetivo avaliativo ou habilidade da BNCC
                  </label>
                  <textarea
                    id="input-objetivo-avaliativo"
                    rows={2}
                    value={objetivoAvaliativo}
                    onChange={(e) => setObjetivoAvaliativo(e.target.value)}
                    placeholder="Ex.: Avaliar interpretação de texto e inferência de sentido implícito (EF67LP08)..."
                    className="w-full rounded-lg bg-white dark:bg-[#0D0221] border border-[#335C67]/25 dark:border-white/20 p-3 text-xs sm:text-sm text-[#0D0221] dark:text-white placeholder:text-[#0D0221]/40 dark:placeholder:text-white/40 focus:outline-none focus:border-[#E35336] resize-none"
                  />
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                  <span className="text-[11px] text-[#0D0221]/65 dark:text-white/65">
                    Retenção mínima exigida pelo Agente Auditor:{" "}
                    <strong>
                      TRCC ≥{" "}
                      {Math.round(
                        (calibrationResult?.invariantes_auditor?.trcc_minimo_exigido || 0.95) * 100
                      )}
                      %
                    </strong>
                    .
                  </span>

                  <button
                    type="button"
                    onClick={handleValidateLocksExplicitly}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold bg-white dark:bg-white/10 hover:bg-[#335C67]/15 text-[#335C67] dark:text-[#9fd0de] border border-[#335C67]/30 dark:border-white/20 transition-colors"
                  >
                    <ShieldCheck className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
                    <span>Validar Trava Curricular</span>
                  </button>
                </div>
              </div>

              {/* Alerta Preventivo Anti-Muleta (RF-09) */}
              {calibrationResult?.alerta_preventivo_antimuleta?.emitido && (
                <div
                  role="alert"
                  aria-live="assertive"
                  data-testid="alerta-preventivo-antimuleta"
                  className={`p-4 sm:p-5 rounded-xl border border-l-4 space-y-3 ${
                    calibrationResult.alerta_preventivo_antimuleta.severidade === "critical"
                      ? "bg-red-500/10 dark:bg-red-950/35 border-red-500/40 border-l-red-600 text-red-950 dark:text-red-100"
                      : "bg-amber-500/12 dark:bg-amber-950/35 border-amber-500/40 border-l-amber-500 text-amber-950 dark:text-amber-100"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <AlertTriangle
                      className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                        calibrationResult.alerta_preventivo_antimuleta.severidade === "critical"
                          ? "text-red-600 dark:text-red-400"
                          : "text-amber-600 dark:text-amber-400"
                      }`}
                      aria-hidden="true"
                    />
                    <div className="flex-1 space-y-1.5">
                      <h3 className="text-xs sm:text-sm font-bold">
                        {calibrationResult.alerta_preventivo_antimuleta.titulo}
                      </h3>
                      <p className="text-xs leading-relaxed">
                        {calibrationResult.alerta_preventivo_antimuleta.mensagem}
                      </p>
                      <p className="text-xs font-semibold pt-0.5">
                        Recomendação:{" "}
                        <span className="font-normal">
                          {calibrationResult.alerta_preventivo_antimuleta.recomendacao_pedagogica}
                        </span>
                      </p>
                    </div>
                  </div>

                  {calibrationResult.alerta_preventivo_antimuleta.nivel_sugerido &&
                    calibrationResult.alerta_preventivo_antimuleta.nivel_sugerido !==
                      selectedLevel && (
                      <div className="flex flex-wrap items-center gap-2 pt-1 pl-8">
                        <button
                          type="button"
                          onClick={() =>
                            handleLevelSelect(
                              calibrationResult.alerta_preventivo_antimuleta!
                                .nivel_sugerido as ScaffoldingLevel
                            )
                          }
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#335C67] text-white hover:bg-[#26464f] transition-colors"
                        >
                          <Sliders className="w-3.5 h-3.5" aria-hidden="true" />
                          <span>
                            Ajustar para Nível{" "}
                            {calibrationResult.alerta_preventivo_antimuleta.nivel_sugerido} recomendado
                          </span>
                        </button>
                      </div>
                    )}
                </div>
              )}
            </div>

            {/* Rodapé da Etapa 3 */}
            <div className="pt-4 border-t border-[#335C67]/15 dark:border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <button
                type="button"
                onClick={handleBackToStep2}
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold bg-[#FAF7F8] dark:bg-white/10 border border-[#335C67]/20 dark:border-white/15 hover:bg-[#335C67]/10 text-[#0D0221] dark:text-white transition-colors"
              >
                <ArrowLeft className="w-4 h-4" aria-hidden="true" />
                <span>Voltar para Etapa 2</span>
              </button>

              <button
                type="button"
                disabled={isCalibrating || !calibrationResult}
                onClick={handleConfirmAndAdvance}
                className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-lg font-semibold text-sm text-white bg-[#C9411F] hover:bg-[#b03618] disabled:opacity-45 disabled:cursor-not-allowed transition-colors"
              >
                {isCalibrating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                    <span>Calibrando andaime...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                    <span>Confirmar nível e travas ({activeMeta.nome_curto})</span>
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
