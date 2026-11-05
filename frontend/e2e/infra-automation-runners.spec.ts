import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, mkdirSync, openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

type Account = { username: string; password: string; principalId: string };
type Scope = { projectId: number; workspaceId: number; projectName: string; projectKey: string };
type Fixture = { version: 1; origin: string; lane: "http-denial"; accounts: Record<"operator" | "viewer" | "unassigned" | "revoked" | "expired", Account>; operatorPool: Account[]; projects: Record<"enabled" | "disabled", Scope> };
const origin = "http://localhost:8080";
const fixturePath = process.env.RUNNER_UI_FIXTURE;
const containerName = process.env.RUNNER_UI_CONTAINER;
const shots = resolve("docs/verification/infra-automation/16-15/screenshots");
let operatorIndex = 0;
// A credential-entry test must never leave a trace, video, automatic screenshot
// or storageState export. Deliberate captures happen only after safe navigation.
// Suppress automatic failure ARIA snapshots while one-time credentials may be visible.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";
test.use({ trace: "off", screenshot: "off", video: "off" });

function verifyDisposableTarget() {
  try {
    if (process.env.BASE_URL !== origin || !containerName || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(containerName)) throw new Error();
    const value = JSON.parse(execFileSync("docker", ["inspect", "--type", "container", containerName], { encoding: "utf8", timeout: 10_000, stdio: ["ignore", "pipe", "pipe"] }))[0];
    const environment = new Map<string, string>((value.Config.Env as string[]).map((entry) => { const separator = entry.indexOf("="); return [entry.slice(0, separator), entry.slice(separator + 1)]; }));
    const ports = value.NetworkSettings.Ports?.["8080/tcp"] as { HostIp: string; HostPort: string }[] | undefined;
    if (!value.State.Running || value.Config.Labels?.["com.docker.compose.project"] !== "deploywhisper-story16-15" ||
        value.Config.User !== "appuser" || environment.get("RUNNER_UI_DISPOSABLE") !== "1" ||
        environment.get("DATABASE_URL") !== "sqlite:////app/data/deploywhisper.db" ||
        environment.get("DEPLOYWHISPER_IDENTITY_PROFILE") !== "local-development" ||
        environment.get("DEPLOYWHISPER_IDENTITY_ORIGIN") !== origin ||
        !(value.Mounts.some((mount: { Destination: string; Type: string }) => mount.Destination === "/app/data" && mount.Type === "tmpfs") || (typeof value.HostConfig.Tmpfs?.["/app/data"] === "string" && !value.Mounts.some((mount: { Destination: string }) => mount.Destination === "/app/data"))) ||
        !ports?.some((port) => port.HostIp === "127.0.0.1" && port.HostPort === "8080")) throw new Error();
  } catch {
    // Docker inspection may contain unrelated secret environment values.
    throw new Error("The exact disposable HTTP runner browser target is required.");
  }
}

function fixture(): Fixture {
  verifyDisposableTarget();
  if (!fixturePath) throw new Error("A private runner browser fixture is required.");
  const descriptor = openSync(fixturePath, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const metadata = fstatSync(descriptor);
    if (!metadata.isFile() || metadata.uid !== process.getuid?.() || (metadata.mode & 0o777) !== 0o600 || metadata.nlink !== 1 || metadata.size < 1 || metadata.size > 262144) throw new Error();
    const value = JSON.parse(readFileSync(descriptor, "utf8")) as Fixture;
    if (value.version !== 1 || value.origin !== origin || value.lane !== "http-denial" || !value.projects.enabled || !value.projects.disabled || !Array.isArray(value.operatorPool)) throw new Error();
    const operator = value.operatorPool[operatorIndex++];
    if (!operator) throw new Error();
    value.accounts.operator = operator;
    return value;
  } catch { throw new Error("The private runner browser fixture is unavailable."); }
  finally { closeSync(descriptor); }
}

const route = (scope: Scope) => `/infra-automation/runners?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`;
async function login(page: Page, account: Account, destination: string): Promise<string> {
  // Respect the unchanged per-origin sign-in rate limit across this single-worker lane.
  await new Promise<void>((resolve) => setTimeout(resolve, 3500));
  await page.goto(`/settings/account?returnTo=${encodeURIComponent(destination)}`);
  await expect(page.getByLabel("Username", { exact: true })).toBeEnabled();
  await page.getByLabel("Username", { exact: true }).focus();
  await expect(page.getByLabel("Username", { exact: true })).toBeFocused();
  await page.keyboard.insertText(account.username);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
  await page.keyboard.insertText(account.password);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeFocused();
  const response = page.waitForResponse((item) => new URL(item.url()).pathname === "/api/v1/auth/login" && item.request().method() === "POST");
  await page.keyboard.press("Enter");
  const receipt = await response;
  expect(receipt.status()).toBe(200);
  const csrf = (await receipt.json()).data.csrf_token as string;
  await expect(page).toHaveURL(new URL(destination, origin).href);
  return csrf;
}
async function noRunnerSecrets(page: Page) {
  const safe = await page.evaluate(() => {
    const values = [document.body.innerText, location.href, ...Object.values(localStorage), ...Object.values(sessionStorage)];
    return values.every((value) => !/enroll-v1-|runner-v1-/.test(value));
  });
  expect(safe).toBe(true);
}
async function capture(page: Page, name: string) {
  mkdirSync(shots, { recursive: true });
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    await noRunnerSecrets(page);
    const result = await new AxeBuilder({ page }).analyze();
    expect(result.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? "")).map((item) => ({ id: item.id, targets: item.nodes.map((node) => node.target) }))).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(shots, `${name}-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}

test.describe("runner HTTP security and unavailable-state acceptance", () => {
  test.skip(!fixturePath, "Requires the disposable Story16.15 HTTP fixture; positive HTTPS enrollment is a separate acceptance lane.");

  test("keyboard entry preserves HTTPS administration denial and accessible recovery", async ({ page, context }) => {
    const data = fixture(), scope = data.projects.enabled;
    const csrf = await login(page, data.accounts.operator, route(scope));
    await expect(page.getByRole("heading", { name: "Runner health", exact: true })).toBeVisible();
    const caps = await context.request.get(`/api/v1/infra-automation/runner-capabilities?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`);
    expect(caps.status()).toBe(200);
    const capability = (await caps.json()).data;
    expect(capability.production_eligible).toBe(false);
    expect(capability.can_enroll).toBe(false);
    expect(capability.restriction).toBe("https_required");
    await expect(page.getByText(/HTTPS/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Issue enrollment", exact: true })).toHaveCount(0);
    expect((await context.request.get(`/api/v1/infra-automation/runners?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`)).status()).toBe(403);
    for (const path of ["enrollments", "unknown/rotate", "unknown/revoke"]) {
      const response = await context.request.post(`/api/v1/infra-automation/runners/${path}`, { headers: { Origin: origin, "X-CSRF-Token": csrf }, data: {} });
      expect(response.status()).toBe(403);
    }
    await page.getByRole("link", { name: "Runners", exact: true }).focus();
    await expect(page.getByRole("link", { name: "Runners", exact: true })).toHaveAttribute("aria-current", "page");
    await capture(page, "runners-http-unavailable");
  });

  test("disabled project and network loss keep consequential actions unavailable", async ({ page, context }) => {
    const data = fixture();
    await login(page, data.accounts.operator, route(data.projects.disabled));
    await expect(page.getByText(/InfraFlow execution is disabled/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Issue enrollment", exact: true })).toHaveCount(0);
    await capture(page, "runners-disabled");
    await context.setOffline(true);
    await expect(page.getByText(/Connection lost/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Refresh access", exact: true }).first()).toBeDisabled();
    await noRunnerSecrets(page);
    await context.setOffline(false);
  });

  test("reader cannot administer and an unassigned account cannot reveal scope details", async ({ page, context }) => {
    const data = fixture(), scope = data.projects.enabled;
    await login(page, data.accounts.viewer, route(scope));
    await expect(page.getByRole("button", { name: "Issue enrollment", exact: true })).toHaveCount(0);
    const caps = await context.request.get(`/api/v1/infra-automation/runner-capabilities?project_id=${scope.projectId}&workspace_id=${scope.workspaceId}`);
    expect(caps.status()).toBe(200);
    expect((await caps.json()).data.can_enroll).toBe(false);
    await capture(page, "runners-reader-unavailable");
    await context.clearCookies();
    await login(page, data.accounts.unassigned, route(scope));
    await expect(page.getByText(/unavailable for your account|No permitted projects/).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Runner health", exact: true })).toHaveCount(0);
    await noRunnerSecrets(page);
  });
});
