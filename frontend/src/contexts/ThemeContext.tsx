"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

const THEME_STORAGE_KEY = "iris.theme.dark_mode";
const HIGH_CONTRAST_STORAGE_KEY = "iris.theme.high_contrast";

interface ThemeContextValue {
  darkMode: boolean;
  setDarkMode: (value: boolean) => void;
  toggleDarkMode: () => void;
  highContrast: boolean;
  setHighContrast: (value: boolean) => void;
  toggleHighContrast: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

/**
 * Provider global de tema (Modo Claro / Escuro e Alto Contraste WCAG 2.1 AA) compartilhado via `app/layout.tsx`
 * entre todas as rotas (`/`, `/etapa-1`, `/etapa-2`, ...).
 * Persiste apenas a preferência visual na `sessionStorage` do navegador (Zero-Database).
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [darkMode, setDarkModeState] = useState<boolean>(false);
  const [highContrast, setHighContrastState] = useState<boolean>(false);
  const [hydrated, setHydrated] = useState<boolean>(false);

  useEffect(() => {
    try {
      const savedDark = window.sessionStorage.getItem(THEME_STORAGE_KEY);
      if (savedDark === "true") {
        setDarkModeState(true);
      }
      const savedHc = window.sessionStorage.getItem(HIGH_CONTRAST_STORAGE_KEY);
      if (savedHc === "true") {
        setHighContrastState(true);
      }
    } catch {
      // Ignora caso sessionStorage esteja indisponível no navegador
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (darkMode || highContrast) {
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
  }, [darkMode, highContrast, hydrated]);

  useEffect(() => {
    const root = document.documentElement;
    if (highContrast) {
      root.classList.add("high-contrast");
    } else {
      root.classList.remove("high-contrast");
    }

    if (!hydrated) return;
    try {
      window.sessionStorage.setItem(HIGH_CONTRAST_STORAGE_KEY, highContrast ? "true" : "false");
    } catch {
      // Ignora caso sessionStorage esteja indisponível no navegador
    }
  }, [highContrast, hydrated]);

  const setDarkMode = useCallback((value: boolean) => {
    setDarkModeState(value);
  }, []);

  const toggleDarkMode = useCallback(() => {
    setDarkModeState((prev) => !prev);
  }, []);

  const setHighContrast = useCallback((value: boolean) => {
    setHighContrastState(value);
  }, []);

  const toggleHighContrast = useCallback(() => {
    setHighContrastState((prev) => !prev);
  }, []);

  return (
    <ThemeContext.Provider
      value={{
        darkMode,
        setDarkMode,
        toggleDarkMode,
        highContrast,
        setHighContrast,
        toggleHighContrast,
      }}
    >
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
