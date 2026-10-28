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
