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

    const latestCreateDialog = () =>
      page.locator('[aria-label="Create project workspace"]').last();

    await page.getByRole("button", { name: "New project" }).click();
    let createDialog = latestCreateDialog();
    await expect(createDialog).toBeVisible();
    await expect(createDialog.getByRole("button", { name: "Close" })).toBeVisible();
    await expect(createDialog.getByRole("button", { name: "Cancel" })).toBeVisible();
    await page.waitForTimeout(6500);
    await expect(createDialog).toBeVisible();
    const createDialogColors = await createDialog.evaluate((dialog) => {
      const buttonStyles = Array.from(dialog.querySelectorAll("button")).map(
        (button) => {
          const style = window.getComputedStyle(button);
          return {
            text: button.textContent.trim(),
            color: style.color,
            backgroundColor: style.backgroundColor,
          };
        }
      );
      return {
        quasarPrimary: window
          .getComputedStyle(document.documentElement)
          .getPropertyValue("--q-primary")
          .trim()
          .toLowerCase(),
        buttonStyles,
      };
    });
    expect(createDialogColors.quasarPrimary).toBe("#ff6900");
    expect(JSON.stringify(createDialogColors.buttonStyles)).not.toContain(
      "88, 152, 212"
    );
    expect(
      createDialogColors.buttonStyles.some(
        (style) =>
          style.color.includes("255, 105, 0") ||
          style.backgroundColor.includes("255, 105, 0")
      )
    ).toBe(true);

    await createDialog.getByRole("button", { name: "Close" }).click();
    await expect(createDialog).toBeHidden();
    await page.waitForTimeout(500);

    await page.getByRole("button", { name: "New project" }).click();
    createDialog = latestCreateDialog();
    await expect(createDialog).toBeVisible();
    await createDialog.getByRole("button", { name: "Cancel" }).click();
    await expect(createDialog).toBeHidden();

    await page.goto("/");
    await page.getByRole("button", { name: "New project" }).click();
    createDialog = latestCreateDialog();
    await expect(createDialog).toBeVisible();
    await createDialog.getByLabel("Project key").fill(projectKey);
    await createDialog.getByLabel("Display name").fill(projectName);
    await createDialog
      .getByLabel("Repository URL")
      .fill(`https://github.com/${repositorySlug}.git`);
    await createDialog.getByRole("button", { name: "Create project" }).click();

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
