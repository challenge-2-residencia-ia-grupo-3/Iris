"use client";

import React from "react";
import { ArrowLeft, Contrast, Moon, Sun } from "lucide-react";
import { IrisLogoBanner } from "./IrisLogoBanner";
import { IrisMacroStep } from "./IrisSidebar";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";

export const STEP_TITLES: Record<IrisMacroStep, string> = {
  1: "Etapa 1 de 5 • Gestão de Insumos Pedagógicos",
  2: "Etapa 2 de 5 • Mapeamento Funcional Cirúrgico",
  3: "Etapa 3 de 5 • Calibragem de Nível de Andaime e Travas",
  4: "Etapa 4 de 5 • Orquestração do Sistema Multiagentes",
  5: "Etapa 5 de 5 • Revisão Lado a Lado",
};

interface IrisHeaderProps {
  currentStep: IrisMacroStep;
  teacherEmail?: string;
  darkMode?: boolean;
  onToggleDarkMode?: () => void;
  highContrast?: boolean;
  onToggleHighContrast?: () => void;
  backButton?: {
    label: string;
    onClick: () => void;
  };
}

/**
 * Barra superior institucional padronizada da Plataforma Íris para todas as etapas (1 a 5).
 * Inclui o banner compacto da marca, identificador da etapa atual, e-mail docente,
 * botão de Alto Contraste (RNF-09) e alternador de Modo Claro / Escuro.
 */
export function IrisHeader({
  currentStep,
  teacherEmail,
  darkMode,
  onToggleDarkMode,
  highContrast,
  onToggleHighContrast,
  backButton,
}: IrisHeaderProps) {
  const { teacher, isAuthenticated } = useAuth();
  const {
    darkMode: contextDarkMode,
    toggleDarkMode: contextToggleDarkMode,
    highContrast: contextHighContrast,
    toggleHighContrast: contextToggleHighContrast,
  } = useTheme();

  const docenteLabel =
    isAuthenticated && teacher ? teacher.email : teacherEmail ?? "Modo Convidado";
  const docenteTitle =
    isAuthenticated && teacher ? teacher.nome_exibicao : undefined;

  const isDarkMode = darkMode ?? contextDarkMode;
  const handleToggleDarkMode = onToggleDarkMode ?? contextToggleDarkMode;
  const isHighContrast = highContrast ?? contextHighContrast;
  const handleToggleHighContrast = onToggleHighContrast ?? contextToggleHighContrast;

  return (
    <header className="w-full bg-[#0D0221] text-white border-b border-white/10 px-4 sm:px-8 py-3.5">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <IrisLogoBanner compact />
          <div className="hidden md:block h-7 w-px bg-white/15" aria-hidden="true" />
          <div className="hidden md:block">
            <p className="text-xs font-semibold text-[#FF8A70] uppercase tracking-wider">
              {STEP_TITLES[currentStep]}
            </p>
            <p className="text-xs text-white/75">
              Docente: <span className="font-mono text-white" title={docenteTitle}>{docenteLabel}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleToggleHighContrast}
            aria-pressed={isHighContrast}
            aria-label="Alternar modo de alto contraste"
            title="Alternar modo de alto contraste (WCAG 2.1 AA)"
            className={`inline-flex min-h-[44px] min-w-[44px] items-center justify-center gap-1.5 px-3 rounded-lg text-xs font-semibold border transition-colors ${
              isHighContrast
                ? "bg-white text-[#0D0221] border-white"
                : "bg-white/10 hover:bg-white/20 text-white border-white/15"
            }`}
          >
            <Contrast
              className={`w-4 h-4 ${isHighContrast ? "text-[#0D0221]" : "text-[#FF8A70]"}`}
              aria-hidden="true"
            />
            <span className="hidden sm:inline leading-none">Alto Contraste</span>
          </button>

          <button
            type="button"
            onClick={handleToggleDarkMode}
            aria-label={isDarkMode ? "Ativar modo claro" : "Ativar modo escuro"}
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg bg-white/10 hover:bg-white/20 text-white border border-white/15 transition-colors"
            title={isDarkMode ? "Modo claro" : "Modo escuro"}
          >
            {isDarkMode ? (
              <Sun className="w-4 h-4 text-[#FF8A70]" aria-hidden="true" />
            ) : (
              <Moon className="w-4 h-4" aria-hidden="true" />
            )}
          </button>

          {backButton && (
            <button
              type="button"
              onClick={backButton.onClick}
              className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-[#335C67] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#2A4D56] transition-colors"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" /> {backButton.label}
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
