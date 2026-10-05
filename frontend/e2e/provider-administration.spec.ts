import { test, expect } from "@playwright/test";

test("provider settings preserve local-only and environment credential boundaries", async ({ page, request }, testInfo) => {
  page.setDefaultTimeout(15_000);
  const originalResponse = await request.get("/api/v1/settings");
  expect(originalResponse.ok()).toBeTruthy();
  const original = (await originalResponse.json()).data.provider;
  test.skip(original.provider !== "ollama", "Provider mutation coverage requires a local Ollama test fixture.");
  const canRestoreProfile = original.source === "database";
  try {
    if (canRestoreProfile) {
      const local = await request.put("/api/v1/settings/provider", {
        data: { provider: "ollama", model: "ollama/test", api_base: "http://127.0.0.1:1", local_mode: true, request_timeout_seconds: 1 },
      });
      expect(local.ok()).toBeTruthy();
    }
    await page.goto("/settings", { waitUntil: "networkidle" });
    await expect(page.getByRole("checkbox", { name: "Local-only mode" })).toBeChecked();

    const rejected = await request.put("/api/v1/settings/provider", {
      data: { provider: "openai", model: "test", api_base: "https://example.invalid/v1", local_mode: true },
    });
    expect(rejected.status()).toBe(400);
    await page.reload({ waitUntil: "networkidle" });
    await expect(page.getByRole("checkbox", { name: "Local-only mode" })).toBeChecked();

    await page.getByRole("combobox", { name: "Active provider", exact: true }).selectOption("openai");
    await page.getByRole("textbox", { name: "Model", exact: true }).fill("   ");
    const invalidResponse = page.waitForResponse((response) => response.url().endsWith("/api/v1/settings/provider") && response.request().method() === "PUT");
    await page.getByRole("button", { name: "Save AI settings" }).click();
    const invalid = await invalidResponse;
    expect(invalid.status()).toBe(400);
    expect((await invalid.json()).error.message).toBe("Provider model must not be blank.");
    await expect(page.getByText("Request failed: /api/v1/settings/provider", { exact: true })).toBeVisible();
    await page.reload({ waitUntil: "networkidle" });
    await expect(page.getByRole("combobox", { name: "Active provider", exact: true })).toHaveValue("ollama");

    if (!canRestoreProfile) {
      // The API cannot delete provider overrides. Avoid creating one over environment defaults.
      await page.screenshot({ path: testInfo.outputPath("provider-settings.png"), fullPage: true });
      return;
    }
    await page.getByRole("combobox", { name: "Active provider", exact: true }).selectOption("openai");
    await page.getByRole("textbox", { name: "API base", exact: true }).fill("http://127.0.0.1:1");
    const saveResponse = page.waitForResponse((response) => response.url().endsWith("/api/v1/settings/provider") && response.request().method() === "PUT");
    await page.getByRole("button", { name: "Save AI settings" }).click();
    const saved = await saveResponse;
    expect(saved.ok()).toBeTruthy();
    const result = (await saved.json()).data;
    expect(result.validation.valid).toBe(false);
    if (!result.settings.api_key_present) {
      expect(result.validation.message).toBe("Provider API key is missing from environment-backed configuration.");
    }
    await expect(page.getByText(result.validation.message, { exact: true })).toBeVisible();
    await expect(page.getByRole("checkbox", { name: "Local-only mode" })).not.toBeChecked();
    await page.screenshot({ path: testInfo.outputPath("provider-settings.png"), fullPage: true });
  } finally {
    if (canRestoreProfile) {
      const restored = await request.put("/api/v1/settings/provider", {
        data: { provider: original.provider, model: original.model, api_base: original.api_base, local_mode: original.local_mode, request_timeout_seconds: original.request_timeout_seconds },
      });
      expect(restored.ok()).toBeTruthy();
    }
  }
});
