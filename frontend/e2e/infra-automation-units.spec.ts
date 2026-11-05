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
  const directory = resolve("docs/verification/infra-automation/16-16/screenshots");
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
    await capture(page, "inventory-unknown");
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
});
