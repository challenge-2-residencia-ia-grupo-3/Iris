"use client";

import React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ClipboardCheck,
  Columns,
  FileText,
  Home,
  Lock,
  ShieldAlert,
  Sliders,
  Sparkles,
} from "lucide-react";

export type Step2SubStep = "a" | "b" | "c";
export type IrisMacroStep = 1 | 2 | 3 | 4 | 5;

export interface IrisSidebarStep2Config {
  currentSubStep: Step2SubStep;
  onSelectSubStep: (sub: Step2SubStep) => void;
  selectedCharacteristicsCount: number;
}

interface IrisSidebarProps {
  currentStep: IrisMacroStep;
  /** Callback opcional para voltar à tela inicial (/). Se omitido, navega via Next.js Link ("/"). */
  onNavigateHome?: () => void;
  /** Callback opcional ao clicar em uma etapa disponível (1..5). Se omitido, usa router.push(href). */
  onNavigateStep?: (step: IrisMacroStep) => void;
  /** Etapas já liberadas/implementadas para navegação direta (padrão: [1, 2]). */
  enabledSteps?: IrisMacroStep[];
  /** Sub-etapas A, B, C exibidas de forma hierárquica quando `currentStep === 2`. */
  step2SubSteps?: IrisSidebarStep2Config;
}

const MACRO_STEPS: Array<{
  id: IrisMacroStep;
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { id: 1, label: "1. Identificar Material", href: "/etapa-1", icon: FileText },
  { id: 2, label: "2. Perfil Funcional", href: "/etapa-2", icon: Sliders },
  { id: 3, label: "3. Nível e Travas", href: "/etapa-3", icon: ShieldAlert },
  { id: 4, label: "4. Adaptação IA", href: "/etapa-4", icon: Sparkles },
  { id: 5, label: "5. Revisão Lado a Lado", href: "/etapa-5", icon: Columns },
];

/**
 * Barra lateral modular reutilizável em todas as etapas da plataforma Íris (1 a 5).
 * Exibe a hierarquia de navegação, sub-etapas contextuais (ex.: A..C na Etapa 2)
 * e garantia Zero-Database.
 */
export function IrisSidebar({
  currentStep,
  onNavigateHome,
  onNavigateStep,
  enabledSteps = [1, 2],
  step2SubSteps,
}: IrisSidebarProps) {
  const router = useRouter();

  const handleStepClick = (step: IrisMacroStep, href: string) => {
    if (onNavigateStep) {
      onNavigateStep(step);
      return;
    }
    router.push(href);
  };

  return (
    <aside
      aria-label="Navegação lateral da plataforma Íris"
      className="w-full lg:w-64 flex-shrink-0 bg-white/90 dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 rounded-2xl p-4 shadow-sm flex flex-col justify-between gap-5 lg:sticky lg:top-6"
    >
      <div>
        <p className="px-2 text-[11px] font-extrabold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de] mb-2">
          Navegação
        </p>
        <nav aria-label="Menu principal" className="space-y-1">
          {onNavigateHome ? (
            <button
              type="button"
              onClick={onNavigateHome}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-[#0D0221]/80 dark:text-white/80 hover:bg-[#335C67]/10 transition-colors text-left"
            >
              <Home className="w-4 h-4 text-[#335C67] dark:text-[#9fd0de]" aria-hidden="true" />
              <span>Início</span>
            </button>
          ) : (
            <Link
              href="/"
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-[#0D0221]/80 dark:text-white/80 hover:bg-[#335C67]/10 transition-colors"
            >
              <Home className="w-4 h-4 text-[#335C67] dark:text-[#9fd0de]" aria-hidden="true" />
              <span>Início</span>
            </Link>
          )}

          {MACRO_STEPS.map((step) => {
            const Icon = step.icon;
            const isCurrent = step.id === currentStep;
            const isEnabled = enabledSteps.includes(step.id);

            if (isCurrent && step.id === 2 && step2SubSteps) {
              const subItems: Array<{
                id: Step2SubStep;
                letter: string;
                label: string;
                disabled: boolean;
              }> = [
                { id: "a", letter: "A", label: "Perfil funcional", disabled: false },
                {
                  id: "b",
                  letter: "B",
                  label: "Interesses temáticos",
                  disabled: step2SubSteps.selectedCharacteristicsCount === 0,
                },
                {
                  id: "c",
                  letter: "C",
                  label: "Resumo",
                  disabled: step2SubSteps.selectedCharacteristicsCount === 0,
                },
              ];

              return (
                <div
                  key={step.id}
                  className="rounded-xl bg-[#E35336]/10 dark:bg-[#E35336]/15 border border-[#E35336]/30 p-2.5 space-y-2"
                >
                  <div className="flex items-center gap-2 text-xs font-extrabold text-[#E35336]">
                    <Icon className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                    <span>{step.label}</span>
                  </div>

                  <div className="pl-2 ml-2 border-l-2 border-[#E35336]/40 space-y-1">
                    {subItems.map((sub) => {
                      const activeSub = step2SubSteps.currentSubStep === sub.id;
                      return (
                        <button
                          key={sub.id}
                          type="button"
                          disabled={sub.disabled}
                          onClick={() => step2SubSteps.onSelectSubStep(sub.id)}
                          className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-[11px] font-semibold text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] ${
                            activeSub
                              ? "bg-[#E35336] text-white shadow-sm"
                              : sub.disabled
                              ? "opacity-40 cursor-not-allowed text-[#0D0221]/60 dark:text-white/50"
                              : "text-[#0D0221]/80 dark:text-white/80 hover:bg-[#E35336]/15"
                          }`}
                        >
                          <span
                            className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-extrabold ${
                              activeSub
                                ? "bg-white text-[#E35336]"
                                : "bg-[#335C67]/15 dark:bg-white/15 text-[#335C67] dark:text-white"
                            }`}
                          >
                            {sub.letter}
                          </span>
                          <span className="truncate">{sub.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            }

            if (isCurrent) {
              return (
                <div
                  key={step.id}
                  aria-current="page"
                  className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-xs font-extrabold bg-[#E35336] text-white shadow-sm"
                >
                  <Icon className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                  <span className="truncate">{step.label}</span>
                </div>
              );
            }

            if (isEnabled) {
              return (
                <button
                  key={step.id}
                  type="button"
                  onClick={() => handleStepClick(step.id, step.href)}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-[#0D0221]/80 dark:text-white/80 hover:bg-[#335C67]/10 transition-colors text-left"
                >
                  <Icon className="w-4 h-4 text-[#335C67] dark:text-[#9fd0de]" aria-hidden="true" />
                  <span className="truncate">{step.label}</span>
                </button>
              );
            }

            return (
              <div
                key={step.id}
                aria-disabled="true"
                className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl text-xs font-medium text-[#0D0221]/45 dark:text-white/40 cursor-not-allowed"
                title="Etapa disponível nas próximas entregas do fluxo"
              >
                <span className="flex items-center gap-2.5 min-w-0">
                  <Icon className="w-4 h-4 flex-shrink-0 opacity-70" aria-hidden="true" />
                  <span className="truncate">{step.label}</span>
                </span>
                <Lock className="w-3 h-3 flex-shrink-0 opacity-60" aria-hidden="true" />
              </div>
            );
          })}
        </nav>
      </div>

      {/* Cartão Zero-Database Ativo */}
      <div className="rounded-xl p-3 bg-[#F5EDF0]/80 dark:bg-black/25 border border-[#335C67]/15 dark:border-white/10 text-[11px] text-[#0D0221]/75 dark:text-white/75 space-y-1">
        <p className="font-bold text-[#335C67] dark:text-[#9fd0de] flex items-center gap-1.5">
          <ClipboardCheck className="w-3.5 h-3.5" aria-hidden="true" />
          Zero-Database Ativo
        </p>
        <p className="leading-snug">
          Nenhum dado de estudante é salvo em servidor. Tudo permanece na sessão atual.
        </p>
      </div>
    </aside>
  );
}
