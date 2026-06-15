const { test, expect } = require("@playwright/test");

test.describe("project selector", () => {
  test("top search selector activates the project across dashboard and history", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    const searchInput = page.getByPlaceholder("Search repo or project name");
    await expect(searchInput).toBeVisible();
    await searchInput.click();
    await searchInput.fill("pay");

    const option = page.getByRole("button", { name: /Payments/i }).first();
    await expect(option).toBeVisible();
    await option.click();

    await expect(page.getByText("Current project: Payments (payments)")).toBeVisible();
    const sidebar = page.getByRole("complementary");
    await expect(sidebar.getByText("Payments", { exact: true })).toBeVisible();
    await expect(sidebar.getByText("acme/payments-api")).toBeVisible();
    await expect(sidebar.getByText("Key payments", { exact: true })).toBeVisible();

    const dashboardProjectSelect = page.getByLabel("Project workspace");
    await expect(dashboardProjectSelect).toHaveValue(
      "Payments · acme/payments-api · payments"
    );

    await page.goto("/history", { waitUntil: "networkidle" });
    await expect(
      page.getByText("Project-scoped history for Payments (payments).")
    ).toBeVisible();
  });
});
