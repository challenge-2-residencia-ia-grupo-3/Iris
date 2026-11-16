"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Eye, EyeOff, Lock, Mail, Moon, Sun } from "lucide-react";
import { IrisLogoBanner } from "@/components/IrisLogoBanner";
import { useTheme } from "@/contexts/ThemeContext";

/**
 * Página inicial de Acesso/Boas-vindas da Plataforma Íris de Adaptação:
 * - Split screen fiel ao Figma (Midnight Violet #0D0221 + Lavender Blush #F5EDF0).
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
      {/* Coluna Esquerda Institucional (Midnight Violet #0D0221 fiel ao Figma) */}
      <aside className="relative flex flex-col justify-between bg-[#0D0221] text-white p-8 sm:p-14 overflow-hidden min-h-[420px] lg:min-h-screen">
        {/* Topo: Card da Marca Íris */}
        <div className="relative z-10">
          <IrisLogoBanner />
        </div>

        {/* Rodapé Hero Institucional */}
        <div className="relative z-10 max-w-lg space-y-4 my-auto lg:my-0 pt-12">
          <p className="text-xs font-bold tracking-[0.14em] uppercase text-[#E35336]">
            Plataforma Gratuita para Professores
          </p>
          <h1 className="text-3xl sm:text-5xl font-bold leading-[1.15] tracking-tight text-white">
            Adapte materiais. Amplie as formas de aprender.
          </h1>
          <p className="text-sm sm:text-base text-white/75 leading-relaxed">
            A Íris usa inteligência artificial para ajudar você a adaptar textos e atividades do Ensino Fundamental II às necessidades de cada perfil pedagógico, sem precisar de conhecimento técnico.
          </p>
        </div>

        {/* Esfera decorativa inferior direita idêntica ao Figma */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-28 -right-24 w-[380px] h-[380px] rounded-full border border-[#E35336]/45 bg-gradient-to-tr from-[#0D0221] via-[#162736]/80 to-[#335C67]/35 shadow-2xl"
        />
      </aside>

      {/* Coluna Direita de Acesso (Lavender Blush #F5EDF0 fiel ao Figma) */}
      <main
        id="conteudo-principal"
        className="relative flex flex-col justify-center items-center p-8 sm:p-14 bg-[#F5EDF0] dark:bg-[#14072E]"
      >
        {/* Botão de Tema (Lua / Sol) e atalhos diretos de rota no canto superior direito */}
        <div className="absolute top-6 right-6 flex items-center gap-3">
          <button
            type="button"
            onClick={() => router.push("/etapa-1")}
            className="text-xs font-semibold text-[#335C67] dark:text-[#F5EDF0] underline hover:text-[#E35336] transition-colors"
          >
            Ir para Etapa 1
          </button>
          <button
            type="button"
            onClick={() => router.push("/etapa-2")}
            className="text-xs font-semibold text-[#E35336] underline hover:opacity-80 transition-opacity"
          >
            Ir para Etapa 2
          </button>
          <button
            type="button"
            onClick={toggleDarkMode}
            aria-label={darkMode ? "Ativar modo claro" : "Ativar modo escuro"}
            className="p-2.5 rounded-full text-[#0D0221] dark:text-white hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
          >
            {darkMode ? <Sun className="w-5 h-5 text-[#E35336]" /> : <Moon className="w-5 h-5" />}
          </button>
        </div>

        <div className="w-full max-w-[420px] space-y-7">
          <div className="space-y-2">
            <h2 className="text-3xl font-extrabold tracking-tight text-[#0D0221] dark:text-white">
              Acesse sua conta
            </h2>
            <p className="text-sm sm:text-base text-[#0D0221]/65 dark:text-white/70 leading-relaxed">
              Entre para continuar criando caminhos de aprendizagem.
            </p>
          </div>

          <form onSubmit={handleLoginSubmit} className="space-y-5">
            {/* Campo E-mail */}
            <div className="space-y-2">
              <label
                htmlFor="login-email"
                className="block text-xs font-bold text-[#0D0221] dark:text-white"
              >
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
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-11 pr-4 py-3.5 rounded-xl bg-white dark:bg-[#0D0221] border border-black/10 dark:border-white/15 text-sm text-[#0D0221] dark:text-white shadow-sm focus:border-[#E35336] transition-colors"
                />
              </div>
            </div>

            {/* Campo Senha */}
            <div className="space-y-2">
              <label
                htmlFor="login-password"
                className="block text-xs font-bold text-[#0D0221] dark:text-white"
              >
                Senha
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
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-11 pr-11 py-3.5 rounded-xl bg-white dark:bg-[#0D0221] border border-black/10 dark:border-white/15 text-sm text-[#0D0221] dark:text-white shadow-sm focus:border-[#E35336] transition-colors"
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

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => router.push("/etapa-1")}
                className="text-xs font-bold text-[#335C67] dark:text-[#8cb6c2] hover:underline"
              >
                Esqueci minha senha
              </button>
            </div>

            {/* Botão Entrar (Fiery Terracotta #E35336 fiel ao Figma) */}
            <button
              type="submit"
              className="w-full py-3.5 px-6 rounded-xl bg-[#E35336] hover:bg-[#c94429] text-white font-bold text-sm flex items-center justify-center gap-2 shadow-[0_10px_25px_-5px_rgba(227,83,54,0.5)] transition-all"
            >
              <span>Entrar</span>
              <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </button>
          </form>

          <p className="text-center text-xs text-[#0D0221]/65 dark:text-white/65">
            Ainda não tem conta?{" "}
            <button
              type="button"
              onClick={() => router.push("/etapa-1")}
              className="font-bold text-[#335C67] dark:text-[#8cb6c2] hover:underline"
            >
              Criar conta
            </button>
          </p>
        </div>
      </main>
    </div>
  );
}
