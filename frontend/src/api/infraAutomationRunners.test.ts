import { afterEach, describe, expect, it, vi } from "vitest";
import { getRunnerCapabilities, getRunnerHealth, enrollRunner, rotateRunner, revokeRunner, isConfirmedRunnerRejection } from "./infraAutomationRunners";

import { ApiClientError } from "./client";
import { RunnerMutationStore } from "../screens/runnerMutationState";

const scope = { projectId: 7, workspaceId: 9 };
const stamp = "2026-11-05T00:00:00Z";
const digest = `sha256:${"a".repeat(64)}`;
const profile = { profile_digest: digest, tool: "opentofu" as const, tool_version: "1.13.1", runner_version: "1.0", tags: ["isolated"] };
const capabilities = { version: 1, project_id: 7, workspace_id: 9, evaluated_at: stamp, can_read_health: true, can_enroll: true, can_rotate: true, can_revoke: true, production_eligible: true, execution_enabled: true, restriction: "none", profile_status: "available", configured_profiles: [profile] };
const runner = { id: "runner-1", project_id: 7, workspace_id: 9, tags: ["isolated"], tool: "opentofu", tool_version: "1.13.1", profile_digest: digest, runner_version: "1.0", protocol_version: 1, generation: 1, status: "active", last_seen_at: stamp, credential_expires_at: "2026-11-05T00:15:00Z", isolation_qualified: false, current_task: { run_id: "run-1", step_id: "collect", attempt_id: "attempt-1" }, evaluated_at: stamp, connectivity: "online", heartbeat_age_seconds: 0, online_threshold_seconds: 60, offline_threshold_seconds: 180, connectivity_reason: "heartbeat_current", credential_status: "valid", profile_status: "registered" };
const cursor = { version: 1, snapshot_id: "snapshot-1", next_cursor: null, limit: 25, last_sequence: 1, truncated: false, gap: false };
const enrollment = { enrollment: { version: 1, audience: "runner-enrollment-v1", enrollment_id: "enrollment-1", runner_id: "runner-1", project_id: "7", workspace_id: "9", expires_at: "2026-11-05T00:05:00Z", one_use: true }, token: "enroll-v1-synthetic-value" };
function response(data: unknown) { const fetcher = vi.fn().mockResolvedValue(Response.json({ data, meta: {} })); vi.stubGlobal("fetch", fetcher); return fetcher; }
afterEach(() => vi.unstubAllGlobals());

describe("runner administration boundary", () => {
  it("reads exact scope without cache and preserves connectivity separately from qualification", async () => {
    const fetcher = response(capabilities); const signal = new AbortController().signal;
    await expect(getRunnerCapabilities(scope, signal)).resolves.toEqual(capabilities);
    expect(fetcher.mock.calls[0]).toEqual(["/api/v1/infra-automation/runner-capabilities?project_id=7&workspace_id=9", expect.objectContaining({ cache: "no-store", credentials: "same-origin", signal })]);
    response({ items: [runner], cursor });
    const page = await getRunnerHealth(scope);
    expect(page.items[0].connectivity).toBe("online"); expect(page.items[0].isolation_qualified).toBe(false);
  });
  it.each([{ ...runner, project_id: 8 }, { ...runner, isolation_qualified: true }, { ...runner, connectivity: "trusted" }, { ...runner, heartbeat_age_seconds: -1 }, { ...runner, current_task: { run_id: "bad/path", step_id: "collect", attempt_id: "attempt-1" } }])("rejects malformed or cross-scope health", async (row) => {
    response({ items: [row], cursor }); await expect(getRunnerHealth(scope)).rejects.toMatchObject({ status: 422 });
  });
  it("rejects unexpected secret-bearing read fields before query caching", async () => {
    response({ items: [{ ...runner, token: "unexpected-secret" }], cursor });
    await expect(getRunnerHealth(scope)).rejects.toMatchObject({ status: 422 });
    response({ ...capabilities, token: "unexpected-secret" });
    await expect(getRunnerCapabilities(scope)).rejects.toMatchObject({ status: 422 });
  });
  it("keeps revocation available for an authorized admin when execution is disabled", async () => {
    const value = { ...capabilities, execution_enabled: false, can_enroll: false, can_rotate: false, restriction: "execution_disabled" };
    response(value); await expect(getRunnerCapabilities(scope)).resolves.toEqual(value);
  });
  it("rejects capabilities that grant insecure administration", async () => {
    response({ ...capabilities, production_eligible: false });
    await expect(getRunnerCapabilities(scope)).rejects.toMatchObject({ status: 422 });
  });
  it("sends CSRF mutations once and validates enrollment's scope and one-time audience", async () => {
    const fetcher = response(enrollment);
    await expect(enrollRunner(scope, profile, ["isolated"], "Enroll qualified runner", "csrf")).resolves.toEqual(enrollment);
    const [path, init] = fetcher.mock.calls[0]; expect(path).toBe("/api/v1/infra-automation/runners/enrollments");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf"); expect(init.cache).toBe("no-store");
    expect(JSON.parse(init.body)).toMatchObject({ project_id: 7, workspace_id: 9, profile_digest: digest });
    response({ ...enrollment, enrollment: { ...enrollment.enrollment, project_id: "8" } });
    await expect(enrollRunner(scope, profile, [], "Enroll runner", "csrf")).rejects.toMatchObject({ status: 502 });
  });
  it("never retries an ambiguous credential mutation or reflects its response", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ data: { token: "secret-never-display" } }, { status: 503 })); vi.stubGlobal("fetch", fetcher);
    await expect(rotateRunner("runner-1", "Rotate runner", "csrf")).rejects.toMatchObject({ message: "Request failed.", status: 503 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("treats an unverifiable successful issuance as ambiguous without exposing its token", async () => {
    const fetcher = response({ ...enrollment, enrollment: { ...enrollment.enrollment, one_use: false } });
    await expect(enrollRunner(scope, profile, [], "Enroll runner", "csrf")).rejects.toMatchObject({ status: 502, message: "Runner mutation response could not be verified. Refresh current state without repeating the request." });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("rejects invalid mutation input before transport", async () => {
    const fetcher = response(null);
    await expect(enrollRunner({ ...scope, workspaceId: null }, profile, [], "reason", "csrf")).rejects.toMatchObject({ status: 422 });
    await expect(revokeRunner("runner-1", "reason", "")).rejects.toMatchObject({ status: 403 });
    expect(fetcher).not.toHaveBeenCalled();
  });
});


describe("verified runner mutation rejection", () => {
  for (const action of ["enroll", "rotate"] as const) {
    for (const status of [400, 401, 403, 404, 409, 422, 429]) {
      it(`${action} retains uncertainty for uncoded HTTP ${status}`, async () => {
        const fetcher = vi.fn().mockResolvedValue(new Response("<html>Unverified proxy response</html>", { status }));
        vi.stubGlobal("fetch", fetcher);
        const store = new RunnerMutationStore();
        let marker: ReturnType<RunnerMutationStore["begin"]> = null;
        const submitted = () => { marker = store.begin("session", "scope", action, action === "rotate" ? "runner-1" : undefined); };
        try {
          if (action === "enroll") await enrollRunner(scope, profile, [], "Enroll runner", "csrf", submitted);
          else await rotateRunner("runner-1", "Rotate runner", "csrf", submitted);
          expect.fail("Unrecognized response must reject");
        } catch (failure) {
          expect(isConfirmedRunnerRejection(failure)).toBe(false);
          expect(marker).not.toBeNull();
          store.unknown(marker!);
        }
        expect(store.begin("session", "scope", action, "runner-1")).toBeNull();
        expect(fetcher).toHaveBeenCalledTimes(1);
      });
    }
    it(`${action} settles recognized application rejection`, async () => {
      const fetcher = vi.fn().mockResolvedValue(Response.json({ error: { code: "request_validation_failed" } }, { status: 422 }));
      vi.stubGlobal("fetch", fetcher);
      const store = new RunnerMutationStore();
      let marker: ReturnType<RunnerMutationStore["begin"]> = null;
      const submitted = () => { marker = store.begin("session", "scope", action, "runner-1"); };
      try {
        if (action === "enroll") await enrollRunner(scope, profile, [], "Enroll runner", "csrf", submitted);
        else await rotateRunner("runner-1", "Rotate runner", "csrf", submitted);
        expect.fail("Rejected response must throw");
      } catch (failure) {
        expect(isConfirmedRunnerRejection(failure)).toBe(true);
        store.verified(marker!, { kind: "rejected" });
      }
      expect(store.begin("session", "scope", action, "runner-1")).not.toBeNull();
    });
  }
  it("validates input and constructs headers before marking transport", async () => {
    const fetcher = response(null), submitted = vi.fn();
    await expect(enrollRunner(scope, profile, [], "bad\treason", "csrf", submitted)).rejects.toMatchObject({ status: 422 });
    await expect(rotateRunner("runner-1", "reason", "\u20ac", submitted)).rejects.toMatchObject({ status: 422 });
    await expect(revokeRunner("runner-1", "reason", "", submitted)).rejects.toMatchObject({ status: 403 });
    expect(submitted).not.toHaveBeenCalled(); expect(fetcher).not.toHaveBeenCalled();
  });
});


it("accepts only appropriate structured runner rejection codes", () => {
  const pairs = [[400, "request_validation_failed"], [401, "authentication_required"], [403, "permission_denied"], [404, "permission_denied"], [409, "binding_conflict"], [422, "request_validation_failed"], [429, "quota_exceeded"]] as const;
  for (const [status, code] of pairs) {
    expect(isConfirmedRunnerRejection(new ApiClientError("fixed", status, { code }))).toBe(true);
    expect(isConfirmedRunnerRejection(new ApiClientError("fixed", status, { code: "authority_unavailable" }))).toBe(false);
    expect(isConfirmedRunnerRejection(new ApiClientError("fixed", status))).toBe(false);
  }
  expect(isConfirmedRunnerRejection(new ApiClientError("fixed", 503, { code: "permission_denied" }))).toBe(false);
  expect(isConfirmedRunnerRejection(new ApiClientError("fixed", 422, { code: "permission_denied" }))).toBe(false);
});
