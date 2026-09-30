import { defineConfig, devices } from "@playwright/test";
import { readFileSync } from "node:fs";

const accessFile = process.env.AGENTGUARD_LIVE_ACCESS;
if (!accessFile) throw new Error("Start a real network with npm run demo -- --config <profile> --ready-file <path>, then set AGENTGUARD_LIVE_ACCESS to that path. These tests never intercept or mock the API.");
const access = JSON.parse(readFileSync(accessFile, "utf8")) as { uiOrigin: string };
export default defineConfig({
  testDir: "./e2e", workers: 1, timeout: 90_000, fullyParallel: false,
  use: { baseURL: access.uiOrigin, trace: "off", screenshot: "only-on-failure", ...(process.env.AGENTGUARD_BROWSER_CHANNEL ? { channel: process.env.AGENTGUARD_BROWSER_CHANNEL } : {}) },
  reporter: [["list"]],
  projects: [{ name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1050 } } }, { name: "mobile", use: { ...devices["Pixel 7"] } }]
});
