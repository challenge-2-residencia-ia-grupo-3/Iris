"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { Step1MaterialIntake } from "@/components/Step1MaterialIntake";

export default function Etapa1Page() {
  const router = useRouter();

  return (
    <Step1MaterialIntake
      teacherEmail="marina.alves@escola.edu.br"
      onBackToLogin={() => router.push("/")}
      onAdvanceToStep2={() => router.push("/etapa-2")}
    />
  );
}

