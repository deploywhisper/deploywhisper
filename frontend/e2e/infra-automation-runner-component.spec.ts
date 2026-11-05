/** Synthetic component fault models, NOT real enrollment or AC6 qualification.
 * Account/scope navigation uses the disposable composed HTTP API. Only the
 * runner/collection responses named below are intercepted to exercise races.
 */
import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, openSync, readFileSync } from "node:fs";
import { expect, test, type Page, type Route } from "@playwright/test";

type Account = { username: string; password: string; principalId: string };
type Scope = { projectId: number; workspaceId: number; projectName: string; projectKey: string };
type Fixture = { version: 1; origin: string; lane: string; accounts: Record<string, Account>; operatorPool: Account[]; projects: Record<"enabled" | "disabled", Scope> };
const origin = "http://localhost:8080", fixturePath = process.env.RUNNER_UI_FIXTURE;
const digest = `sha256:${"a".repeat(64)}`;
const syntheticToken = "enroll-v1-component-only-not-real-authority";
let operatorIndex = 0;
// Suppress automatic failure ARIA snapshots while one-time credentials may be visible.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";
test.use({ trace: "off", screenshot: "off", video: "off" });
const utc = (offset = 0) => new Date(Date.now() + offset).toISOString().replace(/\.\d{3}Z$/, "Z");
const pageRoute = (scope: Scope, path = "/infra-automation/runners") => `${path}?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`;
const envelope = (data: unknown) => ({ data, meta: { schema_version: "v1", correlation_id: "a".repeat(32) } });
const fulfill = (route: Route, data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(envelope(data)) });
const cursor = { version: 1, snapshot_id: "component-snapshot", next_cursor: null, limit: 25, last_sequence: 1, gap: false, truncated: false };

function fixture(): Fixture {
  try {
    const container = process.env.RUNNER_UI_CONTAINER;
    if (!fixturePath || process.env.BASE_URL !== origin || !container || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(container)) throw new Error();
    const inspected = JSON.parse(execFileSync("docker", ["inspect", "--type", "container", container], { encoding: "utf8", timeout: 10_000, stdio: ["ignore", "pipe", "pipe"] }))[0];
    if (!inspected.State.Running || inspected.Config.Labels?.["com.docker.compose.project"] !== "deploywhisper-story16-15" || !inspected.Config.Env.includes("RUNNER_UI_DISPOSABLE=1") || !inspected.Config.Env.includes("DEPLOYWHISPER_IDENTITY_PROFILE=local-development")) throw new Error();
    const fd = openSync(fixturePath, constants.O_RDONLY | constants.O_NOFOLLOW);
    try {
      const info = fstatSync(fd);
      if (!info.isFile() || info.uid !== process.getuid?.() || (info.mode & 0o777) !== 0o600 || info.nlink !== 1 || info.size > 262144) throw new Error();
      const value = JSON.parse(readFileSync(fd, "utf8")) as Fixture;
      if (value.version !== 1 || value.origin !== origin || value.lane !== "http-denial" || !Array.isArray(value.operatorPool) || !value.operatorPool.length) throw new Error();
      value.accounts.operator = value.operatorPool[operatorIndex++ % value.operatorPool.length];
      return value;
    } finally { closeSync(fd); }
  } catch { throw new Error("Component fault models require the private disposable Story16.15 HTTP fixture."); }
}
async function login(page: Page, account: Account, destination: string) {
  // Respect the unchanged per-origin sign-in rate limit across this single-worker lane.
  await new Promise<void>((resolve) => setTimeout(resolve, 3500));
  await page.goto(`/settings/account?returnTo=${encodeURIComponent(destination)}`);
  await page.getByLabel("Username", { exact: true }).fill(account.username);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  const response = page.waitForResponse((item) => new URL(item.url()).pathname === "/api/v1/auth/login" && item.request().method() === "POST");
  await page.getByRole("button", { name: "Sign in", exact: true }).press("Enter");
  expect((await response).status()).toBe(200);
  await expect(page).toHaveURL(new URL(destination, origin).href);
}
function capabilities(scope: Scope, allowed = true) {
  return { version: 1, project_id: scope.projectId, workspace_id: scope.workspaceId, evaluated_at: utc(), can_read_health: true, can_enroll: allowed, can_rotate: allowed, can_revoke: allowed, production_eligible: true, execution_enabled: true, restriction: allowed ? "none" : "administrator_required", profile_status: "available", configured_profiles: [{ profile_digest: digest, tool: "opentofu", tool_version: "1.13.1", runner_version: "1.0", tags: ["isolated"] }] };
}
async function runnerModel(page: Page, scope: Scope, options: { windowMs?: number; hold?: Promise<void>; lateFailure?: boolean } = {}) {
  let submissions = 0, allowed = true, held = options.hold;
  await page.addInitScript(() => {
    Object.defineProperty(window, "componentClipboardCalls", { value: 0, writable: true });
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async () => { const state = window as Window & { componentClipboardCalls: number }; state.componentClipboardCalls += 1; } } });
  });
  await page.route("**/api/v1/infra-automation/runner-capabilities?**", async (route) => {
    const params = new URL(route.request().url()).searchParams;
    await fulfill(route, capabilities({ ...scope, projectId: Number(params.get("project_id")), workspaceId: Number(params.get("workspace_id")) }, allowed));
  });
  await page.route("**/api/v1/infra-automation/runners?**", (route) => fulfill(route, { items: [], cursor }));
  await page.route("**/api/v1/infra-automation/runners/enrollments", async (route) => {
    submissions += 1;
    const request = route.request().postDataJSON();
    if (held) await held;
    if (options.lateFailure) { await route.abort("failed").catch(() => undefined); return; }
    await fulfill(route, { enrollment: { version: 1, audience: "runner-enrollment-v1", enrollment_id: `component-enrollment-${submissions}`, runner_id: `component-runner-${submissions}`, project_id: String(request.project_id), workspace_id: String(request.workspace_id), expires_at: utc(options.windowMs ?? 60_000), one_use: true }, token: syntheticToken }).catch(() => undefined);
  });
  return { submissions: () => submissions, deny: () => { allowed = false; }, holdNext: (promise: Promise<void>) => { held = promise; } };
}
async function issue(page: Page) {
  await page.getByLabel("Administration reason", { exact: true }).fill("Synthetic component race proof");
  await page.getByRole("button", { name: "Issue enrollment", exact: true }).press("Enter");
}
async function noPersistence(page: Page) {
  expect(await page.evaluate((value) => {
    const state = window as Window & { componentClipboardCalls: number };
    return state.componentClipboardCalls === 0 && !location.href.includes(value) && !Object.values(localStorage).some((item) => item.includes(value)) && !Object.values(sessionStorage).some((item) => item.includes(value));
  }, syntheticToken)).toBe(true);
}

test.describe("synthetic runner component races — not production enrollment acceptance", () => {
  test.skip(!fixturePath, "Requires real HTTP account fixture; runner responses are explicitly synthetic component fault models.");

  test("one-time reveal clears on close and never copies or persists automatically", async ({ page }) => {
    const data = fixture();
    const model = await runnerModel(page, data.projects.enabled);
    await login(page, data.accounts.operator, pageRoute(data.projects.enabled));
    await issue(page);
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveValue(syntheticToken);
    await noPersistence(page);
    await page.getByRole("button", { name: "Close and clear secret", exact: true }).press("Enter");
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0);
    await page.getByRole("link", { name: "Workflows and runs", exact: true }).click();
    await page.getByRole("link", { name: "Runners", exact: true }).click();
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0);
    expect(model.submissions()).toBe(1);
    await noPersistence(page);
  });

  test("a backwards wall clock cannot extend the server-anchored reveal window", async ({ page }) => {
    const data = fixture();
    await runnerModel(page, data.projects.enabled, { windowMs: 6000 });
    await page.addInitScript(() => { const original = Date.now.bind(Date); Date.now = () => original() - 3_600_000; });
    await login(page, data.accounts.operator, pageRoute(data.projects.enabled));
    await issue(page);
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveValue(syntheticToken);
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0, { timeout: 7500 });
    await noPersistence(page);
  });

  test("project and current authorization changes clear a visible reveal", async ({ page }) => {
    const data = fixture(), model = await runnerModel(page, data.projects.enabled);
    await login(page, data.accounts.operator, pageRoute(data.projects.enabled));
    await issue(page);
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveValue(syntheticToken);
    await page.locator(".dw-project-trigger").click();
    await page.getByRole("option").filter({ hasText: data.projects.disabled.projectName }).click();
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0);
    await page.locator(".dw-project-trigger").click();
    await page.getByRole("option").filter({ hasText: data.projects.enabled.projectName }).click();
    await issue(page);
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveValue(syntheticToken);
    model.deny();
    await page.getByRole("button", { name: "Refresh runner health", exact: true }).click();
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0);
    await expect(page.getByLabel("Enrollment JSON", { exact: true })).toHaveCount(0);
    await noPersistence(page);
  });

  test("an authentication-expiry response removes a currently visible reveal", async ({ page }) => {
    const data = fixture();
    await runnerModel(page, data.projects.enabled);
    await login(page, data.accounts.operator, pageRoute(data.projects.enabled));
    await issue(page);
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveValue(syntheticToken);
    await page.route("**/api/v1/infra-automation/runner-capabilities?**", (route) => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: { code: "authentication_required", message: "Synthetic component expiry", details: {} } }) }));
    await page.getByRole("button", { name: "Refresh runner health", exact: true }).click();
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Account access required", exact: true })).toBeVisible();
    await noPersistence(page);
  });

  for (const lateFailure of [false, true]) test(`late enrollment after route unmount ${lateFailure ? "keeps unknown authority blocked" : "records known outcome without replay or secret"}`, async ({ page }) => {
    const data = fixture();
    let release!: () => void;
    const hold = new Promise<void>((resolve) => { release = resolve; });
    const model = await runnerModel(page, data.projects.enabled, { hold, lateFailure });
    await login(page, data.accounts.operator, pageRoute(data.projects.enabled));
    await issue(page);
    await expect.poll(model.submissions).toBe(1);
    await page.getByRole("link", { name: "Workflows and runs", exact: true }).click();
    await page.getByRole("link", { name: "Runners", exact: true }).click();
    try {
      await page.getByLabel("Administration reason", { exact: true }).fill("Do not resend uncertain authority");
      await expect(page.getByRole("button", { name: "Issue enrollment", exact: true })).toBeDisabled();
      release();
      await page.waitForTimeout(150);
      await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0);
      await expect(page.getByLabel("Enrollment JSON", { exact: true })).toHaveCount(0);
      if (lateFailure) {
        await page.getByRole("button", { name: "Refresh runner health", exact: true }).click();
        await expect(page.getByRole("button", { name: "Issue enrollment", exact: true })).toBeDisabled();
      } else await expect(page.getByText(/Credential issuance completed for component-runner-1/)).toBeVisible();
      expect(model.submissions()).toBe(1);
      await noPersistence(page);
    } finally { release(); }
  });
});

function collectionView(scope: Scope, runId: string, version: number, capturedAt: string) {
  return { version: 1, run_id: runId, project_id: scope.projectId, workspace_id: scope.workspaceId, run_version: version, observed_at: utc(), finite_wait_seconds: 0, cancellation: { requested: false, requested_at: null, owned_processes: "not_confirmed", external_stop: "not_confirmed", external_possible: false, can_cancel: version === 2 }, limitations: ["Synthetic intercepted component observations; not real runner proof."], items: [{ step_id: "collect", repository_id: "component-repository", commit_sha: "b".repeat(40), profile_digest: digest, attempt_id: "component-attempt", attempt_number: 1, attempt_state: version === 2 ? "running" : "succeeded", lease_until: utc(60_000), routing_failure: null, diagnosis: { code: "eligible", eligible: true, correction: "Synthetic component fixture." }, observations: [ { kind: "source_bound", state: "bound", event_at: capturedAt }, { kind: "collection", state: version === 2 ? "running" : "succeeded", event_at: null }, { kind: "screened_upload", state: version === 2 ? "not_observed" : "finalized", event_at: null }, { kind: "analysis", state: version === 2 ? "pending" : "succeeded", event_at: null } ] }] };
}

test.describe("synthetic collection response ordering — not real runner acceptance", () => {
  test.skip(!fixturePath, "Requires the disposable HTTP account fixture; run responses are explicit fault models.");
  for (const remainsStale of [false, true]) test(`late observations after terminal run ${remainsStale ? "remain bounded and unavailable" : "refresh once without losing focus"}`, async ({ page }) => {
    const data = fixture(), scope = data.projects.enabled, runId = "component-run", capturedAt = utc(), runDeadline = utc(60_000);
    let runReads = 0, collectionReads = 0, release!: () => void;
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route(`**/api/v1/infra-automation/runs/${runId}**`, async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/collection")) {
        collectionReads += 1;
        if (collectionReads === 1) { await held; await fulfill(route, collectionView(scope, runId, 2, capturedAt)).catch(() => undefined); }
        else await fulfill(route, collectionView(scope, runId, remainsStale ? 2 : 3, capturedAt));
      } else if (path.endsWith("/steps")) await fulfill(route, { items: [{ id: "component-attempt", run_id: runId, step_id: "collect", attempt_number: 1, state: "succeeded", version: 3, fence: 1, generation: 1, deadline_at: utc(60_000), lease_until: null, output: null, uploads: [] }], cursor });
      else if (path.endsWith("/handoffs")) await fulfill(route, { version: 1, run_id: runId, project_id: scope.projectId, workspace_id: scope.workspaceId, items: [] });
      else if (path.endsWith("/reports")) await fulfill(route, { items: [], evidence_status: { version: 1, status: "missing", run_state: "succeeded", run_version: 3, attempt_id: null, attempt_state: null, manifest_present: false, report_available: false, evaluated_at: utc(), evidence_deadline: utc(60_000), limitations: [], context_todos: [], approval_eligible: false } });
      else { runReads += 1; await fulfill(route, { id: runId, workflow_id: "component-workflow", revision_id: "component-revision", project_id: scope.projectId, workspace_id: scope.workspaceId, requested_by: data.accounts.operator.principalId, state: runReads === 1 ? "running" : "succeeded", version: runReads === 1 ? 2 : 3, snapshot_digest: "a".repeat(64), definition_digest: "b".repeat(64), input_digest: "c".repeat(64), created_at: capturedAt, deadline_at: runDeadline, cancel_requested: false, cancellation_requested_at: null }); }
    });
    await login(page, data.accounts.operator, pageRoute(scope, `/infra-automation/runs/${runId}`));
    const logs = page.getByRole("button", { name: "View screened logs for attempt 1 (collect)", exact: true });
    await expect(logs).toBeVisible();
    await logs.focus();
    try {
      await expect.poll(() => runReads, { timeout: 8000 }).toBeGreaterThan(1);
      release();
      await expect.poll(() => collectionReads).toBe(2);
      if (remainsStale) await expect(page.getByRole("status").filter({ hasText: /^Collection observations are from a different run version\. Refresh current evidence before acting\./ })).toBeVisible();
      else await expect(page.locator("li").filter({ has: page.getByText("Shared analysis", { exact: true }) })).toContainText("succeeded");
      await expect(logs).toBeFocused();
      await page.waitForTimeout(1000);
      expect(collectionReads).toBe(2);
    } finally { release(); }
  });
});

function definiteFailure(route: Route, status: 403 | 409 | 422 | 503) {
  const code = { 403: "permission_denied", 409: "binding_conflict", 422: "request_validation_failed", 503: "authority_unavailable" }[status];
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ error: { code, message: "Synthetic component fault", details: { retryable: status === 503, correlation_id: "b".repeat(32) } } }) });
}
function syntheticRun(scope: Scope, principal: string, id: string, capturedAt: string) {
  return { id, workflow_id: "component-workflow", revision_id: "component-revision", project_id: scope.projectId, workspace_id: scope.workspaceId, requested_by: principal, state: "running", version: 2, snapshot_digest: "a".repeat(64), definition_digest: "b".repeat(64), input_digest: "c".repeat(64), created_at: capturedAt, deadline_at: utc(60_000), cancel_requested: false, cancellation_requested_at: null };
}
async function activeCollectionModel(page: Page, scope: Scope, principal: string, runId = "component-cancellable-run") {
  const capturedAt = utc();
  let collectionReads = 0, runReads = 0, cancellationPosts = 0, status: 200 | 403 | 503 = 200, runStatus: 200 | 403 | 503 = 200;
  let cancellation: ((route: Route) => Promise<void>) | undefined;
  await page.route(`**/api/v1/infra-automation/runs/${runId}**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/cancel")) { cancellationPosts += 1; if (cancellation) await cancellation(route); else await definiteFailure(route, 422); }
    else if (path.endsWith("/collection")) { collectionReads += 1; if (status !== 200) await definiteFailure(route, status); else await fulfill(route, collectionView(scope, runId, 2, capturedAt)); }
    else if (path.endsWith("/steps")) await fulfill(route, { items: [], cursor });
    else if (path.endsWith("/handoffs")) await fulfill(route, { version: 1, run_id: runId, project_id: scope.projectId, workspace_id: scope.workspaceId, items: [] });
    else if (path.endsWith("/reports")) await fulfill(route, { items: [], evidence_status: { version: 1, status: "pending", run_state: "running", run_version: 2, attempt_id: null, attempt_state: null, manifest_present: false, report_available: false, evaluated_at: utc(), evidence_deadline: utc(60_000), limitations: [], context_todos: [], approval_eligible: false } });
    else { runReads += 1; if (runStatus !== 200) await definiteFailure(route, runStatus); else await fulfill(route, syntheticRun(scope, principal, runId, capturedAt)); }
  });
  await page.route("**/api/v1/infra-automation/runs?**", (route) => fulfill(route, { items: [syntheticRun(scope, principal, runId, capturedAt)], cursor }));
  return { runId, collectionReads: () => collectionReads, runReads: () => runReads, cancellationPosts: () => cancellationPosts, failCollection: (value: 200 | 403 | 503) => { status = value; }, failRun: (value: 200 | 403 | 503) => { runStatus = value; }, onCancel: (handler: (route: Route) => Promise<void>) => { cancellation = handler; } };
}
async function collectedWorkflowModel(page: Page, scope: Scope, principal: string) {
  const workflowId = "component-workflow", revisionId = "component-revision", capturedAt = utc();
  const definition = { workflow_version: 2, project_id: String(scope.projectId), workspace_id: String(scope.workspaceId), environment: "test", inputs: {}, steps: [{ id: "collect", kind: "admitted_collection", depends_on: [], source: { kind: "collected", repository_id: "component-repository", commit_sha: "b".repeat(40), profile_digest: digest } }, { id: "analysis", kind: "shared_analysis", depends_on: ["collect"], artifact: { ref: "step", step_id: "collect", output: "screened_artifacts" } }] };
  const workflow = { id: workflowId, project_id: scope.projectId, workspace_id: scope.workspaceId, name: "Component collected workflow", draft_version: 1, archived: false, draft_digest: "a".repeat(64), definition, created_by: principal, created_at: capturedAt, updated_at: capturedAt };
  const revision = { id: revisionId, workflow_id: workflowId, project_id: scope.projectId, workspace_id: scope.workspaceId, revision_number: 1, digest: "a".repeat(64), published_by: principal, created_at: capturedAt, definition };
  let startPosts = 0;
  let start: (route: Route) => Promise<void> = (route) => definiteFailure(route, 422);
  await page.route(`**/api/v1/infra-automation/workflows/${workflowId}**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/collection")) await fulfill(route, { version: 1, workflow_id: workflowId, revision_id: revisionId, project_id: scope.projectId, workspace_id: scope.workspaceId, observed_at: utc(), finite_wait_seconds: 0, execution_enabled: true, can_request: true, items: [{ step_id: "collect", repository_id: "component-repository", commit_sha: "b".repeat(40), profile_digest: digest, inputs_required: false, diagnosis: { code: "eligible", eligible: true, correction: "Synthetic component readiness." } }] });
    else if (path.endsWith(`/revisions/${revisionId}`)) await fulfill(route, revision);
    else if (path.endsWith("/revisions")) await fulfill(route, { items: [revision], cursor });
    else await fulfill(route, workflow);
  });
  await page.route("**/api/v1/infra-automation/workflows?**", (route) => fulfill(route, { items: [workflow], cursor }));
  await page.route("**/api/v1/infra-automation/runs", async (route) => { if (route.request().method() === "POST") { startPosts += 1; await start(route); } else await route.continue(); });
  return { workflowId, revisionId, startPosts: () => startPosts, onStart: (handler: (route: Route) => Promise<void>) => { start = handler; } };
}
async function returnToCollectedWorkflow(page: Page) {
  await page.getByRole("link", { name: "Workflows and runs", exact: true }).click();
  await page.getByRole("link", { name: "Component collected workflow", exact: true }).click();
  await expect(page.getByLabel("Collection reason", { exact: true })).toBeVisible();
}

test.describe("synthetic reviewed mutation boundaries — not runner acceptance", () => {
  test.skip(!fixturePath, "Requires the real disposable HTTP account fixture; mutation results are explicitly intercepted fault models.");

  test("collection and run503 retain the focused cancellation draft while403 clears protected content", async ({ page }) => {
    const data = fixture(), scope = data.projects.enabled;
    const model = await activeCollectionModel(page, scope, data.accounts.operator.principalId);
    await login(page, data.accounts.operator, pageRoute(scope, `/infra-automation/runs/${model.runId}`));
    const reason = page.getByLabel("Cancellation reason", { exact: true });
    await reason.fill("Keep this local cancellation draft"); await reason.focus();
    const reads = model.collectionReads(); model.failCollection(503);
    await expect.poll(model.collectionReads, { timeout: 8000 }).toBeGreaterThan(reads);
    await expect(page.getByRole("alert").filter({ hasText: /Collection observations unavailable/ })).toBeVisible();
    await expect(reason).toHaveValue("Keep this local cancellation draft"); await expect(reason).toBeFocused();
    await expect(page.getByRole("button", { name: "Request cancellation", exact: true })).toBeDisabled();
    expect(model.cancellationPosts()).toBe(0);
    model.failCollection(200);
    await page.getByRole("button", { name: "Retry collection evidence", exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: /Collection observations unavailable/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Request cancellation", exact: true })).toBeEnabled();
    await reason.focus();
    const runReads = model.runReads(); model.failRun(503);
    await expect.poll(model.runReads, { timeout: 8000 }).toBeGreaterThan(runReads);
    await expect(page.getByRole("alert").filter({ hasText: /Retaining last-known run evidence/ })).toBeVisible();
    await expect(reason).toHaveValue("Keep this local cancellation draft"); await expect(reason).toBeFocused();
    await expect(page.getByRole("button", { name: "Request cancellation", exact: true })).toBeDisabled();
    expect(model.cancellationPosts()).toBe(0);
    model.failRun(403);
    await page.getByRole("button", { name: "Retry run", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Run access unavailable", exact: true })).toBeVisible();
    await expect(reason).toHaveCount(0);
  });

  for (const status of [409, 422] as const) test(`late coded cancellation${status} after unmount releases the same-version pending guard`, async ({ page }) => {
    const data = fixture(), scope = data.projects.enabled;
    const model = await activeCollectionModel(page, scope, data.accounts.operator.principalId);
    let release!: () => void; const held = new Promise<void>((resolve) => { release = resolve; });
    model.onCancel(async (route) => { await held; await definiteFailure(route, status).catch(() => undefined); });
    await login(page, data.accounts.operator, pageRoute(scope, `/infra-automation/runs/${model.runId}`));
    await page.getByLabel("Cancellation reason", { exact: true }).fill("Synthetic held cancellation");
    await page.getByRole("button", { name: "Request cancellation", exact: true }).click();
    await expect.poll(model.cancellationPosts).toBe(1);
    await page.getByRole("link", { name: "Runners", exact: true }).click();
    try {
      const rejected = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith(`/runs/${model.runId}/cancel`) && response.status() === status);
      release(); await rejected;
      await page.getByRole("link", { name: "Workflows and runs", exact: true }).click();
      await page.getByRole("tab", { name: "Runs", exact: true }).click();
      await page.getByRole("link", { name: model.runId, exact: true }).click();
      const reason = page.getByLabel("Cancellation reason", { exact: true });
      await expect(reason).toBeEnabled(); await reason.fill("A deliberate corrected request");
      await expect(page.getByRole("button", { name: "Request cancellation", exact: true })).toBeEnabled();
      expect(model.cancellationPosts()).toBe(1);
    } finally { release(); }
  });

  test("invalid single-line collection reasons never submit or permanently lock the form", async ({ page }) => {
    const data = fixture(), scope = data.projects.enabled;
    const model = await collectedWorkflowModel(page, scope, data.accounts.operator.principalId);
    await login(page, data.accounts.operator, pageRoute(scope, `/infra-automation/workflows/${model.workflowId}`));
    const reason = page.getByLabel("Collection reason", { exact: true }), button = page.getByRole("button", { name: "Request collection", exact: true });
    for (const value of ["bad\treason", "bad\u2028reason", "bad\u2029reason"]) {
      await reason.fill(value);
      if (await button.isEnabled()) await button.click();
      expect(model.startPosts()).toBe(0);
      await expect(reason).toBeEnabled();
    }
    await reason.fill("Valid corrected collection reason"); await expect(button).toBeEnabled(); await button.click();
    await expect.poll(model.startPosts).toBe(1);
  });

  for (const result of [409, 422, "success"] as const) test(`late collectionstart${result} after unmount settles the marker without another POST`, async ({ page }) => {
    const data = fixture(), scope = data.projects.enabled;
    const model = await collectedWorkflowModel(page, scope, data.accounts.operator.principalId);
    let release!: () => void; const held = new Promise<void>((resolve) => { release = resolve; });
    model.onStart(async (route) => { await held; if (result === "success") await fulfill(route, syntheticRun(scope, data.accounts.operator.principalId, "component-confirmed-run", utc())).catch(() => undefined); else await definiteFailure(route, result).catch(() => undefined); });
    await login(page, data.accounts.operator, pageRoute(scope, `/infra-automation/workflows/${model.workflowId}`));
    await page.getByLabel("Collection reason", { exact: true }).fill("Synthetic held collection");
    await page.getByRole("button", { name: "Request collection", exact: true }).click();
    await expect.poll(model.startPosts).toBe(1);
    await page.getByRole("link", { name: "Runners", exact: true }).click();
    try {
      const settled = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/infra-automation/runs" && response.request().method() === "POST");
      release(); await settled;
      await returnToCollectedWorkflow(page);
      if (result === "success") { const known = page.getByRole("link", { name: "Open confirmed collection run", exact: true }); await expect(known).toBeVisible(); await expect(known).toHaveAttribute("href", pageRoute(scope, "/infra-automation/runs/component-confirmed-run")); await expect(page.getByRole("button", { name: "Request collection", exact: true })).toBeDisabled(); }
      else { const reason = page.getByLabel("Collection reason", { exact: true }); await expect(reason).toBeEnabled(); await reason.fill("A deliberate corrected collection"); await expect(page.getByRole("button", { name: "Request collection", exact: true })).toBeEnabled(); }
      expect(model.startPosts()).toBe(1);
    } finally { release(); }
  });

  test("same-session membership refresh clears a reveal but retains uncertain issuance", async ({ page, context }) => {
    const data = fixture(), scope = data.projects.enabled;
    const model = await runnerModel(page, scope);
    let membershipDelta = 0;
    await page.route("**/api/v1/infra-automation/capabilities?**", async (route) => {
      const actual = await route.fetch(); const body = await actual.json();
      body.data.membership_version += membershipDelta;
      await route.fulfill({ response: actual, body: JSON.stringify(body) });
    });
    await login(page, data.accounts.operator, pageRoute(scope));
    const identityBefore = (await (await context.request.get("/api/v1/auth/session")).json()).data;
    await issue(page); await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveValue(syntheticToken);
    membershipDelta = 1; await page.getByRole("button", { name: "Refresh access", exact: true }).first().click();
    await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0);
    await expect(page.getByLabel("Enrollment JSON", { exact: true })).toHaveCount(0);
    let release!: () => void; model.holdNext(new Promise<void>((resolve) => { release = resolve; }));
    await issue(page); await expect.poll(model.submissions).toBe(2);
    membershipDelta = 2; await page.getByRole("button", { name: "Refresh access", exact: true }).first().click();
    try {
      await page.getByLabel("Administration reason", { exact: true }).fill("Do not bypass pending issuance");
      await expect(page.getByRole("button", { name: "Issue enrollment", exact: true })).toBeDisabled();
      const identityAfter = (await (await context.request.get("/api/v1/auth/session")).json()).data;
      expect(identityAfter.session_id).toBe(identityBefore.session_id);
      release();
      await expect(page.getByText(/Credential issuance completed for component-runner-2/)).toBeVisible();
      await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0);
      expect(model.submissions()).toBe(2); await noPersistence(page);
    } finally { release(); }
  });
});
