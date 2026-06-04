const { test, expect } = require("@playwright/test");
const zlib = require("zlib");

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

function parseCssColor(value) {
  const match = String(value).match(/rgba?\(([^)]+)\)/i);
  if (!match) {
    return null;
  }
  const parts = match[1]
    .split(/[,/ ]+/)
    .filter(Boolean)
    .map((part) => Number.parseFloat(part));
  if (parts.length < 3 || parts.slice(0, 3).some(Number.isNaN)) {
    return null;
  }
  return parts.slice(0, 3).map((part) => Math.max(0, Math.min(255, part)));
}

function luminance(color) {
  const channels = color.map((channel) => {
    const normalized = channel / 255;
    return normalized <= 0.03928
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(foreground, background) {
  const light = Math.max(luminance(foreground), luminance(background));
  const dark = Math.min(luminance(foreground), luminance(background));
  return (light + 0.05) / (dark + 0.05);
}

function decodePng(buffer) {
  const signature = "89504e470d0a1a0a";
  if (buffer.subarray(0, 8).toString("hex") !== signature) {
    throw new Error("Expected PNG screenshot");
  }

  const idatChunks = [];
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  let interlace = 0;
  let offset = 8;

  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString("ascii", offset + 4, offset + 8);
    const dataStart = offset + 8;
    const dataEnd = dataStart + length;
    const data = buffer.subarray(dataStart, dataEnd);
    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
      interlace = data[12];
    } else if (type === "IDAT") {
      idatChunks.push(data);
    } else if (type === "IEND") {
      break;
    }
    offset = dataEnd + 4;
  }

  if (bitDepth !== 8 || interlace !== 0 || ![2, 6].includes(colorType)) {
    throw new Error(
      `Unsupported PNG format: bitDepth=${bitDepth} colorType=${colorType} interlace=${interlace}`
    );
  }

  const bytesPerPixel = colorType === 6 ? 4 : 3;
  const stride = width * bytesPerPixel;
  const inflated = zlib.inflateSync(Buffer.concat(idatChunks));
  const pixels = new Uint8Array(width * height * 4);
  let sourceOffset = 0;
  let previous = new Uint8Array(stride);

  const paeth = (left, up, upLeft) => {
    const predictor = left + up - upLeft;
    const leftDistance = Math.abs(predictor - left);
    const upDistance = Math.abs(predictor - up);
    const upLeftDistance = Math.abs(predictor - upLeft);
    if (leftDistance <= upDistance && leftDistance <= upLeftDistance) {
      return left;
    }
    return upDistance <= upLeftDistance ? up : upLeft;
  };

  for (let y = 0; y < height; y += 1) {
    const filter = inflated[sourceOffset];
    sourceOffset += 1;
    const row = new Uint8Array(stride);
    for (let x = 0; x < stride; x += 1) {
      const raw = inflated[sourceOffset + x];
      const left = x >= bytesPerPixel ? row[x - bytesPerPixel] : 0;
      const up = previous[x] || 0;
      const upLeft = x >= bytesPerPixel ? previous[x - bytesPerPixel] || 0 : 0;
      let value = raw;
      if (filter === 1) {
        value += left;
      } else if (filter === 2) {
        value += up;
      } else if (filter === 3) {
        value += Math.floor((left + up) / 2);
      } else if (filter === 4) {
        value += paeth(left, up, upLeft);
      } else if (filter !== 0) {
        throw new Error(`Unsupported PNG filter: ${filter}`);
      }
      row[x] = value & 0xff;
    }
    sourceOffset += stride;
    for (let x = 0; x < width; x += 1) {
      const sourceIndex = x * bytesPerPixel;
      const pixelIndex = (y * width + x) * 4;
      pixels[pixelIndex] = row[sourceIndex];
      pixels[pixelIndex + 1] = row[sourceIndex + 1];
      pixels[pixelIndex + 2] = row[sourceIndex + 2];
      pixels[pixelIndex + 3] = colorType === 6 ? row[sourceIndex + 3] : 255;
    }
    previous = row;
  }

  return { width, height, pixels };
}

function renderedBackgroundFromScreenshot(buffer) {
  const { width, height, pixels } = decodePng(buffer);
  const edgeSize = Math.min(3, Math.ceil(Math.min(width, height) / 2));
  const buckets = new Map();

  const addPixel = (x, y) => {
    const index = (y * width + x) * 4;
    if (pixels[index + 3] === 0) {
      return;
    }
    const color = [pixels[index], pixels[index + 1], pixels[index + 2]];
    const key = color.map((channel) => Math.round(channel / 4) * 4).join(",");
    const bucket = buckets.get(key) || { count: 0, total: [0, 0, 0] };
    bucket.count += 1;
    bucket.total[0] += color[0];
    bucket.total[1] += color[1];
    bucket.total[2] += color[2];
    buckets.set(key, bucket);
  };

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (
        x < edgeSize ||
        y < edgeSize ||
        x >= width - edgeSize ||
        y >= height - edgeSize
      ) {
        addPixel(x, y);
      }
    }
  }

  const background = [...buckets.values()].sort((left, right) => {
    return right.count - left.count;
  })[0];
  if (!background) {
    throw new Error("Could not sample rendered background pixels");
  }
  return {
    background: background.total.map((total) => total / background.count),
    height,
    width,
  };
}

async function expectRenderedTextContrast(locator, minimumRatio = 4.5) {
  const style = await locator.evaluate((element) => {
    const computed = window.getComputedStyle(element);
    return {
      color: computed.color,
      text: element.textContent?.trim() || element.getAttribute("aria-label") || "",
    };
  });
  const foreground = parseCssColor(style.color);
  if (!foreground) {
    throw new Error(`Could not parse foreground color: ${style.color}`);
  }
  const screenshot = await locator.screenshot();
  const { background, height, width } = renderedBackgroundFromScreenshot(screenshot);
  const result = {
    background: `rgb(${background.map(Math.round).join(", ")})`,
    foreground: style.color,
    ratio: contrastRatio(foreground, background),
    size: `${width}x${height}`,
    text: style.text,
  };
  expect(
    result.ratio,
    `${result.text} contrast ${result.foreground} on rendered ${result.background} (${result.size})`
  ).toBeGreaterThanOrEqual(minimumRatio);
}

async function expectHistoryFiltersAligned(page) {
  const metrics = await page.locator(".dw-history-filter-row").first().evaluate(
    (grid) =>
      Array.from(grid.children).map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          top: Math.round(rect.top),
          bottom: Math.round(rect.bottom),
          height: Math.round(rect.height),
        };
      })
  );
  expect(metrics).toHaveLength(4);
  const first = metrics[0];
  for (const metric of metrics.slice(1)) {
    expect(Math.abs(metric.top - first.top)).toBeLessThanOrEqual(2);
    expect(Math.abs(metric.bottom - first.bottom)).toBeLessThanOrEqual(2);
    expect(Math.abs(metric.height - first.height)).toBeLessThanOrEqual(2);
  }
}

async function selectHistoryFilter(page, label, option) {
  const field = page
    .locator(".dw-history-filter-control")
    .filter({ hasText: label })
    .first();
  await field.click();
  const popupOption = page
    .locator(".q-menu .q-item")
    .filter({ hasText: option })
    .first();
  await expect(popupOption).toBeVisible();
  await popupOption.click();
  await expect(field).toContainText(option);
}

async function expectReportSummaryCardsReadable(page) {
  const failures = await page.evaluate(() => {
    const result = [];
    const viewportWidth = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth > viewportWidth + 2) {
      result.push(
        `page has horizontal overflow: ${document.documentElement.scrollWidth} > ${viewportWidth}`
      );
    }

    const cards = Array.from(
      document.querySelectorAll("[data-dw-report-signal]")
    );
    if (cards.length === 0) {
      result.push("no report signal cards found");
      return result;
    }

    for (const card of cards) {
      const cardRect = card.getBoundingClientRect();
      const key = card.getAttribute("data-dw-report-signal") || "unknown";
      if (cardRect.width <= 0 || cardRect.height <= 0) {
        result.push(`${key} card has empty bounds`);
      }
      for (const text of card.querySelectorAll(
        ".dw-report-signal-value, .dw-report-signal-detail"
      )) {
        const textRect = text.getBoundingClientRect();
        if (text.scrollWidth > text.clientWidth + 2) {
          result.push(
            `${key} text overflows horizontally: ${text.scrollWidth} > ${text.clientWidth}`
          );
        }
        if (textRect.right > cardRect.right + 2) {
          result.push(`${key} text spills outside card right edge`);
        }
        if (textRect.bottom > cardRect.bottom + 2) {
          result.push(`${key} text spills outside card bottom edge`);
        }
      }
    }

    const rects = cards.map((card) => ({
      key: card.getAttribute("data-dw-report-signal") || "unknown",
      rect: card.getBoundingClientRect(),
    }));
    if (viewportWidth >= 1180) {
      const verdict = rects.find((item) => item.key === "verdict");
      const topRisk = rects.find((item) => item.key === "top-risk");
      if (verdict && topRisk && topRisk.rect.width <= verdict.rect.width * 2) {
        result.push(
          `top-risk card is not wide enough: ${topRisk.rect.width} <= ${verdict.rect.width * 2}`
        );
      }
    }
    for (let index = 0; index < rects.length; index += 1) {
      for (
        let otherIndex = index + 1;
        otherIndex < rects.length;
        otherIndex += 1
      ) {
        const a = rects[index];
        const b = rects[otherIndex];
        const separated =
          a.rect.right <= b.rect.left + 1 ||
          b.rect.right <= a.rect.left + 1 ||
          a.rect.bottom <= b.rect.top + 1 ||
          b.rect.bottom <= a.rect.top + 1;
        if (!separated) {
          result.push(`${a.key} card overlaps ${b.key} card`);
        }
      }
    }
    return result;
  });
  expect(failures).toEqual([]);
}

test.describe("review keyboard flow", () => {
  test("tabs through review sections in order and supports arrow/escape controls", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(
      page.getByRole("navigation", { name: "Primary navigation" })
    ).toBeVisible();
    await expect(
      page.getByRole("main", { name: "Deployment review workspace" })
    ).toBeVisible();
    const reviewStatus = page.getByRole("status", {
      name: "Review status updates",
    });
    await expect(reviewStatus).toBeAttached();
    await page.evaluate(() => {
      window.dwAnnounceReviewStatus("stale evidence status");
      window.dwAnnounceReviewStatus("latest evidence status");
    });
    await expect(reviewStatus).toHaveText("latest evidence status");
    await expect(page.getByText("5-second verdict")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "5-second verdict" })
    ).toBeVisible();
    await expect(page.getByText("Advisory posture").first()).toBeVisible();
    await expect(page.getByText("Evidence Law").first()).toBeVisible();
    await expect(page.getByText("Next action").first()).toBeVisible();
    await expect(page.getByText("Review linked evidence").first()).toBeVisible();
    await expect(page.getByText("Confidence ledger").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Confidence ledger" }).first()
    ).toBeVisible();
    await expect(page.getByText("Why not lower").first()).toBeVisible();
    await expect(page.getByText("Why not higher").first()).toBeVisible();
    await expect(page.getByText("Uncertainty drivers").first()).toBeVisible();
    await expect(page.getByText("Summary context check").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Summary context check" }).first()
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Findings table" }).first()
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Context completeness" }).first()
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Blast radius" }).first()
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Rollback plan" }).first()
    ).toBeVisible();
    await expect(page.getByText("Context follow-ups").first()).toBeVisible();
    await expect(page.getByText("Manage topology").first()).toBeVisible();
    await expect(page.getByText("Report schema guide").first()).toBeVisible();
    await expect(page.getByText("networking/ingress").first()).toBeVisible();
    await expect(page.getByText("1 evidence item").first()).toBeVisible();
    await expect(page.getByText("3 evidence items").first()).toBeVisible();
    await expect(page.getByText("Evidence Law satisfied").first()).toBeVisible();
    await expect(page.getByText("External").first()).toBeVisible();
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);
    await expectRenderedTextContrast(page.getByRole("link", { name: "Dashboard" }));
    await expectRenderedTextContrast(page.getByText("5-second verdict").first());
    await expectRenderedTextContrast(page.getByText("Confidence ledger").first());
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
    await expect(reviewStatus).toHaveText(
      /Evidence inspector opened for CRITICAL: aws_security_group\.main/
    );
    const firstEvidenceInspector = page.locator(`[id="${firstPanelId}"]`);
    await expect(firstEvidenceInspector).toBeVisible();
    await expect(
      firstEvidenceInspector.getByRole("heading", { name: "Evidence inspector" })
    ).toBeVisible();
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
    await expect(reviewStatus).toHaveText(
      /Evidence inspector closed for HIGH: aws_db_instance\.primary/
    );
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
    await expect(reviewStatus).toHaveText(
      /Evidence inspector opened for HIGH: aws_db_instance\.primary/
    );
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
    await expect(
      page.getByRole("navigation", { name: "Primary navigation" })
    ).toBeVisible();
    await expect(
      page.getByRole("main", { name: "Analysis history workspace" })
    ).toBeVisible();
    await expect(page.locator(".dw-history-card")).toHaveCount(2);
    await expect(page.getByText("Project filter", { exact: true })).toBeVisible();
    await expect(page.getByText("Workspace", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Time range", { exact: true })).toBeVisible();
    await expect(page.getByText("Risk verdict", { exact: true })).toBeVisible();
    await expect(page.getByText("Toolchain", { exact: true })).toBeVisible();
    await expect(page.getByText("Analysis status", { exact: true })).toBeVisible();
    await expectHistoryFiltersAligned(page);
    await selectHistoryFilter(page, "Time range", "Last 90 days");
    await selectHistoryFilter(page, "Risk verdict", "Critical");
    await selectHistoryFilter(page, "Toolchain", "Terraform");
    await selectHistoryFilter(page, "Analysis status", "Complete");
    await expect(page.getByText(/Tools: /).first()).toBeVisible();
    await expect(page.getByText("Schema: v2").first()).toBeVisible();
    await expect(page.getByText(/Status: /).first()).toBeVisible();
    await expect(page.getByText("Rescan diff")).toBeVisible();
    await expect(page.getByText("+48 risk vs report #1")).toBeVisible();
    await page.locator(".dw-history-card").first().click();
    await expect(page).toHaveURL(/\/history\/2$/);
    await page.waitForFunction(() => window.dwReviewAccessibilityInstalled === true);
    await expect(
      page.getByRole("navigation", { name: "Primary navigation" })
    ).toBeVisible();
    await expect(
      page.getByRole("main", { name: "Analysis report workspace" })
    ).toBeVisible();
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
    await page.goto("/history/999", { waitUntil: "networkidle" });
    await expect(
      page.getByRole("main", { name: "Analysis report unavailable" })
    ).toBeVisible();
    await expect(page.getByText("Analysis report not found")).toBeVisible();
    await page.goto("/history/2/compare", { waitUntil: "networkidle" });
    await expect(
      page.getByRole("navigation", { name: "Primary navigation" })
    ).toBeVisible();
    await expect(
      page.getByRole("main", { name: "Analysis report workspace" })
    ).toBeVisible();
    await expect(page.getByText("Comparison with report #1")).toBeVisible();
    await expect(page.getByText("Risk score delta")).toBeVisible();
    await expect(page.getByText("+48")).toBeVisible();
    await expect(page.getByText("MEDIUM → CRITICAL", { exact: true })).toBeVisible();
    await expect(page.getByText("Persistent findings", { exact: true })).toBeVisible();
    await expect(page.getByText("Changed context", { exact: true })).toBeVisible();
    await expect(page.getByText("Evidence changed")).toBeVisible();
  });

  test("keeps report summary cards readable with long dynamic content", async ({
    page,
  }) => {
    const longRisk =
      "CRITICAL: aws_eks_node_group.checkout_workers - Terraform aws_eks_node_group.checkout_workers is a replace change in the compute/workload category targeting production. It may affect 3 downstream service(s) or resource groups. Security flags: Open security group rule detected (protocol -1 / 0.0.0.0/0).";
    const longAction =
      "Review linked evidence and rollback readiness before release, confirm owner acknowledgement, validate topology impact, and record the human decision.";
    const scenarios = [
      { width: 390, height: 900, zoom: "1" },
      { width: 768, height: 1024, zoom: "1" },
      { width: 1366, height: 900, zoom: "1" },
      { width: 1920, height: 1080, zoom: "1.25" },
    ];

    for (const scenario of scenarios) {
      await page.setViewportSize({
        width: scenario.width,
        height: scenario.height,
      });
      await page.goto("/history/1", { waitUntil: "networkidle" });
      await page.evaluate(
        ({ risk, action, zoom }) => {
          document.body.style.zoom = zoom;
          const heading = document.querySelector(
            '[data-dw-report-heading="top-risk"]'
          );
          if (heading) {
            heading.textContent = risk;
          }
          const topRisk = document.querySelector(
            '[data-dw-report-signal-value="top-risk"]'
          );
          if (topRisk) {
            topRisk.textContent = risk;
          }
          const nextAction = document.querySelector(
            '[data-dw-report-signal-value="next-action"]'
          );
          if (nextAction) {
            nextAction.textContent = action;
          }
        },
        { risk: longRisk, action: longAction, zoom: scenario.zoom }
      );
      await expect(
        page.locator('[data-dw-report-signal="top-risk"]')
      ).toBeVisible();
      await expectReportSummaryCardsReadable(page);
    }
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
