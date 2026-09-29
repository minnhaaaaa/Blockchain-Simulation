import { generateKeyPairSync, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const frontendRoot = path.join(repositoryRoot, "frontend");
const workspacePython = path.join(repositoryRoot, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const python = process.env.AGENTGUARD_PYTHON || (existsSync(workspacePython) ? workspacePython : (process.platform === "win32" ? "python" : "python3"));
const runId = new Date().toISOString().replaceAll(":", "-").replace(".", "-");
const runRoot = path.join(repositoryRoot, ".demo-state", runId);
const host = "127.0.0.1";
const processes = [];

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, host, () => {
      const address = server.address();
      if (!address || typeof address === "string") return reject(new Error("Could not allocate a TCP port."));
      const port = address.port;
      server.close(() => resolve(port));
    });
  });
}

function saveJson(file, value) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function createIdentity(dataRoot, nodeId) {
  const { privateKey, publicKey } = generateKeyPairSync("ec", {
    namedCurve: "secp256k1",
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
    publicKeyEncoding: { type: "spki", format: "pem" }
  });
  saveJson(path.join(dataRoot, ".identity", nodeId, "signer.json"), {
    format_version: 2,
    data: { private_key_pem: privateKey }
  });
  const body = publicKey.replace(/-----[^-]+-----/g, "").replace(/\s/g, "");
  // python-ecdsa's VerifyingKey.to_pem() emits 76-column base64. The runtime
  // currently uses the canonical PEM string itself as the genesis map key.
  const canonicalPublicKey = `-----BEGIN PUBLIC KEY-----\n${body.match(/.{1,76}/g).join("\n")}\n-----END PUBLIC KEY-----\n`;
  return canonicalPublicKey;
}

function start(label, command, args, cwd = repositoryRoot) {
  const child = spawn(command, args, { cwd, env: process.env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
  processes.push(child);
  child.stdout.on("data", (chunk) => process.stdout.write(`[${label}] ${chunk}`));
  child.stderr.on("data", (chunk) => process.stderr.write(`[${label}] ${chunk}`));
  child.on("exit", (code, signal) => {
    if (code && !process.exitCode) {
      process.exitCode = code;
      console.error(`[${label}] exited unexpectedly (${signal ?? code}).`);
      stopAll();
    }
  });
  return child;
}

async function waitFor(url, label, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { if ((await fetch(url)).ok) return; } catch { /* process is still starting */ }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`${label} did not become ready at ${url} within ${timeoutMs} ms.`);
}

let stopping = false;
function stopAll() {
  if (stopping) return;
  stopping = true;
  for (const child of processes) {
    if (child.killed || !child.pid) continue;
    if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], { stdio: "ignore", windowsHide: true });
    else child.kill("SIGTERM");
  }
  setTimeout(() => process.exit(process.exitCode ?? 0), 500).unref();
}

process.on("SIGINT", stopAll);
process.on("SIGTERM", stopAll);

async function main() {
  mkdirSync(runRoot, { recursive: true });
  const roomId = `room-${randomUUID().replaceAll("-", "").slice(0, 20)}`;
  const signallingPort = await freePort();
  const frontendPort = await freePort();
  const apiPorts = await Promise.all([freePort(), freePort(), freePort()]);
  const peerPorts = await Promise.all([freePort(), freePort(), freePort()]);
  const uiOrigin = `http://${host}:${frontendPort}`;
  const signallingOrigin = `http://${host}:${signallingPort}`;

  const signallingConfig = path.join(runRoot, "signalling.json");
  saveJson(signallingConfig, {
    bind_host: host,
    bind_port: signallingPort,
    database_path: path.join(runRoot, "signalling.sqlite3"),
    membership_ttl_ms: 15_000,
    max_request_bytes: 1_000_000
  });

  const nodes = apiPorts.map((apiPort, index) => {
    const nodeId = randomUUID();
    const dataRoot = path.join(runRoot, `node-${index + 1}`);
    const publicKey = createIdentity(dataRoot, nodeId);
    const configPath = path.join(runRoot, `node-${index + 1}.json`);
    saveJson(configPath, {
      application: {
        bind_host: host, bind_port: apiPort, data_root: dataRoot, room_id: roomId,
        node_id: nodeId, node_name: `operator-node-${randomUUID().slice(0, 8)}`,
        advertised_host: host, advertised_port: peerPorts[index], signalling_url: signallingOrigin,
        upload_limit_bytes: 10_000_000, allowed_origins: [uiOrigin]
      },
      node: { max_event_bytes: 500_000, connect_timeout_s: 5, transition_timeout_s: 30, ...(index === 0 ? { stake_amount: 50 } : {}) },
      agent: { max_csv_rows: 50_000, max_query_rows: 5_000, max_schema_nodes: 1_000, max_schema_depth: 20 },
      signalling: { timeout_seconds: 5, refresh_interval_ms: 1_000 },
      providers: [{ kind: "manual", provider_id: "manual-operator", label: "Manual operator" }]
    });
    return { index, nodeId, publicKey, apiPort, peerPort: peerPorts[index], configPath };
  });

  saveJson(path.join(runRoot, "operator-inputs.json"), {
    room_id: roomId,
    protocol_version: "1",
    consensus_parameters: { epoch_ms: 600, max_clock_skew_ms: 60_000, finality_depth: 1, max_connections: 8, block_reward: 0, minimum_stake: 1 },
    genesis_allocations: nodes.map((node, index) => ({ public_key: node.publicKey, amount: 1_000, stake: index === 0 ? 50 : 0 })),
    application_api_origins: nodes.map((node) => `http://${host}:${node.apiPort}`)
  });

  start("signalling", python, ["-m", "signalling", "--config", signallingConfig]);
  await waitFor(`${signallingOrigin}/health`, "Signalling service");
  for (const node of nodes) start(`node-${node.index + 1}`, python, ["-m", "api", "--config", node.configPath]);
  await Promise.all(nodes.map((node) => waitFor(`http://${host}:${node.apiPort}/health`, `Node ${node.index + 1}`)));
  start("frontend", process.execPath, [path.join(frontendRoot, "node_modules", "vite", "bin", "vite.js"), "--host", host, "--port", String(frontendPort)], frontendRoot);
  await waitFor(uiOrigin, "React application");

  console.log("\nAgentGuard demo processes are ready.");
  console.log(`UI: ${uiOrigin}`);
  console.log(`Room/operator inputs: ${path.join(runRoot, "operator-inputs.json")}`);
  nodes.forEach((node) => console.log(`Node ${node.index + 1} API: http://${host}:${node.apiPort}`));
  console.log("Create the room through Node 1 in the UI, then join the same room through Nodes 2 and 3. Press Ctrl+C to stop all processes.");
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : error);
  process.exitCode = 1;
  stopAll();
});
