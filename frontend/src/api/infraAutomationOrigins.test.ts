import { afterEach, describe, expect, it, vi } from "vitest";
import { getAutomationAudit, getRun, getRuns, type Run } from "./infraAutomation";

const digest = `sha256:${"a".repeat(64)}`;
const scope = { projectId: 7, workspaceId: 9 };
const cursor = { version: 1, limit: 25, snapshot_id: "snapshot", next_cursor: null, last_sequence: 1, truncated: false, gap: false };
const collected = { kind: "collected" as const, step_id: "collect", repository_id: "repo", commit_sha: "b".repeat(40), profile_digest: digest };
const uploaded = { kind: "uploaded" as const, step_id: "upload", repository_id: null, commit_sha: null, limitation: "Uploaded evidence does not establish repository identity or exact-plan custody." as const };
const run: Run = { id: "run", workflow_id: "workflow", revision_id: "revision", project_id: 7, workspace_id: 9, requested_by: "principal", state: "waiting_approval", version: 1, snapshot_digest: digest, definition_digest: digest, input_digest: digest, created_at: "2026-11-06T00:00:00Z", deadline_at: "2026-11-06T01:00:00Z", cancel_requested: false, cancellation_requested_at: null };
function response(data: unknown) { vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ data, meta: {} }))); }
afterEach(() => vi.unstubAllGlobals());

describe("authenticated run origin decoding", () => {
  it.each([
    { kind: "manual", principal_type: "human", key_id: null, pr_ref: null, sources: [uploaded] },
    { kind: "cli", principal_type: "human", key_id: null, pr_ref: null, sources: [uploaded] },
    { kind: "cli", principal_type: "agent", key_id: "agent-key", pr_ref: null, sources: [collected] },
    { kind: "webhook", principal_type: "service", key_id: "service-key", pr_ref: null, sources: [collected] },
    { kind: "pull_request", principal_type: "service", key_id: "service-key", pr_ref: "refs/pull/12/head", sources: [collected] },
  ])("keeps channel and principal independent for $kind/$principal_type", async (fields) => {
    const value = { ...run, origin: { version: 1, principal_id: run.requested_by, ...fields } };
    response(value); await expect(getRun("run")).resolves.toEqual(value);
    response({ items: [value], cursor }); await expect(getRuns(scope)).resolves.toEqual({ items: [value], cursor });
  });
  it.each([undefined, null])("preserves unavailable legacy origin without inventing a human source", async (origin) => {
    const value = { ...run, origin }; response(value); await expect(getRun("run")).resolves.toMatchObject(run);
  });
  it.each([
    { principal_id: "other" }, { version: 2 }, { principal_type: "runner" },
    { kind: "manual" }, { principal_type: "human" }, { key_id: null },
    { pr_ref: "12" }, { kind: "pull_request", pr_ref: null },
    { sources: [collected, collected] }, { sources: [{ ...collected, commit_sha: "main" }] },
    { sources: [{ ...collected, profile_digest: "not-a-digest" }] },
    { sources: [{ ...uploaded, repository_id: "invented" }] },
    { sources: Array.from({ length: 51 }, (_, i) => ({ ...collected, step_id: `step-${i}` })) },
    { forged_actor: "admin" },
  ])("rejects malformed or misleading origin %#", async (patch) => {
    const value = { ...run, origin: { version: 1, kind: "webhook", principal_id: "principal", principal_type: "service", key_id: "key", pr_ref: null, sources: [collected], ...patch } };
    response(value); await expect(getRun("run")).rejects.toMatchObject({ status: 422 });
    response({ items: [value], cursor }); await expect(getRuns(scope)).rejects.toMatchObject({ status: 422 });
  });
  it("rejects origin-bearing runs from a different scope or detail identity", async () => {
    const value = { ...run, origin: { version: 1, kind: "manual", principal_id: "principal", principal_type: "human", sources: [uploaded] } };
    response({ items: [{ ...value, project_id: 8 }], cursor }); await expect(getRuns(scope)).rejects.toMatchObject({ status: 422 });
    response({ ...value, id: "other" }); await expect(getRun("run")).rejects.toMatchObject({ status: 422 });
  });
});

describe("machine audit attribution", () => {
  const event = { id: "audit", project_id: 7, workspace_id: 9, actor_principal_id: "principal", event_type: "run_requested", target_id: "run", reason: "Authenticated request", before_digest: null, after_digest: digest, created_at: "2026-11-06T00:00:00Z" };
  it.each([["service", "contributor"], ["service", "read-only"], ["agent", "contributor"], ["agent", "read-only"], ["service", "coordinator"], ["human", "admin"]])("accepts registered %s/%s attribution", async (actor_type, actor_role) => {
    const page = { items: [{ ...event, actor_type, actor_role }], cursor }; response(page); await expect(getAutomationAudit(scope)).resolves.toEqual(page);
  });
  it.each([["human", "coordinator"], ["agent", "coordinator"], ["agent", "admin"], ["service", "reviewer"]])("rejects unsupported %s/%s attribution", async (actor_type, actor_role) => {
    response({ items: [{ ...event, actor_type, actor_role }], cursor }); await expect(getAutomationAudit(scope)).rejects.toMatchObject({ status: 422 });
  });
});
