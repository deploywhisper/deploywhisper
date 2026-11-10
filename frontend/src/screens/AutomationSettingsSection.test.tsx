import { describe, expect, it } from "vitest";
import { automationSettingsAccessKey } from "./AutomationSettingsSection";
describe("operator settings access lifetime", () => {
  it("remounts drafts and target state after selected scope, session or identity epoch changes", () => {
    const original = automationSettingsAccessKey(7, 1, "session");
    expect(automationSettingsAccessKey(8, 1, "session")).not.toBe(original);
    expect(automationSettingsAccessKey(7, 2, "session")).not.toBe(original);
    expect(automationSettingsAccessKey(7, 1, "other-session")).not.toBe(original);
  });
});
