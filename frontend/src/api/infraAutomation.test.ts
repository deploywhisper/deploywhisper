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

const digest = `sha256:${"a".repeat(64)}`;
const stamp = "2026-10-29T00:00:00Z";
const deadline = "2026-10-29T00:15:00Z";
function approvalReview(): api.ApprovalReview {
  const binding = {
    version: 1, authorization_kind: "exact_plan" as const, workflow_id: "workflow-1", revision_id: "revision-1",
    workflow_revision_digest: digest, input_digest: digest,
    provenance: { version: 1, authorization_kind: "exact_plan" as const,
      source: { version: 1, kind: "collected" as const, repository_id: "iac-repo", commit_sha: "a".repeat(40), collector_id: "collector", profile_digest: digest, screened_transport_digest: digest, redaction_version: 1, collected_at: stamp, source_deadline: deadline },
      custody: { version: 1, handle: "custody-1", raw_local_digest: digest, expires_at: deadline } },
    project_id: 7, workspace_id: 9, environment: "test", canonical_target: "target-1", receiver_id: "receiver-1",
    pipeline_repository_id: "pipeline-repo", pipeline_workflow_id: "pipeline-workflow", pipeline_workflow_revision: "b".repeat(40),
    report_id: 15, report_schema_version: "v2" as const, report_bytes_digest: digest, policy_version: 1,
    policy_result: "passed" as const, policy_digest: digest, unit_waves_digest: digest, screened_artifact_digests: [digest],
    redaction_version: 1, payload_digest: digest, evidence_deadline: deadline, approval_deadline: deadline, authorization_epoch: 1, restore_epoch: 1,
  };
  return {
    version: 1,
    receipt: { id: "approval-1", run_id: "run-1", step_id: "decision", project_id: 7, workspace_id: 9, requested_by: "requester-1", reviewer_id: null, decision_kind: null, generation: 1, version: 1, status: "pending", reason: null, binding, eligibility: { eligible: false, reasons: ["missing_approval"], limitations: ["No decision"], context_todos: ["Review evidence"] }, binding_digest: digest, deadline_at: deadline, created_at: stamp, decided_at: null },
    report: { report_id: 15, schema_version: "v2", report_bytes_digest: digest, report_url: "/reports/15", recommendation: "go", severity: "low", should_block: false,
      confidence: { score: 0.9, level: "high", context_score: 0.9, uncertainty: null, context_todos: [], partial_context: false, insufficient_context: false },
      blast_radius: { direct_count: 1, transitive_count: 0, affected_services: ["storage"], unmatched_resource_count: 0, warning: null },
      rollback: { complexity: "low", complexity_score: 1, explanation: "Restore the prior version", warning: null, steps: [{ order: 1, title: "Restore", estimated_minutes: 3, critical: true }] }, summary_limited: false },
    action: { kind: "registered_github_handoff", authorization_kind: "exact_plan", canonical_target: "target-1", environment: "test", receiver_id: "receiver-1", pipeline_repository_id: "pipeline-repo", pipeline_workflow_id: "pipeline-workflow", pipeline_workflow_revision: "b".repeat(40), source_kind: "collected", source_repository_id: "iac-repo", source_commit_sha: "a".repeat(40), unit_waves_digest: digest, payload_digest: digest },
    context: { status: "eligible", can_submit: true, evaluated_at: stamp, decision_kind: "independent-approval", confirmation: { required: false, approve_phrase: null, reject_phrase: null }, effective_deadline: deadline, deadlines: { run: deadline, evidence: deadline, approval: deadline, source: deadline, custody: deadline }, policy_status: "advisory", policy_passed: true, reasons: [], limitations: [], context_todos: [] },
    attribution: null, can_export_audit: false, screening_limited: false,
  };
}

function decidedReview(status: "approved" | "rejected" = "approved"): api.ApprovalReview {
  const value = approvalReview();
  value.receipt = { ...value.receipt, version: 2, status, reviewer_id: "reviewer-1", decision_kind: "independent-approval", reason: "Reviewed", decided_at: stamp };
  value.context = { ...value.context, status: "decided", can_submit: false, reasons: ["decision_recorded"] };
  value.attribution = { event_id: "event-1", principal_id: "reviewer-1", principal_type: "human", role: "reviewer", project_id: 7, workspace_id: 9, reason: "Reviewed", occurred_at: stamp, before_digest: digest, after_digest: digest, state_digest_version: 1 };
  return value;
}

describe("approval packet adapters", () => {
  it("reads the exact selected packet with abortable no-store credentials", async () => {
    const value = approvalReview();
    const fetcher = response(value);
    const signal = new AbortController().signal;
    await expect(api.getApprovalReview("approval-1", scope, signal)).resolves.toEqual(value);
    expect(fetcher).toHaveBeenCalledWith("/api/v1/infra-automation/approvals/approval-1?project_id=7&workspace_id=9", expect.objectContaining({ signal, credentials: "same-origin", cache: "no-store" }));
  });

  it("keeps paginated historical approvals separate from decision authority", async () => {
    const value = { items: [approvalReview().receipt], cursor };
    const fetcher = response(value);
    await expect(api.getApprovals(scope, "cursor-1")).resolves.toEqual(value);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/infra-automation/approvals?project_id=7&workspace_id=9&limit=25&cursor=cursor-1");
    expect(value.items[0].eligibility.eligible).toBe(false);
  });

  const malformed = [
    (v: any) => { v.version = true; },
    (v: any) => { v.receipt.id = "other-approval"; },
    (v: any) => { v.receipt.project_id = 8; },
    (v: any) => { v.receipt.binding.workspace_id = 12; },
    (v: any) => { v.context.status = "automatic"; },
    (v: any) => { v.context.status = { toString: "automatic" }; },
    (v: any) => { v.context.future_floor = true; },
    (v: any) => { v.context.deadlines.future = deadline; },
    (v: any) => { v.receipt.deadline_at = "2026-10-29T00:16:00Z"; },
    (v: any) => { v.context.can_submit = "true"; },
    (v: any) => { v.context.decision_kind = "delegated"; },
    (v: any) => { v.context.evaluated_at = null; },
    (v: any) => { v.context.evaluated_at = deadline; },
    (v: any) => { v.context.reasons = ["unknown_floor"]; },
    (v: any) => { v.context.policy_passed = false; },
    (v: any) => { v.report.report_url = "https://elsewhere.invalid/15"; },
    (v: any) => { v.report.report_bytes_digest = `sha256:${"b".repeat(64)}`; },
    (v: any) => { v.report.should_block = 0; },
    (v: any) => { v.report.recommendation = "no_go"; },
    (v: any) => { v.report.confidence.score = 1.1; },
    (v: any) => { v.action.canonical_target = "other-target"; },
    (v: any) => { v.report.severity = "high"; },
  ];
  it.each(malformed)("rejects malformed or contradictory action eligibility", async (change) => {
    const value = approvalReview(); change(value); response(value);
    await expect(api.getApprovalReview("approval-1", scope)).rejects.toMatchObject({ name: "ApiClientError", status: 422 });
  });

  it("accepts readable unavailable clock context without authorizing", async () => {
    const value = approvalReview();
    value.context = { ...value.context, status: "unavailable", evaluated_at: null, can_submit: false, reasons: ["invalid_clock"], limitations: ["Clock unavailable"], context_todos: ["Refresh"] };
    response(value);
    await expect(api.getApprovalReview("approval-1", scope)).resolves.toEqual(value);
  });

  it("preserves bounded multiline report context without accepting multiline decision inputs", async () => {
    const value = approvalReview(); value.report.rollback.explanation = "Restore the prior version.\nVerify health.";
    response(value);
    await expect(api.getApprovalReview("approval-1", scope)).resolves.toEqual(value);
    const fetcher = response(null);
    await expect(api.submitApprovalDecision("approval-1", { expected_version: 1, binding_digest: digest, outcome: "reject", reason: "Review\nreason" }, "csrf")).rejects.toMatchObject({ status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("recovers a recorded receipt with retained attribution even when material is unavailable", async () => {
    const value = approvalReview();
    value.receipt = { ...value.receipt, version: 2, status: "approved", reviewer_id: "reviewer-1", decision_kind: "independent-approval", reason: "Reviewed", decided_at: stamp };
    value.context = { ...value.context, status: "decided", can_submit: false, reasons: ["decision_recorded"] };
    value.attribution = { event_id: "event-1", principal_id: "reviewer-1", principal_type: "human", role: "reviewer", project_id: 7, workspace_id: 9, reason: "Reviewed", occurred_at: stamp, before_digest: digest, after_digest: digest, state_digest_version: 1 };
    response(value);
    await expect(api.getApprovalReview("approval-1", scope)).resolves.toEqual(value);
    response({ ...value, attribution: null });
    await expect(api.getApprovalReview("approval-1", scope)).rejects.toMatchObject({ status: 422 });
  });

  it.each(["approved", "rejected"] as const)("rejects service attribution for a human %s receipt even when the principal matches", async (status) => {
    const value = decidedReview(status);
    value.attribution = { ...value.attribution!, principal_type: "service", role: "coordinator" };
    response(value);
    await expect(api.getApprovalReview("approval-1", scope)).rejects.toMatchObject({ status: 422 });
  });

  it.each(["approved", "rejected"] as const)("rejects mismatched human attribution for a %s receipt", async (status) => {
    const value = decidedReview(status);
    value.attribution = { ...value.attribution!, principal_id: "other-reviewer" };
    response(value);
    await expect(api.getApprovalReview("approval-1", scope)).rejects.toMatchObject({ status: 422 });
  });

  it.each(["coordinator", "unknown"])("rejects a human decision attribution with unsupported role %s", async (role) => {
    const value = decidedReview();
    (value.attribution as any).role = role;
    response(value);
    await expect(api.getApprovalReview("approval-1", scope)).rejects.toMatchObject({ status: 422 });
  });

  it.each([false, true])("preserves separately screened reasons and audit timestamps for retained attribution (legacy: %s)", async (legacy) => {
    const value = decidedReview();
    value.receipt.reason = "a".repeat(600);
    value.attribution = { ...value.attribution!, reason: `${"a".repeat(509)}…`, occurred_at: "2026-10-29T00:00:01Z", before_digest: legacy ? null : digest, state_digest_version: legacy ? null : 1 };
    value.screening_limited = true;
    response(value);
    await expect(api.getApprovalReview("approval-1", scope)).resolves.toEqual(value);
  });

  it("requires exact high-risk mode-sensitive confirmation before trusting eligible context", async () => {
    const value = approvalReview(); value.report.severity = "critical";
    value.context.decision_kind = "acknowledgement";
    value.context.confirmation = { required: true, approve_phrase: "ACKNOWLEDGE target-1", reject_phrase: "REJECT target-1" };
    response(value);
    await expect(api.getApprovalReview("approval-1", scope)).resolves.toEqual(value);
    response({ ...value, context: { ...value.context, confirmation: { ...value.context.confirmation, approve_phrase: "APPROVE target-1" } } });
    await expect(api.getApprovalReview("approval-1", scope)).rejects.toMatchObject({ status: 422 });
  });

  it("submits a closed human decision once with transient CSRF and validates the receipt", async () => {
    const value = approvalReview().receipt;
    const result = { ...value, version: 2, status: "approved", reviewer_id: "reviewer-1", decision_kind: "independent-approval", reason: "Reviewed", decided_at: stamp };
    const fetcher = response(result);
    const payload = { expected_version: 1, binding_digest: digest, outcome: "approve" as const, reason: "Reviewed", confirmation: null };
    await expect(api.submitApprovalDecision("approval-1", payload, "csrf-only-in-memory")).resolves.toEqual(result);
    const [path, init] = fetcher.mock.calls[0];
    expect(path).toBe("/api/v1/infra-automation/approvals/approval-1/decision");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-only-in-memory");
    expect(JSON.parse(init.body)).toEqual(payload);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it.each([{ reviewer: "admin" }, { actor: "admin" }, { decision_kind: "acknowledgement" }, { outcome: "bypass" }, { expected_version: true }, { reason: " " }, { confirmation: 1 }])("rejects actor/mode or malformed fields before transport", async (extra) => {
    const fetcher = response(null);
    await expect(api.submitApprovalDecision("approval-1", { expected_version: 1, binding_digest: digest, outcome: "approve", reason: "Reviewed", ...extra } as any, "csrf")).rejects.toMatchObject({ status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });


  it("rejects missing CSRF and unsafe IDs/scopes before transport", async () => {
    const fetcher = response(null);
    await expect(api.submitApprovalDecision("approval-1", { expected_version: 1, binding_digest: digest, outcome: "approve", reason: "Reviewed" }, "")).rejects.toMatchObject({ status: 403 });
    await expect(api.getApprovalReview("unsafe/id", scope)).rejects.toMatchObject({ status: 422 });
    await expect(api.getApprovals({ projectId: 7, workspaceId: NaN })).rejects.toMatchObject({ status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("rejects successful responses that fail to prove the requested decision transition", async () => {
    const value = { ...approvalReview().receipt, version: 2, status: "rejected", reviewer_id: "reviewer-1", decision_kind: "independent-approval", reason: "Reviewed", decided_at: stamp };
    response(value);
    await expect(api.submitApprovalDecision("approval-1", { expected_version: 1, binding_digest: digest, outcome: "approve", reason: "Reviewed" }, "csrf")).rejects.toMatchObject({ status: 422 });
  });

  it("keeps conflicts observable without automatic replay", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ error: { code: "binding_conflict" } }, { status: 409 }));
    vi.stubGlobal("fetch", fetcher);
    await expect(api.submitApprovalDecision("approval-1", { expected_version: 1, binding_digest: digest, outcome: "reject", reason: "Reviewed" }, "csrf")).rejects.toMatchObject({ status: 409 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("fetches scoped audit pages without broadening permission or draining cursors", async () => {
    const event = { id: "audit-1", project_id: 7, workspace_id: 9, actor_principal_id: "reviewer-1", actor_type: "human", actor_role: "reviewer", event_type: "decision_approve", target_id: "approval-1", reason: "Reviewed", before_digest: digest, after_digest: digest, created_at: stamp };
    const fetcher = response({ items: [event], cursor });
    await expect(api.getAutomationAudit(scope)).resolves.toEqual({ items: [event], cursor });
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/infra-automation/audit?project_id=7&workspace_id=9&limit=25");
    response({ items: [{ ...event, project_id: 8 }], cursor });
    await expect(api.getAutomationAudit(scope)).rejects.toMatchObject({ status: 422 });
  });
});
