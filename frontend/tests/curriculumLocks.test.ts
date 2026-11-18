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
