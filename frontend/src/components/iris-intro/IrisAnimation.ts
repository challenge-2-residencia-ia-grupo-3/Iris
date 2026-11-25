import gsap from "gsap";

export const IRIS_TIMELINE_DURATION = 5.6;

export interface IrisMoment {
  id: string;
  code: string;
  title: string;
  start: number;
  end: number;
}

export const IRIS_MOMENTS: IrisMoment[] = [
  { id: "q01", code: "Q01", title: "Atmosfera", start: 0.0, end: 0.8 },
  { id: "q02", code: "Q02", title: "Estrela", start: 0.8, end: 1.25 },
  { id: "q03", code: "Q03", title: "Núcleo", start: 1.15, end: 1.65 },
  { id: "q04", code: "Q04", title: "Cores invertidas", start: 1.65, end: 2.35 },
  { id: "q05", code: "Q05", title: "Fluxo e troca", start: 2.35, end: 3.55 },
  { id: "q06", code: "Q06", title: "Formação do olho", start: 3.4, end: 4.35 },
  { id: "q07", code: "Q07", title: "Órbita e revelação", start: 4.2, end: 5.6 },
];

export interface IrisIntroOptions {
  onComplete?: () => void;
  onTimeUpdate?: (time: number) => void;
}

function prepStrokeDraw(path: SVGPathElement | null): number {
  if (!path || typeof path.getTotalLength !== "function") return 0;
  const len = path.getTotalLength();
  gsap.set(path, {
    strokeDasharray: len,
    strokeDashoffset: len,
  });
  return len;
}

/** Localiza a distância exata ao longo do path da órbita correspondente ao ponto final (876.5, 274) */
function findPointDistanceOnPath(
  path: SVGPathElement | null,
  targetX: number,
  targetY: number
): number {
  if (
    !path ||
    typeof path.getTotalLength !== "function" ||
    typeof path.getPointAtLength !== "function"
  ) {
    return 0;
  }
  const total = path.getTotalLength();
  let bestDist = total * 0.45;
  let bestErr = Infinity;
  const steps = 160;
  for (let i = 0; i <= steps; i++) {
    const d = (i / steps) * total;
    const pt = path.getPointAtLength(d);
    const err = Math.hypot(pt.x - targetX, pt.y - targetY);
    if (err < bestErr) {
      bestErr = err;
      bestDist = d;
    }
  }
  return bestDist;
}

/**
 * Timeline cinematográfica GSAP (5,6s) — Etapa 05:
 * 1. Atmosfera ampla (#0D0221 + degradês largos)
 * 2. Estrela branca primeiro no centro
 * 3. Núcleo circular ao redor da estrela
 * 4. Forças luminosas nascem em posições invertidas (laranja à esquerda, azul à direita)
 * 5. Fluxo contínuo de duas ondas de luz que cruzam e trocam de lado
 * 6. Convergência e formação fiel do olho (azul à esquerda, laranja à direita)
 * 7. Giro orbital até rotation: 0 e revelação limpa (exclusivamente o símbolo, sem texto)
 */
export function createIrisIntroTimeline(
  root: HTMLElement,
  options: IrisIntroOptions = {}
): { timeline: gsap.core.Timeline; cleanup: () => void } {
  let timeline!: gsap.core.Timeline;

  const ctx = gsap.context(() => {
    const q = (sel: string) => root.querySelector(sel);

    // Campos atmosféricos amplos (iniciam em posições invertidas: laranja esquerda, azul direita)
    const atmOrange = q(".iris-atm-orange");
    const atmCoral = q(".iris-atm-coral");
    const atmTeal = q(".iris-atm-teal");
    const atmCyan = q(".iris-atm-cyan");

    // 8 Grupos oficiais do iris-master.svg
    const innerCore = q("#inner-core");
    const centralStar = q("#central-star");
    const tealShape = q("#teal-shape");
    const orangeShape = q("#orange-shape");
    const eyeContours = q("#eye-contours");
    const orbitalRing = q("#orbital-ring");
    const orbitalAccent = q("#orbital-accent");
    const secondaryCurves = q("#secondary-curves");

    // Correntes/ondas orgânicas de fluxo (camada de animação, não altera SVG mestre)
    const waveOrangeField = q("#iris-wave-orange-field");
    const waveTealField = q("#iris-wave-teal-field");
    const waveOrangeRibbon = q("#iris-wave-orange-ribbon") as SVGPathElement | null;
    const waveTealRibbon = q("#iris-wave-teal-ribbon") as SVGPathElement | null;

    // Paths de traçado progressivo
    const orbitPath = q("#orbital-ring-path") as SVGPathElement | null;
    const orbitHaloPath = q("#iris-orbit-halo-path") as SVGPathElement | null;
    const secArcLeft = q("#secondary-lower-left-arc") as SVGPathElement | null;
    const secTailLine = q("#secondary-crescent-tail-line") as SVGPathElement | null;

    // Máscaras orgânicas de revelação do olho
    const clipTealEllipse = q("#iris-clip-teal-ellipse");
    const clipOrangeEllipse = q("#iris-clip-orange-ellipse");
    const clipCrescentEllipse = q("#iris-clip-crescent-ellipse");

    // Camadas sutis de iluminação temporária (zeram em Q07)
    const coreHalo = q("#iris-core-halo");
    const starGlow = q("#iris-star-glow");
    const dotHalo = q("#iris-dot-halo");
    const tealSweep = q("#iris-glow-teal-sweep") as SVGPathElement | null;
    const orangeSweep = q("#iris-glow-orange-sweep") as SVGPathElement | null;

    // ------------------------------------------------------------------
    // ESTADO INICIAL (t = 0.0s)
    // ------------------------------------------------------------------
    // Laranja inicia amplo nas bordas à esquerda; Azul inicia amplo nas bordas à direita (Estado A)
    gsap.set([atmOrange, atmCoral], { opacity: 0, xPercent: -14, yPercent: 0, scale: 1.08 });
    gsap.set([atmTeal, atmCyan], { opacity: 0, xPercent: 14, yPercent: 0, scale: 1.08 });

    gsap.set(innerCore, {
      opacity: 0,
      scale: 0.78,
      svgOrigin: "550 412",
    });
    gsap.set(centralStar, {
      opacity: 0,
      scale: 0.35,
      svgOrigin: "554 413",
    });
    gsap.set(coreHalo, { opacity: 0, scale: 0.7, svgOrigin: "550 412" });
    gsap.set(starGlow, { opacity: 0, scale: 0.5, svgOrigin: "554 413" });

    // Campos orgânicos amplos de onda (iniciam difusos e largos, sem aspecto de bolinha)
    gsap.set(waveOrangeField, {
      opacity: 0,
      x: -290,
      y: -36,
      scaleX: 1.65,
      scaleY: 1.32,
      skewX: -8,
      svgOrigin: "500 412",
    });
    gsap.set(waveTealField, {
      opacity: 0,
      x: 290,
      y: 36,
      scaleX: 1.65,
      scaleY: 1.32,
      skewX: 8,
      svgOrigin: "500 412",
    });

    const orangeRibbonLen = prepStrokeDraw(waveOrangeRibbon);
    const tealRibbonLen = prepStrokeDraw(waveTealRibbon);
    gsap.set([waveOrangeRibbon, waveTealRibbon], { opacity: 0 });

    // Formas definitivas do olho (aguardam a chegada das ondas em Q06)
    gsap.set(tealShape, { opacity: 0, x: 48, scale: 0.94, svgOrigin: "360 412" });
    gsap.set(orangeShape, { opacity: 0, x: -48, scale: 0.94, svgOrigin: "680 412" });
    gsap.set(eyeContours, { opacity: 0 });
    gsap.set(clipTealEllipse, { attr: { cx: 485, cy: 412, rx: 1, ry: 1 } });
    gsap.set(clipOrangeEllipse, { attr: { cx: 590, cy: 412, rx: 1, ry: 1 } });
    gsap.set(clipCrescentEllipse, { attr: { cx: 470, cy: 412, rx: 1, ry: 1 } });

    // Órbita, curvas secundárias e ponto laranja (ponto posicionado no início do traçado para percorrê-lo)
    gsap.set(orbitalRing, {
      opacity: 0,
      rotation: -68,
      svgOrigin: "550 412",
    });
    gsap.set(secondaryCurves, { opacity: 0 });
    prepStrokeDraw(orbitPath);
    prepStrokeDraw(orbitHaloPath);
    prepStrokeDraw(secArcLeft);
    prepStrokeDraw(secTailLine);
    gsap.set(orbitHaloPath, { opacity: 0 });

    const orbitDotEl = q("#orbital-accent-dot") as SVGCircleElement | null;
    const orbitStartPt =
      orbitPath && typeof orbitPath.getPointAtLength === "function"
        ? orbitPath.getPointAtLength(0)
        : { x: 302, y: 216 };
    const orbitDotFinalDist = findPointDistanceOnPath(orbitPath, 876.5, 274);

    gsap.set(orbitalAccent, {
      opacity: 0,
      rotation: -68,
      svgOrigin: "550 412",
    });
    gsap.set(dotHalo, {
      opacity: 0,
      rotation: -68,
      svgOrigin: "550 412",
    });
    if (orbitDotEl) {
      gsap.set(orbitDotEl, { attr: { cx: orbitStartPt.x, cy: orbitStartPt.y } });
    }
    if (dotHalo) {
      gsap.set(dotHalo, { attr: { cx: orbitStartPt.x, cy: orbitStartPt.y } });
    }

    const tealSweepLen = prepStrokeDraw(tealSweep);
    const orangeSweepLen = prepStrokeDraw(orangeSweep);
    gsap.set([tealSweep, orangeSweep], { opacity: 0 });

    // ------------------------------------------------------------------
    // TIMELINE PRINCIPAL — 5,60 segundos
    // ------------------------------------------------------------------
    timeline = gsap.timeline({
      defaults: { ease: "power2.inOut" },
      onUpdate: () => {
        options.onTimeUpdate?.(timeline.time());
      },
      onComplete: () => {
        options.onComplete?.();
      },
    });

    // ==================================================================
    // Q01 — Estado A: Expansão atmosférica ampla (0.0s – 0.9s)
    // Dois grandes campos volumétricos suaves, baixa concentração no centro
    // ==================================================================
    timeline.addLabel("q01", 0.0);
    timeline.to(
      [atmOrange, atmCoral],
      { opacity: 0.84, xPercent: -9, scale: 1.12, duration: 0.9, ease: "sine.out" },
      0.0
    );
    timeline.to(
      [atmTeal, atmCyan],
      { opacity: 0.84, xPercent: 9, scale: 1.12, duration: 0.9, ease: "sine.out" },
      0.04
    );

    // ==================================================================
    // Q02 — Estrela (0.8s – 1.25s) + início da aproximação atmosférica
    // Brilho inicial bem discreto (o brilho principal fica reservado ao final)
    // ==================================================================
    timeline.addLabel("q02", 0.8);
    timeline.to(
      starGlow,
      { opacity: 0.28, scale: 0.92, duration: 0.32, ease: "power2.out" },
      0.8
    );
    timeline.to(
      centralStar,
      { opacity: 1, scale: 1, duration: 0.38, ease: "power3.out" },
      0.82
    );

    // ==================================================================
    // Q03 — Núcleo (1.15s – 1.65s) + Estado B: Convergência & mistura cromática
    // Campos amplos aproximam-se do centro e começam a interagir suavemente
    // ==================================================================
    timeline.addLabel("q03", 1.15);
    timeline.to(
      [atmOrange, atmCoral],
      { opacity: 0.96, xPercent: 3, scale: 1.04, duration: 1.15, ease: "sine.inOut" },
      1.15
    );
    timeline.to(
      [atmTeal, atmCyan],
      { opacity: 0.96, xPercent: -3, scale: 1.04, duration: 1.15, ease: "sine.inOut" },
      1.15
    );
    timeline.to(
      coreHalo,
      { opacity: 0.62, scale: 1.02, duration: 0.42, ease: "power2.out" },
      1.14
    );
    timeline.to(
      innerCore,
      { opacity: 1, scale: 1, duration: 0.46, ease: "power3.out" },
      1.16
    );
    timeline.to(
      starGlow,
      { opacity: 0.08, scale: 0.85, duration: 0.36, ease: "sine.inOut" },
      1.28
    );

    // ==================================================================
    // Q04 — Estado B -> C: Adensamento orgânico das ondas em posições invertidas (1.65s – 2.35s)
    // Sem bolinhas: campos largos ganham direção preparando o cruzamento
    // ==================================================================
    timeline.addLabel("q04", 1.65);
    timeline.to(
      waveOrangeField,
      {
        opacity: 0.56,
        x: -235,
        y: -46,
        scaleX: 1.48,
        scaleY: 1.12,
        skewX: -10,
        duration: 0.68,
        ease: "sine.inOut",
      },
      1.65
    );
    timeline.to(
      waveTealField,
      {
        opacity: 0.56,
        x: 235,
        y: 46,
        scaleX: 1.48,
        scaleY: 1.12,
        skewX: 10,
        duration: 0.68,
        ease: "sine.inOut",
      },
      1.68
    );

    // ==================================================================
    // Q05 — Fluxo e troca de lados (2.35s – 3.55s)
    // Duas correntes luminosas cruzam-se em onda contínua trocando de lado:
    // - Laranja flui da ESQUERDA -> arco superior -> DIREITA
    // - Azul flui da DIREITA -> arco inferior -> ESQUERDA
    // ==================================================================
    timeline.addLabel("q05", 2.35);

    // Atmosfera acompanha o fluxo trocando de lado organicamente em arco
    timeline.to(
      [atmOrange, atmCoral],
      {
        keyframes: [
          { xPercent: 28, yPercent: -7, scale: 1.06, duration: 0.6, ease: "sine.in" },
          { xPercent: 56, yPercent: 2, scale: 0.96, duration: 0.6, ease: "sine.out" },
        ],
      },
      2.35
    );
    timeline.to(
      [atmTeal, atmCyan],
      {
        keyframes: [
          { xPercent: -28, yPercent: 7, scale: 1.06, duration: 0.6, ease: "sine.in" },
          { xPercent: -56, yPercent: -2, scale: 0.96, duration: 0.6, ease: "sine.out" },
        ],
      },
      2.35
    );

    // Onda luminosa LARANJA cruza por cima da esquerda (-245) -> centro (0, -92) -> direita (+215, 8)
    timeline.to(
      waveOrangeField,
      {
        keyframes: [
          {
            x: 0,
            y: -96,
            scaleX: 1.48,
            scaleY: 0.72,
            skewX: -14,
            opacity: 0.96,
            duration: 0.6,
            ease: "sine.in",
          },
          {
            x: 210,
            y: 12,
            scaleX: 1.04,
            scaleY: 0.96,
            skewX: 4,
            opacity: 0.78,
            duration: 0.6,
            ease: "sine.out",
          },
        ],
      },
      2.35
    );

    // Onda luminosa AZUL cruza por baixo da direita (+245) -> centro (0, +92) -> esquerda (-215, -8)
    timeline.to(
      waveTealField,
      {
        keyframes: [
          {
            x: 0,
            y: 96,
            scaleX: 1.48,
            scaleY: 0.72,
            skewX: 14,
            opacity: 0.96,
            duration: 0.6,
            ease: "sine.in",
          },
          {
            x: -210,
            y: -12,
            scaleX: 1.04,
            scaleY: 0.96,
            skewX: -4,
            opacity: 0.78,
            duration: 0.6,
            ease: "sine.out",
          },
        ],
      },
      2.35
    );

    // Rastros fluidos de corrente de luz percorrendo o cruzamento em S
    if (waveOrangeRibbon) {
      timeline.to(
        waveOrangeRibbon,
        { opacity: 0.62, strokeDashoffset: 0, duration: 0.72, ease: "power2.inOut" },
        2.4
      );
      timeline.to(
        waveOrangeRibbon,
        {
          opacity: 0,
          strokeDashoffset: -orangeRibbonLen * 0.55,
          duration: 0.45,
          ease: "sine.in",
        },
        3.08
      );
    }
    if (waveTealRibbon) {
      timeline.to(
        waveTealRibbon,
        { opacity: 0.65, strokeDashoffset: 0, duration: 0.72, ease: "power2.inOut" },
        2.42
      );
      timeline.to(
        waveTealRibbon,
        {
          opacity: 0,
          strokeDashoffset: -tealRibbonLen * 0.55,
          duration: 0.45,
          ease: "sine.in",
        },
        3.1
      );
    }

    // ==================================================================
    // Q06 — Formação do olho (3.40s – 4.35s)
    // As ondas se transformam nas formas definitivas do SVG mestre:
    // azul consolida à esquerda, laranja à direita + crescente branco
    // ==================================================================
    timeline.addLabel("q06", 3.4);

    // Formas oficiais emergem organicamente enquanto as ondas se fundem nelas
    timeline.to(
      tealShape,
      { opacity: 1, x: 0, scale: 1, duration: 0.85, ease: "power3.out" },
      3.4
    );
    timeline.to(
      clipTealEllipse,
      {
        attr: { cx: 340, cy: 412, rx: 430, ry: 340 },
        duration: 0.88,
        ease: "power2.out",
      },
      3.4
    );

    timeline.to(
      orangeShape,
      { opacity: 1, x: 0, scale: 1, duration: 0.85, ease: "power3.out" },
      3.42
    );
    timeline.to(
      clipOrangeEllipse,
      {
        attr: { cx: 640, cy: 435, rx: 440, ry: 350 },
        duration: 0.88,
        ease: "power2.out",
      },
      3.42
    );

    // Crescente branco define-se com precisão
    timeline.to(eyeContours, { opacity: 1, duration: 0.55, ease: "power2.out" }, 3.62);
    timeline.to(
      clipCrescentEllipse,
      {
        attr: { cx: 500, cy: 415, rx: 220, ry: 220 },
        duration: 0.68,
        ease: "power2.out",
      },
      3.62
    );

    // Ondas de fluxo e atmosfera são absorvidas para dentro do símbolo
    timeline.to(
      [waveOrangeField, waveTealField],
      { opacity: 0, scaleX: 0.72, scaleY: 0.72, duration: 0.65, ease: "power2.in" },
      3.55
    );
    timeline.to(
      [atmOrange, atmCoral, atmTeal, atmCyan],
      { opacity: 0, scale: 0.52, duration: 0.85, ease: "power2.in" },
      3.55
    );

    // Reflexos sutis de consolidação nas asas
    if (tealSweep) {
      timeline.to(
        tealSweep,
        { opacity: 0.52, strokeDashoffset: 0, duration: 0.5, ease: "power2.out" },
        3.72
      );
      timeline.to(
        tealSweep,
        { opacity: 0, strokeDashoffset: -tealSweepLen * 0.4, duration: 0.35, ease: "sine.in" },
        4.15
      );
    }
    if (orangeSweep) {
      timeline.to(
        orangeSweep,
        { opacity: 0.5, strokeDashoffset: 0, duration: 0.5, ease: "power2.out" },
        3.75
      );
      timeline.to(
        orangeSweep,
        { opacity: 0, strokeDashoffset: -orangeSweepLen * 0.4, duration: 0.35, ease: "sine.in" },
        4.18
      );
    }

    // ==================================================================
    // Q07 — Órbita com bolinha percorrendo o traçado + brilho final da estrela (4.20s – 5.60s)
    // ==================================================================
    timeline.addLabel("q07", 4.2);
    timeline.set(orbitalRing, { opacity: 1 }, 4.2);
    timeline.set(secondaryCurves, { opacity: 1 }, 4.28);
    timeline.to(orbitalAccent, { opacity: 1, duration: 0.14, ease: "sine.out" }, 4.2);
    timeline.to(dotHalo, { opacity: 0.68, duration: 0.16, ease: "sine.out" }, 4.2);

    timeline.to(
      [orbitalRing, orbitalAccent, dotHalo],
      { rotation: 0, duration: 0.85, ease: "power2.out" },
      4.2
    );
    timeline.to(
      orbitPath,
      { strokeDashoffset: 0, duration: 0.82, ease: "power2.inOut" },
      4.2
    );
    timeline.to(
      orbitHaloPath,
      { opacity: 0.44, strokeDashoffset: 0, duration: 0.82, ease: "power2.inOut" },
      4.2
    );
    timeline.to(
      [secArcLeft, secTailLine],
      { strokeDashoffset: 0, duration: 0.55, ease: "power2.out" },
      4.3
    );

    // Bolinha percorre continuamente o próprio path da órbita de (302, 216) até (876.5, 274)
    // Usa keyframes declarativos de `attr` (nativo do GSAP) para funcionar tanto em
    // reprodução contínua quanto em pause/scrub (`tl.pause(t)`), sem depender de onUpdate.
    if (orbitPath && orbitDotEl) {
      const dotTargets = dotHalo ? [orbitDotEl, dotHalo] : [orbitDotEl];
      const steps = 24;
      const stepDuration = 0.72 / steps;
      const easeInOutQuad = (p: number) =>
        p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;

      const dotKeyframes = Array.from({ length: steps }, (_, idx) => {
        const i = idx + 1;
        if (i === steps) {
          return {
            attr: { cx: 876.5, cy: 274 },
            duration: stepDuration,
            ease: "none",
          };
        }
        const easedProgress = easeInOutQuad(i / steps);
        const pt = orbitPath.getPointAtLength(easedProgress * orbitDotFinalDist);
        return {
          attr: { cx: Number(pt.x.toFixed(2)), cy: Number(pt.y.toFixed(2)) },
          duration: stepDuration,
          ease: "none",
        };
      });

      timeline.to(dotTargets, { keyframes: dotKeyframes }, 4.2);
    }

    // Dissipação dos halos orbitais/núcleo quando o símbolo completa sua forma
    timeline.to(
      [coreHalo, dotHalo, orbitHaloPath],
      { opacity: 0, duration: 0.48, ease: "power2.out" },
      4.98
    );

    // Brilho final delicado e breve da estrela como acabamento (5.00s -> 5.60s)
    timeline.to(
      starGlow,
      { opacity: 0.84, scale: 1.08, duration: 0.24, ease: "power2.out" },
      5.0
    );
    timeline.to(
      starGlow,
      { opacity: 0, scale: 0.9, duration: 0.36, ease: "power2.inOut" },
      5.24
    );
  }, root);

  return {
    timeline,
    cleanup: () => {
      ctx.revert();
    },
  };
}
