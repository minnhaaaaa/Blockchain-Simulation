import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

function runtimeConfig() {
  const file = process.env.AGENTGUARD_RUNTIME_FILE;
  const supplied = file ? JSON.parse(readFileSync(file, "utf8")) : {};
  // A private launcher access file must never leak credentials if selected
  // accidentally. Only publish explicitly allowed connection metadata.
  const value = {
    ...(typeof supplied.apiOrigin === "string" ? { apiOrigin: supplied.apiOrigin } : {}),
    ...(typeof supplied.pollIntervalMs === "number" ? { pollIntervalMs: supplied.pollIntervalMs } : {}),
    ...(Array.isArray(supplied.nodes) ? { nodes: supplied.nodes.map((node: { name: string; apiOrigin: string }) => ({ name: node.name, apiOrigin: node.apiOrigin })) } : {})
  };
  return `window.__AGENTGUARD_CONFIG__ = ${JSON.stringify(value).replaceAll("<", "\\u003c")};`;
}

export default defineConfig({
  plugins: [react(), {
    name: "operator-runtime-configuration",
    configureServer(server) {
      server.middlewares.use("/runtime-config.js", (_req, res) => {
        res.setHeader("Content-Type", "application/javascript"); res.setHeader("Cache-Control", "no-store"); res.end(runtimeConfig());
      });
    },
    generateBundle() { this.emitFile({ type: "asset", fileName: "runtime-config.js", source: runtimeConfig() }); }
  }],
  define: { __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? "development") },
  build: { sourcemap: true },
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    include: ["tests/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**"],
    css: true,
    coverage: { reporter: ["text", "html"] }
  }
});
