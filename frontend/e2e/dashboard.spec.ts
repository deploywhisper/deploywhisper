import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";

const runId = Date.now();
const projectKey = `phase-3-dashboard-${runId}`;
const projectName = `Phase 3 Dashboard ${runId}`;
const uploadArtifact = path.join(process.cwd(), "samples/ui-demo-infra/analysis-artifacts/kubernetes/checkout-platform.yaml");

type ApiEnvelope<T> = { data: T };
type Project = { id: number; project_key: string; name: string; env_label: string };

async function apiJson<T>(request: APIRequestContext, url: string): Promise<T> {
  const response = await request.get(url);
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as T;
}

async function ensureProject(request: APIRequestContext): Promise<Project> {
  const list = await apiJson<ApiEnvelope<Project[]>>(request, "/api/v1/projects");
  const existing = list.data.find((project) => project.project_key === projectKey);
  if (existing) {
    return existing;
  }

  const created = await request.post("/api/v1/projects", {
    data: {
      project_key: projectKey,
      display_name: projectName,
      description: "Seeded dashboard e2e project",
      default_branch: "main",
    },
  });
  expect(created.ok()).toBeTruthy();
  return ((await created.json()) as ApiEnvelope<Project>).data;
}

async function selectProject(page: Page) {
  await page.goto("/app", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Run analysis/i }).waitFor({ state: "visible" });
  await page.locator(".dw-project-trigger").click();
  await expect(page.getByRole("listbox", { name: "Projects" })).toBeVisible();
  await page.getByPlaceholder("Search projects...").fill(projectName);
  await page.getByRole("option", { name: new RegExp(projectName) }).click();
}

test.describe("React dashboard", () => {
  let project: Project;

  test.beforeAll(async ({ request }) => {
    project = await ensureProject(request);
  });

  test("renders scoped KPIs and supports accessible keyboard navigation", async ({ page }) => {
    await selectProject(page);

    await expect(page.getByRole("heading", { name: /Good afternoon/i })).toBeVisible();
    await expect(page.getByText("Evidence Law enforced").first()).toBeVisible();
    await expect(page.getByText("Total analyses")).toBeVisible();
    await expect(page.getByText("0").first()).toBeVisible();
    await expect(page.getByText("Clean verdict rate")).toBeVisible();
    await expect(page.getByText("High / critical open")).toBeVisible();
    await expect(page.getByText("Avg time to verdict")).toBeVisible();
    await expect(page.getByText("No analyses yet. Run a new analysis to start the evidence trail.")).toBeVisible();

    await page.locator(".dw-project-trigger").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("listbox", { name: "Projects" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("listbox", { name: "Projects" })).toBeHidden();

    const accessibilityScanResults = await new AxeBuilder({ page }).include("main").analyze();
    const seriousOrCritical = accessibilityScanResults.violations.filter((violation) =>
      ["serious", "critical"].includes(violation.impact ?? ""),
    );
    expect(seriousOrCritical).toEqual([]);
  });

  test("uploads a sample artifact and navigates to the report URL", async ({ page }) => {
    await selectProject(page);

    await page.locator('input[type="file"]').setInputFiles(uploadArtifact);
    await expect(page.getByText("1 files staged")).toBeVisible();
    await page.getByRole("button", { name: /^Analyze$/ }).click();
    await expect(page).toHaveURL(/\/app\/reports\/\d+$/, { timeout: 120_000 });
    await expect(page.getByText("Briefing route ready")).toBeVisible();
  });
});
