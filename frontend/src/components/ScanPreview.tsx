"use client";

import React, { useId } from "react";
import { AlertTriangle, CheckCircle2, ImageIcon } from "lucide-react";
import type { OcrMaterialResponse } from "@/services/materialsApi";

interface ScanPreviewProps {
  /** URL local (blob:) da imagem escolhida; vive só na memória do navegador. */
  previewUrl: string;
  fileName: string;
  resultado: OcrMaterialResponse;
}

const NIVEL_TEXTO = {
  baixa: "Baixa densidade visual",
  media: "Densidade visual média",
  alta: "Alta densidade visual",
} as const;

/**
 * Pré-visualização da prova digitalizada (História 1.1.3): a imagem enviada, o indicador de poluição visual
 * (texto, ícone e rótulo, nunca só cor) e os avisos da leitura. O indicador é um aviso e não bloqueia o envio.
 */
export function ScanPreview({ previewUrl, fileName, resultado }: ScanPreviewProps) {
  const detalhesId = useId();
  const { analise_visual: visual, ocr, imagem } = resultado;
  const alta = visual.indicador_poluicao;

  return (
    <section aria-label="Prova digitalizada: pré-visualização e densidade visual" className="space-y-3">
      <figure className="rounded-xl border border-[#335C67]/25 dark:border-white/20 bg-[#FAFAFC] dark:bg-[#0D0221]/80 p-2">
        {/* eslint-disable-next-line @next/next/no-img-element -- blob: local, sem otimização do Next */}
        <img
          src={previewUrl}
          alt={`Pré-visualização da prova digitalizada ${fileName}`}
          className="mx-auto max-h-64 w-auto max-w-full rounded-lg object-contain"
        />
        <figcaption className="mt-1 flex items-center justify-center gap-1.5 text-[11px] text-[#0D0221]/70 dark:text-white/70">
          <ImageIcon className="h-3.5 w-3.5" aria-hidden="true" />
          {imagem.largura}×{imagem.altura} px • lida em memória, a imagem não é guardada
        </figcaption>
      </figure>

      <div
        role="status"
        data-testid="indicador-densidade-visual"
        data-nivel={visual.nivel}
        className={`rounded-xl border p-3 text-xs ${
          alta
            ? "border-amber-600/50 bg-amber-500/10 text-amber-950 dark:text-amber-100"
            : "border-emerald-600/40 bg-emerald-500/10 text-emerald-950 dark:text-emerald-100"
        }`}
      >
        <p className="flex items-center gap-2 font-bold">
          {alta ? (
            <AlertTriangle className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          )}
          {NIVEL_TEXTO[visual.nivel]}
        </p>
        <p className="mt-1">
          {alta
            ? (visual.mensagem ??
              "Esta prova tem muitos elementos visuais concorrentes. Confira o layout ao revisar a adaptação.")
            : "Não há excesso de elementos visuais competindo com o texto."}
        </p>
        <details className="mt-2">
          <summary className="cursor-pointer font-semibold">Como medimos</summary>
          <p id={detalhesId} className="mt-1 opacity-90">
            Bordas e detalhes: {(visual.densidade_bordas * 100).toFixed(1)}% da imagem. Áreas coloridas:{" "}
            {(visual.proporcao_colorida * 100).toFixed(1)}%. É uma estimativa automática, não um laudo: serve para
            você olhar o layout com atenção.
          </p>
        </details>
      </div>

      {ocr.avisos.map((aviso) => (
        <p
          key={aviso.code}
          role="status"
          className="flex items-start gap-2 rounded-xl border border-amber-600/50 bg-amber-500/10 p-3 text-xs text-amber-950 dark:text-amber-100"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
          {aviso.detail}
        </p>
      ))}
    </section>
  );
}
