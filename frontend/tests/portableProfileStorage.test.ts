import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { criarPerfilPortatil, PerfilPortatilError } from "../src/services/portableProfile";
import {
  LOCAL_PROFILES_STORAGE_KEY,
  limparPerfisLocais,
  listarPerfisLocais,
  removerPerfilLocal,
  salvarPerfilLocal,
  sanitizarPerfilParaLocalStorage,
} from "../src/services/portableProfileStorage";

const IDS = ["sobrecarga_memoria_trabalho_comandos_multiplos", "atencao_sustentada_textos_longos"];

function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (k: string) => store.get(k) ?? null,
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    removeItem: (k: string) => {
      store.delete(k);
    },
    setItem: (k: string, v: string) => {
      store.set(k, v);
    },
  };
}

let mockStorage: Storage;

beforeEach(() => {
  mockStorage = createMemoryStorage();
  (globalThis as { localStorage?: Storage }).localStorage = mockStorage;
});

afterEach(() => {
  delete (globalThis as { localStorage?: Storage }).localStorage;
});

describe("armazenamento local anônimo de perfis em localStorage", () => {
  it("salva, lista e ordena perfis anônimos sem dados pessoais", () => {
    const p1 = criarPerfilPortatil([IDS[0]], IDS, new Date("2026-11-15T10:00:00Z"));
    const p2 = criarPerfilPortatil([IDS[1]], IDS, new Date("2026-11-16T10:00:00Z"));

    salvarPerfilLocal(p1);
    const lista = salvarPerfilLocal(p2);

    expect(lista).toHaveLength(2);
    expect(lista.map((p) => p.codigo_anonimo)).toEqual([p2.codigo_anonimo, p1.codigo_anonimo]);
    expect(listarPerfisLocais()).toEqual(lista);

    const bruto = mockStorage.getItem(LOCAL_PROFILES_STORAGE_KEY);
    expect(bruto).toBeTruthy();
    expect(bruto).not.toContain('"nome"');
  });

  it("evita duplicidade por codigo_anonimo ao salvar novamente", () => {
    const p1 = criarPerfilPortatil([IDS[0]], IDS, new Date("2026-11-16T10:00:00Z"));
    salvarPerfilLocal(p1);
    const atualizado = { ...p1, caracteristicas_selecionadas: IDS };
    const lista = salvarPerfilLocal(atualizado);

    expect(lista).toHaveLength(1);
    expect(lista[0].caracteristicas_selecionadas).toEqual(IDS);
  });

  it("remove um perfil específico e limpa todos os perfis locais", () => {
    const p1 = criarPerfilPortatil([IDS[0]], IDS, new Date("2026-11-15T10:00:00Z"));
    const p2 = criarPerfilPortatil([IDS[1]], IDS, new Date("2026-11-16T10:00:00Z"));
    salvarPerfilLocal(p1);
    salvarPerfilLocal(p2);

    const aposRemover = removerPerfilLocal(p1.codigo_anonimo);
    expect(aposRemover).toHaveLength(1);
    expect(aposRemover[0].codigo_anonimo).toBe(p2.codigo_anonimo);

    limparPerfisLocais();
    expect(listarPerfisLocais()).toEqual([]);
    expect(mockStorage.getItem(LOCAL_PROFILES_STORAGE_KEY)).toBeNull();
  });

  it("rejeita campos pessoais ou clínicos (nome, cpf, laudo, cid, etc.)", () => {
    const base = criarPerfilPortatil(IDS, IDS);
    for (const campoProibido of ["nome", "nome_aluno", "cpf", "escola", "email", "turma", "laudo", "cid", "diagnostico"]) {
      expect(() =>
        sanitizarPerfilParaLocalStorage({ ...base, [campoProibido]: "dado sensível" })
      ).toThrow(PerfilPortatilError);
    }
    expect(() =>
      sanitizarPerfilParaLocalStorage({ ...base, codigo_anonimo: "aluno-joao" })
    ).toThrow(PerfilPortatilError);
  });

  it("ignora entradas corrompidas no localStorage ao listar", () => {
    const valido = criarPerfilPortatil(IDS, IDS);
    mockStorage.setItem(
      LOCAL_PROFILES_STORAGE_KEY,
      JSON.stringify([valido, { codigo_anonimo: "joao-silva", nome: "João" }, "lixo"])
    );

    expect(listarPerfisLocais()).toEqual([valido]);
  });
});
