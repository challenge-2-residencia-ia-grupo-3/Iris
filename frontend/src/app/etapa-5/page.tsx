"use client";

import React, { useEffect, useState } from "react";
import { Step5Review } from "@/components/Step5Review";
import { ETAPA5_DEMO } from "@/services/etapa5Demo";
import { Step5Entrada, STEP5_ADAPTACAO_STORAGE_KEY, validarEntrada } from "@/services/comparisonCards";
import { type HistoryActivityDetail, getHistoryActivity } from "@/services/historyApi";

export default function Etapa5Page() {
  const [entrada, setEntrada] = useState<Step5Entrada | null>(null);
  const [historyItem, setHistoryItem] = useState<HistoryActivityDetail | null>(null);
  const [demo, setDemo] = useState(false);
  const [pronto, setPronto] = useState(false);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const params = new URLSearchParams(window.location.search);
        const historyId = params.get("historyId");
        if (historyId) {
          const item = await getHistoryActivity(historyId);
          if (!mounted) return;
          const fallbackCarac = item.caracteristicas_ids[0] ?? "sobrecarga_memoria_trabalho_comandos_multiplos";
          setHistoryItem(item);
          setEntrada({
            titulo: item.titulo,
            questoes: item.questoes.map((q) => ({
              id: q.id,
              original: q.original,
              adaptado: q.adaptado,
              justificativas: q.justificativas ?? [],
              id_caracteristica: fallbackCarac,
              nivel: item.nivel_andaime,
              adaptacao_aplicada: true,
            })),
          });
          setPronto(true);
          return;
        }
        if (params.get("demo") === "1") {
          setEntrada(ETAPA5_DEMO);
          setDemo(true);
        } else {
          const bruto = window.sessionStorage.getItem(STEP5_ADAPTACAO_STORAGE_KEY);
          if (bruto) setEntrada(validarEntrada(JSON.parse(bruto)));
        }
      } catch {
        // sessionStorage indisponível ou atividade de histórico inacessível
      }
      if (mounted) setPronto(true);
    };

    load();
    return () => {
      mounted = false;
    };
  }, []);

  if (!pronto) return null;
  return <Step5Review entrada={entrada} demo={demo} historyItem={historyItem} />;
}
