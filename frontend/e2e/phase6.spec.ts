import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";

const runId = Date.now();
const projectKey = `phase-6-${runId}`;
const projectName = `Phase 6 ${runId}`;

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
      description: "Seeded Phase 6 workspace",
      default_branch: "main",
    },
  });
  expect(created.ok()).toBeTruthy();
  return ((await created.json()) as ApiEnvelope<Project>).data;
}

async function seedPhase6(request: APIRequestContext, project: Project) {
  const topology = {
    services: [
      {
        id: "checkout-api",
        label: "Checkout API",
        resource_keys: ["Deployment/checkout-api"],
        downstream: [],
      },
    ],
  };
  const topologyResponse = await request.put("/api/v1/settings/topology", {
    data: { project_id: project.id, topology },
  });
  expect(topologyResponse.ok()).toBeTruthy();

  const incidentResponse = await request.post("/api/v1/incidents/reindex", {
    data: {
      project_id: project.id,
      files: [
        {
          source_file: "checkout-incident.json",
          content: JSON.stringify({
            title: "Checkout rollout incident",
            severity: "high",
            incident_date: "2026-05-20",
            root_cause: "Ingress drift.",
            trigger_change: "Deployment rollout.",
            affected_services: ["checkout-api"],
            rollback_path: "Restore the previous deployment revision.",
            prevention_notes: ["Review topology drift before deployment."],
            source: { system: "manual", reference: "INC-PHASE6" },
            redaction: { status: "redacted", contains_sensitive_data: false },
          }),
        },
      ],
    },
  });
  expect(incidentResponse.ok()).toBeTruthy();
}

async function selectProject(page: Page) {
  await page.locator(".dw-project-trigger").click();
  await page.getByPlaceholder("Search projects...").fill(projectName);
  await page.getByRole("option", { name: new RegExp(projectName) }).click();
}

async function expectNoSeriousA11y(page: Page) {
  const scan = await new AxeBuilder({ page }).include("main").analyze();
  const violations = scan.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""));
  expect(violations).toEqual([]);
}

test.describe("Phase 6 settings, incidents, and skills", () => {
  let project: Project;

  test.beforeAll(async ({ request }) => {
    project = await ensureProject(request);
    await seedPhase6(request, project);
  });

  test("settings renders provider, topology, feedback, and custom skills controls", async ({ page }) => {
    await page.goto("/settings", { waitUntil: "networkidle" });
    await selectProject(page);
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "AI provider" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Service context" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Reviewer feedback" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Custom AI skills" })).toBeVisible();

    const tempTopology = path.join(os.tmpdir(), `phase6-topology-${runId}.json`);
    fs.writeFileSync(tempTopology, JSON.stringify({ services: [] }), "utf-8");
    await page.locator('input[type="file"]').first().setInputFiles(tempTopology);
    await expect(page.getByText(/Topology validation passed|Topology validation failed/)).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await expectNoSeriousA11y(page);
  });

  test("incidents renders seeded source list and detail", async ({ page }) => {
    await page.goto("/incidents", { waitUntil: "networkidle" });
    await selectProject(page);
    await expect(page.getByRole("heading", { name: "Incidents" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Checkout rollout incident/ })).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: /Checkout rollout incident/ }).click();
    await expect(page.getByText("checkout-incident.json").first()).toBeVisible();
    await expectNoSeriousA11y(page);
  });

  test("skills supports filtering and detail navigation", async ({ page }) => {
    await page.goto("/skills?search=terraform&sort=recency", { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "Skills" })).toBeVisible();
    await expect(page.locator('a[href="/skills/terraform"]')).toBeVisible();
    await page.locator('a[href="/skills/terraform"]').click();
    await expect(page).toHaveURL(/\/skills\/terraform/);
    await expect(page.getByText(/deploywhisper skill install terraform/)).toBeVisible();
    await expect(page.getByText("Version history")).toBeVisible();
    await expectNoSeriousA11y(page);
  });
});
