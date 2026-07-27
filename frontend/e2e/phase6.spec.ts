import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";

const runId = Date.now();
const projectKey = `phase-6-${runId}`;
const projectName = `Phase 6 ${runId}`;
const deprecatedSkillId = `deprecated-phase6-${runId}`;

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

function formatSkillDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

function countLabel(count: number, singular: string) {
  return `${count} ${singular}${count === 1 ? "" : "s"}`;
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
    const skillResponse = await page.request.get("/api/v1/skills/terraform");
    expect(skillResponse.ok()).toBeTruthy();
    const skillPayload = await skillResponse.json() as {
      data: {
        trust_level: string;
        source: "built-in" | "custom-override" | "custom-new";
        contributors: string[];
        author: string;
        install_count: number;
        active_issue_count: number;
        updated_at: string;
        test_results: {
          status: "passing" | "failing" | "missing";
          display_text: string;
          pass_rate: number;
        } | null;
      };
    };
    const registrySkill = skillPayload.data;
    const trustLabel = `${registrySkill.trust_level.charAt(0).toUpperCase()}${registrySkill.trust_level.slice(1)} trust`;
    const sourceLabel = {
      "built-in": "Public registry",
      "custom-override": "Local override",
      "custom-new": "Private local",
    }[registrySkill.source];
    const testStatusLabel = registrySkill.test_results?.status === "passing"
      ? "Tests passing"
      : registrySkill.test_results?.status === "failing"
        ? "Tests failing"
        : "Tests missing";
    const passRateLabel = !registrySkill.test_results || registrySkill.test_results.status === "missing"
      ? "n/a"
      : `${Math.round(registrySkill.test_results.pass_rate * 100)}%`;
    const updatedDate = formatSkillDate(registrySkill.updated_at);

    await page.goto("/skills?search=terraform&sort=recency", { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "Skills" })).toBeVisible();
    const terraformSkill = page.locator('a[href="/skills/terraform"]');
    await expect(terraformSkill).toBeVisible();
    await expect(terraformSkill.getByText(trustLabel)).toBeVisible();
    await expect(terraformSkill.getByText(sourceLabel)).toBeVisible();
    await expect(terraformSkill.getByText(testStatusLabel)).toBeVisible();
    await expect(terraformSkill.getByLabel(countLabel(registrySkill.install_count, "install"))).toBeVisible();
    await expect(terraformSkill.getByLabel(countLabel(registrySkill.active_issue_count, "active issue"))).toBeVisible();
    await expect(
      terraformSkill.getByText(`${registrySkill.author} / Updated ${updatedDate}`, { exact: true }),
    ).toBeVisible();
    await expect(terraformSkill.getByLabel(`${passRateLabel} test pass rate`)).toBeVisible();
    await terraformSkill.click();
    await expect(page).toHaveURL(/\/skills\/terraform/);
    await expect(page.getByText(trustLabel)).toBeVisible();
    await expect(page.getByText(sourceLabel)).toBeVisible();
    await expect(page.getByText(testStatusLabel)).toBeVisible();
    await expect(page.getByText("Harness run")).toBeVisible();
    await expect(page.getByText("Analytics refreshed", { exact: false })).toBeVisible();
    await expect(page.getByText(countLabel(registrySkill.active_issue_count, "active issue"))).toBeVisible();
    await expect(page.getByText(`Updated ${updatedDate}`, { exact: true })).toBeVisible();
    if (registrySkill.test_results) {
      await expect(page.getByText(registrySkill.test_results.display_text)).toBeVisible();
    }
    const contributors = page.locator('section[aria-labelledby="skill-contributors-title"]');
    for (const contributor of registrySkill.contributors) {
      await expect(contributors.getByText(contributor, { exact: true })).toBeVisible();
    }
    await expect(page.getByText(/deploywhisper skill install terraform/)).toBeVisible();
    await expect(page.getByText("Version history")).toBeVisible();
    await expectNoSeriousA11y(page);
  });

  test("deprecated skill is clearly marked in catalog and detail routes", async ({ page }) => {
    const skillResponse = await page.request.get("/api/v1/skills/terraform");
    expect(skillResponse.ok()).toBeTruthy();
    const skillPayload = await skillResponse.json() as {
      data: Record<string, unknown>;
      meta: Record<string, unknown>;
    };
    const deprecatedSkillData = {
      ...skillPayload.data,
      id: deprecatedSkillId,
      name: "Deprecated Phase 6 Skill",
      trust_level: "deprecated",
      author: "Phase 6 Test",
      maintainer: "Phase 6 Test",
      is_official: false,
      is_featured: false,
      description: "Synthetic deprecated Skill for composed browser coverage.",
      install_count: 1,
      active_issue_count: 1,
      install_command: `deploywhisper skill install ${deprecatedSkillId}`,
    };
    const listPayload = {
      data: [deprecatedSkillData],
      meta: {
        ...skillPayload.meta,
        count: 1,
        total_count: 1,
        page: 1,
        page_size: 100,
        filters: {},
      },
    };

    await page.route("**/api/v1/skills?*", async (route) => {
      await route.fulfill({ contentType: "application/json", json: listPayload });
    });
    await page.route(`**/api/v1/skills/${deprecatedSkillId}/versions`, async (route) => {
      await route.fulfill({ contentType: "application/json", json: { data: [], meta: skillPayload.meta } });
    });
    await page.route(`**/api/v1/skills/${deprecatedSkillId}`, async (route) => {
      await route.fulfill({
        contentType: "application/json",
        json: { data: deprecatedSkillData, meta: skillPayload.meta },
      });
    });

    await page.goto(`/skills?search=${deprecatedSkillId}`, { waitUntil: "networkidle" });
    const deprecatedSkill = page.locator(`a[href="/skills/${deprecatedSkillId}"]`);
    await expect(deprecatedSkill).toBeVisible();
    await expect(deprecatedSkill.getByText("Deprecated trust", { exact: true })).toBeVisible();
    await expect(deprecatedSkill.getByText("This Skill is deprecated.", { exact: true })).toBeVisible();
    await expect(deprecatedSkill.getByLabel("1 install")).toBeVisible();
    await expect(deprecatedSkill.getByLabel("1 active issue")).toBeVisible();

    await deprecatedSkill.click();
    await expect(page).toHaveURL(new RegExp(`/skills/${deprecatedSkillId}$`));
    await expect(page.getByText("Deprecated trust", { exact: true })).toBeVisible();
    await expect(
      page.getByText("This Skill is deprecated and may no longer be maintained.", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("1 active issue", { exact: true })).toBeVisible();
    await expectNoSeriousA11y(page);
  });
});
