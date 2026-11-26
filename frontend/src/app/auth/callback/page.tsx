"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2 } from "lucide-react";
import { IrisLogoBanner } from "@/components/IrisLogoBanner";
import { useAuth } from "@/contexts/AuthContext";
import { AuthApiError } from "@/services/authApi";

export default function OAuthCallbackPage() {
  const router = useRouter();
  const { completeOAuthExchange } = useAuth();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const params = new URLSearchParams(window.location.search);
    const err = params.get("error");
    const code = params.get("code");
    const nextRaw = params.get("next") || "/historico";
    const safeNext = nextRaw.startsWith("/") && !nextRaw.startsWith("//") ? nextRaw : "/historico";

    if (err) {
      setErrorMsg(`Autenticação com o Google não concluída (${err}).`);
      return;
    }
    if (!code) {
      setErrorMsg("Código de confirmação OAuth ausente na URL de retorno.");
      return;
    }

    completeOAuthExchange(code)
      .then(() => {
        router.replace(safeNext);
      })
      .catch((e) => {
        setErrorMsg(
          e instanceof AuthApiError ? e.message : "Não foi possível validar sua sessão com o Google."
        );
      });
  }, [completeOAuthExchange, router]);

  return (
    <main
      id="conteudo-principal"
      className="min-h-screen flex flex-col items-center justify-center gap-6 bg-[#F5EDF0] dark:bg-[#0D0221] p-6 text-[#0D0221] dark:text-[#F5EDF0]"
    >
      <IrisLogoBanner compact />
      {errorMsg ? (
        <div
          role="alert"
          className="max-w-md w-full rounded-2xl border border-red-700/40 bg-white dark:bg-[#160A30] p-6 space-y-4 text-center shadow-sm"
        >
          <AlertTriangle className="w-8 h-8 text-[#C9411F] mx-auto" aria-hidden="true" />
          <h1 className="text-lg font-extrabold">Falha ao entrar com Google</h1>
          <p className="text-sm opacity-85">{errorMsg}</p>
          <div className="flex justify-center gap-3">
            <Link
              href="/"
              className="inline-flex min-h-[44px] items-center px-4 py-2 rounded-xl bg-[#C9411F] text-white text-xs font-bold"
            >
              Voltar para o login
            </Link>
            <Link
              href="/etapa-1"
              className="inline-flex min-h-[44px] items-center px-4 py-2 rounded-xl border border-black/15 dark:border-white/20 text-xs font-bold"
            >
              Modo Convidado
            </Link>
          </div>
        </div>
      ) : (
        <div role="status" className="flex items-center gap-3 text-sm font-semibold">
          <Loader2 className="w-5 h-5 animate-spin text-[#C9411F]" aria-hidden="true" />
          <span>Concluindo acesso com sua conta Google…</span>
        </div>
      )}
    </main>
  );
}
