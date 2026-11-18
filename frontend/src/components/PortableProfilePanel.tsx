"use client";

import React, { useEffect, useState } from "react";
import { Check, Download, FileJson, FileText, Loader2, Lock, RefreshCw, Trash2 } from "lucide-react";
import {
  baixarPerfil,
  criarPerfilPortatil,
  PerfilPortatilError,
  type PerfilPedagogicoPortatil,
} from "@/services/portableProfile";
import { InterventionFeedback } from "@/components/InterventionFeedback";
import { baixarPerfilPdf } from "@/services/portableProfileExport";
import {
  listarPerfisLocais,
  removerPerfilLocal,
  salvarPerfilLocal,
} from "@/services/portableProfileStorage";

interface Props {
  selectedIds: string[];
  validIds: string[];
  /** Nome legível por id de característica, para o histórico de intervenções. */
  nomesCaracteristicas?: Record<string, string>;
  onApplyProfile?: (perfil: PerfilPedagogicoPortatil) => void;
}

/**
 * Gera, guarda localmente no `localStorage` (sem nome nem dados pessoais/clínicos) e exporta o perfil portátil.
 * Nada do perfil é salvo no servidor.
 */
export function PortableProfilePanel({ selectedIds, validIds, nomesCaracteristicas, onApplyProfile }: Props) {
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

  const atualizarPerfil = (atualizado: PerfilPedagogicoPortatil) => {
    setPerfil(atualizado);
    setPerfisSalvos(salvarPerfilLocal(atualizado));
  };

  const excluirSalvo = (codigoAnonimo: string) => {
    setPerfisSalvos(removerPerfilLocal(codigoAnonimo));
    if (perfil?.codigo_anonimo === codigoAnonimo) {
      setPerfil(null);
    }
  };

  const exportarJson = (alvo: PerfilPedagogicoPortatil | null = perfil) => {
    if (!alvo) return;
    try {
      baixarPerfil(alvo);
      setErro(null);
    } catch (e) {
      mostrarErro(e, "Não foi possível baixar o arquivo .json.");
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
          {perfil ? "Gerar novo código" : "Gerar e salvar perfil local"}
        </button>
      </div>

      <p className="flex items-start gap-1.5 text-xs text-[#0D0221]/75 dark:text-white/75">
        <Lock className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" aria-hidden="true" />
        <span>
          O perfil usa um código aleatório sem nome do aluno e fica salvo apenas no{" "}
          <code className="font-mono">localStorage</code> deste navegador. Nada é salvo no servidor; não inclua nome,
          laudo ou CID.
        </span>
      </p>

      <div aria-live="polite" className="space-y-3">
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
                onClick={() => exportarJson(perfil)}
                disabled={desatualizado}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-[#E35336] hover:bg-[#c94429] text-white disabled:opacity-45 disabled:cursor-not-allowed transition-colors"
              >
                <Download className="w-3.5 h-3.5" aria-hidden="true" />
                Baixar .json (reuso no sistema)
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
                {gerandoPdf ? "Gerando PDF..." : "Baixar .pdf (anexar ao PDI)"}
              </button>
            </div>
            <p className="text-[11px] text-[#0D0221]/65 dark:text-white/65">
              O .json é gerado neste navegador. Para o .pdf, o perfil é enviado ao servidor só para montar o
              relatório e não é guardado.
            </p>
          </div>
        )}

        {perfil && (
          <InterventionFeedback
            key={perfil.codigo_anonimo}
            perfil={perfil}
            nomes={nomesCaracteristicas}
            onPerfilAtualizado={atualizarPerfil}
          />
        )}

        {perfisSalvos.length > 0 && (
          <div className="rounded-lg border border-[#335C67]/20 dark:border-white/10 p-3 space-y-2">
            <p className="text-xs font-bold text-[#335C67] dark:text-[#9fd0de]">
              Perfis anônimos salvos neste navegador ({perfisSalvos.length})
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
                        • {salvo.caracteristicas_selecionadas.length} característica(s) •{" "}
                        {new Date(salvo.criado_em).toLocaleDateString("pt-BR")}
                        {(salvo.historico_intervencoes?.length ?? 0) > 0 &&
                          ` • ${salvo.historico_intervencoes?.length} intervenção(ões)`}
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
                        onClick={() => exportarJson(salvo)}
                        aria-label={`Baixar JSON do perfil ${salvo.codigo_anonimo}`}
                        className="px-2 py-1 rounded-md text-[11px] font-bold bg-black/5 dark:bg-white/10 hover:bg-[#E35336]/15 transition-colors"
                      >
                        .json
                      </button>
                      <button
                        type="button"
                        onClick={() => excluirSalvo(salvo.codigo_anonimo)}
                        aria-label={`Remover perfil local ${salvo.codigo_anonimo}`}
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
