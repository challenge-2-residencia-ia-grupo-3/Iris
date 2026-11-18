"use client";

import React from "react";
import { ArrowLeft, Contrast, Moon, Sun } from "lucide-react";
import { IrisLogoBanner } from "./IrisLogoBanner";
import { IrisMacroStep } from "./IrisSidebar";

interface IrisHeaderProps {
  currentStep: IrisMacroStep;
  stepTitle: string;
  teacherEmail: string;
  highContrast: boolean;
  onToggleHighContrast: () => void;
  darkMode: boolean;
  onToggleDarkMode: () => void;
  onBackToLogin?: () => void;
}

/**
 * Cabeçalho institucional unificado da Plataforma Íris para todas as etapas (1 a 5).
 * Centraliza a identidade editorial, o contexto da etapa atual em sentence case,
 * a identificação docente e os controles de acessibilidade (Alto Contraste WCAG 2.1 AA e Tema).
 */
export function IrisHeader({
  currentStep,
  stepTitle,
  teacherEmail,
  highContrast,
  onToggleHighContrast,
  darkMode,
  onToggleDarkMode,
  onBackToLogin,
}: IrisHeaderProps) {
  return (
    <header className="sticky top-0 z-30 w-full bg-[#0D0221] text-white border-b border-white/10 px-4 sm:px-8 py-3 hc-surface">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <IrisLogoBanner compact />
          <div className="hidden md:block h-7 w-px bg-white/15" aria-hidden="true" />
          <div className="hidden md:flex flex-col justify-center">
            <div className="flex items-center gap-2 text-xs">
              <span className="inline-flex items-center px-2 py-0.5 rounded-md font-semibold bg-[#E35336]/20 text-[#ff9b85] border border-[#E35336]/35">
                Etapa {currentStep} de 5
              </span>
              <span className="font-semibold text-white/95">{stepTitle}</span>
            </div>
            <p className="text-[11px] text-white/65 mt-0.5">
              Docente: <span className="font-mono text-white/90">{teacherEmail}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onToggleHighContrast}
            aria-pressed={highContrast}
            aria-label="Alternar modo de alto contraste"
            title="Alternar modo de alto contraste (WCAG 2.1 AA)"
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              highContrast
                ? "bg-white text-[#0D0221] border-white font-semibold"
                : "bg-white/5 hover:bg-white/15 text-white/90 border-white/15"
            }`}
          >
            <Contrast className="w-3.5 h-3.5 text-[#E35336]" aria-hidden="true" />
            <span className="hidden sm:inline">Alto contraste</span>
          </button>

          <button
            type="button"
            onClick={onToggleDarkMode}
            aria-pressed={darkMode}
            aria-label={darkMode ? "Ativar modo claro" : "Ativar modo escuro"}
            title={darkMode ? "Ativar modo claro" : "Ativar modo escuro"}
            className="p-2 rounded-lg bg-white/5 hover:bg-white/15 text-white/90 border border-white/15 transition-colors"
          >
            {darkMode ? (
              <Sun className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
            ) : (
              <Moon className="w-4 h-4 text-white/90" aria-hidden="true" />
            )}
          </button>

          {onBackToLogin && (
            <button
              type="button"
              onClick={onBackToLogin}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white/80 hover:text-white hover:bg-white/10 border border-transparent hover:border-white/15 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">Trocar conta</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
