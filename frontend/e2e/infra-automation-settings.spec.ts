import { execFileSync, spawn } from "node:child_process";
import { closeSync, constants, fstatSync, mkdirSync, mkdtempSync, openSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import type { AutomationPolicy, AutomationSettings } from "../src/api/infraAutomationSettings";
import { chromium, expect, test, type Page, type Locator, type BrowserContext } from "@playwright/test";
const file = process.env.SETTINGS_UI_FIXTURE;
const origin = "http://localhost:8080";
test.use({ trace: "off", screenshot: "off", video: "off" });
type Account = { username: string; password: string; principalId: string };
type Scope = { projectId: number; workspaceId: number; projectName: string; projectKey: string };
type Fixture = { historical: { runId: string; manifestId: string; runVersion: number; originalDigest: string }; accounts: Record<string, Account>; projects: Record<"enabled" | "disabled", Scope>; workflows: Record<string, { workflowId: string; revisionId: string }> };
function fixture(): Fixture {
  if (!file || process.env.BASE_URL !== origin || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(process.env.SETTINGS_UI_CONTAINER ?? "")) throw new Error("Protected disposable settings fixture required.");
  const metadata = JSON.parse(execFileSync("docker", ["inspect", process.env.SETTINGS_UI_CONTAINER!], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }))[0];
  if (!metadata.State.Running || metadata.Config.Labels?.["com.docker.compose.project"] !== "deploywhisper-story16-18" || !(metadata.Config.Env as string[]).includes("AUTOMATION_UI_DISPOSABLE=1")) throw new Error("Disposable settings target is not verified.");
  const descriptor = openSync(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try { const stat = fstatSync(descriptor); if (!stat.isFile() || stat.nlink !== 1 || stat.uid !== process.getuid?.() || (stat.mode & 0o777) !== 0o600 || stat.size > 65536) throw new Error("Private fixture required."); return JSON.parse(readFileSync(descriptor, "utf8")); }
  finally { closeSync(descriptor); }
}
async function tabTo(page: Page, locator: Locator) {
  await expect(locator).toBeVisible(); await expect(locator).toBeEnabled();
  for (let n = 0; n < 200; n++) { if (await locator.evaluate((e) => e === document.activeElement)) return; await page.keyboard.press("Tab"); }
  await expect(locator).toBeFocused();
}
async function login(page: Page, account: Account, scope: Scope) {
  const path = `/settings?project_id=${scope.projectId}`;
  await page.goto(`${origin}/settings/account?returnTo=${encodeURIComponent(path)}`);
  await page.evaluate((id) => localStorage.setItem("deploywhisper.selectedProjectId", String(id)), scope.projectId);
  await tabTo(page, page.getByLabel("Username", { exact: true })); await page.keyboard.insertText(account.username); await page.keyboard.press("Tab"); await page.keyboard.insertText(account.password);
  await tabTo(page, page.getByRole("button", { name: "Sign in", exact: true }));
  const response = page.waitForResponse((r) => r.url().endsWith("/api/v1/auth/login") && r.request().method() === "POST"); await page.keyboard.press("Enter");
  const result = await response; expect(result.status()).toBe(200); const csrf = (await result.json()).data.csrf_token as string;
  await expect(page).toHaveURL(new URL(path, origin).href); return csrf;
}
async function screenshot(page: Page, name: string) {
  const dir = resolve("docs/verification/infra-automation/16-18/screenshots"); mkdirSync(dir, { recursive: true });
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByRole("heading", { name: "Automation settings", exact: true }).evaluate((element) => element.scrollIntoView({ block: "start" }));
    const findings = await new AxeBuilder({ page }).analyze(); expect(findings.violations.filter((x) => x.impact === "critical" || x.impact === "serious").map((x) => x.id)).toEqual([]);
    await page.screenshot({ path: resolve(dir, `${name}-${width}.png`) });
    const outcome = name === "settings-conflict" ? page.getByRole("alert") : name === "settings-target" ? page.getByRole("region", { name: "Registered automation targets" }) : name === "settings-draft-changed" ? page.getByRole("status").filter({ hasText: "changed on the server" }) : name.includes("unavailable") ? page.getByRole("status").filter({ hasText: "temporarily unavailable" }) : page.getByRole("status").filter({ hasText: "Automation settings saved" });
    if (name !== "settings-nonadmin") {
      await outcome.evaluate((element) => element.scrollIntoView({ block: "center" }));
      await page.screenshot({ path: resolve(dir, `${name}-outcome-${width}.png`) });
    }

  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}
async function current(context: BrowserContext, scope: Scope): Promise<AutomationPolicy> { const res = await context.request.get(`${origin}/api/v1/infra-automation/settings?project_id=${scope.projectId}`); expect(res.status()).toBe(200); return (await res.json()).data; }
async function patch(context: BrowserContext, scope: Scope, csrf: string, policy: AutomationPolicy, settings: AutomationSettings) { return context.request.patch(`${origin}/api/v1/infra-automation/settings`, { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: { project_id: scope.projectId, expected_version: policy.version, reason: "Synthetic settings browser verification", settings } }); }

function failReads(resources: ("policy" | "membership")[]) {
  // The source-controlled fixture rechecks its original nonroot/tmpfs guard;
  // this private operator-only switch can return failures for GETs only.
  execFileSync("docker", ["exec", process.env.SETTINGS_UI_CONTAINER!, "python", "-c", "import os,runpy,sys; runpy.run_path('/tmp/settings_ui_fixture.py')['guard'](); descriptor=os.open('/tmp/settings-ui-read-failures.json',os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600); os.write(descriptor,sys.argv[1].encode()); os.close(descriptor)", JSON.stringify(resources)], { stdio: ["ignore", "ignore", "pipe"] });
}
async function withNativeFocusBrowser(run: (context: BrowserContext, page: Page) => Promise<void>) {
  // Playwright's normal focus emulation keeps every tab visible, suppressing
  // TanStack's native visibility refetch. A private fresh browser attached with
  // noDefaults exercises actual tab visibility without dispatching app events.
  const profile = mkdtempSync(resolve(tmpdir(), "deploywhisper-settings-focus-"));
  const process = spawn(chromium.executablePath(), ["--headless", "--no-sandbox", "--no-first-run", "--disable-background-networking", "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0", `--user-data-dir=${profile}`], { stdio: "ignore" });
  const exited = new Promise<void>((done) => process.once("exit", () => done()));
  let browser: Awaited<ReturnType<typeof chromium.connectOverCDP>> | undefined;
  try {
    let port = "";
    await expect.poll(() => { try { port = readFileSync(resolve(profile, "DevToolsActivePort"), "utf8").split("\n")[0]; return /^\d+$/.test(port); } catch { return false; } }).toBe(true);
    browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`, { noDefaults: true });
    const context = browser.contexts()[0], page = await context.newPage();
    page.setDefaultTimeout(15000);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await run(context, page);
  } finally {
    await browser?.close(); process.kill("SIGTERM"); await exited;
    rmSync(profile, { recursive: true, force: true });
  }
}
async function focusRefetch(page: Page, context: BrowserContext, scope: Scope, resource: "policy" | "membership" | "session", status: number) {
  const away = await context.newPage();
  try {
    await away.goto("about:blank"); await away.bringToFront();
    await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden");
    const path = resource === "policy" ? `/api/v1/infra-automation/settings?project_id=${scope.projectId}` : resource === "membership" ? `/api/v1/projects/${encodeURIComponent(scope.projectKey)}/memberships` : "/api/v1/auth/session";
    // Session loss cancels sibling requests as soon as any protected read sees
    // 401, so whichever real auth/membership/policy response arrives proves it.
    const response = page.waitForResponse((result) => result.request().method() === "GET" && (resource === "session" ? result.status() === 401 && [path, `/api/v1/infra-automation/settings?project_id=${scope.projectId}`, `/api/v1/projects/${encodeURIComponent(scope.projectKey)}/memberships`].some((value) => result.url() === `${origin}${value}`) : result.url() === `${origin}${path}`));
    await page.bringToFront(); expect((await response).status()).toBe(status);
    await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("visible");
  } finally { await away.close(); }
}

test("operator saves typed settings, reviews conflict, disables with history, and nonadmin denies", async ({ page, context, browser }) => {
  test.skip(!file, "Requires the protected disposable settings Compose fixture.");
  page.setDefaultTimeout(15000);
  const data = fixture(), scope = data.projects.enabled;
  const csrf = await login(page, data.accounts.operator, scope);
  const active = page.getByLabel("Active run limit", { exact: true }); await expect(active).toHaveValue("10");
  const registration = await context.request.post("/api/v1/infra-automation/targets", { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: { project_id: scope.projectId, workspace_id: scope.workspaceId, expected_version: 0, reason: "Synthetic registered destination browser proof", definition: { version: 1, canonical_target: "settings-target", aliases: [], allowed_scopes: [{ project_id: scope.projectId, workspace_id: scope.workspaceId }], environment: "test", receiver_id: "settings-receiver", pipeline_repository_id: "synthetic-settings", pipeline_workflow_id: "settings-pipeline", pipeline_workflow_revision: "a".repeat(40), github_owner: "synthetic-owner", github_repository: "synthetic-repository", github_workflow: "deploy.yml", workflow_ref: "main", api_origin: "https://api.github.com", allowed_private_addresses: [], credential_ref: "settings-github-ref", receiver_credential_ref: "settings-receiver-ref", enabled: true } } });
  expect(registration.status()).toBe(200);
  await page.getByRole("combobox", { name: "Target workspace", exact: true }).selectOption(String(scope.workspaceId));
  await page.getByRole("combobox", { name: "Registered target", exact: true }).selectOption("settings-target");
  await expect(page.getByRole("definition").filter({ hasText: "settings-target" })).toBeVisible();
  await screenshot(page, "settings-target");
  const purge = await context.request.post(`/api/v1/infra-automation/manifests/${data.historical.manifestId}/purge`, { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: { expected_run_version: data.historical.runVersion, reason: "Purge expired synthetic browser manifest" } });
  expect(purge.status()).toBe(200);
  const receipt = (await purge.json()).data;
  expect(receipt.content_status).toBe("removed");
  expect(receipt.original_digest).toBe(data.historical.originalDigest);
  const purgedReports = await context.request.get(`/api/v1/infra-automation/runs/${data.historical.runId}/reports`);
  expect(purgedReports.status()).toBe(200);
  const purgedEvidence = (await purgedReports.json()).data.evidence_status;
  expect(purgedEvidence.approval_eligible).toBe(false);
  expect(purgedEvidence.limitations).toContain("Screened manifest content was removed under retention; retained report and provenance remain advisory.");


  await tabTo(page, active); await active.fill("0");
  await page.getByLabel("Change reason", { exact: true }).fill("Check current safety floors");
  await page.getByRole("button", { name: "Save automation settings", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Active run limit must be an integer from 1 to 10");
  await active.fill("8");
  await page.getByLabel("Change reason", { exact: true }).fill("Synthetic operator capacity adjustment");
  await tabTo(page, page.getByRole("button", { name: "Save automation settings", exact: true })); await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "Automation settings saved" })).toContainText("Version 2");
  expect((await current(context, scope)).settings.max_active_runs).toBe(8);
  await screenshot(page, "settings-saved");
  await page.getByRole("button", { name: "Refresh automation settings", exact: true }).click(); await expect(active).toBeEnabled();
  let policy = await current(context, scope);
  expect((await patch(context, scope, csrf, policy, { ...policy.settings, credential_ttl_seconds: 59 })).status()).toBe(422);
  // Another administrator advances the real policy while the browser holds its old CAS version.
  expect((await patch(context, scope, csrf, policy, { ...policy.settings, max_queued_runs: 90 })).status()).toBe(200);
  await active.fill("7"); await page.getByLabel("Change reason", { exact: true }).fill("Stale form must conflict");
  await page.getByRole("button", { name: "Save automation settings", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Settings changed or the requested reduction conflicts");
  expect((await current(context, scope)).settings.max_active_runs).toBe(8);
  await screenshot(page, "settings-conflict");
  await page.getByRole("button", { name: "Refresh automation settings", exact: true }).click(); await expect(active).toBeEnabled();
  await page.getByLabel("Workflow limit", { exact: true }).fill("1");
  await page.getByLabel("Change reason", { exact: true }).fill("Unsafe reduction below retained workflows");
  await page.getByRole("button", { name: "Save automation settings", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("requested reduction conflicts with retained usage");
  await page.getByRole("button", { name: "Refresh automation settings", exact: true }).click(); await expect(active).toBeEnabled();
  const retainedRunResponse = await context.request.post("/api/v1/infra-automation/preflights", { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: { run: { workflow_id: data.workflows.uploaded.workflowId, revision_id: data.workflows.uploaded.revisionId, workspace_id: scope.workspaceId, inputs: {}, idempotency_key: `settings-history-${Date.now()}`, total_timeout_seconds: 3600, reason: "Synthetic retained history browser verification" }, artifacts: [{ name: "main.tf", content: 'resource "aws_s3_bucket" "settings_history" { bucket = "synthetic-settings-history" }' }] } });
  expect(retainedRunResponse.status()).toBe(200);
  const retainedRun = (await retainedRunResponse.json()).data as { id: string };
  await page.getByLabel("Enable automation execution", { exact: true }).uncheck(); await page.getByLabel("Change reason", { exact: true }).fill("Disable new execution while preserving history");
  await page.getByRole("button", { name: "Save automation settings", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Automation settings saved" })).toContainText("History and reconciliation remain available");
  policy = await current(context, scope); expect(policy.settings.enabled).toBe(false);
  const readHistory = await context.request.get(`/api/v1/infra-automation/runs?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`); expect(readHistory.status()).toBe(200);
  await screenshot(page, "settings-disabled");
  const retainedReports = await context.request.get(`/api/v1/infra-automation/runs/${retainedRun.id}/reports`);
  expect(retainedReports.status()).toBe(200);
  const reports = (await retainedReports.json()).data;
  expect(reports.evidence_status.version).toBe(1);
  expect(reports.evidence_status.approval_eligible).toBe(false);
  expect(reports.evidence_status.manifest_present).toBe(true);
  expect(Array.isArray(reports.evidence_status.limitations)).toBe(true);

  // New selected project remounts the form and discards unsaved/receipt state from the old scope.
  await page.getByRole("button", { name: "Refresh automation settings", exact: true }).click(); await expect(active).toBeEnabled();
  await active.fill("6"); await page.getByLabel("Change reason", { exact: true }).fill("Unsaved values belong only to the original project");
  await page.getByRole("button", { name: /Switch project|UI proof enabled|Select project/ }).first().click();
  const destination = page.getByRole("option", { name: new RegExp(data.projects.disabled.projectName) });
  if (await destination.count()) await destination.click(); else await page.getByText(data.projects.disabled.projectName, { exact: true }).click();
  await expect(page.getByLabel("Active run limit", { exact: true })).toHaveValue("10");
  await expect(page.getByLabel("Change reason", { exact: true })).toHaveValue("");
  await expect(page.getByRole("status").filter({ hasText: "Automation settings saved" })).toHaveCount(0);
  const viewerContext = await browser.newContext({ baseURL: origin }); const viewerPage = await viewerContext.newPage();
  try {
    const viewerCsrf = await login(viewerPage, data.accounts.viewer, scope);
    await expect(viewerPage.getByText("Project administrator access is required to manage automation settings.", { exact: true })).toBeVisible();
    await expect(viewerPage.getByRole("button", { name: "Save automation settings", exact: true })).toHaveCount(0);
    expect((await patch(viewerContext, scope, viewerCsrf, policy, { ...policy.settings, enabled: true })).status()).toBe(403);
    expect((await current(context, scope)).settings.enabled).toBe(false);
    await screenshot(viewerPage, "settings-nonadmin");
  } finally { await viewerContext.close(); }
  await page.goto(`/infra-automation/runs/${data.historical.runId}?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`);
  await expect(page.getByRole("heading", { name: "Preflight run", exact: true })).toBeVisible();
  const evidenceHeading = page.getByRole("heading", { name: /^Evidence / });
  await expect(evidenceHeading).toBeVisible();
  await expect(page.getByText("Screened manifest content was removed under retention; retained report and provenance remain advisory.", { exact: true })).toBeVisible();
  await expect(page.getByText("Submit a new preflight for current evidence; retained metadata cannot restore removed content.", { exact: true })).toBeVisible();
  const directory = resolve("docs/verification/infra-automation/16-18/screenshots");
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    await evidenceHeading.evaluate((element) => element.scrollIntoView({ block: "start" }));
    const findings = await new AxeBuilder({ page }).analyze(); expect(findings.violations.filter((x) => x.impact === "critical" || x.impact === "serious").map((x) => x.id)).toEqual([]);
    await page.screenshot({ path: resolve(directory, `settings-integrated-history-${width}.png`) });
  }
});

test("dirty same-scope drafts survive native focus refetch, server changes and transient read failures", async () => {
  test.skip(!file, "Requires the protected disposable settings Compose fixture.");
  const data = fixture(), scope = data.projects.disabled;
  await withNativeFocusBrowser(async (context, page) => {
    const csrf = await login(page, data.accounts.operator, scope);
    const active = page.getByLabel("Active run limit", { exact: true }), reason = page.getByLabel("Change reason", { exact: true });
    const save = page.getByRole("button", { name: "Save automation settings", exact: true }), refresh = page.getByRole("button", { name: "Refresh automation settings", exact: true });
    await expect(save).toBeEnabled();
    const base = await current(context, scope);
    let browserSaves = 0;
    page.on("request", (request) => { if (request.method() === "PATCH" && request.url() === `${origin}/api/v1/infra-automation/settings`) browserSaves++; });
    try {
      await active.fill("7"); await reason.fill("Keep my original draft and reason");
      expect((await patch(context, scope, csrf, base, { ...base.settings, max_queued_runs: 90 })).status()).toBe(200);
      await focusRefetch(page, context, scope, "policy", 200);
      await expect(page.getByRole("status").filter({ hasText: "changed on the server" })).toBeVisible();
      await expect(active).toHaveValue("7"); await expect(reason).toHaveValue("Keep my original draft and reason");
      await expect(page.getByText(new RegExp(`^Loaded policy version ${base.version}\\.`))).toBeVisible();
      await expect(save).toBeDisabled(); expect(browserSaves).toBe(0);
      expect((await current(context, scope)).settings.max_active_runs).toBe(base.settings.max_active_runs);
      await screenshot(page, "settings-draft-changed");

      await refresh.click(); await expect(save).toBeEnabled();
      const reviewed = await current(context, scope);
      await expect(active).toHaveValue(String(reviewed.settings.max_active_runs));
      await expect(page.getByLabel("Queued run limit", { exact: true })).toHaveValue("90"); await expect(reason).toHaveValue("");
      await active.fill("6"); await reason.fill("Preserve the draft through temporary unavailability");
      for (const resource of ["policy", "membership"] as const) {
        failReads([resource]); await focusRefetch(page, context, scope, resource, 503);
        await expect(page.getByRole("status").filter({ hasText: "temporarily unavailable" })).toBeVisible();
        await expect(active).toHaveValue("6"); await expect(reason).toHaveValue("Preserve the draft through temporary unavailability");
        await expect(save).toBeDisabled(); expect(browserSaves).toBe(0);
        await screenshot(page, `settings-draft-${resource}-unavailable`);
        failReads([]); await focusRefetch(page, context, scope, resource, 200);
        await expect(save).toBeEnabled(); await expect(active).toHaveValue("6");
        await expect(reason).toHaveValue("Preserve the draft through temporary unavailability");
        expect(browserSaves).toBe(0);
      }
      const response = page.waitForResponse((result) => result.url() === `${origin}/api/v1/infra-automation/settings` && result.request().method() === "PATCH");
      await save.click(); const savedResponse = await response; expect(savedResponse.status()).toBe(200);
      expect(savedResponse.request().postDataJSON().expected_version).toBe(reviewed.version);
      await expect(page.getByRole("status").filter({ hasText: "Automation settings saved" })).toBeVisible();
      const saved = await current(context, scope); expect(saved.settings.max_active_runs).toBe(6); expect(saved.settings.max_queued_runs).toBe(90); expect(browserSaves).toBe(1);

      await refresh.click(); await expect(save).toBeEnabled(); await active.fill("5"); await reason.fill("Clear this draft on a definite save denial");
      // Failure-only request tampering reaches the real CSRF guard. Both GET
      // caches still hold successful administrator data when PATCH denies403;
      // no response is mocked and no authenticated operation is approved.
      const denyMutation = async (route: import("@playwright/test").Route) => {
        if (route.request().method() === "PATCH") await route.continue({ headers: { ...route.request().headers(), "x-csrf-token": "synthetic-invalid-mutation-protection" } });
        else await route.continue();
      };
      await page.route("**/api/v1/infra-automation/settings", denyMutation);
      const denied = page.waitForResponse((result) => result.url() === `${origin}/api/v1/infra-automation/settings` && result.request().method() === "PATCH");
      await save.click(); expect((await denied).status()).toBe(403);
      await expect(reason).toHaveCount(0); await expect(save).toHaveCount(0);
      expect(browserSaves).toBe(2);
      await page.unroute("**/api/v1/infra-automation/settings", denyMutation);
      await refresh.click(); await expect(save).toBeEnabled();
      await expect(active).toHaveValue("6"); await expect(reason).toHaveValue("");
      expect(browserSaves).toBe(2);
      await active.fill("5"); await reason.fill("This draft must clear with the session");
      const logout = await context.request.post(`${origin}/api/v1/auth/logout`, { headers: { Origin: origin, "X-CSRF-Token": csrf } }); expect(logout.status()).toBe(200);
      await focusRefetch(page, context, scope, "session", 401);
      await expect(page.getByLabel("Change reason", { exact: true })).toHaveCount(0); await expect(save).toHaveCount(0);
      await login(page, data.accounts.viewer, scope);
      await expect(page.getByText("Project administrator access is required to manage automation settings.", { exact: true })).toBeVisible();
      await expect(page.getByLabel("Change reason", { exact: true })).toHaveCount(0);
    } finally { failReads([]); }
  });
});
