"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Eye,
  EyeOff,
  FolderClock,
  Loader2,
  Lock,
  Mail,
  Moon,
  Sun,
  User,
} from "lucide-react";
import { IrisLogoBanner } from "@/components/IrisLogoBanner";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import { AuthApiError, buildGoogleOAuthStartUrl } from "@/services/authApi";

type AuthMode = "login" | "register";

export default function HomePage() {
  const router = useRouter();
  const { darkMode, toggleDarkMode } = useTheme();
  const { teacher, isAuthenticated, isLoading, providers, login, register, logout } = useAuth();

  const [mode, setMode] = useState<AuthMode>("login");
  const [nomeExibicao, setNomeExibicao] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSubmitting(true);
    try {
      if (mode === "register") {
        await register(email, nomeExibicao, password);
      } else {
        await login(email, password);
      }
      router.push("/historico");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg("Não foi possível falar com o servidor. Você pode continuar no Modo Convidado.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = buildGoogleOAuthStartUrl("/historico");
  };

  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-[#F5EDF0] dark:bg-[#0D0221] text-[#0D0221] dark:text-[#F5EDF0]">
      <aside className="relative flex flex-col justify-between bg-[#0D0221] text-white p-8 sm:p-14 overflow-hidden min-h-[420px] lg:min-h-screen">
        <div className="relative z-10 pt-6 sm:pt-10">
          <IrisLogoBanner />
        </div>

        <div className="relative z-10 max-w-lg space-y-4 my-auto lg:my-0 pt-12 mb-28 sm:mb-28">
          <p className="text-xs font-bold tracking-[0.14em] uppercase text-[#E35336]">
            Plataforma Gratuita para Professores
          </p>
          <h1 className="text-3xl sm:text-5xl font-bold leading-[1.15] tracking-tight text-white">
            Adapte materiais. Amplie as formas de aprender.
          </h1>
          <p className="text-sm text-white/75 leading-relaxed">
            Salve suas atividades adaptadas no histórico da sua conta sem guardar dados pessoais ou clínicos de estudantes.
          </p>
        </div>

        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-28 -right-24 w-[380px] h-[380px] rounded-full border border-[#E35336]/45 bg-gradient-to-tr from-[#0D0221] via-[#162736]/80 to-[#335C67]/35 shadow-2xl"
        />
      </aside>

      <main
        id="conteudo-principal"
        className="relative flex flex-col justify-center items-center p-8 sm:p-14 bg-[#F5EDF0] dark:bg-[#14072E]"
      >
        <div className="absolute top-6 right-6 flex items-center">
          <button
            type="button"
            onClick={toggleDarkMode}
            aria-label={darkMode ? "Ativar modo claro" : "Ativar modo escuro"}
            className="p-2.5 rounded-full text-[#0D0221] dark:text-white hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
          >
            {darkMode ? <Sun className="w-5 h-5 text-[#E35336]" /> : <Moon className="w-5 h-5" />}
          </button>
        </div>

        <div className="w-full max-w-[430px] space-y-6">
          {!isLoading && isAuthenticated && teacher ? (
            <div className="rounded-2xl bg-white dark:bg-[#0D0221] border border-[#335C67]/25 dark:border-white/15 p-6 shadow-sm space-y-5">
              <div className="space-y-1">
                <p className="text-xs font-extrabold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de]">
                  Sessão ativa
                </p>
                <h2 className="text-2xl font-extrabold text-[#0D0221] dark:text-white">
                  Olá, {teacher.nome_exibicao}
                </h2>
                <p className="text-xs text-[#0D0221]/70 dark:text-white/70">{teacher.email}</p>
              </div>

              <div className="space-y-3">
                <Link
                  href="/etapa-1"
                  className="w-full min-h-[44px] py-3 px-5 rounded-xl bg-[#C9411F] hover:bg-[#b23618] text-white font-bold text-sm flex items-center justify-center gap-2 transition-colors"
                >
                  <span>Nova Adaptação (Etapa 1)</span>
                  <ArrowRight className="w-4 h-4" aria-hidden="true" />
                </Link>
                <Link
                  href="/historico"
                  className="w-full min-h-[44px] py-3 px-5 rounded-xl bg-[#335C67] hover:bg-[#274851] text-white font-bold text-sm flex items-center justify-center gap-2 transition-colors"
                >
                  <FolderClock className="w-4 h-4" aria-hidden="true" />
                  <span>Minhas Atividades</span>
                </Link>
                <button
                  type="button"
                  onClick={() => logout()}
                  className="w-full min-h-[44px] py-2.5 px-4 rounded-xl border border-black/15 dark:border-white/20 text-xs font-bold text-[#0D0221] dark:text-white hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
                >
                  Sair e trocar de conta
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <h2 className="text-3xl font-extrabold tracking-tight text-[#0D0221] dark:text-white">
                  {mode === "login" ? "Acesse sua conta" : "Crie sua conta docente"}
                </h2>
                <p className="text-xs text-[#0D0221]/75 dark:text-white/75">
                  Guarde seu histórico de atividades adaptadas para editar, duplicar ou exportar novamente quando precisar.
                </p>
              </div>

              <div
                role="tablist"
                aria-label="Modo de acesso"
                className="grid grid-cols-2 gap-1 p-1 rounded-xl bg-black/5 dark:bg-white/10"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === "login"}
                  onClick={() => {
                    setMode("login");
                    setErrorMsg(null);
                  }}
                  className={`min-h-[40px] rounded-lg text-xs font-bold transition-colors ${
                    mode === "login"
                      ? "bg-white dark:bg-[#0D0221] text-[#0D0221] dark:text-white shadow-sm"
                      : "text-[#0D0221]/70 dark:text-white/70 hover:text-[#0D0221] dark:hover:text-white"
                  }`}
                >
                  Entrar
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === "register"}
                  onClick={() => {
                    setMode("register");
                    setErrorMsg(null);
                  }}
                  className={`min-h-[40px] rounded-lg text-xs font-bold transition-colors ${
                    mode === "register"
                      ? "bg-white dark:bg-[#0D0221] text-[#0D0221] dark:text-white shadow-sm"
                      : "text-[#0D0221]/70 dark:text-white/70 hover:text-[#0D0221] dark:hover:text-white"
                  }`}
                >
                  Criar conta
                </button>
              </div>

              {errorMsg && (
                <div
                  role="alert"
                  className="rounded-xl border border-red-700/40 bg-red-50 dark:bg-red-950/40 px-4 py-3 text-xs font-semibold text-red-900 dark:text-red-200"
                >
                  {errorMsg}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                {mode === "register" && (
                  <div className="space-y-1.5">
                    <label htmlFor="register-name" className="block text-xs font-bold text-[#0D0221] dark:text-white">
                      Nome de exibição
                    </label>
                    <div className="relative flex items-center">
                      <User
                        className="w-4 h-4 text-[#0D0221]/45 dark:text-white/50 absolute left-4 pointer-events-none"
                        aria-hidden="true"
                      />
                      <input
                        id="register-name"
                        type="text"
                        required
                        minLength={2}
                        maxLength={100}
                        placeholder="Ex.: Profa. Marina Alves"
                        value={nomeExibicao}
                        onChange={(e) => setNomeExibicao(e.target.value)}
                        className="w-full pl-11 pr-4 py-3 rounded-xl bg-white dark:bg-[#0D0221] border border-black/10 dark:border-white/15 text-sm text-[#0D0221] dark:text-white shadow-sm focus:border-[#E35336] transition-colors"
                      />
                    </div>
                  </div>
                )}

                <div className="space-y-1.5">
                  <label htmlFor="login-email" className="block text-xs font-bold text-[#0D0221] dark:text-white">
                    E-mail
                  </label>
                  <div className="relative flex items-center">
                    <Mail
                      className="w-4 h-4 text-[#0D0221]/45 dark:text-white/50 absolute left-4 pointer-events-none"
                      aria-hidden="true"
                    />
                    <input
                      id="login-email"
                      type="email"
                      required
                      placeholder="professora@escola.edu.br"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="w-full pl-11 pr-4 py-3 rounded-xl bg-white dark:bg-[#0D0221] border border-black/10 dark:border-white/15 text-sm text-[#0D0221] dark:text-white shadow-sm focus:border-[#E35336] transition-colors"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="login-password" className="block text-xs font-bold text-[#0D0221] dark:text-white">
                    Senha {mode === "register" && <span className="font-normal opacity-75">(mínimo 8 caracteres)</span>}
                  </label>
                  <div className="relative flex items-center">
                    <Lock
                      className="w-4 h-4 text-[#0D0221]/45 dark:text-white/50 absolute left-4 pointer-events-none"
                      aria-hidden="true"
                    />
                    <input
                      id="login-password"
                      type={showPassword ? "text" : "password"}
                      required
                      minLength={mode === "register" ? 8 : 1}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full pl-11 pr-11 py-3 rounded-xl bg-white dark:bg-[#0D0221] border border-black/10 dark:border-white/15 text-sm text-[#0D0221] dark:text-white shadow-sm focus:border-[#E35336] transition-colors"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((prev) => !prev)}
                      aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                      className="absolute right-3.5 p-1 text-[#0D0221]/50 dark:text-white/60 hover:text-[#0D0221] dark:hover:text-white"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full min-h-[46px] py-3.5 px-6 rounded-xl bg-[#C9411F] hover:bg-[#b23618] disabled:opacity-60 text-white font-bold text-sm flex items-center justify-center gap-2 shadow-[0_10px_25px_-5px_rgba(201,65,31,0.45)] transition-all"
                >
                  {submitting ? (
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <>
                      <span>{mode === "login" ? "Entrar" : "Criar conta"}</span>
                      <ArrowRight className="w-4 h-4" aria-hidden="true" />
                    </>
                  )}
                </button>
              </form>

              <div className="relative flex items-center py-1">
                <div className="flex-grow border-t border-black/10 dark:border-white/15" />
                <span className="mx-3 text-[11px] font-semibold uppercase tracking-wider text-[#0D0221]/50 dark:text-white/50">
                  ou
                </span>
                <div className="flex-grow border-t border-black/10 dark:border-white/15" />
              </div>

              <div className="space-y-2">
                <button
                  type="button"
                  disabled={!providers.google_enabled}
                  onClick={handleGoogleLogin}
                  className="w-full min-h-[44px] py-3 px-5 rounded-xl bg-white dark:bg-[#0D0221] border border-black/15 dark:border-white/20 hover:bg-black/5 dark:hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed text-xs font-bold text-[#0D0221] dark:text-white flex items-center justify-center gap-2.5 transition-colors"
                >
                  <svg className="w-4 h-4" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      fill="#4285F4"
                      d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17Z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.11-6.72-4.96H1.29v3.14C3.26 21.3 7.31 24 12 24Z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.28 14.24c-.24-.72-.38-1.49-.38-2.24s.14-1.52.38-2.24V6.62H1.29C.47 8.24 0 10.06 0 12s.47 3.76 1.29 5.38l3.99-3.14Z"
                    />
                    <path
                      fill="#EA4335"
                      d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.62l3.99 3.14c.95-2.85 3.6-4.96 6.72-4.96Z"
                    />
                  </svg>
                  <span>Continuar com Google</span>
                </button>
                {!providers.google_enabled && (
                  <p className="text-[11px] text-center text-[#0D0221]/60 dark:text-white/60">
                    Para ativar o botão do Google, configure <code className="font-mono">GOOGLE_CLIENT_ID</code> e{" "}
                    <code className="font-mono">GOOGLE_CLIENT_SECRET</code> no <code className="font-mono">.env</code>.
                  </p>
                )}
              </div>

              <div className="pt-2 text-center">
                <Link
                  href="/etapa-1"
                  className="inline-flex min-h-[44px] items-center justify-center text-xs font-bold text-[#335C67] dark:text-[#9fd0de] hover:underline"
                >
                  Continuar sem conta (Modo Convidado — 100% em memória)
                </Link>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
