import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, mkdirSync, openSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const origin = "https://localhost:18443";
const fixturePath = process.env.RUNNER_FAULT_FIXTURE;
const resultPath = process.env.RUNNER_FAULT_RESULT;
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";
test.use({ ignoreHTTPSErrors: true, trace: "off", screenshot: "off", video: "off" });

for (const kind of ["wire-lease-expiry", "running-revocation", "log-cap"]) {
  test(`actual runner fault ${kind} remains accurate in browser`, async ({ page, context }) => {
    test.skip(!fixturePath || !resultPath, "Requires the actual TLS runner fault record");
    if (process.env.BASE_URL !== origin || !process.env.RUNNER_FAULT_CONTAINER) throw new Error("Exact disposable fault target required");
    const container = JSON.parse(execFileSync("docker", ["inspect", process.env.RUNNER_FAULT_CONTAINER], { encoding: "utf8" }))[0];
    if (container.Config.Labels?.["com.docker.compose.project"] !== "deploywhisper-s1619-runner-faults" || container.Config.User !== "appuser" || !container.State.Running) throw new Error("Owned disposable fault target required");
    const fd = openSync(fixturePath!, constants.O_RDONLY | constants.O_NOFOLLOW);
    let account: { username: string; password: string; origin: string };
    try {
      const info = fstatSync(fd);
      if (!info.isFile() || info.uid !== process.getuid?.() || (info.mode & 0o777) !== 0o600 || info.nlink !== 1 || info.size > 65536) throw new Error("Private fixture required");
      account = JSON.parse(readFileSync(fd, "utf8"));
    } finally { closeSync(fd); }
    if (account.origin !== origin) throw new Error("Fixture origin mismatch");
    const proof = JSON.parse(readFileSync(resultPath!, "utf8"));
    expect(proof.qualified).toBe(true);
    expect(proof.full_corpus).toBe(true);
    const item = proof.cases.find((entry: { case: string }) => entry.case === kind);
    expect(item.containers_removed).toBe(true);
    if (kind === "running-revocation") expect(item.revoked_after_tool_started).toBe(true);
    const route = `/infra-automation/runs/${item.run_id}?project_id=${item.project_id}&workspace_id=${item.workspace_id}`;
    await page.goto(`/settings/account?returnTo=${encodeURIComponent(route)}`);
    await page.getByLabel("Username", { exact: true }).fill(account.username);
    await page.getByLabel("Password", { exact: true }).fill(account.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(origin + route);
    const response = await context.request.get(`/api/v1/infra-automation/runs/${item.run_id}`);
    expect(response.status()).toBe(200);
    expect((await response.json()).data.state).toBe(item.run_state);
    await expect(page.getByText("Not independently confirmed by this view", { exact: true })).toBeVisible();
    await expect(page.getByText("No external acceptance reported by this view", { exact: true })).toBeVisible();
    if (kind !== "log-cap") {
      expect(item.report_count).toBe(0);
      await expect(page.getByRole("link", { name: /Open permanent briefing/ })).toHaveCount(0);
    } else {
      expect(item.quota_status).toBe(429);
      expect(item.log_page.cursor.truncated).toBe(true);
      expect(item.log_page.cursor.gap).toBe(false);
      const logs = page.getByRole("button", { name: /View screened logs for attempt 1 \(collect\)/ });
      await logs.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByText("Log output is truncated; this page does not represent the complete output.", { exact: true })).toBeVisible();
      await expect(page.getByText("Gap reported in the retained log sequence.", { exact: true })).toHaveCount(0);
      await expect(logs).toBeFocused();
      await page.getByRole("button", { name: "Next log page", exact: true }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByText(`Last sequence: ${item.log_page.cursor.last_sequence}`, { exact: true })).toHaveCount(0);
      await expect(page.getByText("Gap reported in the retained log sequence.", { exact: true })).toHaveCount(0);
    }
    const output = resolve("docs/verification/infra-automation/16-19/prerequisite-profiles/runner-faults/screenshots");
    mkdirSync(output, { recursive: true });
    for (const width of [1440, 760]) {
      await page.setViewportSize({ width, height: 1000 });
      if (kind === "log-cap") await page.getByText("Log output is truncated; this page does not represent the complete output.", { exact: true }).scrollIntoViewIfNeeded();
      const result = await new AxeBuilder({ page }).analyze();
      expect(result.violations.filter(v => v.impact === "critical" || v.impact === "serious").map(v => v.id)).toEqual([]);
      await page.screenshot({ path: resolve(output, `${kind}-${width}.png`), fullPage: false });
    }
  });
}
