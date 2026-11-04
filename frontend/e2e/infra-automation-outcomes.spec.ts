import { closeSync, constants, fstatSync, mkdirSync, openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

type Account = { username: string; password: string; principalId: string };
type Case = { runId: string; operationId: string; projectId: number; workspaceId: number; reportId: number };
type Fixture = { version: 1; accounts: { operator: Account; revoked: Account }; project: { projectId: number; workspaceId: number }; cases: Record<string, Case> };
const origin = "http://localhost:8080";
const fixturePath = process.env.OUTCOME_UI_FIXTURE;
const shots = resolve("docs/verification/infra-automation/16-11/screenshots");
// Synthetic account credentials must not enter traces or browser failure captures.
test.use({ trace: "off", screenshot: "off", video: "off" });
function fixture(): Fixture {
  if (!fixturePath || process.env.BASE_URL !== origin) throw new Error("The disposable composed outcome fixture at localhost:8080 is required.");
  const fd = openSync(fixturePath, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const stat = fstatSync(fd);
    if (!stat.isFile() || (stat.mode & 0o777) !== 0o600 || stat.uid !== process.getuid?.() || stat.size > 262144) throw new Error();
    const value = JSON.parse(readFileSync(fd, "utf8")) as Fixture;
    if (value.version !== 1 || !value.accounts.operator || !value.accounts.revoked || !value.cases.unknown) throw new Error();
    return value;
  } catch { throw new Error("The bounded private outcome browser fixture is invalid."); }
  finally { closeSync(fd); }
}
const route = (item: Case) => `/infra-automation/runs/${encodeURIComponent(item.runId)}?project_id=${item.projectId}&workspace_id=${item.workspaceId}`;
const signInTimes = new Map<string, number[]>();
async function paceSignIn(username: string): Promise<void> {
  const now = Date.now(), recent = (signInTimes.get(username) ?? []).filter((time) => now - time < 61_000);
  if (recent.length >= 5) {
    await new Promise((resolve) => setTimeout(resolve, Math.min(59_000, Math.max(1, 61_000 - (now - recent[0])))));
    return paceSignIn(username);
  }
  signInTimes.set(username, [...recent, now]);
}
async function login(page: Page, account: Account, destination: string): Promise<string> {
  await paceSignIn(account.username);
  await page.goto(`/settings/account?returnTo=${encodeURIComponent(destination)}`);
  await page.getByLabel("Username", { exact: true }).fill(account.username);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  const receipt = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/auth/login" && response.request().method() === "POST");
  await page.getByRole("button", { name: "Sign in", exact: true }).press("Enter");
  const response = await receipt;
  expect(response.status()).toBe(200);
  await expect(page).toHaveURL(new URL(destination, origin).href);
  return (await response.json()).data.csrf_token;
}
async function capture(page: Page, name: string) {
  mkdirSync(shots, { recursive: true });
  for (const width of [1440, 760, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    const target = name === "permanent-report" ? page.locator(".dw-report-title-block") : page.getByRole("heading", { name: "External handoffs", exact: true });
    await target.evaluate((element) => element.scrollIntoView({ block: "start" }));
    if (width === 760) {
      if (name === "permanent-report") {
        const findings = page.getByRole("tab", { name: /^Findings/i });
        await findings.focus(); await findings.press("ArrowLeft");
        const overview = page.getByRole("tab", { name: /^Overview/i });
        await expect(overview).toBeFocused();
        await overview.press("ArrowRight");
        await expect(findings).toBeFocused();
        await expect(findings).toHaveAttribute("aria-selected", "true");
      } else {
        const refresh = page.getByRole("button", { name: "Refresh outcome evidence", exact: true });
        await refresh.focus(); await refresh.press("Enter");
      }
      expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
      await target.evaluate((element) => element.scrollIntoView({ block: "start" }));
    }
    await page.screenshot({ path: resolve(shots, `${name}-${width}.png`), fullPage: true });
    expect(await page.locator(".dw-automation-stack > .dw-card").evaluateAll((cards) => cards.filter((card) => card.getBoundingClientRect().right > window.innerWidth).map((card) => ({ title: card.querySelector("h2")?.textContent, right: card.getBoundingClientRect().right, width: card.getBoundingClientRect().width, overflowing: Array.from(card.querySelectorAll("h2, h3, button, code")).filter((element) => element.getBoundingClientRect().right > window.innerWidth).slice(0, 5).map((element) => ({ tag: element.tagName, width: element.getBoundingClientRect().width })) })))).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}

test.describe("composed external outcome evidence", () => {
  test.skip(!fixturePath, "Requires the disposable Story16.11 outcome fixture.");
  test("real persisted dispatch, observation and verified completion stay separate", async ({ page, context }) => {
    const data = fixture();
    await login(page, data.accounts.operator, route(data.cases.unknown));
    for (const kind of ["unknown", "accepted", "running", "observed_success", "verified_success", "verified_failure", "cancellation"]) {
      const item = data.cases[kind];
      await page.goto(route(item));
      const section = page.getByRole("region", { name: `External handoff ${item.operationId}`, exact: true });
      await expect(section).toBeVisible();
      const response = await context.request.get(`/api/v1/infra-automation/runs/${item.runId}/handoffs?project_id=${item.projectId}&workspace_id=${item.workspaceId}`);
      expect(response.status()).toBe(200);
      const operation = (await response.json()).data.items.find((entry: { id: string }) => entry.id === item.operationId);
      expect(operation).toBeTruthy();
      await expect(section.locator("dt").filter({ hasText: /^Verified receiver completion$/ }).locator("+ dd")).toHaveText(operation.verified_outcome ?? "Unknown — no verified terminal receiver proof");
      if (kind === "observed_success") {
        expect(operation.observation.conclusion).toBe("success");
        expect(operation.verified_outcome).toBeNull();
        await expect(section.getByText("completed · success — observation only", { exact: true })).toBeVisible();
      }
      if (kind === "cancellation") await expect(section.getByText(/does not confirm that external work has stopped/)).toBeVisible();
      if (kind === "unknown" || kind === "verified_success" || kind === "cancellation") await capture(page, kind);
    }
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    const reportCase = data.cases.verified_success;
    const reportPath = `/reports/${reportCase.reportId}?private=1&automation_run=${encodeURIComponent(reportCase.runId)}`;
    await page.goto(reportPath);
    await expect(page.locator(".dw-report-title-block")).toBeVisible();
    await expect(page).toHaveURL(new URL(reportPath, origin).href);
    const overview = page.getByRole("tab", { name: /^Overview/i });
    await overview.focus(); await overview.press("ArrowRight");
    const findings = page.getByRole("tab", { name: /^Findings/i });
    await expect(findings).toBeFocused();
    await expect(findings).toHaveAttribute("aria-selected", "true");
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await capture(page, "permanent-report");
  });

  test("a human reconciles once through the actual scoped endpoint", async ({ page, context }) => {
    const data = fixture(), item = data.cases.reconcile;
    await login(page, data.accounts.operator, route(item));
    const button = page.getByRole("button", { name: `Reconcile handoff ${item.operationId}`, exact: true });
    await expect(button).toBeDisabled();
    await page.getByLabel(`Reconciliation reason for ${item.operationId}`, { exact: true }).fill("Review registered synthetic GitHub outcome evidence");
    let posts = 0;
    page.on("request", (request) => { if (request.method() === "POST" && new URL(request.url()).pathname.endsWith(`/handoffs/${item.operationId}/reconcile`)) posts++; });
    const receipt = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith(`/handoffs/${item.operationId}/reconcile`) && response.request().method() === "POST");
    await button.focus(); await button.press("Enter");
    expect((await receipt).status()).toBe(200);
    await expect(page.getByText("Reconciliation recorded. Refresh current outcome evidence.")).toBeVisible();
    expect(posts).toBe(1);
    const read = await context.request.get(`/api/v1/infra-automation/runs/${item.runId}/handoffs?project_id=${item.projectId}&workspace_id=${item.workspaceId}`);
    expect(read.status()).toBe(200);
    expect((await read.json()).data.items.find((entry: { id: string }) => entry.id === item.operationId).observation).not.toBeNull();
    await capture(page, "reconciled");
  });

  test("a rejected reconciliation permits a corrected manual request", async ({ page }) => {
    const data = fixture(), item = data.cases.reconcile_corrected;
    await login(page, data.accounts.operator, route(item));
    const path = `**/api/v1/infra-automation/handoffs/${item.operationId}/reconcile`;
    let posts = 0;
    await page.route(path, async (intercepted) => {
      posts++;
      if (posts === 1) return intercepted.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ error: { code: "request_validation_failed", message: "Correct the reason" } }) });
      await intercepted.continue();
    });
    const input = page.getByLabel(`Reconciliation reason for ${item.operationId}`, { exact: true });
    const button = page.getByRole("button", { name: `Reconcile handoff ${item.operationId}`, exact: true });
    await expect(input).toBeVisible();
    await input.fill("Initial synthetic reason");
    await button.click();
    await expect(page.getByText(/Reconciliation was rejected/)).toBeVisible();
    expect(posts).toBe(1);
    await input.fill("Corrected human reason to read registered external outcome");
    const receipt = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith(`/handoffs/${item.operationId}/reconcile`) && response.status() === 200);
    await button.press("Enter");
    expect((await receipt).status()).toBe(200);
    expect(posts).toBe(2);
    await expect(page.getByText("Reconciliation recorded. Refresh current outcome evidence.")).toBeVisible();
  });

  test("lost committed reconciliation stays blocked on equal-version reads without resending", async ({ page, context }) => {
    const data = fixture(), item = data.cases.reconcile_ambiguous;
    await login(page, data.accounts.operator, route(item));
    const readPath = `/api/v1/infra-automation/runs/${item.runId}/handoffs?project_id=${item.projectId}&workspace_id=${item.workspaceId}`;
    const before = await context.request.get(readPath);
    expect(before.status()).toBe(200);
    const stale = await before.json();
    const readPattern = `**/api/v1/infra-automation/runs/${item.runId}/handoffs?*`;
    await page.route(readPattern, (intercepted) => intercepted.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(stale) }));
    const mutationPattern = `**/api/v1/infra-automation/handoffs/${item.operationId}/reconcile`;
    let posts = 0;
    await page.route(mutationPattern, async (intercepted) => {
      posts++;
      const committed = await intercepted.fetch();
      expect(committed.status()).toBe(200);
      await intercepted.abort("failed");
    });
    await page.getByLabel(`Reconciliation reason for ${item.operationId}`, { exact: true }).fill("Review registered evidence despite synthetic lost response");
    const button = page.getByRole("button", { name: `Reconcile handoff ${item.operationId}`, exact: true });
    await button.click();
    await expect(page.getByText(/Reconciliation was not confirmed/)).toBeVisible();
    await expect(button).toBeDisabled();
    await page.getByRole("button", { name: "Refresh outcome evidence", exact: true }).click();
    await expect(page.getByText(/previous request remains unconfirmed/)).toBeVisible();
    await expect(button).toBeDisabled();
    expect(posts).toBe(1);
    await page.unroute(readPattern);
    await page.getByRole("button", { name: "Refresh outcome evidence", exact: true }).click();
    await expect(page.getByText(/previous request remains unconfirmed/)).toHaveCount(0);
    expect(posts).toBe(1);
    const after = await context.request.get(readPath);
    expect(after.status()).toBe(200);
    const operation = (await after.json()).data.items.find((entry: { id: string }) => entry.id === item.operationId);
    expect(operation.version).toBeGreaterThan(stale.data.items[0].version);
  });

  test("an in-flight reconciliation survives child error and equal-version remount", async ({ page }) => {
    const data = fixture(), item = data.cases.reconcile_lifecycle;
    await login(page, data.accounts.operator, route(item));
    const button = page.getByRole("button", { name: `Reconcile handoff ${item.operationId}`, exact: true });
    await expect(button).toBeVisible();
    await page.getByLabel(`Reconciliation reason for ${item.operationId}`, { exact: true }).fill("Read outcome evidence once across a synthetic child read failure");
    let release!: () => void, arrived!: () => void, posts = 0;
    const held = new Promise<void>((resolve) => { release = resolve; });
    const started = new Promise<void>((resolve) => { arrived = resolve; });
    await page.route(`**/api/v1/infra-automation/handoffs/${item.operationId}/reconcile`, async (intercepted) => {
      posts++; arrived(); await held;
      const result = await intercepted.fetch();
      await intercepted.fulfill({ response: result });
    });
    try {
      await button.click(); await started;
      let failNextRead = true;
      await page.route(`**/api/v1/infra-automation/runs/${item.runId}/handoffs?*`, async (intercepted) => {
        if (failNextRead) {
          failNextRead = false;
          return intercepted.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "authority_unavailable" } }) });
        }
        await intercepted.continue();
      });
      await page.getByRole("button", { name: "Refresh outcome evidence", exact: true }).click();
      await expect(page.getByText("External outcome evidence unavailable.", { exact: false })).toBeVisible();
      await page.getByRole("button", { name: "Retry outcome evidence", exact: true }).click();
      await expect(page.getByText(/previous request remains unconfirmed/)).toBeVisible();
      await expect(button).toBeDisabled();
      expect(posts).toBe(1);
      const receipt = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith(`/handoffs/${item.operationId}/reconcile`) && response.status() === 200);
      release(); expect((await receipt).status()).toBe(200);
      await page.getByRole("button", { name: "Refresh outcome evidence", exact: true }).click();
      await expect(page.getByText(/previous request remains unconfirmed/)).toHaveCount(0);
      expect(posts).toBe(1);
    } finally { release(); }
  });

  test("revocation removes handoff evidence from a mounted run", async ({ browser, page, context }) => {
    const data = fixture(), item = data.cases.unknown;
    const csrf = await login(page, data.accounts.operator, route(item));
    const targetContext = await browser.newContext({ baseURL: origin });
    try {
      const target = await targetContext.newPage();
      await login(target, data.accounts.revoked, route(item));
      await expect(target.getByRole("region", { name: `External handoff ${item.operationId}`, exact: true })).toBeVisible();
      const revoked = await context.request.post(`/api/v1/auth/accounts/${data.accounts.revoked.principalId}/revoke`, { headers: { Origin: origin, "X-CSRF-Token": csrf } });
      expect(revoked.status()).toBe(200);
      await target.getByRole("button", { name: "Refresh outcome evidence", exact: true }).click();
      await expect(target.getByRole("link", { name: /sign in|account access/i }).first()).toBeVisible();
      await expect(target.getByRole("region", { name: `External handoff ${item.operationId}`, exact: true })).toHaveCount(0);
      expect((await targetContext.request.get(`/api/v1/infra-automation/runs/${item.runId}/handoffs?project_id=${item.projectId}&workspace_id=${item.workspaceId}`)).status()).toBe(401);
    } finally { await targetContext.close(); }
  });
});
