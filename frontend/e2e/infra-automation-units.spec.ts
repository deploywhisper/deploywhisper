import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, mkdirSync, openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";

type Account = { username: string; password: string; principalId: string };
type Scope = { projectId: number; workspaceId: number; projectName: string; projectKey: string };
type Fixture = { version: number; origin: string; lane: string; accounts: Record<string, Account>; operatorPool: Account[]; projects: Record<"enabled" | "disabled", Scope> };
const fixturePath = process.env.UNIT_UI_FIXTURE;
const origin = "http://localhost:8080";
let operatorIndex = 0;
// Credential entry never produces traces, videos or automatic failure screenshots.
test.use({ trace: "off", screenshot: "off", video: "off" });

function fixture(): Fixture {
  const container = process.env.UNIT_UI_CONTAINER;
  if (!fixturePath || !container || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(container) || process.env.BASE_URL !== origin) {
    throw new Error("The protected disposable units fixture is required.");
  }
  try {
    const inspected = JSON.parse(execFileSync("docker", ["inspect", "--type", "container", container], {
      encoding: "utf8", timeout: 10_000, stdio: ["ignore", "pipe", "pipe"],
    }))[0];
    const environment = new Map<string, string>((inspected.Config.Env as string[]).map((entry) => {
      const split = entry.indexOf("="); return [entry.slice(0, split), entry.slice(split + 1)];
    }));
    const bindings = inspected.NetworkSettings.Ports?.["8080/tcp"] as { HostIp: string; HostPort: string }[] | undefined;
    if (!inspected.State.Running || inspected.Config.Labels?.["com.docker.compose.project"] !== "deploywhisper-story16-16" ||
      environment.get("UNIT_UI_DISPOSABLE") !== "1" || environment.get("AUTOMATION_UI_DISPOSABLE") !== "1" ||
      environment.get("DEPLOYWHISPER_IDENTITY_PROFILE") !== "local-development" || environment.get("DEPLOYWHISPER_IDENTITY_ORIGIN") !== origin ||
      !bindings?.some((binding) => binding.HostIp === "127.0.0.1" && binding.HostPort === "8080")) throw new Error();
  } catch {
    // Docker output may include credentials; never surface child-process details.
    throw new Error("The live disposable unit Compose target could not be verified.");
  }
  const descriptor = openSync(fixturePath, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  let value: Fixture;
  try {
    const metadata = fstatSync(descriptor);
    if (!metadata.isFile() || metadata.nlink !== 1 || (metadata.mode & 0o777) !== 0o600 || metadata.uid !== process.getuid?.() || metadata.size < 1 || metadata.size > 65_536) {
      throw new Error("Unit fixture must be a bounded private regular file.");
    }
    value = JSON.parse(readFileSync(descriptor, "utf8")) as Fixture;
  } finally { closeSync(descriptor); }
  if (value.version !== 1 || value.origin !== origin || value.lane !== "uploaded-unit-preflight") throw new Error("Unsupported unit fixture.");
  const operator = value.operatorPool[operatorIndex++];
  if (!operator) throw new Error("Synthetic operator pool exhausted.");
  value.accounts.operator = operator;
  return value;
}

const route = (scope: Scope, path = "/infra-automation/inventory") => `${path}?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`;
// Read focus state only: all focus movement is native Tab/Shift+Tab input.
// A hidden, disabled or untabbable control therefore fails this journey.
async function tabTo(page: Page, control: Locator, reverse = false) {
  await expect(control).toBeVisible();
  await expect(control).toBeEnabled();
  for (let count = 0; count < 160; count += 1) {
    if (await control.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press(reverse ? "Shift+Tab" : "Tab");
  }
  await expect(control).toBeFocused();
}
async function keyboardActivate(page: Page, control: Locator, key = "Enter") {
  await tabTo(page, control);
  await page.keyboard.press(key);
}
async function keyboardSelect(page: Page, label: string, value: string) {
  const control = page.getByRole("combobox", { name: label, exact: true });
  await expect(control.locator(`option[value="${value}"]`)).toHaveCount(1);
  await tabTo(page, control);
  const option = control.locator(`option[value="${value}"]`);
  const labelText = (await option.textContent())?.trim();
  expect(labelText).toBeTruthy();
  // Native Chromium selects on macOS accept keyboard typeahead; synthetic
  // ArrowDown opens an OS popup without selecting under headless execution.
  // Typeahead remains real keyboard input, with no DOM value/focus mutation.
  await page.keyboard.type(labelText!);
  await page.keyboard.press("Tab");
  await expect(control).toHaveValue(value);
}
async function login(page: Page, account: Account, scope: Scope): Promise<string> {
  await page.goto(`/settings/account?returnTo=${encodeURIComponent(route(scope))}`);
  const username = page.getByLabel("Username", { exact: true });
  await expect(username).toBeEnabled();
  await tabTo(page, username); await page.keyboard.insertText(account.username); await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
  await page.keyboard.insertText(account.password); await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeFocused();
  const pending = page.waitForResponse((response) => response.url().endsWith("/api/v1/auth/login") && response.request().method() === "POST");
  await page.keyboard.press("Enter");
  const response = await pending;
  expect(response.status()).toBe(200);
  const csrf = (await response.json()).data.csrf_token as string;
  await expect(page).toHaveURL(new URL(route(scope), origin).href);
  return csrf;
}

async function keyboardText(page: Page, label: string, value: string, reverse = false) {
  const control = page.getByLabel(label, { exact: true });
  await tabTo(page, control, reverse); await expect(control).toBeFocused();
  await page.keyboard.press("ControlOrMeta+A"); await page.keyboard.press("Backspace");
  if (value) await page.keyboard.insertText(value);
}
async function cleanAxe(page: Page) {
  const result = await new AxeBuilder({ page }).analyze();
  expect(result.violations.filter((item) => item.impact === "critical" || item.impact === "serious").map(({ id, nodes }) => ({ id, elements: nodes.map((node) => node.target) }))).toEqual([]);
}
async function capture(page: Page, name: string, anchor?: Locator) {
  const directory = resolve("docs/verification/infra-automation/16-16/review-screenshots");
  mkdirSync(directory, { recursive: true });
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    if (anchor) {
      // Reflow does not scroll an already focused element back into view.
      // Traverse away and back using the keyboard at each viewport width.
      await page.keyboard.press("Shift+Tab");
      await tabTo(page, anchor);
    }
    await cleanAxe(page);
    await page.screenshot({ path: resolve(directory, `${name}-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}

async function publishedWorkflow(context: BrowserContext, csrf: string, scope: Scope) {
  const headers = { Origin: origin, "X-CSRF-Token": csrf };
  const steps = [
    { id: "network-upload", kind: "uploaded_intake", depends_on: [], source: { kind: "uploaded" } },
    { id: "network-analysis", kind: "shared_analysis", depends_on: ["network-upload"], artifact: { ref: "step", step_id: "network-upload", output: "screened_artifacts" } },
    { id: "app-upload", kind: "uploaded_intake", depends_on: ["network-analysis"], source: { kind: "uploaded" } },
    { id: "app-analysis", kind: "shared_analysis", depends_on: ["app-upload"], artifact: { ref: "step", step_id: "app-upload", output: "screened_artifacts" } },
  ];
  const created = await context.request.post("/api/v1/infra-automation/workflows", { headers, data: {
    project_id: scope.projectId, workspace_id: scope.workspaceId, name: `Declared unit browser proof ${Date.now()}`,
    definition: JSON.stringify({ workflow_version: 2, project_id: String(scope.projectId), workspace_id: String(scope.workspaceId), environment: "test", inputs: {}, steps }),
    reason: "Synthetic declared unit browser setup",
  } });
  expect(created.status()).toBe(200);
  const workflow = (await created.json()).data as { id: string; draft_version: number };
  const published = await context.request.post(`/api/v1/infra-automation/workflows/${workflow.id}/revisions`, { headers, data: {
    expected_version: workflow.draft_version, idempotency_key: `units-publish-${Date.now()}`, reason: "Publish exact declared collection order",
  } });
  expect(published.status()).toBe(200);
  return { workflow, revision: (await published.json()).data as { id: string } };
}

async function validate(page: Page) {
  const pending = page.waitForResponse((response) => response.url().endsWith("/units/validate") && response.request().method() === "POST");
  await keyboardActivate(page, page.getByRole("button", { name: "Validate inventory", exact: true }));
  const response = await pending;
  expect(response.status()).toBe(200);
  return (await response.json()).data;
}


function declaredMap(path = ".") {
  return { version: 1, affected: ["app"], units: [
    { id: "network", source: { kind: "uploaded", path }, environment: "test", target: "synthetic-network", prerequisites: [] as string[] },
    { id: "app", source: { kind: "uploaded", path }, environment: "test", target: "synthetic-app", prerequisites: ["network"] },
  ] };
}
async function saveMap(context: BrowserContext, csrf: string, scope: Scope, map = declaredMap(), current?: { inventory_id: string; version: number }) {
  const response = await context.request.post("/api/v1/infra-automation/units", { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: {
    project_id: scope.projectId, workspace_id: scope.workspaceId, inventory_id: current?.inventory_id ?? null,
    expected_version: current?.version ?? 0, reason: "Synthetic review recovery declaration", map,
  } });
  expect(response.status()).toBe(200); return (await response.json()).data;
}
async function openSaved(page: Page, saved: { inventory_id: string; version: number }) {
  await keyboardActivate(page, page.getByRole("button", { name: "Refresh inventories", exact: true }));
  await keyboardActivate(page, page.getByRole("button", { name: `Open inventory ${saved.inventory_id} · revision ${saved.version}`, exact: true }));
  await expect(page.getByRole("heading", { name: `Run saved revision ${saved.version}`, exact: true })).toBeVisible();
}
async function fillRunBindings(page: Page) {
  for (const unit of ["network", "app"]) {
    await keyboardText(page, `${unit} intake step`, `${unit}-upload`);
    await keyboardText(page, `${unit} analysis step`, `${unit}-analysis`);
    const input = page.getByLabel(`${unit} artifacts`, { exact: true }); await tabTo(page, input);
    await input.setInputFiles({ name: "main.tf", mimeType: "text/plain", buffer: Buffer.from(`resource "aws_s3_bucket" "${unit}" { bucket = "synthetic-review-${unit}" }\n`) });
  }
  await keyboardText(page, "Run reason", "Exercise exact review recovery");
  await keyboardActivate(page, page.getByLabel("I confirm this saved revision and collection/review order", { exact: true }), "Space");
}
async function loseNextCommittedResponse(page: Page, pathname: string) {
  await page.evaluate((path) => {
    const original = window.fetch.bind(window);
    window.fetch = async (input, options) => {
      const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
      const method = options?.method ?? (input instanceof Request ? input.method : "GET");
      const response = await original(input, options);
      if (url.pathname === path && method === "POST" && response.ok) {
        // Fully receive the real server result before discarding it. This avoids
        // leaving an unread browser stream while preserving client uncertainty.
        await response.clone().arrayBuffer();
        window.fetch = original;
        throw new TypeError("Synthetic lost committed response");
      }
      return response;
    };
  }, pathname);
}

test.describe("declared units using real composed APIs", () => {
  test.skip(!fixturePath, "Requires the disposable unit Compose lane and protected fixture.");
  test.beforeEach(async ({ page }) => { page.setDefaultTimeout(15_000); });

  test("keyboard exact scope, located errors, confirmation and two-unit evidence", async ({ page, context }) => {
    const { accounts, projects } = fixture();
    const scope = projects.enabled;
    const csrf = await login(page, accounts.operator, scope);
    const { workflow, revision } = await publishedWorkflow(context, csrf, scope);
    // Stay in the signed-in SPA: a full reload intentionally loses in-memory CSRF.
    await keyboardText(page, "Unit 1 ID", "network");
    await keyboardSelect(page, "Unit 1 source kind", "uploaded");
    await keyboardText(page, "Unit 1 path", ".");
    await keyboardText(page, "Unit 1 environment", "test");
    await keyboardText(page, "Unit 1 target", "synthetic-network");
    const networkAffected = page.getByLabel("Unit 1 affected", { exact: true });
    if (await networkAffected.isChecked()) await keyboardActivate(page, networkAffected, "Space");
    await keyboardActivate(page, page.getByRole("button", { name: "Add unit", exact: true }));
    await keyboardText(page, "Unit 2 ID", "app");
    await keyboardSelect(page, "Unit 2 source kind", "uploaded");
    await keyboardText(page, "Unit 2 path", ".");
    await keyboardText(page, "Unit 2 environment", "test");
    await keyboardText(page, "Unit 2 target", "synthetic-app");
    const appAffected = page.getByLabel("Unit 2 affected", { exact: true });
    if (!await appAffected.isChecked()) await keyboardActivate(page, appAffected, "Space");
    await keyboardText(page, "Unit 2 prerequisites", "missing");
    expect((await validate(page)).valid).toBe(false);
    await expect(page.getByRole("alert").first()).toBeFocused();
    const invalidPrerequisite = page.getByLabel("Unit 2 prerequisites", { exact: true });
    await expect(invalidPrerequisite).toHaveAttribute("aria-invalid", "true");
    await expect(invalidPrerequisite).toHaveAttribute("aria-describedby", "unit-1-prerequisites-errors");
    await expect(page.getByLabel("Unit 2 ID", { exact: true })).not.toHaveAttribute("aria-invalid", "true");
    await keyboardActivate(page, page.getByRole("link", { name: /^units\.1\.prerequisites\.0:/ }));
    await expect(invalidPrerequisite).toBeFocused();
    await capture(page, "inventory-unknown", invalidPrerequisite);
    await keyboardText(page, "Unit 2 prerequisites", "network");
    await keyboardText(page, "Unit 1 prerequisites", "app", true);
    expect((await validate(page)).valid).toBe(false);
    await expect(page.getByRole("alert").first()).toBeFocused();
    await keyboardText(page, "Unit 1 prerequisites", "");
    const validated = await validate(page);
    expect(validated.valid).toBe(true);
    expect(validated.plan.waves).toEqual([["network"], ["app"]]);
    await capture(page, "inventory-editor");
    const scopeConfirmation = page.getByLabel("I confirm this exact affected and prerequisite scope", { exact: true });
    await tabTo(page, scopeConfirmation);
    await capture(page, "inventory-confirmation", scopeConfirmation);
    await page.keyboard.press("Space");
    await keyboardText(page, "Revision reason", "Confirm the affected app and prerequisite network");
    const savedResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/infra-automation/units" && response.request().method() === "POST");
    await keyboardActivate(page, page.getByRole("button", { name: "Save revision", exact: true }));
    const saved = await savedResponse; expect(saved.status()).toBe(200);
    const savedRevision = (await saved.json()).data;
    expect(savedRevision.map_digest).toBe(validated.plan.map_digest);
    await keyboardSelect(page, "Workflow", workflow.id);
    await keyboardSelect(page, "Workflow revision", revision.id);
    for (const unit of ["network", "app"]) {
      await keyboardText(page, `${unit} intake step`, `${unit}-upload`);
      await keyboardText(page, `${unit} analysis step`, `${unit}-analysis`);
      const upload = page.getByLabel(`${unit} artifacts`, { exact: true });
      await tabTo(page, upload);
      // Native OS picker content is fixture injection; its input must be Tab reachable.
      await upload.setInputFiles({
        name: "main.tf", mimeType: "text/plain", buffer: Buffer.from(`resource "aws_s3_bucket" "${unit}" { bucket = "synthetic-unit-${unit}" }\n`),
      });
    }
    await keyboardText(page, "Run reason", "Review combined uploaded unit evidence");
    await keyboardActivate(page, page.getByLabel("I confirm this saved revision and collection/review order", { exact: true }), "Space");
    const admittedResponse = page.waitForResponse((response) => response.url().endsWith("/units/runs") && response.request().method() === "POST");
    await keyboardActivate(page, page.getByRole("button", { name: "Start preflight run", exact: true }));
    const admitted = await admittedResponse; expect(admitted.status()).toBe(200);
    const run = (await admitted.json()).data;
    await expect(page).toHaveURL(new RegExp(`/infra-automation/runs/${run.id}`));
    const unitsUrl = `/api/v1/infra-automation/runs/${run.id}/units?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`;
    await expect.poll(async () => {
      const response = await context.request.get(unitsUrl);
      if (response.status() !== 200) return "unavailable";
      return (await response.json()).data.evidence?.status;
    }, { timeout: 180_000, intervals: [1000, 2000, 4000] }).toBe("available");
    const evidence = (await (await context.request.get(unitsUrl)).json()).data;
    expect(evidence.snapshot.revision.plan.waves).toEqual([["network"], ["app"]]);
    expect(evidence.snapshot.revision.map_digest).toBe(validated.plan.map_digest);
    expect(evidence.evidence.items).toHaveLength(2);
    expect(evidence.evidence.combined_digest).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(evidence.locks.map((lock: { status: string }) => lock.status)).toEqual(["not_requested", "not_requested"]);
    await page.reload();
    await expect(page.getByText(evidence.evidence.combined_digest, { exact: true })).toBeVisible();
    await expect(page.getByText(/collection.*review order/i).first()).toBeVisible();
    await tabTo(page, page.getByRole("link", { name: `Report ${evidence.evidence.items[0].report_id}`, exact: true }));
    await capture(page, "run-unit-evidence", page.getByRole("link", { name: `Report ${evidence.evidence.items[0].report_id}`, exact: true }));
    const reports = await context.request.get(`/api/v1/infra-automation/runs/${run.id}/reports`);
    expect(reports.status()).toBe(200);
    const links = (await reports.json()).data.items;
    expect(links).toHaveLength(2);
    expect(links.every((link: { provenance: { kind: string } }) => link.provenance.kind === "uploaded")).toBe(true);
    const briefing = page.getByRole("link", { name: /briefing/i }).first();
    await keyboardActivate(page, briefing);
    await expect(page).toHaveURL(/\/reports\/[0-9]+/);
    await cleanAxe(page);
    const overview = page.getByRole("tab", { name: /^Overview/i });
    await tabTo(page, overview);
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: /^Findings/i })).toBeFocused();
    await page.keyboard.press("Home");
    await expect(overview).toBeFocused();
    await keyboardActivate(page, page.getByRole("link", { name: /back to run/i }), "Enter");
    await expect(page).toHaveURL(new RegExp(`/infra-automation/runs/${run.id}`));
    // A new declaration invalidates eligibility without changing the run version.
    // Keep this page mounted to prove live evidence polling, not reload behavior.
    const changedMap = structuredClone(savedRevision.plan.inventory);
    changedMap.units.find((unit: { id: string }) => unit.id === "app").source.path = "changed";
    const superseded = await context.request.post("/api/v1/infra-automation/units", {
      headers: { Origin: origin, "X-CSRF-Token": csrf },
      data: { project_id: scope.projectId, workspace_id: scope.workspaceId, inventory_id: savedRevision.inventory_id,
        expected_version: savedRevision.version, reason: "Declare changed downstream evidence scope", map: changedMap },
    });
    expect(superseded.status()).toBe(200);
    await expect(page.getByText("Review required again. Recollect, reanalyze and obtain a new approval.", { exact: true })).toBeVisible({ timeout: 30_000 });
    const changedEvidence = (await (await context.request.get(unitsUrl)).json()).data;
    expect(changedEvidence.run_version).toBe(evidence.run_version);
    expect(changedEvidence.evidence.status).toBe("changed");
    await tabTo(page, page.getByRole("link", { name: `Report ${evidence.evidence.items[0].report_id}`, exact: true }));
    await capture(page, "run-review-required", page.getByRole("link", { name: `Report ${evidence.evidence.items[0].report_id}`, exact: true }));
  });
  test("lost committed start replays one original run after inventory supersession", async ({ page, context }) => {
    const { accounts, projects } = fixture(), scope = projects.enabled;
    const csrf = await login(page, accounts.operator, scope);
    const { workflow, revision } = await publishedWorkflow(context, csrf, scope);
    const saved = await saveMap(context, csrf, scope);
    await openSaved(page, saved);
    await keyboardSelect(page, "Workflow", workflow.id);
    await keyboardSelect(page, "Workflow revision", revision.id);
    await fillRunBindings(page);
    await loseNextCommittedResponse(page, "/api/v1/infra-automation/units/runs");
    const responsePromise = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith("/units/runs") && r.request().method() === "POST");
    await keyboardActivate(page, page.getByRole("button", { name: "Start preflight run", exact: true }));
    const admitted = await responsePromise; expect(admitted.status()).toBe(200);
    const originalPayload = admitted.request().postDataJSON();
    await expect(page.getByRole("button", { name: "Retry original run request", exact: true })).toBeEnabled();
    const durableRuns = await context.request.get(`/api/v1/infra-automation/runs?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}&limit=100`);
    expect(durableRuns.status()).toBe(200);
    const admittedRuns = (await durableRuns.json()).data.items.filter((item: { workflow_id: string }) => item.workflow_id === workflow.id);
    expect(admittedRuns).toHaveLength(1); const run = admittedRuns[0];
    await saveMap(context, csrf, scope, declaredMap("superseded"), saved);
    // Explicit gateway/client fault model: one rejected retry never reaches the
    // server. It cannot establish that the earlier successful request did not commit.
    await page.evaluate(() => {
      const original = window.fetch.bind(window);
      const state = window as unknown as { retryFaultCount: number; rejectedRetryBody: unknown };
      state.retryFaultCount = 0;
      window.fetch = async (input, options) => {
        const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
        const method = options?.method ?? (input instanceof Request ? input.method : "GET");
        if (url.pathname === "/api/v1/infra-automation/units/runs" && method === "POST") {
          window.fetch = original; state.retryFaultCount += 1;
          state.rejectedRetryBody = JSON.parse(String(options?.body));
          return new Response(JSON.stringify({ error: { code: "quota_exceeded", message: "Synthetic gateway rejection", details: { retryable: true } } }), { status: 429, headers: { "Content-Type": "application/json" } });
        }
        return original(input, options);
      };
    });
    await keyboardActivate(page, page.getByRole("button", { name: "Retry original run request", exact: true }));
    await expect.poll(() => page.evaluate(() => (window as unknown as { retryFaultCount: number }).retryFaultCount)).toBe(1);
    expect(await page.evaluate(() => (window as unknown as { rejectedRetryBody: unknown }).rejectedRetryBody)).toEqual(originalPayload);
    await expect(page.getByRole("button", { name: "Retry original run request", exact: true })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Start preflight run", exact: true })).toBeDisabled();
    await expect(page.getByRole("combobox", { name: "Workflow", exact: true })).toBeDisabled();
    await expect(page.getByLabel("app artifacts", { exact: true })).toBeDisabled();
    await capture(page, "review-retry-rate-rejected", page.getByRole("button", { name: "Retry original run request", exact: true }));
    const retryResponse = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith("/units/runs") && r.request().method() === "POST");
    await keyboardActivate(page, page.getByRole("button", { name: "Retry original run request", exact: true }));
    const replayed = await retryResponse; expect(replayed.status()).toBe(200);
    expect(replayed.request().postDataJSON()).toEqual(originalPayload);
    expect((await replayed.json()).data.id).toBe(run.id);
    await expect(page).toHaveURL(new RegExp(`/infra-automation/runs/${run.id}`));
    const response = await context.request.get(`/api/v1/infra-automation/runs?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}&limit=100`);
    expect(response.status()).toBe(200);
    expect((await response.json()).data.items.filter((item: { workflow_id: string }) => item.workflow_id === workflow.id).map((item: { id: string }) => item.id)).toEqual([run.id]);
    await expect(page.getByText("Review required again. Recollect, reanalyze and obtain a new approval.", { exact: true })).toBeVisible();
    await capture(page, "review-replayed-superseded-run", page.getByRole("button", { name: "Refresh unit evidence", exact: true }));
  });

  test("lost save can adopt exact historical revision after a newer save", async ({ page, context }) => {
    const { accounts, projects } = fixture(), scope = projects.enabled;
    const csrf = await login(page, accounts.operator, scope);
    const first = await saveMap(context, csrf, scope);
    await openSaved(page, first);
    await keyboardText(page, "Unit 1 path", "version-two");
    expect((await validate(page)).valid).toBe(true);
    await keyboardActivate(page, page.getByLabel("I confirm this exact affected and prerequisite scope", { exact: true }), "Space");
    await keyboardText(page, "Revision reason", "Save exact second revision before response loss");
    await loseNextCommittedResponse(page, "/api/v1/infra-automation/units");
    const secondResponse = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v1/infra-automation/units" && r.request().method() === "POST");
    await keyboardActivate(page, page.getByRole("button", { name: "Save revision", exact: true }));
    const second = await secondResponse; expect(second.status()).toBe(200);
    await expect(page.getByText("An earlier save remains unresolved. Inspect refreshed inventory history; this page will not repeat it.", { exact: true })).toBeVisible();
    const durableHistory = await context.request.get(`/api/v1/infra-automation/units/${first.inventory_id}/revisions?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`);
    expect(durableHistory.status()).toBe(200);
    const committed = (await durableHistory.json()).data.items.find((item: { version: number }) => item.version === 2);
    expect(committed).toBeTruthy();
    const third = await saveMap(context, csrf, scope, declaredMap("version-three"), committed);
    expect(third.version).toBe(3);
    let saveRequests = 0;
    const countSave = (request: import("@playwright/test").Request) => { if (new URL(request.url()).pathname === "/api/v1/infra-automation/units" && request.method() === "POST") saveRequests += 1; };
    page.on("request", countSave);
    await keyboardActivate(page, page.getByRole("button", { name: "Refresh inventories", exact: true }));
    await keyboardActivate(page, page.getByRole("button", { name: `Read revision history for ${first.inventory_id}`, exact: true }));
    await keyboardActivate(page, page.getByRole("button", { name: "Open historical revision 2", exact: true }));
    await expect(page.getByRole("button", { name: "Use this verified revision", exact: true })).toBeEnabled();
    await capture(page, "review-historical-save-adoption", page.getByRole("button", { name: "Use this verified revision", exact: true }));
    await keyboardActivate(page, page.getByRole("button", { name: "Use this verified revision", exact: true }));
    await expect(page.getByLabel("Unit 1 path", { exact: true })).toBeEnabled();
    await expect(page.getByLabel("Unit 1 path", { exact: true })).toHaveValue("version-two");
    expect(saveRequests).toBe(0); page.off("request", countSave);
  });

  test("all pagination controls freeze during pending artifact reads", async ({ page, context }) => {
    test.setTimeout(300_000);
    const { accounts, projects } = fixture(), scope = projects.enabled;
    const csrf = await login(page, accounts.operator, scope);
    // Default100workflow/revision quotas and25-item pages support three pages.
    // Every option below is a real authorized API-created immutable workflow.
    const created = new Map<string, Awaited<ReturnType<typeof publishedWorkflow>>>();
    for (let count = 0; count < 51; count += 1) {
      const value = await publishedWorkflow(context, csrf, scope); created.set(value.workflow.id, value);
    }
    const saved = await saveMap(context, csrf, scope);
    await openSaved(page, saved);
    const workflowPage = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith("/workflows") && new URL(r.url()).searchParams.has("cursor"));
    await keyboardActivate(page, page.getByRole("button", { name: "Next workflow page", exact: true }));
    const middle = (await (await workflowPage).json()).data.items.find((item: { id: string }) => created.has(item.id));
    expect(middle).toBeTruthy(); const selected = created.get(middle.id)!;
    let expectedVersion = selected.workflow.draft_version + 1;
    for (let index = 0; index < 50; index += 1) {
      const published = await context.request.post(`/api/v1/infra-automation/workflows/${middle.id}/revisions`, { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: {
        expected_version: expectedVersion++, idempotency_key: `review-pagination-${index}-${Date.now()}`, reason: "Synthetic revision pagination proof",
      } }); expect(published.status()).toBe(200);
    }
    await keyboardSelect(page, "Workflow", middle.id);
    const revisionPage = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith(`/workflows/${middle.id}/revisions`) && new URL(r.url()).searchParams.has("cursor"));
    await keyboardActivate(page, page.getByRole("button", { name: "Next revision page", exact: true }));
    const middleRevision = (await (await revisionPage).json()).data.items[0];
    await keyboardSelect(page, "Workflow revision", middleRevision.id);
    await fillRunBindings(page);
    await page.evaluate(() => {
      const state = window as unknown as { unitReadCount: number; releaseUnitReads: () => void };
      state.unitReadCount = 0; const original = File.prototype.text;
      let release: () => void; const waiting = new Promise<void>((resolve) => { release = resolve; });
      state.releaseUnitReads = () => { File.prototype.text = original; release(); };
      File.prototype.text = async function () { state.unitReadCount += 1; await waiting; return original.call(this); };
    });
    await keyboardActivate(page, page.getByRole("button", { name: "Start preflight run", exact: true }));
    await expect.poll(() => page.evaluate(() => (window as unknown as { unitReadCount: number }).unitReadCount)).toBe(2);
    for (const name of ["First workflow page", "Next workflow page", "First revision page", "Next revision page"]) await expect(page.getByRole("button", { name, exact: true })).toBeDisabled();
    await capture(page, "review-pending-pagination");
    const admittedResponse = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith("/units/runs") && r.request().method() === "POST");
    await page.evaluate(() => (window as unknown as { releaseUnitReads: () => void }).releaseUnitReads());
    const admitted = await admittedResponse; expect(admitted.status()).toBe(200);
    expect(admitted.request().postDataJSON().run).toMatchObject({ workflow_id: middle.id, revision_id: middleRevision.id });
    await expect(page).toHaveURL(new RegExp(`/infra-automation/runs/${(await admitted.json()).data.id}`));
  });

});
