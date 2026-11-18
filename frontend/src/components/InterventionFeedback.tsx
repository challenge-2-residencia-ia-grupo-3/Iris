"use client";

import React, { useId, useMemo, useRef, useState } from "react";
import { ClipboardCheck, Loader2, Plus } from "lucide-react";
import {
  EFICACIAS,
  historicoOrdenado,
  PerfilPortatilError,
  ROTULO_EFICACIA,
  resumoEficacia,
  type EficaciaIntervencao,
  type PerfilPedagogicoPortatil,
} from "@/services/portableProfile";
import {
  MAX_ESTRATEGIA,
  MAX_OBSERVACAO,
  registrarIntervencao,
  validarIntervencao,
  type NovaIntervencao,
} from "@/services/interventionHistory";

interface Props {
  perfil: PerfilPedagogicoPortatil;
  /** Nome legível por id de característica (catálogo). Sem ele, mostra o próprio id. */
  nomes?: Record<string, string>;
  onPerfilAtualizado: (perfil: PerfilPedagogicoPortatil) => void;
}

const VAZIO: NovaIntervencao = { estrategia: "", id_caracteristica: "", eficacia: "", observacao: "" };

const CLASSE_EFICACIA: Record<EficaciaIntervencao, string> = {
  alta: "bg-[#E1F2E5] text-[#14532D] dark:bg-[#1C3B26] dark:text-[#C8F0D4]",
  media: "bg-[#FFF1DC] text-[#5C2A00] dark:bg-[#4A2A08] dark:text-[#FFE2B8]",
  baixa: "bg-[#FDE4E1] text-[#7A1F14] dark:bg-[#4A1A14] dark:text-[#FFD0CA]",
};

/**
 * Registra se uma estratégia funcionou (eficácia alta, média ou baixa) para uma característica do perfil e mostra o
 * histórico. O servidor valida e devolve o perfil atualizado; nada fica no servidor (RNF-01).
 */
export function InterventionFeedback({ perfil, nomes = {}, onPerfilAtualizado }: Props) {
  const uid = useId();
  const [dados, setDados] = useState<NovaIntervencao>(VAZIO);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const estrategiaRef = useRef<HTMLInputElement>(null);

  const nome = (id: string) => nomes[id] ?? id;
  const historico = useMemo(() => historicoOrdenado(perfil), [perfil]);
  const resumo = useMemo(() => resumoEficacia(perfil), [perfil]);
  const recentesPrimeiro = useMemo(() => [...historico].reverse(), [historico]);

  const mudar = <K extends keyof NovaIntervencao>(campo: K, valor: NovaIntervencao[K]) => {
    setDados((d) => ({ ...d, [campo]: valor }));
    setErro(null);
  };

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (enviando) return;
    const problema = validarIntervencao(dados, perfil.caracteristicas_selecionadas);
    if (problema) {
      setErro(problema);
      setAviso(null);
      return;
    }
    setEnviando(true);
    setErro(null);
    setAviso(null);
    try {
      const atualizado = await registrarIntervencao(perfil, dados);
      onPerfilAtualizado(atualizado);
      setDados((d) => ({ ...VAZIO, id_caracteristica: d.id_caracteristica }));
      setAviso("Registro adicionado ao histórico do perfil.");
      estrategiaRef.current?.focus();
    } catch (err) {
      setErro(err instanceof PerfilPortatilError ? err.message : "Não foi possível registrar a eficácia.");
    } finally {
      setEnviando(false);
    }
  };

  const campo =
    "w-full min-h-[44px] rounded-lg border border-[#335C67]/40 dark:border-white/25 bg-white dark:bg-[#160A30] px-3 py-2 text-sm text-[#0D0221] dark:text-[#F5EDF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336]";

  return (
    <section aria-labelledby={`${uid}-titulo`} className="rounded-lg border border-[#335C67]/25 dark:border-white/15 p-3 space-y-3">
      <div className="flex items-center gap-2">
        <ClipboardCheck className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
        <h3 id={`${uid}-titulo`} className="text-sm font-extrabold">
          Eficácia das intervenções
        </h3>
      </div>
      <p className="text-xs text-[#0D0221]/75 dark:text-white/75">
        Registre se uma estratégia funcionou para o aluno. Descreva só o que foi feito e o que você observou; não inclua
        nome, laudo, diagnóstico ou medicação.
      </p>

      <form onSubmit={enviar} className="space-y-3" noValidate>
        <div>
          <label htmlFor={`${uid}-car`} className="block text-xs font-bold mb-1">
            Característica
          </label>
          <select
            id={`${uid}-car`}
            value={dados.id_caracteristica}
            onChange={(e) => mudar("id_caracteristica", e.target.value)}
            className={campo}
          >
            <option value="">Selecione…</option>
            {perfil.caracteristicas_selecionadas.map((id) => (
              <option key={id} value={id}>
                {nome(id)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor={`${uid}-est`} className="block text-xs font-bold mb-1">
            Estratégia utilizada
          </label>
          <input
            id={`${uid}-est`}
            ref={estrategiaRef}
            type="text"
            value={dados.estrategia}
            maxLength={MAX_ESTRATEGIA}
            onChange={(e) => mudar("estrategia", e.target.value)}
            placeholder="Ex.: fragmentação da prova em checklist"
            className={campo}
          />
        </div>

        <fieldset>
          <legend className="text-xs font-bold mb-1">Eficácia</legend>
          <div className="flex flex-wrap gap-2">
            {EFICACIAS.map((ef) => {
              const marcado = dados.eficacia === ef;
              return (
                <label
                  key={ef}
                  className={`inline-flex items-center gap-2 min-h-[44px] px-4 rounded-lg border text-sm font-bold cursor-pointer focus-within:ring-2 focus-within:ring-[#E35336] ${
                    marcado
                      ? "border-[#E35336] bg-[#E35336]/10"
                      : "border-[#335C67]/40 dark:border-white/25 bg-white dark:bg-[#160A30]"
                  }`}
                >
                  <input
                    type="radio"
                    name={`${uid}-eficacia`}
                    value={ef}
                    checked={marcado}
                    onChange={() => mudar("eficacia", ef)}
                    className="accent-[#E35336]"
                  />
                  {ROTULO_EFICACIA[ef]}
                </label>
              );
            })}
          </div>
        </fieldset>

        <div>
          <label htmlFor={`${uid}-obs`} className="block text-xs font-bold mb-1">
            Observação pedagógica <span className="font-normal">(opcional)</span>
          </label>
          <textarea
            id={`${uid}-obs`}
            rows={3}
            value={dados.observacao}
            maxLength={MAX_OBSERVACAO}
            onChange={(e) => mudar("observacao", e.target.value)}
            placeholder="Ex.: terminou a prova inteira e ficou mais calmo."
            aria-describedby={`${uid}-cont`}
            className={campo}
          />
          <p id={`${uid}-cont`} className="mt-1 text-[11px] text-[#0D0221]/70 dark:text-white/70">
            {dados.observacao.length}/{MAX_OBSERVACAO} caracteres
          </p>
        </div>

        <button
          type="submit"
          disabled={enviando}
          className="inline-flex items-center gap-1.5 min-h-[44px] px-4 rounded-xl text-sm font-bold bg-[#335C67] hover:bg-[#274851] text-white disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        >
          {enviando ? (
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
          ) : (
            <Plus className="w-4 h-4" aria-hidden="true" />
          )}
          {enviando ? "Registrando…" : "Registrar eficácia"}
        </button>
      </form>

      <div aria-live="polite" className="space-y-1">
        {erro && (
          <p role="alert" className="text-xs font-bold text-red-700 dark:text-red-300">
            {erro}
          </p>
        )}
        {aviso && (
          <p role="status" className="text-xs font-bold text-[#14532D] dark:text-[#C8F0D4]">
            {aviso}
          </p>
        )}
      </div>

      <div>
        <h4 className="text-xs font-extrabold text-[#335C67] dark:text-[#9fd0de]">
          Histórico ({historico.length})
        </h4>
        {historico.length === 0 ? (
          <p className="text-xs text-[#0D0221]/70 dark:text-white/70 mt-1">Nenhuma intervenção registrada ainda.</p>
        ) : (
          <>
            <ul className="mt-1 space-y-1 text-xs" aria-label="Resumo por característica">
              {Object.entries(resumo).map(([id, r]) => (
                <li key={id}>
                  <span className="font-bold">{nome(id)}:</span> alta {r.alta} • média {r.media} • baixa {r.baixa}
                  {" "}(última: {ROTULO_EFICACIA[r.ultima].toLowerCase()})
                </li>
              ))}
            </ul>
            <ol className="mt-2 space-y-2" aria-label="Intervenções registradas, das mais recentes para as mais antigas">
              {recentesPrimeiro.map((r, i) => (
                <li
                  key={`${r.registrado_em}-${i}`}
                  className="rounded-lg bg-[#F5EDF0]/70 dark:bg-black/25 p-2.5 text-xs space-y-1"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-bold">{r.estrategia}</span>
                    <span className={`px-2 py-0.5 rounded-full font-bold ${CLASSE_EFICACIA[r.eficacia]}`}>
                      Eficácia {ROTULO_EFICACIA[r.eficacia].toLowerCase()}
                    </span>
                  </div>
                  <p className="text-[#0D0221]/75 dark:text-white/75">
                    {nome(r.id_caracteristica)} • {new Date(r.registrado_em).toLocaleDateString("pt-BR")}
                  </p>
                  {r.observacao && <p>{r.observacao}</p>}
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </section>
  );
}
