import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";

const runId = Date.now();
const projectKey = `phase-5-history-${runId}`;
const projectName = `Phase 5 History ${runId}`;
const uploadArtifact = path.join(process.cwd(), "samples/ui-demo-infra/analysis-artifacts/kubernetes/checkout-platform.yaml");

type ApiEnvelope<T> = { data: T };
type Project = { id: number; project_key: string; name: string; env_label: string };
type AnalysisRun = { persisted_report: { id: number } };
type ReportSummary = { id: number; severity: string; recommendation: string };

async function apiJson<T>(responsePromise: Promise<import("@playwright/test").APIResponse>): Promise<T> {
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as T;
}

async function ensureProject(request: APIRequestContext): Promise<Project> {
  const listed = await apiJson<ApiEnvelope<Project[]>>(request.get("/api/v1/projects"));
  const existing = listed.data.find((project) => project.project_key === projectKey);
  if (existing) {
    return existing;
  }

  const created = await apiJson<ApiEnvelope<Project>>(
    request.post("/api/v1/projects", {
      data: {
        project_key: projectKey,
        display_name: projectName,
        description: "Seeded history e2e project",
        default_branch: "main",
      },
    }),
  );
  return created.data;
}

async function seedReport(request: APIRequestContext, project: Project): Promise<ReportSummary> {
  const run = await apiJson<ApiEnvelope<AnalysisRun>>(
    request.post("/api/v1/analyses", {
      headers: {
        "X-DeployWhisper-Actor": "react_history_e2e",
        "X-DeployWhisper-Trigger-Type": "playwright_seed",
      },
      multipart: {
        project_id: String(project.id),
        artifact_paths: "checkout-platform.yaml",
        files: {
          name: "checkout-platform.yaml",
          mimeType: "application/x-yaml",
          buffer: fs.readFileSync(uploadArtifact),
        },
      },
    }),
  );
  const detail = await apiJson<ApiEnvelope<ReportSummary>>(request.get(`/api/v1/analyses/${run.data.persisted_report.id}`));
  return detail.data;
}

function severityTabName(value: string) {
  const normalized = value.toLowerCase();
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function recommendationTabName(value: string) {
  if (value === "no-go") {
    return "No-go";
  }
  if (value === "caution") {
    return "Caution";
  }
  return "Proceed";
}

async function selectProject(page: Page) {
  await page.goto("/app/history", { waitUntil: "networkidle" });
  await page.locator(".dw-project-trigger").click();
  await expect(page.getByRole("listbox", { name: "Projects" })).toBeVisible();
  await page.getByPlaceholder("Search projects...").fill(projectName);
  await page.getByRole("option", { name: new RegExp(projectName) }).click();
  await expect(page.getByRole("heading", { name: /Review prior verdicts/i })).toBeVisible();
}

async function maybeCapture(page: Page, width: number) {
  if (process.env.CAPTURE_HISTORY_SCREENSHOTS !== "1") {
    return;
  }
  await page.setViewportSize({ width, height: 1000 });
  await page.screenshot({
    fullPage: true,
    path: path.join(process.cwd(), `docs/design/phase-5-history-${width}.png`),
  });
}

test.describe("React history screen", () => {
  let seededReports: ReportSummary[] = [];

  test.beforeAll(async ({ request }) => {
    const project = await ensureProject(request);
    seededReports = [await seedReport(request, project), await seedReport(request, project)];
  });

  test("filters, expands, paginates, bulk-deletes, and passes axe", async ({ page }) => {
    await selectProject(page);

    await expect(page.getByText("Analysis runs")).toBeVisible();
    await expect(page.getByText(/matching reports/i)).toBeVisible();
    await expect(page.getByText("checkout-platform.yaml").first()).toBeVisible({ timeout: 120_000 });
    await expect(page.getByText(/risk vs #/i)).toBeVisible();

    await maybeCapture(page, 1440);
    await maybeCapture(page, 760);

    await page.getByLabel("Search analysis history").fill("checkout");
    await expect(page.getByText("checkout-platform.yaml").first()).toBeVisible();
    await page.getByRole("tab", { name: severityTabName(seededReports[0].severity) }).click();
    await expect(page.getByText(severityTabName(seededReports[0].severity)).first()).toBeVisible();
    await page.getByRole("tab", { name: recommendationTabName(seededReports[0].recommendation) }).click();
    await expect(page.getByText(recommendationTabName(seededReports[0].recommendation).toUpperCase()).first()).toBeVisible();

    await page.locator(".dw-history-row-trigger").first().click();
    await expect(page.getByText("Summary")).toBeVisible();
    await expect(page.getByRole("link", { name: /Open report/i })).toBeVisible();

    await page.getByLabel("Rows per page").selectOption("10");
    await expect(page.getByText(/Page 1/i)).toBeVisible();
    await page.keyboard.press("Home");
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();

    const accessibilityScanResults = await new AxeBuilder({ page }).include("main").analyze();
    const seriousOrCritical = accessibilityScanResults.violations.filter((violation) =>
      ["serious", "critical"].includes(violation.impact ?? ""),
    );
    expect(seriousOrCritical).toEqual([]);

    for (const reportId of seededReports.map((report) => report.id)) {
      await page.getByLabel(`Select report ${reportId}`).check();
    }
    await expect(page.getByText(`${seededReports.length} selected`)).toBeVisible();
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: /Delete selected/i }).click();
    await expect(page.getByText(`Deleted ${seededReports.length} analysis report(s).`)).toBeVisible();
  });
});
