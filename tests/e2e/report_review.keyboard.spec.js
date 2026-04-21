const { test, expect } = require("@playwright/test");

const REVIEW_ORDER = [
  "verdict",
  "findings",
  "evidence",
  "context",
  "blast-radius",
  "rollback",
];

async function focusedFindingLabel(page) {
  return page.evaluate(() => {
    const active = document.activeElement;
    if (!(active instanceof HTMLElement)) {
      return "";
    }
    return active.getAttribute("aria-label") || "";
  });
}

async function activeReviewTarget(page) {
  return page.evaluate(() => {
    const active = document.activeElement;
    if (!active) {
      return { kind: "none", label: "" };
    }
    const reviewSection = active.closest("[data-dw-review-section]");
    if (reviewSection) {
      return {
        kind: "section",
        label: reviewSection.getAttribute("data-dw-review-section") || "",
      };
    }
    const findingRow = active.closest('[data-dw-finding-row="1"]');
    if (findingRow) {
      return {
        kind: "finding-row",
        label: findingRow.getAttribute("aria-label") || "",
      };
    }
    const modalClose = active.closest('[data-dw-modal-close="1"]');
    if (modalClose) {
      return {
        kind: "modal-close",
        label: modalClose.textContent?.trim() || "",
      };
    }
    return {
      kind: active.tagName.toLowerCase(),
      label: active.textContent?.trim() || "",
    };
  });
}

async function tabUntilSection(page, label, maxSteps = 40) {
  for (let step = 0; step < maxSteps; step += 1) {
    await page.keyboard.press("Tab");
    const target = await activeReviewTarget(page);
    if (target.kind === "section" && target.label === label) {
      return target.label;
    }
  }
  return "";
}

test.describe("review keyboard flow", () => {
  test("tabs through review sections in order and supports arrow/escape controls", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByText("5-second verdict")).toBeVisible();
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);

    const findingRows = page.locator('[data-dw-finding-row="1"]');
    await expect(findingRows).toHaveCount(2);
    await findingRows.nth(0).focus();
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "CRITICAL: aws_security_group.main"
    );
    await page.keyboard.press("ArrowDown");
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "HIGH: aws_db_instance.primary"
    );
    await page.keyboard.press("ArrowUp");
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "CRITICAL: aws_security_group.main"
    );
    await page.keyboard.press("ArrowDown");
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "HIGH: aws_db_instance.primary"
    );
    await page.keyboard.press("Enter");
    await expect(
      page.locator('[data-dw-review-section="evidence"]')
    ).toBeVisible();

    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByText("5-second verdict")).toBeVisible();
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);

    await page.locator('[data-dw-review-section="verdict"]').focus();
    const findingsSection = await tabUntilSection(page, "findings", 8);
    expect(findingsSection).toBe("findings");

    await findingRows.nth(1).focus();
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "HIGH: aws_db_instance.primary"
    );
    await page.keyboard.press("Enter");
    await expect(
      page.locator('[data-dw-review-section="evidence"]')
    ).toBeVisible();

    const seen = ["verdict", "findings"];
    for (let step = 0; step < 40; step += 1) {
      await page.keyboard.press("Tab");
      const target = await activeReviewTarget(page);
      if (target.kind !== "section" || !REVIEW_ORDER.includes(target.label)) {
        continue;
      }
      if (!seen.includes(target.label)) {
        seen.push(target.label);
      }
      if (target.label === "rollback") {
        break;
      }
    }

    expect(seen).toEqual(REVIEW_ORDER);

    await page.goto("/history", { waitUntil: "networkidle" });
    await expect(page.locator(".dw-history-card")).toHaveCount(1);
    await page.locator(".dw-history-card").first().click();
    await expect(page).toHaveURL(/\/history\/1$/);
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);
    await expect(page.getByText("Analysis report detail")).toBeVisible();
    await expect(page.getByText("Back to History")).toBeVisible();
    await expect(page.locator('[data-dw-modal-root="1"]')).toHaveCount(0);
    await expect(page.locator('[data-dw-review-section="findings"]')).toBeVisible();
    await expect(page.locator('[data-dw-review-section="context"]')).toBeVisible();
    await expect(
      page.locator('[data-dw-review-section="blast-radius"]')
    ).toBeVisible();
    await expect(page.locator('[data-dw-review-section="rollback"]')).toBeVisible();
    await page.getByRole("button", { name: "Back to History" }).click();
    await expect(page).toHaveURL(/\/history$/);
  });
});
