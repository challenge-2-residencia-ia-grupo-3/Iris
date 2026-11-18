"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Eye, EyeOff, Lock, Mail, Moon, Sun } from "lucide-react";
import { IrisLogoBanner } from "@/components/IrisLogoBanner";
import { useTheme } from "@/contexts/ThemeContext";

/**
 * Página inicial de Acesso/Boas-vindas da Plataforma Íris de Adaptação:
 * - Ao entrar, redireciona via App Router para `/etapa-1` (fluxo unificado por rotas).
 */
export default function HomePage() {
  const router = useRouter();
  const { darkMode, toggleDarkMode } = useTheme();
  const [email, setEmail] = useState("marina.alves@escola.edu.br");
  const [password, setPassword] = useState("••••••••");
  const [showPassword, setShowPassword] = useState(false);

  const handleLoginSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    router.push("/etapa-1");
  };

  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-[#F5EDF0] dark:bg-[#0D0221] text-[#0D0221] dark:text-[#F5EDF0]">
      <aside className="relative flex flex-col justify-between bg-[#0D0221] text-white p-8 sm:p-14 overflow-hidden min-h-[460px] lg:min-h-screen">
        {/* Topo: Card da Marca Íris */}
        <div className="relative z-10 pt-2 sm:pt-4">
          <IrisLogoBanner />
        </div>

        {/* Bloco Editorial Central */}
        <div className="relative z-10 max-w-xl space-y-6 my-auto py-10">
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-white/10 text-[#ff9b85] border border-white/15">
            Apoio à decisão docente na Educação Básica
          </span>

          <h1 className="font-display text-3xl sm:text-5xl font-medium leading-[1.12] tracking-tight text-white">
            Adapte materiais. Amplie as formas de aprender.
          </h1>

          <p className="text-sm sm:text-base text-white/75 leading-relaxed max-w-md">
            Intervenção pedagógica cirúrgica fundamentada no Desenho Universal para a Aprendizagem (DUA), preservando o rigor curricular de cada atividade.
          </p>

          {/* Síntese Editorial dos 3 Pilares */}
          <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4 border-t border-white/15 text-xs">
            <div className="space-y-1">
              <dt className="font-semibold text-white">Escopo cirúrgico</dt>
              <dd className="text-white/65 leading-snug">
                Atua somente nas barreiras observadas em sala, sem rótulos clínicos em bloco.
              </dd>
            </div>
            <div className="space-y-1">
              <dt className="font-semibold text-white">Andaime em 3 níveis</dt>
              <dd className="text-white/65 leading-snug">
                Suporte graduado do ajuste visual à decomposição passo a passo.
              </dd>
            </div>
            <div className="space-y-1">
              <dt className="font-semibold text-white">Zero-Database</dt>
              <dd className="text-white/65 leading-snug">
                Processamento em memória com proteção automática de dados (LGPD).
              </dd>
            </div>
          </dl>
        </div>

        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-32 -right-28 w-[360px] h-[360px] rounded-full border border-[#E35336]/30 bg-gradient-to-tr from-[#0D0221] via-[#162736]/60 to-[#335C67]/25"
        />
      </aside>

      <main
        id="conteudo-principal"
        className="relative flex flex-col justify-center items-center p-8 sm:p-14 bg-[#F5EDF0] dark:bg-[#14072E]"
      >
        {/* Botão de Tema (Lua / Sol) no canto superior direito */}
        <div className="absolute top-6 right-6 flex items-center">
          <button
            type="button"
            onClick={toggleDarkMode}
            aria-label={darkMode ? "Ativar modo claro" : "Ativar modo escuro"}
            className="p-2.5 rounded-lg border border-[#335C67]/20 dark:border-white/15 text-[#0D0221] dark:text-white hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
          >
            {darkMode ? <Sun className="w-4 h-4 text-[#E35336]" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>

        <div className="w-full max-w-[400px] space-y-7 bg-white dark:bg-[#160A30] p-7 sm:p-9 rounded-2xl border border-[#335C67]/20 dark:border-white/15 shadow-sm">
          <div className="space-y-1.5">
            <h2 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight text-[#0D0221] dark:text-white">
              Acesse sua conta
            </h2>
            <p className="text-xs sm:text-sm text-[#0D0221]/70 dark:text-white/70">
              Entre para iniciar ou retomar uma sessão de adaptação pedagógica.
            </p>
          </div>

          <form onSubmit={handleLoginSubmit} className="space-y-5">
            {/* Campo E-mail */}
            <div className="space-y-1.5">
              <label
                htmlFor="login-email"
                className="block text-xs font-semibold text-[#0D0221] dark:text-white"
              >
                E-mail institucional
              </label>
              <div className="relative flex items-center">
                <Mail
                  className="w-4 h-4 text-[#0D0221]/45 dark:text-white/50 absolute left-3.5 pointer-events-none"
                  aria-hidden="true"
                />
                <input
                  id="login-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 rounded-lg bg-[#FAF7F8] dark:bg-[#0D0221] border border-[#335C67]/25 dark:border-white/15 text-sm text-[#0D0221] dark:text-white focus:border-[#E35336] transition-colors"
                />
              </div>
            </div>

            {/* Campo Senha */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label
                  htmlFor="login-password"
                  className="block text-xs font-semibold text-[#0D0221] dark:text-white"
                >
                  Senha
                </label>
                <button
                  type="button"
                  onClick={() => router.push("/etapa-1")}
                  className="text-xs font-semibold text-[#335C67] dark:text-[#9fd0de] hover:underline"
                >
                  Recuperar senha
                </button>
              </div>
              <div className="relative flex items-center">
                <Lock
                  className="w-4 h-4 text-[#0D0221]/45 dark:text-white/50 absolute left-3.5 pointer-events-none"
                  aria-hidden="true"
                />
                <input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-10 pr-10 py-3 rounded-lg bg-[#FAF7F8] dark:bg-[#0D0221] border border-[#335C67]/25 dark:border-white/15 text-sm text-[#0D0221] dark:text-white focus:border-[#E35336] transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                  className="absolute right-3 p-1 text-[#0D0221]/50 dark:text-white/60 hover:text-[#0D0221] dark:hover:text-white"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="w-full py-3 px-5 rounded-lg bg-[#E35336] hover:bg-[#c94429] text-white font-semibold text-sm flex items-center justify-center gap-2 transition-colors"
            >
              <span>Iniciar sessão de adaptação</span>
              <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </button>
          </form>

          <p className="text-center text-xs text-[#0D0221]/65 dark:text-white/65 pt-2 border-t border-[#335C67]/15 dark:border-white/10">
            Primeiro acesso?{" "}
            <button
              type="button"
              onClick={() => router.push("/etapa-1")}
              className="font-semibold text-[#335C67] dark:text-[#9fd0de] hover:underline"
            >
              Criar conta docente
            </button>
          </p>
        </div>
      </main>
    </div>
  );
}
