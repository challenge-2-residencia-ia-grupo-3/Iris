/**
 * Perfil Pedagógico Portátil (História 3.1.1 — Issue #26, RF-15, RNF-01).
 *
 * O perfil é montado e baixado inteiramente no navegador: este módulo NÃO usa fetch, localStorage,
 * sessionStorage, IndexedDB nem cookies. Nada do perfil chega ao servidor; quem guarda o arquivo é o docente.
 * O formato espelha `backend/src/iris/schemas/portable_profile.py` (versão 1.0).
 */

export const PREFIXO_CODIGO = "aluno-";
export const PADRAO_CODIGO = /^aluno-[0-9a-f]{8,32}$/;
export const PADRAO_ID_CARACTERISTICA = /^[a-z][a-z0-9_]{5,80}$/;
export const MAX_CARACTERISTICAS = 50;

export type EficaciaIntervencao = "alta" | "media" | "baixa";
export const EFICACIAS: readonly EficaciaIntervencao[] = ["alta", "media", "baixa"];
export const ROTULO_EFICACIA: Record<EficaciaIntervencao, string> = { alta: "Alta", media: "Média", baixa: "Baixa" };
export const MAX_INTERVENCOES = 200;

/** Eficácia de uma estratégia para uma característica (História 3.1.2 — Issue #27). Espelha `RegistroIntervencao`. */
export interface RegistroIntervencao {
  estrategia: string;
  id_caracteristica: string;
  eficacia: EficaciaIntervencao;
  observacao: string | null;
  registrado_em: string; // ISO 8601 em UTC
}

export interface PerfilPedagogicoPortatil {
  versao_schema: "1.0";
  codigo_anonimo: string;
  criado_em: string; // ISO 8601 em UTC
  caracteristicas_selecionadas: string[];
  barreiras_observadas: [];
  historico_estrategias: [];
  anotacoes_pedagogicas: [];
  /** Só existe depois do primeiro registro de eficácia: perfis anteriores à #27 continuam válidos. */
  historico_intervencoes?: RegistroIntervencao[];
}

export class PerfilPortatilError extends Error {
  constructor(message: string, public readonly code: string) {
    super(message);
    this.name = "PerfilPortatilError";
  }
}

/** Aleatoriedade criptográfica do navegador; nunca Math.random (previsível). */
export function gerarCodigoAnonimo(nHex = 8): string {
  if (!Number.isInteger(nHex) || nHex < 8 || nHex > 32) {
    throw new PerfilPortatilError("O código anônimo deve ter entre 8 e 32 dígitos hexadecimais.", "INVALID_CODE_LENGTH");
  }
  const c = globalThis.crypto;
  if (!c || typeof c.getRandomValues !== "function") {
    throw new PerfilPortatilError("Este navegador não oferece gerador aleatório seguro.", "NO_SECURE_RANDOM");
  }
  const bytes = new Uint8Array(Math.ceil(nHex / 2));
  c.getRandomValues(bytes);
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").slice(0, nHex);
  return `${PREFIXO_CODIGO}${hex}`;
}

/**
 * Cria o perfil em memória. Recebe só os IDs das características: não há parâmetro para nome,
 * turma, escola ou qualquer dado do estudante.
 */
export function criarPerfilPortatil(
  caracteristicasSelecionadas: readonly string[],
  idsValidos?: Iterable<string>,
  agora: Date = new Date()
): PerfilPedagogicoPortatil {
  const ids = Array.from(new Set(caracteristicasSelecionadas.map((i) => i.trim()).filter(Boolean)));
  if (ids.length === 0) {
    throw new PerfilPortatilError("Selecione ao menos uma característica funcional para gerar o perfil.", "EMPTY_SELECTION");
  }
  if (ids.length > MAX_CARACTERISTICAS) {
    throw new PerfilPortatilError(`O perfil aceita no máximo ${MAX_CARACTERISTICAS} características.`, "TOO_MANY");
  }
  const malFormados = ids.filter((i) => !PADRAO_ID_CARACTERISTICA.test(i));
  if (malFormados.length > 0) {
    throw new PerfilPortatilError("Há identificador de característica em formato inválido.", "INVALID_CHARACTERISTIC_ID");
  }
  if (idsValidos) {
    const ok = new Set(idsValidos);
    const desconhecidos = ids.filter((i) => !ok.has(i));
    if (desconhecidos.length > 0) {
      throw new PerfilPortatilError(
        `Característica(s) fora do catálogo: ${desconhecidos.join(", ")}.`,
        "UNKNOWN_CHARACTERISTIC_ID"
      );
    }
  }
  return {
    versao_schema: "1.0",
    codigo_anonimo: gerarCodigoAnonimo(),
    criado_em: agora.toISOString(),
    caracteristicas_selecionadas: ids,
    barreiras_observadas: [],
    historico_estrategias: [],
    anotacoes_pedagogicas: [],
  };
}

/** Histórico em ordem cronológica (do mais antigo ao mais recente); empate mantém a ordem de entrada. */
export function historicoOrdenado(perfil: Pick<PerfilPedagogicoPortatil, "historico_intervencoes">): RegistroIntervencao[] {
  return (perfil.historico_intervencoes ?? [])
    .map((r, i) => ({ r, i, t: Date.parse(r.registrado_em) }))
    .sort((a, b) => (a.t - b.t) || (a.i - b.i))
    .map(({ r }) => r);
}

/** Por característica: contagem por nível e eficácia do registro mais recente. */
export function resumoEficacia(
  perfil: Pick<PerfilPedagogicoPortatil, "historico_intervencoes">
): Record<string, Record<EficaciaIntervencao, number> & { total: number; ultima: EficaciaIntervencao }> {
  const out: Record<string, Record<EficaciaIntervencao, number> & { total: number; ultima: EficaciaIntervencao }> = {};
  for (const r of historicoOrdenado(perfil)) {
    const item = (out[r.id_caracteristica] ??= { alta: 0, media: 0, baixa: 0, total: 0, ultima: r.eficacia });
    item[r.eficacia] += 1;
    item.total += 1;
    item.ultima = r.eficacia;
  }
  return out;
}

export function perfilParaJson(perfil: PerfilPedagogicoPortatil): string {
  return JSON.stringify(perfil, null, 2);
}

export function nomeArquivoPerfil(perfil: PerfilPedagogicoPortatil): string {
  return `perfil-${perfil.codigo_anonimo}.json`;
}

/** Dispara o download de um Blob no dispositivo do docente. Não envia nada pela rede. */
export function baixarBlob(blob: Blob, nome: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Entrega o JSON como download local (Blob). Funciona offline: não envia nada pela rede. */
export function baixarPerfil(perfil: PerfilPedagogicoPortatil): void {
  baixarBlob(new Blob([perfilParaJson(perfil)], { type: "application/json" }), nomeArquivoPerfil(perfil));
}
