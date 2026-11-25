"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  Moon,
  Sun,
} from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";

interface FormErrors {
  email?: string;
  password?: string;
  general?: string;
}

/**
 * Tela de Login / Autenticação da Plataforma Íris
 * - Lado Esquerdo: Identidade visual com fundo roxo profundo, composição orbital e destaque em coral.
 * - Lado Direito: Formulário de autenticação acessível (WCAG 2.1 AA) e botão de alternância de tema.
 */
export default function HomePage() {
  const router = useRouter();
  const { darkMode, toggleDarkMode } = useTheme();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});

  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      newErrors.email = "Informe seu e-mail para acessar.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      newErrors.email = "Formato de e-mail inválido. Exemplo: docente@escola.edu.br";
    }

    if (!password) {
      newErrors.password = "Informe sua senha para continuar.";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);
    try {
      // Simulação rápida para feedback visual perceptível (Heurística de Nielsen 1)
      await new Promise((resolve) => setTimeout(resolve, 350));
      router.push("/etapa-1");
    } catch {
      setErrors({
        general: "Não foi possível autenticar no momento. Tente novamente.",
      });
      setIsLoading(false);
    }
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEmail(e.target.value);
    if (errors.email) {
      setErrors((prev) => ({ ...prev, email: undefined }));
    }
  };

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPassword(e.target.value);
    if (errors.password) {
      setErrors((prev) => ({ ...prev, password: undefined }));
    }
  };

  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-[#FAF7F9] dark:bg-[#0D0221] text-[#0D0221] dark:text-[#F5EDF0] antialiased selection:bg-[#E35336]/20 selection:text-[#E35336]">
      {/* ========================================================================= */}
      {/* LADO ESQUERDO: Apresentação da Íris (Identidade Visual & Órbitas)           */}
      {/* ========================================================================= */}
      <aside
        aria-label="Apresentação da plataforma Íris"
        className="relative flex flex-col justify-between bg-[#0D0221] text-white p-6 sm:p-12 lg:p-16 overflow-hidden min-h-[460px] lg:min-h-screen select-none"
      >
        {/* Camada gráfica orbital de fundo com elementos curvos e detalhes em coral */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 overflow-hidden"
        >
          {/* Brilho radial de profundidade */}
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_25%,rgba(51,92,103,0.22)_0%,transparent_65%)]" />

          {/* Órbitas superiores com esfera luminosa principal (fiel à referência) */}
          <svg
            className="absolute -top-20 -right-20 sm:-top-12 sm:-right-12 w-[520px] h-[520px] lg:w-[600px] lg:h-[600px] overflow-visible"
            viewBox="0 0 600 600"
            fill="none"
          >
            {/* Linha orbital curva em azul petróleo */}
            <ellipse
              cx="300"
              cy="300"
              rx="270"
              ry="210"
              stroke="#335C67"
              strokeWidth="1.25"
              strokeOpacity="0.45"
              transform="rotate(-20 300 300)"
            />
            {/* Linha orbital curva em coral */}
            <ellipse
              cx="300"
              cy="300"
              rx="210"
              ry="165"
              stroke="#E35336"
              strokeWidth="1.5"
              strokeOpacity="0.6"
              transform="rotate(-10 300 300)"
            />
            {/* Esfera luminosa com auréola suave na órbita */}
            <g transform="translate(195, 145)">
              <circle cx="0" cy="0" r="22" fill="#E35336" fillOpacity="0.15" />
              <circle cx="0" cy="0" r="12" fill="#E35336" fillOpacity="0.45" />
              <circle cx="0" cy="0" r="7" fill="#FF7A59" />
            </g>
          </svg>

          {/* Órbita inferior de profundidade */}
          <svg
            className="absolute -bottom-36 -right-16 w-[460px] h-[460px] lg:w-[540px] lg:h-[540px] overflow-visible"
            viewBox="0 0 500 500"
            fill="none"
          >
            <circle
              cx="250"
              cy="250"
              r="230"
              stroke="#E35336"
              strokeWidth="1.25"
              strokeOpacity="0.35"
            />
            <circle
              cx="250"
              cy="250"
              r="190"
              stroke="#335C67"
              strokeWidth="1"
              strokeOpacity="0.25"
            />
          </svg>
        </div>

        {/* Marca d'água institucional no canto superior esquerdo (discreta, sem bolinha luminosa e sem o nome Íris) */}
        <div
          data-testid="marca-dagua-lado-roxo"
          aria-hidden="true"
          className="relative z-10 pt-2 sm:pt-4 pointer-events-none select-none opacity-30 dark:opacity-25"
        >
          <div className="relative inline-flex items-center">
            <svg
              className="w-16 h-10 overflow-visible"
              viewBox="0 0 64 40"
              fill="none"
              aria-hidden="true"
            >
              <ellipse
                cx="32"
                cy="20"
                rx="30"
                ry="15"
                stroke="#E35336"
                strokeWidth="1.25"
                strokeOpacity="0.6"
                transform="rotate(-8 32 20)"
              />
              <ellipse
                cx="32"
                cy="20"
                rx="20"
                ry="10"
                stroke="#335C67"
                strokeWidth="1"
                strokeOpacity="0.5"
              />
            </svg>
            <img
              src="/iris-eye.png"
              alt=""
              className="w-9 h-6 object-contain -ml-12 filter drop-shadow-sm opacity-70"
            />
          </div>
        </div>

        {/* Bloco de Textos com hierarquia visual clara */}
        <div className="relative z-10 max-w-lg space-y-6 my-auto pt-10 pb-12 sm:pb-16 lg:py-0">
          {/* Identificação institucional */}
          <div className="space-y-2">
            <p className="text-xs sm:text-sm font-bold tracking-[0.16em] uppercase text-[#FF7A59]">
              PLATAFORMA INTELIGENTE PARA PROFESSORES
            </p>
            {/* Traço de destaque em coral */}
            <div className="w-12 h-1 bg-[#E35336] rounded-full" aria-hidden="true" />
          </div>

          {/* Título principal e Destaque em coral */}
          <h1 className="text-3xl sm:text-4xl lg:text-[2.85rem] xl:text-5xl font-extrabold leading-[1.14] tracking-tight text-white">
            Amplie as formas
            <br />
            de aprender.
            <br />
            <span className="text-[#FF7A59]">Adapte materiais.</span>
          </h1>

          {/* Texto de apresentação */}
          <p className="text-sm sm:text-base lg:text-lg text-white/85 font-normal leading-relaxed max-w-md">
            A Íris usa inteligência artificial para adaptar materiais do Ensino
            Fundamental II às diferentes necessidades dos seus alunos.
          </p>
        </div>

        {/* Rodapé discreto de suporte institucional / acessibilidade */}
        <div className="relative z-10 pt-4 hidden lg:block">
          <p className="text-xs text-white/50 tracking-wide">
            Design inclusivo com foco em barreiras funcionais e privacidade Zero-Database.
          </p>
        </div>
      </aside>

      {/* ========================================================================= */}
      {/* LADO DIREITO: Autenticação & Acessibilidade                                 */}
      {/* ========================================================================= */}
      <main
        id="conteudo-principal"
        className="relative flex flex-col justify-between p-6 sm:p-12 lg:p-16 bg-[#FAF7F9] dark:bg-[#14072E] min-h-[540px] lg:min-h-screen transition-colors duration-200"
      >
        {/* Canto superior direito: Botão acessível de alternância de tema */}
        <div className="w-full flex justify-end">
          <button
            type="button"
            role="switch"
            aria-checked={darkMode}
            aria-label={
              darkMode
                ? "Modo escuro ativado. Pressione Enter ou Espaço para mudar para o modo claro."
                : "Modo claro ativado. Pressione Enter ou Espaço para mudar para o modo escuro."
            }
            onClick={toggleDarkMode}
            className="inline-flex items-center gap-1.5 p-1 rounded-full border border-black/15 dark:border-white/20 bg-white/90 dark:bg-[#0D0221]/90 shadow-xs hover:border-[#E35336] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] transition-all cursor-pointer"
          >
            {/* Ícone Sol (Modo Claro) */}
            <span
              className={`p-1.5 rounded-full transition-all flex items-center justify-center ${
                !darkMode
                  ? "bg-[#E35336] text-white shadow-xs"
                  : "text-[#0D0221]/60 hover:text-[#0D0221] dark:text-white/60 dark:hover:text-white"
              }`}
              aria-hidden="true"
            >
              <Sun className="w-4 h-4" />
            </span>
            {/* Ícone Lua (Modo Escuro) */}
            <span
              className={`p-1.5 rounded-full transition-all flex items-center justify-center ${
                darkMode
                  ? "bg-[#E35336] text-white shadow-xs"
                  : "text-[#0D0221]/60 hover:text-[#0D0221] dark:text-white/60 dark:hover:text-white"
              }`}
              aria-hidden="true"
            >
              <Moon className="w-4 h-4" />
            </span>
          </button>
        </div>

        {/* Área centralizada do Formulário */}
        <div className="w-full max-w-[420px] mx-auto my-auto py-8 sm:py-12 space-y-7">
          {/* Logo oficial da Íris no lado claro (símbolo do olho + nome Íris + órbita com pequena esfera luminosa, sem traço vertical) */}
          <div
            data-testid="logo-lado-claro"
            className="relative inline-flex items-center gap-3.5 select-none"
          >
            {/* Órbita integrada à logo com pequena esfera luminosa */}
            <svg
              className="absolute -left-3 -top-2.5 w-[140px] h-[58px] pointer-events-none overflow-visible"
              viewBox="0 0 140 58"
              fill="none"
              aria-hidden="true"
            >
              <ellipse
                cx="68"
                cy="29"
                rx="65"
                ry="23"
                stroke="#D13B1E"
                strokeWidth="1.25"
                strokeOpacity="0.55"
                transform="rotate(-7 68 29)"
              />
              <circle cx="122" cy="16" r="2.75" fill="#D13B1E" />
              <circle cx="122" cy="16" r="5.5" fill="#D13B1E" fillOpacity="0.35" />
            </svg>

            {/* Símbolo do olho */}
            <div className="relative z-10 w-11 h-8 sm:w-12 sm:h-9 flex items-center justify-center">
              <img
                src="/iris-eye.png"
                alt=""
                aria-hidden="true"
                className="w-full h-full object-contain filter drop-shadow-sm"
              />
            </div>

            {/* Nome Íris (sem o traço vertical separador) */}
            <span className="relative z-10 text-2xl sm:text-3xl font-bold tracking-tight text-[#0D0221] dark:text-white font-sans">
              Íris
            </span>
          </div>

          {/* Cabeçalho do formulário */}
          <div className="space-y-2">
            <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-[#0D0221] dark:text-white">
              Acesse sua conta
            </h2>
            <p className="text-sm text-[#4A4358] dark:text-white/75 font-normal leading-relaxed">
              Entre para continuar criando caminhos de aprendizagem.
            </p>
          </div>

          {/* Feedback Geral de Erro (se houver) */}
          {errors.general && (
            <div
              role="alert"
              className="flex items-start gap-2.5 p-3.5 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-xs sm:text-sm font-medium"
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
              <span>{errors.general}</span>
            </div>
          )}

          <form
            onSubmit={handleLoginSubmit}
            noValidate
            className="space-y-5"
            aria-label="Formulário de acesso à plataforma Íris"
          >
            {/* 1. Campo E-mail */}
            <div className="space-y-2">
              <label
                htmlFor="login-email"
                className="block text-xs sm:text-sm font-bold text-[#1E1B2E] dark:text-white"
              >
                E-mail
              </label>
              <div className="relative flex items-center">
                <Mail
                  className="w-4 h-4 text-[#4A4358] dark:text-white/60 absolute left-4 pointer-events-none"
                  aria-hidden="true"
                />
                <input
                  id="login-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={handleEmailChange}
                  placeholder="Seu e-mail"
                  aria-invalid={errors.email ? "true" : "false"}
                  aria-describedby={errors.email ? "login-email-error" : undefined}
                  disabled={isLoading}
                  className={`w-full pl-11 pr-4 py-3 sm:py-3.5 rounded-xl sm:rounded-2xl bg-white dark:bg-[#0D0221] border ${
                    errors.email
                      ? "border-red-500 dark:border-red-500 focus:border-red-600 focus:ring-red-500/25"
                      : "border-black/15 dark:border-white/20 focus:border-[#E35336] focus:ring-[#E35336]/20"
                  } text-sm sm:text-base text-[#0D0221] dark:text-white placeholder:text-[#64748B] dark:placeholder:text-white/45 shadow-xs focus:ring-2 focus:outline-none transition-all disabled:opacity-60 disabled:cursor-not-allowed`}
                />
              </div>
              {errors.email && (
                <p
                  id="login-email-error"
                  role="alert"
                  className="flex items-center gap-1.5 text-xs font-semibold text-red-600 dark:text-red-400 mt-1"
                >
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                  <span>{errors.email}</span>
                </p>
              )}
            </div>

            {/* 2. Campo Senha */}
            <div className="space-y-2">
              <label
                htmlFor="login-password"
                className="block text-xs sm:text-sm font-bold text-[#1E1B2E] dark:text-white"
              >
                Senha
              </label>
              <div className="relative flex items-center">
                <Lock
                  className="w-4 h-4 text-[#4A4358] dark:text-white/60 absolute left-4 pointer-events-none"
                  aria-hidden="true"
                />
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={handlePasswordChange}
                  placeholder="Sua senha"
                  aria-invalid={errors.password ? "true" : "false"}
                  aria-describedby={errors.password ? "login-password-error" : undefined}
                  disabled={isLoading}
                  className={`w-full pl-11 pr-12 py-3 sm:py-3.5 rounded-xl sm:rounded-2xl bg-white dark:bg-[#0D0221] border ${
                    errors.password
                      ? "border-red-500 dark:border-red-500 focus:border-red-600 focus:ring-red-500/25"
                      : "border-black/15 dark:border-white/20 focus:border-[#E35336] focus:ring-[#E35336]/20"
                  } text-sm sm:text-base text-[#0D0221] dark:text-white placeholder:text-[#64748B] dark:placeholder:text-white/45 shadow-xs focus:ring-2 focus:outline-none transition-all disabled:opacity-60 disabled:cursor-not-allowed`}
                />

                {/* 3. Controle para visualizar ou ocultar senha */}
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label={showPassword ? "Ocultar senha" : "Exibir senha em texto claro"}
                  aria-pressed={showPassword}
                  disabled={isLoading}
                  className="absolute right-3.5 p-1.5 rounded-lg text-[#4A4358] dark:text-white/60 hover:text-[#0D0221] dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] transition-colors"
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" aria-hidden="true" />
                  ) : (
                    <Eye className="w-4 h-4" aria-hidden="true" />
                  )}
                </button>
              </div>
              {errors.password && (
                <p
                  id="login-password-error"
                  role="alert"
                  className="flex items-center gap-1.5 text-xs font-semibold text-red-600 dark:text-red-400 mt-1"
                >
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                  <span>{errors.password}</span>
                </p>
              )}
            </div>

            {/* 4. Link "Esqueci minha senha" */}
            <div className="flex justify-end pt-0.5">
              <button
                type="button"
                onClick={() => router.push("/etapa-1")}
                className="text-xs sm:text-sm font-bold text-[#335C67] dark:text-[#8CB6C2] hover:text-[#25434B] dark:hover:text-white underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] rounded-sm transition-colors cursor-pointer"
              >
                Esqueci minha senha
              </button>
            </div>

            {/* 5. Botão principal "Entrar" */}
            <button
              type="submit"
              disabled={isLoading}
              aria-busy={isLoading}
              className="w-full py-3.5 px-6 rounded-xl sm:rounded-2xl bg-[#D13B1E] hover:bg-[#B73318] active:bg-[#9E2B14] text-white font-bold text-sm sm:text-base flex items-center justify-center gap-2 shadow-[0_8px_20px_-4px_rgba(209,59,30,0.45)] hover:shadow-[0_10px_24px_-4px_rgba(209,59,30,0.6)] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-[#D13B1E] focus-visible:ring-offset-2 dark:focus-visible:ring-offset-[#14072E] disabled:opacity-75 disabled:cursor-not-allowed transition-all cursor-pointer group"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none shrink-0" aria-hidden="true" />
                  <span>Entrando...</span>
                </>
              ) : (
                <>
                  <span>Entrar</span>
                  <ArrowRight
                    className="w-4 h-4 shrink-0 transition-transform group-hover:translate-x-1"
                    aria-hidden="true"
                  />
                </>
              )}
            </button>
          </form>

          {/* 6. Texto de apoio: "Ainda não tem conta? Criar conta" */}
          <p className="text-center text-xs sm:text-sm text-[#4A4358] dark:text-white/70">
            Ainda não tem conta?{" "}
            <button
              type="button"
              onClick={() => router.push("/etapa-1")}
              className="font-bold text-[#335C67] dark:text-[#8CB6C2] hover:text-[#25434B] dark:hover:text-white underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] rounded-sm transition-colors cursor-pointer"
            >
              Criar conta
            </button>
          </p>
        </div>

        {/* Rodapé institucional sutil */}
        <footer className="w-full text-center py-2">
          <p className="text-[11px] text-[#4A4358]/70 dark:text-white/40">
            Íris — Plataforma Inteligente de Adaptação de Materiais Pedagógicos © {new Date().getFullYear()}
          </p>
        </footer>
      </main>
    </div>
  );
}
