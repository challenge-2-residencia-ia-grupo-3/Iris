"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import { CheckCircle2, FileJson, Loader2, TriangleAlert, Undo2, Upload } from "lucide-react";
import {
  clearSurgicalSelectionFromSession,
  ENGAGEMENT_PROFILE_STORAGE_KEY,
  loadSurgicalSelectionFromSession,
} from "@/services/catalogsApi";
import { STEP5_ADAPTACAO_STORAGE_KEY } from "@/services/comparisonCards";
import { STEP4_RESULT_STORAGE_KEY } from "@/services/agentsApi";
import { PerfilPortatilError } from "@/services/portableProfile";
import {
  carregarRestauracaoDaSessao,
  importarPerfilDeArquivo,
  limparRestauracaoDaSessao,
  ROTULO_NIVEL_ANDAIME,
  salvarRestauracaoNaSessao,
  type ResultadoImportacao,
} from "@/services/portableProfileImport";
import { clearScaffoldingFromSession, loadScaffoldingFromSession } from "@/services/scaffoldingApi";

/**
 * Importa o `.json` do Perfil Pedagógico Portátil no início do fluxo (História 3.2.2, RF-15).
 * O arquivo é lido no navegador; o que vai para a sessão são só os identificadores das características e a sugestão
 * de nível, e a pré-seleção aparece nas Etapas 2 e 3 para o docente conferir. Nada é guardado no servidor.
 */
export function PerfilImport() {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [pendente, setPendente] = useState<ResultadoImportacao | null>(null);
  const [aplicado, setAplicado] = useState<string | null>(null);

  // Lê a sessão só no navegador (evita divergência entre a renderização do servidor e a do cliente).
  useEffect(() => {
    setAplicado(carregarRestauracaoDaSessao()?.codigo_anonimo ?? null);
  }, []);

  const temNaSessao = (chave: string) => {
    try {
      return window.sessionStorage.getItem(chave) !== null;
    } catch {
      return false;
    }
  };
  const apagarDaSessao = (...chaves: string[]) => {
    try {
      chaves.forEach((c) => window.sessionStorage.removeItem(c));
    } catch {
      // sessionStorage indisponível: nada a limpar
    }
  };

  /** Interesses e resultado das Etapas 4 e 5 de outro estudante não podem sobreviver à troca de perfil. */
  const jaTemSelecao = () =>
    loadSurgicalSelectionFromSession() !== null ||
    loadScaffoldingFromSession() !== null ||
    temNaSessao(ENGAGEMENT_PROFILE_STORAGE_KEY) ||
    temNaSessao(STEP4_RESULT_STORAGE_KEY) ||
    temNaSessao(STEP5_ADAPTACAO_STORAGE_KEY);

  const aoEscolher = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const arquivo = e.target.files?.[0];
    e.target.value = ""; // permite escolher o mesmo arquivo de novo depois de um erro
    if (!arquivo) return;
    setErro(null);
    setPendente(null);
    setCarregando(true);
    try {
      setPendente(await importarPerfilDeArquivo(arquivo));
    } catch (err) {
      setErro(
        err instanceof PerfilPortatilError
          ? err.message
          : "Não foi possível importar o arquivo. Tente de novo com o .json exportado pela plataforma."
      );
    } finally {
      setCarregando(false);
    }
  };

  const aplicar = () => {
    if (!pendente) return;
    // O docente escolheu o perfil: ele substitui tudo o que já existia nesta sessão (seleção, calibração,
    // interesses e o resultado das Etapas 4 e 5, que podem ser de outro estudante).
    clearSurgicalSelectionFromSession();
    clearScaffoldingFromSession();
    apagarDaSessao(ENGAGEMENT_PROFILE_STORAGE_KEY, STEP4_RESULT_STORAGE_KEY, STEP5_ADAPTACAO_STORAGE_KEY);
    salvarRestauracaoNaSessao(pendente.restaurado);
    setAplicado(pendente.restaurado.codigo_anonimo);
    setPendente(null);
  };

  /** "Cancelar" só descarta a prévia: o perfil que já estava aplicado continua valendo. */
  const cancelarPrevia = () => {
    setPendente(null);
    setErro(null);
  };

  /** Desfaz o perfil aplicado e o que veio dele: a seleção da Etapa 2 e o nível da Etapa 3. */
  const removerAplicado = () => {
    limparRestauracaoDaSessao();
    clearSurgicalSelectionFromSession();
    clearScaffoldingFromSession();
    setAplicado(null);
    setPendente(null);
    setErro(null);
  };

  const r = pendente?.restaurado;

  return (
    <section
      aria-labelledby="titulo-importar-perfil"
      className="bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 rounded-2xl p-5 shadow-sm space-y-3 hc-surface"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <h2 id="titulo-importar-perfil" className="text-base font-bold flex items-center gap-2">
            <FileJson className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
            Já tem um perfil pedagógico portátil?
          </h2>
          <p id={`${inputId}-ajuda`} className="text-sm text-[#335C67] dark:text-[#C9B8D9]">
            Importe o arquivo .json recebido da coordenação ou do AEE para pré-marcar as características e o nível de
            suporte nas próximas etapas. O arquivo é lido neste navegador e nada é guardado no servidor.
          </p>
        </div>
        <div className="flex-shrink-0">
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            accept=".json,application/json"
            hidden
            tabIndex={-1}
            aria-label="Arquivo .json do perfil pedagógico portátil"
            onChange={aoEscolher}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={carregando}
            aria-describedby={`${inputId}-ajuda`}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-[#335C67] hover:bg-[#274851] text-white disabled:opacity-60 transition-colors"
          >
            {carregando ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <Upload className="w-3.5 h-3.5" aria-hidden="true" />
            )}
            {carregando ? "Lendo o arquivo…" : "Importar perfil (.json)"}
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {erro && (
          <div
            role="alert"
            data-testid="erro-importacao"
            className="flex items-start gap-2 rounded-xl border border-red-300 bg-red-50 text-red-900 dark:bg-[#3A1212] dark:text-red-100 dark:border-red-500/40 p-3 text-sm"
          >
            <TriangleAlert className="w-4 h-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
            <div>
              <p className="font-bold">Não foi possível importar o perfil</p>
              <p>{erro}</p>
              <p className="mt-1 text-xs">Você pode continuar normalmente sem importar nada.</p>
            </div>
          </div>
        )}

        {pendente && r && (
          <div
            role="status"
            data-testid="previa-importacao"
            className="rounded-xl border border-[#335C67]/30 dark:border-white/20 p-3 text-sm space-y-2"
          >
            <p className="font-bold">
              Perfil <span className="font-mono">{r.codigo_anonimo}</span> lido com sucesso
              {pendente.origem === "local" ? " (validado neste navegador, servidor indisponível)" : ""}
            </p>
            <ul className="list-disc pl-5 space-y-0.5">
              <li>
                {r.caracteristicas.length} característica{r.caracteristicas.length === 1 ? "" : "s"} funciona
                {r.caracteristicas.length === 1 ? "l" : "is"} para pré-marcar na Etapa 2
                {r.alta_eficacia.length > 0 ? ` (${r.alta_eficacia.length} com eficácia alta no histórico)` : ""}.
              </li>
              <li>
                {r.nivel_andaime
                  ? `Nível de suporte sugerido para a Etapa 3: ${ROTULO_NIVEL_ANDAIME[r.nivel_andaime]}. ${r.motivo_nivel}`
                  : r.motivo_nivel}
              </li>
            </ul>
            {jaTemSelecao() && (
              <p className="flex items-start gap-1.5 text-xs font-semibold text-[#7A3E00] dark:text-[#FFD9A8]">
                <TriangleAlert className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" aria-hidden="true" />
                Aplicar este perfil substitui o que já está na sessão: a seleção de características, a calibração do nível, os interesses e o resultado das Etapas 4 e 5.
              </p>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                onClick={aplicar}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-[#E35336] hover:bg-[#C8432A] text-white transition-colors"
              >
                <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                Aplicar ao fluxo
              </button>
              <button
                type="button"
                onClick={cancelarPrevia}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold border border-[#335C67]/40 hover:bg-[#335C67]/10 transition-colors"
              >
                Cancelar
              </button>
            </div>
          </div>
        )}

        {aplicado && !pendente && (
          <div
            role="status"
            data-testid="perfil-aplicado"
            className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-emerald-300 bg-emerald-50 text-emerald-950 dark:bg-[#12301F] dark:text-emerald-100 dark:border-emerald-500/40 p-3 text-sm"
          >
            <p className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
              Perfil <span className="font-mono">{aplicado}</span> aplicado. As características serão pré-marcadas na
              Etapa 2 e você poderá alterá-las. Remover o perfil também desfaz a seleção e o nível que vieram dele.
            </p>
            <button
              type="button"
              onClick={removerAplicado}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border border-emerald-700/40 hover:bg-emerald-700/10 transition-colors"
            >
              <Undo2 className="w-3.5 h-3.5" aria-hidden="true" />
              Remover perfil importado
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
