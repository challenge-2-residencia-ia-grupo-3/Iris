"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  type AuthProvidersStatus,
  type AuthSession,
  type TeacherProfile,
  clearStoredAuthSession,
  deleteTeacherAccount,
  exchangeGoogleOAuthCode,
  fetchAuthProviders,
  fetchCurrentTeacher,
  loadStoredAuthSession,
  loginTeacher,
  logoutTeacher,
  registerTeacher,
  saveStoredAuthSession,
} from "@/services/authApi";

interface AuthContextValue {
  teacher: TeacherProfile | null;
  session: AuthSession | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  providers: AuthProvidersStatus;
  login: (email: string, senha: string) => Promise<AuthSession>;
  register: (email: string, nomeExibicao: string, senha: string) => Promise<AuthSession>;
  completeOAuthExchange: (code: string) => Promise<AuthSession>;
  logout: () => Promise<void>;
  deleteMyAccount: () => Promise<void>;
}

const DEFAULT_PROVIDERS: AuthProvidersStatus = {
  local_enabled: true,
  google_enabled: false,
  guest_mode_enabled: true,
  database_online: false,
};

const DEFAULT_CONTEXT: AuthContextValue = {
  teacher: null,
  session: null,
  isAuthenticated: false,
  isLoading: false,
  providers: DEFAULT_PROVIDERS,
  login: async () => {
    throw new Error("AuthProvider não inicializado.");
  },
  register: async () => {
    throw new Error("AuthProvider não inicializado.");
  },
  completeOAuthExchange: async () => {
    throw new Error("AuthProvider não inicializado.");
  },
  logout: async () => {},
  deleteMyAccount: async () => {},
};

const AuthContext = createContext<AuthContextValue>(DEFAULT_CONTEXT);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [providers, setProviders] = useState<AuthProvidersStatus>(DEFAULT_PROVIDERS);

  useEffect(() => {
    let mounted = true;
    const init = async () => {
      const stored = loadStoredAuthSession();
      if (stored && mounted) {
        setSession(stored);
      }

      fetchAuthProviders()
        .then((status) => {
          if (mounted) setProviders(status);
        })
        .catch(() => {
          // Mantém defaults quando backend estiver offline
        });

      if (stored) {
        try {
          const freshTeacher = await fetchCurrentTeacher();
          if (mounted) {
            const latest = loadStoredAuthSession() ?? stored;
            const updated: AuthSession = { ...latest, teacher: freshTeacher };
            saveStoredAuthSession(updated);
            setSession(updated);
          }
        } catch {
          if (mounted) {
            clearStoredAuthSession();
            setSession(null);
          }
        }
      }

      if (mounted) setIsLoading(false);
    };

    init();
    return () => {
      mounted = false;
    };
  }, []);

  const login = useCallback(async (email: string, senha: string) => {
    const newSession = await loginTeacher({ email, senha });
    setSession(newSession);
    return newSession;
  }, []);

  const register = useCallback(async (email: string, nomeExibicao: string, senha: string) => {
    const newSession = await registerTeacher({ email, nome_exibicao: nomeExibicao, senha });
    setSession(newSession);
    return newSession;
  }, []);

  const completeOAuthExchange = useCallback(async (code: string) => {
    const newSession = await exchangeGoogleOAuthCode(code);
    setSession(newSession);
    return newSession;
  }, []);

  const logout = useCallback(async () => {
    const current = loadStoredAuthSession();
    await logoutTeacher(current?.refresh_token);
    setSession(null);
  }, []);

  const deleteMyAccount = useCallback(async () => {
    await deleteTeacherAccount();
    setSession(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        teacher: session?.teacher ?? null,
        session,
        isAuthenticated: Boolean(session?.teacher && session?.access_token),
        isLoading,
        providers,
        login,
        register,
        completeOAuthExchange,
        logout,
        deleteMyAccount,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
