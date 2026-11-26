"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  BookmarkCheck,
  CheckCircle2,
  FolderClock,
  Loader2,
  ShieldAlert,
} from "lucide-react";
import { IrisHeader, STEP_TITLES } from "./IrisHeader";
import { IrisSidebar } from "./IrisSidebar";
import { ReviewEditor } from "./ReviewEditor";
import { JustificativaCard } from "./JustificativaCard";
import { useAuth } from "@/contexts/AuthContext";
import { loadStep4ResultFromSession, QuestionMultiAgentTrace } from "@/services/agentsApi";
import { FALLBACK_OFFICIAL_CATALOG } from "@/services/catalogsApi";
import { criarSessao, SessaoRevisao, SessaoRevisaoError } from "@/services/sessionReview";
import { indicadoresAndaime, montarCartao, QuestaoEtapa5, Step5Entrada } from "@/services/comparisonCards";
import type { EstadoRevisao } from "@/services/reviewState";
import {
  type HistoryActivityDetail,
  HistoryApiError,
  type SaveHistoryPayload,
  createHistoryActivity,
  updateHistoryActivity,
} from "@/services/historyApi";

interface Props {
  /** Resultado do pipeline (Etapas 3 e 4). `null` quando ainda não há adaptação gerada. */
  entrada: Step5Entrada | null;
  /** Exemplo ilustrativo (?demo=1): a tela avisa que não é uma adaptação real. */
  demo?: boolean;
  teacherEmail?: string;
  /** Atividade carregada do histórico (?historyId=...) para edição/atualização. */
  historyItem?: HistoryActivityDetail | null;
}

/**
 * Etapa 5 — Revisão lado a lado (História 2.2.1, RF-10/RF-13). Original à esquerda, versão adaptada editável
 * à direita, alinhadas questão por questão (em telas estreitas, uma sobre a outra), cada uma com o cartão
 * retrátil da justificativa pedagógica (característica funcional + diretriz do DUA/MEC).
 * A edição, a aprovação e a trava de exportação são da História 2.2.2 (`ReviewEditor`).
 */
export function Step5Review({ entrada, demo = false, teacherEmail, historyItem = null }: Props) {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [sessao, setSessao] = useState<SessaoRevisao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  const [tracesPorId, setTracesPorId] = useState<Map<string, QuestionMultiAgentTrace>>(new Map());
  const iniciada = useRef<number | null>(null);

  const [liveEstado, setLiveEstado] = useState<EstadoRevisao | null>(null);
  const [savedHistoryId, setSavedHistoryId] = useState<string | null>(historyItem?.id ?? null);
  const [tituloHistorico, setTituloHistorico] = useState(
    historyItem?.titulo ?? entrada?.titulo ?? "Atividade adaptada"
  );
  const [disciplinaHistorico, setDisciplinaHistorico] = useState(historyItem?.disciplina ?? "");
  const [anoHistorico, setAnoHistorico] = useState(historyItem?.ano_escolar ?? "");
  const [salvandoHistorico, setSalvandoHistorico] = useState(false);
  const [historicoMsg, setHistoricoMsg] = useState<string | null>(null);
  const [historicoErro, setHistoricoErro] = useState<string | null>(null);
  const [precisaSanitizarPii, setPrecisaSanitizarPii] = useState(false);

  const porId = useMemo(
    () => new Map<string, QuestaoEtapa5>((entrada?.questoes ?? []).map((q) => [q.id, q])),
    [entrada]
  );

  useEffect(() => {
    if (historyItem) {
      setSavedHistoryId(historyItem.id);
      setTituloHistorico(historyItem.titulo);
      setDisciplinaHistorico(historyItem.disciplina ?? "");
      setAnoHistorico(historyItem.ano_escolar ?? "");
    } else if (entrada?.titulo) {
      setTituloHistorico(entrada.titulo);
    }
  }, [historyItem, entrada?.titulo]);

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
      historyItem?.titulo ?? entrada.titulo
    )
      .then((s) => {
        setSessao(s);
        setLiveEstado({ questoes: s.questoes, homologada: s.homologada });
      })
      .catch((e) => setErro(e instanceof SessaoRevisaoError ? e.message : "Não foi possível abrir a revisão."))
      .finally(() => setCarregando(false));
  }, [entrada, tentativa, historyItem?.titulo]);

  const salvarNoHistorico = async (autoSanitizar = false) => {
    if (!sessao || !entrada) return;
    const estadoAtual = liveEstado ?? { questoes: sessao.questoes, homologada: sessao.homologada };
    const caracteristicasUnicas = Array.from(
      new Set(entrada.questoes.map((q) => q.id_caracteristica).filter(Boolean))
    );
    const nivelPrincipal = (historyItem?.nivel_andaime ?? entrada.questoes[0]?.nivel ?? 2) as 1 | 2 | 3;

    const payload: SaveHistoryPayload = {
      titulo: tituloHistorico.trim() || "Atividade adaptada",
      disciplina: disciplinaHistorico.trim() || null,
      ano_escolar: anoHistorico.trim() || null,
      nivel_andaime: nivelPrincipal,
      caracteristicas_ids: caracteristicasUnicas,
      travas_curriculares: historyItem?.travas_curriculares ?? {},
      questoes: estadoAtual.questoes.map((q) => {
        const meta = porId.get(q.id);
        return {
          id: q.id,
          original: q.original,
          adaptado: q.adaptado,
          editada: q.editada,
          aprovada: q.aprovada,
          justificativas: meta?.justificativas ?? [],
          ...(meta?.recomendacao_docente ? { recomendacao_docente: meta.recomendacao_docente } : {}),
        };
      }),
      metricas: historyItem?.metricas ?? {},
      status: estadoAtual.homologada ? "homologada" : "rascunho",
    };

    setSalvandoHistorico(true);
    setHistoricoErro(null);
    setHistoricoMsg(null);
    setPrecisaSanitizarPii(false);

    try {
      const saved = savedHistoryId
        ? await updateHistoryActivity(savedHistoryId, payload, autoSanitizar)
        : await createHistoryActivity(payload, autoSanitizar);
      setSavedHistoryId(saved.id);
      setHistoricoMsg(
        saved.status === "homologada"
          ? "Atividade homologada salva no seu histórico!"
          : "Rascunho salvo no seu histórico!"
      );
    } catch (e) {
      if (e instanceof HistoryApiError) {
        setHistoricoErro(e.message);
        if (e.code === "PII_DETECTED") {
          setPrecisaSanitizarPii(true);
        }
      } else {
        setHistoricoErro("Não foi possível salvar no histórico agora.");
      }
    } finally {
      setSalvandoHistorico(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#F5EDF0] text-[#0D0221] dark:bg-[#0D0221] dark:text-[#F5EDF0]">
      <IrisHeader
        currentStep={5}
        teacherEmail={teacherEmail}
        backButton={{ label: "Etapa 4", onClick: () => router.push("/etapa-4") }}
      />

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
                className="self-start sm:self-center shrink-0 min-h-[44px] rounded-lg border border-[#5C2A00]/30 dark:border-[#FFE2B8]/30 px-3 py-1.5 text-xs font-semibold hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              >
                Ver parecer do Auditor
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
            <>
              <ReviewEditor
                sessao={sessao}
                onStateChange={setLiveEstado}
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

              <section
                aria-label="Salvar no histórico da conta docente"
                className="rounded-2xl border border-[#335C67]/25 bg-white dark:bg-[#160A30] p-5 space-y-4 shadow-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-base font-extrabold flex items-center gap-2">
                      <BookmarkCheck className="w-5 h-5 text-[#335C67] dark:text-[#9fd0de]" aria-hidden />
                      <span>{savedHistoryId ? "Atualizar no Meu Histórico" : "Salvar no Meu Histórico"}</span>
                    </h2>
                    <p className="text-xs opacity-75">
                      O gate de privacidade verifica o material antes de salvar para garantir ausência de dados pessoais de alunos ou termos clínicos.
                    </p>
                  </div>
                  {savedHistoryId && (
                    <Link
                      href="/historico"
                      className="inline-flex min-h-[44px] items-center gap-1.5 rounded-xl border border-[#335C67]/30 px-3 py-1.5 text-xs font-bold text-[#335C67] dark:text-[#9fd0de]"
                    >
                      <FolderClock className="w-3.5 h-3.5" aria-hidden />
                      <span>Ver em Minhas Atividades</span>
                    </Link>
                  )}
                </div>

                {!isAuthenticated ? (
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[#F5EDF0]/70 dark:bg-black/25 p-3.5 text-xs">
                    <span>Entre com sua conta (e-mail ou Google) para guardar esta atividade no seu histórico.</span>
                    <Link
                      href="/"
                      className="inline-flex min-h-[44px] items-center rounded-xl bg-[#C9411F] px-4 py-2 font-bold text-white"
                    >
                      Entrar / Criar conta
                    </Link>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                      <div>
                        <label htmlFor="hist-titulo" className="block text-xs font-bold mb-1">
                          Título da atividade
                        </label>
                        <input
                          id="hist-titulo"
                          type="text"
                          maxLength={120}
                          value={tituloHistorico}
                          onChange={(e) => setTituloHistorico(e.target.value)}
                          className="w-full min-h-[44px] rounded-xl border border-black/15 dark:border-white/15 bg-[#F5EDF0]/40 dark:bg-[#0D0221] px-3 text-sm"
                        />
                      </div>
                      <div>
                        <label htmlFor="hist-disciplina" className="block text-xs font-bold mb-1">
                          Disciplina (opcional)
                        </label>
                        <input
                          id="hist-disciplina"
                          type="text"
                          maxLength={80}
                          placeholder="Ex.: Ciências"
                          value={disciplinaHistorico}
                          onChange={(e) => setDisciplinaHistorico(e.target.value)}
                          className="w-full min-h-[44px] rounded-xl border border-black/15 dark:border-white/15 bg-[#F5EDF0]/40 dark:bg-[#0D0221] px-3 text-sm"
                        />
                      </div>
                      <div>
                        <label htmlFor="hist-ano" className="block text-xs font-bold mb-1">
                          Ano escolar (opcional)
                        </label>
                        <input
                          id="hist-ano"
                          type="text"
                          maxLength={60}
                          placeholder="Ex.: 7º ano"
                          value={anoHistorico}
                          onChange={(e) => setAnoHistorico(e.target.value)}
                          className="w-full min-h-[44px] rounded-xl border border-black/15 dark:border-white/15 bg-[#F5EDF0]/40 dark:bg-[#0D0221] px-3 text-sm"
                        />
                      </div>
                    </div>

                    {historicoErro && (
                      <div role="alert" className="rounded-xl border border-red-700/40 bg-red-50 dark:bg-red-950/40 p-3 text-xs text-red-900 dark:text-red-200 space-y-2">
                        <p className="flex items-center gap-1.5 font-semibold">
                          <ShieldAlert className="w-4 h-4 shrink-0" aria-hidden />
                          <span>{historicoErro}</span>
                        </p>
                        {precisaSanitizarPii && (
                          <button
                            type="button"
                            disabled={salvandoHistorico}
                            onClick={() => salvarNoHistorico(true)}
                            className="min-h-[44px] rounded-lg bg-[#C9411F] px-3 py-1.5 font-bold text-white"
                          >
                            Sanitizar dados pessoais e salvar
                          </button>
                        )}
                      </div>
                    )}

                    {historicoMsg && (
                      <p role="status" className="flex items-center gap-1.5 text-xs font-bold text-emerald-800 dark:text-emerald-300">
                        <CheckCircle2 className="w-4 h-4" aria-hidden />
                        <span>{historicoMsg}</span>
                      </p>
                    )}

                    <button
                      type="button"
                      disabled={salvandoHistorico}
                      onClick={() => salvarNoHistorico(false)}
                      className="inline-flex min-h-[44px] items-center gap-2 rounded-xl bg-[#335C67] hover:bg-[#274851] disabled:opacity-60 px-4 py-2 text-xs font-bold text-white"
                    >
                      {salvandoHistorico ? (
                        <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
                      ) : (
                        <BookmarkCheck className="w-4 h-4" aria-hidden />
                      )}
                      <span>{savedHistoryId ? "Atualizar no Meu Histórico" : "Salvar no Meu Histórico"}</span>
                    </button>
                  </div>
                )}
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
