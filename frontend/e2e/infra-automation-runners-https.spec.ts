import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, mkdirSync, openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const fixturePath = process.env.RUNNER_HTTPS_FIXTURE;
const origin = process.env.RUNNER_HTTPS_ORIGIN ?? "https://localhost:8443";
if (!["https://localhost:8443", "https://localhost:18443"].includes(origin)) throw new Error("Unsupported TLS test origin");
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";
test.setTimeout(60_000);
test.use({ ignoreHTTPSErrors: true, trace: "off", screenshot: "off", video: "off" });

test("actual TLS administration enrolls, polls, rotates and revokes without retaining secrets", async ({ page, context }) => {
  test.skip(!fixturePath, "Requires an owned disposable TLS fixture");
  if (process.env.BASE_URL !== origin || !process.env.RUNNER_HTTPS_CONTAINER) throw new Error("Exact disposable TLS target required");
  const container = JSON.parse(execFileSync("docker", ["inspect", process.env.RUNNER_HTTPS_CONTAINER], { encoding: "utf8" }))[0];
  if (container.Config.Labels?.["com.docker.compose.project"] !== (process.env.RUNNER_HTTPS_PROJECT ?? "deploywhisper-story16-19-https") || container.Config.User !== "appuser" || !container.State.Running) throw new Error("Disposable TLS container required");
  const fd = openSync(fixturePath!, constants.O_RDONLY | constants.O_NOFOLLOW);
  let data: { username: string; password: string; origin: string; project_id: number; workspace_id: number };
  try {
    const stat = fstatSync(fd);
    if (!stat.isFile() || stat.uid !== process.getuid?.() || (stat.mode & 0o777) !== 0o600 || stat.nlink !== 1 || stat.size > 65536) throw new Error("Private fixture required");
    data = JSON.parse(readFileSync(fd, "utf8"));
  } finally { closeSync(fd); }
  if (data.origin !== origin) throw new Error("Fixture origin mismatch");
  const route = `/infra-automation/runners?project_id=${data.project_id}&workspace_id=${data.workspace_id}`;
  console.info("TLS stage: login");
  await page.goto(`/settings/account?returnTo=${encodeURIComponent(route)}`);
  await page.getByLabel("Username", { exact: true }).fill(data.username);
  await page.getByLabel("Password", { exact: true }).fill(data.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(origin + route);
  console.info("TLS stage: capabilities");
  const caps = await context.request.get(`/api/v1/infra-automation/runner-capabilities?project_id=${data.project_id}&workspace_id=${data.workspace_id}`);
  expect(caps.status()).toBe(200);
  expect((await caps.json()).data.production_eligible).toBe(true);
  await page.getByLabel("Administration reason").fill("Synthetic HTTPS administration qualification");
  console.info("TLS stage: enrollment");
  await expect(page.getByRole("button", { name: "Issue enrollment", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Issue enrollment", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("One-time enrollment token", { exact: true })).toBeVisible();
  const token = await page.getByLabel("One-time enrollment token", { exact: true }).inputValue();
  const enrollment = JSON.parse(await page.getByLabel("Enrollment JSON").inputValue());
  console.info("TLS stage: redeem");
  const redeem = await context.request.post(`/api/v1/infra-automation/runners/enrollments/${enrollment.enrollment_id}/redeem`, { headers: { authorization: `Bearer ${token}` }, data: enrollment });
  expect(redeem.status()).toBe(200);
  const credential = (await redeem.json()).data;
  const poll = await context.request.get(`/api/v1/infra-automation/runners/${credential.runner_id}/tasks`, { headers: { authorization: `Bearer ${credential.token}` } });
  expect(poll.status()).toBe(200);
  await page.getByRole("button", { name: "Close and clear secret" }).click();
  await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0);
  console.info("TLS stage: health");
  await page.getByRole("button", { name: "Refresh runner health", exact: true }).click();
  await expect(page.getByRole("row").filter({ hasText: credential.runner_id }).getByText("online", { exact: true })).toBeVisible();
  await context.setOffline(true);
  await page.getByRole("button", { name: "Refresh runner health", exact: true }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByRole("button", { name: `Rotate credential for ${credential.runner_id}`, exact: true })).toHaveCount(0);
  await context.setOffline(false);
  await page.getByRole("button", { name: "Refresh runner health", exact: true }).click();
  await expect(page.getByLabel("Administration reason")).toBeEnabled();
  await page.getByLabel("Administration reason").fill("Rotate synthetic HTTPS runner");
  await page.getByRole("button", { name: `Rotate credential for ${credential.runner_id}`, exact: true }).click();
  await expect(page.getByLabel("One-time runner credential", { exact: true })).toBeVisible();
  const rotated = await page.getByLabel("One-time runner credential", { exact: true }).inputValue();
  const oldPoll = await context.request.get(`/api/v1/infra-automation/runners/${credential.runner_id}/tasks`, { headers: { authorization: `Bearer ${credential.token}` } });
  expect(oldPoll.status()).toBe(401);
  const newPoll = await context.request.get(`/api/v1/infra-automation/runners/${credential.runner_id}/tasks`, { headers: { authorization: `Bearer ${rotated}` } });
  expect(newPoll.status()).toBe(200);
  await page.getByRole("button", { name: "Close and clear secret" }).click();
  await page.getByLabel("Administration reason").fill("Revoke synthetic HTTPS runner");
  await page.getByRole("button", { name: `Revoke runner ${credential.runner_id}`, exact: true }).click();
  await expect(page.getByText(`Revocation confirmed for ${credential.runner_id}.`, { exact: true })).toBeVisible();
  const revokedPoll = await context.request.get(`/api/v1/infra-automation/runners/${credential.runner_id}/tasks`, { headers: { authorization: `Bearer ${rotated}` } });
  expect(revokedPoll.status()).toBe(401);
  expect(await page.evaluate(() => [document.body.innerText, location.href, ...Object.values(localStorage), ...Object.values(sessionStorage)].every(value => !/enroll-v1-|runner-v1-/.test(value)))).toBe(true);
  const shots = resolve("docs/verification/infra-automation/16-19/prerequisite-profiles/https/screenshots");
  mkdirSync(shots, { recursive: true });
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    const axe = await new AxeBuilder({ page }).analyze();
    expect(axe.violations.filter(v => v.impact === "critical" || v.impact === "serious").map(v => v.id)).toEqual([]);
    await page.screenshot({ path: resolve(shots, `revoked-${width}.png`), fullPage: true });
  }
});

test("actual isolated TLS collection opens its same permanent briefing", async ({ page }) => {
  test.skip(!fixturePath || !process.env.RUNNER_HTTPS_COLLECTION_RESULT, "Requires actual same-task TLS collector result");
  const fd = openSync(fixturePath!, constants.O_RDONLY | constants.O_NOFOLLOW);
  let credentials: { username: string; password: string; origin: string };
  try {
    const metadata = fstatSync(fd);
    if (!metadata.isFile() || metadata.uid !== process.getuid?.() || (metadata.mode & 0o777) !== 0o600 || metadata.nlink !== 1) throw new Error("Private fixture required");
    credentials = JSON.parse(readFileSync(fd, "utf8"));
  } finally { closeSync(fd); }
  if (process.env.BASE_URL !== origin || credentials.origin !== origin) throw new Error("Exact TLS origin required");
  const proof = JSON.parse(readFileSync(process.env.RUNNER_HTTPS_COLLECTION_RESULT!, "utf8"));
  const run = proof.runs[0];
  expect(run.actual_tls && run.default_runner_transport && run.state === "succeeded").toBe(true);
  const route = `/infra-automation/runs/${run.run_id}?project_id=${run.project_id}&workspace_id=${run.workspace_id}`;
  await page.goto(`/settings/account?returnTo=${encodeURIComponent(route)}`);
  await page.getByLabel("Username", { exact: true }).fill(credentials.username);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(origin + route);
  const reportLink = page.getByRole("link", { name: `Open permanent briefing #${run.report_id}`, exact: true });
  await expect(reportLink).toBeVisible();
  const shots = resolve("docs/verification/infra-automation/16-19/prerequisite-profiles/https/screenshots");
  mkdirSync(shots, { recursive: true });
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    const result = await new AxeBuilder({ page }).analyze();
    expect(result.violations.filter(v => v.impact === "critical" || v.impact === "serious").map(v => v.id)).toEqual([]);
    await page.screenshot({ path: resolve(shots, `real-collection-${width}.png`), fullPage: true });
  }
  await reportLink.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/reports/${run.report_id}\\?`));
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect(page.getByRole("main")).toBeVisible();
    const result = await new AxeBuilder({ page }).analyze();
    expect(result.violations.filter(v => v.impact === "critical" || v.impact === "serious").map(v => v.id)).toEqual([]);
    await page.screenshot({ path: resolve(shots, `real-report-${width}.png`), fullPage: true });
  }
});

test("actual enrollment expiry clears the one-time reveal and denies redemption", async ({ page, context }) => {
  test.setTimeout(90_000);
  test.skip(!fixturePath, "Requires short-lived disposable TLS credentials");
  const fd = openSync(fixturePath!, constants.O_RDONLY | constants.O_NOFOLLOW);
  let credentials: { username: string; password: string; origin: string; project_id: number; workspace_id: number };
  try {
    const metadata = fstatSync(fd);
    if (!metadata.isFile() || metadata.uid !== process.getuid?.() || (metadata.mode & 0o777) !== 0o600 || metadata.nlink !== 1) throw new Error("Private fixture required");
    credentials = JSON.parse(readFileSync(fd, "utf8"));
  } finally { closeSync(fd); }
  if (process.env.BASE_URL !== origin || credentials.origin !== origin) throw new Error("Exact TLS origin required");
  const route = `/infra-automation/runners?project_id=${credentials.project_id}&workspace_id=${credentials.workspace_id}`;
  await page.goto(`/settings/account?returnTo=${encodeURIComponent(route)}`);
  await page.getByLabel("Username", { exact: true }).fill(credentials.username);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(origin + route);
  await page.getByLabel("Administration reason").fill("Verify real one-time enrollment expiry");
  await page.getByRole("button", { name: "Issue enrollment", exact: true }).click();
  await expect(page.getByLabel("One-time enrollment token", { exact: true })).toBeVisible();
  const token = await page.getByLabel("One-time enrollment token", { exact: true }).inputValue();
  const enrollment = JSON.parse(await page.getByLabel("Enrollment JSON").inputValue());
  const remaining = Date.parse(enrollment.expires_at) - Date.now();
  expect(remaining > 0 && remaining <= 65_000).toBe(true);
  await expect(page.getByLabel("One-time enrollment token", { exact: true })).toHaveCount(0, { timeout: 70_000 });
  const rejected = await context.request.post(`/api/v1/infra-automation/runners/enrollments/${enrollment.enrollment_id}/redeem`, { headers: { authorization: `Bearer ${token}` }, data: enrollment });
  expect(rejected.status()).toBe(401);
  expect(await page.evaluate(() => [document.body.innerText, location.href, ...Object.values(localStorage), ...Object.values(sessionStorage)].every(value => !/enroll-v1-|runner-v1-/.test(value)))).toBe(true);
  const shots = resolve("docs/verification/infra-automation/16-19/prerequisite-profiles/https/screenshots");
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    const result = await new AxeBuilder({ page }).analyze();
    expect(result.violations.filter(v => v.impact === "critical" || v.impact === "serious").map(v => v.id)).toEqual([]);
    await page.screenshot({ path: resolve(shots, `expired-${width}.png`), fullPage: true });
  }
});
