import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "./infraAutomation";

afterEach(() => vi.unstubAllGlobals());
const scope = { projectId: 7, workspaceId: 9 };
const capabilities = { version: 1, project_id: 7, workspace_id: 9, membership_version: 1, policy_version: 0, execution_enabled: true, capabilities: ["automation.read", "automation.request"] };
const cursor = { version: 1, snapshot_id: "snapshot-1", next_cursor: "cursor-2", limit: 25, last_sequence: 1, truncated: false, gap: true };
const evidence = { version: 1, status: "available", run_state: "succeeded", run_version: 1, attempt_id: "attempt-1", attempt_state: "succeeded", manifest_present: true, report_available: true, evaluated_at: "2026-10-28T00:00:00Z", evidence_deadline: "2026-10-29T00:00:00Z", limitations: [], context_todos: [], approval_eligible: false };
function response(data: unknown) {
  const fetcher = vi.fn().mockImplementation(() => Promise.resolve(Response.json({ data, meta: {} })));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

describe("automation resource adapters", () => {
  it("uses exact scope, no-store, same-origin credentials and abortable reads", async () => {
    const fetcher = response(capabilities);
    const signal = new AbortController().signal;
    await expect(api.getCapabilities(scope, signal)).resolves.toEqual(capabilities);
    expect(fetcher).toHaveBeenCalledWith("/api/v1/infra-automation/capabilities?project_id=7&workspace_id=9", expect.objectContaining({ cache: "no-store", credentials: "same-origin", signal }));
  });

  it.each([{ ...capabilities, version: 2 }, { ...capabilities, project_id: 8 }, { ...capabilities, workspace_id: null }, { ...capabilities, capabilities: ["automation.admin"] }, { ...capabilities, execution_enabled: "true" }, { ...capabilities, capabilities: ["automation.request", "automation.read"] }])("fails closed for invalid capability projections", async (data) => {
    response(data);
    await expect(api.getCapabilities(scope)).rejects.toMatchObject({ name: "ApiClientError", status: 422, message: "Automation response or request is unsupported. Refresh current state." });
  });

  it("fetches one bounded page and preserves gap/truncation without auto-draining", async () => {
    const fetcher = response({ items: [], cursor });
    await expect(api.getWorkflows(scope, "cursor-1")).resolves.toEqual({ items: [], cursor });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/infra-automation/workflows?project_id=7&workspace_id=9&limit=25&cursor=cursor-1");
  });

  it.each([{ ...cursor, version: 2 }, { ...cursor, next_cursor: "unsafe/value" }, { ...cursor, limit: 101 }])("rejects unsupported or malformed cursor envelopes", async (value) => {
    response({ items: [], cursor: value });
    await expect(api.getRuns(scope)).rejects.toMatchObject({ name: "ApiClientError" });
  });

  it("uses JSON, CSRF and snake_case without retrying conflicts", async () => {
    const fetcher = response({ id: "workflow-1" });
    const payload = { expected_version: 3, definition: "workflow_version: 2", reason: "Edit draft" };
    await api.saveWorkflowDraft("workflow-1", payload, "transient-csrf");
    const [path, init] = fetcher.mock.calls[0];
    expect(path).toBe("/api/v1/infra-automation/workflows/workflow-1/draft");
    expect(init).toMatchObject({ method: "PUT", cache: "no-store", credentials: "same-origin", body: JSON.stringify(payload) });
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("transient-csrf");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    vi.stubGlobal("fetch", fetcher.mockImplementation(() => Promise.resolve(Response.json({ error: { code: "binding_conflict" } }, { status: 409 }))));
    await expect(api.saveWorkflowDraft("workflow-1", payload, "transient-csrf")).rejects.toMatchObject({ status: 409, code: "binding_conflict" });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("rejects missing CSRF, invalid scope and cursors before transport", async () => {
    const fetcher = response(null);
    await expect(api.createWorkflow({ project_id: 7, name: "workflow", definition: "", reason: "test" }, "")).rejects.toMatchObject({ name: "ApiClientError" });
    await expect(api.getCapabilities({ projectId: NaN, workspaceId: null })).rejects.toMatchObject({ name: "ApiClientError" });
    await expect(api.getRuns(scope, "invalid/cursor")).rejects.toMatchObject({ name: "ApiClientError" });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("uses attempt-specific bounded logs and encoded workspace keys", async () => {
    const fetcher = response({ items: [], cursor });
    await api.getRunLogs("run-1", "attempt-1", undefined);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/infra-automation/runs/run-1/logs?attempt_id=attempt-1&limit=25");
    response([]);
    await expect(api.getWorkspaces("project key")).resolves.toEqual([]);
  });

  it("fails closed for unsupported evidence versions or unproven permanent links", async () => {
    response({ items: [], evidence_status: { version: 2 } });
    await expect(api.getRunReports("run-1")).rejects.toMatchObject({ name: "ApiClientError" });
    response({ items: [{ run_id: "run-1", report_id: 1, report_url: "https://elsewhere/1", provenance: { version: 1, kind: "uploaded", repository_source: "unavailable" }, approval_eligible: false }], evidence_status: { version: 1, approval_eligible: false } });
    await expect(api.getRunReports("run-1")).rejects.toMatchObject({ name: "ApiClientError" });
  });

  it("preserves a proven uploaded report relation and evidence uncertainty", async () => {
    const value = { items: [{ id: "link-1", run_id: "run-1", attempt_id: "attempt-1", manifest_id: "manifest-1", report_id: 15, report_url: "/reports/15", provenance: { version: 1, kind: "uploaded", repository_source: "unavailable", limitation: "Repository and immutable commit were not verified for uploaded evidence." }, limitations: ["Unknown source"], context_todos: [], approval_eligible: false }], evidence_status: evidence };
    response(value);
    await expect(api.getRunReports("run-1")).resolves.toEqual(value);
    response({ ...value, items: [{ ...value.items[0], provenance: { ...value.items[0].provenance, version: 2 } }] });
    await expect(api.getRunReports("run-1")).rejects.toMatchObject({ name: "ApiClientError" });
  });

  it("binds validation, publication and archival to their distinct lifecycle endpoints", async () => {
    const fetcher = response({});
    await api.validateWorkflow({ projectId: 7, workspaceId: null }, "candidate", "csrf");
    await api.validateDraft("workflow-1", 4, "edited", "csrf");
    await api.publishWorkflow("workflow-1", { expected_version: 4, idempotency_key: "publish-1", reason: "Publish" }, "csrf");
    await api.archiveWorkflow("workflow-1", { expected_version: 5, reason: "Archive" }, "csrf");
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/infra-automation/workflows/validate", "/api/v1/infra-automation/workflows/workflow-1/validate",
      "/api/v1/infra-automation/workflows/workflow-1/revisions", "/api/v1/infra-automation/workflows/workflow-1/archive",
    ]);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ project_id: 7, workspace_id: null, definition: "candidate" });
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ expected_version: 4, definition: "edited" });
  });

  it("propagates cancellation without wrapping or retrying", async () => {
    const fetcher = vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError"));
    vi.stubGlobal("fetch", fetcher);
    await expect(api.getRun("run-1", new AbortController().signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
