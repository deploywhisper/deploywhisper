import { closeSync, constants, fstatSync, openSync, readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

// Explicit opt-in for the root-owned disposable local-development Compose proof.
// Credentials never enter screenshots, videos, traces or assertion messages.
test.use({ trace: "off", screenshot: "off", video: "off" });
const fixturePath = process.env.LOCAL_ACCOUNT_UI_FIXTURE;
test.skip(!fixturePath, "Requires the private disposable local-account fixture.");

function readAccount(): { username: string; password: string } {
  let descriptor: number | undefined;
  try {
    if (!fixturePath || process.env.BASE_URL !== "http://localhost:8080" || typeof process.getuid !== "function") throw new Error();
    descriptor = openSync(fixturePath, constants.O_RDONLY | constants.O_NOFOLLOW);
    const stat = fstatSync(descriptor);
    if (!stat.isFile() || stat.uid !== process.getuid() || (stat.mode & 0o777) !== 0o600 || stat.nlink !== 1 || stat.size < 1 || stat.size > 8192) throw new Error();
    const value: unknown = JSON.parse(readFileSync(descriptor, "utf8"));
    if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).sort().join(",") !== "password,username") throw new Error();
    const account = value as { username: unknown; password: unknown };
    if (typeof account.username !== "string" || !account.username.trim() || account.username.length > 128 || typeof account.password !== "string" || Buffer.byteLength(account.password, "utf8") < 15 || Buffer.byteLength(account.password, "utf8") > 1024) throw new Error();
    return { username: account.username, password: account.password };
  } catch {
    throw new Error("Disposable local account fixture is unavailable or invalid. No credential output was retained.");
  } finally { if (descriptor !== undefined) closeSync(descriptor); }
}

test("real configured local account sign-in and sign-out", async ({ page, request }) => {
  const account = readAccount();
  const configurationResponse = await request.get("/api/v1/auth/configuration");
  expect(configurationResponse.ok()).toBe(true);
  const configuration = (await configurationResponse.json()).data;
  expect(configuration).toMatchObject({ version: 1, profile: "local-development", configured_origin: "http://localhost:8080", configuration_valid: true, login_available: true });
  await page.goto("/settings");
  const section = page.locator(".dw-settings-account");
  await expect(section.getByText("local-development", { exact: true })).toBeVisible();
  await expect(section.getByText("http://localhost:8080", { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("link")).toHaveText(["Dashboard", "Skills", /Incidents/, "History", "Automation", "Settings"]);
  try {
    await section.getByLabel("Username", { exact: true }).focus();
    await page.keyboard.insertText(account.username);
    await section.getByLabel("Password", { exact: true }).focus();
    await page.keyboard.insertText(account.password);
    const login = page.waitForResponse((response) => response.url().endsWith("/api/v1/auth/login") && response.request().method() === "POST");
    await section.getByRole("button", { name: "Sign in", exact: true }).click();
    if (!(await login).ok()) throw new Error();
    await expect(section.locator("p").filter({ hasText: "Signed in as" })).toBeVisible();
    await expect(page).toHaveURL(/\/settings$/);
    expect(await page.locator("#account-password").count()).toBe(0);
    const logout = page.waitForResponse((response) => response.url().endsWith("/api/v1/auth/logout") && response.request().method() === "POST");
    await section.getByRole("button", { name: "Sign out", exact: true }).click();
    if (!(await logout).ok()) throw new Error();
    await expect(section.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
    expect(await page.locator("#account-password").evaluate((input: HTMLInputElement) => input.value.length === 0)).toBe(true);
  } catch {
    // Suppress Playwright action logs/assertion bodies that could retain input.
    throw new Error("Disposable local account sign-in/sign-out proof failed. No credential output was retained.");
  }
  await page.goto("/settings/account");
  await expect(page.getByRole("heading", { name: "Account access", exact: true })).toBeVisible();
  await expect(page.locator(".dw-settings-account").getByText("local-development", { exact: true })).toBeVisible();
  await expect(page.locator("#account-password")).toHaveValue("");
});
