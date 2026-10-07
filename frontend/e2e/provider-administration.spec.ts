import { test, expect } from "@playwright/test";

test("rejected provider settings preserve existing configuration", async ({ page, request }, testInfo) => {
  page.setDefaultTimeout(15_000);
  const originalResponse = await request.get("/api/v1/settings");
  expect(originalResponse.ok()).toBeTruthy();
  const original = (await originalResponse.json()).data;

  await page.goto("/settings", { waitUntil: "networkidle" });
  await expect(page.getByRole("combobox", { name: "Active provider", exact: true })).toHaveValue(original.provider.provider);
  await expect(page.getByRole("checkbox", { name: "Local-only mode" })).toBeChecked({ checked: original.provider.local_mode });

  const rejected = await request.put("/api/v1/settings/provider", {
    data: { provider: "openai", model: "test", api_base: "http://127.0.0.1:1", local_mode: true },
  });
  expect(rejected.status()).toBe(400);

  await page.getByRole("combobox", { name: "Active provider", exact: true }).selectOption("openai");
  await page.getByRole("textbox", { name: "Model", exact: true }).fill("   ");
  const invalidResponse = page.waitForResponse((response) => response.url().endsWith("/api/v1/settings/provider") && response.request().method() === "PUT");
  await page.getByRole("button", { name: "Save AI settings" }).click();
  const invalid = await invalidResponse;
  expect(invalid.status()).toBe(400);
  expect((await invalid.json()).error.message).toBe("Provider model must not be blank.");
  await expect(page.getByText("Request failed: /api/v1/settings/provider", { exact: true })).toBeVisible();

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByRole("combobox", { name: "Active provider", exact: true })).toHaveValue(original.provider.provider);
  await expect(page.getByRole("checkbox", { name: "Local-only mode" })).toBeChecked({ checked: original.provider.local_mode });
  const unchangedResponse = await request.get("/api/v1/settings");
  expect(unchangedResponse.ok()).toBeTruthy();
  const unchanged = (await unchangedResponse.json()).data;
  expect(unchanged.provider).toEqual(original.provider);
  expect(unchanged.provider_options).toEqual(original.provider_options);
  await page.screenshot({ path: testInfo.outputPath("provider-settings.png"), fullPage: true });
});

test("disposable provider fixture validates transient keys without persisting them", async ({ page, request }, testInfo) => {
  test.skip(process.env.PROVIDER_ADMIN_TEST_MUTATION !== "1", "Successful saves require an explicitly opted-in disposable Compose app and database.");
  page.setDefaultTimeout(15_000);
  // Successful saves intentionally remain in this disposable database.
  // Every validation request uses a closed localhost port, never a hosted provider.
  const fixture = await request.put("/api/v1/settings/provider", {
    data: { provider: "openai", model: "test", api_base: "http://127.0.0.1:1", local_mode: false, request_timeout_seconds: 1 },
  });
  expect(fixture.ok()).toBeTruthy();
  const baseline = (await fixture.json()).data;
  const missingKeyMessage = "Provider API key is missing from environment-backed configuration.";
  expect(baseline.validation.valid).toBe(false);
  if (!baseline.settings.api_key_present) {
    expect(baseline.validation.message).toBe(missingKeyMessage);
  } else {
    expect(baseline.validation.message).not.toBe(missingKeyMessage);
  }

  await page.goto("/settings", { waitUntil: "networkidle" });
  await expect(page.getByRole("combobox", { name: "Active provider", exact: true })).toHaveValue("openai");
  await expect(page.getByRole("checkbox", { name: "Local-only mode" })).not.toBeChecked();
  await page.getByRole("button", { name: "Reveal API key field", exact: true }).click();
  await page.getByRole("textbox", { name: /^API key/ }).fill("synthetic-provider-administration-test-key");
  const saveResponse = page.waitForResponse((response) => response.url().endsWith("/api/v1/settings/provider") && response.request().method() === "PUT");
  await page.getByRole("button", { name: "Save AI settings" }).click();
  const saved = await saveResponse;
  expect(saved.ok()).toBeTruthy();
  const result = (await saved.json()).data;
  expect(result.settings.api_key_present).toBe(true);
  expect(result.settings.api_key_preview).toBe("syn****-key");
  expect(result.validation.valid).toBe(false);
  expect(result.validation.message).not.toBe(missingKeyMessage);
  await expect(page.getByText(result.validation.message, { exact: true })).toBeVisible();

  // GET resolves credentials from the environment again, rather than the transient save key.
  const resolvedResponse = await request.get("/api/v1/settings");
  expect(resolvedResponse.ok()).toBeTruthy();
  expect((await resolvedResponse.json()).data.provider).toEqual(baseline.settings);
  await page.reload({ waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Reveal API key field", exact: true }).click();
  await expect(page.getByRole("textbox", { name: /^API key/ })).toHaveValue("");
  const environmentResponse = page.waitForResponse((response) => response.url().endsWith("/api/v1/settings/provider") && response.request().method() === "PUT");
  await page.getByRole("button", { name: "Save AI settings" }).click();
  const environment = await environmentResponse;
  expect(environment.ok()).toBeTruthy();
  const environmentResult = (await environment.json()).data;
  expect(environmentResult.settings).toEqual(baseline.settings);
  expect(environmentResult.validation.message).toBe(baseline.validation.message);
  await expect(page.getByText(baseline.validation.message, { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("provider-settings-transient-key.png"), fullPage: true });
});
