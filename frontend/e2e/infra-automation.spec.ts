import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, mkdirSync, openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type BrowserContext } from "@playwright/test";

type Account = { username: string; password: string; principalId: string };
type Scope = { projectId: number; workspaceId: number; projectName: string; projectKey: string };
type Fixture = { accounts: Record<"operator" | "viewer" | "unassigned" | "revoked" | "expired", Account>; operatorPool: Account[]; projects: Record<"enabled" | "disabled", Scope> };
const fixturePath = process.env.AUTOMATION_UI_FIXTURE;
let nextOperator = 0;
test.use({ trace: "off", screenshot: "off", video: "off" });
function verifyDisposableTarget(): void {
  try {
    const container = process.env.AUTOMATION_UI_CONTAINER;
    if (!container || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(container) || process.env.BASE_URL !== "http://localhost:8080") throw new Error();
    const inspected = JSON.parse(execFileSync("docker", ["inspect", "--type", "container", container], {
      encoding: "utf8", timeout: 10_000, stdio: ["ignore", "pipe", "pipe"],
    }))[0];
    const environment = new Map<string, string>((inspected.Config.Env as string[]).map((entry) => {
      const separator = entry.indexOf("=");
      return [entry.slice(0, separator), entry.slice(separator + 1)];
    }));
    const bindings = inspected.NetworkSettings.Ports?.["8080/tcp"] as { HostIp: string; HostPort: string }[] | undefined;
    if (!inspected.State.Running || inspected.Config.Labels?.["com.docker.compose.project"] !== "deploywhisper-story16-7" ||
      environment.get("AUTOMATION_UI_DISPOSABLE") !== "1" ||
      environment.get("DEPLOYWHISPER_IDENTITY_PROFILE") !== "local-development" ||
      environment.get("DEPLOYWHISPER_IDENTITY_ORIGIN") !== "http://localhost:8080" ||
      !bindings?.some((binding) => binding.HostPort === "8080" && ["", "0.0.0.0", "127.0.0.1", "::", "::1"].includes(binding.HostIp))) throw new Error();
  } catch {
    // Docker inspection may include secret environment values. Never propagate
    // its output, parse failures or child-process errors into test artifacts.
    throw new Error("The live disposable Compose qualification target could not be verified.");
  }
}
function fixture(): Fixture {
  if (!fixturePath) throw new Error("Disposable automation fixture is required.");
  verifyDisposableTarget();
  const descriptor = openSync(fixturePath, constants.O_RDONLY | constants.O_NOFOLLOW);
  let value: Fixture;
  try {
    const metadata = fstatSync(descriptor);
    if (!metadata.isFile() || (metadata.mode & 0o777) !== 0o600 || metadata.uid !== process.getuid?.() || metadata.size < 1 || metadata.size > 65_536) {
      throw new Error("Fixture must be a bounded operator-owned regular file with mode 0600.");
    }
    value = JSON.parse(readFileSync(descriptor, "utf8")) as Fixture;
  } finally {
    closeSync(descriptor);
  }
  const operator = value.operatorPool[nextOperator++];
  if (!operator) throw new Error("Synthetic operator pool exhausted; reseed the disposable qualification lane.");
  value.accounts.operator = operator;
  return value;
}
const route = (scope: Scope, path = "/infra-automation") => `${path}?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`;
const origin = () => new URL(process.env.BASE_URL ?? "http://localhost:8080").origin;

// Passwords, cookies and CSRF values remain in test process memory. In particular,
// never attach API bodies, storageState or traces to this credential-entry lane.
async function login(page: Page, account: Account, returnTo: string): Promise<string> {
  await page.goto(`/settings/account?returnTo=${encodeURIComponent(returnTo)}`);
  const username = page.getByLabel("Username", { exact: true });
  await expect(username).toBeEnabled();
  await username.focus();
  await page.keyboard.insertText(account.username);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
  await page.keyboard.insertText(account.password);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeFocused();
  const response = page.waitForResponse((item) => item.url().endsWith("/api/v1/auth/login") && item.request().method() === "POST", { timeout: 15_000 });
  await page.keyboard.press("Enter");
  expect((await response).status()).toBe(200);
  const csrf = (await (await response).json()).data.csrf_token as string;
  await expect(page).toHaveURL(new URL(returnTo, origin()).href);
  return csrf;
}

async function cleanAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((item) => item.impact === "critical" || item.impact === "serious").map(({ id, nodes }) => ({ id, elements: nodes.map((node) => node.target) }))).toEqual([]);
}

async function screenshot(page: Page, name: string) {
  const directory = resolve("docs/verification/infra-automation/16-7/screenshots");
  mkdirSync(directory, { recursive: true });
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.screenshot({ path: resolve(directory, `${name}-${width}.png`), fullPage: true });
  }
}

function definition(scope: Scope) {
  return JSON.stringify({ workflow_version: 2, project_id: String(scope.projectId), workspace_id: String(scope.workspaceId), environment: "test", inputs: {}, steps: [
    { id: "upload", kind: "uploaded_intake", depends_on: [], source: { kind: "uploaded" } },
    { id: "analysis", kind: "shared_analysis", depends_on: ["upload"], artifact: { ref: "step", step_id: "upload", output: "screened_artifacts" } },
  ] });
}

async function createWorkflow(context: BrowserContext, csrf: string, scope: Scope, name: string) {
  const response = await context.request.post("/api/v1/infra-automation/workflows", { headers: { Origin: origin(), "X-CSRF-Token": csrf }, data: {
    project_id: scope.projectId, workspace_id: scope.workspaceId, name, definition: definition(scope), reason: "Synthetic browser proof",
  } });
  expect(response.status()).toBe(200);
  return (await response.json()).data as { id: string; draft_version: number; definition: string };
}

test.describe("isolated authenticated infrastructure automation", () => {
  test.beforeEach(async ({ page }) => { page.setDefaultTimeout(15_000); });
  test.skip(!fixturePath, "Requires the separate identity-enabled disposable Compose lane and protected fixture file.");

  test("keyboard login, template validation, draft publication, uploaded run and permanent briefing", async ({ page, context }) => {
    const { accounts, projects } = fixture();
    const scope = projects.enabled;
    await login(page, accounts.operator, route(scope));
    await cleanAxe(page);
    await expect(page.getByRole("button", { name: "Create workflow", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Create workflow", exact: true }).press("Enter");
    await page.getByLabel("Workflow name", { exact: true }).fill(`Browser uploaded preflight ${Date.now()}`);
    await page.getByLabel("Workflow name", { exact: true }).focus();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Use upload template", exact: true })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Workflow YAML", { exact: true })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Reason", { exact: true })).toBeFocused();
    await expect(page.getByRole("button", { name: "Validate", exact: true })).toBeEnabled();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Validate", exact: true })).toBeFocused();
    await expect(page.getByRole("button", { name: "Use upload template", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Use upload template", exact: true }).press("Enter");
    await page.getByLabel("Reason", { exact: true }).fill("Review synthetic uploaded configuration");
    await expect(page.getByRole("button", { name: "Validate", exact: true })).toBeEnabled();
    const validated = page.waitForResponse((response) => /\/workflows(?:\/[^/]+)?\/validate$/.test(new URL(response.url()).pathname), { timeout: 15_000 });
    await page.getByRole("button", { name: /validate/i, exact: true }).press("Enter");
    expect((await validated).status()).toBe(200);
    expect((await (await validated).json()).data.valid).toBe(true);
    await cleanAxe(page);
    await expect(page.getByRole("button", { name: "Save draft", exact: true })).toBeEnabled();
    const created = page.waitForResponse((response) => response.url().endsWith("/api/v1/infra-automation/workflows") && response.request().method() === "POST", { timeout: 15_000 });
    await page.getByRole("button", { name: /save draft/i }).press("Enter");
    expect((await created).status()).toBe(200);
    const workflow = (await (await created).json()).data;
    await expect(page).toHaveURL(new RegExp(`/infra-automation/workflows/${workflow.id}`));
    await expect(page.getByRole("heading", { name: workflow.name, level: 2, exact: true })).toBeFocused();
    await page.getByLabel("Reason", { exact: true }).fill("Publish the reviewed synthetic upload workflow");
    await expect(page.getByRole("button", { name: "Publish revision", exact: true })).toBeEnabled();
    const published = page.waitForResponse((response) => response.url().endsWith(`/workflows/${workflow.id}/revisions`) && response.request().method() === "POST", { timeout: 15_000 });
    await page.getByRole("button", { name: /publish/i }).press("Enter");
    expect((await published).status()).toBe(200);
    const revision = (await (await published).json()).data;
    await expect(page.getByLabel("Published revision", { exact: true })).toHaveValue(revision.id);
    await screenshot(page, "workflow");
    await expect(page.getByLabel("Uploaded artifacts", { exact: true })).toBeEnabled();
    await page.getByLabel("Uploaded artifacts", { exact: true }).setInputFiles({ name: "main.tf", mimeType: "text/plain", buffer: Buffer.from('resource "aws_s3_bucket" "synthetic" { bucket = "ui-proof-local" }\n') });
    await page.getByLabel("Run reason", { exact: true }).fill("Review synthetic uploaded evidence");
    await expect(page.getByRole("button", { name: "Start preflight", exact: true })).toBeEnabled();
    await page.getByLabel("Uploaded artifacts", { exact: true }).focus();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Run inputs (JSON)", { exact: true })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Run reason", { exact: true })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Start preflight", exact: true })).toBeFocused();
    await expect(page.getByRole("button", { name: "Start preflight", exact: true })).toBeEnabled();
    const admitted = page.waitForResponse((response) => response.url().endsWith("/infra-automation/preflights") && response.request().method() === "POST", { timeout: 15_000 });
    await page.getByRole("button", { name: /start.*preflight|run.*preflight/i }).press("Enter");
    expect((await admitted).status()).toBe(200);
    const run = (await (await admitted).json()).data;
    expect(run.revision_id).toBe(revision.id);
    await expect(page).toHaveURL(new RegExp(`/infra-automation/runs/${run.id}`));
    await expect(page.getByRole("heading", { name: "Preflight run", level: 2, exact: true })).toBeFocused();
    const firstLogsButton = page.getByRole("button", { name: /^View screened logs for attempt/ }).first();
    await expect(firstLogsButton).toBeVisible();
    const logsButtonName = await firstLogsButton.innerText();
    const logsButton = page.getByRole("button", { name: logsButtonName, exact: true });
    await logsButton.focus();
    const currentRun = (await (await context.request.get(`/api/v1/infra-automation/runs/${run.id}`)).json()).data;
    if (!["succeeded", "failed", "stopped_by_gate", "rejected", "expired", "timed_out", "cancelled"].includes(currentRun.state)) {
      await page.waitForResponse((response) => new URL(response.url()).pathname === `/api/v1/infra-automation/runs/${run.id}` && response.status() === 200, { timeout: 15_000 });
      await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))));
      await expect(logsButton).toBeFocused();
    }
    await expect(page.getByRole("link", { name: /briefing/i })).toBeVisible({ timeout: 180_000 });
    await expect(page.getByText(run.snapshot_digest, { exact: true })).toBeVisible();
    await expect(page.getByText(/not eligible for approval/i).first()).toBeVisible();
    await cleanAxe(page);
    await screenshot(page, "run");
    const linksResponse = await context.request.get(`/api/v1/infra-automation/runs/${run.id}/reports`);
    expect(linksResponse.status()).toBe(200);
    const links = (await linksResponse.json()).data;
    expect(links.items).toHaveLength(1);
    expect(links.items[0].provenance.kind).toBe("uploaded");
    await page.getByRole("link", { name: /briefing/i }).press("Enter");
    await expect(page).toHaveURL(new RegExp(`/reports/${links.items[0].report_id}`));
    await expect(page.getByText(/repository.*commit.*not verified/i).first()).toBeVisible();
    const overviewTab = page.getByRole("tab", { name: /^Overview/i });
    await overviewTab.focus();
    await overviewTab.press("ArrowRight");
    const findingsTab = page.getByRole("tab", { name: /^Findings/i });
    await expect(findingsTab).toBeFocused();
    await expect(findingsTab).toHaveAttribute("aria-selected", "true");
    await expect(findingsTab).toHaveAttribute("aria-controls", "report-panel-findings");
    await expect(page.getByRole("tabpanel", { name: /^Findings/i })).toBeVisible();
    await findingsTab.press("Home");
    await expect(overviewTab).toBeFocused();
    await overviewTab.press("End");
    const auditTab = page.getByRole("tab", { name: /^Audit/i });
    await expect(auditTab).toBeFocused();
    await auditTab.press("ArrowLeft");
    await expect(page.getByRole("tab", { name: /^Rollback/i })).toBeFocused();
    await auditTab.press("Home");
    await expect(overviewTab).toBeFocused();
    await cleanAxe(page);
    await screenshot(page, "briefing");
    await page.getByRole("link", { name: /back to run/i }).press("Enter");
    await page.getByRole("link", { name: /· Account$/ }).press("Enter");
    await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Sign out", exact: true }).press("Enter");
    await expect(page.getByLabel("Username", { exact: true })).toBeVisible();
    await page.goto(route(scope, `/infra-automation/workflows/${workflow.id}`));
    await expect(page.getByRole("link", { name: /sign in|account access/i }).first()).toBeVisible();
    expect((await context.request.get(`/api/v1/infra-automation/workflows/${workflow.id}`)).status()).toBe(401);
    await expect(page.getByText(workflow.name, { exact: true })).toHaveCount(0);
  });

  test("bad login clears password and operator recovery guidance stays local", async ({ page }) => {
    const { accounts } = fixture();
    await page.goto("/settings/account");
    await page.getByLabel("Username", { exact: true }).fill(accounts.operator.username);
    await page.getByLabel("Password", { exact: true }).fill("synthetic-incorrect-password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("alert").first()).toContainText(/sign-in failed/i);
    await expect(page.getByRole("alert").filter({ hasText: /sign-in failed/i }).first()).toBeFocused();
    await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
    await expect(page.getByText(/python -m cli.identity/)).toBeVisible();
    await cleanAxe(page);
  });

  for (const unsafe of ["https://foreign.invalid/", "//foreign.invalid/", "/\\foreign.invalid", "/infra-automation?token=synthetic", "/api/v1/auth/logout"]) {
    test(`unsafe account return target is screened: ${unsafe}`, async ({ page }) => {
      const { accounts } = fixture();
      await page.goto(`/settings/account?returnTo=${encodeURIComponent(unsafe)}`);
      await page.getByLabel("Username", { exact: true }).fill(accounts.operator.username);
      await page.getByLabel("Password", { exact: true }).fill(accounts.operator.password);
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(page).toHaveURL((url) => url.origin === origin() && url.pathname === "/infra-automation" && !url.hash &&
        Array.from(url.searchParams.entries()).every(([key, value]) =>
          ["project_id", "workspace_id"].includes(key) && /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value))) &&
        ["project_id", "workspace_id"].every((key) => url.searchParams.getAll(key).length <= 1));
    });
  }

  test("read-only, unassigned and feature-off scopes enforce actual server capabilities", async ({ page, context, browser }) => {
    const { accounts, projects } = fixture();
    const csrf = await login(page, accounts.operator, route(projects.enabled));
    const workflow = await createWorkflow(context, csrf, projects.enabled, `Protected workflow ${Date.now()}`);
    const viewerContext = await browser.newContext({ baseURL: origin() });
    try {
      const viewer = await viewerContext.newPage();
      const viewerCsrf = await login(viewer, accounts.viewer, route(projects.enabled, `/infra-automation/workflows/${workflow.id}`));
      await expect(viewer.getByRole("button", { name: /publish/i })).toBeDisabled();
      const denied = await viewerContext.request.put(`/api/v1/infra-automation/workflows/${workflow.id}/draft`, { headers: { Origin: origin(), "X-CSRF-Token": viewerCsrf }, data: { expected_version: workflow.draft_version, definition: definition(projects.enabled), reason: "Denied viewer write" } });
      expect(denied.status()).toBe(403);
      await screenshot(viewer, "readonly");
    } finally { await viewerContext.close(); }
    const disabledScope = projects.disabled;
    const headers = { Origin: origin(), "X-CSRF-Token": csrf };
    const settingsResponse = await context.request.get(`/api/v1/infra-automation/settings?project_id=${disabledScope.projectId}`);
    expect(settingsResponse.status()).toBe(200);
    const policy = (await settingsResponse.json()).data;
    const enabledPolicy = await context.request.patch("/api/v1/infra-automation/settings", { headers, data: {
      project_id: disabledScope.projectId, expected_version: policy.version,
      settings: { ...policy.settings, enabled: true }, reason: "Prepare disposable feature-off history proof",
    } });
    expect(enabledPolicy.status()).toBe(200);
    const enabledVersion = (await enabledPolicy.json()).data.version;
    let historicalRun: { id: string };
    let preflightPayload: Record<string, unknown>;
    try {
      const historicalWorkflow = await createWorkflow(context, csrf, disabledScope, `Historical disabled workflow ${Date.now()}`);
      const published = await context.request.post(`/api/v1/infra-automation/workflows/${historicalWorkflow.id}/revisions`, { headers, data: {
        expected_version: historicalWorkflow.draft_version, idempotency_key: `disabled-publish-${Date.now()}`, reason: "Publish synthetic historical workflow",
      } });
      expect(published.status()).toBe(200);
      const revision = (await published.json()).data;
      preflightPayload = {
        run: { workflow_id: historicalWorkflow.id, revision_id: revision.id, workspace_id: disabledScope.workspaceId, inputs: {}, idempotency_key: `disabled-run-${Date.now()}`, reason: "Retain actual history after execution disable" },
        artifacts: [{ name: "known.tf", content: 'resource "aws_s3_bucket" "history" { bucket = "synthetic-disabled-history" }' }],
      };
      const admitted = await context.request.post("/api/v1/infra-automation/preflights", { headers, data: preflightPayload });
      expect(admitted.status()).toBe(200);
      historicalRun = (await admitted.json()).data;
    } finally {
      const disabledPolicy = await context.request.patch("/api/v1/infra-automation/settings", { headers, data: {
        project_id: disabledScope.projectId, expected_version: enabledVersion,
        settings: { ...policy.settings, enabled: false }, reason: "Prove readable history with execution disabled",
      } });
      expect(disabledPolicy.status()).toBe(200);
    }
    await page.locator(".dw-project-trigger").focus();
    await page.keyboard.press("Enter");
    await page.getByPlaceholder("Search projects...").fill(projects.disabled.projectName);
    await page.keyboard.press("Tab");
    await expect(page.getByRole("option", { name: new RegExp(projects.disabled.projectName) })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByText(/execution.*disabled|execution.*off/i).first()).toBeVisible();
    await expect(page.getByText(workflow.id, { exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /^Protected workflow / })).toHaveCount(0);
    const disabled = await context.request.get(`/api/v1/infra-automation/capabilities?project_id=${projects.disabled.projectId}&workspace_id=${projects.disabled.workspaceId}`);
    expect((await disabled.json()).data.execution_enabled).toBe(false);
    const selectedWorkflows = page.getByRole("link", { name: "Open selected project workflows", exact: true });
    if (await selectedWorkflows.isVisible()) await selectedWorkflows.click();
    await page.getByRole("tab", { name: "Runs", exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("link", { name: historicalRun!.id, exact: true })).toBeVisible();
    await page.getByRole("link", { name: historicalRun!.id, exact: true }).press("Enter");
    await expect(page).toHaveURL(new RegExp(`/infra-automation/runs/${historicalRun!.id}`));
    await page.getByRole("link", { name: /Run history$/ }).press("Enter");
    await expect(page.getByRole("tab", { name: "Runs", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page).toHaveURL((url) => url.searchParams.get("project_id") === String(disabledScope.projectId) && url.searchParams.get("workspace_id") === String(disabledScope.workspaceId) && url.searchParams.get("view") === "runs");
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`/infra-automation/runs/${historicalRun!.id}`));
    await expect(page.getByRole("combobox", { name: "Workspace", exact: true })).toHaveValue(String(disabledScope.workspaceId));
    await page.goForward();
    await expect(page.getByRole("tab", { name: "Runs", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("link", { name: historicalRun!.id, exact: true })).toBeVisible();
    const reports = await context.request.get(`/api/v1/infra-automation/runs/${historicalRun!.id}/reports`);
    expect(reports.status()).toBe(200);
    const runsPath = `/api/v1/infra-automation/runs?project_id=${disabledScope.projectId}&workspace_id=${disabledScope.workspaceId}&limit=100`;
    const beforeRuns = await context.request.get(runsPath);
    expect(beforeRuns.status()).toBe(200);
    const previousRunIds = (await beforeRuns.json()).data.items.map((run: { id: string }) => run.id);
    const rejectedStart = await context.request.post("/api/v1/infra-automation/preflights", { headers, data: {
      ...preflightPayload!, run: { ...(preflightPayload!.run as Record<string, unknown>), idempotency_key: `disabled-denied-${Date.now()}` },
    } });
    expect(rejectedStart.status()).toBe(403);
    const afterRuns = await context.request.get(runsPath);
    expect(afterRuns.status()).toBe(200);
    expect((await afterRuns.json()).data.items.map((run: { id: string }) => run.id)).toEqual(previousRunIds);
    await page.getByRole("combobox", { name: "Workspace", exact: true }).selectOption("project");
    await expect(page).toHaveURL((url) => url.searchParams.get("project_id") === String(disabledScope.projectId) && !url.searchParams.has("workspace_id"));
    await page.goBack();
    await expect(page.getByRole("combobox", { name: "Workspace", exact: true })).toHaveValue(String(disabledScope.workspaceId));
    await expect(page.getByRole("link", { name: historicalRun!.id, exact: true })).toBeVisible();
    await page.goForward();
    await expect(page.getByRole("combobox", { name: "Workspace", exact: true })).toHaveValue("project");
    await page.goBack();
    await page.locator(".dw-project-trigger").focus();
    await page.keyboard.press("Enter");
    await page.getByPlaceholder("Search projects...").fill(projects.enabled.projectName);
    await page.keyboard.press("Tab");
    await page.getByRole("option", { name: new RegExp(projects.enabled.projectName) }).press("Enter");
    await expect(page).toHaveURL((url) => url.searchParams.get("project_id") === String(projects.enabled.projectId));
    await page.goBack();
    await expect(page).toHaveURL((url) => url.searchParams.get("project_id") === String(disabledScope.projectId) && url.searchParams.get("workspace_id") === String(disabledScope.workspaceId));
    await expect(page.getByRole("link", { name: historicalRun!.id, exact: true })).toBeVisible();
    await page.goForward();
    await expect(page).toHaveURL((url) => url.searchParams.get("project_id") === String(projects.enabled.projectId));
    await page.goBack();
    await expect(page.getByRole("link", { name: historicalRun!.id, exact: true })).toBeVisible();
    await screenshot(page, "execution-disabled");
    const otherContext = await browser.newContext({ baseURL: origin() });
    try {
      const other = await otherContext.newPage();
      await login(other, accounts.unassigned, route(projects.enabled, `/infra-automation/workflows/${workflow.id}`));
      expect((await otherContext.request.get(`/api/v1/infra-automation/workflows/${workflow.id}`)).status()).toBe(403);
      await expect(other.getByText(/no permitted projects|project membership|operation.*unavailable/i).first()).toBeVisible();
      await expect(other.getByText(workflow.id, { exact: true })).toHaveCount(0);
    } finally { await otherContext.close(); }
  });

  test("bad Origin and missing CSRF cannot mutate a browser-authenticated draft", async ({ page, context }) => {
    const { accounts, projects } = fixture();
    const csrf = await login(page, accounts.operator, route(projects.enabled));
    const workflow = await createWorkflow(context, csrf, projects.enabled, `Transport proof ${Date.now()}`);
    const data = { expected_version: workflow.draft_version, definition: definition(projects.enabled), reason: "Transport denial proof" };
    for (const headers of [{ Origin: "https://foreign.invalid", "X-CSRF-Token": csrf }, { Origin: origin() }, { Origin: origin(), "X-CSRF-Token": "synthetic-invalid-csrf" }]) {
      const denied = await context.request.put(`/api/v1/infra-automation/workflows/${workflow.id}/draft`, { headers, data });
      expect(denied.status()).toBe(403);
    }
    const current = await context.request.get(`/api/v1/infra-automation/workflows/${workflow.id}`);
    expect((await current.json()).data.draft_version).toBe(workflow.draft_version);
  });

  test("concurrent edit conflict clears validation and requires a fresh review", async ({ page, context }) => {
    const { accounts, projects } = fixture();
    const csrf = await login(page, accounts.operator, route(projects.enabled));
    const workflowName = `Conflict proof ${Date.now()}`;
    const workflow = await createWorkflow(context, csrf, projects.enabled, workflowName);
    await page.getByRole("button", { name: "Refresh workflows", exact: true }).click();
    await page.getByRole("link", { name: workflowName, exact: true }).click();
    await page.getByLabel("Reason", { exact: true }).fill("Stale browser save");
    const initialValidation = page.waitForResponse((response) => response.url().endsWith(`/workflows/${workflow.id}/validate`) && response.request().method() === "POST", { timeout: 15_000 });
    await page.getByRole("button", { name: /validate/i, exact: true }).click();
    expect((await (await initialValidation).json()).data.valid).toBe(true);
    await expect(page.getByRole("button", { name: /save draft/i })).toBeEnabled();
    const changed = await context.request.put(`/api/v1/infra-automation/workflows/${workflow.id}/draft`, { headers: { Origin: origin(), "X-CSRF-Token": csrf }, data: { expected_version: workflow.draft_version, definition: definition(projects.enabled), reason: "Concurrent author changed the draft" } });
    expect(changed.status()).toBe(200);
    const saveButton = page.getByRole("button", { name: /save draft/i });
    let staleSaveStatus: number | null = null;
    page.on("response", (response) => {
      if (response.url().endsWith(`/workflows/${workflow.id}/draft`) && response.request().method() === "PUT") staleSaveStatus = response.status();
    });
    let clicked = false;
    try { await saveButton.click({ timeout: 1500 }); clicked = true; }
    catch (error) { if (await saveButton.isEnabled()) throw error; }
    if (clicked) await expect.poll(() => staleSaveStatus, { timeout: 15_000 }).toBe(409);
    else await expect(page.getByRole("alert").filter({ hasText: /saved version changed/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /publish/i })).toBeDisabled();
    await page.getByRole("button", { name: "Reload server state" }).click();
    await expect(page.getByText("Current server draft reloaded. Validate before continuing.")).toBeVisible();
    await expect(page.getByRole("button", { name: /publish/i })).toBeDisabled();
    const reviewed = page.waitForResponse((response) => response.url().endsWith(`/workflows/${workflow.id}/validate`) && response.request().method() === "POST", { timeout: 15_000 });
    await page.getByRole("button", { name: "Validate", exact: true }).click();
    expect((await (await reviewed).json()).data.valid).toBe(true);
    await expect(page.getByRole("button", { name: /publish/i })).toBeEnabled();
    let committedRevision: string | undefined;
    let publishRequests = 0;
    const publicationPath = `**/api/v1/infra-automation/workflows/${workflow.id}/revisions`;
    await page.route(publicationPath, async (intercepted) => {
      if (intercepted.request().method() !== "POST") return intercepted.continue();
      publishRequests += 1;
      const committed = await intercepted.fetch();
      expect(committed.status()).toBe(200);
      committedRevision = (await committed.json()).data.id;
      await intercepted.abort("failed");
    });
    await page.getByRole("button", { name: "Publish revision", exact: true }).press("Enter");
    await expect(page.getByRole("alert").filter({ hasText: /last mutation was not confirmed/i })).toBeVisible();
    expect(committedRevision).toBeTruthy();
    expect(publishRequests).toBe(1);
    await page.getByRole("button", { name: "Reload server state", exact: true }).click();
    await expect(page.getByRole("button", { name: "Publish revision", exact: true })).toBeDisabled();
    const revisionRead = await context.request.get(`/api/v1/infra-automation/workflows/${workflow.id}/revisions`);
    expect(revisionRead.status()).toBe(200);
    expect((await revisionRead.json()).data.items.map((revision: { id: string }) => revision.id)).toEqual([committedRevision]);
    await page.getByRole("link", { name: "Back to workflows", exact: true }).click();
    await page.getByRole("link", { name: workflowName, exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: /last mutation was not confirmed/i })).toBeVisible();
    await expect(page.getByRole("button", { name: "Publish revision", exact: true })).toBeDisabled();
    expect(publishRequests).toBe(1);
    await page.unroute(publicationPath);
  });

  test("workflow list network failure exposes explicit recovery", async ({ page }) => {
    const { accounts, projects } = fixture();
    await page.route("**/api/v1/infra-automation/workflows?*", (intercepted) => intercepted.abort("failed"));
    await login(page, accounts.operator, route(projects.enabled));
    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(page.getByText(/No workflows in this scope|No uploaded preflight runs in this scope/)).toHaveCount(0);
    await page.unroute("**/api/v1/infra-automation/workflows?*");
    await page.getByRole("button", { name: "Refresh workflows", exact: true }).click();
    await expect(page.getByRole("button", { name: "Create workflow", exact: true })).toBeEnabled();
  });

  test("same-scope unsaved YAML survives ordinary session network loss and explicit recovery", async ({ page, context }) => {
    const { accounts, projects } = fixture();
    await login(page, accounts.operator, route(projects.enabled));
    await expect(page.getByRole("button", { name: "Create workflow", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Create workflow", exact: true }).press("Enter");
    await page.getByLabel("Workflow name", { exact: true }).fill("Retained synthetic offline draft");
    await page.getByLabel("Reason", { exact: true }).fill("Review after local connection recovery");
    const yaml = page.getByLabel("Workflow YAML", { exact: true });
    const candidate = `${await yaml.inputValue()}\n# Synthetic unsaved offline review note\n`;
    await yaml.fill(candidate);
    await expect(page.getByRole("button", { name: "Validate", exact: true })).toBeEnabled();
    try {
      await context.setOffline(true);
      const sessionFailed = page.waitForEvent("requestfailed", { predicate: (request) => request.url().endsWith("/api/v1/auth/session") });
      await page.evaluate(() => window.dispatchEvent(new Event("focus")));
      await sessionFailed;
      await expect(yaml).toHaveValue(candidate);
      await expect(page.getByRole("button", { name: "Validate", exact: true })).toBeDisabled();
      await expect(page.getByRole("button", { name: "Save draft", exact: true })).toBeDisabled();
      await expect(page.getByRole("button", { name: "Publish revision", exact: true })).toBeDisabled();
      // A new draft cannot expose a run-start action before publication.
      await expect(page.getByRole("button", { name: "Start preflight", exact: true })).toHaveCount(0);
    } finally { await context.setOffline(false); }
    await page.getByRole("button", { name: "Refresh access", exact: true }).click();
    await expect(yaml).toHaveValue(candidate);
    await expect(page.getByRole("button", { name: "Validate", exact: true })).toBeEnabled();
    const validated = page.waitForResponse((response) => response.url().endsWith("/workflows/validate"), { timeout: 15_000 });
    await page.getByRole("button", { name: "Validate", exact: true }).press("Enter");
    expect((await validated).status()).toBe(200);
    expect((await (await validated).json()).data.valid).toBe(true);
    await expect(page.getByRole("button", { name: "Save draft", exact: true })).toBeEnabled();
    await expect(yaml).toHaveValue(candidate);
  });

  test("server account revocation removes protected workflow content", async ({ browser, page, context }) => {
    const { accounts, projects } = fixture();
    const csrf = await login(page, accounts.operator, route(projects.enabled));
    const workflow = await createWorkflow(context, csrf, projects.enabled, `Revocation proof ${Date.now()}`);
    const targetContext = await browser.newContext({ baseURL: origin() });
    try {
      const target = await targetContext.newPage();
      await login(target, accounts.revoked, route(projects.enabled, `/infra-automation/workflows/${workflow.id}`));
      const revoked = await context.request.post(`/api/v1/auth/accounts/${accounts.revoked.principalId}/revoke`, { headers: { Origin: origin(), "X-CSRF-Token": csrf } });
      expect(revoked.status()).toBe(200);
      await target.reload();
      await expect(target.getByRole("link", { name: /sign in|account access/i }).first()).toBeVisible();
      expect((await targetContext.request.get(`/api/v1/infra-automation/workflows/${workflow.id}`)).status()).toBe(401);
      await expect(target.getByText(workflow.id, { exact: true })).toHaveCount(0);
    } finally { await targetContext.close(); }
  });

  test("server-expired browser session returns to named account entry", async ({ page, context }) => {
    test.skip(!process.env.AUTOMATION_UI_CONTAINER, "Requires the disposable container name to expire synthetic server sessions.");
    const { accounts, projects } = fixture();
    const csrf = await login(page, accounts.expired, route(projects.enabled));
    const scope = projects.enabled;
    const workflow = await createWorkflow(context, csrf, scope, `Mounted report expiry proof ${Date.now()}`);
    const headers = { Origin: origin(), "X-CSRF-Token": csrf };
    const published = await context.request.post(`/api/v1/infra-automation/workflows/${workflow.id}/revisions`, { headers, data: {
      expected_version: workflow.draft_version, idempotency_key: `expiry-publish-${Date.now()}`, reason: "Publish synthetic mounted report expiry proof",
    } });
    expect(published.status()).toBe(200);
    const revision = (await published.json()).data;
    const admitted = await context.request.post("/api/v1/infra-automation/preflights", { headers, data: {
      run: { workflow_id: workflow.id, revision_id: revision.id, workspace_id: scope.workspaceId, inputs: {}, idempotency_key: `expiry-run-${Date.now()}`, reason: "Produce independent protected expiry evidence" },
      artifacts: [{ name: "main.tf", content: 'resource "aws_s3_bucket" "expiry" { bucket = "synthetic-expiry-proof" }' }],
    } });
    expect(admitted.status()).toBe(200);
    const run = (await admitted.json()).data;
    let reportId: number | undefined;
    await expect.poll(async () => {
      const response = await context.request.get(`/api/v1/infra-automation/runs/${run.id}/reports`);
      expect(response.status()).toBe(200);
      const links = (await response.json()).data;
      reportId = links.items[0]?.report_id;
      return typeof reportId === "number";
    }, { timeout: 180_000, intervals: [1000, 2000] }).toBe(true);
    const reportPath = `/reports/${reportId}?private=1&automation_run=${run.id}`;
    await page.goto(reportPath);
    await expect(page.locator(".dw-report-title-block")).toBeVisible();
    await expect(page.getByRole("link", { name: /back to run/i })).toBeVisible();
    execFileSync("docker", ["exec", process.env.AUTOMATION_UI_CONTAINER!, "python", "/tmp/seed_infra_automation_ui.py", "--expire-user", accounts.expired.username], { stdio: "pipe" });
    const expired = page.waitForResponse((response) => response.url().endsWith("/api/v1/auth/session") && response.status() === 401, { timeout: 15_000 });
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expired;
    // Keep the same mounted report route: a reload would conceal retained
    // React Query observer data after identity invalidation.
    await expect(page).toHaveURL(new URL(reportPath, origin()).href);
    await expect(page.locator(".dw-report-title-block")).toHaveCount(0);
    await expect(page.getByRole("link", { name: /back to run/i })).toHaveCount(0);
    const protectedReport = await context.request.get(`/api/v1/analyses/${reportId}`);
    expect([401, 403]).toContain(protectedReport.status());
    expect((await protectedReport.json()).data).toBeUndefined();
    expect((await context.request.get(`/api/v1/infra-automation/workflows/${workflow.id}`)).status()).toBe(401);
    expect((await context.request.get(`/api/v1/infra-automation/capabilities?project_id=${projects.enabled.projectId}`)).status()).toBe(401);
    await page.goto(`/settings/account?returnTo=${encodeURIComponent(reportPath)}`);
    await expect(page.getByLabel("Username", { exact: true })).toBeVisible();
  });
});
