/// <reference types="vite/client" />

interface Window {
  __AGENTGUARD_CONFIG__?: {
    apiOrigin?: string;
    pollIntervalMs?: number;
  };
}
