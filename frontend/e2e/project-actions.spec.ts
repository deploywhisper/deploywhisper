import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { resolve } from "node:path";

// Run only against the isolated normal Compose app with a disposable database.
// These tests create synthetic projects through the production UI/API.
const key = `project-actions-${Date.now()}`;
const name = `Project actions ${key}`;
const screenshots = resolve("docs/verification/ui-project-actions/screenshots");
async function capture(page: Page, surface: string) {
  for (const width of [1440, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    if (surface === "new-project-dialog") await expect(page.getByRole("dialog").getByRole("button", { name: "Create project", exact: true })).toBeVisible();
    await page.screenshot({ path: resolve(screenshots, `${surface}-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}
async function openForm(page: Page, search = "") {
  await page.locator(".dw-project-trigger").click();
  if (search) await page.getByPlaceholder("Search projects...").fill(search);
  await page.getByRole("button", { name: "New project", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "New project", exact: true });
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("listbox", { name: "Projects" })).toHaveCount(0);
  return dialog;
}

test("creates a real project, selects it, rejects duplicate safely and links setup", async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  const dialog = await openForm(page, name);
  await expect(dialog.getByLabel("Project name", { exact: true })).toHaveValue(name);
  await expect(dialog.getByLabel("Project name", { exact: true })).toBeFocused();
  await dialog.getByLabel("Project key", { exact: true }).fill(key);
  await dialog.getByLabel("Description (optional)").fill("Disposable UI project fixture");
  const results = await new AxeBuilder({ page }).include(".dw-project-dialog").analyze();
  expect(results.violations).toEqual([]);
  await capture(page, "new-project-dialog");
  await page.setViewportSize({ width: 760, height: 1000 });
  await expect(dialog.getByRole("button", { name: "Create project", exact: true })).toBeVisible();
  const response = page.waitForResponse((r) => r.url().endsWith("/api/v1/projects") && r.request().method() === "POST");
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();
  expect((await response).ok()).toBeTruthy();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator(".dw-project-trigger-name")).toHaveText(name);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const list = await request.get("/api/v1/projects");
  const project = (await list.json()).data.find((p: { project_key: string }) => p.project_key === key);
  expect(project).toBeTruthy();
  expect(await page.evaluate(() => localStorage.getItem("deploywhisper.selectedProjectId"))).toBe(String(project.id));
  for (const route of ["/", "/history", "/settings"]) {
    await page.goto(route);
    await expect(page.locator(".dw-project-trigger-name")).toHaveText(name);
    await page.reload();
    await expect(page.locator(".dw-project-trigger-name")).toHaveText(name);
  }
  await page.goto("/");
  await openForm(page);
  await dialog.getByLabel("Project name", { exact: true }).fill(name);
  await dialog.getByLabel("Project key", { exact: true }).fill(key);
  let posts = 0;
  page.on("request", (r) => { if (r.url().endsWith("/api/v1/projects") && r.method() === "POST") posts++; });
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();
  await expect(dialog.getByRole("alert")).toHaveText("Check the project key and name. The key may already be in use.");
  await expect(dialog.getByLabel("Project key", { exact: true })).toHaveValue(key);
  expect(posts).toBe(1);
  await page.keyboard.press("Escape");
  await expect(page.locator(".dw-project-trigger")).toBeFocused();
  await page.getByRole("link", { name: "Automation", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/infra-automation\\?project_id=${project.id}$`));
  await expect(page.getByText(/Sign in.*|Account access/i).first()).toBeVisible();
  await expect(page.getByText("Your application operator must configure named accounts and grant project access before you can use automation.")).toBeVisible();
  const setupAxe = await new AxeBuilder({ page }).include("main").analyze();
  expect(setupAxe.violations).toEqual([]);
  await capture(page, "automation-account-setup");
});

test("all production switchers support modal keyboard isolation and focus restore", async ({ page }) => {
  for (const route of ["/", "/history", "/settings"]) {
    await page.goto(route);
    const dialog = await openForm(page);
    await expect(dialog.getByLabel("Project name", { exact: true })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(dialog.getByRole("button", { name: "Cancel", exact: true })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(dialog.getByLabel("Project name", { exact: true })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(page.locator(".dw-project-trigger")).toBeFocused();
  }
});

test("lost creation response blocks replay until an explicit project reread", async ({ page }) => {
  let posts = 0;
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    posts++; await route.abort("failed");
  });
  await page.goto("/");
  const dialog = await openForm(page, `Uncertain ${Date.now()}`);
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Creation could not be confirmed");
  await expect(dialog.getByRole("button", { name: "Create project", exact: true })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "History", exact: true }).click();
  await openForm(page);
  await expect(dialog.getByRole("alert")).toContainText("Creation could not be confirmed");
  expect(posts).toBe(1);
  await dialog.getByRole("button", { name: "Refresh project list" }).click();
  await expect(dialog.getByRole("alert")).toContainText("not currently listed");
  expect(posts).toBe(1);
});


test("accepted response loss resolves by reread and allows a new project afterwards", async ({ page }) => {
  let posts = 0;
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    posts++;
    const result = await route.fetch();
    expect(result.ok()).toBeTruthy();
    await route.abort("failed");
  });
  await page.goto("/");
  const projectName = `Accepted synthetic ${Date.now()}`;
  const dialog = await openForm(page, projectName);
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Creation could not be confirmed");
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "History", exact: true }).click();
  await openForm(page);
  await expect(dialog.getByLabel("Project name", { exact: true })).toHaveValue(projectName);
  await dialog.getByRole("button", { name: "Refresh project list" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator(".dw-project-trigger-name")).toHaveText(projectName);
  await openForm(page, "Another synthetic project");
  await expect(dialog.getByLabel("Project name", { exact: true })).toHaveValue("Another synthetic project");
  await expect(dialog.getByRole("button", { name: "Create project", exact: true })).toBeEnabled();
  expect(posts).toBe(1);
});

test("pending creation survives route changes and closing never claims cancellation", async ({ page }) => {
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  let posts = 0;
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    posts++; await held; await route.abort("failed");
  });
  try {
    await page.goto("/");
    const dialog = await openForm(page, `Pending synthetic ${Date.now()}`);
    await dialog.getByRole("button", { name: "Create project", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("Closing this form does not cancel");
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await page.getByRole("link", { name: "History", exact: true }).click();
    await openForm(page);
    await expect(dialog.getByRole("button", { name: "Refresh project list" })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Create project", exact: true })).toHaveCount(0);
    release();
    await expect(dialog.getByRole("alert")).toContainText("Creation could not be confirmed");
    await dialog.getByRole("button", { name: "Refresh project list" }).click();
    await expect(dialog.getByRole("alert")).toContainText("not currently listed");
    expect(posts).toBe(1);
  } finally { release(); }
});

test("shared shell offers first-project creation with an empty authorized list", async ({ page }) => {
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "GET") await route.fulfill({ json: { data: [], meta: {} } });
    else await route.continue();
  });
  await page.goto("/settings");
  await expect(page.locator(".dw-project-trigger-name")).toHaveText("Select project");
  const dialog = await openForm(page, `First synthetic project ${Date.now()}`);
  await expect(dialog.getByRole("button", { name: "Create project", exact: true })).toBeEnabled();
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("not visible in your current project list");
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await openForm(page, "Another first project");
  await expect(dialog.getByRole("button", { name: "Create project", exact: true })).toBeEnabled();
  await expect(dialog.getByLabel("Project name", { exact: true })).toHaveValue("Another first project");
});


test("stalled project recovery times out without clearing uncertainty or replaying POST", async ({ page }) => {
  let posts = 0;
  let stallRead = false;
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "POST") { posts++; await route.abort("failed"); return; }
    if (!stallRead) { await route.continue(); return; }
    await held;
    await route.abort("failed").catch(() => {});
  });
  try {
    await page.goto("/");
    const projectName = `Stalled recovery ${Date.now()}`;
    const dialog = await openForm(page, projectName);
    await dialog.getByRole("button", { name: "Create project", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("Creation could not be confirmed");
    await page.clock.install();
    stallRead = true;
    await dialog.getByRole("button", { name: "Refresh project list" }).click();
    await expect(dialog.getByRole("button", { name: "Checking…", exact: true })).toBeDisabled();
    await page.clock.fastForward(15_001);
    await expect(dialog.getByRole("alert")).toContainText("The project list could not be refreshed");
    await expect(dialog.getByRole("button", { name: "Refresh project list" })).toBeEnabled();
    await expect(dialog.getByRole("button", { name: "Create project", exact: true })).toHaveCount(0);
    await expect(dialog.getByLabel("Project name", { exact: true })).toHaveValue(projectName);
    await page.keyboard.press("Escape");
    await page.getByRole("link", { name: "History", exact: true }).click();
    await openForm(page);
    await expect(dialog.getByRole("button", { name: "Refresh project list" })).toBeEnabled();
    await expect(dialog.getByRole("button", { name: "Create project", exact: true })).toHaveCount(0);
    expect(posts).toBe(1);
  } finally { release(); }
});
