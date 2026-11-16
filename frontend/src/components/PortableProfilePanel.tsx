"use client";

import React, { useState } from "react";
import { Download, FileJson, FileText, Loader2, Lock, RefreshCw } from "lucide-react";
import {
  baixarPerfil,
  criarPerfilPortatil,
  PerfilPortatilError,
  type PerfilPedagogicoPortatil,
} from "@/services/portableProfile";
import { baixarPerfilPdf } from "@/services/portableProfileExport";

interface Props {
  selectedIds: string[];
  validIds: string[];
}

/** Gera e exporta o perfil portátil. O perfil só existe nesta variável de estado: nada é salvo no servidor nem no navegador. */
export function PortableProfilePanel({ selectedIds, validIds }: Props) {
  const [perfil, setPerfil] = useState<PerfilPedagogicoPortatil | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [gerandoPdf, setGerandoPdf] = useState(false);

  const mostrarErro = (e: unknown, padrao: string) =>
    setErro(e instanceof PerfilPortatilError ? e.message : padrao);

  const gerar = () => {
    try {
      setPerfil(criarPerfilPortatil(selectedIds, validIds));
      setErro(null);
    } catch (e) {
      setPerfil(null);
      mostrarErro(e, "Não foi possível gerar o perfil.");
    }
  };

  const exportarJson = () => {
    if (!perfil) return;
    try {
      baixarPerfil(perfil);
      setErro(null);
    } catch (e) {
      mostrarErro(e, "Não foi possível baixar o arquivo .json.");
    }
  };

  const exportarPdf = async () => {
    if (!perfil) return;
    setGerandoPdf(true);
    setErro(null);
    try {
      await baixarPerfilPdf(perfil);
    } catch (e) {
      mostrarErro(e, "Não foi possível gerar o PDF.");
    } finally {
      setGerandoPdf(false);
    }
  };

  // Se a seleção mudou depois de gerado, o perfil mostrado já não corresponde: exige gerar de novo.
  const desatualizado =
    perfil !== null &&
    (perfil.caracteristicas_selecionadas.length !== selectedIds.length ||
      perfil.caracteristicas_selecionadas.some((id) => !selectedIds.includes(id)));

  return (
    <section
      aria-label="Perfil pedagógico portátil"
      className="rounded-xl border border-[#335C67]/30 dark:border-white/15 p-4 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FileJson className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
          <h2 className="text-sm font-extrabold">Perfil pedagógico portátil</h2>
        </div>
        <button
          type="button"
          onClick={gerar}
          disabled={selectedIds.length === 0}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-[#335C67] hover:bg-[#274851] text-white disabled:opacity-45 disabled:cursor-not-allowed transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
          {perfil ? "Gerar novo código" : "Gerar perfil portátil"}
        </button>
      </div>

      <p className="flex items-start gap-1.5 text-xs text-[#0D0221]/75 dark:text-white/75">
        <Lock className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" aria-hidden="true" />
        <span>
          O perfil é criado só no seu navegador, com um código aleatório sem relação com o aluno. Nada é salvo no
          servidor: guarde o arquivo baixado e reutilize-o quando quiser. Não inclua nome, laudo ou CID.
        </span>
      </p>

      <div aria-live="polite">
        {erro && (
          <p role="alert" className="text-xs font-bold text-red-700 dark:text-red-300">
            {erro}
          </p>
        )}
        {perfil && (
          <div className="rounded-lg bg-[#F5EDF0]/70 dark:bg-black/25 p-3 space-y-2 text-xs">
            <p>
              Código: <span className="font-mono font-bold">{perfil.codigo_anonimo}</span>
            </p>
            <p>
              Criado em: {new Date(perfil.criado_em).toLocaleString("pt-BR")} •{" "}
              {perfil.caracteristicas_selecionadas.length} característica(s)
            </p>
            {desatualizado && (
              <p role="status" className="font-bold text-amber-700 dark:text-amber-300">
                A seleção mudou depois de gerar o perfil. Gere novamente antes de exportar.
              </p>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={exportarJson}
                disabled={desatualizado}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-[#E35336] hover:bg-[#c94429] text-white disabled:opacity-45 disabled:cursor-not-allowed transition-colors"
              >
                <Download className="w-3.5 h-3.5" aria-hidden="true" />
                Baixar .json (reuso no sistema)
              </button>
              <button
                type="button"
                onClick={exportarPdf}
                disabled={desatualizado || gerandoPdf}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-[#335C67] hover:bg-[#274851] text-white disabled:opacity-45 disabled:cursor-not-allowed transition-colors"
              >
                {gerandoPdf ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <FileText className="w-3.5 h-3.5" aria-hidden="true" />
                )}
                {gerandoPdf ? "Gerando PDF..." : "Baixar .pdf (anexar ao PDI)"}
              </button>
            </div>
            <p className="text-[11px] text-[#0D0221]/65 dark:text-white/65">
              O .json é gerado neste navegador. Para o .pdf, o perfil é enviado ao servidor só para montar o
              relatório e não é guardado.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
