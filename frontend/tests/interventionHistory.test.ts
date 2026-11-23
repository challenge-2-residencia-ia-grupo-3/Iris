import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  criarPerfilPortatil,
  historicoOrdenado,
  PerfilPortatilError,
  resumoEficacia,
  type PerfilPedagogicoPortatil,
  type RegistroIntervencao,
} from "../src/services/portableProfile";
import {
  registrarIntervencao,
  ROTA_INTERVENCOES,
  validarIntervencao,
  type NovaIntervencao,
} from "../src/services/interventionHistory";
import {
  limparPerfisLocais,
  listarPerfisLocais,
  salvarPerfilLocal,
  sanitizarPerfilParaLocalStorage,
} from "../src/services/portableProfileStorage";

const A = "atencao_sustentada_textos_longos";
const B = "sobrecarga_memoria_trabalho_comandos_multiplos";

function reg(estrategia: string, id: string, eficacia: RegistroIntervencao["eficacia"], dia: number): RegistroIntervencao {
  return { estrategia, id_caracteristica: id, eficacia, observacao: null, registrado_em: `2026-11-${String(dia).padStart(2, "0")}T12:00:00Z` };
}

const FORM: NovaIntervencao = { estrategia: "Fragmentação em checklist", id_caracteristica: A, eficacia: "alta", observacao: "  Terminou a prova.  " };

afterEach(() => vi.unstubAllGlobals());

describe("perfil novo", () => {
  it("não ganha chave nova: o conjunto de campos da #26/#30 não muda", () => {
    expect("historico_intervencoes" in criarPerfilPortatil([A])).toBe(false);
  });
});

describe("historicoOrdenado e resumoEficacia", () => {
  const base = criarPerfilPortatil([A, B]);
  const perfil: PerfilPedagogicoPortatil = {
    ...base,
    historico_intervencoes: [reg("Terceira", B, "baixa", 13), reg("Primeira", A, "alta", 11), reg("Segunda", A, "media", 12)],
  };
  it("ordena do mais antigo ao mais recente, sem alterar o perfil", () => {
    expect(historicoOrdenado(perfil).map((r) => r.estrategia)).toEqual(["Primeira", "Segunda", "Terceira"]);
    expect(perfil.historico_intervencoes![0].estrategia).toBe("Terceira");
  });
  it("mesmo instante mantém a ordem de entrada", () => {
    const p = { ...base, historico_intervencoes: [reg("Um", A, "alta", 11), reg("Dois", A, "baixa", 11)] };
    expect(historicoOrdenado(p).map((r) => r.estrategia)).toEqual(["Um", "Dois"]);
  });
  it("perfil sem histórico dá lista e resumo vazios", () => {
    expect(historicoOrdenado(base)).toEqual([]);
    expect(resumoEficacia(base)).toEqual({});
  });
  it("resume por característica com a eficácia mais recente", () => {
    const r = resumoEficacia(perfil);
    expect(r[A]).toEqual({ alta: 1, media: 1, baixa: 0, total: 2, ultima: "media" });
    expect(r[B]).toEqual({ alta: 0, media: 0, baixa: 1, total: 1, ultima: "baixa" });
  });
});

describe("validarIntervencao", () => {
  it("aceita um registro completo", () => expect(validarIntervencao(FORM, [A, B])).toBeNull());
  it("observação é opcional", () => expect(validarIntervencao({ ...FORM, observacao: "" }, [A])).toBeNull());
  it.each([
    [{ id_caracteristica: "" }, /característica/],
    [{ id_caracteristica: "outra_caracteristica" }, /característica/],
    [{ estrategia: "  ab " }, /mínimo de 3/],
    [{ estrategia: "x".repeat(301) }, /no máximo 300/],
    [{ eficacia: "" as const }, /alta, média ou baixa/],
    [{ observacao: "y".repeat(501) }, /no máximo 500/],
  ])("recusa %#", (alteracao, msg) => expect(validarIntervencao({ ...FORM, ...alteracao }, [A, B])).toMatch(msg));
});

describe("registrarIntervencao (chamada ao servidor)", () => {
  const perfil = criarPerfilPortatil([A, B]);
  const atualizado = { ...perfil, historico_intervencoes: [reg("Fragmentação em checklist", A, "alta", 11)] };

  it("envia perfil + registro limpo e devolve o perfil atualizado", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ perfil: atualizado, resumo_eficacia: {} }) });
    vi.stubGlobal("fetch", f);
    const r = await registrarIntervencao(perfil, FORM);
    expect(r).toEqual(atualizado);
    const [url, init] = f.mock.calls[0];
    expect(String(url).endsWith(ROTA_INTERVENCOES)).toBe(true);
    expect(init.method).toBe("POST");
    expect(init.cache).toBe("no-store");
    const corpo = JSON.parse(init.body);
    expect(corpo.perfil.codigo_anonimo).toBe(perfil.codigo_anonimo);
    expect(corpo.intervencao).toEqual({ estrategia: "Fragmentação em checklist", id_caracteristica: A, eficacia: "alta", observacao: "Terminou a prova." });
  });

  it("observação vazia vai como null", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ perfil: atualizado }) });
    vi.stubGlobal("fetch", f);
    await registrarIntervencao(perfil, { ...FORM, observacao: "   " });
    expect(JSON.parse(f.mock.calls[0][1].body).intervencao.observacao).toBeNull();
  });

  it("formulário inválido nem chama o servidor", async () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    await expect(registrarIntervencao(perfil, { ...FORM, eficacia: "" })).rejects.toMatchObject({ code: "INVALID_INTERVENTION" });
    expect(f).not.toHaveBeenCalled();
  });

  it("recusa do servidor (ex.: conteúdo clínico) vira erro com a mensagem orientadora", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 422,
      json: async () => ({ detail: { code: "CLINICAL_DATA_BLOCKED", detail: "Dados clínicos não são permitidos no perfil." } }),
    }));
    const e = await registrarIntervencao(perfil, FORM).catch((x) => x);
    expect(e).toBeInstanceOf(PerfilPortatilError);
    expect(e).toMatchObject({ code: "CLINICAL_DATA_BLOCKED", message: "Dados clínicos não são permitidos no perfil." });
  });

  it("servidor fora do ar e resposta estranha viram erros claros", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("rede")));
    await expect(registrarIntervencao(perfil, FORM)).rejects.toMatchObject({ code: "INTERVENTION_SERVER_UNAVAILABLE" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    await expect(registrarIntervencao(perfil, FORM)).rejects.toMatchObject({ code: "INTERVENTION_BAD_RESPONSE" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => { throw new Error("x"); } }));
    await expect(registrarIntervencao(perfil, FORM)).rejects.toMatchObject({ code: "INTERVENTION_REJECTED" });
  });
});

describe("armazenamento local do histórico", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    (globalThis as { localStorage?: Storage }).localStorage = {
      get length() { return store.size; },
      clear: () => store.clear(),
      getItem: (k: string) => store.get(k) ?? null,
      key: (i: number) => Array.from(store.keys())[i] ?? null,
      removeItem: (k: string) => { store.delete(k); },
      setItem: (k: string, v: string) => { store.set(k, v); },
    };
  });
  afterEach(() => {
    limparPerfisLocais();
    delete (globalThis as { localStorage?: Storage }).localStorage;
  });

  it("guarda e relê o perfil com o histórico", () => {
    const p = { ...criarPerfilPortatil([A]), historico_intervencoes: [reg("Checklist", A, "alta", 11)] };
    salvarPerfilLocal(p);
    expect(listarPerfisLocais()[0].historico_intervencoes).toEqual(p.historico_intervencoes);
  });

  it("perfil sem histórico continua sem o campo", () => {
    salvarPerfilLocal(criarPerfilPortatil([A]));
    expect("historico_intervencoes" in listarPerfisLocais()[0]).toBe(false);
  });

  it("descarta registros malformados e chaves extras do registro", () => {
    const p = {
      ...criarPerfilPortatil([A]),
      historico_intervencoes: [
        reg("Checklist", A, "alta", 11),
        { ...reg("Tempo extra", A, "media", 12), nome_aluno: "João" },
        { ...reg("ab", A, "media", 12) },
        { ...reg("Eficácia inválida", A, "otima" as never, 12) },
        { ...reg("Id ruim", "Maiuscula", "alta", 12) },
        { ...reg("Data ruim", A, "alta", 12), registrado_em: "ontem" },
        "texto solto",
      ],
    };
    const limpo = sanitizarPerfilParaLocalStorage(p);
    expect(limpo.historico_intervencoes!.map((r) => r.estrategia)).toEqual(["Checklist", "Tempo extra"]);
    expect(Object.keys(limpo.historico_intervencoes![1])).not.toContain("nome_aluno");
  });

  it("não deixa o histórico passar de 200 registros", () => {
    const muitos = Array.from({ length: 250 }, (_, i) => reg(`Estratégia ${i}`, A, "alta", 11));
    const limpo = sanitizarPerfilParaLocalStorage({ ...criarPerfilPortatil([A]), historico_intervencoes: muitos });
    expect(limpo.historico_intervencoes).toHaveLength(200);
  });
});
