const path = require("path");
const fs = require("fs");
const os = require("os");
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
    await expect(page.locator('input[type="file"]').first()).not.toHaveAttribute(
      "webkitdirectory",
      "",
    );

    await page.waitForTimeout(6500);
    const uploadRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        request.url().includes("/_deploywhisper/dashboard-upload/"),
    );
    await fileInput.setInputFiles(
      path.join(
        process.cwd(),
        "samples/ui-demo-infra/analysis-artifacts/kubernetes/checkout-platform.yaml",
      ),
    );
    const uploadBody = (await uploadRequest).postData() || "";
    expect(uploadBody).toContain('name="artifact_paths"');
    expect(uploadBody).toContain("checkout-platform.yaml");

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
    if (
      await continueAnyway
        .waitFor({ state: "visible", timeout: 15_000 })
        .then(() => true)
        .catch(() => false)
    ) {
      await continueAnyway.click();
    }

    await expect(page.getByText("0 files", { exact: true })).toBeVisible({
      timeout: 90_000,
    });

    const recentAnalysesCard = page
      .locator(".q-card")
      .filter({ hasText: "Recent Analyses" })
      .first();
    await expect(
      recentAnalysesCard
        .getByRole("link", { name: /checkout-platform\.yaml/ })
        .first(),
    ).toBeVisible({ timeout: 90_000 });
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

  test("sends browser relative paths for directory uploads", async ({ page }) => {
    const uploadRoot = fs.mkdtempSync(
      path.join(os.tmpdir(), "deploywhisper-owners-"),
    );
    fs.mkdirSync(path.join(uploadRoot, "services/payments"), {
      recursive: true,
    });
    fs.writeFileSync(
      path.join(uploadRoot, "CODEOWNERS"),
      "/services/payments/ @payments-sre\n",
    );
    fs.writeFileSync(
      path.join(uploadRoot, "services/payments/plan.json"),
      '{"resource_changes": [{"address": "aws_security_group.payments", "change": {"actions": ["update"]}}]}',
    );

    await page.goto("/", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Run Analysis/ }).click();
    await expect(page.getByText("Deploy review", { exact: true })).toBeInViewport({
      timeout: 15_000,
    });

    const fileInputs = page.locator('input[type="file"]');
    await expect(fileInputs).toHaveCount(2);
    await expect(fileInputs.nth(0)).not.toHaveAttribute("webkitdirectory", "");
    await expect(fileInputs.nth(1)).toHaveAttribute("webkitdirectory", "");

    const uploadRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        request.url().includes("/_deploywhisper/dashboard-upload/"),
    );
    await fileInputs.nth(1).setInputFiles(uploadRoot);
    const uploadBody = (await uploadRequest).postData() || "";

    expect(uploadBody).toContain('name="artifact_paths"');
    expect(uploadBody).toContain("CODEOWNERS");
    expect(uploadBody).toContain("services/payments/plan.json");
    await expect(page.getByText("2 files", { exact: true })).toBeVisible();
    await expect(page.getByText("1 accepted", { exact: true })).toBeVisible();

    const analyzeButton = page.getByRole("button", { name: /^Analyze$/ });
    await expect(analyzeButton).toBeEnabled();
    await analyzeButton.click();

    const continueAnyway = page.getByRole("button", { name: "Continue Anyway" });
    if (
      await continueAnyway
        .waitFor({ state: "visible", timeout: 15_000 })
        .then(() => true)
        .catch(() => false)
    ) {
      await continueAnyway.click();
    }

    await expect(page.getByText("0 files", { exact: true })).toBeVisible({
      timeout: 90_000,
    });
    await expect(page.getByText("Ownership context").first()).toBeVisible({
      timeout: 90_000,
    });
    await expect(
      page
        .getByText(/Owner: .*services\/payments\/plan\.json -> @payments-sre/)
        .first(),
    ).toBeVisible();
  });
});
