import React from "react";

/** Texto com **negrito** do Agente Adaptador, sem mostrar os asteriscos. */
export function Negrito({ texto }: { texto: string }) {
  return (
    <>
      {texto.split(/(\*\*[^*\n]+\*\*)/g).map((parte, i) =>
        /^\*\*[^*\n]+\*\*$/.test(parte) ? <strong key={i}>{parte.slice(2, -2)}</strong> : <React.Fragment key={i}>{parte}</React.Fragment>
      )}
    </>
  );
}

/** `[ ]` e `[x]` do andaime viram uma caixa de conferência desenhada, com nome para leitor de tela. */
function ComCaixas({ linha }: { linha: string }) {
  return (
    <>
      {linha.split(/(\[[ xX]\])/g).map((parte, i) => {
        if (!/^\[[ xX]\]$/.test(parte)) return <Negrito key={i} texto={parte} />;
        const marcada = parte !== "[ ]";
        return (
          <span key={i} role="img" aria-label={marcada ? "caixa marcada" : "caixa para marcar"} className="inline-block align-[-0.2em]">
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false" className="inline-block">
              <rect x="1.5" y="1.5" width="13" height="13" rx="2" fill="none" stroke="currentColor" strokeWidth="1.6" />
              {marcada && <path d="M4.5 8.5l2.5 2.5 4.5-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />}
            </svg>
          </span>
        );
      })}
    </>
  );
}

interface PreviaProps {
  texto: string;
  /** Número da questão, para o nome acessível do bloco. */
  numero: number;
}

/**
 * Como o aluno verá a questão adaptada: o mesmo texto da caixa de edição, sem a marcação (`**negrito**`,
 * `[ ]`). Acompanha o que o professor digita. A caixa de edição continua sendo a fonte de verdade.
 */
export function PreviaAdaptada({ texto, numero }: PreviaProps) {
  const linhas = texto.split("\n");
  return (
    <div
      role="group"
      aria-label={`Como o aluno verá a questão ${numero}`}
      data-testid={`previa-adaptada-${numero}`}
      className="mt-2 rounded-md border border-dashed border-slate-400 bg-slate-50 p-2 text-sm text-slate-900 dark:border-slate-500 dark:bg-slate-800 dark:text-slate-100"
    >
      <p className="mb-1 text-xs font-semibold uppercase text-slate-700 dark:text-slate-300">Como o aluno verá</p>
      {texto.trim() === "" ? (
        <p className="text-slate-700 dark:text-slate-300">A versão adaptada está vazia.</p>
      ) : (
        <div className="space-y-1 break-words">
          {linhas.map((linha, i) =>
            linha.trim() === "" ? <div key={i} className="h-2" aria-hidden="true" /> : (
              <p key={i} className="whitespace-pre-wrap">
                <ComCaixas linha={linha} />
              </p>
            )
          )}
        </div>
      )}
    </div>
  );
}
