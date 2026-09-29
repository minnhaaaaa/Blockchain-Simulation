import { expect, test, type Page, type Route } from "@playwright/test";
import path from "node:path";

const apiOrigin = "http://api.agentguard.test";
const roomId = "room-browser-acceptance";
const jobId = "11111111-1111-4111-8111-111111111111";
const actionId = "22222222-2222-4222-8222-222222222222";
const artifactId = "33333333-3333-4333-8333-333333333333";
const publicKey = `-----BEGIN PUBLIC KEY-----\n${"A".repeat(88)}\n-----END PUBLIC KEY-----\n`;
const signature = "A".repeat(88);
const hash = "a".repeat(64);
const now = 1_780_000_000_000;
const screenshotRoot = path.resolve("..", "verification", "screenshots");

const job = {
  job_id: jobId, room_id: roomId, title: "Review quarterly evidence", owner_fingerprint: hash,
  worker_fingerprint: hash, provider_id: "manual-operator", status: "waiting_approval", latest_sequence: 3,
  action_count: 1, completed_action_count: 0, pending_approval_count: 1,
  created_at_ms: now, updated_at_ms: now + 1_000, finality: "included"
};

function event(eventId: string, eventType: string, sequence: number, payload: object) {
  return { schema_version: 1, event_id: eventId, event_type: eventType, room_id: roomId, job_id: jobId,
    actor_public_key: publicKey, sequence, created_at_ms: now + sequence, previous_event_hash: sequence ? hash : null,
    payload, event_hash: hash, signature };
}

const action = { schema_version: 1, action_id: actionId, job_id: jobId, action_sequence: 0, tool_id: "sha256",
  arguments: { text: "acceptance" }, input_artifact_ids: [artifactId], expected_output_kind: "text",
  proposer_public_key: publicKey, proposed_at_ms: now + 1 };
const decision = { schema_version: 1, decision_id: "44444444-4444-4444-8444-444444444444", job_id: jobId,
  action_id: actionId, decision: "approval_required", basis: "policy", decided_by_public_key: publicKey,
  reason_code: "OWNER_APPROVAL", reason: "Owner approval is required.", policy_hash: hash, decided_at_ms: now + 2 };

function response(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function mockApi(page: Page) {
  let jobs = [job];
  let pending = true;
  await page.route(`${apiOrigin}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (url.pathname === "/health") return response(route, { status: "ok" });
    if (url.pathname === "/api/room-session" && method === "POST") return response(route, {
      schema_version: 1, room_id: roomId, protocol_version: "1",
      consensus: { type: "pos", parameters: { epoch_ms: 600, max_clock_skew_ms: 60_000, finality_depth: 1, max_connections: 8, block_reward: 0, minimum_stake: 1 } },
      genesis: { block_id: "55555555-5555-4555-8555-555555555555", created_at_ms: now, allocations: [{ public_key: publicKey, amount: 1_000, stake: 50 }] },
      creator_public_key: publicKey, created_at_ms: now, signature
    });
    if (url.pathname === "/api/status") return response(route, { room_id: roomId, node_id: "66666666-6666-4666-8666-666666666666", node_name: "browser-node", node_public_key_fingerprint: hash, node_state: "online", api_state: "online", provider_state: "configured", chain_height: 4, finalized_height: 3, updated_at_ms: now });
    if (url.pathname === "/api/providers") return response(route, { items: [{ provider_id: "manual-operator", label: "Manual operator", kind: "manual", state: "ready" }] });
    if (url.pathname === "/api/tools") return response(route, { items: [{ tool_id: "sha256", label: "SHA-256", description: "Hash text", version: "1", argument_schema: { type: "object" }, output_kinds: ["text"] }] });
    if (url.pathname === "/api/peers") return response(route, { items: [{ node_id: "77777777-7777-4777-8777-777777777777", name: "peer-bravo", advertised_host: "127.0.0.1", advertised_port: 49100, public_key_fingerprint: hash, discovery_state: "discovered", connection_state: "connected", last_seen_ms: now }] });
    if (url.pathname === "/api/chain") return response(route, { height: 4, finalized_height: 3, head_hash: hash, blocks: [] });
    if (url.pathname === "/api/stakes") return response(route, { epoch_seed: hash, total_stake: 50, latest_proposer_fingerprint: hash, items: [{ staker_fingerprint: hash, amount: 50 }] });
    if (url.pathname === "/api/artifacts" && method === "POST") return response(route, { artifact_id: artifactId, name: "evidence.csv", media_type: "text/csv", size_bytes: 12, sha256: hash }, 201);
    if (url.pathname === "/api/jobs" && method === "POST") { jobs = [job]; return response(route, { submission_id: "88888888-8888-4888-8888-888888888888", event_id: "99999999-9999-4999-8999-999999999999", ledger_state: "submitted", event_hash: null }, 202); }
    if (url.pathname === "/api/jobs") return response(route, { items: jobs });
    if (url.pathname === `/api/jobs/${jobId}`) return response(route, { job: { ...job, pending_approval_count: pending ? 1 : 0, status: pending ? "waiting_approval" : "running" }, events: [
      event("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "action.proposed", 1, action),
      event("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "action.approval_required", 2, decision),
      ...(!pending ? [event("abababab-abab-4bab-8bab-abababababab", "action.approved", 3, { ...decision, decision_id: "acacacac-acac-4cac-8cac-acacacacacac", decision: "approved", basis: "human", reason_code: "OWNER_DECISION", reason: "Input and scope verified.", decided_at_ms: now + 3 })] : [])
    ] });
    if (url.pathname.endsWith(`/actions/${actionId}/decision`) && method === "POST") { pending = false; return response(route, { submission_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", event_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", ledger_state: "submitted", event_hash: null }, 202); }
    if (url.pathname === "/api/violations") return response(route, { items: [{ violation_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", job_id: jobId, action_id: actionId, category: "policy", code: "ARTIFACT_NOT_ALLOWED", message: "The action attempted to read an artifact outside its policy.", evidence_hash: hash, actor_fingerprint: hash, detected_at_ms: now, finality: "finalized" }] });
    return response(route, { code: "NOT_MOCKED", message: `${method} ${url.pathname}`, request_id: "ffffffff-ffff-4fff-8fff-ffffffffffff" }, 404);
  });
}

async function openConfigured(page: Page, pathName: string) {
  await page.addInitScript((origin) => localStorage.setItem("agentguard.api-origin", origin), apiOrigin);
  await page.goto(pathName);
}

async function useNavigation(page: Page, name: "Network" | "Security") {
  if ((page.viewportSize()?.width ?? 1200) < 960) await page.getByRole("button", { name: "Menu" }).click();
  await page.getByRole("link", { name }).click();
}

test("connects, joins, discovers peers, and refreshes without invented data", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByLabel(/Application API URL/).fill(apiOrigin);
  await page.getByRole("button", { name: "Check API" }).click();
  await expect(page.getByText("API health check passed.")).toBeVisible();
  await page.getByLabel(/Room ID/).fill(roomId);
  await page.getByRole("button", { name: "Verify manifest and join" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.screenshot({ path: path.join(screenshotRoot, "browser-test-room-overview.png"), fullPage: true });
  await useNavigation(page, "Network");
  await expect(page.getByText("peer-bravo")).toBeVisible();
  await page.screenshot({ path: path.join(screenshotRoot, "browser-test-discovered-peer.png"), fullPage: true });
  await page.reload();
  await expect(page.getByText("peer-bravo")).toBeVisible();
});

test("uploads input and serializes an operator policy through the real form", async ({ page }) => {
  await mockApi(page);
  await openConfigured(page, `/r/${roomId}/jobs/new`);
  await page.getByLabel("Title").fill("Review quarterly evidence");
  await page.getByLabel("Instructions").fill("Hash the uploaded evidence after owner review.");
  await page.getByLabel("Provider").selectOption("manual-operator");
  await page.locator('input[type="file"]').setInputFiles({ name: "evidence.csv", mimeType: "text/csv", buffer: Buffer.from("value\n42\n") });
  await expect(page.getByRole("strong").filter({ hasText: "evidence.csv" })).toBeVisible();
  await page.getByLabel("Tool").selectOption("sha256");
  await page.getByLabel("Effect").selectOption("approval_required");
  await page.getByLabel("Maximum actions").fill("2");
  await page.getByLabel("Runtime per action (ms)").fill("3000");
  await page.getByLabel("Output per action (bytes)").fill("4096");
  await page.getByRole("button", { name: "Submit job" }).click();
  await expect(page.getByText(/Submission accepted/)).toBeVisible();
  await page.screenshot({ path: path.join(screenshotRoot, "browser-test-job-submitted.png"), fullPage: true });
});

test("records an explicit approval and explains a finalized rejection", async ({ page }) => {
  await mockApi(page);
  await openConfigured(page, `/r/${roomId}/jobs/${jobId}`);
  await expect(page.locator(".current-gate").getByText("Owner approval is required.")).toBeVisible();
  await page.getByRole("button", { name: "Review approval" }).click();
  await expect(page.getByRole("heading", { name: "Review requested action" })).toBeVisible();
  await page.getByLabel("Decision note").fill("Input and scope verified.");
  await page.screenshot({ path: path.join(screenshotRoot, "browser-test-approval.png"), fullPage: true });
  await page.getByRole("button", { name: "Approve action" }).click();
  await expect(page.getByText("No action is waiting at a policy or owner gate.")).toBeVisible();
  await useNavigation(page, "Security");
  await expect(page.getByText("ARTIFACT_NOT_ALLOWED")).toBeVisible();
  await page.screenshot({ path: path.join(screenshotRoot, "browser-test-malicious-action-rejection.png"), fullPage: true });
});

test("shows API loss and recovers on retry", async ({ page }) => {
  await page.addInitScript((origin) => localStorage.setItem("agentguard.api-origin", origin), apiOrigin);
  let offline = true;
  await page.route(`${apiOrigin}/**`, async (route) => {
    if (offline) return route.abort("failed");
    return response(route, { room_id: roomId, node_id: "66666666-6666-4666-8666-666666666666", node_name: "recovered-node", node_public_key_fingerprint: hash, node_state: "online", api_state: "online", provider_state: "configured", chain_height: 0, finalized_height: 0, updated_at_ms: now });
  });
  await page.goto(`/r/${roomId}/settings`);
  await expect(page.getByRole("heading", { name: "Node unavailable" })).toBeVisible();
  offline = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.locator("#main-content dd").filter({ hasText: "recovered-node" })).toBeVisible();
});
