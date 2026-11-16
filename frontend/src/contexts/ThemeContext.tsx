"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

const THEME_STORAGE_KEY = "iris.theme.dark_mode";

interface ThemeContextValue {
  darkMode: boolean;
  setDarkMode: (value: boolean) => void;
  toggleDarkMode: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

/**
 * Provider global de tema (Modo Claro / Escuro) compartilhado via `app/layout.tsx`
 * entre todas as rotas (`/`, `/etapa-1`, `/etapa-2`, ...).
 * Persiste apenas a preferência visual na `sessionStorage` do navegador (Zero-Database).
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [darkMode, setDarkModeState] = useState<boolean>(false);
  const [hydrated, setHydrated] = useState<boolean>(false);

  useEffect(() => {
    try {
      const saved = window.sessionStorage.getItem(THEME_STORAGE_KEY);
      if (saved === "true") {
        setDarkModeState(true);
      }
    } catch {
      // Ignora caso sessionStorage esteja indisponível no navegador
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (darkMode) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }

    if (!hydrated) return;
    try {
      window.sessionStorage.setItem(THEME_STORAGE_KEY, darkMode ? "true" : "false");
    } catch {
      // Ignora caso sessionStorage esteja indisponível no navegador
    }
  }, [darkMode, hydrated]);

  const setDarkMode = useCallback((value: boolean) => {
    setDarkModeState(value);
  }, []);

  const toggleDarkMode = useCallback(() => {
    setDarkModeState((prev) => !prev);
  }, []);

  return (
    <ThemeContext.Provider value={{ darkMode, setDarkMode, toggleDarkMode }}>
      {children}
    </ThemeContext.Provider>
  );
}

/**
 * Hook para ler e alternar o tema compartilhado em qualquer página ou componente cliente.
 */
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme deve ser usado dentro de <ThemeProvider>.");
  }
  return context;
}
