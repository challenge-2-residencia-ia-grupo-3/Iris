"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Contrast,
  Copy,
  Download,
  ExternalLink,
  FilePlus2,
  FolderClock,
  Loader2,
  LogIn,
  Moon,
  Search,
  Sun,
  Trash2,
} from "lucide-react";
import { IrisLogoBanner } from "@/components/IrisLogoBanner";
import { IrisSidebar } from "@/components/IrisSidebar";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import {
  type ActivityStatus,
  type HistoryActivitySummary,
  HistoryApiError,
  deleteHistoryActivity,
  downloadHistoryActivity,
  duplicateHistoryActivity,
  listHistoryActivities,
} from "@/services/historyApi";

export default function HistoricoPage() {
  const router = useRouter();
  const { darkMode, toggleDarkMode, highContrast, toggleHighContrast } = useTheme();
  const { teacher, isAuthenticated, isLoading: authLoading, deleteMyAccount } = useAuth();

  const [items, setItems] = useState<HistoryActivitySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const [busca, setBusca] = useState("");
  const [filtroNivel, setFiltroNivel] = useState<string>("");
  const [filtroStatus, setFiltroStatus] = useState<ActivityStatus | "">("");

  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmDeleteAccount, setConfirmDeleteAccount] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    setErro(null);
    try {
      const res = await listHistoryActivities({
        q: busca,
        nivel_andaime: filtroNivel ? Number(filtroNivel) : null,
        status: filtroStatus,
        limit: 50,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      setErro(e instanceof HistoryApiError ? e.message : "Não foi possível carregar seu histórico.");
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, busca, filtroNivel, filtroStatus]);

  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      carregar();
    }
  }, [authLoading, isAuthenticated, carregar]);

  const handleDuplicate = async (id: string) => {
    setBusyId(id);
    setErro(null);
    setFeedback(null);
    try {
      await duplicateHistoryActivity(id);
      setFeedback("Cópia criada como rascunho no seu histórico.");
      await carregar();
    } catch (e) {
      setErro(e instanceof HistoryApiError ? e.message : "Não foi possível duplicar a atividade.");
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (id: string) => {
    setBusyId(id);
    setErro(null);
    setFeedback(null);
    try {
      await deleteHistoryActivity(id);
      setConfirmDeleteId(null);
      setFeedback("Atividade excluída permanentemente.");
      await carregar();
    } catch (e) {
      setErro(e instanceof HistoryApiError ? e.message : "Não foi possível excluir a atividade.");
    } finally {
      setBusyId(null);
    }
  };

  const handleExport = async (item: HistoryActivitySummary, formato: "pdf" | "docx") => {
    setBusyId(item.id);
    setErro(null);
    try {
      await downloadHistoryActivity(item.id, formato, item.titulo);
    } catch (e) {
      setErro(e instanceof HistoryApiError ? e.message : "Não foi possível exportar a atividade.");
    } finally {
      setBusyId(null);
    }
  };

  const handleDeleteAccount = async () => {
    try {
      await deleteMyAccount();
      router.push("/");
    } catch {
      setErro("Não foi possível excluir sua conta no momento.");
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#F5EDF0] text-[#0D0221] dark:bg-[#0D0221] dark:text-[#F5EDF0]">
      <header className="w-full border-b border-white/10 bg-[#0D0221] px-4 py-3.5 text-white sm:px-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <IrisLogoBanner compact />
            <p className="text-xs font-semibold uppercase tracking-wider text-[#FF8A70]">
              Minhas Atividades • Histórico Docente
            </p>
          </div>
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={toggleHighContrast}
              aria-pressed={highContrast}
              aria-label="Alternar modo de alto contraste"
              title="Alternar modo de alto contraste (WCAG 2.1 AA)"
              className={`inline-flex min-h-[44px] items-center justify-center gap-1.5 px-3 rounded-lg text-xs font-semibold border transition-colors ${
                highContrast
                  ? "bg-white text-[#0D0221] border-white"
                  : "bg-white/10 hover:bg-white/20 text-white border-white/15"
              }`}
            >
              <Contrast
                className={`w-4 h-4 ${highContrast ? "text-[#0D0221]" : "text-[#FF8A70]"}`}
                aria-hidden="true"
              />
              <span className="hidden sm:inline leading-none">Alto Contraste</span>
            </button>
            <button
              type="button"
              onClick={toggleDarkMode}
              aria-label={darkMode ? "Ativar modo claro" : "Ativar modo escuro"}
              className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg border border-white/20 bg-white/10 text-white hover:bg-white/20"
            >
              {darkMode ? <Sun className="h-4 w-4" aria-hidden /> : <Moon className="h-4 w-4" aria-hidden />}
            </button>
            <Link
              href="/etapa-1"
              className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-[#C9411F] px-3.5 py-2 text-xs font-bold text-white hover:bg-[#b23618]"
            >
              <FilePlus2 className="h-4 w-4" aria-hidden />
              <span>Nova Adaptação</span>
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col items-start gap-6 px-4 py-6 sm:px-8 lg:flex-row">
        <IrisSidebar
          currentStep={0}
          currentPage="historico"
          enabledSteps={[1, 2, 3, 4, 5]}
          onNavigateStep={(s) => router.push(`/etapa-${s}`)}
        />

        <main id="conteudo-principal" className="min-w-0 flex-1 space-y-5 w-full">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-extrabold flex items-center gap-2">
                <FolderClock className="w-6 h-6 text-[#C9411F]" aria-hidden />
                <span>Histórico de Atividades Adaptadas</span>
              </h1>
              <p className="text-sm text-[#0D0221]/80 dark:text-[#F5EDF0]/80 mt-1">
                Apenas materiais pedagógicos sanitizados ficam salvos na sua conta. Nenhum dado de estudante é armazenado.
              </p>
            </div>
          </div>

          {authLoading ? (
            <div role="status" className="flex items-center gap-2 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
              <span>Verificando sessão docente…</span>
            </div>
          ) : !isAuthenticated || !teacher ? (
            <section className="rounded-2xl border border-[#335C67]/25 bg-white dark:bg-[#160A30] p-6 space-y-4 shadow-sm">
              <h2 className="text-lg font-extrabold">Você está no Modo Convidado</h2>
              <p className="text-sm text-[#0D0221]/80 dark:text-white/80">
                No Modo Convidado nenhuma atividade é salva em banco de dados. Entre ou crie uma conta (e-mail ou Google) para salvar, editar e baixar novamente suas atividades.
              </p>
              <div className="flex flex-wrap gap-3">
                <Link
                  href="/"
                  className="inline-flex min-h-[44px] items-center gap-2 rounded-xl bg-[#C9411F] px-5 py-2.5 text-xs font-bold text-white hover:bg-[#b23618]"
                >
                  <LogIn className="w-4 h-4" aria-hidden />
                  <span>Entrar ou criar conta</span>
                </Link>
                <Link
                  href="/etapa-1"
                  className="inline-flex min-h-[44px] items-center gap-2 rounded-xl border border-[#335C67]/30 px-5 py-2.5 text-xs font-bold"
                >
                  <span>Continuar no Modo Convidado</span>
                </Link>
              </div>
            </section>
          ) : (
            <>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  carregar();
                }}
                className="grid grid-cols-1 gap-3 rounded-2xl border border-[#335C67]/20 bg-white dark:bg-[#160A30] p-4 sm:grid-cols-4 shadow-sm"
              >
                <div className="sm:col-span-2 relative flex items-center">
                  <Search className="w-4 h-4 absolute left-3 opacity-50 pointer-events-none" aria-hidden />
                  <input
                    type="search"
                    aria-label="Buscar por título da atividade"
                    placeholder="Buscar por título…"
                    value={busca}
                    onChange={(e) => setBusca(e.target.value)}
                    className="w-full min-h-[44px] pl-9 pr-3 rounded-xl border border-black/15 dark:border-white/15 bg-[#F5EDF0]/40 dark:bg-[#0D0221] text-sm"
                  />
                </div>
                <select
                  aria-label="Filtrar por nível de andaime"
                  value={filtroNivel}
                  onChange={(e) => setFiltroNivel(e.target.value)}
                  className="min-h-[44px] rounded-xl border border-black/15 dark:border-white/15 bg-[#F5EDF0]/40 dark:bg-[#0D0221] px-3 text-sm"
                >
                  <option value="">Todos os níveis</option>
                  <option value="1">Nível 1 (Leve)</option>
                  <option value="2">Nível 2 (Moderado)</option>
                  <option value="3">Nível 3 (Intensivo)</option>
                </select>
                <select
                  aria-label="Filtrar por status"
                  value={filtroStatus}
                  onChange={(e) => setFiltroStatus(e.target.value as ActivityStatus | "")}
                  className="min-h-[44px] rounded-xl border border-black/15 dark:border-white/15 bg-[#F5EDF0]/40 dark:bg-[#0D0221] px-3 text-sm"
                >
                  <option value="">Todos os status</option>
                  <option value="homologada">Homologadas</option>
                  <option value="rascunho">Rascunhos</option>
                </select>
              </form>

              {erro && (
                <div role="alert" className="rounded-xl border border-red-700/40 bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm text-red-900 dark:text-red-200">
                  {erro}
                </div>
              )}
              {feedback && (
                <div role="status" className="rounded-xl border border-emerald-700/40 bg-emerald-50 dark:bg-emerald-950/40 px-4 py-3 text-sm text-emerald-900 dark:text-emerald-200">
                  {feedback}
                </div>
              )}

              {loading ? (
                <div role="status" className="flex items-center gap-2 text-sm">
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
                  <span>Carregando atividades…</span>
                </div>
              ) : items.length === 0 ? (
                <div className="rounded-2xl border border-[#335C67]/20 bg-white dark:bg-[#160A30] p-6 text-sm space-y-3">
                  <p className="font-semibold">Nenhuma atividade encontrada no seu histórico ainda.</p>
                  <p className="opacity-80">
                    Conclua uma adaptação na Etapa 5 e clique em <strong>Salvar no Meu Histórico</strong> para guardá-la aqui.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-xs font-semibold opacity-75">{total} atividade(s) encontrada(s)</p>
                  <ul className="space-y-3">
                    {items.map((item) => {
                      const isBusy = busyId === item.id;
                      const homologada = item.status === "homologada";
                      return (
                        <li
                          key={item.id}
                          className="rounded-2xl border border-[#335C67]/20 bg-white dark:bg-[#160A30] p-4 shadow-sm space-y-3"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="space-y-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <h2 className="text-base font-extrabold break-words">{item.titulo}</h2>
                                <span
                                  className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                                    homologada
                                      ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200"
                                      : "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200"
                                  }`}
                                >
                                  {homologada ? "Homologada" : "Rascunho"}
                                </span>
                                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-[#335C67]/15 text-[#335C67] dark:text-[#9fd0de]">
                                  Nível {item.nivel_andaime}
                                </span>
                              </div>
                              <p className="text-xs opacity-75">
                                {item.disciplina ? `${item.disciplina} • ` : ""}
                                {item.ano_escolar ? `${item.ano_escolar} • ` : ""}
                                {item.total_questoes} questão(ões) • Atualizada em{" "}
                                {new Date(item.atualizado_em).toLocaleString("pt-BR")}
                              </p>
                            </div>

                            <div className="flex flex-wrap items-center gap-2">
                              <Link
                                href={`/etapa-5?historyId=${encodeURIComponent(item.id)}`}
                                className="inline-flex min-h-[44px] items-center gap-1.5 rounded-xl bg-[#335C67] px-3 py-2 text-xs font-bold text-white hover:bg-[#274851]"
                              >
                                <ExternalLink className="w-3.5 h-3.5" aria-hidden />
                                <span>Revisar / Editar</span>
                              </Link>
                              <button
                                type="button"
                                disabled={isBusy}
                                onClick={() => handleDuplicate(item.id)}
                                className="inline-flex min-h-[44px] items-center gap-1.5 rounded-xl border border-black/15 dark:border-white/20 px-3 py-2 text-xs font-bold hover:bg-black/5 dark:hover:bg-white/10"
                              >
                                <Copy className="w-3.5 h-3.5" aria-hidden />
                                <span>Duplicar</span>
                              </button>
                              <button
                                type="button"
                                disabled={isBusy || !homologada}
                                title={homologada ? "Baixar PDF" : "Homologue na Etapa 5 para liberar o download"}
                                onClick={() => handleExport(item, "pdf")}
                                className="inline-flex min-h-[44px] items-center gap-1 rounded-xl border border-black/15 dark:border-white/20 px-3 py-2 text-xs font-bold disabled:opacity-45"
                              >
                                <Download className="w-3.5 h-3.5" aria-hidden />
                                <span>PDF</span>
                              </button>
                              <button
                                type="button"
                                disabled={isBusy || !homologada}
                                title={homologada ? "Baixar DOCX" : "Homologue na Etapa 5 para liberar o download"}
                                onClick={() => handleExport(item, "docx")}
                                className="inline-flex min-h-[44px] items-center gap-1 rounded-xl border border-black/15 dark:border-white/20 px-3 py-2 text-xs font-bold disabled:opacity-45"
                              >
                                <Download className="w-3.5 h-3.5" aria-hidden />
                                <span>DOCX</span>
                              </button>
                              {confirmDeleteId === item.id ? (
                                <div className="flex items-center gap-1.5">
                                  <button
                                    type="button"
                                    disabled={isBusy}
                                    onClick={() => handleDelete(item.id)}
                                    className="min-h-[44px] rounded-xl bg-red-700 px-3 py-2 text-xs font-bold text-white"
                                  >
                                    Confirmar exclusão
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setConfirmDeleteId(null)}
                                    className="min-h-[44px] rounded-xl border border-black/15 px-3 py-2 text-xs font-semibold"
                                  >
                                    Cancelar
                                  </button>
                                </div>
                              ) : (
                                <button
                                  type="button"
                                  aria-label={`Excluir atividade ${item.titulo}`}
                                  onClick={() => setConfirmDeleteId(item.id)}
                                  className="inline-flex min-h-[44px] items-center gap-1 rounded-xl border border-red-700/30 px-3 py-2 text-xs font-bold text-red-800 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-950/30"
                                >
                                  <Trash2 className="w-3.5 h-3.5" aria-hidden />
                                  <span>Excluir</span>
                                </button>
                              )}
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              <section className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/60 dark:bg-[#160A30]/70 p-4 flex flex-wrap items-center justify-between gap-3">
                <div className="text-xs opacity-80">
                  <strong>Privacidade LGPD:</strong> você pode apagar sua conta docente e todo o histórico salvo a qualquer momento.
                </div>
                {confirmDeleteAccount ? (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleDeleteAccount}
                      className="min-h-[44px] rounded-xl bg-red-700 px-3.5 py-2 text-xs font-bold text-white"
                    >
                      Confirmar exclusão da conta
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmDeleteAccount(false)}
                      className="min-h-[44px] rounded-xl border border-black/15 px-3 py-2 text-xs font-semibold"
                    >
                      Cancelar
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmDeleteAccount(true)}
                    className="min-h-[44px] rounded-xl border border-red-700/30 px-3.5 py-2 text-xs font-bold text-red-800 dark:text-red-300"
                  >
                    Excluir minha conta e histórico
                  </button>
                )}
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
