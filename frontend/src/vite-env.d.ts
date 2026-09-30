/// <reference types="vite/client" />

interface Window {
  __AGENTGUARD_CONFIG__?: {
    apiOrigin?: string;
    pollIntervalMs?: number;
    nodes?: { name: string; apiOrigin: string }[];
  };
}
