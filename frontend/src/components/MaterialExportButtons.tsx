"use client";

import React, { useState } from "react";
import { AlertTriangle, FileText, FileType2, Loader2 } from "lucide-react";
import {
  AvisosExportacao,
  baixarMaterial,
  ExportacaoMaterialError,
  FormatoMaterial,
  temAvisos,
  verificarExportacao,
} from "@/services/materialExport";

interface Props {
  /** Texto da atividade JÁ aprovado pelo professor (História 2.2.2). */
  texto: string;
  titulo?: string;
  disabled?: boolean;
}

/**
 * Botões de exportação do material adaptado (PDF econômico e DOCX editável).
 * Componente pronto para encaixar na tela de revisão/aprovação (Histórias 2.2.1 e 2.2.2); ainda não está ligado a nenhuma página.
 */
export function MaterialExportButtons({ texto, titulo, disabled = false }: Props) {
  const [formatoAtivo, setFormatoAtivo] = useState<FormatoMaterial | null>(null);
  const [avisos, setAvisos] = useState<{ formato: FormatoMaterial; dados: AvisosExportacao } | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const exportar = async (formato: FormatoMaterial, confirmado = false) => {
    setFormatoAtivo(formato);
    setErro(null);
    try {
      const material = { titulo, texto };
      if (!confirmado) {
        const dados = await verificarExportacao(material);
        if (temAvisos(dados)) {
          setAvisos({ formato, dados });
          return;
        }
      }
      setAvisos(null);
      await baixarMaterial(material, formato);
    } catch (e) {
      setErro(e instanceof ExportacaoMaterialError ? e.message : "Não foi possível exportar o material.");
    } finally {
      setFormatoAtivo(null);
    }
  };

  const ocupado = formatoAtivo !== null;
  const botao =
    "inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold text-white disabled:opacity-45 disabled:cursor-not-allowed transition-colors";

  return (
    <section aria-label="Exportar material adaptado" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => exportar("pdf")}
          disabled={disabled || ocupado || !texto.trim()}
          className={`${botao} bg-[#335C67] hover:bg-[#274851]`}
        >
          {formatoAtivo === "pdf" ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <FileText className="w-3.5 h-3.5" aria-hidden="true" />
          )}
          Exportar PDF (impressão econômica)
        </button>
        <button
          type="button"
          onClick={() => exportar("docx")}
          disabled={disabled || ocupado || !texto.trim()}
          className={`${botao} bg-[#E35336] hover:bg-[#c94429]`}
        >
          {formatoAtivo === "docx" ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <FileType2 className="w-3.5 h-3.5" aria-hidden="true" />
          )}
          Exportar DOCX (editável)
        </button>
      </div>

      <div aria-live="polite">
        {erro && (
          <p role="alert" className="text-xs font-bold text-red-700 dark:text-red-300">
            {erro}
          </p>
        )}
        {avisos && (
          <div role="alert" className="rounded-lg border border-amber-500/50 bg-amber-50 dark:bg-amber-950/40 p-3 text-xs space-y-2">
            <p className="flex items-start gap-1.5 font-bold text-amber-900 dark:text-amber-100">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
              Confira o texto antes de entregar ao aluno
            </p>
            <ul className="list-disc list-inside text-amber-900 dark:text-amber-100">
              {avisos.dados.possiveis_dados_pessoais > 0 && (
                <li>Há {avisos.dados.possiveis_dados_pessoais} possível(is) dado(s) pessoal(is) (CPF, e-mail, telefone ou nome).</li>
              )}
              {avisos.dados.categorias_clinicas_no_texto.length > 0 && (
                <li>O texto menciona termo clínico. O documento é entregue ao aluno e não deve expor diagnóstico.</li>
              )}
            </ul>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => exportar(avisos.formato, true)} className={`${botao} bg-[#335C67] hover:bg-[#274851]`}>
                Exportar mesmo assim
              </button>
              <button
                type="button"
                onClick={() => setAvisos(null)}
                className="px-3.5 py-2 rounded-xl text-xs font-bold bg-black/5 dark:bg-white/10"
              >
                Voltar e revisar
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
