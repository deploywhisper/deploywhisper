import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, mkdirSync, openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

type Account = { username: string; password: string; principalId: string };
type Scope = { projectId: number; workspaceId: number; projectName: string; projectKey: string };
type Fixture = { version: 1; profile: "shared" | "single-operator"; accounts: Record<string, Account>; projects: Record<"primary" | "alternate", Scope> };
type Case = { caseId: string; runId: string; approvalId: string; projectId: number; workspaceId: number; reportId: number; deadline: string };
type Packet = {
  receipt: { id: string; version: number; binding_digest: string; status: string; reviewer_id: string | null; reason: string | null };
  context: { can_submit: boolean; confirmation: { required: boolean; approve_phrase: string | null; reject_phrase: string | null } };
  attribution: { principal_id: string; principal_type: string; role: string; before_digest: string | null; after_digest: string } | null;
};
const origin = "http://localhost:8080";
const fixturePath = process.env.APPROVAL_UI_FIXTURE;
const container = process.env.APPROVAL_UI_CONTAINER;
const identifier = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
const screenshotDirectory = resolve("docs/verification/infra-automation/16-9/screenshots");

// Authentication credentials must never enter traces, videos or failure captures.
test.use({ trace: "off", screenshot: "off", video: "off" });

function verifyDisposableTarget(): string {
  try {
    if (!container || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(container) || process.env.BASE_URL !== origin) throw new Error();
    const inspected = JSON.parse(execFileSync("docker", ["inspect", "--type", "container", container], {
      encoding: "utf8", timeout: 10_000, stdio: ["ignore", "pipe", "pipe"],
    }))[0];
    const environment = new Map<string, string>((inspected.Config.Env as string[]).map((entry) => {
      const separator = entry.indexOf("=");
      return [entry.slice(0, separator), entry.slice(separator + 1)];
    }));
    const ports = inspected.NetworkSettings.Ports?.["8080/tcp"] as { HostIp: string; HostPort: string }[] | undefined;
    const mounts = inspected.Mounts as { Type: string; Destination: string; RW: boolean }[];
    const tmpfs = inspected.HostConfig?.Tmpfs as Record<string, unknown> | undefined;
    // Docker Desktop records `tmpfs:` mounts in HostConfig.Tmpfs rather than
    // Mounts. The server independently checks /proc/self/mountinfo before writes.
    const hasDisposableData = mounts.some((mount) => mount.Type === "tmpfs" && mount.Destination === "/app/data") ||
      (typeof tmpfs?.["/app/data"] === "string" && tmpfs["/app/data"].length > 0);
    if (!inspected.State.Running || inspected.Config.Labels?.["com.docker.compose.project"] !== "deploywhisper-story16-9" ||
      environment.get("APPROVAL_UI_DISPOSABLE") !== "1" || environment.get("DATABASE_URL") !== "sqlite:////app/data/deploywhisper.db" ||
      environment.get("DEPLOYWHISPER_IDENTITY_PROFILE") !== "local-development" || environment.get("DEPLOYWHISPER_IDENTITY_ORIGIN") !== origin ||
      !["shared", "single-operator"].includes(environment.get("DEPLOYWHISPER_IDENTITY_DECISION_MODE") ?? "") ||
      !ports?.some((binding) => binding.HostPort === "8080" && ["", "0.0.0.0", "127.0.0.1", "::", "::1"].includes(binding.HostIp)) ||
      mounts.some((mount) => mount.Type === "volume") ||
      mounts.some((mount) => mount.Destination === "/app/data" && mount.Type !== "tmpfs") ||
      !hasDisposableData ||
      !mounts.some((mount) => mount.Type === "bind" && mount.Destination === "/tmp/approval_fixture.py" && !mount.RW)) throw new Error();
    return environment.get("DEPLOYWHISPER_IDENTITY_DECISION_MODE")!;
  } catch {
    // Docker inspect contains environment secrets. Do not propagate its output.
    throw new Error("The exact disposable approval Compose target could not be verified.");
  }
}

function loadFixture(): Fixture {
  const profile = verifyDisposableTarget();
  if (!fixturePath) throw new Error("Private approval browser fixture is required.");
  const descriptor = openSync(fixturePath, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const metadata = fstatSync(descriptor);
    if (!metadata.isFile() || (metadata.mode & 0o777) !== 0o600 || metadata.uid !== process.getuid?.() || metadata.size < 1 || metadata.size > 262_144) {
      throw new Error("Approval fixture must be an owned bounded mode-0600 regular file.");
    }
    const value = JSON.parse(readFileSync(descriptor, "utf8")) as Fixture & { requesterSession?: unknown };
    if (value.version !== 1 || value.profile !== profile || value.requesterSession || !value.accounts.admin || !value.projects.primary || !value.projects.alternate) throw new Error();
    for (const account of Object.values(value.accounts)) {
      if (typeof account.username !== "string" || !account.username.startsWith("ui-proof-approval-") || typeof account.password !== "string" || typeof account.principalId !== "string") throw new Error();
    }
    return value;
  } catch {
    throw new Error("Approval browser fixture is invalid or contains private server credentials.");
  } finally {
    closeSync(descriptor);
  }
}

const fixture = fixturePath ? loadFixture() : null;
let activeCases: Case[] = [];

function harness(args: string[]): string {
  verifyDisposableTarget();
  try {
    return execFileSync("docker", ["exec", container!, "python", "/tmp/approval_fixture.py", ...args], {
      encoding: "utf8", timeout: 30_000, stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  } catch {
    throw new Error("Disposable approval fixture operation failed; no credential output was retained.");
  }
}

function newCase(kind = "normal", project: "primary" | "alternate" = "primary"): Case {
  const value = JSON.parse(harness(["--new-case", kind, "--project", project])) as Case;
  if (!identifier.test(value.caseId) || !identifier.test(value.runId) || !identifier.test(value.approvalId) || value.projectId !== fixture!.projects[project].projectId || value.workspaceId !== fixture!.projects[project].workspaceId) throw new Error("Unexpected synthetic case scope.");
  activeCases.push(value);
  return value;
}

const inboxRoute = (scope: Scope) => `/infra-automation/approvals?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`;
const reviewRoute = (item: Case) => `/infra-automation/runs/${item.runId}?project_id=${item.projectId}&workspace_id=${item.workspaceId}&approval_id=${item.approvalId}`;
const approvalPath = (item: Case) => `/api/v1/infra-automation/approvals/${item.approvalId}`;
const approvalReadPath = (item: Case) => `${approvalPath(item)}?project_id=${item.projectId}&workspace_id=${item.workspaceId}`;

// The real identity service allows five sign-ins per account/minute. Keep the
// proof below that boundary rather than disabling or bypassing the limiter.
const signInTimes = new Map<string, number[]>();
async function paceSignIn(account: Account): Promise<void> {
  const now = Date.now(), recent = (signInTimes.get(account.username) ?? []).filter((time) => now - time < 61_000);
  if (recent.length >= 5) {
    await new Promise((resolve) => setTimeout(resolve, Math.min(59_000, Math.max(1, 61_000 - (now - recent[0])))));
    return paceSignIn(account);
  }
  signInTimes.set(account.username, [...recent, now]);
}

async function login(page: Page, account: Account, returnTo: string): Promise<string> {
  await paceSignIn(account);
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
  const signedIn = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/auth/login" && response.request().method() === "POST");
  await page.keyboard.press("Enter");
  const response = await signedIn;
  expect(response.status()).toBe(200);
  const csrf = (await response.json()).data.csrf_token as string;
  await expect(page).toHaveURL(new URL(returnTo, origin).href);
  return csrf;
}

async function apiLogin(request: APIRequestContext, account: Account): Promise<string> {
  await paceSignIn(account);
  const response = await request.post(`${origin}/api/v1/auth/login`, { headers: { Origin: origin }, data: { username: account.username, password: account.password } });
  expect(response.status()).toBe(200);
  return (await response.json()).data.csrf_token as string;
}

async function packet(request: APIRequestContext, item: Case): Promise<Packet> {
  const response = await request.get(`${origin}${approvalReadPath(item)}`);
  expect(response.status()).toBe(200);
  return (await response.json()).data as Packet;
}

async function cleanAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((item) => item.impact === "serious" || item.impact === "critical").map(({ id, nodes }) => ({ id, elements: nodes.map((node) => node.target) }))).toEqual([]);
}

async function screenshot(page: Page, name: string, section?: Locator) {
  // Call only after named-account login has completed and password inputs left.
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(0);
  mkdirSync(screenshotDirectory, { recursive: true });
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    if (section) await section.scrollIntoViewIfNeeded();
    await page.screenshot({ path: resolve(screenshotDirectory, `${name}-${width}.png`), fullPage: true });
  }
}

async function openDecision(page: Page, action: "approval" | "rejection" | "acknowledgement") {
  const trigger = page.getByRole("button", { name: action === "rejection" ? "Reject handoff" : action === "acknowledgement" ? "Acknowledge handoff" : "Approve handoff", exact: true });
  await expect(trigger).toBeEnabled();
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: `Confirm ${action}`, exact: true });
  await expect(dialog).toBeVisible();
  await expect.poll(async () => dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  return { trigger, dialog, confirm: dialog.getByRole("button", { name: `Confirm ${action}`, exact: true }) };
}

async function reviewReady(page: Page) {
  await expect(page.getByRole("heading", { name: "Review approval", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reload approval", exact: true })).toBeEnabled();
}

async function navigateReview(page: Page, item: Case) {
  await page.getByRole("link", { name: /^(Approval inbox|Approvals)$/ }).first().press("Enter");
  await expect(page.getByRole("heading", { name: "Approval inbox", exact: true })).toBeVisible();
  await page.getByRole("link", { name: `Review packet ${item.approvalId}`, exact: true }).press("Enter");
  await reviewReady(page);
}

async function submitDecision(page: Page, item: Case, action: "approval" | "rejection" | "acknowledgement", phrase?: string) {
  const opened = await openDecision(page, action);
  await opened.dialog.getByLabel("Reason", { exact: true }).fill(`Synthetic deliberate ${action}`);
  if (phrase) await opened.dialog.getByLabel("Type the confirmation phrase", { exact: true }).fill(phrase);
  if (action === "acknowledgement") await screenshot(page, "confirmation-acknowledgement");
  const submitted = page.waitForResponse((response) => new URL(response.url()).pathname === `${approvalPath(item)}/decision` && response.request().method() === "POST");
  await opened.confirm.press("Enter");
  expect((await submitted).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Decision receipt", exact: true })).toBeFocused();
}

test.describe("disposable human approval decision journeys", () => {
  test.skip(!fixture, "Requires the isolated Story16.9 Compose lane and protected exported browser fixture.");
  test.beforeEach(async ({ page }) => { activeCases = []; page.setDefaultTimeout(15_000); });
  test.afterEach(async () => {
    for (const item of activeCases) harness(["--cancel-case", item.caseId]);
  });

  test("shared keyboard inbox, high approval, critical rejection and advisory no-go", async ({ page, context }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const high = newCase("high"), critical = newCase("critical"), noGo = newCase("no-go");
    await login(page, fixture!.accounts.reviewer, inboxRoute(fixture!.projects.primary));
    await expect(page.getByRole("heading", { name: "Approval inbox", exact: true })).toBeVisible();
    await cleanAxe(page);
    await screenshot(page, "inbox");
    await page.getByRole("link", { name: `Review packet ${high.approvalId}`, exact: true }).press("Enter");
    await expect(page.getByRole("heading", { name: "Review approval", exact: true })).toBeFocused();
    const current = await packet(context.request, high);
    const missingCsrf = await context.request.post(`${approvalPath(high)}/decision`, { headers: { Origin: origin }, data: { expected_version: current.receipt.version, binding_digest: current.receipt.binding_digest, outcome: "approve", reason: "Missing mutation credential must deny", confirmation: "APPROVE ui-proof-target" } });
    expect(missingCsrf.status()).toBe(403);
    await expect(page.getByRole("link", { name: /permanent.*briefing|report/i }).first()).toHaveAttribute("href", new RegExp(`/reports/${high.reportId}`));
    for (const label of ["Collected at", "Source verification", "Redaction version", "Evidence deadline", "Approval expiry", "Remaining validity"]) await expect(page.getByText(label, { exact: true })).toBeVisible();
    await expect(page.getByText(/^\d+ minutes? \d+ seconds? remaining$/)).toBeVisible();
    await screenshot(page, "review-high");
    await screenshot(page, "freshness-window", page.getByText("Remaining validity", { exact: true }));
    await screenshot(page, "evidence-high", page.getByRole("heading", { name: "Confidence and context", exact: true }));
    await screenshot(page, "decision-controls-high", page.getByRole("button", { name: "Approve handoff", exact: true }));
    await page.getByRole("heading", { name: "Review approval", exact: true }).scrollIntoViewIfNeeded();
    const { trigger, dialog, confirm } = await openDecision(page, "approval");
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel("Reason", { exact: true }).fill("Review high synthetic risk deliberately");
    await dialog.getByLabel("Type the confirmation phrase", { exact: true }).fill("APPROVE other");
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel("Type the confirmation phrase", { exact: true }).fill("APPROVE ui-proof-target");
    await expect(confirm).toBeEnabled();
    // Check repeated Tab and Shift+Tab stay inside the modal, then Escape restores trigger.
    for (let index = 0; index < 8; index++) { await page.keyboard.press("Tab"); await expect.poll(async () => dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true); }
    for (let index = 0; index < 8; index++) { await page.keyboard.press("Shift+Tab"); await expect.poll(async () => dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true); }
    await cleanAxe(page);
    await screenshot(page, "confirmation-high");
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await submitDecision(page, high, "approval", "APPROVE ui-proof-target");
    expect((await packet(context.request, high)).receipt.status).toBe("approved");
    await cleanAxe(page);
    await screenshot(page, "receipt-approved", page.getByRole("heading", { name: "Decision receipt", exact: true }));
    await page.getByRole("link", { name: `Open permanent report ${high.reportId}`, exact: true }).press("Enter");
    await expect(page).toHaveURL(new RegExp(`/reports/${high.reportId}(?:[?#].*)?$`));
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await cleanAxe(page);
    await screenshot(page, "linked-permanent-report");
    await page.goBack();
    await reviewReady(page);
    await navigateReview(page, critical);
    await submitDecision(page, critical, "rejection", "REJECT ui-proof-target");
    expect((await packet(context.request, critical)).receipt.status).toBe("rejected");
    await screenshot(page, "receipt-rejected", page.getByRole("heading", { name: "Decision receipt", exact: true }));
    await navigateReview(page, noGo);
    await submitDecision(page, noGo, "approval");
    expect((await packet(context.request, noGo)).receipt.status).toBe("approved");
  });

  test("shared expiry during confirmation preserves reason and disables stale submission", async ({ page, context }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const item = newCase("expiry");
    await login(page, fixture!.accounts.reviewer2, reviewRoute(item));
    const { dialog, confirm } = await openDecision(page, "approval");
    const reason = "Preserve this local reason while evidence expires";
    await dialog.getByLabel("Reason", { exact: true }).fill(reason);
    await expect(confirm).toBeEnabled();
    await expect.poll(async () => (await packet(context.request, item)).context.can_submit, { timeout: 40_000, intervals: [1000] }).toBe(false);
    await expect(confirm).toBeDisabled({ timeout: 15_000 });
    await expect(dialog.getByLabel("Reason", { exact: true })).toHaveValue(reason);
    await cleanAxe(page);
    await screenshot(page, "expired-confirmation");
  });

  test("shared delayed review response cannot renew an elapsed server window", async ({ page }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const item = newCase("expiry");
    let delayed = false;
    await page.route((url) => url.pathname === approvalPath(item), async (route) => {
      if (delayed) { await route.continue(); return; }
      delayed = true;
      const response = await route.fetch();
      const data = (await response.json()).data;
      expect(data.context.can_submit).toBe(true);
      const wait = Math.max(0, Date.parse(data.context.effective_deadline) - Date.now() + 100);
      await new Promise((resolve) => setTimeout(resolve, wait));
      await route.fulfill({ response });
    });
    await login(page, fixture!.accounts.reviewer, reviewRoute(item));
    await expect(page.getByText("Elapsed; current server verification required", { exact: true })).toBeVisible({ timeout: 40_000 });
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toBeDisabled();
    await cleanAxe(page);
  });

  test("shared lost response reloads exact durable receipt without a second decision", async ({ page, context }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const item = newCase();
    await login(page, fixture!.accounts.reviewer2, reviewRoute(item));
    let posts = 0;
    page.on("request", (request) => { if (new URL(request.url()).pathname === `${approvalPath(item)}/decision` && request.method() === "POST") posts += 1; });
    let committed = false, blockRecovery = false, failedRecoveryReads = 0;
    await page.route((url) => url.pathname === approvalPath(item), async (route) => {
      if (blockRecovery && route.request().method() === "GET") {
        failedRecoveryReads += 1;
        await route.abort("failed");
      } else await route.continue();
    });
    await page.route(`**${approvalPath(item)}/decision`, async (route) => {
      const response = await route.fetch();
      committed = response.status() === 200;
      blockRecovery = committed;
      await response.dispose();
      await route.abort("failed");
    });
    const { dialog, confirm } = await openDecision(page, "approval");
    await dialog.getByLabel("Reason", { exact: true }).fill("Record despite a lost response");
    await confirm.press("Enter");
    await expect.poll(() => committed).toBe(true);
    await expect.poll(() => failedRecoveryReads).toBeGreaterThan(0);
    await expect(page.locator(".dw-automation-error-summary")).toBeFocused();
    if (await dialog.isVisible()) {
      await expect(dialog.getByRole("button", { name: "Cancel", exact: true })).toBeEnabled();
      await page.keyboard.press("Escape");
    }
    await expect(page.getByText(/previous submission is unconfirmed/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toBeDisabled();
    await cleanAxe(page);
    await screenshot(page, "response-unconfirmed");
    await expect(page.getByRole("button", { name: "Reload approval", exact: true })).toBeEnabled();
    blockRecovery = false;
    await page.getByRole("button", { name: "Reload approval", exact: true }).press("Enter");
    await expect(page.getByRole("heading", { name: "Decision receipt", exact: true })).toBeFocused();
    expect((await packet(context.request, item)).receipt.status).toBe("approved");
    expect(posts).toBe(1);
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toHaveCount(0);
    await cleanAxe(page);
    await screenshot(page, "receipt-recovered", page.getByRole("heading", { name: "Decision receipt", exact: true }));
  });

  test("shared ambiguous submission stays blocked after an unchanged pending read", async ({ page, playwright }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const item = newCase();
    await login(page, fixture!.accounts.reviewer, reviewRoute(item));
    let posts = 0;
    await page.route(`**${approvalPath(item)}/decision`, async (route) => { posts += 1; await route.abort("failed"); });
    const { dialog, confirm } = await openDecision(page, "approval");
    await dialog.getByLabel("Reason", { exact: true }).fill("A pending recovery cannot prove this request completed");
    await confirm.press("Enter");
    await expect(page.locator(".dw-automation-error-summary")).toBeFocused();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Reload approval", exact: true }).press("Enter");
    await expect(page.getByText(/previous submission is unconfirmed/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toBeDisabled();
    const other = await playwright.request.newContext({ baseURL: origin });
    try {
      const csrf = await apiLogin(other, fixture!.accounts.reviewer2), current = await packet(other, item);
      expect(current.receipt.status).toBe("pending");
      const response = await other.post(`${approvalPath(item)}/decision`, { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: { expected_version: current.receipt.version, binding_digest: current.receipt.binding_digest, outcome: "reject", reason: "Resolve the retained request with one verified decision" } });
      expect(response.status()).toBe(200);
      await page.getByRole("button", { name: "Reload approval", exact: true }).press("Enter");
      await expect(page.getByRole("heading", { name: "Decision receipt", exact: true })).toBeFocused();
      expect(posts).toBe(1);
      await cleanAxe(page);
    } finally { await other.dispose(); }
  });

  test("shared definite server rejection allows a corrected manual decision", async ({ page }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const item = newCase("high");
    await login(page, fixture!.accounts.reviewer2, reviewRoute(item));
    let rejected = false;
    await page.route(`**${approvalPath(item)}/decision`, async (route) => {
      const body = route.request().postDataJSON();
      const response = await route.fetch({ postData: JSON.stringify({ ...body, confirmation: "WRONG" }) });
      expect(response.status()).toBe(422); rejected = true;
      await route.fulfill({ response });
    });
    const { dialog, confirm } = await openDecision(page, "approval");
    await dialog.getByLabel("Reason", { exact: true }).fill("A definite validation rejection may be corrected");
    await dialog.getByLabel("Type the confirmation phrase", { exact: true }).fill("APPROVE ui-proof-target");
    await confirm.press("Enter"); await expect.poll(() => rejected).toBe(true);
    await expect(page.locator(".dw-automation-error-summary")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toBeEnabled();
    await page.unroute(`**${approvalPath(item)}/decision`);
    await submitDecision(page, item, "approval", "APPROVE ui-proof-target");
  });

  test("shared concurrent reviewer decision refreshes the existing receipt", async ({ page, context, playwright }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const item = newCase();
    await login(page, fixture!.accounts.reviewer, reviewRoute(item));
    let posts = 0;
    page.on("request", (request) => { if (new URL(request.url()).pathname === `${approvalPath(item)}/decision` && request.method() === "POST") posts += 1; });
    const opened = await openDecision(page, "approval");
    await opened.dialog.getByLabel("Reason", { exact: true }).fill("Second browser must not mint another decision");
    const other = await playwright.request.newContext({ baseURL: origin });
    try {
      const csrf = await apiLogin(other, fixture!.accounts.reviewer2);
      const current = await packet(other, item);
      const decided = await other.post(`${approvalPath(item)}/decision`, { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: { expected_version: current.receipt.version, binding_digest: current.receipt.binding_digest, outcome: "reject", reason: "Concurrent distinct verified reviewer" } });
      expect(decided.status()).toBe(200);
      // Polling may observe the competing decision before this keyboard action.
      // Either polling or the submission precheck must close stale confirmation.
      if (await opened.confirm.isVisible() && await opened.confirm.isEnabled()) await opened.confirm.press("Enter").catch(() => undefined);
      await expect(opened.dialog).toHaveCount(0);
      await expect(page.getByRole("heading", { name: "Decision receipt", exact: true })).toBeFocused();
      expect(posts).toBe(0);
      const result = await packet(context.request, item);
      expect(result.receipt.status).toBe("rejected");
      expect(result.receipt.reviewer_id).toBe(fixture!.accounts.reviewer2.principalId);
      await cleanAxe(page);
    } finally { await other.dispose(); }
  });

  test("shared changed tuple, unavailable authority and mandatory evidence cannot be overridden", async ({ page }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const changed = newCase(), unavailable = newCase(), blocked = newCase("pending-allowhardblock");
    await login(page, fixture!.accounts.reviewer, reviewRoute(changed));
    await reviewReady(page);
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toBeEnabled();
    harness(["--mutate-case", changed.caseId, "--mutation", "payload"]);
    await page.getByRole("button", { name: "Reload approval", exact: true }).press("Enter");
    await reviewReady(page);
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toBeDisabled();
    await cleanAxe(page);
    await screenshot(page, "changed-binding");
    harness(["--mutate-case", unavailable.caseId, "--mutation", "unavailable"]);
    await navigateReview(page, unavailable);
    await reviewReady(page);
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toBeDisabled();
    await cleanAxe(page);
    harness(["--mutate-case", unavailable.caseId, "--mutation", "restore"]);
    await page.getByRole("button", { name: "Reload approval", exact: true }).press("Enter");
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toBeEnabled();
    await navigateReview(page, blocked);
    await reviewReady(page);
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toBeDisabled();
    await expect(page.getByText(/incomplete/i).first()).toBeVisible();
    await cleanAxe(page);
    await screenshot(page, "hard-eligibility-block");
  });

  test("shared scope switching clears local decisions and live reviewer revocation clears protected data", async ({ page }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const item = newCase(), alternate = newCase("normal", "alternate");
    await login(page, fixture!.accounts.reviewer2, reviewRoute(item));
    const opened = await openDecision(page, "approval");
    await opened.dialog.getByLabel("Reason", { exact: true }).fill("Reason from the previous project");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: new RegExp(fixture!.projects.primary.projectName) }).press("Enter");
    await page.getByRole("option", { name: new RegExp(fixture!.projects.alternate.projectName) }).press("Enter");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await navigateReview(page, alternate);
    const next = await openDecision(page, "approval");
    await expect(next.dialog.getByLabel("Reason", { exact: true })).toHaveValue("");
    await page.keyboard.press("Escape");
    harness(["--revoke", "reviewer2"]);
    try {
      await page.getByRole("button", { name: "Reload approval", exact: true }).press("Enter");
      await expect(page.getByRole("heading", { name: "Review approval", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toHaveCount(0);
      await expect(page.getByText(/sign in|session expired|access required/i).first()).toBeVisible();
      await cleanAxe(page);
      await screenshot(page, "revoked-reviewer");
    } finally { harness(["--restore", "reviewer2"]); }
  });

  test("shared requester self-approval and read-only/unassigned accounts deny; admin exports retained attribution", async ({ page, playwright }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const self = newCase("self"), decided = newCase();
    const other = await playwright.request.newContext({ baseURL: origin });
    try {
      const csrf = await apiLogin(other, fixture!.accounts.reviewer);
      const before = await packet(other, decided);
      const response = await other.post(`${approvalPath(decided)}/decision`, { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: { expected_version: before.receipt.version, binding_digest: before.receipt.binding_digest, outcome: "approve", reason: "Immutable reviewer attribution" } });
      expect(response.status()).toBe(200);
    } finally { await other.dispose(); }
    harness(["--demote", "reviewer"]);
    try {
      await login(page, fixture!.accounts.readonly, reviewRoute(self));
      await expect(page.getByRole("heading", { name: "Approval access unavailable", exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Download scoped audit JSON", exact: true })).toHaveCount(0);
      await cleanAxe(page);
      await login(page, fixture!.accounts.unassigned, reviewRoute(self));
      await expect(page.getByText(/unavailable|no permitted projects/i).first()).toBeVisible();
      await expect(page.getByRole("heading", { name: "Review approval", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toHaveCount(0);
      await cleanAxe(page);
      await login(page, fixture!.accounts.admin, reviewRoute(self));
      await reviewReady(page);
      await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toBeDisabled();
      await cleanAxe(page);
      await screenshot(page, "requester-self-denied");
      await navigateReview(page, decided);
      await reviewReady(page);
      const retained = await packet(page.request, decided);
      expect(retained.attribution?.principal_id).toBe(fixture!.accounts.reviewer.principalId);
      expect(retained.attribution?.principal_type).toBe("human");
      expect(retained.attribution?.role).toBe("reviewer");
      expect(Boolean(retained.attribution?.before_digest && retained.attribution.after_digest && retained.attribution.before_digest !== retained.attribution.after_digest)).toBe(true);
      const download = page.waitForEvent("download");
      await page.getByRole("button", { name: "Download scoped audit JSON", exact: true }).press("Enter");
      const downloaded = await download;
      const stream = await downloaded.createReadStream();
      if (!stream) throw new Error("Scoped audit download unavailable.");
      const chunks: Buffer[] = [];
      for await (const chunk of stream) chunks.push(Buffer.from(chunk));
      const body = Buffer.concat(chunks).toString("utf8");
      expect(Object.values(fixture!.accounts).some((account) => body.includes(account.password))).toBe(false);
      expect(body.includes(fixture!.accounts.reviewer.principalId)).toBe(true);
      await cleanAxe(page);
      await screenshot(page, "audit-attribution", page.getByRole("heading", { name: "Decision receipt", exact: true }));
    } finally { harness(["--restore", "reviewer"]); }
  });

  test("shared late submission conflict cannot steal a recovered receipt's focus", async ({ page, playwright }) => {
    test.skip(fixture?.profile !== "shared", "Shared decision profile.");
    const item = newCase();
    await login(page, fixture!.accounts.reviewer, reviewRoute(item));
    let release!: () => void, held = false, replied = false;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    await page.route(`**${approvalPath(item)}/decision`, async (route) => {
      held = true; await gate;
      const response = await route.fetch(); expect(response.status()).toBe(409);
      await route.fulfill({ response }); replied = true;
    });
    const other = await playwright.request.newContext({ baseURL: origin });
    try {
      const opened = await openDecision(page, "approval");
      await opened.dialog.getByLabel("Reason", { exact: true }).fill("Wait for a late conflict after polling observes the receipt");
      await opened.confirm.press("Enter"); await expect.poll(() => held).toBe(true);
      const csrf = await apiLogin(other, fixture!.accounts.reviewer2), current = await packet(other, item);
      const response = await other.post(`${approvalPath(item)}/decision`, { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: { expected_version: current.receipt.version, binding_digest: current.receipt.binding_digest, outcome: "reject", reason: "First verified terminal decision" } });
      expect(response.status()).toBe(200);
      const receipt = page.getByRole("heading", { name: "Decision receipt", exact: true });
      await expect(receipt).toBeFocused(); release();
      await expect.poll(() => replied).toBe(true);
      await expect(page.getByRole("button", { name: "Reload approval", exact: true })).toBeEnabled();
      await expect(receipt).toBeFocused();
      await expect(page.locator(".dw-automation-error-summary")).toHaveCount(0);
      await cleanAxe(page);
    } finally { release(); await other.dispose(); }
  });

  test("single-operator keyboard acknowledgement is explicit and high confirmation is server-selected", async ({ page, context }) => {
    test.skip(fixture?.profile !== "single-operator", "Fresh one-human acknowledgement profile.");
    // Both cases precede admin browser login: later CLI authentication revokes it.
    const high = newCase("high"), rejected = newCase();
    await login(page, fixture!.accounts.admin, reviewRoute(high));
    await expect(page.getByText(/does not record independent review/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve handoff", exact: true })).toHaveCount(0);
    await cleanAxe(page);
    await screenshot(page, "acknowledgement-review", page.getByRole("heading", { name: "Authenticated acknowledgement", exact: true }));
    await submitDecision(page, high, "acknowledgement", "ACKNOWLEDGE ui-proof-target");
    const result = await packet(context.request, high);
    expect(result.receipt.status).toBe("approved");
    expect(result.receipt.reviewer_id).toBe(fixture!.accounts.admin.principalId);
    await cleanAxe(page);
    await screenshot(page, "acknowledgement-receipt", page.getByRole("heading", { name: "Decision receipt", exact: true }));
    await navigateReview(page, rejected);
    await submitDecision(page, rejected, "rejection");
    expect((await packet(context.request, rejected)).receipt.status).toBe("rejected");
  });
});
