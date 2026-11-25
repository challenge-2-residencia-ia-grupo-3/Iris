"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, FileText, FileType2, Loader2, ShieldCheck } from "lucide-react";
import {
  baixarSessao,
  diferencas,
  salvarRevisao,
  SessaoRevisao,
  SessaoRevisaoError,
} from "@/services/sessionReview";
import {
  definirAprovacao,
  editarQuestao,
  EstadoRevisao,
  podeExportar,
  podeHomologar,
  QuestaoRevisao,
  resumo,
} from "@/services/reviewState";
import type { FormatoMaterial } from "@/services/materialExport";
import { PreviaAdaptada } from "./TextoAdaptado";

interface Props {
  /** Sessão já criada no servidor (POST /api/v1/sessions) com as questões original/adaptada. */
  sessao: SessaoRevisao;
  /** Conteúdo extra abaixo de cada par de colunas (ex.: cartão de justificativa pedagógica, Etapa 5). */
  extras?: (questao: QuestaoRevisao, indice: number) => React.ReactNode;
}

const ATRASO_SALVAR_MS = 600;

/**
 * Revisão docente (História 2.2.2): edição inline da coluna adaptada, aprovação por questão, confirmação
 * final e exportação só depois da homologação. A trava real está no servidor; aqui o botão só reflete.
 * Usado pela Etapa 5 (História 2.2.1), que acrescenta o cartão de justificativas via `extras`.
 */
export function ReviewEditor({ sessao, extras }: Props) {
  const [estado, setEstado] = useState<EstadoRevisao>({ questoes: sessao.questoes, homologada: sessao.homologada });
  const [confirmado, setConfirmado] = useState(sessao.questoes);
  const [salvando, setSalvando] = useState(false);
  const [exportando, setExportando] = useState<FormatoMaterial | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const emVoo = useRef(false);

  const pendente = diferencas(estado.questoes, confirmado).length > 0;
  const salvo = !pendente && !salvando;

  const sincronizar = useCallback(async () => {
    if (emVoo.current) return;
    const envio = diferencas(estado.questoes, confirmado);
    if (envio.length === 0) return;
    emVoo.current = true;
    setSalvando(true);
    try {
      const resp = await salvarRevisao(sessao.id, { questoes: envio });
      setConfirmado(resp.questoes);
      setErro(null);
    } catch (e) {
      setErro(e instanceof SessaoRevisaoError ? e.message : "Não foi possível salvar as edições.");
    } finally {
      emVoo.current = false;
      setSalvando(false);
    }
  }, [estado.questoes, confirmado, sessao.id]);

  useEffect(() => {
    if (!pendente) return;
    const t = setTimeout(sincronizar, ATRASO_SALVAR_MS);
    return () => clearTimeout(t);
  }, [pendente, sincronizar]);

  const temQuestaoVazia = estado.questoes.some((q) => !q.adaptado.trim());
  const todasAprovadas = estado.questoes.length > 0 && estado.questoes.every((q) => q.aprovada);

  const aprovarTodas = () => {
    if (temQuestaoVazia || todasAprovadas) return;
    setEstado((e) => e.questoes.reduce((acc, q) => definirAprovacao(acc, q.id, true), e));
  };

  const homologarAgora = async () => {
    if (!podeHomologar(estado) || !salvo) return;
    setErro(null);
    try {
      const resp = await salvarRevisao(sessao.id, { homologar: true });
      setConfirmado(resp.questoes);
      setEstado((e) => ({
        ...e,
        homologada: resp.homologada && podeHomologar(e) && diferencas(e.questoes, resp.questoes).length === 0,
      }));
    } catch (e) {
      setErro(e instanceof SessaoRevisaoError ? e.message : "Não foi possível confirmar a revisão.");
    }
  };

  const exportar = async (formato: FormatoMaterial) => {
    if (!podeExportar(estado, salvo)) return;
    setExportando(formato);
    setErro(null);
    try {
      await baixarSessao(sessao.id, formato);
    } catch (e) {
      setErro(e instanceof SessaoRevisaoError ? e.message : "Não foi possível exportar a atividade.");
    } finally {
      setExportando(null);
    }
  };

  const { aprovadas, total } = resumo(estado);
  const liberado = podeExportar(estado, salvo);

  return (
    <section aria-label="Revisão da atividade adaptada" className="space-y-4">
      <ul className="space-y-3">
        {estado.questoes.map((q, i) => (
          <li
            key={q.id}
            aria-label={`Questão ${i + 1}`}
            className="grid grid-cols-1 gap-3 rounded-lg border border-slate-300 p-3 md:grid-cols-2 dark:border-slate-600"
          >
            <div className="min-w-0">
              <h2 className="mb-1 text-xs font-semibold uppercase text-slate-600 dark:text-slate-300">Original · questão {i + 1}</h2>
              <p className="whitespace-pre-wrap break-words text-sm text-slate-800 dark:text-slate-200">{q.original}</p>
            </div>
            <div className="min-w-0">
              <label htmlFor={`adaptado-${q.id}`} className="mb-1 block text-xs font-semibold uppercase text-slate-600 dark:text-slate-300">
                Adaptada (edite à vontade){q.editada ? " · editada por você" : ""}
              </label>
              <textarea
                id={`adaptado-${q.id}`}
                value={q.adaptado}
                onChange={(ev) => setEstado((e) => editarQuestao(e, q.id, ev.target.value))}
                rows={Math.max(3, q.adaptado.split("\n").length + 1)}
                className="w-full rounded-md border border-slate-400 bg-white p-2 text-sm text-slate-900 dark:border-slate-500 dark:bg-slate-900 dark:text-slate-100"
              />
              <PreviaAdaptada texto={q.adaptado} numero={i + 1} />
              <button
                type="button"
                onClick={() => setEstado((e) => definirAprovacao(e, q.id, !q.aprovada))}
                aria-pressed={q.aprovada}
                disabled={!q.adaptado.trim()}
                className={`mt-2 inline-flex min-h-[44px] items-center gap-1 rounded-md border px-3 py-1 text-sm ${
                  q.aprovada ? "border-emerald-700 bg-emerald-50 text-emerald-900" : "border-slate-400 bg-white text-slate-900 dark:border-slate-500 dark:bg-slate-800 dark:text-slate-100"
                }`}
              >
                <CheckCircle2 className="h-4 w-4" aria-hidden />
                {q.aprovada ? "Questão aprovada" : "Aprovar questão"}
              </button>
            </div>
            {extras && <div className="min-w-0 md:col-span-2">{extras(q, i)}</div>}
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-300 p-3 dark:border-slate-600">
        <span className="text-sm" aria-live="polite">
          {aprovadas} de {total} questões aprovadas · {salvando ? "salvando…" : pendente ? "alterações por salvar" : "tudo salvo"}
        </span>
        {!todasAprovadas && total > 1 && (
          <button
            type="button"
            onClick={aprovarTodas}
            disabled={temQuestaoVazia}
            className="inline-flex min-h-[44px] items-center gap-1 rounded-md border border-slate-400 bg-white px-3 py-1.5 text-sm text-slate-900 disabled:opacity-60 dark:border-slate-500 dark:bg-slate-800 dark:text-slate-100"
          >
            <CheckCircle2 className="h-4 w-4" aria-hidden />
            Aprovar todas
          </button>
        )}
        <button
          type="button"
          onClick={homologarAgora}
          disabled={!podeHomologar(estado) || !salvo || estado.homologada}
          className="inline-flex min-h-[44px] items-center gap-1 rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900"
        >
          <ShieldCheck className="h-4 w-4" aria-hidden />
          {estado.homologada ? "Revisão confirmada" : "Confirmar revisão final"}
        </button>
        {(["pdf", "docx"] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => exportar(f)}
            disabled={!liberado || exportando !== null}
            title={liberado ? undefined : "Libera depois que você aprovar todas as questões e confirmar a revisão final."}
            className="inline-flex min-h-[44px] items-center gap-1 rounded-md border border-slate-400 bg-white px-3 py-1.5 text-sm text-slate-900 disabled:opacity-60 dark:border-slate-500 dark:bg-slate-800 dark:text-slate-100"
          >
            {exportando === f ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : f === "pdf" ? <FileText className="h-4 w-4" aria-hidden /> : <FileType2 className="h-4 w-4" aria-hidden />}
            Exportar {f.toUpperCase()}
          </button>
        ))}
      </div>
      {erro && (
        <p role="alert" className="text-sm text-red-800 dark:text-red-300">
          {erro}
        </p>
      )}
    </section>
  );
}
