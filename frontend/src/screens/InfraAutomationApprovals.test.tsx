import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ApiClientError } from "../api/client";
import type { ApprovalReview } from "../api/infraAutomation";
import type { AutomationContext } from "./InfraAutomationShared";
import { ApprovalReviewPanel, approvalScopeKey, approvalFingerprint, approvalMatchesRun, approvalCanRestoreFocus, approvalReadAdvances, approvalIsUncertain, markApprovalUncertain, recoverApprovalRead, remainingApprovalTime, validApprovalReason, filterRecordedApprovals } from "./InfraAutomationApprovals";
const digest = `sha256:${"a".repeat(64)}`;
const stamp = "2026-10-29T00:00:00Z";
const deadline = "2026-10-29T00:15:00Z";
export function approvalReviewFixture(): ApprovalReview {
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

const context = { scope: { projectId: 7, workspaceId: 9 }, identity: { epoch: 3, csrfToken: "csrf", status: "ready" }, fresh: true, ensureFresh: async () => ({}), refresh: async () => ({}), capabilities: { execution_enabled: true } } as unknown as AutomationContext;
function renderPacket(packet: ApprovalReview, options: { expectedRunId?: string; error?: Error; currentContext?: AutomationContext } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
  const current = options.currentContext ?? context;
  const key = ["automation", current.identity.epoch, current.scope.projectId, current.scope.workspaceId, "approval", packet.receipt.id];
  client.setQueryData(key, packet);
  if (options.error) client.getQueryCache().find({ queryKey: key })?.setState({ error: options.error, status: "error" });
  return renderToStaticMarkup(<MemoryRouter><QueryClientProvider client={client}><ApprovalReviewPanel context={current} approvalId={packet.receipt.id} expectedRunId={options.expectedRunId} /></QueryClientProvider></MemoryRouter>);
}
describe("human decision review", () => {
  it("shows retained evidence and exact action before the decision controls", () => {
    const html = renderPacket(approvalReviewFixture());
    for (const value of ["Review approval", "target-1", "iac-repo", "Confidence and context", "Blast radius and rollback", "Open permanent report 15", "2026-10-29 00:15:00 UTC"]) expect(html).toContain(value);
    expect(html.indexOf("Confidence and context")).toBeLessThan(html.indexOf("Approve handoff"));
    expect(html).toContain('href="/reports/15?private=1"');
    expect(html).not.toContain("automation_run=");
    expect(html).toContain("Full evidence fingerprints");
    expect(html).not.toContain("<dialog");
  });
  it("rejects a mismatching URL run before displaying protected packet data", () => {
    const packet = approvalReviewFixture();
    expect(approvalMatchesRun(packet, "run-1")).toBe(true);
    expect(approvalMatchesRun(packet, "wrong-run")).toBe(false);
    const html = renderPacket(packet, { expectedRunId: "wrong-run" });
    expect(html).toContain("Approval does not match this run");
    expect(html).not.toContain(packet.receipt.binding_digest);
    expect(html).not.toContain("Confidence and context");
  });
  it("hides all retained fields after denied refresh rather than retaining an old authorized packet", () => {
    for (const status of [401,403]) {
      const packet = approvalReviewFixture();
      const html = renderPacket(packet, { error: new ApiClientError("unsafe server detail", status) });
      expect(html).toContain("Approval access unavailable");
      expect(html).not.toContain(packet.receipt.binding_digest);
      expect(html).not.toContain("unsafe server detail");
    }
  });
  it("withholds controls on failed refreshes, unavailable proof and read-only restored sessions", () => {
    const packet = approvalReviewFixture();
    packet.context = { ...packet.context, status: "unavailable", can_submit: false, evaluated_at: null, reasons: ["authority_unavailable"], limitations: ["Current proof unavailable"] };
    const html = renderPacket(packet);
    expect(html).toContain("Current proof unavailable");
    expect(html).toMatch(/disabled=""[^>]*>Approve handoff/);
    const restored = { ...context, identity: { ...context.identity, csrfToken: null } };
    expect(renderPacket(approvalReviewFixture(), { currentContext: restored })).toMatch(/disabled=""[^>]*>Approve handoff/);
    expect(renderPacket(approvalReviewFixture(), { error: new Error("offline") })).toContain("Displayed evidence is read-only");
  });
  it("labels server-selected acknowledgement without claiming independent review", () => {
    const packet = approvalReviewFixture(); packet.context.decision_kind = "acknowledgement";
    const html = renderPacket(packet);
    expect(html).toContain("Acknowledge handoff");
    expect(html).toContain("It does not record independent review");
    expect(html).not.toContain(">Approve handoff<");
  });
  it("preserves canonical no-go separately from the actual workflow policy", () => {
    const packet = approvalReviewFixture(); packet.report.recommendation = "no-go";
    const html = renderPacket(packet);
    expect(html).toContain("Workflow policy is evaluated separately");
    expect(html).toContain("advisory");
    expect(html).not.toMatch(/disabled=""[^>]*>Approve handoff/);
  });
  it("shows retained actor attribution and legacy/audit trust limits after recording", () => {
    const packet = approvalReviewFixture();
    packet.receipt = { ...packet.receipt, status: "approved", version: 2, reviewer_id: "retained-reviewer", decision_kind: "acknowledgement" };
    packet.context = { ...packet.context, status: "decided", can_submit: false };
    packet.attribution = { event_id: "event-1", principal_id: "retained-reviewer", principal_type: "human", role: "reviewer", project_id: 7, workspace_id: 9, reason: "Verified exact evidence", occurred_at: stamp, before_digest: null, after_digest: digest, state_digest_version: null };
    const html = renderPacket(packet);
    expect(html).toContain("Decision receipt"); expect(html).toContain("retained-reviewer");
    expect(html).toContain("Legacy binding attribution"); expect(html).toContain("Database and host administrators remain trusted");
    expect(html).not.toContain("Download scoped audit JSON"); expect(html).not.toContain("Approve handoff");
  });
  it("requires a bounded single-line nonblank reason", () => {
    for (const bad of ["", "  ", "x".repeat(257), "two\nlines", "hidden\u0000value"]) expect(validApprovalReason(bad)).toBe(false);
    expect(validApprovalReason("Reviewed the retained source and policy")).toBe(true);
  });
  it("uses server evaluation plus monotonic elapsed time only to expire/refetch", () => {
    const packet = approvalReviewFixture();
    expect(remainingApprovalTime(packet)).toBe(900000);
    expect(remainingApprovalTime(packet,900001)).toBe(0);
    packet.context.evaluated_at = null; expect(remainingApprovalTime(packet)).toBeNull();
  });
  it("invalidates prepared confirmation for mode/challenge/policy/window changes", () => {
    const packet=approvalReviewFixture(), original=approvalFingerprint(packet);
    for (const mutate of [(v:ApprovalReview)=>{v.context.decision_kind="acknowledgement";},(v:ApprovalReview)=>{v.context.confirmation.required=true;},(v:ApprovalReview)=>{v.context.effective_deadline=stamp;},(v:ApprovalReview)=>{v.receipt.binding.policy_version++;}]) {
      const next=structuredClone(packet); mutate(next); expect(approvalFingerprint(next)).not.toBe(original);
    }
  });
  it("isolates uncertain actions by actor epoch and exact scope", () => {
    const key=approvalScopeKey(context,"isolated-approval"), packet=approvalReviewFixture();
    markApprovalUncertain(key,packet.receipt); expect(approvalIsUncertain(key)).toBe(true);
    expect(approvalIsUncertain(approvalScopeKey({...context,scope:{projectId:8,workspaceId:9}},"isolated-approval"))).toBe(false);
    expect(approvalIsUncertain(approvalScopeKey({...context,identity:{...context.identity,epoch:4}},"isolated-approval"))).toBe(false);
  });
  it("keeps uncertain outcomes blocked on failed reads and clears only after exact durable recovery", async () => {
    const packet=approvalReviewFixture(), key="recover-one"; markApprovalUncertain(key,packet.receipt);
    await expect(recoverApprovalRead(key,async()=>{throw new Error("lost response");})).rejects.toThrow(); expect(approvalIsUncertain(key)).toBe(true);
    await recoverApprovalRead(key,async()=>({...packet,receipt:{...packet.receipt,version:2,status:"approved"}})); expect(approvalIsUncertain(key)).toBe(false);
  });
  it("does not let an older in-flight read clear a newer ambiguous submission", async () => {
    const packet=approvalReviewFixture(), key="recover-race"; markApprovalUncertain(key,packet.receipt);
    let finish!:(value:ApprovalReview)=>void; const reading=recoverApprovalRead(key,()=>new Promise(resolve=>{finish=resolve;}));
    markApprovalUncertain(key,packet.receipt); finish(packet); await reading; expect(approvalIsUncertain(key)).toBe(true);
    await recoverApprovalRead(key,async()=>packet);
  });
  it("does not clear uncertainty from a mismatched binding or earlier version", async () => {
    const packet=approvalReviewFixture(),key="recover-mismatch";markApprovalUncertain(key,packet.receipt);
    await recoverApprovalRead(key,async()=>({...packet,receipt:{...packet.receipt,binding_digest:`sha256:${"b".repeat(64)}`}}));expect(approvalIsUncertain(key)).toBe(true);
    await recoverApprovalRead(key,async()=>packet);
  });
  it("restores focus only to connected enabled decision triggers", () => {
    const button = (connected: boolean, disabled: boolean) => ({ isConnected: connected, matches: () => disabled }) as unknown as HTMLElement;
    expect(approvalCanRestoreFocus(button(true, false))).toBe(true);
    expect(approvalCanRestoreFocus(button(true, true))).toBe(false);
    expect(approvalCanRestoreFocus(button(false, false))).toBe(false);
    expect(approvalCanRestoreFocus(null)).toBe(false);
  });
  it("does not replace an observed durable outcome with a late pending read", () => {
    const pending = approvalReviewFixture();
    const decided: ApprovalReview = { ...pending, receipt: { ...pending.receipt, version: 2, status: "approved", reviewer_id: "reviewer-1", decision_kind: "independent-approval", decided_at: stamp } };
    expect(approvalReadAdvances(pending, decided)).toBe(true);
    expect(approvalReadAdvances(decided, pending)).toBe(false);
    expect(approvalReadAdvances(decided, { ...pending, receipt: { ...pending.receipt, version: 2 } })).toBe(false);
    for (const patch of [{ id: "other" }, { generation: 2 }, { binding_digest: `sha256:${"b".repeat(64)}` }]) {
      expect(approvalReadAdvances(pending, { ...pending, receipt: { ...pending.receipt, ...patch } })).toBe(false);
    }
    expect(approvalReadAdvances(undefined, pending)).toBe(true);
  });
  it("filters only recorded states without inventing full backend totals", () => {
    const pending=approvalReviewFixture().receipt;
    const rows=[pending,{...pending,id:"expired",status:"expired" as const},{...pending,id:"decided",status:"rejected" as const}];
    expect(filterRecordedApprovals(rows,"pending")).toEqual([pending]);
    expect(filterRecordedApprovals(rows,"expired").map(row=>row.id)).toEqual(["expired"]);
    expect(filterRecordedApprovals(rows,"decided").map(row=>row.id)).toEqual(["decided"]);
  });
});
