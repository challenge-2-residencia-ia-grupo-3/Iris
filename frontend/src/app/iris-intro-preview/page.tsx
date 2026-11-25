"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import type gsap from "gsap";
import { IrisIntro } from "@/components/iris-intro/IrisIntro";
import {
  IRIS_MOMENTS,
  IRIS_TIMELINE_DURATION,
} from "@/components/iris-intro/IrisAnimation";

/**
 * Ambiente isolado de pré-visualização e validação da abertura cinematográfica Íris.
 * Os controles abaixo são exclusivamente de desenvolvimento e não fazem parte
 * do componente `IrisIntro`.
 */
export default function IrisIntroPreviewPage() {
  const tlRef = useRef<gsap.core.Timeline | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [hideControls, setHideControls] = useState(false);

  // Suporta query params ?t=2.0&controls=0 para capturas precisas de quadros-chave
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("controls") === "0") {
      setHideControls(true);
    }
    if (params.get("reduced") === "1") {
      setReducedMotion(true);
    }
  }, []);

  const handleTimelineReady = useCallback((tl: gsap.core.Timeline | null) => {
    tlRef.current = tl;
    if (!tl || typeof window === "undefined") return;

    const params = new URLSearchParams(window.location.search);
    const seekStr = params.get("t");
    if (seekStr !== null) {
      const seekSec = Number(seekStr);
      if (!Number.isNaN(seekSec)) {
        tl.pause(Math.max(0, Math.min(IRIS_TIMELINE_DURATION, seekSec)));
        setIsPaused(true);
        setCurrentTime(tl.time());
        return;
      }
    }
    setIsPaused(false);
  }, []);

  const handleReplay = () => {
    if (reducedMotion) {
      setReducedMotion(false);
      return;
    }
    const tl = tlRef.current;
    if (!tl) return;
    tl.restart();
    setIsPaused(false);
  };

  const handleTogglePlay = () => {
    const tl = tlRef.current;
    if (!tl) return;
    if (tl.paused()) {
      if (tl.progress() >= 0.999) {
        tl.restart();
      } else {
        tl.play();
      }
      setIsPaused(false);
    } else {
      tl.pause();
      setIsPaused(true);
    }
  };

  const handleScrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    const tl = tlRef.current;
    if (!tl) return;
    tl.pause(val);
    setIsPaused(true);
    setCurrentTime(val);
  };

  const jumpTo = (sec: number) => {
    if (reducedMotion) return;
    const tl = tlRef.current;
    if (!tl) return;
    tl.pause(sec);
    setIsPaused(true);
    setCurrentTime(sec);
  };

  const activeMoment =
    IRIS_MOMENTS.find((m) => currentTime >= m.start && currentTime <= m.end) ??
    IRIS_MOMENTS[IRIS_MOMENTS.length - 1];

  return (
    <main className="relative min-h-screen bg-[#0D0221]">
      <IrisIntro
        reducedMotion={reducedMotion}
        onTimelineReady={handleTimelineReady}
        onTimeUpdate={(t) => setCurrentTime(t)}
        onComplete={() => setIsPaused(true)}
      />

      {/* Botão discreto para reexibir controles quando ocultos */}
      {hideControls && (
        <button
          type="button"
          onClick={() => setHideControls(false)}
          className="fixed bottom-4 right-4 z-50 rounded-full border border-white/15 bg-[#0D0221]/80 px-3.5 py-1.5 text-xs text-white/70 backdrop-blur-md transition hover:border-white/35 hover:text-white"
        >
          Mostrar controles
        </button>
      )}

      {/* Barra de controles de desenvolvimento (isolada do componente final) */}
      {!hideControls && (
        <aside
          aria-label="Controles de teste da animação"
          className="fixed bottom-5 left-1/2 z-50 w-[min(94vw,760px)] -translate-x-1/2 rounded-2xl border border-white/12 bg-[#0D0221]/85 px-4 py-3 text-white shadow-2xl backdrop-blur-md"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-white/10">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleReplay}
                className="rounded-lg bg-[#399CAD]/25 border border-[#399CAD]/50 px-3 py-1.5 text-xs font-medium text-[#8CE6F2] transition hover:bg-[#399CAD]/40"
              >
                Reproduzir novamente
              </button>
              <button
                type="button"
                onClick={handleTogglePlay}
                disabled={reducedMotion}
                className="rounded-lg bg-white/10 border border-white/15 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-white/20 disabled:opacity-40"
              >
                {isPaused ? "Continuar" : "Pausar"}
              </button>
              <button
                type="button"
                onClick={() => setReducedMotion((v) => !v)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                  reducedMotion
                    ? "border-[#F68B46] bg-[#F68B46]/25 text-[#FFD2AC]"
                    : "border-white/15 bg-white/5 text-white/75 hover:bg-white/15"
                }`}
              >
                {reducedMotion ? "Movimento Reduzido: ON" : "Testar Movimento Reduzido"}
              </button>
            </div>

            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-white/75 tabular-nums">
                {reducedMotion
                  ? "Estático"
                  : `${currentTime.toFixed(2)}s / ${IRIS_TIMELINE_DURATION.toFixed(1)}s · ${activeMoment.code}`}
              </span>
              <button
                type="button"
                onClick={() => setHideControls(true)}
                className="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-white/55 transition hover:border-white/25 hover:text-white"
              >
                Ocultar
              </button>
            </div>
          </div>

          {!reducedMotion && (
            <div className="pt-2.5 space-y-2">
              <input
                type="range"
                min={0}
                max={IRIS_TIMELINE_DURATION}
                step={0.01}
                value={currentTime}
                onChange={handleScrub}
                aria-label="Linha do tempo da animação"
                className="w-full accent-[#399CAD] cursor-pointer h-1.5"
              />
              <div className="flex flex-wrap justify-between gap-1">
                {IRIS_MOMENTS.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => jumpTo(m.start + (m.end - m.start) * 0.55)}
                    className={`rounded px-2 py-0.5 font-mono text-[10.5px] transition ${
                      activeMoment.id === m.id
                        ? "bg-[#399CAD]/30 text-[#8CE6F2] border border-[#399CAD]/50"
                        : "bg-white/5 text-white/60 hover:bg-white/15 hover:text-white"
                    }`}
                  >
                    {m.code} · {m.title}
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>
      )}
    </main>
  );
}
