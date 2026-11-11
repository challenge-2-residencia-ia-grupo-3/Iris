"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Step2FunctionalProfile } from "@/components/Step2FunctionalProfile";
import { STEP1_MATERIAL_STORAGE_KEY } from "@/services/catalogsApi";

export default function Etapa2Page() {
  const router = useRouter();
  const [darkMode, setDarkMode] = useState(false);
  const [materialText, setMaterialText] = useState<string>("");

  useEffect(() => {
    const root = document.documentElement;
    if (darkMode) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }, [darkMode]);

  useEffect(() => {
    try {
      const savedMaterial = window.sessionStorage.getItem(STEP1_MATERIAL_STORAGE_KEY);
      if (savedMaterial) {
        setMaterialText(savedMaterial);
      }
    } catch {
      // Ignora caso sessionStorage não esteja acessível
    }
  }, []);

  return (
    <Step2FunctionalProfile
      teacherEmail="marina.alves@escola.edu.br"
      materialPreviewText={materialText}
      onBackToStep1={() => router.push("/etapa-1")}
      darkMode={darkMode}
      onToggleDarkMode={() => setDarkMode((prev) => !prev)}
    />
  );
}
