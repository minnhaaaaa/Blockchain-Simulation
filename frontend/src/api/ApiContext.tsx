import { createContext, useContext, useMemo, useState, type PropsWithChildren } from "react";
import { ApiClient, normalizeApiOrigin } from "./client";

const STORAGE_KEY = "agentguard.api-origin";
const configuredOrigin = window.__AGENTGUARD_CONFIG__?.apiOrigin;
const configuredPoll = window.__AGENTGUARD_CONFIG__?.pollIntervalMs;

type ApiContextValue = {
  apiOrigin: string | null;
  client: ApiClient | null;
  pollIntervalMs: number;
  setApiOrigin: (origin: string | null) => void;
};

const ApiContext = createContext<ApiContextValue | null>(null);

function initialOrigin() {
  const candidate = configuredOrigin ?? localStorage.getItem(STORAGE_KEY);
  if (!candidate) return null;
  try { return normalizeApiOrigin(candidate); } catch { return null; }
}

export function ApiProvider({ children }: PropsWithChildren) {
  const [apiOrigin, setOrigin] = useState<string | null>(initialOrigin);
  const pollIntervalMs = typeof configuredPoll === "number" && configuredPoll >= 1000 ? configuredPoll : 5000;
  const setApiOrigin = (origin: string | null) => {
    if (origin === null) { localStorage.removeItem(STORAGE_KEY); setOrigin(null); return; }
    const normalized = normalizeApiOrigin(origin);
    localStorage.setItem(STORAGE_KEY, normalized);
    setOrigin(normalized);
  };
  const value = useMemo<ApiContextValue>(() => ({
    apiOrigin,
    client: apiOrigin ? new ApiClient(apiOrigin) : null,
    pollIntervalMs,
    setApiOrigin
  }), [apiOrigin, pollIntervalMs]);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi() {
  const value = useContext(ApiContext);
  if (!value) throw new Error("useApi must be used inside ApiProvider");
  return value;
}
