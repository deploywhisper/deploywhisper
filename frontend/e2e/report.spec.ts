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
type ContextSource = {
  source_id: string;
  source_type: string;
  source_ref?: string | null;
  scope: string;
  freshness_status: string;
  last_observed_at?: string | null;
  age_days?: number | null;
  confidence: number;
  conflicts?: string[];
  limitations?: string[];
};
type ReportDetail = {
  id: number;
  findings: { finding_id: string; title: string }[];
  context_completeness?: { context_sources?: ContextSource[] };
  evidence_items?: { context_source?: ContextSource | null }[];
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

function multipartBody(parts: { name: string; value: string }[], files: { name: string; filename: string; mimeType: string; buffer: Buffer }[]) {
  const boundary = `----deploywhisper-${runId}`;
  const chunks: Buffer[] = [];
  const pushText = (value: string) => chunks.push(Buffer.from(value, "utf-8"));

  for (const part of parts) {
    pushText(`--${boundary}\r\n`);
    pushText(`Content-Disposition: form-data; name="${part.name}"\r\n\r\n`);
    pushText(`${part.value}\r\n`);
  }
  for (const file of files) {
    pushText(`--${boundary}\r\n`);
    pushText(
      `Content-Disposition: form-data; name="${file.name}"; filename="${file.filename}"\r\n`,
    );
    pushText(`Content-Type: ${file.mimeType}\r\n\r\n`);
    chunks.push(file.buffer);
    pushText("\r\n");
  }
  pushText(`--${boundary}--\r\n`);
  return { boundary, body: Buffer.concat(chunks) };
}

async function seedReport(request: APIRequestContext, project: Project): Promise<ReportDetail> {
  const uploadBuffer = fs.readFileSync(uploadArtifact);
  const shadowUploadBuffer = Buffer.from(
    uploadBuffer
      .toString("utf-8")
      .replaceAll("checkout-api", "checkout-api-shadow")
      .replaceAll("checkout-web", "checkout-web-shadow")
      .replaceAll("payments-worker", "payments-worker-shadow"),
    "utf-8",
  );
  const { boundary, body } = multipartBody(
    [
      { name: "project_id", value: String(project.id) },
      { name: "artifact_paths", value: "checkout-platform.yaml" },
      { name: "artifact_paths", value: "checkout-platform-shadow.yaml" },
    ],
    [
      {
        name: "files",
        filename: "checkout-platform.yaml",
        mimeType: "application/x-yaml",
        buffer: uploadBuffer,
      },
      {
        name: "files",
        filename: "checkout-platform-shadow.yaml",
        mimeType: "application/x-yaml",
        buffer: shadowUploadBuffer,
      },
    ],
  );
  const run = await apiJson<ApiEnvelope<AnalysisRun>>(
    request.post("/api/v1/analyses", {
      headers: {
        "X-DeployWhisper-Actor": "react_report_e2e",
        "X-DeployWhisper-Trigger-Type": "playwright_seed",
        "Content-Type": `multipart/form-data; boundary=${boundary}`,
      },
      data: body,
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

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function contextSourceRow(page: Page, source: ContextSource) {
  const identity = contextSourceIdentity(source);
  return page
    .locator(`[data-testid="context-source-row"][data-context-source-identity="${identity}"]`);
}

function contextSourceIdentity(source: ContextSource) {
  const notes = [
    ...new Set([...(source.conflicts ?? []), ...(source.limitations ?? [])]),
  ].sort();
  return encodeURIComponent(JSON.stringify([
    source.source_id,
    source.source_type,
    source.source_ref ?? "",
    source.scope,
    source.freshness_status,
    source.confidence ?? "",
    source.last_observed_at ?? "",
    source.age_days ?? "",
    notes,
  ]));
}

function distinctContextSources(sources: ContextSource[]) {
  const seen = new Set<string>();
  return sources.filter((source) => {
    const identity = contextSourceIdentity(source);
    if (seen.has(identity)) {
      return false;
    }
    seen.add(identity);
    return true;
  });
}

async function expectContextSourceRow(page: Page, source: ContextSource) {
  const row = contextSourceRow(page, source);
  await expect(row).toHaveCount(1);
  await expect(row.getByText(source.source_type, { exact: true })).toBeVisible();
  await expect(row.getByText(source.source_id, { exact: true })).toBeVisible();
  await expect(
    row.getByText(source.source_ref || "source reference unavailable", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(row.getByText(source.scope)).toBeVisible();
  await expect(
    row.getByText(
      new RegExp(
        `${escapeRegExp(source.freshness_status)}\\s*-\\s*${Math.round(
          (source.confidence ?? 0) * 100,
        )}%\\s*-\\s*${escapeRegExp(source.scope)}`,
      ),
    ),
  ).toBeVisible();
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

    const contextSources = report.context_completeness?.context_sources ?? [];
    const distinctSources = distinctContextSources(contextSources);
    expect(distinctSources.length).toBeGreaterThan(1);
    const contextSource = distinctSources[0];
    const secondContextSource = distinctSources[1];

    await clickTab(page, "Context");
    await expect(page.getByText("CONTEXT SOURCES")).toBeVisible();
    await expectContextSourceRow(page, contextSource);
    await expectContextSourceRow(page, secondContextSource);
    const notedContextSource = contextSources.find(
      (source) =>
        (source.conflicts?.length ?? 0) > 0 ||
        (source.limitations?.length ?? 0) > 0,
    );
    const contextNote = notedContextSource
      ? [...(notedContextSource.conflicts ?? []), ...(notedContextSource.limitations ?? [])][0]
      : null;
    if (notedContextSource && contextNote) {
      const notedRow = contextSourceRow(page, notedContextSource);
      await expect(notedRow).toHaveCount(1);
      await expect(notedRow.getByText(notedContextSource.source_id)).toBeVisible();
      await expect(notedRow.getByText(contextNote, { exact: true })).toBeVisible();
    }

    await clickTab(page, "Confidence");
    const evidenceContextSources =
      report.evidence_items
        ?.map((item) => item.context_source)
        .filter((source): source is ContextSource => Boolean(source)) ?? [];
    const distinctEvidenceContextSources = distinctContextSources(evidenceContextSources);
    expect(distinctEvidenceContextSources.length).toBeGreaterThan(1);
    for (const source of distinctEvidenceContextSources.slice(0, 2)) {
      expect(source.scope).toBeTruthy();
      expect(source.confidence).toBeGreaterThanOrEqual(0);
      expect(source.confidence).toBeLessThanOrEqual(1);
      await expect(
        page.getByText(
          new RegExp(
            `${escapeRegExp(source.source_id)}\\s*\\(${escapeRegExp(
              source.freshness_status,
            )}\\)`,
          ),
        ).first(),
      ).toBeVisible();
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
