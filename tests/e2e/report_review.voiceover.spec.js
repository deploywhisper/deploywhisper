const { expect } = require("@playwright/test");
const { voiceOverTest: test } = require("@guidepup/playwright");

const EXPECTED_HEADINGS = [
  "5-second verdict",
  "Findings table",
  "Evidence inspector",
  "Context completeness",
  "Blast radius",
  "Rollback plan",
];

async function collectHeadingOrder(voiceOver, expectedLabels) {
  const found = [];

  for (let step = 0; step < 80 && found.length < expectedLabels.length; step += 1) {
    const itemText = ((await voiceOver.itemText()) || "").toLowerCase();
    for (const label of expectedLabels) {
      if (itemText.includes(label.toLowerCase()) && !found.includes(label)) {
        found.push(label);
        break;
      }
    }
    await voiceOver.perform(voiceOver.keyboardCommands.findNextHeading);
  }

  return found;
}

test.describe("review VoiceOver flow", () => {
  test.use({ voiceOverStartOptions: { capture: "initial" } });

  test("announces review headings in the expected order", async ({
    page,
    voiceOver,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByText("5-second verdict")).toBeVisible();
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);

    const findingRows = page.locator('[data-dw-finding-row="1"]');
    await expect(findingRows).toHaveCount(2);
    await findingRows.nth(0).focus();
    await page.keyboard.press("Enter");
    await expect(
      page.locator('[data-dw-review-section="evidence"]')
    ).toBeVisible();

    await voiceOver.navigateToWebContent();
    const headings = await collectHeadingOrder(voiceOver, EXPECTED_HEADINGS);

    expect(headings).toEqual(EXPECTED_HEADINGS);
  });
});
