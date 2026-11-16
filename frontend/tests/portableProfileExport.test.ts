import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { criarPerfilPortatil, PerfilPortatilError } from "../src/services/portableProfile";
import { baixarPerfilPdf, nomePdfPerfil, ROTA_EXPORTAR_PERFIL } from "../src/services/portableProfileExport";

const ID = "sobrecarga_memoria_trabalho_comandos_multiplos";
// Mesmas chaves do exemplo usado nos testes do backend (backend/tests/test_exportacao_perfil.py::JSON_DO_FRONT).
const CHAVES_ESPERADAS = [
  "anotacoes_pedagogicas",
  "barreiras_observadas",
  "caracteristicas_selecionadas",
  "codigo_anonimo",
  "criado_em",
  "historico_estrategias",
  "versao_schema",
];

let cliques: string[];

beforeEach(() => {
  cliques = [];
  const a = { href: "", download: "", click: () => cliques.push(a.download), remove: vi.fn() };
  vi.stubGlobal("document", { createElement: () => a, body: { appendChild: vi.fn() } });
  vi.stubGlobal("URL", { createObjectURL: () => "blob:x", revokeObjectURL: vi.fn() });
});
afterEach(() => vi.unstubAllGlobals());

describe("formato do JSON baixado", () => {
  it("tem exatamente as chaves que o schema do backend aceita", () => {
    expect(Object.keys(criarPerfilPortatil([ID])).sort()).toEqual(CHAVES_ESPERADAS);
  });
});

describe("exportação em PDF", () => {
  it("envia o perfil por POST à rota de exportação e baixa o PDF", async () => {
    const perfil = criarPerfilPortatil([ID]);
    const pdf = new Blob(["%PDF-1.7"], { type: "application/pdf" });
    const f = vi.fn().mockResolvedValue({ ok: true, blob: async () => pdf });
    vi.stubGlobal("fetch", f);

    await baixarPerfilPdf(perfil);

    expect(f).toHaveBeenCalledTimes(1);
    const [url, init] = f.mock.calls[0];
    expect(String(url).endsWith(`${ROTA_EXPORTAR_PERFIL}?formato=pdf`)).toBe(true);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual(perfil);
    expect(init.cache).toBe("no-store");
    expect(cliques).toEqual([nomePdfPerfil(perfil)]);
    expect(nomePdfPerfil(perfil)).toBe(`perfil-${perfil.codigo_anonimo}.pdf`);
  });

  it("não usa nenhum armazenamento do navegador", async () => {
    const guarda = vi.fn();
    vi.stubGlobal("localStorage", { setItem: guarda });
    vi.stubGlobal("sessionStorage", { setItem: guarda });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(["%PDF"]) }));
    await baixarPerfilPdf(criarPerfilPortatil([ID]));
    expect(guarda).not.toHaveBeenCalled();
  });

  it("mostra a recusa do servidor e não baixa arquivo", async () => {
    const detail = { detail: "O perfil contém dado clínico.", code: "PERFIL_CLINICO" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail }) }));
    await expect(baixarPerfilPdf(criarPerfilPortatil([ID]))).rejects.toThrow("dado clínico");
    expect(cliques).toEqual([]);
  });

  it("explica quando o servidor está fora do ar e lembra do .json offline", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("falha de rede")));
    const e = await baixarPerfilPdf(criarPerfilPortatil([ID])).catch((x) => x);
    expect(e).toBeInstanceOf(PerfilPortatilError);
    expect(e.code).toBe("PDF_SERVER_UNAVAILABLE");
    expect(e.message).toContain(".json");
    expect(cliques).toEqual([]);
  });

  it("usa mensagem padrão se o servidor responder erro sem corpo JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => { throw new Error("x"); } }));
    await expect(baixarPerfilPdf(criarPerfilPortatil([ID]))).rejects.toThrow("não gerou o PDF");
  });
});

describe("a rede fica isolada no módulo do PDF", () => {
  const limpo = (arq: string) =>
    readFileSync(resolve(__dirname, arq), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

  it("portableProfile.ts continua sem rede nem armazenamento", () => {
    const c = limpo("../src/services/portableProfile.ts");
    for (const t of ["fetch(", "XMLHttpRequest", "localStorage", "sessionStorage", "indexedDB", "document.cookie", "sendBeacon", "WebSocket"]) {
      expect(c).not.toContain(t);
    }
  });

  it("portableProfileExport.ts só chama a rota de exportação e não usa armazenamento", () => {
    const c = limpo("../src/services/portableProfileExport.ts");
    expect(c.match(/fetch\(/g)?.length).toBe(1);
    for (const t of ["localStorage", "sessionStorage", "indexedDB", "document.cookie"]) expect(c).not.toContain(t);
  });
});
