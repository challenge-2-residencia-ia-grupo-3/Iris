import { describe, expect, it } from "vitest";
import catalogoRaw from "../../rag/catalogs/tdah_caracteristicas_funcionais.json";
import type { CharacteristicItem } from "../src/services/catalogsApi";
import {
  contarTrechosNovos,
  indicadoresAndaime,
  marcarMudancas,
  montarCartao,
  PALETA_ETAPA5,
  QuestaoEtapa5,
  razaoContraste,
  validarEntrada,
} from "../src/services/comparisonCards";
import { CLASSE_AVISO, CLASSE_INDICADOR } from "../src/components/JustificativaCard";
import { ETAPA5_DEMO } from "../src/services/etapa5Demo";

const CATALOGO = catalogoRaw.caracteristicas as unknown as CharacteristicItem[];
const q = (extra: Partial<QuestaoEtapa5> = {}): QuestaoEtapa5 => ({
  id: "q1",
  original: "Leia o texto e explique a evaporação.",
  adaptado: "1. [ ] **Leia** o texto.\n2. [ ] **Explique** a evaporação.",
  justificativas: ["Separou os comandos."],
  id_caracteristica: CATALOGO[0].id_caracteristica,
  nivel: 2,
  adaptacao_aplicada: true,
  ...extra,
});

describe("montarCartao: característica funcional e fundamento DUA/MEC", () => {
  it.each(CATALOGO.flatMap((c) => ([1, 2, 3] as const).map((n) => [c.id_caracteristica, n] as const)))(
    "%s nível %i cita característica, princípio do DUA e referência",
    (id, nivel) => {
      const c = montarCartao(q({ id_caracteristica: id, nivel }), CATALOGO);
      expect(c.caracteristicaEncontrada).toBe(true);
      expect(c.caracteristicaNome.length).toBeGreaterThan(5);
      expect(c.principioDua).toMatch(/^DUA (I|II|III) — /);
      expect(c.rotuloNivel).not.toBe(`Nível ${nivel}`);
      expect(c.objetivoAndaime.length).toBeGreaterThan(10);
      expect(c.referencias.length).toBeGreaterThan(0);
      expect(c.referencias.every((r) => r.doc_id && r.citacao_curta)).toBe(true);
    }
  );

  it("característica desconhecida não inventa fundamento", () => {
    const c = montarCartao(q({ id_caracteristica: "nao_existe_no_catalogo" }), CATALOGO);
    expect(c.caracteristicaEncontrada).toBe(false);
    expect(c.referencias).toEqual([]);
    expect(c.principioDua).toBe("");
  });

  it("marca quando não houve adaptação", () => {
    expect(montarCartao(q({ adaptacao_aplicada: false }), CATALOGO).semMudanca).toBe(true);
    expect(montarCartao(q({ adaptado: "Leia o texto e explique a evaporação." }), CATALOGO).semMudanca).toBe(true);
    expect(montarCartao(q(), CATALOGO).semMudanca).toBe(false);
  });

  it("justificativas vazias são descartadas", () => {
    expect(montarCartao(q({ justificativas: ["  ", "Ok."] }), CATALOGO).justificativas).toEqual(["Ok."]);
  });
});

describe("marcarMudancas", () => {
  it("texto igual não tem trecho novo", () => {
    const t = marcarMudancas("Explique a evaporação.", "Explique a evaporação.");
    expect(contarTrechosNovos(t)).toBe(0);
    expect(t.map((x) => x.texto).join("")).toBe("Explique a evaporação.");
  });
  it("marca só o que foi acrescentado e preserva o texto adaptado inteiro", () => {
    const adaptado = "1. [ ] **Leia** o texto.\n2. [ ] **Explique** a evaporação.";
    const t = marcarMudancas("Leia o texto e explique a evaporação.", adaptado);
    expect(t.map((x) => x.texto).join("")).toBe(adaptado);
    const novos = t.filter((x) => x.novo).map((x) => x.texto.trim());
    expect(novos.join(" ")).toContain("1.");
    expect(novos.join(" ")).not.toContain("evaporação");
  });
  it("ignora negrito e pontuação ao comparar palavras", () => {
    expect(contarTrechosNovos(marcarMudancas("Leia o texto.", "**Leia** o texto"))).toBe(0);
  });
  it("palavras novas vizinhas formam um trecho só", () => {
    const t = marcarMudancas("Descreva a condensação.", "Descreva com calma a condensação.");
    expect(t.filter((x) => x.novo).map((x) => x.texto.trim())).toEqual(["com calma"]);
  });
  it("lida com textos vazios", () => {
    expect(marcarMudancas("", "")).toEqual([]);
    expect(contarTrechosNovos(marcarMudancas("", "novo texto"))).toBe(1);
  });
});

describe("indicadoresAndaime: só o que está no texto", () => {
  it("checklist com verbos em destaque (nível 2)", () => {
    const ids = indicadoresAndaime(ETAPA5_DEMO.questoes[0].adaptado).map((i) => i.id);
    expect(ids).toEqual(["verbos_destacados", "checklist"]);
    expect(indicadoresAndaime(ETAPA5_DEMO.questoes[0].adaptado)[1].quantidade).toBe(3);
  });
  it("passos com resposta e lembrete (nível 3)", () => {
    const ind = indicadoresAndaime(ETAPA5_DEMO.questoes[1].adaptado);
    expect(ind.map((i) => i.id)).toEqual(["verbos_destacados", "passos_com_resposta", "lembrete_conferencia"]);
    expect(ind.find((i) => i.id === "verbos_destacados")?.quantidade).toBe(2); // "Passo N" não conta
  });
  it("caixa de conferência para comandos de leitura", () => {
    expect(indicadoresAndaime("**Passo 1**\n[ ] **Leia** o texto.\n").map((i) => i.id)).toContain("caixas_selecao");
  });
  it("texto sem andaime não mostra indicador", () => {
    expect(indicadoresAndaime("Leia o texto e explique.")).toEqual([]);
  });
});

describe("validarEntrada", () => {
  it("aceita o formato da Etapa 4 e normaliza", () => {
    const v = validarEntrada({ questoes: [{ ...q(), adaptacao_aplicada: undefined }] });
    expect(v?.questoes[0].adaptacao_aplicada).toBe(true);
  });
  it.each([
    null, 5, {}, { questoes: [] }, { questoes: [null] },
    { questoes: [{ ...q(), nivel: 4 }] },
    { questoes: [{ ...q(), adaptado: "  " }] },
    { questoes: [q(), q()] },
    { questoes: [{ ...q(), id_caracteristica: 3 }] },
  ])("recusa entrada inválida %#", (bruto) => expect(validarEntrada(bruto)).toBeNull());
});

describe("contraste WCAG 2.1 AA (≥ 4,5:1) das cores desta tela", () => {
  const pares = Object.entries(PALETA_ETAPA5).flatMap(([nome, tema]) =>
    Object.entries(tema).map(([modo, c]) => [`${nome}/${modo}`, c.fg, c.bg] as const)
  );
  it.each(pares)("%s", (_n, fg, bg) => expect(razaoContraste(fg, bg)).toBeGreaterThanOrEqual(4.5));
  it("preto sobre branco é 21:1 (sanidade da fórmula)", () => expect(razaoContraste("#000000", "#FFFFFF")).toBeCloseTo(21, 0));
  it("as classes do Tailwind usam exatamente as cores testadas", () => {
    const { indicador, aviso } = PALETA_ETAPA5;
    for (const [classe, par] of [[CLASSE_INDICADOR, indicador], [CLASSE_AVISO, aviso]] as const) {
      expect(classe).toContain(`bg-[${par.claro.bg}]`);
      expect(classe).toContain(`text-[${par.claro.fg}]`);
      expect(classe).toContain(`dark:bg-[${par.escuro.bg}]`);
      expect(classe).toContain(`dark:text-[${par.escuro.fg}]`);
    }
  });
});
