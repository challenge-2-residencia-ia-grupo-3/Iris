import { describe, expect, it } from "vitest";
import {
  buildAuditorInvariantsLocally,
  calibrateScaffoldingLocally,
  evaluatePreventiveAntiCrutchLocally,
  EXEMPLOS_TRAVAS_CURRICULARES,
  extractCurriculumLocksFromMaterialLocally,
} from "../src/services/scaffoldingApi";
import { FALLBACK_OFFICIAL_CATALOG } from "../src/services/catalogsApi";

describe("História 1.3.2 (#13): Travas Curriculares Inegociáveis e Alerta Preventivo Anti-Muleta", () => {
  it("extrai automaticamente conceitos, equação e objetivo avaliativo do texto do material da Etapa 1", () => {
    const extraido = extractCurriculumLocksFromMaterialLocally(
      "Questão 1 (EF07MA18): Calcule o valor da incógnita na equação 2x + 6 = 14 e explique os cloroplastos."
    );
    expect(extraido.conceitos_obrigatorios).toContain("2x + 6 = 14");
    expect(extraido.conceitos_obrigatorios).toContain("incógnita");
    expect(extraido.habilidade_bncc).toBe("EF07MA18");
    expect(extraido.verbo_comando_bncc).toBe("calcular");
    expect(extraido.objetivo_avaliativo).toContain("Calcular");
  });

  it("marca conceitos técnicos e habilidade BNCC como invariantes obrigatórios para o Agente Auditor", () => {
    const res = calibrateScaffoldingLocally(
      ["sobrecarga_memoria_trabalho_comandos_multiplos"],
      2,
      FALLBACK_OFFICIAL_CATALOG,
      {
        conceitos_obrigatorios: ["fotossíntese", "cloroplastos", "glicose"],
        termos_tecnicos_intocaveis: ["cloroplastos", "glicose"],
        habilidade_bncc: "EF06CI05",
        verbo_comando_bncc: "explicar",
        objetivo_avaliativo: "Explicar o processo de fotossíntese nas células vegetais.",
      }
    );

    expect(res.invariantes_auditor).toBeDefined();
    expect(res.invariantes_auditor?.blindagem_ativa).toBe(true);
    expect(res.invariantes_auditor?.conceitos_obrigatorios).toEqual([
      "fotossíntese",
      "cloroplastos",
      "glicose",
    ]);
    expect(res.invariantes_auditor?.habilidade_bncc).toBe("EF06CI05");
    expect(res.invariantes_auditor?.trcc_minimo_exigido).toBe(0.95);
    expect(res.alerta_preventivo_antimuleta?.emitido).toBe(false);
  });

  it("emite alerta preventivo crítico ao pedir resumo interpretativo em questão de interpretação de texto", () => {
    const alerta = evaluatePreventiveAntiCrutchLocally(
      2,
      ["atencao_sustentada_textos_longos"],
      {
        conceitos_obrigatorios: ["ironia", "sentido figurado"],
        habilidade_bncc: "EF67LP08",
        verbo_comando_bncc: "interpretar",
        objetivo_avaliativo: "Avaliar interpretação de texto e inferência na crônica.",
        observacao_adaptacao_docente: "Fornecer um resumo interpretativo do texto para guiar o aluno.",
      }
    );

    expect(alerta.emitido).toBe(true);
    expect(alerta.severidade).toBe("critical");
    expect(alerta.codigo).toBe("CONTRADICAO_DIRETA_INTERPRETACAO");
    expect(alerta.mensagem.toLowerCase()).toContain("resumo interpretativo");
  });

  it("emite alerta preventivo crítico ao pedir fórmula pronta em questão de cálculo algébrico", () => {
    const alerta = evaluatePreventiveAntiCrutchLocally(
      2,
      ["retencao_dados_intermediarios_problemas_multietapas"],
      {
        conceitos_obrigatorios: ["equação", "2x + 6 = 14"],
        verbo_comando_bncc: "calcular",
        objetivo_avaliativo: "Calcular o valor da incógnita na equação.",
        observacao_adaptacao_docente: "Dar a fórmula pronta e o primeiro passo resolvido.",
      }
    );

    expect(alerta.emitido).toBe(true);
    expect(alerta.severidade).toBe("critical");
    expect(alerta.codigo).toBe("CONTRADICAO_DIRETA_CALCULO");
  });

  it("emite aviso preventivo quando Nível 3 (Intensivo) é combinado com habilidade de inferência textual", () => {
    const alerta = evaluatePreventiveAntiCrutchLocally(
      3,
      ["bloqueio_iniciacao_tarefas_abertas"],
      {
        conceitos_obrigatorios: ["ironia", "intenção do autor"],
        verbo_comando_bncc: "inferir",
        objetivo_avaliativo: "Inferir o sentido implícito do texto.",
      }
    );

    expect(alerta.emitido).toBe(true);
    expect(alerta.severidade).toBe("warning");
    expect(alerta.codigo).toBe("RISCO_NIVEL_INTENSIVO_INFERENCIA");
    expect(alerta.nivel_sugerido).toBe(2);
  });

  it("dispõe de exemplos práticos de travas curriculares por disciplina", () => {
    expect(EXEMPLOS_TRAVAS_CURRICULARES.length).toBeGreaterThanOrEqual(3);
    const inv = buildAuditorInvariantsLocally(
      EXEMPLOS_TRAVAS_CURRICULARES[0],
      evaluatePreventiveAntiCrutchLocally(1, ["atencao_sustentada_textos_longos"], EXEMPLOS_TRAVAS_CURRICULARES[0])
    );
    expect(inv.blindagem_ativa).toBe(true);
    expect(inv.conceitos_obrigatorios.length).toBeGreaterThan(0);
  });
});

describe("Revisão do PR #115 (achados 1 e 3) no navegador", () => {
  const alerta = (objetivo: string, observacao?: string, nivel: 1 | 2 | 3 = 1) =>
    evaluatePreventiveAntiCrutchLocally(nivel, [], {
      conceitos_obrigatorios: [],
      termos_tecnicos_intocaveis: [],
      habilidade_bncc: null,
      verbo_comando_bncc: null,
      objetivo_avaliativo: objetivo,
      observacao_adaptacao_docente: observacao ?? null,
    });

  it.each([
    "Avaliar se o aluno sabe resumir o texto e identificar a ideia central",
    "Resolver a equação e chegar ao resultado sem consultar o gabarito",
    "Interpretar o poema; não entregar resposta pronta ao aluno",
    "Interpretar o poema sem dar a ideia central pronta",
  ])("objetivo que cita a habilidade ou proíbe a muleta não dispara alerta: %s", (objetivo) => {
    expect(alerta(objetivo).emitido).toBe(false);
  });

  it("pedido explícito na observação continua disparando", () => {
    expect(alerta("Avaliar interpretação de texto", "Incluir um resumo interpretativo para o aluno.").codigo).toBe(
      "CONTRADICAO_DIRETA_INTERPRETACAO"
    );
    expect(alerta("Calcular o valor da incógnita na equação.", "Entregar a fórmula pronta.").codigo).toBe(
      "CONTRADICAO_DIRETA_CALCULO"
    );
  });

  it("pedido negado não dispara, e a negação só vale na mesma frase", () => {
    expect(alerta("Avaliar interpretação de texto", "Não incluir resumo interpretativo.").emitido).toBe(false);
    expect(alerta("Avaliar interpretação de texto", "Sem resumo interpretativo, apenas destaque.").emitido).toBe(false);
    expect(alerta("Avaliar interpretação de texto", "Não use cores fortes. Incluir resumo interpretativo.").emitido).toBe(true);
  });

  it("verbo de pedido dentro do objetivo ainda dispara", () => {
    expect(alerta("Avaliar interpretação de texto. Incluir resumo interpretativo para o aluno.").emitido).toBe(true);
  });

  it("Nível 3 em questão de inferência continua gerando aviso", () => {
    expect(alerta("Inferir o sentido implícito da tirinha.", undefined, 3).codigo).toBe("RISCO_NIVEL_INTENSIVO_INFERENCIA");
  });

  it("a extração ignora o cabeçalho da prova", () => {
    const e = extractCurriculumLocksFromMaterialLocally(
      "Escola Estadual X. Aluno: Pedro Souza. Leia o texto sobre fotossíntese e explique o papel do cloroplasto."
    );
    expect(e.conceitos_obrigatorios).not.toContain("estadual");
    expect(e.conceitos_obrigatorios).toContain("fotossíntese");
    expect(e.objetivo_avaliativo).not.toMatch(/estadual|Pedro/i);
  });

  it("só cabeçalho: não perde o material", () => {
    expect(extractCurriculumLocksFromMaterialLocally("Escola Municipal Machado de Assis.").objetivo_avaliativo).toBeTruthy();
  });

  it("sanitiza PII inline antes de extrair conceitos locais e evita chaves extras no alerta", () => {
    const e = extractCurriculumLocksFromMaterialLocally(
      "Questão 1 (Colégio Paulo Freire): O aluno Gabriel Silva calculou a fotossíntese dos cloroplastos."
    );
    expect(e.conceitos_obrigatorios).not.toContain("gabriel");
    expect(e.conceitos_obrigatorios).not.toContain("freire");
    expect(e.conceitos_obrigatorios).toContain("fotossíntese");

    const res = alerta("Definir o conceito de fotossíntese.", "Dar a definição pronta ao aluno.");
    expect(res.codigo).toBe("CONTRADICAO_DIRETA_CONCEITO");
    expect(res.mensagem).not.toContain("{");
    expect(res.mensagem).not.toContain("}");
  });
});
