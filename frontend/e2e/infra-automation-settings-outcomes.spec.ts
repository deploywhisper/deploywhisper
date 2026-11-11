import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, mkdirSync, openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";
const fixturePath = process.env.SETTINGS_OUTCOME_UI_FIXTURE;
const origin = "http://localhost:8080";
test.use({ trace: "off", screenshot: "off", video: "off" });
type Account = { username: string; password: string; principalId: string };
type Case = { runId: string; operationId: string; projectId: number; workspaceId: number; reportId: number };
type Fixture = { version: 1; accounts: { operator: Account }; cases: Record<string, Case> };
function fixture(): Fixture {
  const container = process.env.SETTINGS_OUTCOME_UI_CONTAINER;
  if (!fixturePath || process.env.BASE_URL !== origin || !container || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(container)) throw new Error("Protected disposable settings outcome fixture required.");
  const metadata = JSON.parse(execFileSync("docker", ["inspect", container], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }))[0];
  if (!metadata.State.Running || metadata.Config.Labels?.["com.docker.compose.project"] !== "deploywhisper-story16-18-outcomes" || !(metadata.Config.Env as string[]).includes("OUTCOME_UI_DISPOSABLE=1")) throw new Error("Disposable settings outcome target is not verified.");
  const descriptor = openSync(fixturePath, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try { const stat = fstatSync(descriptor); if (!stat.isFile() || stat.nlink !== 1 || stat.uid !== process.getuid?.() || (stat.mode & 0o777) !== 0o600 || stat.size > 262144) throw new Error("Private fixture required."); const value = JSON.parse(readFileSync(descriptor, "utf8")); if (value.version !== 1 || !value.cases?.accepted) throw new Error("Unsupported outcome fixture."); return value; }
  finally { closeSync(descriptor); }
}
async function tabTo(page: Page, locator: Locator) {
  await expect(locator).toBeVisible(); await expect(locator).toBeEnabled();
  for (let n = 0; n < 200; n++) { if (await locator.evaluate((element) => element === document.activeElement)) return; await page.keyboard.press("Tab"); }
  await expect(locator).toBeFocused();
}
async function capture(page: Page, name: string, target: Locator) {
  const directory = resolve("docs/verification/infra-automation/16-18/screenshots"); mkdirSync(directory, { recursive: true });
  for (const width of [1440, 760]) { await page.setViewportSize({ width, height: 1000 }); await target.evaluate((element) => element.scrollIntoView({ block: "start" })); const result = await new AxeBuilder({ page }).analyze(); expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious").map((v) => v.id)).toEqual([]); await page.screenshot({ path: resolve(directory, `${name}-${width}.png`) }); }
  await page.setViewportSize({ width: 1440, height: 1000 });
}
test("disabling after an actual synthetic approval preserves accepted-operation reconciliation", async ({ page, context }) => {
  test.skip(!fixturePath, "Requires protected disposable settings outcome Compose fixture.");
  page.setDefaultTimeout(15000);
  const data = fixture(), operation = data.cases.accepted;
  const settingsRoute = `/settings?project_id=${operation.projectId}`;
  await page.goto(`/settings/account?returnTo=${encodeURIComponent(settingsRoute)}`);
  await page.evaluate((id) => localStorage.setItem("deploywhisper.selectedProjectId", String(id)), operation.projectId);
  await tabTo(page, page.getByLabel("Username", { exact: true })); await page.keyboard.insertText(data.accounts.operator.username); await page.keyboard.press("Tab"); await page.keyboard.insertText(data.accounts.operator.password);
  await tabTo(page, page.getByRole("button", { name: "Sign in", exact: true })); const login = page.waitForResponse((r) => r.url().endsWith("/api/v1/auth/login") && r.request().method() === "POST"); await page.keyboard.press("Enter"); expect((await login).status()).toBe(200);
  await expect(page).toHaveURL(new URL(settingsRoute, origin).href);
  const handoffPath = `/api/v1/infra-automation/runs/${operation.runId}/handoffs?project_id=${operation.projectId}&workspace_id=${operation.workspaceId}`;
  const before = await context.request.get(handoffPath); expect(before.status()).toBe(200);
  const original = (await before.json()).data.items.find((item: { id: string }) => item.id === operation.operationId);
  expect(original.receiver_state).toBe("accepted"); expect(original.verified_outcome).toBeNull(); expect(original.lock_status).toBe("held");
  const enabled = page.getByLabel("Enable automation execution", { exact: true }); await expect(enabled).toBeChecked();
  await tabTo(page, enabled); await page.keyboard.press("Space");
  await page.getByLabel("Change reason", { exact: true }).fill("Disable after approved accepted synthetic handoff");
  await tabTo(page, page.getByRole("button", { name: "Save automation settings", exact: true })); await page.keyboard.press("Enter");
  const receipt = page.getByRole("status").filter({ hasText: "Automation settings saved" }); await expect(receipt).toContainText("History and reconciliation remain available");
  await capture(page, "settings-after-approval-disabled", receipt);
  // Router links preserve the freshly issued CSRF material; a full document reload intentionally does not.
  await page.getByRole("link", { name: "Read run history and reconcile external work", exact: true }).click();
  await page.getByRole("link", { name: operation.runId, exact: true }).click();
  await page.getByRole("button", { name: "Use run workspace", exact: true }).click();
  const region = page.getByRole("region", { name: `External handoff ${operation.operationId}`, exact: true }); await expect(region).toBeVisible();
  const reason = page.getByLabel(`Reconciliation reason for ${operation.operationId}`, { exact: true }); await expect(reason).toBeEnabled();
  await reason.fill("Read accepted operation evidence after feature disable");
  const button = page.getByRole("button", { name: `Reconcile handoff ${operation.operationId}`, exact: true }); await tabTo(page, button);
  const response = page.waitForResponse((r) => r.url().endsWith(`/handoffs/${operation.operationId}/reconcile`) && r.request().method() === "POST"); await page.keyboard.press("Enter"); expect((await response).status()).toBe(200);
  const after = await context.request.get(handoffPath); expect(after.status()).toBe(200);
  const reconciled = (await after.json()).data.items.find((item: { id: string }) => item.id === operation.operationId);
  expect(reconciled.version).toBeGreaterThan(original.version);
  expect(reconciled.acceptance.run_id).toBe(original.acceptance.run_id);
  expect(reconciled.receiver_state).toBe("accepted"); expect(reconciled.verified_outcome).toBeNull(); expect(reconciled.lock_status).toBe("held");
  const settings = await context.request.get(`/api/v1/infra-automation/settings?project_id=${operation.projectId}`); expect(settings.status()).toBe(200); expect((await settings.json()).data.settings.enabled).toBe(false);
  await capture(page, "settings-feature-off-reconciled", region);
});
