"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Step1MaterialIntake } from "@/components/Step1MaterialIntake";

export default function Etapa1Page() {
  const router = useRouter();
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    if (darkMode) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }, [darkMode]);

  return (
    <Step1MaterialIntake
      teacherEmail="marina.alves@escola.edu.br"
      onAdvanceToStep2={() => router.push("/etapa-2")}
      darkMode={darkMode}
      onToggleDarkMode={() => setDarkMode((prev) => !prev)}
    />
  );
}

