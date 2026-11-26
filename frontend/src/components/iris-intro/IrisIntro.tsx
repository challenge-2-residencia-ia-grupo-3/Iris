"use client";

import React, { useEffect, useRef, useState } from "react";
import type gsap from "gsap";
import {
  createIrisIntroTimeline,
  IRIS_TIMELINE_DURATION,
} from "./IrisAnimation";
import "./IrisIntro.css";

export interface IrisIntroProps {
  /** Força o modo estático (útil para testes de acessibilidade/movimento reduzido) */
  reducedMotion?: boolean;
  /** Callback disparado quando a timeline GSAP está pronta para controle externo */
  onTimelineReady?: (timeline: gsap.core.Timeline | null) => void;
  /** Callback de progresso da timeline (em segundos) */
  onTimeUpdate?: (time: number) => void;
  /** Callback ao finalizar a animação */
  onComplete?: () => void;
}

/**
 * Componente cinematográfico de abertura da marca Íris (Etapa 05).
 * Utiliza inline o SVG mestre aprovado (`assets/iris/iris-master.svg`),
 * preservando integralmente geometria, gradientes e identificadores das 8 camadas.
 * Resultado final apresenta exclusivamente o símbolo do olho (sem texto).
 */
export function IrisIntro({
  reducedMotion,
  onTimelineReady,
  onTimeUpdate,
  onComplete,
}: IrisIntroProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [prefersReduced, setPrefersReduced] = useState(false);

  // Detecta preferência do sistema operacional (prefers-reduced-motion)
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setPrefersReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const isReduced = reducedMotion ?? prefersReduced;

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    if (isReduced) {
      onTimelineReady?.(null);
      onTimeUpdate?.(IRIS_TIMELINE_DURATION);
      return;
    }

    const { timeline, cleanup } = createIrisIntroTimeline(root, {
      onTimeUpdate,
      onComplete,
    });

    onTimelineReady?.(timeline);

    return () => {
      cleanup();
      onTimelineReady?.(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReduced]);

  return (
    <section
      ref={rootRef}
      className={`iris-intro-root${isReduced ? " is-reduced-motion" : ""}`}
      aria-label="Abertura da marca Íris"
    >
      {/* Campos atmosféricos amplos (iniciam em posições invertidas e cruzam em onda) */}
      <div className="iris-atmosphere" aria-hidden="true">
        <div className="iris-atm-field iris-atm-orange" />
        <div className="iris-atm-field iris-atm-coral" />
        <div className="iris-atm-field iris-atm-teal" />
        <div className="iris-atm-field iris-atm-cyan" />
      </div>

      {/* Palco principal: exclusivamente o símbolo oficial */}
      <div className="iris-stage">
        <div className="iris-symbol-wrap">
          <svg
            className="iris-master-svg"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 1000 800"
            role="img"
            aria-label="Símbolo oficial da Íris"
          >
            <defs>
              {/* === GRADIENTES OFICIAIS APROVADOS (iris-master.svg) === */}
              <linearGradient id="orbit-grad" x1="15%" y1="15%" x2="88%" y2="75%">
                <stop offset="0%" stopColor="#224552" />
                <stop offset="35%" stopColor="#3B4954" />
                <stop offset="65%" stopColor="#8B483C" />
                <stop offset="100%" stopColor="#BD452F" />
              </linearGradient>

              <linearGradient id="teal-outer-grad" x1="32%" y1="5%" x2="48%" y2="95%">
                <stop offset="0%" stopColor="#399CAD" />
                <stop offset="22%" stopColor="#247387" />
                <stop offset="52%" stopColor="#134C5E" />
                <stop offset="82%" stopColor="#092C3C" />
                <stop offset="100%" stopColor="#051C2B" />
              </linearGradient>

              <linearGradient id="teal-inner-grad" x1="25%" y1="8%" x2="72%" y2="92%">
                <stop offset="0%" stopColor="#144454" />
                <stop offset="38%" stopColor="#0D3140" />
                <stop offset="72%" stopColor="#082332" />
                <stop offset="100%" stopColor="#041522" />
              </linearGradient>

              <radialGradient id="teal-soft-luminance" cx="76%" cy="54%" r="36%" fx="80%" fy="54%">
                <stop offset="0%" stopColor="#35A8B8" stopOpacity="0.72" />
                <stop offset="45%" stopColor="#1A6A7C" stopOpacity="0.32" />
                <stop offset="100%" stopColor="#092938" stopOpacity="0" />
              </radialGradient>

              <linearGradient id="top-bridge-grad" x1="0%" y1="50%" x2="100%" y2="50%">
                <stop offset="0%" stopColor="#1A4F5F" stopOpacity="0" />
                <stop offset="28%" stopColor="#5A6C72" stopOpacity="0.72" />
                <stop offset="56%" stopColor="#BF846E" stopOpacity="0.90" />
                <stop offset="82%" stopColor="#E47A4C" stopOpacity="0.65" />
                <stop offset="100%" stopColor="#F68240" stopOpacity="0" />
              </linearGradient>

              <linearGradient id="orange-outer-grad" x1="25%" y1="10%" x2="78%" y2="85%">
                <stop offset="0%" stopColor="#F68B46" />
                <stop offset="35%" stopColor="#F77B35" />
                <stop offset="72%" stopColor="#F16626" />
                <stop offset="100%" stopColor="#E4521E" />
              </linearGradient>

              <linearGradient id="orange-tail-grad" x1="78%" y1="18%" x2="18%" y2="94%">
                <stop offset="0%" stopColor="#F06424" />
                <stop offset="36%" stopColor="#F48244" />
                <stop offset="68%" stopColor="#FCCEB2" />
                <stop offset="86%" stopColor="#F7A77C" />
                <stop offset="100%" stopColor="#DC5326" />
              </linearGradient>

              <linearGradient id="orange-recess-grad" x1="15%" y1="15%" x2="82%" y2="85%">
                <stop offset="0%" stopColor="#B83B18" stopOpacity="0.92" />
                <stop offset="52%" stopColor="#DC4B1D" stopOpacity="0.88" />
                <stop offset="100%" stopColor="#F26C2C" stopOpacity="0" />
              </linearGradient>

              <radialGradient id="core-base-grad" cx="50%" cy="50%" r="52%">
                <stop offset="0%" stopColor="#170726" />
                <stop offset="62%" stopColor="#12041E" />
                <stop offset="100%" stopColor="#0B0115" />
              </radialGradient>

              <radialGradient id="core-subtle-teal-edge" cx="24%" cy="76%" r="32%">
                <stop offset="0%" stopColor="#228B9C" stopOpacity="0.28" />
                <stop offset="100%" stopColor="#12041E" stopOpacity="0" />
              </radialGradient>

              <radialGradient id="core-subtle-warm-edge" cx="76%" cy="28%" r="34%">
                <stop offset="0%" stopColor="#C4532E" stopOpacity="0.24" />
                <stop offset="100%" stopColor="#12041E" stopOpacity="0" />
              </radialGradient>

              <linearGradient id="secondary-curve-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#C86A54" stopOpacity="0.15" />
                <stop offset="45%" stopColor="#CC5536" stopOpacity="0.85" />
                <stop offset="100%" stopColor="#DC5224" stopOpacity="0.95" />
              </linearGradient>

              {/* === CAMADAS ORGÂNICAS DE ONDA / FLUXO (Q04 -> Q06, ZERAM EM Q07) === */}
              <radialGradient id="iris-wave-orange-grad" cx="46%" cy="48%" r="52%">
                <stop offset="0%" stopColor="#FFA96B" stopOpacity="0.78" />
                <stop offset="36%" stopColor="#F16626" stopOpacity="0.54" />
                <stop offset="72%" stopColor="#B83B18" stopOpacity="0.18" />
                <stop offset="100%" stopColor="#0D0221" stopOpacity="0" />
              </radialGradient>

              <radialGradient id="iris-wave-teal-grad" cx="54%" cy="52%" r="52%">
                <stop offset="0%" stopColor="#5CD0DF" stopOpacity="0.78" />
                <stop offset="36%" stopColor="#247387" stopOpacity="0.54" />
                <stop offset="72%" stopColor="#0D3140" stopOpacity="0.20" />
                <stop offset="100%" stopColor="#0D0221" stopOpacity="0" />
              </radialGradient>

              <linearGradient id="iris-ribbon-orange-grad" x1="0%" y1="50%" x2="100%" y2="50%">
                <stop offset="0%" stopColor="#F68B46" stopOpacity="0" />
                <stop offset="45%" stopColor="#FFAE72" stopOpacity="0.82" />
                <stop offset="85%" stopColor="#F16626" stopOpacity="0.65" />
                <stop offset="100%" stopColor="#F16626" stopOpacity="0" />
              </linearGradient>

              <linearGradient id="iris-ribbon-teal-grad" x1="100%" y1="50%" x2="0%" y2="50%">
                <stop offset="0%" stopColor="#399CAD" stopOpacity="0" />
                <stop offset="45%" stopColor="#72DFEC" stopOpacity="0.82" />
                <stop offset="85%" stopColor="#247387" stopOpacity="0.65" />
                <stop offset="100%" stopColor="#247387" stopOpacity="0" />
              </linearGradient>

              {/* === EFEITOS LUMINOSOS TEMPORÁRIOS DA ANIMAÇÃO (ZERAM EM Q07) === */}
              <radialGradient id="iris-core-halo-grad" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.24" />
                <stop offset="48%" stopColor="#399CAD" stopOpacity="0.12" />
                <stop offset="100%" stopColor="#0D0221" stopOpacity="0" />
              </radialGradient>

              <radialGradient id="iris-star-glow-grad" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.92" />
                <stop offset="32%" stopColor="#B8E8F2" stopOpacity="0.44" />
                <stop offset="70%" stopColor="#399CAD" stopOpacity="0.12" />
                <stop offset="100%" stopColor="#0D0221" stopOpacity="0" />
              </radialGradient>

              <radialGradient id="iris-dot-halo-grad" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#FF9A5A" stopOpacity="0.72" />
                <stop offset="52%" stopColor="#DD4119" stopOpacity="0.24" />
                <stop offset="100%" stopColor="#0D0221" stopOpacity="0" />
              </radialGradient>

              <filter id="iris-glow-blur" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="4" />
              </filter>

              <filter id="iris-wave-soft" x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur stdDeviation="16" />
              </filter>

              {/* === CLIP PATHS ORGÂNICOS PARA REVELAÇÃO PROGRESSIVA (Q06) === */}
              {!isReduced && (
                <>
                  <clipPath id="iris-clip-teal">
                    <ellipse id="iris-clip-teal-ellipse" cx="340" cy="412" rx="430" ry="340" />
                  </clipPath>
                  <clipPath id="iris-clip-orange">
                    <ellipse id="iris-clip-orange-ellipse" cx="640" cy="435" rx="440" ry="350" />
                  </clipPath>
                  <clipPath id="iris-clip-crescent">
                    <ellipse id="iris-clip-crescent-ellipse" cx="500" cy="415" rx="220" ry="220" />
                  </clipPath>
                </>
              )}
            </defs>

            {/* Ondas amplas de fluxo orgânico (Q04 invertidas -> Q05 cruzamento -> Q06 absorção) */}
            {!isReduced && (
              <g aria-hidden="true">
                {/* Onda Laranja/Coral: nasce à esquerda, cruza por cima para a direita */}
                <path
                  id="iris-wave-orange-field"
                  d="M 220 390 C 310 215, 585 180, 745 315 C 835 390, 790 545, 635 585 C 460 630, 155 520, 220 390 Z"
                  fill="url(#iris-wave-orange-grad)"
                  filter="url(#iris-wave-soft)"
                />
                {/* Onda Azul/Ciano: nasce à direita, cruza por baixo para a esquerda */}
                <path
                  id="iris-wave-teal-field"
                  d="M 780 435 C 690 610, 415 645, 255 510 C 165 435, 210 280, 365 240 C 540 195, 845 305, 780 435 Z"
                  fill="url(#iris-wave-teal-grad)"
                  filter="url(#iris-wave-soft)"
                />
                {/* Correntes luminosas em S durante o cruzamento (Q05) */}
                <path
                  id="iris-wave-orange-ribbon"
                  d="M 110 385 C 290 165, 650 140, 885 405"
                  fill="none"
                  stroke="url(#iris-ribbon-orange-grad)"
                  strokeWidth="24"
                  strokeLinecap="round"
                  filter="url(#iris-wave-soft)"
                />
                <path
                  id="iris-wave-teal-ribbon"
                  d="M 890 435 C 710 655, 350 680, 115 415"
                  fill="none"
                  stroke="url(#iris-ribbon-teal-grad)"
                  strokeWidth="24"
                  strokeLinecap="round"
                  filter="url(#iris-wave-soft)"
                />
              </g>
            )}

            {/* Halo suave temporário do núcleo (Q03 -> Q07) */}
            {!isReduced && (
              <circle
                id="iris-core-halo"
                cx="550"
                cy="412"
                r="220"
                fill="url(#iris-core-halo-grad)"
              />
            )}

            {/* 3. TEAL SHAPE (Asa azul-petróleo — posição definitiva à esquerda) */}
            <g clipPath={isReduced ? undefined : "url(#iris-clip-teal)"}>
              <g id="teal-shape">
                <path
                  id="teal-outer-wing"
                  d="M 80 418 C 155 322, 288 196, 488 196 C 518 196, 548 202, 568 212 C 535 232, 502 252, 476 268 C 402 288, 365 348, 365 415 C 365 498, 422 562, 526 578 C 368 632, 198 572, 80 418 Z"
                  fill="url(#teal-outer-grad)"
                />
                <path
                  id="teal-inner-layer"
                  d="M 488 196 C 356 206, 268 292, 268 392 C 268 492, 354 574, 522 574 C 422 558, 365 496, 365 415 C 365 348, 402 288, 476 268 C 506 244, 536 222, 568 212 C 545 201, 518 196, 488 196 Z"
                  fill="url(#teal-inner-grad)"
                />
                <path
                  id="teal-inner-luminance"
                  d="M 488 196 C 356 206, 268 292, 268 392 C 268 492, 354 574, 522 574 C 422 558, 365 496, 365 415 C 365 348, 402 288, 476 268 C 506 244, 536 222, 568 212 C 545 201, 518 196, 488 196 Z"
                  fill="url(#teal-soft-luminance)"
                />
              </g>
            </g>

            {/* 4. ORANGE SHAPE (Asa coral-laranja + cauda pêssego — posição definitiva à direita) */}
            <g clipPath={isReduced ? undefined : "url(#iris-clip-orange)"}>
              <g id="orange-shape">
                <path
                  id="orange-outer-wing"
                  d="M 488 196 C 655 196, 804 282, 905 415 C 818 538, 672 648, 476 672 C 432 676, 392 674, 356 666 C 492 644, 622 562, 678 456 C 702 410, 692 346, 650 302 C 610 262, 558 248, 496 254 C 520 226, 534 206, 488 196 Z"
                  fill="url(#orange-outer-grad)"
                />
                <path
                  id="orange-swoop-tail"
                  d="M 488 196 C 632 200, 756 286, 788 408 C 812 500, 742 592, 620 638 C 530 672, 434 676, 356 666 C 496 640, 628 552, 682 448 C 704 402, 692 340, 646 296 C 604 256, 552 246, 496 254 C 522 226, 532 206, 488 196 Z"
                  fill="url(#orange-tail-grad)"
                />
                <path
                  id="orange-inner-recess"
                  d="M 578 268 C 652 288, 718 348, 718 424 C 718 498, 656 556, 582 582 C 638 532, 682 476, 682 412 C 682 348, 642 294, 578 268 Z"
                  fill="url(#orange-recess-grad)"
                />
                <path
                  id="orange-top-bridge"
                  d="M 412 202 C 470 194, 545 195, 608 208 C 578 232, 542 250, 496 262 C 456 265, 424 276, 396 294 C 402 252, 408 222, 412 202 Z"
                  fill="url(#top-bridge-grad)"
                />
              </g>
            </g>

            {/* Reflexos luminosos temporários nas asas (Q06) */}
            {!isReduced && (
              <>
                <path
                  id="iris-glow-teal-sweep"
                  d="M 105 390 C 185 290, 310 208, 468 198"
                  fill="none"
                  stroke="#7CEAF5"
                  strokeWidth="5.5"
                  strokeLinecap="round"
                  filter="url(#iris-glow-blur)"
                />
                <path
                  id="iris-glow-orange-sweep"
                  d="M 885 434 C 795 548, 655 642, 468 668"
                  fill="none"
                  stroke="#FFD2AC"
                  strokeWidth="5.5"
                  strokeLinecap="round"
                  filter="url(#iris-glow-blur)"
                />
              </>
            )}

            {/* 6. ORBITAL RING (Giro orbital fluido até rotation: 0 em Q07) */}
            <g id="orbital-ring">
              {!isReduced && (
                <path
                  id="iris-orbit-halo-path"
                  d="M 302 216 A 352 320 0 1 1 750 701"
                  fill="none"
                  stroke="#FFB27D"
                  strokeWidth="6"
                  strokeLinecap="round"
                  filter="url(#iris-glow-blur)"
                />
              )}
              <path
                id="orbital-ring-path"
                d="M 302 216 A 352 320 0 1 1 750 701"
                fill="none"
                stroke="url(#orbit-grad)"
                strokeWidth="3.2"
                strokeLinecap="round"
              />
            </g>

            {/* 5. EYE CONTOURS (Crescente branco característico) */}
            <g clipPath={isReduced ? undefined : "url(#iris-clip-crescent)"}>
              <g id="eye-contours">
                <path
                  id="white-crescent"
                  d="M 594 278 C 542 252, 466 260, 414 306 C 374 342, 363 384, 363 415 C 363 488, 412 548, 486 572 C 538 588, 598 568, 642 522 C 594 554, 534 560, 484 534 C 436 508, 408 464, 408 412 C 408 348, 448 294, 508 276 C 536 268, 566 270, 594 278 Z"
                  fill="#FFFFFF"
                />
              </g>
            </g>

            {/* 8. SECONDARY CURVES (Linhas curvas complementares) */}
            <g id="secondary-curves">
              <path
                id="secondary-lower-left-arc"
                d="M 142 522 C 204 606, 294 658, 396 668"
                fill="none"
                stroke="url(#secondary-curve-grad)"
                strokeWidth="2.6"
                strokeLinecap="round"
              />
              <path
                id="secondary-crescent-tail-line"
                d="M 486 572 C 540 588, 600 568, 644 520"
                fill="none"
                stroke="#1E4B5A"
                strokeWidth="1.6"
                strokeOpacity="0.55"
                strokeLinecap="round"
              />
            </g>

            {/* 2. INNER CORE (Núcleo circular roxo quase preto) */}
            <g id="inner-core">
              <circle id="inner-core-base" cx="550" cy="412" r="143" fill="url(#core-base-grad)" />
              <circle
                id="inner-core-edge-teal"
                cx="550"
                cy="412"
                r="143"
                fill="url(#core-subtle-teal-edge)"
              />
              <circle
                id="inner-core-edge-warm"
                cx="550"
                cy="412"
                r="143"
                fill="url(#core-subtle-warm-edge)"
              />
            </g>

            {/* Brilho discreto temporário da estrela (Q02 -> Q07) */}
            {!isReduced && (
              <circle
                id="iris-star-glow"
                cx="554"
                cy="413"
                r="112"
                fill="url(#iris-star-glow-grad)"
              />
            )}

            {/* 1. CENTRAL STAR (Estrela branca de 4 pontas) */}
            <g id="central-star">
              <path
                id="star-shape"
                d="M 554 352 C 558 394, 574 409, 614 413 C 574 417, 558 432, 554 474 C 550 432, 534 417, 494 413 C 534 409, 550 394, 554 352 Z"
                fill="#FFFFFF"
              />
            </g>

            {/* Halo sutil temporário do ponto orbital (Q07) */}
            {!isReduced && (
              <circle
                id="iris-dot-halo"
                cx="876.5"
                cy="274"
                r="46"
                fill="url(#iris-dot-halo-grad)"
              />
            )}

            {/* 7. ORBITAL ACCENT (Pequeno ponto laranja simples sobre a órbita) */}
            <g id="orbital-accent">
              <circle id="orbital-accent-dot" cx="876.5" cy="274" r="23" fill="#DD4119" />
            </g>
          </svg>
        </div>
      </div>
    </section>
  );
}
