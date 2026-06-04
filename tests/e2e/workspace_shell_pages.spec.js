const { test, expect } = require("@playwright/test");

const ROUTES = [
  { path: "/skills", active: "Skills", title: /DeployWhisper skills atlas/ },
  {
    path: "/incidents",
    active: "Incidents",
    title: /Incident ingestion management/,
  },
  { path: "/history", active: "History", title: /Analysis history/ },
  { path: "/settings", active: "Settings", title: /Operational settings/ },
];

test.describe("workspace shell pages", () => {
  for (const route of ROUTES) {
    test(`${route.active} uses the dashboard shell`, async ({ page }) => {
      const browserErrors = [];
      page.on("pageerror", (error) => browserErrors.push(error.message));
      page.on("console", (message) => {
        if (message.type() === "error") {
          browserErrors.push(message.text());
        }
      });

      await page.goto(route.path, { waitUntil: "networkidle" });

      const sidebar = page.getByRole("complementary");
      await expect(sidebar.getByText("DeployWhisper", { exact: true })).toBeVisible();
      await expect(sidebar.getByText("Evidence engine", { exact: true })).toBeVisible();
      await expect(page.getByPlaceholder("Search analyses, services...")).toBeVisible();
      await expect(page.getByPlaceholder("Search repo or project name")).toBeVisible();
      const runAnalysisButton = page.getByRole("button", { name: /Run Analysis/ });
      await expect(runAnalysisButton).toBeVisible();
      await expect(runAnalysisButton).toHaveCSS(
        "background-color",
        "rgb(255, 105, 0)",
      );
      const themeToggle = page.getByRole("button", { name: "Toggle theme" });
      await expect(themeToggle).toBeVisible();
      await expect(themeToggle).toHaveCSS("width", "40px");
      await expect(page.getByText(route.title)).toBeVisible();

      const nav = page.getByRole("navigation", { name: "Primary navigation" });
      for (const label of [
        "Dashboard",
        "Skills",
        "Incidents",
        "History",
        "Settings",
      ]) {
        await expect(nav.getByRole("link", { name: new RegExp(label) })).toBeVisible();
      }

      const activeLink = nav.getByRole("link", {
        name: new RegExp(route.active),
      });
      await expect(activeLink).toHaveCSS(
        "background-color",
        "rgba(255, 105, 0, 0.1)",
      );

      expect(
        browserErrors.filter(
          (message) =>
            message.includes("getElementsByClassName") ||
            message.includes("Cannot read properties of null"),
        ),
      ).toEqual([]);
    });
  }

  test("Run Analysis in the shared header opens Deploy Review from secondary pages", async ({
    page,
  }) => {
    await page.goto("/settings", { waitUntil: "networkidle" });

    await page.getByRole("button", { name: /Run Analysis/ }).click();

    await expect(page).toHaveURL(/\/#deploy-review$/);
    await expect(page.locator("#deploy-review")).toBeAttached({ timeout: 20_000 });
    await expect(page.getByText("Deploy review", { exact: true })).toBeVisible();
  });

  test("theme toggle switches the shared shell between light and dark", async ({
    page,
  }) => {
    await page.addInitScript(() =>
      window.localStorage.removeItem("deploywhisper-theme"),
    );
    await page.goto("/skills", { waitUntil: "networkidle" });

    await expect(page.locator("html")).toHaveAttribute("data-dw-theme", "light");
    await page.getByRole("button", { name: "Toggle theme" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-dw-theme", "dark");
    await expect(page.locator("body")).toHaveCSS(
      "background-color",
      "rgb(39, 39, 42)",
    );
    await expect(page.getByRole("complementary")).toHaveCSS(
      "background-color",
      "rgb(24, 24, 27)",
    );
    const historyLink = page
      .getByRole("navigation", { name: "Primary navigation" })
      .getByRole("link", { name: /History/ });
    await historyLink.hover();
    await expect(historyLink).toHaveCSS("background-color", "rgb(39, 39, 42)");
    await page.getByRole("button", { name: "Toggle theme" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-dw-theme", "light");
  });

  test("dark theme keeps dashboard content readable", async ({ page }) => {
    await page.addInitScript(() =>
      window.localStorage.removeItem("deploywhisper-theme"),
    );
    await page.goto("/", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Toggle theme" }).click();

    await expect(page.locator("html")).toHaveAttribute("data-dw-theme", "dark");
    await expect(page.getByText("Analysis snapshot")).toHaveCSS(
      "color",
      "rgb(244, 244, 245)",
    );

    const totalAnalysesCard = page
      .locator(".q-card")
      .filter({ hasText: "Total Analyses" })
      .first();
    await expect(totalAnalysesCard).toHaveCSS(
      "background-color",
      "rgb(24, 24, 27)",
    );
    await expect(totalAnalysesCard.getByText("Total Analyses")).toHaveCSS(
      "color",
      "rgb(161, 161, 170)",
    );

    const briefingCard = page
      .locator(".q-card")
      .filter({ hasText: "Deployment briefing" })
      .first();
    await expect(briefingCard.getByText(/Last scan:/).first()).toHaveCSS(
      "color",
      "rgb(244, 244, 245)",
    );
  });
});
