import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  baixarMaterial,
  ExportacaoMaterialError,
  nomeArquivoMaterial,
  ROTA_EXPORTAR_MATERIAL,
  ROTA_VERIFICAR_EXPORTACAO,
  temAvisos,
  verificarExportacao,
} from "../src/services/materialExport";

const MATERIAL = { titulo: "Ciências - Ciclo da água", texto: "1) Explique a evaporação." };
let cliques: string[];

beforeEach(() => {
  cliques = [];
  const a = { href: "", download: "", click: () => cliques.push(a.download), remove: vi.fn() };
  vi.stubGlobal("document", { createElement: () => a, body: { appendChild: vi.fn() } });
  vi.stubGlobal("URL", { createObjectURL: () => "blob:x", revokeObjectURL: vi.fn() });
});
afterEach(() => vi.unstubAllGlobals());

describe("baixarMaterial", () => {
  it.each(["pdf", "docx"] as const)("envia o texto aprovado por POST e baixa o %s", async (formato) => {
    const f = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(["x"]) });
    vi.stubGlobal("fetch", f);
    await baixarMaterial(MATERIAL, formato);
    const [url, init] = f.mock.calls[0];
    expect(String(url).endsWith(`${ROTA_EXPORTAR_MATERIAL}?formato=${formato}`)).toBe(true);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual(MATERIAL);
    expect(init.cache).toBe("no-store");
    expect(cliques).toEqual([nomeArquivoMaterial(formato)]);
  });

  it("nome do arquivo é genérico (sem título nem nome de aluno)", () => {
    expect(nomeArquivoMaterial("pdf")).toBe("atividade-adaptada.pdf");
    expect(nomeArquivoMaterial("docx")).toBe("atividade-adaptada.docx");
  });

  it("mostra a recusa do servidor e não baixa nada", async () => {
    const detail = { detail: "O título não pode conter laudo.", code: "CLINICAL_LABEL_IN_HEADER" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail }) }));
    const e = await baixarMaterial(MATERIAL, "pdf").catch((x) => x);
    expect(e).toBeInstanceOf(ExportacaoMaterialError);
    expect(e.code).toBe("CLINICAL_LABEL_IN_HEADER");
    expect(e.message).toContain("laudo");
    expect(cliques).toEqual([]);
  });

  it("explica quando o servidor está fora do ar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("rede")));
    const e = await baixarMaterial(MATERIAL, "docx").catch((x) => x);
    expect(e.code).toBe("EXPORT_SERVER_UNAVAILABLE");
    expect(cliques).toEqual([]);
  });

  it("usa mensagem padrão se o erro vier sem corpo JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => { throw new Error("x"); } }));
    await expect(baixarMaterial(MATERIAL, "pdf")).rejects.toThrow("não gerou o documento");
  });

  it("não usa armazenamento do navegador", async () => {
    const guarda = vi.fn();
    vi.stubGlobal("localStorage", { setItem: guarda });
    vi.stubGlobal("sessionStorage", { setItem: guarda });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(["x"]) }));
    await baixarMaterial(MATERIAL, "pdf");
    expect(guarda).not.toHaveBeenCalled();
  });
});

describe("verificarExportacao", () => {
  it("chama a rota de verificação e devolve os avisos", async () => {
    const avisos = { titulo: "T", possiveis_dados_pessoais: 2, categorias_clinicas_no_texto: ["diagnostico"], pode_exportar: true };
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => avisos });
    vi.stubGlobal("fetch", f);
    const r = await verificarExportacao(MATERIAL);
    expect(String(f.mock.calls[0][0]).endsWith(ROTA_VERIFICAR_EXPORTACAO)).toBe(true);
    expect(r).toEqual(avisos);
    expect(temAvisos(r)).toBe(true);
  });

  it("temAvisos é falso para texto limpo", () => {
    expect(temAvisos({ titulo: "T", possiveis_dados_pessoais: 0, categorias_clinicas_no_texto: [], pode_exportar: true })).toBe(false);
  });
});

describe("isolamento", () => {
  it("o serviço só faz rede por fetch e não usa armazenamento", () => {
    const c = readFileSync(resolve(__dirname, "../src/services/materialExport.ts"), "utf-8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");
    expect(c.match(/fetch\(/g)?.length).toBe(1);
    for (const t of ["localStorage", "sessionStorage", "indexedDB", "document.cookie", "sendBeacon", "WebSocket"]) {
      expect(c).not.toContain(t);
    }
  });
});
