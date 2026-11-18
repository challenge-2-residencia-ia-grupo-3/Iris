"use client";

import React from "react";

interface IrisLogoBannerProps {
  compact?: boolean;
}

/**
 * Componente da marca oficial "Íris | Aprender de novas formas"
 * Fiel ao card do protótipo no Figma (fundo escuro Midnight Violet #0D0221,
 * borda branca/suave, olho estilizado em gradiente azul-petróleo e terracota com estrela central).
 */
export function IrisLogoBanner({ compact = false }: IrisLogoBannerProps) {
  if (compact) {
    return (
      <div className="inline-flex items-center gap-3 px-3 py-1.5 rounded-xl bg-white/5 border border-white/15 text-white">
        <img
          src="/logo.jpg"
          alt="Símbolo da Íris"
          className="w-8 h-8 rounded-lg object-cover border border-white/15"
        />
        <div className="flex items-center gap-2.5">
          <span className="font-display text-xl font-semibold tracking-tight text-white">Íris</span>
          <span className="h-4 w-px bg-white/20" aria-hidden="true" />
          <span className="text-[11px] leading-tight text-white/75 font-normal">
            Aprender
            <br />
            de novas formas.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="relative w-full max-w-[390px] rounded-2xl bg-[#130429] border border-white/25 px-6 py-5 shadow-xl overflow-hidden select-none">
      {/* Arco orbital discreto */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-10 -right-10 w-40 h-40 rounded-full border border-[#E35336]/35"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute top-6 right-7 w-2.5 h-2.5 rounded-full bg-[#E35336]"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-16 right-4 w-36 h-36 rounded-full border border-[#335C67]/40"
      />

      <div className="relative z-10 flex items-center gap-4">
        {/* Ícone do olho da Íris */}
        <div className="relative flex-shrink-0 w-20 h-16 flex items-center justify-center">
          <img
            src="/logo.jpg"
            alt="Logotipo Íris"
            className="w-16 h-16 rounded-full object-cover shadow-md border border-white/20"
          />
        </div>

        <div className="h-11 w-px bg-white/20" aria-hidden="true" />

        <div className="flex items-center gap-3">
          <span className="font-display text-3xl sm:text-4xl font-medium tracking-tight text-white">
            Íris
          </span>
          <div className="h-8 w-px bg-white/20" aria-hidden="true" />
          <span className="text-xs leading-snug text-white/75 font-normal">
            Aprender
            <br />
            de novas formas.
          </span>
        </div>
      </div>
    </div>
  );
}
