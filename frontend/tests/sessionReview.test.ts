import { afterEach, describe, expect, it, vi } from "vitest";
import {
  baixarSessao,
  criarSessao,
  diferencas,
  rotaExportarSessao,
  rotaRevisao,
  salvarRevisao,
  SessaoRevisaoError,
} from "../src/services/sessionReview";

afterEach(() => vi.unstubAllGlobals());

describe("diferencas", () => {
  const q = (id: string, adaptado: string, aprovada = false) => ({ id, original: "", adaptado, aprovada, editada: false });
  it("envia só o que mudou", () => {
    const conf = [q("q1", "a"), q("q2", "b")];
    expect(diferencas([q("q1", "a"), q("q2", "b")], conf)).toEqual([]);
    expect(diferencas([q("q1", "a", true), q("q2", "b")], conf)).toEqual([{ id: "q1", aprovada: true }]);
    expect(diferencas([q("q1", "novo"), q("q2", "b")], conf)).toEqual([{ id: "q1", adaptado: "novo", aprovada: false }]);
  });
});

describe("chamadas", () => {
  it("salvarRevisao usa PUT em /sessions/{id}/review", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: "s1" }) });
    vi.stubGlobal("fetch", f);
    await salvarRevisao("s 1", { questoes: [{ id: "q1", adaptado: "x" }], homologar: false });
    const [url, init] = f.mock.calls[0];
    expect(String(url).endsWith(rotaRevisao("s 1"))).toBe(true);
    expect(String(url)).toContain("/api/v1/sessions/s%201/review");
    expect(init.method).toBe("PUT");
    expect(init.cache).toBe("no-store");
    expect(JSON.parse(init.body)).toEqual({ questoes: [{ id: "q1", adaptado: "x" }], homologar: false });
  });

  it("criarSessao envia as questões por POST", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: "s1" }) });
    vi.stubGlobal("fetch", f);
    await criarSessao([{ adaptado: "x" }], "Aula");
    expect(f.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ titulo: "Aula", questoes: [{ adaptado: "x" }] });
  });

  it("exportação bloqueada vira erro com o código do servidor e não baixa nada", async () => {
    const cliques: string[] = [];
    vi.stubGlobal("document", { createElement: () => ({ click: () => cliques.push("x") }), body: { appendChild: vi.fn() } });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ detail: { code: "EXPORT_BLOCKED", detail: "Homologue antes." } }),
      })
    );
    const erro = await baixarSessao("s1", "pdf").catch((e) => e);
    expect(erro).toBeInstanceOf(SessaoRevisaoError);
    expect(erro).toMatchObject({ code: "EXPORT_BLOCKED", status: 409, message: "Homologue antes." });
    expect(cliques).toEqual([]);
  });

  it("servidor fora do ar vira erro claro", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("x")));
    await expect(salvarRevisao("s1", {})).rejects.toMatchObject({ code: "SERVER_UNAVAILABLE" });
  });

  it("baixarSessao usa POST na rota da sessão e baixa com nome genérico", async () => {
    const a = { href: "", download: "", click: vi.fn(), remove: vi.fn() };
    vi.stubGlobal("document", { createElement: () => a, body: { appendChild: vi.fn() } });
    vi.stubGlobal("URL", { createObjectURL: () => "blob:x", revokeObjectURL: vi.fn() });
    const f = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(["x"]) });
    vi.stubGlobal("fetch", f);
    await baixarSessao("s1", "docx");
    expect(String(f.mock.calls[0][0]).endsWith(rotaExportarSessao("s1", "docx"))).toBe(true);
    expect(f.mock.calls[0][1].method).toBe("POST");
    expect(a.download).toBe("atividade-adaptada.docx");
  });
});
