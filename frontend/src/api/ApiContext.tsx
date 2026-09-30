import { createContext, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiClient, normalizeApiOrigin } from "./client";

type Session = { origin: string; token: string; expiresAt: number; pollIntervalMs: number };
const storageKey = "agentguard.operator-session";
type ApiContextValue = {
  apiOrigin: string | null;
  client: ApiClient | null;
  pollIntervalMs: number;
  signIn: (session: Session) => void;
  signOut: () => Promise<void>;
};
const ApiContext = createContext<ApiContextValue | null>(null);

function restore(): Session | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) ?? "null") as Session | null;
    if (!value || value.expiresAt <= Date.now() || !value.token || !Number.isFinite(value.pollIntervalMs) || value.pollIntervalMs < 1000) return null;
    return { ...value, origin: normalizeApiOrigin(value.origin) };
  } catch { return null; }
}

export function ApiProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(restore);
  const queries = useQueryClient();
  const client = useMemo(() => session ? new ApiClient(session.origin, session.token) : null, [session]);
  const clear = () => { sessionStorage.removeItem(storageKey); setSession(null); queries.clear(); };
  useEffect(() => {
    const expired = (event: Event) => {
      if ((event as CustomEvent<string>).detail === session?.token) {
        sessionStorage.removeItem(storageKey); setSession(null); queries.clear();
      }
    };
    window.addEventListener("agentguard:session-expired", expired);
    return () => window.removeEventListener("agentguard:session-expired", expired);
  }, [session?.token, queries]);
  const signIn = (next: Session) => {
    sessionStorage.setItem(storageKey, JSON.stringify(next)); queries.clear(); setSession(next);
  };
  const signOut = async () => { try { await client?.post("/api/auth/logout"); } finally { clear(); } };
  return <ApiContext.Provider value={{ apiOrigin: session?.origin ?? null, client, pollIntervalMs: session?.pollIntervalMs ?? 0, signIn, signOut }}>{children}</ApiContext.Provider>;
}

export function useApi() {
  const value = useContext(ApiContext);
  if (!value) throw new Error("useApi must be used inside ApiProvider");
  return value;
}
