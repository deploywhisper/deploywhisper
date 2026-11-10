import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, mkdirSync, openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import type { AutomationPolicy, AutomationSettings } from "../src/api/infraAutomationSettings";
import { expect, test, type Page, type Locator, type BrowserContext } from "@playwright/test";
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
  await page.goto(`/settings/account?returnTo=${encodeURIComponent(path)}`);
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
    const outcome = name === "settings-conflict" ? page.getByRole("alert") : name === "settings-target" ? page.getByRole("region", { name: "Registered automation targets" }) : page.getByRole("status").filter({ hasText: "Automation settings saved" });
    if (name !== "settings-nonadmin") {
      await outcome.evaluate((element) => element.scrollIntoView({ block: "center" }));
      await page.screenshot({ path: resolve(dir, `${name}-outcome-${width}.png`) });
    }

  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}
async function current(context: BrowserContext, scope: Scope): Promise<AutomationPolicy> { const res = await context.request.get(`/api/v1/infra-automation/settings?project_id=${scope.projectId}`); expect(res.status()).toBe(200); return (await res.json()).data; }
async function patch(context: BrowserContext, scope: Scope, csrf: string, policy: AutomationPolicy, settings: AutomationSettings) { return context.request.patch("/api/v1/infra-automation/settings", { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: { project_id: scope.projectId, expected_version: policy.version, reason: "Synthetic settings browser verification", settings } }); }

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
  await page.getByRole("button", { name: /Switch project|UI proof enabled|Select project/ }).first().click();
  const destination = page.getByRole("option", { name: new RegExp(data.projects.disabled.projectName) });
  if (await destination.count()) await destination.click(); else await page.getByText(data.projects.disabled.projectName, { exact: true }).click();
  await expect(page.getByLabel("Active run limit", { exact: true })).toHaveValue("10");
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
