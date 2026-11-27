"use client";

import React, { useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Bot,
  CheckCircle2,
  Cpu,
  FileCheck2,
  Loader2,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";

import { IrisHeader, STEP_TITLES } from "./IrisHeader";
import { IrisSidebar } from "./IrisSidebar";
import {
  AgentProviderOption,
  AgentsPrivacyStatus,
  fetchAgentsPrivacyStatus,
  fontesCitadas,
  loadStep4ResultFromSession,
  MultiAgentMaterialResponse,
  QuestionMultiAgentTrace,
  runMultiAgentAdaptation,
  saveStep5AdaptationToSession,
} from "@/services/agentsApi";
import {
  CharacteristicItem,
  FALLBACK_OFFICIAL_CATALOG,
  loadStep1StateFromSession,
  loadSurgicalSelectionFromSession,
} from "@/services/catalogsApi";
import { IrisApiError } from "@/services/materialsApi";
import { loadScaffoldingFromSession, ScaffoldingLevel } from "@/services/scaffoldingApi";

const EXEMPLO_MATERIAL_PADRAO =
  "Avaliação Diagnóstica — Ciências e Matemática\n\n" +
  "1. Leia o texto sobre a fotossíntese, identifique os reagentes absorvidos pelas plantas e explique como os cloroplastos produzem glicose e oxigênio.\n\n" +
  "2. Resolva a equação 2x + 6 = 14 e verifique se o valor encontrado está correto.";

const PROVIDER_LABELS: Record<AgentProviderOption, string> = {
  auto: "Automático (conforme política do servidor)",
  anthropic: "Anthropic Claude Haiku (API externa)",
  ollama: "Modelo Local (Ollama)",
  groq: "API Externa (Groq)",
  extractive: "Modo Rápido Determinístico (sem LLM externo)",
};

const EXTERNAL_PROVIDERS = new Set<AgentProviderOption>(["anthropic", "groq"]);

const DEFAULT_AVISO_EXTERNO =
  "Processamento com IA externa (Anthropic Claude): para melhorar a qualidade da adaptação, esta escola " +
  "habilitou o envio apenas do enunciado da questão (após remoção automática de nomes, CPFs, telefones e escolas), " +
  "da característica funcional selecionada e do nível de apoio (1 a 3). Nunca são enviados nome do estudante, " +
  "matrícula, laudo clínico ou código do Perfil Portátil. O Íris não grava prompts nem questões nos logs. " +
  "Não digite nomes de alunos no texto ou nas travas manuais. Para manter 100% local, escolha Modelo Local (Ollama) " +
  "ou Modo Determinístico.";

const DEFAULT_AVISO_LOCAL =
  "Processamento 100% local (Privacidade por Padrão): nenhum enunciado ou característica funcional sai desta " +
  "máquina. O envio a provedores externos está desativado nas configurações deste servidor.";

interface Step4AgentAdaptationProps {
  teacherEmail?: string;
}

export function Step4AgentAdaptation({
  teacherEmail,
}: Step4AgentAdaptationProps = {}) {
  const router = useRouter();

  const materialInputId = useId();
  const travaInputId = useId();
  const disciplinaInputId = useId();
  const anoInputId = useId();
  const providerSelectId = useId();
  const simulateId = useId();

  const [materialText, setMaterialText] = useState<string>("");
  const [materialTitle, setMaterialTitle] = useState<string>("Atividade Pedagógica Adaptada");
  const [usandoExemplo, setUsandoExemplo] = useState<boolean>(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([
    "sobrecarga_memoria_trabalho_comandos_multiplos",
  ]);
  const [nivel, setNivel] = useState<ScaffoldingLevel>(2);
  const [travaManualTexto, setTravaManualTexto] = useState<string>("");
  const [invariantesEtapa3, setInvariantesEtapa3] = useState<
    ReturnType<typeof loadScaffoldingFromSession> extends infer T
      ? T extends { invariantes_auditor?: infer I }
        ? I | null
        : null
      : null
  >(null);
  const [disciplina, setDisciplina] = useState<string>("");
  const [anoEscolar, setAnoEscolar] = useState<string>("");
  const [provider, setProvider] = useState<AgentProviderOption>("auto");
  const [privacyStatus, setPrivacyStatus] = useState<AgentsPrivacyStatus | null>(null);
  const [simularAutocorrecao, setSimularAutocorrecao] = useState<boolean>(false);

  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [result, setResult] = useState<MultiAgentMaterialResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    const step1 = loadStep1StateFromSession();
    if (step1 && step1.textContent && step1.textContent.trim().length >= 15) {
      setMaterialText(step1.textContent);
      setUsandoExemplo(false);
      if (step1.selectedFile?.name) {
        setMaterialTitle(step1.selectedFile.name.replace(/\.[^.]+$/, ""));
      }
    } else {
      setMaterialText(EXEMPLO_MATERIAL_PADRAO);
      setUsandoExemplo(true);
    }

    const surgical = loadSurgicalSelectionFromSession();
    if (surgical && Array.isArray(surgical.selected_ids) && surgical.selected_ids.length > 0) {
      setSelectedIds(surgical.selected_ids);
    }

    const scaffolding = loadScaffoldingFromSession();
    if (scaffolding && [1, 2, 3].includes(scaffolding.nivel)) {
      setNivel(scaffolding.nivel);
      if (scaffolding.invariantes_auditor) {
        setInvariantesEtapa3(scaffolding.invariantes_auditor);
      }
      const travasEtapa3 =
        scaffolding.invariantes_auditor?.conceitos_obrigatorios ||
        scaffolding.trava_curricular?.conceitos_obrigatorios ||
        [];
      if (travasEtapa3.length > 0) {
        setTravaManualTexto(travasEtapa3.join("; "));
      }
    }

    const savedStep4 = loadStep4ResultFromSession();
    if (savedStep4) {
      setResult(savedStep4);
    }

    let active = true;
    fetchAgentsPrivacyStatus().then((status) => {
      if (!active || !status) return;
      setPrivacyStatus(status);
      if (!status.external_adaptation_allowed) {
        setProvider((prev) => (EXTERNAL_PROVIDERS.has(prev) ? "auto" : prev));
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const externalDisabledByPolicy =
    privacyStatus !== null && !privacyStatus.external_adaptation_allowed;
  const willUseExternal =
    !externalDisabledByPolicy &&
    (EXTERNAL_PROVIDERS.has(provider) ||
      (provider === "auto" && Boolean(privacyStatus?.auto_uses_external_llm)));

  const catalogMap = new Map<string, CharacteristicItem>(
    FALLBACK_OFFICIAL_CATALOG.caracteristicas.map((c) => [c.id_caracteristica, c])
  );

  const handleRunPipeline = async (advanceAfter = false) => {
    setErrorMsg(null);
    setIsRunning(true);
    try {
      const separador = /[;\n]/.test(travaManualTexto) ? /[;\n]+/ : /[;\n,]+/;
      const travas = travaManualTexto
        .split(separador)
        .map((s) => s.trim())
        .filter(Boolean);

      const res = await runMultiAgentAdaptation({
        text: materialText,
        titulo: materialTitle,
        selected_ids: selectedIds,
        nivel,
        disciplina: disciplina.trim() || undefined,
        ano_escolar: anoEscolar.trim() || undefined,
        trava_manual_docente: travas.length > 0 ? travas : undefined,
        invariantes_etapa3: invariantesEtapa3 || undefined,
        provider,
        metodo_rag: "bm25",
        simular_autocorrecao: simularAutocorrecao,
      });
      setResult(res);
      if (advanceAfter && res.requerem_revisao_humana === 0) {
        saveStep5AdaptationToSession(res.etapa5_entrada);
        router.push("/etapa-5");
      }
    } catch (err) {
      if (err instanceof IrisApiError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg("Erro inesperado ao executar o Sistema Multiagentes.");
      }
    } finally {
      setIsRunning(false);
    }
  };

  const handleAdvanceToStep5 = () => {
    if (!result) return;
    saveStep5AdaptationToSession(result.etapa5_entrada);
    router.push("/etapa-5");
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F5EDF0] dark:bg-[#0D0221] text-[#0D0221] dark:text-[#F5EDF0] transition-colors">
      <IrisHeader currentStep={4} teacherEmail={teacherEmail} />

      <div className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 flex flex-col lg:flex-row gap-6">
        <IrisSidebar
          currentStep={4}
          enabledSteps={[1, 2, 3, 4, 5]}
          onNavigateHome={() => router.push("/")}
          onNavigateStep={(s) => router.push(`/etapa-${s}`)}
        />

        <main id="conteudo-principal" className="flex-1 min-w-0 space-y-6">
          {/* Painel de Parametrização e Execução */}
          <section
            aria-labelledby="titulo-etapa-4"
            className="p-5 sm:p-7 rounded-2xl bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 shadow-sm space-y-5"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="space-y-1.5">
                <div className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#B53319] dark:text-[#FF8A70]">
                  <span>{STEP_TITLES[4]}</span>
                </div>
                <h1
                  id="titulo-etapa-4"
                  className="text-xl sm:text-2xl font-black text-[#0D0221] dark:text-white tracking-tight"
                >
                  Motor Multiagentes com Isolamento de Escopo
                </h1>
                <p className="text-xs sm:text-sm text-[#0D0221]/75 dark:text-white/75">
                  Acompanhe os 4 agentes colaborando para extrair travas curriculares, recuperar evidências DUA/MEC, adaptar a apresentação e auditar a retenção (TRCC ≥ 95%).
                </p>
              </div>
              <span className="self-start px-3 py-1 rounded-full text-xs font-extrabold bg-[#335C67] text-white whitespace-nowrap">
                Nível {nivel} • {selectedIds.length} característica(s)
              </span>
            </div>

            {usandoExemplo && (
              <div
                role="note"
                className="flex items-start gap-2.5 p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-700/60 text-xs text-amber-950 dark:text-amber-100"
              >
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-700 dark:text-amber-300" aria-hidden="true" />
                <span>
                  Nenhum material veio da Etapa 1 nesta sessão; carregamos um exemplo com 2 questões para teste imediato (você pode editar o texto abaixo ou voltar à Etapa 1).
                </span>
              </div>
            )}

            {/* Características ativas */}
            <div className="flex flex-wrap gap-2">
              {selectedIds.map((id) => {
                const info = catalogMap.get(id);
                return (
                  <span
                    key={id}
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-semibold bg-[#F5EDF0] dark:bg-white/10 border border-[#335C67]/20 dark:border-white/10"
                  >
                    <ShieldCheck className="w-3.5 h-3.5 text-[#335C67] dark:text-[#9fd0de]" aria-hidden="true" />
                    <span>{info ? info.nome : id}</span>
                  </span>
                );
              })}
            </div>

            {/* Material + Travas manuais + Opções */}
            <div className="space-y-4">
              <div>
                <label htmlFor={materialInputId} className="block text-xs font-bold mb-1.5">
                  Material Pedagógico de Entrada (será sanitizado e decomposto em questões)
                </label>
                <textarea
                  id={materialInputId}
                  rows={5}
                  value={materialText}
                  onChange={(e) => setMaterialText(e.target.value)}
                  className="w-full rounded-xl border border-[#335C67]/30 dark:border-white/20 bg-[#F5EDF0]/40 dark:bg-[#0D0221]/70 px-3.5 py-2.5 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-[#E35336]"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="md:col-span-1">
                  <label htmlFor={disciplinaInputId} className="block text-xs font-bold mb-1">
                    Disciplina (opcional)
                  </label>
                  <input
                    id={disciplinaInputId}
                    type="text"
                    placeholder="Ex.: Ciências, Matemática"
                    value={disciplina}
                    onChange={(e) => setDisciplina(e.target.value)}
                    className="w-full min-h-[44px] rounded-xl border border-[#335C67]/30 dark:border-white/20 bg-[#F5EDF0]/40 dark:bg-[#0D0221]/70 px-3 text-xs focus:outline-none focus:ring-2 focus:ring-[#E35336]"
                  />
                </div>
                <div className="md:col-span-1">
                  <label htmlFor={anoInputId} className="block text-xs font-bold mb-1">
                    Ano / Etapa (opcional)
                  </label>
                  <input
                    id={anoInputId}
                    type="text"
                    placeholder="Ex.: 7º ano, Ensino Médio"
                    value={anoEscolar}
                    onChange={(e) => setAnoEscolar(e.target.value)}
                    className="w-full min-h-[44px] rounded-xl border border-[#335C67]/30 dark:border-white/20 bg-[#F5EDF0]/40 dark:bg-[#0D0221]/70 px-3 text-xs focus:outline-none focus:ring-2 focus:ring-[#E35336]"
                  />
                </div>
                <div className="md:col-span-1">
                  <label htmlFor={providerSelectId} className="block text-xs font-bold mb-1">
                    Provedor de IA
                  </label>
                  <select
                    id={providerSelectId}
                    value={provider}
                    onChange={(e) => setProvider(e.target.value as AgentProviderOption)}
                    className="w-full min-h-[44px] rounded-xl border border-[#335C67]/30 dark:border-white/20 bg-[#F5EDF0]/40 dark:bg-[#0D0221]/70 px-3 text-xs focus:outline-none focus:ring-2 focus:ring-[#E35336]"
                  >
                    {(Object.keys(PROVIDER_LABELS) as AgentProviderOption[]).map((opt) => {
                      const isExternalOpt = EXTERNAL_PROVIDERS.has(opt);
                      const disabled = externalDisabledByPolicy && isExternalOpt;
                      return (
                        <option key={opt} value={opt} disabled={disabled}>
                          {PROVIDER_LABELS[opt]}
                          {disabled ? " (desativado pela escola)" : ""}
                        </option>
                      );
                    })}
                  </select>
                </div>
              </div>

              <div>
                <label htmlFor={travaInputId} className="block text-xs font-bold mb-1">
                  Travas Curriculares Manuais do Professor (opcional — termos separados por vírgula)
                </label>
                <input
                  id={travaInputId}
                  type="text"
                  placeholder="Ex.: fotossíntese, cloroplastos, 2x + 6 = 14"
                  value={travaManualTexto}
                  onChange={(e) => setTravaManualTexto(e.target.value)}
                  className="w-full min-h-[44px] rounded-xl border border-[#335C67]/30 dark:border-white/20 bg-[#F5EDF0]/40 dark:bg-[#0D0221]/70 px-3 text-xs focus:outline-none focus:ring-2 focus:ring-[#E35336]"
                />
              </div>

              <label
                htmlFor={simulateId}
                className="flex items-start gap-2.5 p-3 rounded-xl bg-[#F5EDF0]/60 dark:bg-white/5 border border-[#335C67]/20 dark:border-white/10 cursor-pointer"
              >
                <input
                  id={simulateId}
                  type="checkbox"
                  checked={simularAutocorrecao}
                  onChange={(e) => setSimularAutocorrecao(e.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-[#E35336]"
                />
                <span className="text-xs leading-relaxed">
                  <strong>Demonstrar ciclo de auto-correção (Auditor ↔ Adaptador):</strong> simula uma falha curricular na 1ª tentativa para você visualizar o Agente Auditor reprovando, gerando feedback e o Agente Adaptador corrigindo na 2ª tentativa.
                </span>
              </label>
            </div>

            <div
              role="note"
              data-testid="aviso-privacidade-llm"
              className={`flex items-start gap-2.5 p-3.5 rounded-xl border text-xs leading-relaxed ${
                willUseExternal
                  ? "bg-amber-50 dark:bg-amber-950/40 border-amber-300 dark:border-amber-700/60 text-amber-950 dark:text-amber-100"
                  : "bg-emerald-50/80 dark:bg-emerald-950/30 border-emerald-300 dark:border-emerald-800/60 text-emerald-950 dark:text-emerald-100"
              }`}
            >
              {willUseExternal ? (
                <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5 text-amber-700 dark:text-amber-300" aria-hidden="true" />
              ) : (
                <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5 text-emerald-700 dark:text-emerald-300" aria-hidden="true" />
              )}
              <span>
                {willUseExternal
                  ? privacyStatus?.aviso_docente_externo || DEFAULT_AVISO_EXTERNO
                  : externalDisabledByPolicy
                  ? privacyStatus?.aviso_docente_local || DEFAULT_AVISO_LOCAL
                  : provider === "ollama" || provider === "extractive"
                  ? "Processamento 100% local selecionado: nenhum enunciado ou característica funcional sai desta máquina."
                  : privacyStatus?.aviso_docente_local || DEFAULT_AVISO_LOCAL}
              </span>
            </div>

            {errorMsg && (
              <div
                role="alert"
                className="p-4 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-300 dark:border-red-700 text-xs sm:text-sm text-red-950 dark:text-red-100 flex items-start gap-2.5"
              >
                <AlertCircle className="w-5 h-5 shrink-0 text-red-600 dark:text-red-400" aria-hidden="true" />
                <span>{errorMsg}</span>
              </div>
            )}

            <div className="pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => router.push("/etapa-3")}
                className="min-h-[44px] inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold bg-[#F5EDF0] dark:bg-white/10 hover:bg-[#335C67]/20 text-[#0D0221] dark:text-white transition-colors"
              >
                <ArrowLeft className="w-4 h-4" aria-hidden="true" />
                <span>Voltar para Etapa 3</span>
              </button>

              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  disabled={isRunning || materialText.trim().length < 15}
                  onClick={() => handleRunPipeline(false)}
                  className="min-h-[44px] inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl font-bold text-sm text-[#0D0221] dark:text-white bg-[#F5EDF0] dark:bg-white/10 hover:bg-[#335C67]/20 disabled:opacity-45 disabled:cursor-not-allowed transition-all"
                >
                  {isRunning ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                      <span>Executando os 4 Agentes...</span>
                    </>
                  ) : result ? (
                    <>
                      <RefreshCw className="w-4 h-4" aria-hidden="true" />
                      <span>Reexecutar Multiagentes</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" aria-hidden="true" />
                      <span>Executar Sistema Multiagentes</span>
                    </>
                  )}
                </button>

                <button
                  type="button"
                  disabled={isRunning || materialText.trim().length < 15}
                  onClick={() => (result ? handleAdvanceToStep5() : handleRunPipeline(true))}
                  className="min-h-[44px] inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-bold text-sm text-white bg-[#C9411F] hover:bg-[#ad3618] disabled:opacity-45 disabled:cursor-not-allowed shadow-md transition-all"
                >
                  {isRunning ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                      <span>Adaptando e avançando...</span>
                    </>
                  ) : result ? (
                    <>
                      <span>Avançar para Etapa 5 (Revisão)</span>
                      <ArrowRight className="w-4 h-4" aria-hidden="true" />
                    </>
                  ) : (
                    <>
                      <span>Adaptar e Ir para Etapa 5</span>
                      <ArrowRight className="w-4 h-4" aria-hidden="true" />
                    </>
                  )}
                </button>
              </div>
            </div>
          </section>

          {/* Painel de Resultado da Colaboração entre os 4 Agentes */}
          {result && (
            <section aria-live="polite" className="space-y-6">
              {/* Resumo Global da Execução */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-4 rounded-2xl bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15">
                  <p className="text-[11px] font-semibold opacity-70">Aprovação do Auditor</p>
                  <p className="text-lg font-black mt-0.5 text-emerald-700 dark:text-emerald-300">
                    {result.aprovadas_auditor} de {result.total_questoes}
                  </p>
                </div>
                <div className="p-4 rounded-2xl bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15">
                  <p className="text-[11px] font-semibold opacity-70">Provedor / Modelo</p>
                  <p className="text-xs font-mono font-bold mt-1 break-all">
                    {result.provider} / {result.model}
                  </p>
                  <p className="text-[11px] mt-1 font-semibold text-[#335C67] dark:text-[#9fd0de]">
                    {(result.usa_provedor_externo ?? (result.provider === "anthropic" || result.provider === "groq"))
                      ? "API externa (sanitizado)"
                      : "Processamento 100% local"}
                  </p>
                  {result.provedores_por_agente && Object.keys(result.provedores_por_agente).length > 0 && (
                    <p className="text-[10px] font-mono opacity-75 mt-0.5 break-all">
                      {Object.entries(result.provedores_por_agente)
                        .map(([ag, pv]) => `${ag}:${pv}`)
                        .join(" • ")}
                    </p>
                  )}
                </div>
                <div className="p-4 rounded-2xl bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15">
                  <p className="text-[11px] font-semibold opacity-70">Latência / Tokens</p>
                  <p className="text-sm font-bold mt-1">
                    {Math.round(result.total_ms)} ms • {result.total_tokens} tok
                  </p>
                </div>
                <div className="p-4 rounded-2xl bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15">
                  <p className="text-[11px] font-semibold opacity-70">PII Sanitizados</p>
                  <p className="text-lg font-black mt-0.5">{result.pii_substituicoes}</p>
                </div>
              </div>

              {result.questoes_trace.map((qTrace, index) => (
                <QuestionCollaborationCard key={qTrace.id} trace={qTrace} index={index} />
              ))}
            </section>
          )}
        </main>
      </div>
    </div>
  );
}

function QuestionCollaborationCard({
  trace,
  index,
}: {
  trace: QuestionMultiAgentTrace;
  index: number;
}) {
  const inv = trace.extrator.invariants;
  const est = trace.estrategista;

  return (
    <article className="p-5 sm:p-6 rounded-2xl bg-white dark:bg-[#160A30] border border-[#335C67]/25 dark:border-white/15 shadow-sm space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3 pb-4 border-b border-[#335C67]/15 dark:border-white/10">
        <div>
          <p className="text-xs font-extrabold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de]">
            Questão {index + 1} (Ref. {trace.numero_original})
          </p>
          <p className="text-sm font-medium mt-1 whitespace-pre-wrap">{trace.original}</p>
        </div>

        <span
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-extrabold ${
            trace.aprovado_final
              ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/50 dark:text-emerald-200"
              : "bg-amber-100 text-amber-900 dark:bg-amber-900/50 dark:text-amber-200"
          }`}
        >
          {trace.aprovado_final ? (
            <>
              <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
              <span>Aprovada ({trace.tentativas.length} tentativa{trace.tentativas.length > 1 ? "s" : ""})</span>
            </>
          ) : (
            <>
              <ShieldAlert className="w-4 h-4" aria-hidden="true" />
              <span>Requer Revisão Humana</span>
            </>
          )}
        </span>
      </div>

      {/* Grid dos 4 Agentes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Agente 1: Extrator Curricular */}
        <div className="p-4 rounded-xl bg-[#F5EDF0]/50 dark:bg-white/5 border border-[#335C67]/15 dark:border-white/10 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-xs font-extrabold uppercase tracking-wider flex items-center gap-1.5 text-[#335C67] dark:text-[#9fd0de]">
              <Cpu className="w-4 h-4" aria-hidden="true" />
              <span>1. Agente Extrator Curricular (#17)</span>
            </h2>
            <span className="text-[11px] font-mono opacity-70">
              {Math.round(trace.extrator.telemetry.total_ms)} ms
            </span>
          </div>
          <p className="text-xs">
            <strong>Verbo BNCC:</strong>{" "}
            <span className="font-mono font-bold text-[#C9411F] dark:text-[#FF8A70]">
              {inv.verbo_comando_bncc}
            </span>
            {inv.habilidade_bncc_sugerida && ` • ${inv.habilidade_bncc_sugerida}`}
          </p>
          <p className="text-xs opacity-90">
            <strong>Operação:</strong> {inv.operacao_cognitiva}
          </p>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {inv.conceitos_obrigatorios.map((c) => (
              <span
                key={c}
                className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-white dark:bg-[#0D0221] border border-[#335C67]/25"
              >
                {c}
              </span>
            ))}
          </div>
          {inv.alerta_anti_muleta && (
            <p className="text-[11px] text-amber-900 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 px-2.5 py-1.5 rounded-lg">
              <strong>Anti-muleta:</strong> {inv.alerta_anti_muleta}
            </p>
          )}
        </div>

        {/* Agente 2: Estrategista RAG */}
        <div className="p-4 rounded-xl bg-[#F5EDF0]/50 dark:bg-white/5 border border-[#335C67]/15 dark:border-white/10 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-xs font-extrabold uppercase tracking-wider flex items-center gap-1.5 text-[#335C67] dark:text-[#9fd0de]">
              <BookOpen className="w-4 h-4" aria-hidden="true" />
              <span>2. Agente Estrategista RAG (#16)</span>
            </h2>
            <span className="text-[11px] font-mono opacity-70">
              {est.telemetry.metodo_efetivo} • {est.fontes.length} fontes
            </span>
          </div>
          {est.diretiva ? (
            <p className="text-xs whitespace-pre-wrap leading-relaxed">{est.diretiva}</p>
          ) : (
            <p className="text-xs italic opacity-75">Nenhuma evidência recuperada para o filtro.</p>
          )}
          {fontesCitadas(est).length > 0 && (
            <div className="pt-1 space-y-1" data-testid="fontes-citadas">
              <p className="text-[11px] font-bold opacity-80">Fontes científicas citadas:</p>
              <ul className="space-y-1 text-[11px] opacity-85">
                {fontesCitadas(est).map((f) => (
                  <li key={`${f.rotulo}-${f.chunk_id}`} className="truncate">
                    <span className="font-mono font-bold">[{f.rotulo}]</span> {f.referencia}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Agente 3: Adaptador Pedagógico */}
        <div className="p-4 rounded-xl bg-[#F5EDF0]/50 dark:bg-white/5 border border-[#335C67]/15 dark:border-white/10 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-xs font-extrabold uppercase tracking-wider flex items-center gap-1.5 text-[#335C67] dark:text-[#9fd0de]">
              <Sparkles className="w-4 h-4" aria-hidden="true" />
              <span>3. Agente Adaptador (#18)</span>
            </h2>
            <span className="text-[11px] font-mono opacity-70">
              {trace.adaptacao_aplicada ? "Adaptado" : "Original mantido"}
            </span>
          </div>
          <pre className="text-xs whitespace-pre-wrap font-sans bg-white dark:bg-[#0D0221] p-3 rounded-lg border border-black/10 dark:border-white/10 leading-relaxed">
            {trace.adaptado}
          </pre>
          {trace.justificativas.length > 0 && (
            <ul className="list-disc list-inside text-[11px] space-y-0.5 opacity-85">
              {trace.justificativas.map((j, idx) => (
                <li key={idx}>{j}</li>
              ))}
            </ul>
          )}
          {trace.recomendacao_docente && (
            <p className="text-[11px] p-2 rounded-lg border border-[#335C67]/30 dark:border-white/20" data-testid="recomendacao-docente">
              <span className="font-bold">Para o docente (não vai para a prova): </span>
              {trace.recomendacao_docente}
            </p>
          )}
        </div>

        {/* Agente 4: Auditor de Integridade & Auto-correção */}
        <div className="p-4 rounded-xl bg-[#F5EDF0]/50 dark:bg-white/5 border border-[#335C67]/15 dark:border-white/10 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-xs font-extrabold uppercase tracking-wider flex items-center gap-1.5 text-[#335C67] dark:text-[#9fd0de]">
              <FileCheck2 className="w-4 h-4" aria-hidden="true" />
              <span>4. Agente Auditor (#19)</span>
            </h2>
            <span className="text-[11px] font-mono opacity-70">
              Ciclo: {Math.round(trace.ciclo_resumo.total_ms)} ms
            </span>
          </div>

          <ol className="space-y-2.5">
            {trace.tentativas.map((t) => (
              <li
                key={t.tentativa}
                className={`p-3 rounded-lg border text-xs space-y-1.5 ${
                  t.aprovado_auditor
                    ? "bg-emerald-50/70 dark:bg-emerald-950/30 border-emerald-300 dark:border-emerald-800/60"
                    : "bg-red-50/70 dark:bg-red-950/30 border-red-300 dark:border-red-800/60"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold flex items-center gap-1.5">
                    {t.aprovado_auditor ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-700 dark:text-emerald-300" aria-hidden="true" />
                    ) : (
                      <Wrench className="w-3.5 h-3.5 text-red-700 dark:text-red-300" aria-hidden="true" />
                    )}
                    Tentativa {t.tentativa}: {t.aprovado_auditor ? "Aprovada" : "Reprovada"}
                  </span>
                  <span className="font-mono text-[11px]">
                    TRCC: {t.trcc !== null ? `${Math.round(t.trcc * 100)}%` : "N/A"} • Escopo:{" "}
                    {t.escopo_aprovado ? "OK" : "Violado"}
                  </span>
                </div>

                {!t.aprovado_auditor && t.motivos_auditor.length > 0 && (
                  <p className="text-[11px] opacity-90">
                    <strong>Motivo:</strong> {t.motivos_auditor.join("; ")}
                  </p>
                )}

                {!t.aprovado_auditor && (
                  <details className="text-[11px] bg-white/60 dark:bg-black/20 rounded p-2">
                    <summary className="cursor-pointer font-semibold">
                      Ver minuta reprovada (Tentativa {t.tentativa})
                    </summary>
                    <pre className="mt-1.5 whitespace-pre-wrap font-sans opacity-90">{t.texto_minuta}</pre>
                  </details>
                )}

                {t.feedback_gerado && (
                  <p className="text-[11px] bg-white/80 dark:bg-black/30 p-2 rounded border border-red-200 dark:border-red-800/50">
                    <Bot className="w-3 h-3 inline mr-1" aria-hidden="true" />
                    <strong>Feedback enviado ao Adaptador:</strong> {t.feedback_gerado}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </article>
  );
}
