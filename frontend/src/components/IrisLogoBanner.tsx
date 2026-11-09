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
      <div className="inline-flex items-center gap-3 px-3.5 py-2 rounded-xl bg-[#0D0221] border border-white/20 text-white shadow-sm">
        <img
          src="/logo.jpg"
          alt="Símbolo da Íris"
          className="w-8 h-8 rounded-lg object-cover"
        />
        <div className="flex items-center gap-2.5">
          <span className="text-lg font-bold tracking-tight text-white">Íris</span>
          <span className="h-4 w-px bg-white/25" aria-hidden="true" />
          <span className="text-[11px] leading-tight text-white/80 font-normal">
            Aprender
            <br />
            de novas formas.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="relative w-full max-w-[390px] rounded-2xl bg-[#130429] border-2 border-white/85 px-6 py-6 shadow-2xl overflow-hidden select-none">
      {/* Arco orbital decorativo idêntico ao protótipo do Figma */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-10 -right-10 w-44 h-44 rounded-full border border-[#E35336]/40"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute top-7 right-8 w-3.5 h-3.5 rounded-full bg-[#E35336] shadow-[0_0_12px_#E35336]"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-16 right-4 w-40 h-40 rounded-full border border-[#335C67]/40"
      />

      <div className="relative z-10 flex items-center gap-4">
        {/* Ícone do olho da Íris */}
        <div className="relative flex-shrink-0 w-24 h-16 flex items-center justify-center">
          <img
            src="/logo.jpg"
            alt="Logotipo Íris"
            className="w-20 h-20 rounded-full object-cover shadow-md border border-white/15"
          />
        </div>

        <div className="h-12 w-px bg-white/25" aria-hidden="true" />

        <div className="flex items-center gap-3">
          <span className="text-4xl font-light tracking-tight text-white">Íris</span>
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
