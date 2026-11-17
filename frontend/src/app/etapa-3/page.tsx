"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { Step3ScaffoldingLevel } from "@/components/Step3ScaffoldingLevel";

export default function Etapa3Page() {
  const router = useRouter();

  return (
    <Step3ScaffoldingLevel
      teacherEmail="marina.alves@escola.edu.br"
      onBackToStep2={() => router.push("/etapa-2")}
      onAdvanceToNext={() => router.push("/etapa-4")}
    />
  );
}
