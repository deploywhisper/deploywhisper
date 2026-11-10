import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, mkdirSync, openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";

type Account = { username: string; password: string; principalId: string };
type Scope = { projectId: number; workspaceId: number; projectName: string; projectKey: string };
type Workflow = { workflowId: string; revisionId: string };
type Origin = { kind: string; principal_id: string; principal_type: string; key_id: string | null; pr_ref: string | null; sources: { kind: string; repository_id?: string | null; commit_sha?: string | null; profile_digest?: string; step_id: string }[] };
type Run = { id: string; state: string; requested_by: string; origin: Origin };
type Fixture = { version: number; origin: string; lane: string; accounts: Record<string, Account>; operatorPool: Account[]; projects: Record<"enabled" | "disabled", Scope>; workflows: Record<"uploaded" | "collected", Workflow>; principals: Record<"service" | "agent", { principalId: string; keyId: string }>; source: { repository_id: string; commit_sha: string; profile_digest: string } };
const fixturePath = process.env.TRIGGER_UI_FIXTURE;
const origin = "http://localhost:8080";
let operatorIndex = 0;
// Credential entry never produces traces, videos or automatic failure screenshots.
test.use({ trace: "off", screenshot: "off", video: "off" });

function fixture(): Fixture {
  const container = process.env.TRIGGER_UI_CONTAINER;
  if (!fixturePath || !container || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(container) || process.env.BASE_URL !== origin) {
    throw new Error("The protected disposable trigger fixture is required.");
  }
  try {
    const inspected = JSON.parse(execFileSync("docker", ["inspect", "--type", "container", container], {
      encoding: "utf8", timeout: 10_000, stdio: ["ignore", "pipe", "pipe"],
    }))[0];
    const environment = new Map<string, string>((inspected.Config.Env as string[]).map((entry) => {
      const split = entry.indexOf("="); return [entry.slice(0, split), entry.slice(split + 1)];
    }));
    const bindings = inspected.NetworkSettings.Ports?.["8080/tcp"] as { HostIp: string; HostPort: string }[] | undefined;
    if (!inspected.State.Running || inspected.Config.Labels?.["com.docker.compose.project"] !== "deploywhisper-story16-17" ||
      environment.get("TRIGGER_UI_DISPOSABLE") !== "1" || environment.get("AUTOMATION_UI_DISPOSABLE") !== "1" ||
      environment.get("DEPLOYWHISPER_IDENTITY_PROFILE") !== "local-development" || environment.get("DEPLOYWHISPER_IDENTITY_ORIGIN") !== origin ||
      !bindings?.some((binding) => binding.HostIp === "127.0.0.1" && binding.HostPort === "8080")) throw new Error();
  } catch {
    // Docker output may include credentials; never surface child-process details.
    throw new Error("The live disposable trigger Compose target could not be verified.");
  }
  const descriptor = openSync(fixturePath, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  let value: Fixture;
  try {
    const metadata = fstatSync(descriptor);
    if (!metadata.isFile() || metadata.nlink !== 1 || (metadata.mode & 0o777) !== 0o600 || metadata.uid !== process.getuid?.() || metadata.size < 1 || metadata.size > 65_536) {
      throw new Error("Trigger fixture must be a bounded private regular file.");
    }
    value = JSON.parse(readFileSync(descriptor, "utf8")) as Fixture;
  } finally { closeSync(descriptor); }
  if (value.version !== 1 || value.origin !== origin || value.lane !== "signed-trigger-origins") throw new Error("Unsupported trigger fixture.");
  const operator = value.operatorPool[operatorIndex++];
  if (!operator) throw new Error("Synthetic operator pool exhausted.");
  value.accounts.operator = operator;
  return value;
}

const route = (scope: Scope, path = "/infra-automation") => `${path}?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`;
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

async function cleanAxe(page: Page) {
  const result = await new AxeBuilder({ page }).analyze();
  expect(result.violations.filter((item) => item.impact === "critical" || item.impact === "serious").map(({ id, nodes }) => ({ id, elements: nodes.map((node) => node.target) }))).toEqual([]);
}
async function capture(page: Page, name: string, anchor?: Locator) {
  const directory = resolve("docs/verification/infra-automation/16-17/screenshots");
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
    await page.screenshot({ path: resolve(directory, `${name}-${width}.png`), fullPage: false });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}


function exerciseOrigins(): Record<"humanCli" | "agentCli" | "webhook" | "pullRequest", Run> {
  const container = process.env.TRIGGER_UI_CONTAINER!;
  try {
    execFileSync("docker", ["exec", container, "python", "/tmp/trigger_ui_fixture.py", "--exercise"], { encoding: "utf8", timeout: 120_000, stdio: ["ignore", "pipe", "pipe"] });
    const output = execFileSync("docker", ["exec", container, "python", "/tmp/trigger_ui_fixture.py", "--results"], { encoding: "utf8", timeout: 15_000, maxBuffer: 131072, stdio: ["ignore", "pipe", "pipe"] });
    return JSON.parse(output);
  } catch (failure) {
    const stderr = (failure as { stderr?: Buffer }).stderr?.toString() ?? "";
    const safe = stderr.match(/Synthetic CLI [a-z-]+ failed: exit=-?\d+, code=[a-z_]+\./)?.[0] ?? stderr.match(/Disposable signed-origin fixture failed \([A-Za-z]+, status=(?:None|\d+)\)\./)?.[0];
    throw new Error(`The real synthetic CLI/signed API exercise did not complete.${safe ? ` ${safe}` : ""}`);
  }
}

async function manualRun(context: BrowserContext, csrf: string, data: Fixture): Promise<Run> {
  const scope = data.projects.enabled, workflow = data.workflows.uploaded;
  const response = await context.request.post("/api/v1/infra-automation/preflights", { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: {
    run: { workflow_id: workflow.workflowId, revision_id: workflow.revisionId, workspace_id: scope.workspaceId, inputs: {}, idempotency_key: `manual-origin-${Date.now()}`, total_timeout_seconds: 3600, reason: "Actual manual origin browser proof" },
    artifacts: [{ name: "main.tf", content: 'resource "aws_s3_bucket" "manual" { bucket = "synthetic-origin-manual" }' }],
  } });
  expect(response.status()).toBe(200); return (await response.json()).data;
}

async function showRunsTab(page: Page) {
  const runs = page.getByRole("tab", { name: "Runs", exact: true });
  if (await runs.getAttribute("aria-selected") !== "true") {
    await tabTo(page, page.getByRole("tab", { name: "Workflows", exact: true }));
    await page.keyboard.press("ArrowRight");
  }
  await expect(runs).toHaveAttribute("aria-selected", "true");
}

async function showRun(page: Page, scope: Scope, run: Run) {
  const listLink = page.getByRole("link", { name: "Workflows and runs", exact: true });
  await keyboardActivate(page, listLink);
  await expect(page).toHaveURL(new URL(route(scope), origin).href);
  await expect(page.getByRole("tab", { name: "Workflows", exact: true })).toHaveAttribute("aria-selected", "true");
  await showRunsTab(page);
  await keyboardActivate(page, page.getByRole("button", { name: "Refresh runs", exact: true }));
  const table = page.getByRole("table", { name: "Immutable runs in the selected scope", exact: true });
  await expect(table.getByRole("columnheader", { name: "Request origin", exact: true })).toBeVisible();
  const link = table.getByRole("link", { name: run.id, exact: true });
  await keyboardActivate(page, link);
  await expect(page).toHaveURL(new URL(route(scope, `/infra-automation/runs/${run.id}`), origin).href);
  const heading = page.getByRole("heading", { name: "Request origin", exact: true });
  await expect(heading).toBeVisible();
  return heading.locator("..");
}

function fact(region: Locator, name: string) { return region.locator("dt").filter({ hasText: new RegExp(`^${name}$`) }).locator("+ dd"); }

test.describe("signed trigger origin using real composed APIs", () => {
  test.skip(!fixturePath, "Requires the disposable signed-origin Compose lane.");
  test.beforeEach(async ({ page }) => page.setDefaultTimeout(15_000));
  test("manual, CLI, service and agent origins remain distinct and source-pinned", async ({ page, context }) => {
    const data = fixture(), scope = data.projects.enabled;
    const runs = exerciseOrigins();
    const csrf = await login(page, data.accounts.operator, scope);
    const manual = await manualRun(context, csrf, data);
    for (const run of [manual, runs.humanCli]) {
      await expect.poll(async () => {
        const response = await context.request.get(`/api/v1/infra-automation/runs/${run.id}`);
        return response.ok() ? (await response.json()).data.state : "unavailable";
      }, { timeout: 90_000 }).toBe("succeeded");
      const reports = await context.request.get(`/api/v1/infra-automation/runs/${run.id}/reports`);
      expect(reports.status()).toBe(200);
      expect((await reports.json()).data.items).toHaveLength(1);
    }
    expect(manual.origin.kind).toBe("manual");
    expect(manual.origin.principal_type).toBe("human");
    expect(runs.humanCli.origin.kind).toBe("cli");
    expect(runs.humanCli.origin.principal_type).toBe("human");
    expect(runs.agentCli.origin.kind).toBe("cli");
    expect(runs.agentCli.origin.principal_type).toBe("agent");
    expect(runs.webhook.origin.kind).toBe("webhook");
    expect(runs.webhook.origin.principal_type).toBe("service");
    expect(runs.pullRequest.origin.kind).toBe("pull_request");
    expect(runs.pullRequest.origin.pr_ref).toBe("refs/pull/17/head");
    await showRunsTab(page);
    await keyboardActivate(page, page.getByRole("button", { name: "Refresh runs", exact: true }));
    const table = page.getByRole("table", { name: "Immutable runs in the selected scope", exact: true });
    for (const run of [manual, ...Object.values(runs)]) await expect(table.getByRole("link", { name: run.id, exact: true })).toBeVisible();
    await capture(page, "origin-history", table.getByRole("link", { name: manual.id, exact: true }));
    const cases: [string, Run, string, string][] = [
      ["manual", manual, "Manual", "Human"], ["human-cli", runs.humanCli, "CLI channel", "Human"],
      ["agent-cli", runs.agentCli, "CLI channel", "Agent"], ["service-webhook", runs.webhook, "Signed webhook", "Service"],
      ["service-pr", runs.pullRequest, "Signed PR request", "Service"],
    ];
    for (const [name, run, channel, principal] of cases) {
      const region = await showRun(page, scope, run);
      await expect(fact(region, "Channel")).toHaveText(channel);
      await expect(fact(region, "Authenticated principal type")).toHaveText(principal);
      await expect(fact(region, "Authenticated principal ID")).toHaveText(run.requested_by);
      const sources = region.getByRole("table", { name: "Requested source pins", exact: true });
      if (principal === "Human") {
        await expect(sources).toContainText("Unavailable");
        await expect(region.getByText("Signing key ID", { exact: true })).toHaveCount(0);
      } else {
        await expect(fact(region, "Signing key ID")).toHaveText(run.origin.key_id!);
        await expect(sources).toContainText(data.source.repository_id);
        await expect(sources).toContainText(data.source.commit_sha);
        await expect(sources).toContainText(data.source.profile_digest);
        await expect(region).not.toContainText("Acknowledgement");
      }
      if (name === "service-pr") await expect(fact(region, "Declared PR reference")).toHaveText("refs/pull/17/head");
      await capture(page, `origin-${name}`, region.getByRole("region", { name: "Requested source pins", exact: true }));
      const current = await context.request.get(`/api/v1/infra-automation/runs/${run.id}`);
      expect((await current.json()).data.origin).toEqual(run.origin);
    }
  });
});
