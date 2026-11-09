"use client";

import React from "react";
import { CheckCircle2, FileText, Sliders, ShieldAlert, Sparkles, Columns } from "lucide-react";

interface Stepper5EtapasProps {
  currentStep?: 1 | 2 | 3 | 4 | 5;
}

const STEPS = [
  {
    id: 1,
    title: "1. Identificar Material",
    subtitle: "Texto ou Upload (.pdf, .docx, .txt)",
    icon: FileText,
  },
  {
    id: 2,
    title: "2. Perfil Funcional",
    subtitle: "Características atômicas observadas",
    icon: Sliders,
  },
  {
    id: 3,
    title: "3. Nível e Travas",
    subtitle: "Andaime 1-3 e Trava Curricular",
    icon: ShieldAlert,
  },
  {
    id: 4,
    title: "4. Adaptação IA",
    subtitle: "Multiagentes + Evidências DUA",
    icon: Sparkles,
  },
  {
    id: 5,
    title: "5. Revisão Lado a Lado",
    subtitle: "Edição docente e Exportação",
    icon: Columns,
  },
] as const;

/**
 * Stepper linear de 5 etapas guiadas (RNF-10: Carga Cognitiva Reduzida na Interface do Professor).
 */
export function Stepper5Etapas({ currentStep = 1 }: Stepper5EtapasProps) {
  return (
    <nav
      aria-label="Progresso do fluxo de adaptação em 5 etapas"
      className="w-full bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 rounded-2xl p-4 shadow-sm"
    >
      <ol className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {STEPS.map((step) => {
          const Icon = step.icon;
          const isCurrent = step.id === currentStep;
          const isCompleted = step.id < currentStep;

          return (
            <li
              key={step.id}
              aria-current={isCurrent ? "step" : undefined}
              className={`flex items-center gap-3 p-3 rounded-xl border transition-all ${
                isCurrent
                  ? "bg-[#E35336]/10 dark:bg-[#E35336]/20 border-[#E35336] text-[#0D0221] dark:text-white shadow-sm"
                  : isCompleted
                  ? "bg-[#335C67]/10 border-[#335C67]/40 text-[#335C67] dark:text-[#F5EDF0]"
                  : "bg-[#F5EDF0]/50 dark:bg-white/5 border-transparent text-[#0D0221]/55 dark:text-white/50"
              }`}
            >
              <div
                className={`flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center font-bold text-sm ${
                  isCurrent
                    ? "bg-[#E35336] text-white"
                    : isCompleted
                    ? "bg-[#335C67] text-white"
                    : "bg-[#335C67]/15 dark:bg-white/10 text-[#335C67] dark:text-white/70"
                }`}
              >
                {isCompleted ? (
                  <CheckCircle2 className="w-5 h-5" aria-hidden="true" />
                ) : (
                  <Icon className="w-4 h-4" aria-hidden="true" />
                )}
              </div>
              <div className="min-w-0">
                <p className="text-xs font-bold truncate">{step.title}</p>
                <p className="text-[11px] opacity-80 truncate">{step.subtitle}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
