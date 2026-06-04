const path = require("path");
const { test, expect } = require("@playwright/test");

test.describe("dashboard deploy review upload", () => {
  test("accepts a Kubernetes YAML artifact and runs analysis from Deploy Review", async ({
    page,
  }) => {
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") {
        browserErrors.push(message.text());
      }
    });

    await page.goto("/", { waitUntil: "networkidle" });

    const headerRunButton = page.getByRole("button", { name: /Run Analysis/ });
    await expect(headerRunButton).toHaveCSS(
      "background-color",
      "rgb(255, 105, 0)",
    );
    await headerRunButton.click();

    await expect(page.getByText("Deploy review", { exact: true })).toBeInViewport({
      timeout: 15_000,
    });

    await expect(page.getByText(/Current project:/)).toBeVisible();
    await expect(page.locator(".q-uploader__header").first()).toHaveCSS(
      "background-color",
      "rgb(255, 105, 0)",
    );

    const fileInput = await page
      .locator('input[type="file"]')
      .first()
      .elementHandle();
    expect(fileInput).not.toBeNull();

    await page.waitForTimeout(6500);
    await fileInput.setInputFiles(
      path.join(
        process.cwd(),
        "samples/ui-demo-infra/analysis-artifacts/kubernetes/checkout-platform.yaml",
      ),
    );

    await expect(page.getByText("1 files", { exact: true })).toBeVisible();
    await expect(page.getByText("1 accepted", { exact: true })).toBeVisible();

    const analyzeButton = page.getByRole("button", { name: /^Analyze$/ });
    await expect(analyzeButton).toBeEnabled();
    await expect(analyzeButton).toHaveCSS(
      "background-color",
      "rgb(255, 105, 0)",
    );
    await analyzeButton.click();

    const continueAnyway = page.getByRole("button", { name: "Continue Anyway" });
    if (await continueAnyway.isVisible({ timeout: 15_000 }).catch(() => false)) {
      await continueAnyway.click();
    }

    await expect(
      page.getByRole("link", { name: /^Saved report #/ }),
    ).toBeVisible({ timeout: 90_000 });

    const recentAnalysesCard = page
      .locator(".q-card")
      .filter({ hasText: "Recent Analyses" })
      .first();
    await expect(recentAnalysesCard).toContainText(/\d+s/, {
      timeout: 15_000,
    });

    const avgTimeCard = page
      .locator(".q-card")
      .filter({ hasText: "Avg Time to Verdict" })
      .first();
    await expect(avgTimeCard).toContainText(/\d+s/);

    expect(
      browserErrors.filter(
        (message) =>
          message.includes("getElementsByClassName") ||
          message.includes("Cannot read properties of null"),
      ),
    ).toEqual([]);
  });
});
