import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const virtualenv = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const python = process.env.AGENTGUARD_PYTHON || (existsSync(virtualenv) ? virtualenv : (process.platform === "win32" ? "python" : "python3"));
const child = spawn(python, [path.join(root, "scripts/live_demo.py"), ...process.argv.slice(2)], { cwd: root, env: process.env, stdio: "inherit" });
child.on("error", error => { console.error(error.message); process.exitCode = 1; });
child.on("exit", code => { process.exitCode = code ?? 1; });
process.on("SIGINT", () => child.kill("SIGINT"));
process.on("SIGTERM", () => child.kill("SIGTERM"));
