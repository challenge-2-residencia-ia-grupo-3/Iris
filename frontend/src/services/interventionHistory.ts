/**
 * Registro de eficácia das intervenções no perfil portátil (História 3.1.2 — Issue #27, RF-15, RNF-01, RNF-03).
 *
 * O servidor valida o registro (inclusive o bloqueio de laudo/CID/diagnóstico/medicação) e devolve o perfil com o
 * histórico atualizado. Ele não guarda nada: o perfil continua só com o docente (memória e `localStorage`).
 */
import {
  EFICACIAS,
  type EficaciaIntervencao,
  PerfilPortatilError,
  type PerfilPedagogicoPortatil,
} from "./portableProfile";

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const ROTA_INTERVENCOES = "/api/v1/perfil/intervencoes";
export const MAX_ESTRATEGIA = 300;
export const MIN_ESTRATEGIA = 3;
export const MAX_OBSERVACAO = 500;

export interface NovaIntervencao {
  estrategia: string;
  id_caracteristica: string;
  eficacia: EficaciaIntervencao | "";
  observacao: string;
}

/** Confere o formulário antes de chamar o servidor. Devolve a mensagem de erro ou null. */
export function validarIntervencao(dados: NovaIntervencao, idsDoPerfil: readonly string[]): string | null {
  if (!dados.id_caracteristica || !idsDoPerfil.includes(dados.id_caracteristica)) {
    return "Escolha a característica em que a estratégia foi usada.";
  }
  const estrategia = dados.estrategia.trim();
  if (estrategia.length < MIN_ESTRATEGIA) return "Descreva a estratégia usada (mínimo de 3 caracteres).";
  if (estrategia.length > MAX_ESTRATEGIA) return `A estratégia deve ter no máximo ${MAX_ESTRATEGIA} caracteres.`;
  if (!EFICACIAS.includes(dados.eficacia as EficaciaIntervencao)) return "Escolha a eficácia: alta, média ou baixa.";
  if (dados.observacao.trim().length > MAX_OBSERVACAO) {
    return `A observação deve ter no máximo ${MAX_OBSERVACAO} caracteres.`;
  }
  return null;
}

/** Envia o perfil e o registro; devolve o perfil atualizado. Nada é guardado no servidor. */
export async function registrarIntervencao(
  perfil: PerfilPedagogicoPortatil,
  dados: NovaIntervencao
): Promise<PerfilPedagogicoPortatil> {
  const erro = validarIntervencao(dados, perfil.caracteristicas_selecionadas);
  if (erro) throw new PerfilPortatilError(erro, "INVALID_INTERVENTION");

  let resposta: Response;
  try {
    resposta = await fetch(`${API_BASE_URL}${ROTA_INTERVENCOES}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        perfil,
        intervencao: {
          estrategia: dados.estrategia.trim(),
          id_caracteristica: dados.id_caracteristica,
          eficacia: dados.eficacia,
          observacao: dados.observacao.trim() || null,
        },
      }),
      cache: "no-store",
    });
  } catch {
    throw new PerfilPortatilError(
      "Não foi possível falar com o servidor para validar o registro. Tente de novo em instantes.",
      "INTERVENTION_SERVER_UNAVAILABLE"
    );
  }

  const corpo = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    const detalhe = corpo?.detail;
    const mensagem =
      typeof detalhe === "object" && detalhe?.detail ? String(detalhe.detail) : "O servidor recusou o registro.";
    throw new PerfilPortatilError(mensagem, detalhe?.code ?? "INTERVENTION_REJECTED");
  }
  if (!corpo?.perfil || typeof corpo.perfil !== "object") {
    throw new PerfilPortatilError("Resposta inesperada do servidor.", "INTERVENTION_BAD_RESPONSE");
  }
  return corpo.perfil as PerfilPedagogicoPortatil;
}
