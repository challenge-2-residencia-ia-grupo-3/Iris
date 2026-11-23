"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ShieldAlert } from "lucide-react";
import { IrisHeader, STEP_TITLES } from "./IrisHeader";
import { IrisSidebar } from "./IrisSidebar";
import { ReviewEditor } from "./ReviewEditor";
import { JustificativaCard } from "./JustificativaCard";
import { loadStep4ResultFromSession, QuestionMultiAgentTrace } from "@/services/agentsApi";
import { FALLBACK_OFFICIAL_CATALOG } from "@/services/catalogsApi";
import { criarSessao, SessaoRevisao, SessaoRevisaoError } from "@/services/sessionReview";
import { indicadoresAndaime, montarCartao, QuestaoEtapa5, Step5Entrada } from "@/services/comparisonCards";

interface Props {
  /** Resultado do pipeline (Etapas 3 e 4). `null` quando ainda não há adaptação gerada. */
  entrada: Step5Entrada | null;
  /** Exemplo ilustrativo (?demo=1): a tela avisa que não é uma adaptação real. */
  demo?: boolean;
  teacherEmail?: string;
}

/**
 * Etapa 5 — Revisão lado a lado (História 2.2.1, RF-10/RF-13). Original à esquerda, versão adaptada editável
 * à direita, alinhadas questão por questão (em telas estreitas, uma sobre a outra), cada uma com o cartão
 * retrátil da justificativa pedagógica (característica funcional + diretriz do DUA/MEC).
 * A edição, a aprovação e a trava de exportação são da História 2.2.2 (`ReviewEditor`).
 */
export function Step5Review({ entrada, demo = false, teacherEmail = "marina.alves@escola.edu.br" }: Props) {
  const router = useRouter();
  const [sessao, setSessao] = useState<SessaoRevisao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  const [tracesPorId, setTracesPorId] = useState<Map<string, QuestionMultiAgentTrace>>(new Map());
  const iniciada = useRef<number | null>(null);

  const porId = useMemo(() => new Map<string, QuestaoEtapa5>((entrada?.questoes ?? []).map((q) => [q.id, q])), [entrada]);

  useEffect(() => {
    if (demo) {
      setTracesPorId(new Map());
      return;
    }
    const step4 = loadStep4ResultFromSession();
    if (step4?.questoes_trace) {
      setTracesPorId(new Map(step4.questoes_trace.map((t) => [t.id, t])));
    }
  }, [demo, entrada]);

  const reprovadasAuditor = useMemo(() => {
    if (!entrada) return [];
    return entrada.questoes
      .map((q, idx) => ({ questao: q, numero: idx + 1, trace: tracesPorId.get(q.id) }))
      .filter((item) => item.trace && (item.trace.requer_revisao_humana || !item.trace.aprovado_final));
  }, [entrada, tracesPorId]);

  useEffect(() => {
    if (!entrada || entrada.questoes.length === 0 || iniciada.current === tentativa) return;
    iniciada.current = tentativa; // evita criar duas sessões no modo estrito do React
    setCarregando(true);
    setErro(null);
    criarSessao(
      entrada.questoes.map((q) => ({ id: q.id, original: q.original, adaptado: q.adaptado })),
      entrada.titulo
    )
      .then(setSessao)
      .catch((e) => setErro(e instanceof SessaoRevisaoError ? e.message : "Não foi possível abrir a revisão."))
      .finally(() => setCarregando(false));
  }, [entrada, tentativa]);

  return (
    <div className="flex min-h-screen flex-col bg-[#F5EDF0] text-[#0D0221] dark:bg-[#0D0221] dark:text-[#F5EDF0]">
      <IrisHeader currentStep={5} teacherEmail={teacherEmail} />

      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col items-start gap-6 px-4 py-6 sm:px-8 lg:flex-row">
        <IrisSidebar currentStep={5} enabledSteps={[1, 2, 3, 4, 5]} onNavigateStep={(s) => router.push(`/etapa-${s}`)} />

        <main id="conteudo-principal" className="min-w-0 flex-1 space-y-5">
          <div className="space-y-1.5">
            <div className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#B53319] dark:text-[#FF8A70]">
              <span>{STEP_TITLES[5]}</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-extrabold">Revise a adaptação, questão por questão</h1>
          </div>
          <p className="text-sm text-[#0D0221]/80 dark:text-[#F5EDF0]/85">
            À esquerda, o material original. À direita, a versão sugerida pela IA: você pode editar qualquer palavra. Abra “Por que mudou” para ver a
            característica funcional tratada e a diretriz do DUA/MEC que fundamenta a mudança. A exportação só é liberada depois que você aprovar
            todas as questões e confirmar a revisão final.
          </p>

          {demo && (
            <p role="note" className="flex items-start gap-2 rounded-lg bg-[#FFF1DC] px-3 py-2 text-sm font-semibold text-[#5C2A00] dark:bg-[#4A2A08] dark:text-[#FFE2B8]">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              Exemplo ilustrativo: não é uma adaptação gerada pelo pipeline.
            </p>
          )}

          {reprovadasAuditor.length > 0 && (
            <div
              role="alert"
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-amber-600/40 border-l-4 border-l-amber-600 bg-[#FFF1DC] px-4 py-3 text-xs sm:text-sm text-[#5C2A00] dark:bg-[#4A2A08] dark:text-[#FFE2B8]"
            >
              <div className="flex items-start gap-2.5">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <div>
                  <p className="font-bold">
                    Atenção: {reprovadasAuditor.length}{" "}
                    {reprovadasAuditor.length === 1
                      ? "questão foi reprovada pelo Agente Auditor e requer revisão humana"
                      : "questões foram reprovadas pelo Agente Auditor e requerem revisão humana"}{" "}
                    ({reprovadasAuditor.map((r) => `Questão ${r.numero}`).join(", ")}).
                  </p>
                  <p className="mt-0.5 text-xs opacity-90">
                    Confira os motivos abaixo de cada questão e ajuste o texto antes de aprovar.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => router.push("/etapa-4")}
                className="self-start sm:self-center shrink-0 rounded-lg border border-[#5C2A00]/30 dark:border-[#FFE2B8]/30 px-3 py-1.5 text-xs font-semibold hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              >
                Ver detalhes na Etapa 4
              </button>
            </div>
          )}

          {!entrada || entrada.questoes.length === 0 ? (
            <div role="status" className="rounded-xl border border-slate-300 bg-white p-4 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100">
              Ainda não há uma atividade adaptada para revisar. Conclua a adaptação (Etapa 4) e volte aqui.
            </div>
          ) : erro ? (
            <div role="alert" className="space-y-2 rounded-xl border border-red-700 bg-white p-4 text-sm text-red-900 dark:bg-slate-900 dark:text-red-200">
              <p>{erro}</p>
              <button type="button" onClick={() => setTentativa((n) => n + 1)} className="min-h-[44px] rounded-lg bg-[#0D0221] px-4 py-2 font-semibold text-white dark:bg-white dark:text-[#0D0221]">
                Tentar de novo
              </button>
            </div>
          ) : carregando || !sessao ? (
            <p role="status" className="text-sm">Abrindo a revisão…</p>
          ) : (
            <ReviewEditor
              sessao={sessao}
              extras={(q, i) => {
                const dados = porId.get(q.id);
                if (!dados) return null;
                const trace = tracesPorId.get(q.id);
                const reprovada = trace && (trace.requer_revisao_humana || !trace.aprovado_final);
                const ultimaTentativa = trace?.tentativas?.[trace.tentativas.length - 1];
                const motivos = ultimaTentativa?.motivos_auditor ?? [];
                return (
                  <div className="space-y-2">
                    {reprovada && (
                      <div
                        role="note"
                        className="flex items-start gap-2 rounded-lg border border-amber-600/35 bg-[#FFF1DC] px-3 py-2 text-xs text-[#5C2A00] dark:bg-[#4A2A08] dark:text-[#FFE2B8]"
                      >
                        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                        <div>
                          <span className="font-bold">Reprovada pelo Agente Auditor (Requer Revisão Humana)</span>
                          {motivos.length > 0 && (
                            <span className="block mt-0.5">Motivo: {motivos.join("; ")}</span>
                          )}
                        </div>
                      </div>
                    )}
                    <JustificativaCard
                      numero={i + 1}
                      cartao={montarCartao(dados, FALLBACK_OFFICIAL_CATALOG.caracteristicas)}
                      original={q.original}
                      adaptado={q.adaptado}
                      indicadores={indicadoresAndaime(q.adaptado)}
                    />
                  </div>
                );
              }}
            />
          )}
        </main>
      </div>
    </div>
  );
}
