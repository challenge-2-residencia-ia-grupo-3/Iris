"use client";

import React, { useEffect, useState } from "react";
import { Bookmark, Check, Download, FileText, Loader2, Lock, RefreshCw, Trash2 } from "lucide-react";
import {
  baixarPerfil,
  criarPerfilPortatil,
  PerfilPortatilError,
  type PerfilPedagogicoPortatil,
} from "@/services/portableProfile";
import { baixarPerfilPdf } from "@/services/portableProfileExport";
import {
  listarPerfisLocais,
  removerPerfilLocal,
  salvarPerfilLocal,
} from "@/services/portableProfileStorage";

interface Props {
  selectedIds: string[];
  validIds: string[];
  onApplyProfile?: (perfil: PerfilPedagogicoPortatil) => void;
}

/**
 * Gera, guarda neste dispositivo (sem nome nem dados pessoais/clínicos) e exporta o perfil pedagógico portátil.
 */
export function PortableProfilePanel({ selectedIds, validIds, onApplyProfile }: Props) {
  const [perfil, setPerfil] = useState<PerfilPedagogicoPortatil | null>(null);
  const [perfisSalvos, setPerfisSalvos] = useState<PerfilPedagogicoPortatil[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [gerandoPdf, setGerandoPdf] = useState(false);

  useEffect(() => {
    setPerfisSalvos(listarPerfisLocais());
  }, []);

  const mostrarErro = (e: unknown, padrao: string) =>
    setErro(e instanceof PerfilPortatilError ? e.message : padrao);

  const gerar = () => {
    try {
      const novo = criarPerfilPortatil(selectedIds, validIds);
      setPerfil(novo);
      setPerfisSalvos(salvarPerfilLocal(novo));
      setErro(null);
    } catch (e) {
      setPerfil(null);
      mostrarErro(e, "Não foi possível gerar o perfil.");
    }
  };

  const aplicarSalvo = (salvo: PerfilPedagogicoPortatil) => {
    setPerfil(salvo);
    setErro(null);
    if (onApplyProfile) {
      onApplyProfile(salvo);
    }
  };

  const excluirSalvo = (codigoAnonimo: string) => {
    setPerfisSalvos(removerPerfilLocal(codigoAnonimo));
    if (perfil?.codigo_anonimo === codigoAnonimo) {
      setPerfil(null);
    }
  };

  const exportarArquivo = (alvo: PerfilPedagogicoPortatil | null = perfil) => {
    if (!alvo) return;
    try {
      baixarPerfil(alvo);
      setErro(null);
    } catch (e) {
      mostrarErro(e, "Não foi possível baixar o arquivo do perfil.");
    }
  };

  const exportarPdf = async (alvo: PerfilPedagogicoPortatil | null = perfil) => {
    if (!alvo) return;
    setGerandoPdf(true);
    setErro(null);
    try {
      await baixarPerfilPdf(alvo);
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

  const formatarQtd = (qtd: number) =>
    qtd === 1 ? "1 característica" : `${qtd} características`;

  return (
    <section
      aria-label="Perfil pedagógico portátil"
      className="rounded-xl border border-[#335C67]/30 dark:border-white/15 p-4 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Bookmark className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
          <h2 className="text-sm font-extrabold">Perfil pedagógico portátil</h2>
        </div>
        <button
          type="button"
          onClick={gerar}
          disabled={selectedIds.length === 0}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-[#335C67] hover:bg-[#274851] text-white disabled:opacity-45 disabled:cursor-not-allowed transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
          {perfil ? "Gerar novo código" : "Salvar perfil"}
        </button>
      </div>

      <p className="flex items-center gap-1.5 text-xs text-[#0D0221]/75 dark:text-white/75">
        <Lock className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
        <span>Salvo apenas neste dispositivo, sem nome, laudo ou CID do estudante.</span>
      </p>

      <div aria-live="polite" className="space-y-3">
        {erro && (
          <p role="alert" className="text-xs font-bold text-red-700 dark:text-red-300">
            {erro}
          </p>
        )}
        {perfil && (
          <div className="rounded-lg bg-[#F5EDF0]/70 dark:bg-black/25 p-3 space-y-2.5 text-xs">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span>
                Código: <strong className="font-mono">{perfil.codigo_anonimo}</strong>
              </span>
              <span aria-hidden="true">•</span>
              <span>{formatarQtd(perfil.caracteristicas_selecionadas.length)}</span>
              <span aria-hidden="true">•</span>
              <span className="text-[#0D0221]/70 dark:text-white/70">
                {new Date(perfil.criado_em).toLocaleDateString("pt-BR")}
              </span>
            </div>

            {desatualizado && (
              <p role="status" className="font-bold text-amber-700 dark:text-amber-300">
                A seleção mudou. Gere um novo código antes de baixar.
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => exportarArquivo(perfil)}
                disabled={desatualizado}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-[#E35336] hover:bg-[#c94429] text-white disabled:opacity-45 disabled:cursor-not-allowed transition-colors"
              >
                <Download className="w-3.5 h-3.5" aria-hidden="true" />
                Baixar para reutilizar
              </button>
              <button
                type="button"
                onClick={() => exportarPdf(perfil)}
                disabled={desatualizado || gerandoPdf}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-[#335C67] hover:bg-[#274851] text-white disabled:opacity-45 disabled:cursor-not-allowed transition-colors"
              >
                {gerandoPdf ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <FileText className="w-3.5 h-3.5" aria-hidden="true" />
                )}
                {gerandoPdf ? "Gerando PDF..." : "Baixar PDF (PDI)"}
              </button>
            </div>
          </div>
        )}

        {perfisSalvos.length > 0 && (
          <div className="rounded-lg border border-[#335C67]/20 dark:border-white/10 p-3 space-y-2">
            <p className="text-xs font-bold text-[#335C67] dark:text-[#9fd0de]">
              Perfis salvos neste dispositivo ({perfisSalvos.length})
            </p>
            <ul className="space-y-1.5 text-xs">
              {perfisSalvos.map((salvo) => {
                const ativo = perfil?.codigo_anonimo === salvo.codigo_anonimo;
                return (
                  <li
                    key={salvo.codigo_anonimo}
                    className={`flex flex-wrap items-center justify-between gap-2 rounded-lg px-2.5 py-2 ${
                      ativo
                        ? "bg-[#335C67]/15 dark:bg-[#335C67]/30"
                        : "bg-[#F5EDF0]/50 dark:bg-black/20"
                    }`}
                  >
                    <div className="min-w-0">
                      <span className="font-mono font-bold">{salvo.codigo_anonimo}</span>
                      <span className="ml-2 text-[#0D0221]/70 dark:text-white/70">
                        • {formatarQtd(salvo.caracteristicas_selecionadas.length)} •{" "}
                        {new Date(salvo.criado_em).toLocaleDateString("pt-BR")}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {onApplyProfile && (
                        <button
                          type="button"
                          onClick={() => aplicarSalvo(salvo)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-bold bg-[#335C67] hover:bg-[#274851] text-white transition-colors"
                        >
                          <Check className="w-3 h-3" aria-hidden="true" />
                          Aplicar
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => exportarArquivo(salvo)}
                        aria-label={`Baixar arquivo do perfil ${salvo.codigo_anonimo}`}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold bg-black/5 dark:bg-white/10 hover:bg-[#E35336]/15 transition-colors"
                      >
                        <Download className="w-3 h-3" aria-hidden="true" />
                        Baixar
                      </button>
                      <button
                        type="button"
                        onClick={() => excluirSalvo(salvo.codigo_anonimo)}
                        aria-label={`Remover perfil ${salvo.codigo_anonimo}`}
                        className="p-1 rounded-md text-[#0D0221]/65 dark:text-white/65 hover:text-red-700 dark:hover:text-red-300 transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
