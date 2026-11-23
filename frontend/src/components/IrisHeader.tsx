"use client";

import React from "react";
import { Moon, Sun } from "lucide-react";
import { IrisLogoBanner } from "./IrisLogoBanner";
import { IrisMacroStep } from "./IrisSidebar";
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
}

/**
 * Barra superior institucional padronizada da Plataforma Íris para todas as etapas (1 a 5).
 * Inclui o banner compacto da marca, identificador da etapa atual, e-mail docente
 * e alternador de Modo Claro / Escuro.
 */
export function IrisHeader({
  currentStep,
  teacherEmail = "marina.alves@escola.edu.br",
  darkMode,
  onToggleDarkMode,
}: IrisHeaderProps) {
  const { darkMode: contextDarkMode, toggleDarkMode: contextToggleDarkMode } = useTheme();

  const isDarkMode = darkMode ?? contextDarkMode;
  const handleToggleDarkMode = onToggleDarkMode ?? contextToggleDarkMode;

  return (
    <header className="w-full bg-[#0D0221] text-white border-b border-white/10 px-4 sm:px-8 py-3.5">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <IrisLogoBanner compact />
          <div className="hidden md:block h-7 w-px bg-white/15" aria-hidden="true" />
          <div className="hidden md:block">
            <p className="text-xs font-semibold text-[#E35336] uppercase tracking-wider">
              {STEP_TITLES[currentStep]}
            </p>
            <p className="text-xs text-white/75">
              Docente: <span className="font-mono text-white">{teacherEmail}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={handleToggleDarkMode}
            aria-label={isDarkMode ? "Ativar modo claro" : "Ativar modo escuro"}
            className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white border border-white/15 transition-colors"
            title={isDarkMode ? "Modo claro" : "Modo escuro"}
          >
            {isDarkMode ? (
              <Sun className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
            ) : (
              <Moon className="w-4 h-4" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
