import { afterEach, describe, expect, it, vi } from "vitest";
import { cancelCollectionRun, startCollectedRun } from "./infraAutomationCollection";
import type { Run } from "./infraAutomation";
const runFixture: Run = { id: "run-one", workflow_id: "workflow-one", revision_id: "revision-one", project_id: 1, workspace_id: 2, requested_by: "principal-one", state: "succeeded", version: 3, snapshot_digest: "a".repeat(64), definition_digest: "b".repeat(64), input_digest: "c".repeat(64), created_at: "2026-10-28T00:00:00Z", deadline_at: "2026-10-28T01:00:00Z", cancel_requested: false, cancellation_requested_at: null };

afterEach(() => vi.unstubAllGlobals());
const scope = { projectId: 1, workspaceId: 2 };
const active = { ...runFixture, state: "running" as const, version: 3 };
function response(value: unknown) {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ data: value, meta: {} }));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

describe("collection mutation boundaries", () => {
  it("cancels the exact observed version without inferring external stop", async () => {
    const result = { ...active, version: 4, cancel_requested: true, cancellation_requested_at: active.created_at };
    const fetcher = response(result);
    await expect(cancelCollectionRun(active, scope, "Stop this collection", "csrf")).resolves.toEqual(result);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/infra-automation/runs/run-one/cancel");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ expected_version: 3, reason: "Stop this collection" });
    expect(fetcher.mock.calls[0][1]).toMatchObject({ credentials: "same-origin", cache: "no-store", method: "POST" });
  });
  it("starts only the supplied immutable revision and concrete scope", async () => {
    const fetcher = response({ ...active, state: "queued" });
    await startCollectedRun({ workflow_id: active.workflow_id, revision_id: active.revision_id, workspace_id: 2, inputs: {}, idempotency_key: "request-one", reason: "Review approved source", total_timeout_seconds: 3600 }, scope, "csrf");
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/infra-automation/runs");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).not.toHaveProperty("command");
  });
  it("rejects cross-scope or regressing mutation responses", async () => {
    for (const value of [{ ...active, project_id: 4 }, { ...active, workspace_id: 3 }, { ...active, id: "foreign" }, { ...active, version: 2 }]) {
      response(value);
      await expect(cancelCollectionRun(active, scope, "Stop", "csrf")).rejects.toMatchObject({ status: 422 });
    }
  });
  it("does not send missing CSRF, invalid reason, or project-wide cancellation", async () => {
    const fetcher = response(active);
    await expect(cancelCollectionRun(active, scope, "Stop", "")).rejects.toMatchObject({ status: 403 });
    await expect(cancelCollectionRun(active, scope, "", "csrf")).rejects.toMatchObject({ status: 422 });
    await expect(cancelCollectionRun(active, { projectId: 1, workspaceId: null }, "Stop", "csrf")).rejects.toMatchObject({ status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });
});

import { getCollectionReadiness, getCollectionView, validCollectedReportProvenance, type CollectionView } from "./infraAutomationCollection";
export const collectionFixture: CollectionView = {
  version: 1, run_id: "run-one", project_id: 1, workspace_id: 2, run_version: 3,
  observed_at: "2026-11-05T00:00:00Z", finite_wait_seconds: 0,
  cancellation: { requested: false, requested_at: null, owned_processes: "not_confirmed", external_stop: "not_confirmed", external_possible: false, can_cancel: true },
  limitations: ["Collector substages are not independently observed."],
  items: [{ step_id: "collect", repository_id: "repo-one", commit_sha: "a".repeat(40), profile_digest: `sha256:${"b".repeat(64)}`, attempt_id: "attempt-one", attempt_number: 1, attempt_state: "running", lease_until: "2026-11-05T00:01:00Z", routing_failure: null, diagnosis: { code: "heartbeat_stale", correction: "Reconnect the runner.", eligible: false }, observations: [ { kind: "source_bound", state: "bound", event_at: "2026-11-04T23:59:00Z" }, { kind: "collection", state: "running", event_at: null }, { kind: "screened_upload", state: "not_observed", event_at: null }, { kind: "analysis", state: "not_observed", event_at: null } ] }],
};
describe("collection durable read contracts", () => {
  it("binds reads to the exact scope and preserves unknown stage timestamps", async () => {
    const fetcher = response(collectionFixture), signal = new AbortController().signal;
    await expect(getCollectionView("run-one", scope, signal)).resolves.toEqual(collectionFixture);
    expect(fetcher.mock.calls[0]).toEqual(["/api/v1/infra-automation/runs/run-one/collection?project_id=1&workspace_id=2", expect.objectContaining({ signal, cache: "no-store", credentials: "same-origin" })]);
  });
  it("rejects scope mismatch, invented stop confirmation, extra stages, and bad diagnostics", async () => {
    for (const changed of [
      { ...collectionFixture, run_id: "foreign" }, { ...collectionFixture, project_id: 2 },
      { ...collectionFixture, finite_wait_seconds: 60 }, { ...collectionFixture, observed_at: "2026-02-30T00:00:00Z" },
      { ...collectionFixture, cancellation: { ...collectionFixture.cancellation, external_stop: "confirmed" } },
      { ...collectionFixture, items: [{ ...collectionFixture.items[0], observations: [...collectionFixture.items[0].observations].reverse() }] },
      { ...collectionFixture, items: [{ ...collectionFixture.items[0], diagnosis: { code: "no_runner", correction: "No runner", eligible: true } }] },
    ]) {
      response(changed);
      await expect(getCollectionView("run-one", scope)).rejects.toMatchObject({ status: 422 });
    }
  });
  it("retains unresolved input references without granting runner availability", async () => {
    const value = { version: 1, workflow_id: "workflow-one", revision_id: "revision-one", project_id: 1, workspace_id: 2, observed_at: collectionFixture.observed_at, finite_wait_seconds: 0, execution_enabled: true, can_request: true, items: [{ step_id: "collect", repository_id: null, commit_sha: null, profile_digest: collectionFixture.items[0].profile_digest, inputs_required: true, diagnosis: collectionFixture.items[0].diagnosis }] };
    response(value); await expect(getCollectionReadiness("workflow-one", "revision-one", scope)).resolves.toEqual(value);
    response({ ...value, revision_id: "other" }); await expect(getCollectionReadiness("workflow-one", "revision-one", scope)).rejects.toMatchObject({ status: 422 });
  });
});

describe("collected report provenance", () => {
  const hash = `sha256:${"c".repeat(64)}`;
  const provenance = {
    version: 1, kind: "collected", scope: { version: 1, runner_id: "runner-one", project_id: "1", workspace_id: "2", run_id: "run-one", step_id: "collect", attempt: 1, fence: 1, coordinator_generation: 1, authorization_epoch: 1, restore_epoch: 1, lease_deadline: "2026-11-05T00:01:00Z", audience: "runner-task-v1" },
    repository_id: "repo-one", commit_sha: "b".repeat(40), profile_digest: hash, command_digest: hash, argv_digest: hash, raw_local_digest: hash, sanitized_digest: hash, tool: "opentofu", tool_version: "1.13.1", redaction_version: 1, exit_code: 2, collected_at: "2026-11-05T00:00:00Z", source_deadline: "2026-11-05T00:05:00Z", custody: { version: 1, handle: "opaque-plan", raw_local_digest: hash, expires_at: "2026-11-05T00:05:00Z" }, limitation: "Collected provenance does not establish completeness or authorize an action.",
  };
  it("accepts bound collected evidence without granting eligibility", async () => {
    expect(validCollectedReportProvenance(provenance, "run-one")).toBe(true);
    const { getRunReports } = await import("./infraAutomation");
    const value = { items: [{ id: "link", run_id: "run-one", report_id: 1, report_url: "/reports/1", approval_eligible: false, provenance }], evidence_status: { version: 1, approval_eligible: false } };
    response(value); await expect(getRunReports("run-one")).resolves.toEqual(value);
  });
  it("rejects false custody digests, wrong attempts and invalid freshness", () => {
    for (const changed of [{ ...provenance, exit_code: 1 }, { ...provenance, scope: { ...provenance.scope, run_id: "other" } }, { ...provenance, scope: { ...provenance.scope, fence: 0 } }, { ...provenance, custody: { ...provenance.custody, raw_local_digest: `sha256:${"d".repeat(64)}` } }, { ...provenance, source_deadline: provenance.collected_at }]) expect(validCollectedReportProvenance(changed, "run-one")).toBe(false);
  });
});

import { validCollectionReason } from "./infraAutomationCollection";
describe("collection local validation before submission", () => {
  it("shares bounded single-line validation and never marks invalid requests submitted", async () => {
    const fetcher = response(active), submitted = vi.fn();
    for (const reason of ["bad\treason", "bad\u2028reason", "bad\u2029reason", " ", "x".repeat(257)]) {
      expect(validCollectionReason(reason)).toBe(false);
      await expect(startCollectedRun({ workflow_id: active.workflow_id, revision_id: active.revision_id, workspace_id: 2, reason, inputs: {}, idempotency_key: "request", total_timeout_seconds: 3600 }, scope, "csrf", submitted)).rejects.toMatchObject({ status: 422 });
      await expect(cancelCollectionRun(active, scope, reason, "csrf", submitted)).rejects.toMatchObject({ status: 422 });
    }
    expect(submitted).not.toHaveBeenCalled(); expect(fetcher).not.toHaveBeenCalled();
    expect(validCollectionReason("Review approved source")).toBe(true);
  });
  it("marks the request immediately before fetch only after validation", async () => {
    const events: string[] = [];
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => { events.push("fetch"); return Promise.resolve(Response.json({ data: active, meta: {} })); }));
    await cancelCollectionRun(active, scope, "Stop collection", "csrf", () => events.push("submitted"));
    expect(events).toEqual(["submitted", "fetch"]);
  });
});
