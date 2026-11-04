import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { resolve } from "node:path";

// Credential wiring uses synthetic intercepted responses. Never record credentials.
test.use({ trace: "off", screenshot: "off", video: "off" });

test("normal Settings exposes local account configuration and consistent navigation", async ({ page, request }) => {
  const response = await request.get("/api/v1/auth/configuration");
  expect(response.ok()).toBeTruthy();
  const configuration = (await response.json()).data;
  expect(configuration.profile).toBe("disabled");
  for (const path of ["/", "/history", "/settings"]) {
    await page.goto(path);
    const links = page.getByRole("navigation", { name: "Primary" }).getByRole("link");
    await expect(links).toHaveText(["Dashboard", "Skills", /Incidents/, "History", "InfraFlow", "Settings"]);
  }
  const section = page.locator(".dw-settings-account");
  await expect(section.getByRole("heading", { name: "Local account", exact: true })).toBeVisible();
  await expect(section.getByText("disabled", { exact: true })).toBeVisible();
  await expect(section.getByRole("button", { name: "Sign in", exact: true })).toBeDisabled();
  await section.getByText("Operator setup for local accounts", { exact: true }).click();
  await expect(section.getByRole("button", { name: "Copy Compose configuration" })).toBeVisible();
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    const axe = await new AxeBuilder({ page }).include(".dw-settings-account").analyze();
    expect(axe.violations).toEqual([]);
    await page.screenshot({ path: resolve(`docs/verification/ui-project-actions/screenshots/settings-local-account-${width}.png`), fullPage: true });
  }
});

test("inline sign-in and sign-out work without a project or settings permission", async ({ page }) => {
  const csrf = "synthetic-ephemeral-csrf";
  let signedIn = false;
  let loginCount = 0;
  let logoutCount = 0;
  const principal = { principal_id: "synthetic-local-account", username: "synthetic-operator", principal_type: "human", is_admin: false, enabled: true, authentication_version: 1, credential_audience: "human", session_id: "synthetic-session", expires_at: new Date(Date.now() + 3_600_000).toISOString(), security_profile: "local-development", production_eligible: false };
  await page.route("**/api/v1/projects", (route) => route.fulfill({ json: { data: [], meta: {} } }));
  await page.route("**/api/v1/settings/summary**", (route) => route.fulfill({ status: 403, json: { error: { code: "permission_denied" } } }));
  await page.route("**/api/v1/auth/configuration", (route) => route.fulfill({ json: { data: { version: 1, profile: "local-development", configured_origin: "http://localhost:8080", configuration_valid: true, login_available: true, authorization_profile: "verified", decision_mode: "shared" }, meta: {} } }));
  await page.route("**/api/v1/auth/session", (route) => route.fulfill(signedIn ? { json: { data: principal, meta: {} } } : { status: 401, json: {} }));
  await page.route("**/api/v1/auth/login", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ username: "synthetic-operator", password: "synthetic-test-password-only" });
    loginCount++; signedIn = true;
    await route.fulfill({ json: { data: { principal, csrf_token: csrf }, meta: {} } });
  });
  await page.route("**/api/v1/auth/logout", async (route) => {
    expect(route.request().headers()["x-csrf-token"]).toBe(csrf);
    logoutCount++; signedIn = false;
    await route.fulfill({ json: { data: { logged_out: true }, meta: {} } });
  });
  await page.goto("/settings");
  const section = page.locator(".dw-settings-account");
  await expect(section.getByText("http://localhost:8080", { exact: true })).toBeVisible();
  await section.getByLabel("Username", { exact: true }).fill("synthetic-operator");
  await section.getByLabel("Password", { exact: true }).fill("synthetic-test-password-only");
  await section.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(section.getByText("synthetic-operator", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(section.getByLabel("Password", { exact: true })).toHaveCount(0);
  expect(loginCount).toBe(1);
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("synthetic-test-password-only");
  await section.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(section.getByLabel("Password", { exact: true })).toHaveValue("");
  expect(logoutCount).toBe(1);
});
