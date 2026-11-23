import { afterEach, describe, expect, it, vi } from "vitest";
import { criarPerfilPortatil, perfilParaJson, type PerfilPedagogicoPortatil } from "../src/services/portableProfile";
import {
  carregarRestauracaoDaSessao,
  importarPerfilDeArquivo,
  importarPerfilDeTexto,
  lerArquivoPerfil,
  MAX_BYTES_PERFIL,
  nivelCitadoNaEstrategia,
  PERFIL_IMPORTADO_STORAGE_KEY,
  recomendarDoPerfil,
  salvarRestauracaoNaSessao,
} from "../src/services/portableProfileImport";

const ID_A = "atencao_sustentada_textos_longos";
const ID_B = "sobrecarga_memoria_trabalho_comandos_multiplos";

function perfilComHistorico(
  regs: Array<{ estrategia: string; id?: string; eficacia: "alta" | "media" | "baixa"; quando?: string }>
): PerfilPedagogicoPortatil {
  const base = criarPerfilPortatil([ID_A, ID_B]);
  return {
    ...base,
    historico_intervencoes: regs.map((r, i) => ({
      estrategia: r.estrategia,
      id_caracteristica: r.id ?? ID_A,
      eficacia: r.eficacia,
      observacao: null,
      registrado_em: r.quando ?? `2026-11-${String(10 + i).padStart(2, "0")}T12:00:00Z`,
    })),
  };
}

const arquivo = (conteudo: string, nome = "perfil-aluno-8f7a2c1b.json") =>
  new File([conteudo], nome, { type: "application/json" });

function memoriaDeSessao() {
  const dados = new Map<string, string>();
  const sessionStorage = {
    getItem: (k: string) => dados.get(k) ?? null,
    setItem: (k: string, v: string) => void dados.set(k, v),
    removeItem: (k: string) => void dados.delete(k),
  };
  vi.stubGlobal("window", { sessionStorage });
  return dados;
}

afterEach(() => vi.unstubAllGlobals());

describe("regra de pré-seleção do perfil importado", () => {
  it("pré-marca as características do perfil e as que têm eficácia alta", () => {
    const r = recomendarDoPerfil(
      perfilComHistorico([
        { estrategia: "Checklist", id: ID_A, eficacia: "alta" },
        { estrategia: "Leitura em voz alta", id: ID_B, eficacia: "baixa" },
      ])
    );
    expect(r.caracteristicas).toEqual([ID_A, ID_B]);
    expect(r.alta_eficacia).toEqual([ID_A]);
  });

  it.each([
    ["Fragmentação com andaime nível 2", 2],
    ["Nível 3: comandos um de cada vez", 3],
    ["nível leve com exemplos", 1],
    ["Andaime moderado nas questões abertas", 2],
    ["Nivel de andaime intensivo", 3],
  ])("reconhece a menção explícita ao nível em %j", (texto, nivel) => {
    expect(nivelCitadoNaEstrategia(texto)).toBe(nivel);
  });

  it.each(["Checklist de etapas", "Texto leve e curto", "Questão de nível médio do ENEM", "Nível 4", ""])(
    "não inventa nível quando o texto não cita um: %j",
    (texto) => {
      expect(nivelCitadoNaEstrategia(texto)).toBeNull();
    }
  );

  it("sugere o nível que aparece mais nas estratégias de eficácia ALTA", () => {
    const r = recomendarDoPerfil(
      perfilComHistorico([
        { estrategia: "Andaime nível 2 com checklist", eficacia: "alta" },
        { estrategia: "Andaime nível 2 com exemplo resolvido", eficacia: "alta" },
        { estrategia: "Andaime nível 3 com dicas", eficacia: "alta" },
        { estrategia: "Andaime nível 1", eficacia: "baixa" }, // baixa eficácia não conta
      ])
    );
    expect(r.nivel_andaime).toBe(2);
    expect(r.motivo_nivel).toContain("Moderado");
    expect(r.motivo_nivel).toContain("2 estratégias");
  });

  it("em caso de empate não sugere nível e diz por quê", () => {
    const r = recomendarDoPerfil(
      perfilComHistorico([
        { estrategia: "Andaime nível 1", eficacia: "alta" },
        { estrategia: "Andaime nível 3", eficacia: "alta" },
      ])
    );
    expect(r.nivel_andaime).toBeNull();
    expect(r.motivo_nivel).toMatch(/mais de um nível/);
  });

  it("sem histórico, ou sem nível citado, mantém o padrão da Etapa 3 e explica", () => {
    expect(recomendarDoPerfil(criarPerfilPortatil([ID_A])).nivel_andaime).toBeNull();
    expect(recomendarDoPerfil(criarPerfilPortatil([ID_A])).motivo_nivel).toMatch(/não tem registro de eficácia alta/);
    const semNivel = recomendarDoPerfil(perfilComHistorico([{ estrategia: "Checklist", eficacia: "alta" }]));
    expect(semNivel.nivel_andaime).toBeNull();
    expect(semNivel.motivo_nivel).toMatch(/não citam um nível/);
  });
});

describe("leitura do arquivo", () => {
  it("recusa o que não é .json, vazio ou grande demais, dizendo o motivo", async () => {
    await expect(lerArquivoPerfil(arquivo("{}", "perfil.pdf"))).rejects.toMatchObject({ code: "UNSUPPORTED_PROFILE_FORMAT" });
    await expect(lerArquivoPerfil(arquivo("", "perfil.json"))).rejects.toMatchObject({ code: "EMPTY_FILE" });
    await expect(lerArquivoPerfil(arquivo("  \n ", "perfil.json"))).rejects.toMatchObject({ code: "EMPTY_FILE" });
    await expect(lerArquivoPerfil(arquivo("x".repeat(MAX_BYTES_PERFIL + 1), "perfil.json"))).rejects.toMatchObject({
      code: "FILE_TOO_LARGE",
    });
  });

  it("aceita .json em qualquer caixa e devolve o texto", async () => {
    expect(await lerArquivoPerfil(arquivo("{}", "PERFIL.JSON"))).toBe("{}");
  });
});

describe("importação", () => {
  it("com o servidor: envia só o texto do arquivo e devolve o perfil validado", async () => {
    const perfil = perfilComHistorico([{ estrategia: "Andaime nível 2", eficacia: "alta" }]);
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ perfil, resumo_eficacia: {} }) });
    vi.stubGlobal("fetch", f);

    const r = await importarPerfilDeArquivo(arquivo(perfilParaJson(perfil)));

    expect(r.origem).toBe("servidor");
    expect(r.restaurado.nivel_andaime).toBe(2);
    const [url, init] = f.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/perfil\/importar$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ arquivo: perfilParaJson(perfil) });
  });

  it("mostra a mensagem do servidor quando o arquivo é recusado e NÃO cai na validação local", async () => {
    const corpo = { detail: { code: "INVALID_JSON", field: "perfil", detail: "O arquivo do perfil não é um JSON válido." } };
    const f = vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => corpo });
    vi.stubGlobal("fetch", f);
    await expect(importarPerfilDeTexto("{quebrado")).rejects.toMatchObject({
      name: "PerfilPortatilError",
      code: "INVALID_JSON",
      message: "O arquivo do perfil não é um JSON válido.",
    });
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("servidor fora do ar: valida localmente o mesmo schema", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const perfil = criarPerfilPortatil([ID_A, ID_B]);
    const r = await importarPerfilDeTexto(perfilParaJson(perfil));
    expect(r.origem).toBe("local");
    expect(r.restaurado.caracteristicas).toEqual([ID_A, ID_B]);
  });

  it("servidor fora do ar: arquivo corrompido ou com dado pessoal continua sendo recusado", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(importarPerfilDeTexto("isto não é json")).rejects.toMatchObject({ code: "INVALID_JSON" });
    await expect(importarPerfilDeTexto("[1,2]")).rejects.toMatchObject({ code: "INVALID_STRUCTURE" });
    const comNome = { ...criarPerfilPortatil([ID_A]), nome: "Maria" };
    await expect(importarPerfilDeTexto(JSON.stringify(comNome))).rejects.toMatchObject({ code: "CLINICAL_DATA_BLOCKED" });
    const versaoNova = { ...criarPerfilPortatil([ID_A]), versao_schema: "2.0" };
    await expect(importarPerfilDeTexto(JSON.stringify(versaoNova))).rejects.toMatchObject({ code: "INVALID_STRUCTURE" });
  });

  it("resposta inesperada do servidor vira erro amigável", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ perfil: 42 }) }));
    await expect(importarPerfilDeTexto("{}")).rejects.toMatchObject({ code: "INVALID_SERVER_RESPONSE" });
  });
});

describe("sessão da aba", () => {
  it("guarda só identificadores e a sugestão, nunca o conteúdo do arquivo", () => {
    const dados = memoriaDeSessao();
    const perfil = perfilComHistorico([{ estrategia: "Andaime nível 2 para Maria", eficacia: "alta" }]);
    salvarRestauracaoNaSessao(recomendarDoPerfil(perfil));
    const guardado = dados.get(PERFIL_IMPORTADO_STORAGE_KEY)!;
    expect(guardado).not.toContain("Maria");
    expect(guardado).not.toContain("estrategia");
    expect(Object.keys(JSON.parse(guardado)).sort()).toEqual(
      ["alta_eficacia", "caracteristicas", "codigo_anonimo", "motivo_nivel", "nivel_andaime"]
    );
    expect(carregarRestauracaoDaSessao()).toMatchObject({ codigo_anonimo: perfil.codigo_anonimo, nivel_andaime: 2 });
  });

  it("dado malformado na sessão vira 'sem perfil importado'", () => {
    const dados = memoriaDeSessao();
    dados.set(PERFIL_IMPORTADO_STORAGE_KEY, "{não é json");
    expect(carregarRestauracaoDaSessao()).toBeNull();
    dados.set(PERFIL_IMPORTADO_STORAGE_KEY, JSON.stringify({ codigo_anonimo: 7 }));
    expect(carregarRestauracaoDaSessao()).toBeNull();
    dados.set(
      PERFIL_IMPORTADO_STORAGE_KEY,
      JSON.stringify({ codigo_anonimo: "aluno-8f7a2c1b", caracteristicas: [ID_A, "Id Inválido!", 5], nivel_andaime: 9 })
    );
    expect(carregarRestauracaoDaSessao()).toMatchObject({ caracteristicas: [ID_A], nivel_andaime: null });
  });

  it("sem sessionStorage (ex.: renderização no servidor) não quebra", () => {
    expect(carregarRestauracaoDaSessao()).toBeNull();
    expect(() => salvarRestauracaoNaSessao(recomendarDoPerfil(criarPerfilPortatil([ID_A])))).not.toThrow();
  });
});
