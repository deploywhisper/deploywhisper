const { test, expect } = require("@playwright/test");

test.describe("live project selector", () => {
  test("can create and activate a project from the top search selector", async ({
    page,
  }) => {
    const suffix = Date.now().toString().slice(-6);
    const projectKey = `payments-live-${suffix}`;
    const projectName = `Payments Live ${suffix}`;
    const repositorySlug = `acme/payments-live-${suffix}`;

    await page.goto("/");

    await page.getByRole("button", { name: "New project" }).click();
    await page.getByLabel("Project key").fill(projectKey);
    await page.getByLabel("Display name").fill(projectName);
    await page
      .getByLabel("Repository URL")
      .fill(`https://github.com/${repositorySlug}.git`);
    await page
      .locator('[aria-label="Create project workspace"]')
      .getByRole("button", { name: "Create project" })
      .click();

    const topSearch = page.getByPlaceholder("Search repo or project name");
    await expect(topSearch).toBeVisible();
    await topSearch.click();
    await topSearch.fill(`live ${suffix}`);

    const option = page.locator(".dw-project-option-button").filter({
      hasText: projectName,
    });
    await expect(option.first()).toBeVisible();
    await option.first().click();

    await expect(
      page.getByText(`Current project: ${projectName} (${projectKey})`)
    ).toBeVisible();
    await expect(
      page.locator(".dw-project-filter-meta").filter({ hasText: repositorySlug })
    ).toBeVisible();

    const analyzeProject = page.getByLabel("Project workspace");
    await expect(analyzeProject).toHaveValue(
      `${projectName} · ${repositorySlug} · ${projectKey}`
    );

    await page.goto("/history");
    await expect(
      page.getByText(`Project-scoped history for ${projectName} (${projectKey}).`)
    ).toBeVisible();
  });
});
