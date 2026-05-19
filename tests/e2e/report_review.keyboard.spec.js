const { test, expect } = require("@playwright/test");

const REVIEW_ORDER = [
  "verdict",
  "confidence-ledger",
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

async function expectDelayedEvidenceFocusDoesNotStealUserFocus(page) {
  await page.evaluate(() => {
    document
      .querySelectorAll("[data-dw-focus-steal-fixture]")
      .forEach((element) => element.remove());
    const originalToggle = document.createElement("button");
    originalToggle.textContent = "Fixture evidence toggle";
    originalToggle.setAttribute("data-dw-focus-steal-fixture", "1");
    originalToggle.setAttribute("data-dw-evidence-toggle", "1");
    originalToggle.setAttribute("aria-controls", "fixture-evidence-panel");
    originalToggle.setAttribute("aria-expanded", "false");
    const sentinel = document.createElement("button");
    sentinel.id = "dw-focus-steal-sentinel";
    sentinel.textContent = "Fixture sentinel";
    sentinel.setAttribute("data-dw-focus-steal-fixture", "1");
    document.body.append(originalToggle, sentinel);
    originalToggle.focus();
    originalToggle.click();
    sentinel.focus();
    window.setTimeout(() => {
      const delayedToggle = document.createElement("button");
      delayedToggle.textContent = "Fixture delayed evidence toggle";
      delayedToggle.setAttribute("data-dw-focus-steal-fixture", "1");
      delayedToggle.setAttribute("data-dw-evidence-toggle", "1");
      delayedToggle.setAttribute("aria-controls", "fixture-evidence-panel");
      delayedToggle.setAttribute("aria-expanded", "true");
      document.body.append(delayedToggle);
      window.dwFocusStealFixtureReady = true;
    }, 80);
  });
  await page.waitForFunction(() => window.dwFocusStealFixtureReady === true);
  await page.waitForFunction(
    () => window.dwFocusRestoreLastStatus?.status === "aborted"
  );
  await expect
    .poll(() => page.evaluate(() => document.activeElement?.id || ""))
    .toBe("dw-focus-steal-sentinel");
}

test.describe("review keyboard flow", () => {
  test("tabs through review sections in order and supports arrow/escape controls", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByText("5-second verdict")).toBeVisible();
    await expect(page.getByText("Advisory posture").first()).toBeVisible();
    await expect(page.getByText("Evidence Law").first()).toBeVisible();
    await expect(page.getByText("Next action").first()).toBeVisible();
    await expect(page.getByText("Review linked evidence").first()).toBeVisible();
    await expect(page.getByText("Confidence ledger").first()).toBeVisible();
    await expect(page.getByText("Why not lower").first()).toBeVisible();
    await expect(page.getByText("Why not higher").first()).toBeVisible();
    await expect(page.getByText("Uncertainty drivers").first()).toBeVisible();
    await expect(page.getByText("Summary context check").first()).toBeVisible();
    await expect(page.getByText("Context follow-ups").first()).toBeVisible();
    await expect(page.getByText("Manage topology").first()).toBeVisible();
    await expect(page.getByText("Report schema guide").first()).toBeVisible();
    await expect(page.getByText("networking/ingress").first()).toBeVisible();
    await expect(page.getByText("1 evidence item").first()).toBeVisible();
    await expect(page.getByText("3 evidence items").first()).toBeVisible();
    await expect(page.getByText("Evidence Law satisfied").first()).toBeVisible();
    await expect(page.getByText("External").first()).toBeVisible();
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);
    await expectDelayedEvidenceFocusDoesNotStealUserFocus(page);
    await expect(page.getByText("Module: module.network").first()).toBeVisible();
    await expect(
      page
        .getByText("Provider: registry.terraform.io/hashicorp/aws")
        .first()
    ).toBeVisible();
    await expect(
      page.getByText("Unsupported plan fields: plan.planned_values").first()
    ).toBeVisible();
    await page.getByRole("button", { name: "Thumbs up" }).first().click();
    await expect(page.getByText("Module: module.network").first()).toBeVisible();
    await expect(
      page.getByText("Unsupported plan fields: plan.planned_values").first()
    ).toBeVisible();

    const findingRows = page.locator('[data-dw-finding-row="1"]');
    await expect(findingRows).toHaveCount(3);
    await findingRows.nth(0).focus();
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "CRITICAL: aws_security_group.main"
    );
    const firstFinding = findingRows.nth(0);
    const firstPanelId = await firstFinding.getAttribute("aria-controls");
    expect(firstPanelId).toMatch(/^evidence-inspector-/);
    await page.keyboard.press("Enter");
    const firstEvidenceInspector = page.locator(`[id="${firstPanelId}"]`);
    await expect(firstEvidenceInspector).toBeVisible();
    await expect(firstFinding).toBeFocused();
    await expect(
      firstEvidenceInspector.getByText("Ingress CIDR widened to 0.0.0.0/0.")
    ).toBeVisible();
    await expect(
      firstEvidenceInspector.getByRole("link", {
        name: /plan\.json.*aws_security_group\.main/,
      })
    ).toHaveAttribute("href", /\/history\/\d+\/artifacts\?name=plan\.json/);
    await page.keyboard.press("ArrowDown");
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "HIGH: aws_db_instance.primary"
    );
    const focusedFinding = findingRows.nth(1);
    const controlledPanelId = await focusedFinding.getAttribute("aria-controls");
    expect(controlledPanelId).toMatch(/^evidence-inspector-/);
    await page.keyboard.press("Enter");
    await expect(firstEvidenceInspector).toBeHidden();
    const evidenceInspector = page.locator(`[id="${controlledPanelId}"]`);
    await expect(evidenceInspector).toBeVisible();
    await expect(focusedFinding).toBeFocused();
    await page.keyboard.press("Space");
    await expect(evidenceInspector).toBeHidden();
    await expect(focusedFinding).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "CRITICAL: aws_security_group.main"
    );
    await page.keyboard.press("ArrowDown");
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "HIGH: aws_db_instance.primary"
    );
    await page.keyboard.press("Enter");
    await expect(evidenceInspector).toBeVisible();
    await expect(focusedFinding).toBeFocused();
    await expect(
      evidenceInspector.getByText("Proof reference payments-api")
    ).toBeVisible();
    await expect(evidenceInspector.getByText("Resource service")).toBeVisible();
    await expect(
      evidenceInspector.getByText("Operation operation not recorded")
    ).toBeVisible();
    await expect(
      evidenceInspector.getByText("Context source Topology")
    ).toBeVisible();
    await expect(evidenceInspector.getByText("Redaction None")).toBeVisible();
    await expect(
      evidenceInspector.getByText("Evidence content unavailable").first()
    ).toBeVisible();
    await expect(evidenceInspector.getByText("Redaction Redacted")).toBeVisible();
    await expect(
      evidenceInspector.getByText("metadata remains available").first()
    ).toBeVisible();
    await expect(
      evidenceInspector.getByText(
        "Redacted database maintenance evidence should not render."
      )
    ).toHaveCount(0);
    await expect(
      evidenceInspector.getByText("Redaction Sensitive blocked")
    ).toBeVisible();
    await expect(
      evidenceInspector.getByText("Sensitive evidence reference blocked")
    ).toBeVisible();
    await expect(
      evidenceInspector.getByText("Proof reference sensitive evidence blocked")
    ).toBeVisible();
    await expect(
      evidenceInspector.getByText("Resource resource withheld")
    ).toBeVisible();
    await expect(
      evidenceInspector.getByText("Operation operation withheld")
    ).toBeVisible();
    await expect(
      evidenceInspector.getByText("Sensitive blocked browser summary should not render.")
    ).toHaveCount(0);
    await expect(evidenceInspector.getByText("browser-secret.env")).toHaveCount(
      0
    );
    await expect(
      evidenceInspector.getByText("aws_iam_policy.browser_sensitive")
    ).toHaveCount(0);
    await expect(focusedFinding).toBeFocused();
    await page.keyboard.press("Space");
    await expect(evidenceInspector).toBeHidden();
    await expect(focusedFinding).toHaveAttribute("aria-expanded", "false");
    await expect(focusedFinding).toBeFocused();
    await page.keyboard.press("Space");
    await expect(evidenceInspector).toBeVisible();
    await expect(focusedFinding).toHaveAttribute("aria-expanded", "true");
    await expect(focusedFinding).toBeFocused();
    await focusedFinding.getByRole("button", { name: "Hide evidence" }).click();
    await expect(evidenceInspector).toBeHidden();
    await expect(focusedFinding).not.toBeFocused();
    await expect(
      focusedFinding.getByRole("button", { name: "View evidence" })
    ).toBeFocused();
    await focusedFinding.getByRole("button", { name: "View evidence" }).click();
    await expect(evidenceInspector).toBeVisible();
    await expect(
      focusedFinding.getByRole("button", { name: "Hide evidence" })
    ).toBeFocused();
    await evidenceInspector.getByText("Proof reference payments-api").click();
    await expect(evidenceInspector).toBeVisible();
    await expect(focusedFinding).toHaveAttribute("aria-expanded", "true");
    await focusedFinding.focus();
    await page.keyboard.press("ArrowDown");
    const legacyFinding = findingRows.nth(2);
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      'HIGH: "legacy" missing evidence'
    );
    const legacyPanelId = await legacyFinding.getAttribute("aria-controls");
    expect(legacyPanelId).toMatch(/^evidence-inspector-/);
    expect(legacyPanelId).not.toContain('finding "003"/legacy');
    await page.keyboard.press("Enter");
    const legacyInspector = page.locator(`[id="${legacyPanelId}"]`);
    await expect(legacyInspector).toBeVisible();
    await expect(legacyFinding).toBeFocused();
    await expect(legacyInspector.getByText("Evidence unavailable")).toBeVisible();
    await page.keyboard.press("Space");
    await expect(legacyInspector).toBeHidden();
    await expect(legacyFinding).toBeFocused();
    await legacyFinding.getByRole("button", { name: "View evidence" }).click();
    await expect(legacyInspector).toBeVisible();
    await expect(
      legacyFinding.getByRole("button", { name: "Hide evidence" })
    ).toBeFocused();

    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByText("5-second verdict")).toBeVisible();
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);

    await page.locator('[data-dw-review-section="verdict"]').focus();
    const confidenceLedgerSection = await tabUntilSection(
      page,
      "confidence-ledger",
      8
    );
    expect(confidenceLedgerSection).toBe("confidence-ledger");
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
    const activeEvidenceRegion = page
      .locator('[data-dw-review-section="evidence"]')
      .first();
    await activeEvidenceRegion.focus();
    await expect(activeEvidenceRegion).toBeFocused();
    const expandedBeforeInspectorKeys = await focusedFinding.getAttribute(
      "aria-expanded"
    );
    await page.keyboard.press("ArrowDown");
    await expect(activeEvidenceRegion).toBeFocused();
    await expect(focusedFinding).toHaveAttribute(
      "aria-expanded",
      expandedBeforeInspectorKeys
    );
    await page.keyboard.press("Space");
    await expect(activeEvidenceRegion).toBeFocused();
    await expect(focusedFinding).toHaveAttribute(
      "aria-expanded",
      expandedBeforeInspectorKeys
    );

    const seen = ["verdict", "confidence-ledger", "findings", "evidence"];
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
    await expect(page.locator(".dw-history-card")).toHaveCount(2);
    await expect(page.getByText("Rescan diff")).toBeVisible();
    await expect(page.getByText("+48 risk vs report #1")).toBeVisible();
    await page.locator(".dw-history-card").first().click();
    await expect(page).toHaveURL(/\/history\/2$/);
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);
    await expect(page.getByText("Analysis report detail")).toBeVisible();
    await expect(page.getByText("Back to History")).toBeVisible();
    await expect(page.getByText("Module: module.network").first()).toBeVisible();
    await expect(
      page.getByText("Unsupported plan fields: plan.planned_values").first()
    ).toBeVisible();
    await expect(page.locator('[data-dw-modal-root="1"]')).toHaveCount(0);
    await expect(
      page.locator('[data-dw-review-section="confidence-ledger"]')
    ).toBeVisible();
    await expect(page.getByText("Confidence ledger").first()).toBeVisible();
    await expect(page.getByText("Why not lower").first()).toBeVisible();
    await expect(page.getByText("Why not higher").first()).toBeVisible();
    await expect(page.locator('[data-dw-review-section="findings"]')).toBeVisible();
    await expect(page.locator('[data-dw-review-section="context"]')).toBeVisible();
    await expect(
      page.locator('[data-dw-review-section="blast-radius"]')
    ).toBeVisible();
    await expect(page.locator('[data-dw-review-section="rollback"]')).toBeVisible();
    await page.goto("/history/2/compare", { waitUntil: "networkidle" });
    await expect(page.getByText("Comparison with report #1")).toBeVisible();
    await expect(page.getByText("Risk score delta")).toBeVisible();
    await expect(page.getByText("+48")).toBeVisible();
    await expect(page.getByText(/MEDIUM.*CRITICAL/)).toBeVisible();
  });

  test("opens unavailable evidence with sanitized legacy finding ids", async ({
    page,
  }) => {
    await page.goto("/_e2e/missing-evidence", { waitUntil: "networkidle" });
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);
    await expect(
      page.getByText("0 evidence items, 1 unavailable").first()
    ).toBeVisible();

    const finding = page.locator('[data-dw-finding-row="1"]').first();
    await finding.focus();
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      'HIGH: "missing" secret ref'
    );
    const panelId = await finding.getAttribute("aria-controls");
    expect(panelId).toMatch(/^evidence-inspector-/);
    expect(panelId).not.toContain('finding "missing"/legacy');
    await page.keyboard.press("Enter");

    const inspector = page.locator(`[id="${panelId}"]`);
    await expect(inspector).toBeVisible();
    await expect(finding).toBeFocused();
    await expect(inspector.getByText("Evidence unavailable")).toBeVisible();
    await expect(
      inspector.getByText("Missing evidence refs: 1 unavailable reference")
    ).toBeVisible();
    await expect(
      inspector.getByText("Proof reference unavailable reference 1")
    ).toBeVisible();
    await expect(inspector.getByText("secret/path.env#TOKEN")).toHaveCount(0);
    await page.keyboard.press("Space");
    await expect(inspector).toBeHidden();
    await expect(finding).toBeFocused();

    const redactionFinding = page.locator('[data-dw-finding-row="1"]').nth(1);
    await redactionFinding.focus();
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "HIGH: fail-closed redaction states"
    );
    const redactionPanelId = await redactionFinding.getAttribute("aria-controls");
    await page.keyboard.press("Enter");
    const redactionInspector = page.locator(`[id="${redactionPanelId}"]`);
    await expect(redactionInspector).toBeVisible();
    await expect(
      redactionInspector.getByText("Redaction Sensitive blocked")
    ).toBeVisible();
    await expect(
      redactionInspector.getByText("Sensitive evidence reference blocked")
    ).toBeVisible();
    await expect(
      redactionInspector.getByText("Proof reference sensitive evidence blocked")
    ).toBeVisible();
    await expect(
      redactionInspector.getByText("Redaction Unknown")
    ).toBeVisible();
    await expect(
      redactionInspector.getByText("Evidence reference unavailable")
    ).toBeVisible();
    await expect(
      redactionInspector.getByText("Proof reference evidence metadata unavailable")
    ).toBeVisible();
    await expect(
      redactionInspector.getByText("content availability is unknown")
    ).toBeVisible();
    await expect(
      redactionInspector.getByText("Sensitive blocked browser summary should not render.")
    ).toHaveCount(0);
    await expect(
      redactionInspector.getByText("Future redaction browser summary should not render.")
    ).toHaveCount(0);
    await expect(redactionInspector.getByText("browser-secret.env")).toHaveCount(
      0
    );
    await expect(redactionInspector.getByText("unknown-browser.json")).toHaveCount(
      0
    );
    await expect(
      redactionInspector.getByText("aws_iam_policy.browser_sensitive")
    ).toHaveCount(0);
    await expect(
      redactionInspector.getByText("aws_iam_policy.browser_unknown")
    ).toHaveCount(0);
  });

  test("opens explicit v1 evidence with legacy summary and artifact link", async ({
    page,
  }) => {
    await page.goto("/_e2e/v1-evidence", { waitUntil: "networkidle" });
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);

    const finding = page.locator('[data-dw-finding-row="1"]').first();
    await finding.focus();
    await expect.poll(() => focusedFindingLabel(page)).toContain(
      "HIGH: legacy browser evidence"
    );
    const panelId = await finding.getAttribute("aria-controls");
    await page.keyboard.press("Enter");
    const inspector = page.locator(`[id="${panelId}"]`);

    await expect(inspector).toBeVisible();
    await expect(finding).toBeFocused();
    await expect(
      inspector.getByText("Legacy browser summary remains visible.")
    ).toBeVisible();
    await expect(inspector.getByText("Redaction None")).toBeVisible();
    await expect(
      inspector.getByRole("link", {
        name: /legacy-plan\.json.*line 7/,
      })
    ).toHaveAttribute(
      "href",
      "/history/44/artifacts?name=legacy-plan.json&line=7#L7"
    );
    await page.keyboard.press("Space");
    await expect(inspector).toBeHidden();
    await expect(finding).toBeFocused();
  });
});
