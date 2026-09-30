import { expect, test, type Page, type Locator } from "@playwright/test";
import { readFileSync } from "node:fs";
import { randomUUID, createHash } from "node:crypto";

const access = JSON.parse(readFileSync(process.env.AGENTGUARD_LIVE_ACCESS!, "utf8")) as {
  room_id: string; nodes: { name: string; apiOrigin: string; access_key: string }[];
};

async function choose(page: Page, field: Locator, label: string) {
  await field.click();
  await page.getByRole("option", { name: label, exact: true }).click();
}
async function navigate(page: Page, name: string) {
  const closed = page.getByRole("button", { name: "Open navigation", exact: true });
  if (await closed.isVisible()) await closed.click();
  await page.getByRole("link", { name, exact: true }).click();
}

test("real uploads, signed actions, approval, download, denial, finality and logout", async ({ page, request }, info) => {
  const first = access.nodes[0]!;
  const title = `Evidence ${randomUUID()}`;
  const content = randomUUID(); const secondContent = randomUUID();
  const firstName = `${randomUUID()}.txt`; const secondName = `${randomUUID()}.txt`;
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
  const publicConfig = await (await request.get("/runtime-config.js")).text();
  for (const node of access.nodes) expect(publicConfig).not.toContain(node.access_key);
  expect((await request.get(`${first.apiOrigin}/api/jobs`)).status()).toBe(401);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Let agents work. Keep the say." })).toBeVisible();
  await expect(page.locator(".permission-machine")).toHaveCSS("opacity", "1");
  await expect(page.locator(".hero-description")).toHaveCSS("opacity", "1");
  await page.screenshot({ path: info.outputPath("landing.png"), fullPage: true, animations: "disabled" });
  await page.goto(`/r/${access.room_id}/overview`);
  await expect(page.getByRole("heading", { name: "Welcome to your workspace." })).toBeVisible();
  await page.screenshot({ path: info.outputPath("sign-in.png"), fullPage: true });
  await page.getByLabel("Node API URL").fill(first.apiOrigin);
  await page.getByLabel("Node access key").fill(randomUUID());
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("incorrect");
  await page.getByLabel("Node access key").fill(first.access_key);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your work, in view." })).toBeVisible();
  await page.screenshot({ path: info.outputPath("live-overview.png"), fullPage: true });
  await navigate(page, "Network");
  for (const node of access.nodes.slice(1)) await expect(page.locator(".node-list").getByText(node.name, { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("network.png"), fullPage: true });
  await page.goto(`/r/${access.room_id}/ledger`);
  await page.getByRole("button", { name: "0 · Genesis" }).click();
  await expect(page.getByText(/Genesis is the network’s starting block/)).toBeVisible();
  await page.goto(`/r/${access.room_id}/jobs/new`);
  await expect(page.getByRole("heading", { name: "What would you like to do?" })).toBeVisible();
  await page.screenshot({ path: info.outputPath("prompt.png"), fullPage: true });
  await page.getByRole("button", { name: "Advanced setup" }).click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("Instructions", { exact: true }).fill(`Compute the SHA-256 of ${firstName}; preserve the signed decision and result.`);
  await page.getByLabel("Execution provider").click();
  await page.getByRole("option").nth(1).click();
  await page.getByLabel("Upload input files").setInputFiles([
    { name: firstName, mimeType: "text/plain", buffer: Buffer.from(content) },
    { name: secondName, mimeType: "text/plain", buffer: Buffer.from(secondContent) }
  ]);
  await expect(page.locator(".artifact-list li")).toHaveCount(2);
  const rule = page.locator(".policy-rule").first();
  await choose(page, rule.getByRole("combobox", { name: "Tool", exact: true }), "Hash artifact");
  await choose(page, rule.getByRole("combobox", { name: "Permission", exact: true }), "Require my approval");
  await rule.getByLabel(firstName, { exact: true }).check();
  await page.getByRole("button", { name: "Add permission" }).click();
  const secondRule = page.locator(".policy-rule").nth(1);
  await choose(page, secondRule.getByRole("combobox", { name: "Tool", exact: true }), "Write report");
  await choose(page, secondRule.getByRole("combobox", { name: "Permission", exact: true }), "Deny");
  await page.getByLabel("Maximum actions").fill("3");
  await page.getByLabel("Runtime per action (ms)").fill("5000");
  await page.getByLabel("Output per action (bytes)").fill("100000");
  await page.getByRole("button", { name: "Create job", exact: true }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  const jobId = page.url().split("/").at(-1)!;
  await page.getByRole("button", { name: "Accept on this node" }).click();
  await choose(page, page.getByLabel("Action tool"), "Hash artifact");
  await choose(page, page.getByRole("combobox", { name: "artifact id", exact: true }), firstName);
  await page.getByRole("button", { name: "Propose action" }).click();
  await expect(page.getByRole("heading", { name: "A decision is needed." })).toBeVisible();
  await page.getByRole("button", { name: "Review approval", exact: true }).click();
  await page.getByLabel("Decision note").fill(`Reviewed input ${firstName}`);
  await page.getByRole("button", { name: "Approve action" }).click();
  await expect(page.locator(".execution-rail").getByText("action.completed", { exact: true })).toBeVisible();
  const outputRow = page.locator(".download-list li").filter({ hasText: ".json" }).first();
  const downloadEvent = page.waitForEvent("download");
  await outputRow.getByRole("button").click();
  const download = await downloadEvent; const downloadedPath = await download.path();
  expect(JSON.parse(readFileSync(downloadedPath!, "utf8"))).toEqual({ sha256: createHash("sha256").update(content).digest("hex") });
  await choose(page, page.getByLabel("Action tool"), "Write report");
  await page.getByLabel("name", { exact: true }).fill(`${randomUUID()}.txt`);
  await choose(page, page.getByRole("combobox", { name: "format", exact: true }), "text");
  await page.getByLabel("content", { exact: true }).fill(randomUUID());
  await page.getByRole("button", { name: "Propose action" }).click();
  await expect(page.locator(".execution-rail").getByText("security.violation", { exact: true })).toBeVisible();
  await page.getByLabel("Completion summary").fill(`## Verification\n\nVerified the **hash** of ${firstName}.\n\n- The out-of-policy write was denied.\n- The original file was preserved.`);
  await page.getByRole("button", { name: "Complete job", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Work completed." })).toBeVisible();
  await expect(page.locator(".markdown-answer").getByRole("heading", { name: "Verification" })).toBeVisible();
  await expect(page.locator(".markdown-answer strong")).toHaveText("hash");
  await expect(page.locator(".markdown-answer li")).toHaveCount(2);
  for (const node of access.nodes) {
    const login = await request.post(`${node.apiOrigin}/api/auth/login`, { data: { access_key: node.access_key } });
    const { token } = await login.json(); const headers = { Authorization: `Bearer ${token}` };
    await expect.poll(async () => {
      const response = await request.get(`${node.apiOrigin}/api/jobs/${jobId}`, { headers });
      if (!response.ok()) return null;
      const result = await response.json(); return `${result.job.status}/${result.job.finality}`;
    }, { timeout: 30_000 }).toBe("completed/finalized");
    await request.post(`${node.apiOrigin}/api/auth/logout`, { headers });
  }
  await page.screenshot({ path: info.outputPath("live-job-completed.png"), fullPage: true });
  await navigate(page, "Security");
  await expect(page.getByText("EXPLICIT_DENY", { exact: true }).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await navigate(page, "Settings");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Welcome to your workspace." })).toBeVisible();
  expect(errors).toEqual([]);
});

test("prompt attachments are aligned, removable and have no shield logo", async ({ page }, info) => {
  await page.goto("/sign-in");
  await page.getByLabel("Node API URL").fill(access.nodes[0]!.apiOrigin);
  await page.getByLabel("Node access key").fill(access.nodes[0]!.access_key);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your work, in view." })).toBeVisible();
  await page.goto(`/r/${access.room_id}/jobs/new`);
  await expect(page.locator(".prompt-heading svg")).toHaveCount(0);
  const attach = page.getByRole("button", { name: "Attach files", exact: true });
  await expect(attach.locator("svg")).toHaveCount(1);
  const filename = `Document-${randomUUID()}.txt`;
  await page.getByLabel("Your task").fill("Read the attached document and summarize the main points.");
  await page.getByLabel("Upload input files").setInputFiles({ name: filename, mimeType: "text/plain", buffer: Buffer.from(randomUUID()) });
  await expect(page.locator(".compact-uploader .artifact-list li")).toHaveCount(1);
  const file = await page.locator(".compact-uploader .artifact-list li").boundingBox();
  const form = await page.locator(".prompt-form").boundingBox();
  expect(file!.x).toBeGreaterThanOrEqual(form!.x);
  expect(file!.x + file!.width).toBeLessThanOrEqual(form!.x + form!.width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("prompt-attachment.png"), fullPage: true });
  await page.getByRole("button", { name: `Remove ${filename}`, exact: true }).click();
  await expect(page.locator(".compact-uploader .artifact-list li")).toHaveCount(0);
  await page.goto(`/r/${access.room_id}/settings`);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
});

test("Certa controls, orbit, reduced motion and page spacing", async ({ page }, info) => {
  await page.goto("/sign-in");
  await page.getByLabel("Node API URL").fill(access.nodes[0]!.apiOrigin);
  await page.getByLabel("Node access key").fill(access.nodes[0]!.access_key);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your work, in view." })).toBeVisible();
  await expect(page.locator(".brand svg")).toHaveCount(0);
  await page.mouse.move(1, 1);
  await page.getByRole("heading", { name: "Your work, in view." }).click();
  await expect(page.getByRole("button", { name: "Open navigation" })).toHaveAttribute("aria-expanded", "false", { timeout: 6000 });
  await navigate(page, "Network");
  const orbitNode = page.locator(".orbit-node").first();
  await expect(orbitNode).toBeVisible();
  await page.mouse.move(1, 1);
  const firstPosition = await orbitNode.getAttribute("transform");
  await expect.poll(() => orbitNode.getAttribute("transform")).not.toBe(firstPosition);
  await page.getByRole("button", { name: "Pause orbit", exact: true }).click();
  const stopped = await orbitNode.getAttribute("transform");
  await page.waitForTimeout(300);
  expect(await orbitNode.getAttribute("transform")).toBe(stopped);
  await orbitNode.focus(); await page.keyboard.press("Enter");
  await expect(orbitNode).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(page.locator(".peer-graph>g")).toHaveAttribute("transform", /scale\(1\.1\)/);
  await page.getByRole("button", { name: "Reset zoom" }).click();
  await page.screenshot({ path: info.outputPath("interactive-network.png"), fullPage: true });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.getByRole("button", { name: "Resume orbit" })).toBeDisabled();
  await navigate(page, "Jobs");
  const state = page.getByRole("combobox", { name: "Job state", exact: true });
  await state.focus(); await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("listbox")).toBeVisible();
  await page.keyboard.press("End"); await expect(page.getByRole("option").last()).toBeFocused(); await page.keyboard.press("Enter");
  await expect(page.getByRole("listbox")).toHaveCount(0);
  await expect(page).toHaveURL(/state=expired/);
  await expect(state).toContainText("Expired");
  await state.focus(); await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("listbox")).toBeVisible();
  await page.keyboard.press("Home"); await expect(page.getByRole("option", { name: "All states", exact: true })).toBeFocused(); await page.keyboard.press("Enter");
  await expect(page).not.toHaveURL(/state=/);
  await expect(state).toContainText("All states");
  const filter = await page.locator(".filter-bar").boundingBox();
  const table = await page.locator(".surface").first().boundingBox();
  expect(table!.y).toBeGreaterThan(filter!.y + filter!.height);
  await page.screenshot({ path: info.outputPath("jobs-spacing.png"), fullPage: true });
  for (const path of ["overview", "jobs/new", "security", "ledger", "settings"]) {
    await page.goto(`/r/${access.room_id}/${path}`);
    await expect(page.locator(".page")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
});
