"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { IrisIntro } from "./IrisIntro";

export interface IrisIntroOverlayProps {
  /** Disparado no início do fade-out para iniciar a revelação gradual do login */
  onExitStart?: () => void;
  /** Chamado quando a animação e o fade-out suave terminam completamente */
  onFinished: () => void;
}

/**
 * Orquestra a exibição em tela cheia da abertura cinematográfica `IrisIntro`
 * sobre a tela de login já montada, realizando uma transição suave sem flash
 * assim que a timeline GSAP é concluída.
 */
export function IrisIntroOverlay({ onExitStart, onFinished }: IrisIntroOverlayProps) {
  const [isExiting, setIsExiting] = useState(false);
  const [prefersReduced, setPrefersReduced] = useState(false);
  const exitStartedRef = useRef(false);
  const timersRef = useRef<number[]>([]);

  // Limpa timers pendentes caso o componente seja desmontado antes do fim
  useEffect(() => {
    return () => {
      timersRef.current.forEach((id) => window.clearTimeout(id));
      timersRef.current = [];
    };
  }, []);

  const triggerSmoothExit = useCallback(
    (holdMs: number, fadeMs: number) => {
      if (exitStartedRef.current) return;
      exitStartedRef.current = true;

      const tHold = window.setTimeout(() => {
        setIsExiting(true);
        onExitStart?.();
        const tDone = window.setTimeout(() => {
          onFinished();
        }, fadeMs);
        timersRef.current.push(tDone);
      }, holdMs);

      timersRef.current.push(tHold);
    },
    [onExitStart, onFinished]
  );

  // Detecta prefers-reduced-motion para oferecer transição simplificada e respeitosa
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq.matches) {
      setPrefersReduced(true);
      triggerSmoothExit(650, 350);
    }
  }, [triggerSmoothExit]);

  // Disparado exatamente pelo onComplete real da timeline GSAP (t = 5.2s)
  const handleIntroComplete = useCallback(() => {
    // Breve respiro de 400ms na assinatura final antes do fade-out suave de 650ms
    triggerSmoothExit(400, 650);
  }, [triggerSmoothExit]);

  return (
    <div
      role="presentation"
      aria-label="Abertura da marca Íris"
      style={{
        transition: `opacity ${prefersReduced ? 350 : 650}ms cubic-bezier(0.22, 1, 0.36, 1)`,
        opacity: isExiting ? 0 : 1,
        pointerEvents: isExiting ? "none" : "auto",
      }}
      className="fixed inset-0 z-50 bg-[#0D0221]"
    >
      <IrisIntro
        reducedMotion={prefersReduced}
        onComplete={handleIntroComplete}
      />
    </div>
  );
}
