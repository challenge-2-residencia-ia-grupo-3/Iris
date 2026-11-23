/**
 * Persistência local anônima de Perfis Pedagógicos Portáteis no `localStorage` do navegador (RNF-01).
 *
 * Guarda EXCLUSIVAMENTE perfis anônimos (`codigo_anonimo` aleatório + características funcionais),
 * sem nome do estudante, matrícula, escola, dados civis ou informações clínicas.
 * Nada é enviado ou salvo no servidor.
 */

import {
  EFICACIAS,
  type EficaciaIntervencao,
  MAX_CARACTERISTICAS,
  MAX_INTERVENCOES,
  PADRAO_CODIGO,
  PADRAO_ID_CARACTERISTICA,
  type PerfilPedagogicoPortatil,
  PerfilPortatilError,
  type RegistroIntervencao,
} from "./portableProfile";

export const LOCAL_PROFILES_STORAGE_KEY = "iris_local_perfis_portateis_v1";
export const MAX_LOCAL_PROFILES = 100;

const ALLOWED_PROFILE_KEYS = new Set([
  "versao_schema",
  "codigo_anonimo",
  "criado_em",
  "caracteristicas_selecionadas",
  "barreiras_observadas",
  "historico_estrategias",
  "historico_intervencoes",
  "anotacoes_pedagogicas",
]);

const FORBIDDEN_PERSONAL_OR_CLINICAL_KEYS = new Set([
  "nome",
  "nome_aluno",
  "aluno",
  "cpf",
  "rg",
  "matricula",
  "escola",
  "email",
  "telefone",
  "turma",
  "laudo",
  "cid",
  "diagnostico",
  "medicacao",
]);

function getLocalStorage(): Storage | null {
  if (typeof globalThis === "undefined") return null;
  const candidate = (globalThis as { localStorage?: Storage }).localStorage;
  if (!candidate || typeof candidate.getItem !== "function" || typeof candidate.setItem !== "function") {
    return null;
  }
  return candidate;
}

/** Mantém só registros de intervenção bem formados; qualquer outra chave do registro é descartada. */
function sanitizarIntervencoes(raw: unknown): RegistroIntervencao[] {
  if (!Array.isArray(raw)) return [];
  const out: RegistroIntervencao[] = [];
  for (const item of raw.slice(0, MAX_INTERVENCOES)) {
    if (!item || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    if (
      typeof r.estrategia !== "string" ||
      r.estrategia.trim().length < 3 ||
      typeof r.id_caracteristica !== "string" ||
      !PADRAO_ID_CARACTERISTICA.test(r.id_caracteristica) ||
      !EFICACIAS.includes(r.eficacia as EficaciaIntervencao) ||
      typeof r.registrado_em !== "string" ||
      Number.isNaN(Date.parse(r.registrado_em))
    ) {
      continue;
    }
    out.push({
      estrategia: r.estrategia.trim(),
      id_caracteristica: r.id_caracteristica,
      eficacia: r.eficacia as EficaciaIntervencao,
      observacao: typeof r.observacao === "string" && r.observacao.trim() ? r.observacao.trim() : null,
      registrado_em: r.registrado_em,
    });
  }
  return out;
}

/**
 * Valida e normaliza um objeto de perfil antes de gravar ou ler do `localStorage`,
 * garantindo ausência de nome, dados pessoais ou campos clínicos extras.
 */
export function sanitizarPerfilParaLocalStorage(raw: unknown): PerfilPedagogicoPortatil {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new PerfilPortatilError("Estrutura de perfil inválida.", "INVALID_PROFILE_SCHEMA");
  }

  const record = raw as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    const normalizedKey = key.trim().toLowerCase();
    if (FORBIDDEN_PERSONAL_OR_CLINICAL_KEYS.has(normalizedKey)) {
      throw new PerfilPortatilError(
        `Campo '${key}' proibido no armazenamento local: o perfil não pode conter dados pessoais ou clínicos.`,
        "FORBIDDEN_PERSONAL_DATA"
      );
    }
    if (!ALLOWED_PROFILE_KEYS.has(key)) {
      throw new PerfilPortatilError(
        `Campo '${key}' não faz parte do schema oficial do Perfil Pedagógico Portátil.`,
        "INVALID_PROFILE_SCHEMA"
      );
    }
  }

  if (record.versao_schema !== "1.0") {
    throw new PerfilPortatilError("Versão de schema do perfil não suportada.", "INVALID_PROFILE_SCHEMA");
  }

  if (typeof record.codigo_anonimo !== "string" || !PADRAO_CODIGO.test(record.codigo_anonimo)) {
    throw new PerfilPortatilError(
      "O código do perfil deve seguir o padrão anônimo 'aluno-<hex>'.",
      "INVALID_ANONYMOUS_CODE"
    );
  }

  if (typeof record.criado_em !== "string" || Number.isNaN(Date.parse(record.criado_em))) {
    throw new PerfilPortatilError("Data de criação do perfil inválida.", "INVALID_PROFILE_SCHEMA");
  }

  if (!Array.isArray(record.caracteristicas_selecionadas)) {
    throw new PerfilPortatilError("Lista de características selecionadas inválida.", "INVALID_PROFILE_SCHEMA");
  }

  const ids = Array.from(
    new Set(
      record.caracteristicas_selecionadas
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );

  if (ids.length === 0 || ids.length > MAX_CARACTERISTICAS) {
    throw new PerfilPortatilError("Quantidade de características inválida para o perfil.", "INVALID_PROFILE_SCHEMA");
  }

  if (ids.some((id) => !PADRAO_ID_CARACTERISTICA.test(id))) {
    throw new PerfilPortatilError("Identificador de característica inválido no perfil.", "INVALID_CHARACTERISTIC_ID");
  }

  const perfil: PerfilPedagogicoPortatil = {
    versao_schema: "1.0",
    codigo_anonimo: record.codigo_anonimo,
    criado_em: record.criado_em,
    caracteristicas_selecionadas: ids,
    barreiras_observadas: Array.isArray(record.barreiras_observadas) ? (record.barreiras_observadas as []) : [],
    historico_estrategias: Array.isArray(record.historico_estrategias) ? (record.historico_estrategias as []) : [],
    anotacoes_pedagogicas: Array.isArray(record.anotacoes_pedagogicas) ? (record.anotacoes_pedagogicas as []) : [],
  };
  if ("historico_intervencoes" in record) {
    perfil.historico_intervencoes = sanitizarIntervencoes(record.historico_intervencoes);
  }
  return perfil;
}

/**
 * Lista todos os perfis anônimos salvos localmente no `localStorage` (mais recentes primeiro).
 */
export function listarPerfisLocais(): PerfilPedagogicoPortatil[] {
  const storage = getLocalStorage();
  if (!storage) return [];

  try {
    const raw = storage.getItem(LOCAL_PROFILES_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    const validos: PerfilPedagogicoPortatil[] = [];
    const vistos = new Set<string>();
    for (const item of parsed) {
      try {
        const limpo = sanitizarPerfilParaLocalStorage(item);
        if (!vistos.has(limpo.codigo_anonimo)) {
          vistos.add(limpo.codigo_anonimo);
          validos.push(limpo);
        }
      } catch {
        // Descarta entradas corrompidas ou fora do schema anônimo
      }
    }

    return validos.sort((a, b) => Date.parse(b.criado_em) - Date.parse(a.criado_em));
  } catch {
    return [];
  }
}

/**
 * Salva um perfil anônimo no `localStorage` do navegador (sem dados pessoais ou clínicos).
 */
export function salvarPerfilLocal(perfil: PerfilPedagogicoPortatil): PerfilPedagogicoPortatil[] {
  const limpo = sanitizarPerfilParaLocalStorage(perfil);
  const atuais = listarPerfisLocais().filter((p) => p.codigo_anonimo !== limpo.codigo_anonimo);
  const atualizados = [limpo, ...atuais].slice(0, MAX_LOCAL_PROFILES);

  const storage = getLocalStorage();
  if (storage) {
    try {
      storage.setItem(LOCAL_PROFILES_STORAGE_KEY, JSON.stringify(atualizados));
    } catch {
      // Ignora caso localStorage esteja bloqueado ou com cota excedida
    }
  }
  return atualizados;
}

/**
 * Remove um perfil específico do `localStorage` pelo seu código anônimo.
 */
export function removerPerfilLocal(codigoAnonimo: string): PerfilPedagogicoPortatil[] {
  const atualizados = listarPerfisLocais().filter((p) => p.codigo_anonimo !== codigoAnonimo);
  const storage = getLocalStorage();
  if (storage) {
    try {
      if (atualizados.length === 0) {
        storage.removeItem(LOCAL_PROFILES_STORAGE_KEY);
      } else {
        storage.setItem(LOCAL_PROFILES_STORAGE_KEY, JSON.stringify(atualizados));
      }
    } catch {
      // Ignora erro de storage indisponível
    }
  }
  return atualizados;
}

/**
 * Limpa todos os perfis anônimos salvos no `localStorage` deste navegador.
 */
export function limparPerfisLocais(): void {
  const storage = getLocalStorage();
  if (!storage) return;
  try {
    storage.removeItem(LOCAL_PROFILES_STORAGE_KEY);
  } catch {
    // Ignora erro de storage indisponível
  }
}
