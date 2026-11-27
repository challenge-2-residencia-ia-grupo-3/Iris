"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  Contrast,
  Eye,
  EyeOff,
  FolderClock,
  Info,
  Loader2,
  Lock,
  Mail,
  Moon,
  Sun,
  User,
} from "lucide-react";
import { IrisIntroOverlay } from "@/components/iris-intro/IrisIntroOverlay";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import { AuthApiError, buildGoogleOAuthStartUrl } from "@/services/authApi";

type AuthMode = "login" | "register";

interface FormErrors {
  name?: string;
  email?: string;
  password?: string;
  general?: string;
}

/**
 * Tela de Login / Autenticação da Plataforma Íris
 * - Abertura cinematográfica da marca Íris (Preloader, PR #143): revelação suave da interface.
 * - Lado Esquerdo: Identidade visual com fundo roxo profundo, composição orbital e destaque em coral.
 * - Lado Direito: Autenticação local (e-mail/senha), Google OAuth 2.0 (PKCE) e Modo Convidado stateless.
 */
export default function HomePage() {
  const router = useRouter();
  const { darkMode, toggleDarkMode, highContrast, toggleHighContrast } = useTheme();
  const { teacher, isAuthenticated, isLoading: authLoading, providers, login, register, logout } = useAuth();

  const [showIntro, setShowIntro] = useState(true);
  const [loginRevealed, setLoginRevealed] = useState(false);
  const [mode, setMode] = useState<AuthMode>("login");
  const [nomeExibicao, setNomeExibicao] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};

    if (mode === "register") {
      const trimmedName = nomeExibicao.trim();
      if (trimmedName.length < 2 || trimmedName.length > 100) {
        newErrors.name = "Informe um nome de exibição entre 2 e 100 caracteres.";
      }
    }

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      newErrors.email = "Informe seu e-mail para acessar.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      newErrors.email = "Formato de e-mail inválido. Exemplo: docente@escola.edu.br";
    }

    if (!password) {
      newErrors.password = "Informe sua senha para continuar.";
    } else if (mode === "register" && password.length < 8) {
      newErrors.password = "A senha deve ter no mínimo 8 caracteres para cadastro.";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setInfoMessage(null);

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);
    setErrors({});
    try {
      const trimmedEmail = email.trim();
      if (mode === "register") {
        await register(trimmedEmail, nomeExibicao.trim(), password);
      } else {
        await login(trimmedEmail, password);
      }
      router.push("/etapa-1");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setErrors({ general: err.message });
      } else {
        setErrors({
          general: "Não foi possível autenticar no momento. Você pode continuar no Modo Convidado.",
        });
      }
      setIsLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    window.location.assign(buildGoogleOAuthStartUrl("/historico"));
  };

  const handleSwitchMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setErrors({});
    setInfoMessage(null);
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setNomeExibicao(e.target.value);
    if (errors.name) {
      setErrors((prev) => ({ ...prev, name: undefined }));
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
    <>
      {showIntro && (
        <IrisIntroOverlay
          onExitStart={() => setLoginRevealed(true)}
          onFinished={() => {
            setLoginRevealed(true);
            setShowIntro(false);
          }}
        />
      )}

      <div
        aria-hidden={showIntro}
        className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-[#FAF7F9] dark:bg-[#0D0221] text-[#0D0221] dark:text-[#F5EDF0] antialiased selection:bg-[#E35336]/20 selection:text-[#E35336]"
      >
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

            {/* Órbitas superiores com esfera luminosa principal */}
            <svg
              className="absolute -top-20 -right-20 sm:-top-12 sm:-right-12 w-[520px] h-[520px] lg:w-[600px] lg:h-[600px] overflow-visible"
              viewBox="0 0 600 600"
              fill="none"
            >
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
            className={`relative z-10 pt-2 sm:pt-4 pointer-events-none select-none opacity-30 dark:opacity-25 transition-opacity duration-500 ease-out delay-100 motion-reduce:transition-none ${
              loginRevealed ? "opacity-30 dark:opacity-25" : "opacity-0"
            }`}
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
          <div
            className={`relative z-10 max-w-lg space-y-6 my-auto pt-10 pb-12 sm:pb-16 lg:py-0 transition-opacity duration-500 ease-out delay-150 motion-reduce:transition-none ${
              loginRevealed ? "opacity-100" : "opacity-0"
            }`}
          >
            <div className="space-y-2">
              <p className="text-xs sm:text-sm font-bold tracking-[0.16em] uppercase text-[#FF7A59]">
                PLATAFORMA INTELIGENTE PARA PROFESSORES
              </p>
              <div className="w-12 h-1 bg-[#E35336] rounded-full" aria-hidden="true" />
            </div>

            <h1 className="text-3xl sm:text-4xl lg:text-[2.85rem] xl:text-5xl font-extrabold leading-[1.14] tracking-tight text-white">
              Amplie as formas
              <br />
              de aprender.
              <br />
              <span className="text-[#FF7A59]">Adapte materiais.</span>
            </h1>

            <p className="text-sm sm:text-base lg:text-lg text-white/85 font-normal leading-relaxed max-w-md">
              A Íris usa inteligência artificial para adaptar materiais do Ensino
              Fundamental II às diferentes necessidades dos seus alunos.
            </p>
          </div>

          {/* Rodapé discreto de suporte institucional / acessibilidade */}
          <div
            className={`relative z-10 pt-4 hidden lg:block transition-opacity duration-500 ease-out delay-200 motion-reduce:transition-none ${
              loginRevealed ? "opacity-100" : "opacity-0"
            }`}
          >
            <p className="text-xs text-white/75 tracking-wide">
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
          {/* Canto superior direito: Botões acessíveis de Alto Contraste e alternância de tema */}
          <div
            className={`w-full flex items-center justify-end gap-2 transition-opacity duration-500 ease-out delay-100 motion-reduce:transition-none ${
              loginRevealed ? "opacity-100" : "opacity-0"
            }`}
          >
            <button
              type="button"
              onClick={toggleHighContrast}
              aria-pressed={highContrast}
              aria-label="Alternar modo de alto contraste"
              title="Alternar modo de alto contraste (WCAG 2.1 AA)"
              className={`inline-flex min-h-[44px] min-w-[44px] items-center justify-center gap-1.5 px-3 rounded-full text-xs font-semibold border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] cursor-pointer ${
                highContrast
                  ? "bg-white text-[#0D0221] border-white"
                  : "bg-white/90 dark:bg-[#0D0221]/90 text-[#0D0221] dark:text-white border-black/15 dark:border-white/20 hover:border-[#E35336]"
              }`}
            >
              <Contrast
                className={`w-4 h-4 ${highContrast ? "text-[#0D0221]" : "text-[#B53319] dark:text-[#FF8A70]"}`}
                aria-hidden="true"
              />
              <span className="hidden sm:inline leading-none">Alto Contraste</span>
            </button>

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
              className="inline-flex min-h-[44px] min-w-[44px] items-center gap-1.5 px-2 py-1.5 rounded-full border border-black/15 dark:border-white/20 bg-white/90 dark:bg-[#0D0221]/90 shadow-sm hover:border-[#E35336] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] transition-all cursor-pointer"
            >
              <span
                className={`p-1.5 rounded-full transition-all flex items-center justify-center ${
                  !darkMode
                    ? "bg-[#E35336] text-white shadow-sm"
                    : "text-[#0D0221]/60 hover:text-[#0D0221] dark:text-white/60 dark:hover:text-white"
                }`}
                aria-hidden="true"
              >
                <Sun className="w-4 h-4" />
              </span>
              <span
                className={`p-1.5 rounded-full transition-all flex items-center justify-center ${
                  darkMode
                    ? "bg-[#E35336] text-white shadow-sm"
                    : "text-[#0D0221]/60 hover:text-[#0D0221] dark:text-white/60 dark:hover:text-white"
                }`}
                aria-hidden="true"
              >
                <Moon className="w-4 h-4" />
              </span>
            </button>
          </div>

          {/* Área centralizada do Formulário */}
          <div
            className={`w-full max-w-[420px] mx-auto my-auto py-8 sm:py-12 space-y-6 transition-opacity duration-500 ease-out delay-[220ms] motion-reduce:transition-none ${
              loginRevealed ? "opacity-100" : "opacity-0"
            }`}
          >
            {/* Logo oficial da Íris no lado claro */}
            <div
              data-testid="logo-lado-claro"
              className="relative inline-flex items-center gap-3.5 select-none"
            >
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

              <div className="relative z-10 w-11 h-8 sm:w-12 sm:h-9 flex items-center justify-center">
                <img
                  src="/iris-eye.png"
                  alt=""
                  aria-hidden="true"
                  className="w-full h-full object-contain filter drop-shadow-sm"
                />
              </div>

              <span className="relative z-10 text-2xl sm:text-3xl font-bold tracking-tight text-[#0D0221] dark:text-white font-sans">
                Íris
              </span>
            </div>

            {!authLoading && isAuthenticated && teacher ? (
              <div className="rounded-2xl bg-white dark:bg-[#0D0221] border border-[#335C67]/25 dark:border-white/15 p-6 shadow-sm space-y-5">
                <div className="space-y-1">
                  <p className="text-xs font-extrabold uppercase tracking-wider text-[#335C67] dark:text-[#9fd0de]">
                    Sessão ativa
                  </p>
                  <h2 className="text-2xl font-extrabold text-[#0D0221] dark:text-white">
                    Olá, {teacher.nome_exibicao}
                  </h2>
                  <p className="text-xs text-[#4A4358] dark:text-white/75">{teacher.email}</p>
                </div>

                <div className="space-y-3">
                  <Link
                    href="/etapa-1"
                    className="w-full min-h-[44px] py-3 px-5 rounded-xl bg-[#D13B1E] hover:bg-[#B73318] text-white font-bold text-sm flex items-center justify-center gap-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D13B1E] focus-visible:ring-offset-2 dark:focus-visible:ring-offset-[#0D0221]"
                  >
                    <span>Nova Adaptação (Etapa 1)</span>
                    <ArrowRight className="w-4 h-4" aria-hidden="true" />
                  </Link>
                  <Link
                    href="/historico"
                    className="w-full min-h-[44px] py-3 px-5 rounded-xl bg-[#335C67] hover:bg-[#274851] text-white font-bold text-sm flex items-center justify-center gap-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#335C67] focus-visible:ring-offset-2 dark:focus-visible:ring-offset-[#0D0221]"
                  >
                    <FolderClock className="w-4 h-4" aria-hidden="true" />
                    <span>Minhas Atividades</span>
                  </Link>
                  <button
                    type="button"
                    onClick={() => logout()}
                    className="w-full min-h-[44px] py-2.5 px-4 rounded-xl border border-black/15 dark:border-white/20 text-xs font-bold text-[#0D0221] dark:text-white hover:bg-black/5 dark:hover:bg-white/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336]"
                  >
                    Sair e trocar de conta
                  </button>
                </div>
              </div>
            ) : (
              <>
                {/* Cabeçalho do formulário */}
                <div className="space-y-2">
                  <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-[#0D0221] dark:text-white">
                    {mode === "login" ? "Acesse sua conta" : "Crie sua conta docente"}
                  </h2>
                  <p className="text-sm text-[#4A4358] dark:text-white/75 font-normal leading-relaxed">
                    {mode === "login"
                      ? "Entre para continuar criando caminhos de aprendizagem."
                      : "Salve suas atividades sanitizadas com privacidade Zero-Database de estudantes."}
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

                {infoMessage && (
                  <div
                    role="status"
                    className="flex items-start gap-2.5 p-3.5 rounded-xl bg-[#335C67]/10 dark:bg-[#335C67]/25 border border-[#335C67]/30 text-[#0D0221] dark:text-white text-xs sm:text-sm"
                  >
                    <Info className="w-4 h-4 shrink-0 mt-0.5 text-[#335C67] dark:text-[#9FD0DE]" aria-hidden="true" />
                    <span>{infoMessage}</span>
                  </div>
                )}

                <form
                  onSubmit={handleLoginSubmit}
                  noValidate
                  className="space-y-4"
                  aria-label="Formulário de acesso à plataforma Íris"
                >
                  {mode === "register" && (
                    <div className="space-y-2">
                      <label
                        htmlFor="register-name"
                        className="block text-xs sm:text-sm font-bold text-[#1E1B2E] dark:text-white"
                      >
                        Nome de exibição
                      </label>
                      <div className="relative flex items-center">
                        <User
                          className="w-4 h-4 text-[#4A4358] dark:text-white/60 absolute left-4 pointer-events-none"
                          aria-hidden="true"
                        />
                        <input
                          id="register-name"
                          name="nome_exibicao"
                          type="text"
                          autoComplete="name"
                          required
                          minLength={2}
                          maxLength={100}
                          value={nomeExibicao}
                          onChange={handleNameChange}
                          placeholder="Ex.: Profa. Marina Alves"
                          aria-invalid={errors.name ? "true" : "false"}
                          aria-describedby={errors.name ? "register-name-error" : undefined}
                          disabled={isLoading}
                          className={`w-full pl-11 pr-4 py-3 sm:py-3.5 rounded-xl sm:rounded-2xl bg-white dark:bg-[#0D0221] border ${
                            errors.name
                              ? "border-red-500 dark:border-red-500 focus:border-red-600 focus:ring-red-500/25"
                              : "border-black/15 dark:border-white/20 focus:border-[#E35336] focus:ring-[#E35336]/20"
                          } text-sm sm:text-base text-[#0D0221] dark:text-white placeholder:text-[#556070] dark:placeholder:text-white/65 shadow-sm focus:ring-2 focus:outline-none transition-all disabled:opacity-60 disabled:cursor-not-allowed`}
                        />
                      </div>
                      {errors.name && (
                        <p
                          id="register-name-error"
                          role="alert"
                          className="flex items-center gap-1.5 text-xs font-semibold text-red-600 dark:text-red-400 mt-1"
                        >
                          <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                          <span>{errors.name}</span>
                        </p>
                      )}
                    </div>
                  )}

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
                        } text-sm sm:text-base text-[#0D0221] dark:text-white placeholder:text-[#556070] dark:placeholder:text-white/65 shadow-sm focus:ring-2 focus:outline-none transition-all disabled:opacity-60 disabled:cursor-not-allowed`}
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
                      Senha{" "}
                      {mode === "register" && (
                        <span className="font-normal text-[#4A4358] dark:text-white/75">(mínimo 8 caracteres)</span>
                      )}
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
                        autoComplete={mode === "register" ? "new-password" : "current-password"}
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
                        } text-sm sm:text-base text-[#0D0221] dark:text-white placeholder:text-[#556070] dark:placeholder:text-white/65 shadow-sm focus:ring-2 focus:outline-none transition-all disabled:opacity-60 disabled:cursor-not-allowed`}
                      />

                      <button
                        type="button"
                        onClick={() => setShowPassword((prev) => !prev)}
                        aria-label={showPassword ? "Ocultar senha" : "Exibir senha em texto claro"}
                        aria-pressed={showPassword}
                        disabled={isLoading}
                        className="absolute right-1 min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg text-[#4A4358] dark:text-white/60 hover:text-[#0D0221] dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] transition-colors"
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

                  {/* Link "Esqueci minha senha" */}
                  {mode === "login" && (
                    <div className="flex justify-end pt-0.5">
                      <button
                        type="button"
                        onClick={() =>
                          setInfoMessage(
                            "A recuperação automática por e-mail ainda não está configurada. Você pode entrar com Google ou continuar no Modo Convidado."
                          )
                        }
                        className="min-h-[44px] inline-flex items-center px-2 text-xs sm:text-sm font-bold text-[#335C67] dark:text-[#8CB6C2] hover:text-[#25434B] dark:hover:text-white underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] rounded-sm transition-colors cursor-pointer"
                      >
                        Esqueci minha senha
                      </button>
                    </div>
                  )}

                  {/* Botão principal "Entrar" / "Criar conta" */}
                  <button
                    type="submit"
                    disabled={isLoading}
                    aria-busy={isLoading}
                    className="w-full min-h-[44px] py-3.5 px-6 rounded-xl sm:rounded-2xl bg-[#D13B1E] hover:bg-[#B73318] active:bg-[#9E2B14] text-white font-bold text-sm sm:text-base flex items-center justify-center gap-2 shadow-[0_8px_20px_-4px_rgba(209,59,30,0.45)] hover:shadow-[0_10px_24px_-4px_rgba(209,59,30,0.6)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D13B1E] focus-visible:ring-offset-2 dark:focus-visible:ring-offset-[#14072E] disabled:opacity-75 disabled:cursor-not-allowed transition-all cursor-pointer group"
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none shrink-0" aria-hidden="true" />
                        <span>{mode === "login" ? "Entrando..." : "Criando conta..."}</span>
                      </>
                    ) : (
                      <>
                        <span>{mode === "login" ? "Entrar" : "Criar conta"}</span>
                        <ArrowRight
                          className="w-4 h-4 shrink-0 transition-transform group-hover:translate-x-1"
                          aria-hidden="true"
                        />
                      </>
                    )}
                  </button>
                </form>

                {/* Separador e Login OAuth Google / Modo Convidado */}
                <div className="relative flex items-center py-0.5">
                  <div className="flex-grow border-t border-black/10 dark:border-white/15" />
                  <span className="mx-3 text-[11px] font-semibold uppercase tracking-wider text-[#4A4358] dark:text-white/70">
                    ou
                  </span>
                  <div className="flex-grow border-t border-black/10 dark:border-white/15" />
                </div>

                <div className="space-y-2.5">
                  <button
                    type="button"
                    disabled={!providers.google_enabled}
                    onClick={handleGoogleLogin}
                    className="w-full min-h-[44px] py-3 px-5 rounded-xl sm:rounded-2xl bg-white dark:bg-[#0D0221] border border-black/15 dark:border-white/20 hover:bg-black/5 dark:hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed text-xs sm:text-sm font-bold text-[#0D0221] dark:text-white flex items-center justify-center gap-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] transition-colors"
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
                    <p className="text-[11px] text-center text-[#4A4358] dark:text-white/70">
                      Login Google opcional (configure <code className="font-mono">GOOGLE_CLIENT_ID</code> e{" "}
                      <code className="font-mono">GOOGLE_CLIENT_SECRET</code> no <code className="font-mono">.env</code>).
                    </p>
                  )}

                  <button
                    type="button"
                    onClick={() => router.push("/etapa-1")}
                    className="w-full min-h-[44px] py-2.5 px-4 rounded-xl text-xs sm:text-sm font-bold text-[#335C67] dark:text-[#8CB6C2] hover:bg-[#335C67]/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] transition-colors cursor-pointer"
                  >
                    Continuar sem conta (Modo Convidado — 100% em memória)
                  </button>
                </div>

                {/* Alternância Login / Cadastro */}
                <p className="text-center text-xs sm:text-sm text-[#4A4358] dark:text-white/75">
                  {mode === "login" ? (
                    <>
                      Ainda não tem conta?{" "}
                      <button
                        type="button"
                        onClick={() => handleSwitchMode("register")}
                        className="min-h-[44px] inline-flex items-center px-2 font-bold text-[#335C67] dark:text-[#8CB6C2] hover:text-[#25434B] dark:hover:text-white underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] rounded-sm transition-colors cursor-pointer"
                      >
                        Criar conta
                      </button>
                    </>
                  ) : (
                    <>
                      Já tem uma conta?{" "}
                      <button
                        type="button"
                        onClick={() => handleSwitchMode("login")}
                        className="min-h-[44px] inline-flex items-center px-2 font-bold text-[#335C67] dark:text-[#8CB6C2] hover:text-[#25434B] dark:hover:text-white underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] rounded-sm transition-colors cursor-pointer"
                      >
                        Entrar
                      </button>
                    </>
                  )}
                </p>
              </>
            )}
          </div>

          {/* Rodapé institucional sutil */}
          <footer
            className={`w-full text-center py-2 transition-opacity duration-500 ease-out delay-[250ms] motion-reduce:transition-none ${
              loginRevealed ? "opacity-100" : "opacity-0"
            }`}
          >
            <p className="text-[11px] text-[#4A4358] dark:text-white/70">
              Íris — Plataforma Inteligente de Adaptação de Materiais Pedagógicos © {new Date().getFullYear()}
            </p>
          </footer>
        </main>
      </div>
    </>
  );
}
