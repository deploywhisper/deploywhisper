import { afterEach, describe, expect, it, vi } from "vitest";
import { getIdentitySession, loginIdentity, logoutIdentity, safeAccountReturnTo } from "./identity";

afterEach(() => vi.unstubAllGlobals());
describe("account return destinations", () => {
  it("accepts only known local read surfaces and bounded nonsecret scope queries", () => {
    for (const path of ["/", "/history", "/settings", "/infra-automation", "/infra-automation/workflows/12", "/infra-automation/runs/34?project_id=1&workspace_id=2", "/infra-automation/workflows/wf-demo:revision_1.2", "/infra-automation/workflows/new", "/infra-automation/runs/run_abc-123", "/reports/42", "/reports/42?private=1&automation_run=run:abc_123"]) {
      expect(safeAccountReturnTo(path)).toBe(path);
    }
  });
  it.each([
    "/infra-automation/runners",
    "/infra-automation/runners?project_id=2&workspace_id=1",
    "/infra-automation/approvals?project_id=2&workspace_id=1",
    "/infra-automation/runs/run-1?project_id=2&workspace_id=1&approval_id=approval-1",
  ])("preserves an approved scoped approval return destination %j", (path) => {
    expect(safeAccountReturnTo(path)).toBe(path);
  });
  it.each([
    "/infra-automation/runners/enroll",
    "/infra-automation/runners?token=private",
    "/infra-automation/runners?view=enroll",
    "/infra-automation/approvals/approval-1",
    "/infra-automation/approvals?approval_id=approval-1",
    "/infra-automation/workflows/wf-1?approval_id=approval-1",
    "/infra-automation/runs/run-1?approval_id=approval-1&approval_id=approval-2",
    "/infra-automation/runs/run-1?approval_id=../../settings",
    "/infra-automation/runs/run-1?approval_id=approval-1&actor=admin",
  ])("rejects misplaced or unsafe approval return selectors %j", (path) => {
    expect(safeAccountReturnTo(path)).toBe("/infra-automation");
  });
  it.each([
    "/infra-automation?view=runs",
    "/infra-automation?view=workflows",
    "/infra-automation?project_id=1&view=runs&workspace_id=2",
  ])("preserves the selected index tab in %j", (path) => {
    expect(safeAccountReturnTo(path)).toBe(path);
  });
  it.each([
    "/infra-automation?view=runs&view=workflows",
    "/infra-automation?view=runs&view=runs",
    "/infra-automation?view=publish",
    "/infra-automation?view=start",
    "/infra-automation?view=",
    "/infra-automation?view=Runs",
    "/infra-automation?view=%72uns",
    "/infra-automation?view=runs\n",
    "/infra-automation?view=runs&action=start",
    "/infra-automation/workflows?view=workflows",
    "/infra-automation/workflows/wf_1?view=runs",
    "/infra-automation/runs/run_1?view=runs",
    "/reports/1?view=runs",
    "/history?view=runs",
  ])("rejects unsafe or misplaced index tab in %j", (path) => {
    expect(safeAccountReturnTo(path)).toBe("/infra-automation");
  });
  it.each(["https://evil.test", "//evil.test", "/\\evil.test", "/%2f%2fevil", "/infra-automation/%252f", "/infra-automation/runs/1\n", "/unknown", "/settings/account", "/reports/1?token=secret", "/reports/1?action=delete", "/infra-automation/start", "/reports/../settings", "/reports/1#token", "/reports/1?project_id=1&project_id=2", "/reports/abc", "/reports/0", "/reports/9007199254740992", "/reports/1?private=2", "/reports/1?automation_run=run/evil", "/history?private=1", "/infra-automation/runs/run?private=1", "/reports/1?project_id=9007199254740992", "/infra-automation/runs/-bad", "/infra-automation/workflows/.", "/infra-automation/workflows/.."])("rejects unsafe target %j", (path) => {
    expect(safeAccountReturnTo(path)).toBe("/infra-automation");
  });
});
it("uses same-origin no-store session and credential requests without caching passwords", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ data: {}, meta: {} }) });
  vi.stubGlobal("fetch", fetchMock);
  await getIdentitySession();
  await loginIdentity("operator", "private-password");
  await logoutIdentity("csrf-value");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "same-origin", cache: "no-store", method: "GET" });
  expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST", body: JSON.stringify({ username: "operator", password: "private-password" }) });
  expect(new Headers(fetchMock.mock.calls[2][1].headers).get("X-CSRF-Token")).toBe("csrf-value");
});

describe("local account configuration", () => {
  it("reads the public configuration without mutation credentials", async () => {
    const { getIdentityConfiguration } = await import("./identity");
    const data = { version: 1, profile: "disabled", configured_origin: null, configuration_valid: true, login_available: false, authorization_profile: "legacy-evaluation", decision_mode: "shared" };
    const fetcher = vi.fn().mockResolvedValue(Response.json({ data, meta: {} }));
    vi.stubGlobal("fetch", fetcher);
    await expect(getIdentityConfiguration()).resolves.toEqual(data);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/auth/configuration");
    expect(fetcher.mock.calls[0][1]).toMatchObject({ credentials: "same-origin", cache: "no-store" });
    expect(new Headers(fetcher.mock.calls[0][1].headers).has("X-CSRF-Token")).toBe(false);
  });
  it.each(["https://name:secret@example.test", "https://example.test/path", "https://example.test?secret=value", "javascript:secret"]) ("rejects unsafe origin %s", async (configured_origin) => {
    const { getIdentityConfiguration } = await import("./identity");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ data: { version: 1, profile: "https", configured_origin, configuration_valid: true, login_available: true, authorization_profile: "verified", decision_mode: "shared" }, meta: {} })));
    await expect(getIdentityConfiguration()).rejects.toMatchObject({ status: 503, message: "Account configuration is unavailable." });
  });
  it("keeps embedded sign-in on Settings unless an explicit known safe return is supplied", async () => {
    const { localAccountReturnTo } = await import("./identity");
    expect(localAccountReturnTo(null)).toBe("/settings");
    expect(localAccountReturnTo("https://example.test")).toBe("/settings");
    expect(localAccountReturnTo("/infra-automation?project_id=7")).toBe("/infra-automation?project_id=7");
  });
});

it("preserves a safe configured origin without imposing browser URL normalization", async () => {
  const { getIdentityConfiguration } = await import("./identity");
  const configured_origin = "http://localhost:80";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ data: { version: 1, profile: "local-development", configured_origin, configuration_valid: true, login_available: false, authorization_profile: "verified", decision_mode: "shared" }, meta: {} })));
  await expect(getIdentityConfiguration()).resolves.toMatchObject({ configured_origin });
});
