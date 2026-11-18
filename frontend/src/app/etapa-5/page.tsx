"use client";

import React, { useEffect, useState } from "react";
import { Step5Review } from "@/components/Step5Review";
import { ETAPA5_DEMO } from "@/services/etapa5Demo";
import { Step5Entrada, STEP5_ADAPTACAO_STORAGE_KEY, validarEntrada } from "@/services/comparisonCards";

export default function Etapa5Page() {
  const [entrada, setEntrada] = useState<Step5Entrada | null>(null);
  const [demo, setDemo] = useState(false);
  const [pronto, setPronto] = useState(false);

  useEffect(() => {
    try {
      if (new URLSearchParams(window.location.search).get("demo") === "1") {
        setEntrada(ETAPA5_DEMO);
        setDemo(true);
      } else {
        const bruto = window.sessionStorage.getItem(STEP5_ADAPTACAO_STORAGE_KEY);
        if (bruto) setEntrada(validarEntrada(JSON.parse(bruto)));
      }
    } catch {
      // sessionStorage indisponível ou conteúdo inválido: segue sem adaptação
    }
    setPronto(true);
  }, []);

  if (!pronto) return null;
  return <Step5Review entrada={entrada} demo={demo} />;
}
