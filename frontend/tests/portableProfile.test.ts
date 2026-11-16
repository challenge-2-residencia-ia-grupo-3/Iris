import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PADRAO_CODIGO,
  PerfilPortatilError,
  criarPerfilPortatil,
  gerarCodigoAnonimo,
  nomeArquivoPerfil,
  perfilParaJson,
} from "../src/services/portableProfile";

const IDS = ["sobrecarga_memoria_trabalho_comandos_multiplos", "leitura_texto_longo_fadiga"];

afterEach(() => vi.restoreAllMocks());

describe("código anônimo", () => {
  it("segue o formato aluno-<hex> aceito pelo backend", () => {
    for (let i = 0; i < 200; i++) expect(gerarCodigoAnonimo()).toMatch(PADRAO_CODIGO);
    expect(gerarCodigoAnonimo(16)).toMatch(/^aluno-[0-9a-f]{16}$/);
  });
  it("é único em 2000 gerações (16 hex)", () => {
    expect(new Set(Array.from({ length: 2000 }, () => gerarCodigoAnonimo(16))).size).toBe(2000);
  });
  it("usa crypto.getRandomValues, nunca Math.random", () => {
    const rnd = vi.spyOn(Math, "random");
    const cr = vi.spyOn(globalThis.crypto, "getRandomValues");
    gerarCodigoAnonimo();
    expect(cr).toHaveBeenCalled();
    expect(rnd).not.toHaveBeenCalled();
  });
  it("rejeita tamanhos fora de 8..32", () => {
    expect(() => gerarCodigoAnonimo(4)).toThrow(PerfilPortatilError);
    expect(() => gerarCodigoAnonimo(33)).toThrow(PerfilPortatilError);
  });
});

describe("criarPerfilPortatil", () => {
  it("tem código, data UTC e as características escolhidas", () => {
    const p = criarPerfilPortatil(IDS, IDS, new Date("2026-11-13T12:00:00Z"));
    expect(p.codigo_anonimo).toMatch(PADRAO_CODIGO);
    expect(p.criado_em).toBe("2026-11-13T12:00:00.000Z");
    expect(p.caracteristicas_selecionadas).toEqual(IDS);
    expect(p.versao_schema).toBe("1.0");
  });
  it("não tem campo de dado pessoal", () => {
    const chaves = Object.keys(criarPerfilPortatil(IDS));
    for (const proibido of ["nome", "cpf", "escola", "email", "turma"]) expect(chaves).not.toContain(proibido);
  });
  it("remove repetidos e rejeita vazio, desconhecido e mal formado", () => {
    expect(criarPerfilPortatil([IDS[0], IDS[0]]).caracteristicas_selecionadas).toEqual([IDS[0]]);
    expect(() => criarPerfilPortatil([])).toThrow(PerfilPortatilError);
    expect(() => criarPerfilPortatil(["nao_existe"], IDS)).toThrow(/fora do catálogo/);
    expect(() => criarPerfilPortatil(["TDAH do Joao"])).toThrow(PerfilPortatilError);
  });
  it("gera JSON que volta igual e nome de arquivo com o código", () => {
    const p = criarPerfilPortatil(IDS);
    expect(JSON.parse(perfilParaJson(p))).toEqual(p);
    expect(nomeArquivoPerfil(p)).toBe(`perfil-${p.codigo_anonimo}.json`);
  });
});

describe("nada é persistido nem enviado", () => {
  it("criar o perfil não chama fetch nem usa storage", () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    const set = vi.fn();
    vi.stubGlobal("localStorage", { setItem: set, getItem: vi.fn() });
    vi.stubGlobal("sessionStorage", { setItem: set, getItem: vi.fn() });
    criarPerfilPortatil(IDS, IDS);
    expect(f).not.toHaveBeenCalled();
    expect(set).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
  it("o código-fonte não referencia rede nem armazenamento", () => {
    const codigo = readFileSync(resolve(__dirname, "../src/services/portableProfile.ts"), "utf-8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");
    for (const termo of ["fetch(", "XMLHttpRequest", "localStorage", "sessionStorage", "indexedDB", "document.cookie", "sendBeacon", "WebSocket"]) {
      expect(codigo).not.toContain(termo);
    }
  });
});
