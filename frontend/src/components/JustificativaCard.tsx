"use client";

import React, { useId, useState } from "react";
import { BookOpen, ChevronDown, ListChecks, Target } from "lucide-react";
import {
  CartaoPedagogico,
  contarTrechosNovos,
  IndicadorAndaime,
  marcarMudancas,
} from "@/services/comparisonCards";

// Classes LITERAIS (o Tailwind só gera o que está escrito por extenso). Os hexes espelham `PALETA_ETAPA5`,
// e um teste confere que são os mesmos e que passam de 4,5:1.
export const CLASSE_INDICADOR = "bg-[#E6F0F2] text-[#1F4650] dark:bg-[#1E3A44] dark:text-[#CDE8F0]";
export const CLASSE_AVISO = "bg-[#FFF1DC] text-[#5C2A00] dark:bg-[#4A2A08] dark:text-[#FFE2B8]";

/** Texto com **negrito** do Agente Adaptador, sem mostrar os asteriscos. */
function Negrito({ texto }: { texto: string }) {
  return (
    <>
      {texto.split(/(\*\*[^*\n]+\*\*)/g).map((parte, i) =>
        /^\*\*[^*\n]+\*\*$/.test(parte) ? <strong key={i}>{parte.slice(2, -2)}</strong> : <React.Fragment key={i}>{parte}</React.Fragment>
      )}
    </>
  );
}

interface Props {
  numero: number;
  cartao: CartaoPedagogico;
  original: string;
  adaptado: string;
  indicadores: IndicadorAndaime[];
  inicialAberto?: boolean;
}

/**
 * Cartão retrátil com a justificativa pedagógica de uma questão: característica funcional tratada,
 * diretriz do DUA/MEC que fundamenta a mudança, andaimes aplicados e o que mudou no texto.
 * Disclosure acessível: botão com aria-expanded/aria-controls; funciona só com teclado.
 */
export function JustificativaCard({ numero, cartao, original, adaptado, indicadores, inicialAberto = false }: Props) {
  const [aberto, setAberto] = useState(inicialAberto);
  const idPainel = useId();
  const trechos = marcarMudancas(original, adaptado);
  const novos = contarTrechosNovos(trechos);

  return (
    <div className="rounded-lg border border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-900">
      <h3 className="m-0">
        <button
          type="button"
          onClick={() => setAberto((v) => !v)}
          aria-expanded={aberto}
          aria-controls={idPainel}
          className="flex min-h-[44px] w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm font-semibold text-slate-900 dark:text-slate-100"
        >
          <span className="min-w-0">
            Por que mudou · questão {numero}
            <span className="block break-words text-xs font-normal text-slate-700 dark:text-slate-300">
              {cartao.caracteristicaNome}
              {cartao.principioDua ? ` · ${cartao.principioDua}` : ""}
            </span>
          </span>
          <ChevronDown className={`h-5 w-5 shrink-0 transition-transform ${aberto ? "rotate-180" : ""}`} aria-hidden />
        </button>
      </h3>

      {indicadores.length > 0 && (
        <ul aria-label={`Andaimes aplicados na questão ${numero}`} className="flex flex-wrap gap-2 px-3 pb-2">
          {indicadores.map((ind) => (
            <li key={ind.id} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${CLASSE_INDICADOR}`}>
              <ListChecks className="h-3.5 w-3.5" aria-hidden />
              {ind.rotulo}
              {ind.quantidade > 1 ? ` (${ind.quantidade})` : ""}
            </li>
          ))}
        </ul>
      )}

      <div id={idPainel} role="region" aria-label={`Justificativa pedagógica da questão ${numero}`} hidden={!aberto} className="space-y-3 border-t border-slate-300 px-3 py-3 text-sm text-slate-900 dark:border-slate-600 dark:text-slate-100">
        {!cartao.caracteristicaEncontrada && (
          <p role="note" className={`rounded-md px-3 py-2 text-xs font-semibold ${CLASSE_AVISO}`}>
            Esta característica não está no catálogo funcional carregado. Confira a adaptação com mais atenção: não há diretriz do DUA/MEC para citar.
          </p>
        )}
        {cartao.semMudanca && (
          <p role="note" className={`rounded-md px-3 py-2 text-xs font-semibold ${CLASSE_AVISO}`}>
            Nenhuma adaptação foi aplicada nesta questão: o texto da direita é o original.
          </p>
        )}

        {cartao.caracteristicaEncontrada && (
          <div>
            <h4 className="flex items-center gap-1 text-xs font-bold uppercase text-slate-700 dark:text-slate-300">
              <Target className="h-4 w-4" aria-hidden /> Característica funcional tratada
            </h4>
            <p className="mt-1 font-semibold">{cartao.caracteristicaNome}</p>
            <p className="text-slate-800 dark:text-slate-200">{cartao.descricaoObservavel}</p>
            <p className="mt-1 text-xs text-slate-700 dark:text-slate-300">
              {cartao.principioDua} · {cartao.rotuloNivel}
            </p>
          </div>
        )}

        {cartao.justificativas.length > 0 && (
          <div>
            <h4 className="text-xs font-bold uppercase text-slate-700 dark:text-slate-300">O que foi feito</h4>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {cartao.justificativas.map((j, i) => (
                <li key={i}>{j}</li>
              ))}
            </ul>
          </div>
        )}

        {cartao.objetivoAndaime && (
          <div>
            <h4 className="text-xs font-bold uppercase text-slate-700 dark:text-slate-300">Objetivo do andaime</h4>
            <p className="mt-1">{cartao.objetivoAndaime}</p>
          </div>
        )}

        {cartao.referencias.length > 0 && (
          <div>
            <h4 className="flex items-center gap-1 text-xs font-bold uppercase text-slate-700 dark:text-slate-300">
              <BookOpen className="h-4 w-4" aria-hidden /> Fundamentação (DUA / MEC)
            </h4>
            <ul className="mt-1 space-y-2">
              {cartao.referencias.map((r) => (
                <li key={r.doc_id} className="break-words">
                  {r.ponto_verificacao_dua && <span className="font-semibold">{r.ponto_verificacao_dua}. </span>}
                  {r.citacao_curta}
                  <span className="block font-mono text-xs text-slate-700 dark:text-slate-300">{r.doc_id}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {indicadores.length > 0 && (
          <div>
            <h4 className="text-xs font-bold uppercase text-slate-700 dark:text-slate-300">Andaimes aplicados neste texto</h4>
            <ul className="mt-1 space-y-1">
              {indicadores.map((ind) => (
                <li key={ind.id}>
                  <span className="font-semibold">{ind.rotulo}:</span> {ind.descricao}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <h4 className="text-xs font-bold uppercase text-slate-700 dark:text-slate-300">O que mudou no texto</h4>
          <p className="mt-1 text-xs text-slate-700 dark:text-slate-300">Trecho <ins className="font-bold underline decoration-2 underline-offset-2">sublinhado e em negrito</ins> = acrescentado ou reescrito.</p>
          <p className="mt-1 whitespace-pre-wrap break-words rounded-md border border-slate-300 p-2 dark:border-slate-600">
            {trechos.map((t, i) =>
              t.novo ? (
                <ins key={i} className="font-bold underline decoration-2 underline-offset-2">
                  <span className="sr-only">início do trecho acrescentado: </span>
                  <Negrito texto={t.texto} />
                  <span className="sr-only"> fim do trecho acrescentado.</span>
                </ins>
              ) : (
                <Negrito key={i} texto={t.texto} />
              )
            )}
          </p>
          <p className="mt-1 text-xs text-slate-700 dark:text-slate-300">{novos === 0 ? "Nenhum trecho novo." : `${novos} trecho(s) novo(s) em relação ao original.`}</p>
        </div>
      </div>
    </div>
  );
}
