import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";

const runId = Date.now();
const projectKey = `phase-4-report-${runId}`;
const projectName = `Phase 4 Report ${runId}`;
const uploadArtifact = path.join(process.cwd(), "samples/ui-demo-infra/analysis-artifacts/kubernetes/checkout-platform.yaml");
const sharePassword = "review-only";
const shareToken = process.env.DEPLOYWHISPER_SHARE_TOKEN ?? "DEPLOYWHISPER_API_TOKEN-for-test-123";

type ApiEnvelope<T> = { data: T };
type Project = { id: number; project_key: string; name: string; env_label: string };
type AnalysisRun = { persisted_report: { id: number } };
type ReportDetail = {
  id: number;
  findings: { finding_id: string; title: string }[];
  feedback_state: { finding_feedback: Record<string, { outcome_label: string }> };
};

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
        description: "Seeded report e2e project",
        default_branch: "main",
      },
    }),
  );
  return created.data;
}

async function seedReport(request: APIRequestContext, project: Project): Promise<ReportDetail> {
  const run = await apiJson<ApiEnvelope<AnalysisRun>>(
    request.post("/api/v1/analyses", {
      headers: {
        "X-DeployWhisper-Actor": "react_report_e2e",
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

  const report = await apiJson<ApiEnvelope<ReportDetail>>(request.get(`/api/v1/analyses/${run.data.persisted_report.id}`));
  expect(report.data.findings.length).toBeGreaterThan(0);
  return report.data;
}

async function configureProtectedShare(request: APIRequestContext, reportId: number) {
  await apiJson<ApiEnvelope<unknown>>(
    request.post(`/api/v1/analyses/${reportId}/share`, {
      headers: { "X-DeployWhisper-Share-Token": shareToken },
      data: { password: sharePassword, redact_filenames: true },
    }),
  );
}

async function openReport(page: Page, reportId: number) {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async () => undefined,
      },
    });
  });
  await page.goto(`/reports/${reportId}?private=1`, { waitUntil: "networkidle" });
  await expect(page.getByRole("heading").first()).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  await expect(page.getByRole("img", { name: "DeployWhisper" })).toBeVisible();
  await expect(page.getByLabel("Global search")).toBeVisible();
}

async function clickTab(page: Page, name: string) {
  await page.getByRole("tab", { name: new RegExp(name, "i") }).click();
  await expect(page.getByRole("tabpanel")).toBeVisible();
}

async function maybeCapture(page: Page, name: string, width: number) {
  if (process.env.CAPTURE_REPORT_SCREENSHOTS !== "1") {
    return;
  }
  await page.setViewportSize({ width, height: 1100 });
  await page.screenshot({
    fullPage: true,
    path: path.join(process.cwd(), `docs/design/phase-4-report-${name}-${width}.png`),
  });
}

test.describe("React report screen", () => {
  let report: ReportDetail;

  test.beforeAll(async ({ request }) => {
    const project = await ensureProject(request);
    report = await seedReport(request, project);
    await configureProtectedShare(request, report.id);
  });

  test("walks tabs, expands findings, persists feedback, copies briefing, and passes axe", async ({ page, request }) => {
    await openReport(page, report.id);

    await maybeCapture(page, "overview", 1440);
    for (const tabName of ["Findings", "Confidence", "Context", "Rollback", "Audit"]) {
      await clickTab(page, tabName);
      await maybeCapture(page, tabName.toLowerCase(), 1440);
    }

    await clickTab(page, "Findings");
    const finding = report.findings[0];
    const findingButton = page.getByRole("button", { name: new RegExp(finding.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i") }).first();
    await expect(findingButton).toHaveAttribute("aria-expanded", "true");
    await findingButton.click();
    await expect(findingButton).toHaveAttribute("aria-expanded", "false");
    await findingButton.click();
    await expect(findingButton).toHaveAttribute("aria-expanded", "true");

    await page.getByRole("button", { name: "Useful" }).click();
    await expect(page.getByText("Feedback saved.")).toBeVisible();
    const detail = await apiJson<ApiEnvelope<ReportDetail>>(request.get(`/api/v1/analyses/${report.id}`));
    expect(detail.data.feedback_state.finding_feedback[finding.finding_id]?.outcome_label).toBe("useful");

    await page.getByRole("button", { name: /Copy briefing/i }).click();
    await expect(page.getByText("Briefing copied.")).toBeVisible();

    await page.keyboard.press("Home");
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();

    const accessibilityScanResults = await new AxeBuilder({ page }).include("main").analyze();
    const seriousOrCritical = accessibilityScanResults.violations.filter((violation) =>
      ["serious", "critical"].includes(violation.impact ?? ""),
    );
    expect(seriousOrCritical).toEqual([]);

    await clickTab(page, "Overview");
    await maybeCapture(page, "overview", 760);
    await clickTab(page, "Findings");
    await maybeCapture(page, "findings", 760);
  });

  test("respects the password-protected public shared-report flow", async ({ page }) => {
    await page.goto(`/reports/${report.id}?compare=previous`, { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "Password required" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Copy briefing/i })).toHaveCount(0);

    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Open shared report" }).click();
    await expect(page.getByRole("alert")).toContainText("Incorrect password");

    await page.getByLabel("Password").fill(sharePassword);
    await page.getByRole("button", { name: "Open shared report" }).click();
    await expect(page.getByRole("heading").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Copy briefing/i })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /Compare/i })).toBeVisible();
  });
});
