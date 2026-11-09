"use client";

import React, { useEffect, useState } from "react";
import { Step1MaterialIntake } from "@/components/Step1MaterialIntake";

export default function Etapa1Page() {
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
      darkMode={darkMode}
      onToggleDarkMode={() => setDarkMode((prev) => !prev)}
    />
  );
}
