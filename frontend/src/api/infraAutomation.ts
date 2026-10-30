import { ApiClientError, requestData } from "./client";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type AutomationScope = { projectId: number; workspaceId: number | null };
export type WorkflowSummary = Schemas["AutomationWorkflowSummary"];
export type WorkflowDetail = Schemas["AutomationWorkflowDetail"];
export type WorkflowPage = Schemas["AutomationWorkflowPage"];
export type RevisionSummary = Schemas["AutomationRevisionSummary"];
export type RevisionDetail = Schemas["AutomationRevisionDetail"];
export type RevisionPage = Schemas["AutomationRevisionPage"];
export type Capabilities = Schemas["AutomationCapabilities"];
export type Run = Schemas["RunView"];
export type RunPage = Schemas["RunPage"];
export type Step = Schemas["StepView"];
export type StepPage = Schemas["StepPage"];
export type RunReports = Schemas["AutomationPreflightLinks"];
export type Validation = Schemas["AutomationValidation"];
export type LogPage = Schemas["LogPage"];
export type Workspace = Schemas["WorkspaceData"];
export type CreateWorkflowRequest = Schemas["CreateWorkflowRequest"];
export type SaveDraftRequest = Schemas["SaveDraftRequest"];
export type PublishWorkflowRequest = Schemas["PublishWorkflowRequest"];
export type ArchiveWorkflowRequest = Schemas["ArchiveWorkflowRequest"];
export type PreflightRequest = Schemas["PreflightRequest"];

const base = "/api/v1/infra-automation";
const identifierPattern = /^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$/;
const capabilityOrder = ["automation.read", "automation.draft", "automation.publish", "automation.request"];
const positive = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value > 0;
const nonnegative = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

function invalid(): never {
  throw new ApiClientError("Automation response or request is unsupported. Refresh current state.", 422);
}

function id(value: string): string {
  if (!identifierPattern.test(value)) invalid();
  return encodeURIComponent(value);
}

function scopedParams(scope: AutomationScope): URLSearchParams {
  if (!positive(scope.projectId) || (scope.workspaceId !== null && !positive(scope.workspaceId))) invalid();
  const query = new URLSearchParams({ project_id: String(scope.projectId) });
  if (scope.workspaceId !== null) query.set("workspace_id", String(scope.workspaceId));
  return query;
}

function pagedParams(cursor?: string, query = new URLSearchParams()): URLSearchParams {
  query.set("limit", "25");
  if (cursor !== undefined) {
    if (!identifierPattern.test(cursor)) invalid();
    query.set("cursor", cursor);
  }
  return query;
}

function read<T>(path: string, signal?: AbortSignal): Promise<T> {
  return requestData<T>(path, { credentials: "same-origin", cache: "no-store", signal });
}

function mutate<T>(path: string, payload: unknown, csrf: string, method = "POST"): Promise<T> {
  if (!csrf || csrf.length > 1024 || /[\r\n]/.test(csrf)) return Promise.reject(new ApiClientError("Sign in again before making changes.", 403));
  return requestData<T>(`${base}${path}`, {
    method, credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify(payload),
  });
}

function checkPage<T extends { items: unknown[]; cursor: Schemas["CursorEnvelope"] }>(page: T): T {
  if (!record(page) || !Array.isArray(page.items) || !record(page.cursor)) invalid();
  const cursor = page.cursor;
  if (cursor.version !== 1 || !positive(cursor.limit) || cursor.limit > 100 || page.items.length > cursor.limit ||
      typeof cursor.snapshot_id !== "string" || !identifierPattern.test(cursor.snapshot_id) ||
      !(cursor.next_cursor === null || (typeof cursor.next_cursor === "string" && identifierPattern.test(cursor.next_cursor))) ||
      !nonnegative(cursor.last_sequence) || typeof cursor.truncated !== "boolean" || typeof cursor.gap !== "boolean") invalid();
  return page;
}

export async function getCapabilities(scope: AutomationScope, signal?: AbortSignal): Promise<Capabilities> {
  const value = await read<Capabilities>(`${base}/capabilities?${scopedParams(scope)}`, signal);
  if (!record(value) || value.version !== 1 || value.project_id !== scope.projectId || value.workspace_id !== scope.workspaceId ||
      !positive(value.membership_version) || !nonnegative(value.policy_version) || typeof value.execution_enabled !== "boolean" ||
      !Array.isArray(value.capabilities) || value.capabilities.length < 1 || value.capabilities.length > 4 ||
      value.capabilities[0] !== "automation.read" ||
      JSON.stringify(value.capabilities) !== JSON.stringify(capabilityOrder.filter((name) => value.capabilities.includes(name as Capabilities["capabilities"][number])))) invalid();
  return value;
}

export function getWorkspaces(projectKey: string, signal?: AbortSignal): Promise<Workspace[]> {
  return read(`/api/v1/projects/${encodeURIComponent(projectKey)}/workspaces`, signal);
}

export async function getWorkflows(scope: AutomationScope, cursor?: string, signal?: AbortSignal): Promise<WorkflowPage> {
  return checkPage(await read<WorkflowPage>(`${base}/workflows?${pagedParams(cursor, scopedParams(scope))}`, signal));
}
export function getWorkflow(workflowId: string, signal?: AbortSignal): Promise<WorkflowDetail> {
  return read(`${base}/workflows/${id(workflowId)}`, signal);
}
export async function validateWorkflow(scope: AutomationScope, definition: string, csrf: string): Promise<Validation> {
  scopedParams(scope);
  return mutate("/workflows/validate", { project_id: scope.projectId, workspace_id: scope.workspaceId, definition }, csrf);
}
export function validateDraft(workflowId: string, expectedVersion: number, definition: string | undefined, csrf: string): Promise<Validation> {
  return mutate(`/workflows/${id(workflowId)}/validate`, { expected_version: expectedVersion, definition }, csrf);
}
export function createWorkflow(payload: CreateWorkflowRequest, csrf: string): Promise<WorkflowDetail> {
  return mutate("/workflows", payload, csrf);
}
export function saveWorkflowDraft(workflowId: string, payload: SaveDraftRequest, csrf: string): Promise<WorkflowDetail> {
  return mutate(`/workflows/${id(workflowId)}/draft`, payload, csrf, "PUT");
}
export function publishWorkflow(workflowId: string, payload: PublishWorkflowRequest, csrf: string): Promise<RevisionDetail> {
  return mutate(`/workflows/${id(workflowId)}/revisions`, payload, csrf);
}
export function archiveWorkflow(workflowId: string, payload: ArchiveWorkflowRequest, csrf: string): Promise<WorkflowDetail> {
  return mutate(`/workflows/${id(workflowId)}/archive`, payload, csrf);
}
export async function getRevisions(workflowId: string, cursor?: string, signal?: AbortSignal): Promise<RevisionPage> {
  return checkPage(await read<RevisionPage>(`${base}/workflows/${id(workflowId)}/revisions?${pagedParams(cursor)}`, signal));
}
export function getRevision(workflowId: string, revisionId: string, signal?: AbortSignal): Promise<RevisionDetail> {
  return read(`${base}/workflows/${id(workflowId)}/revisions/${id(revisionId)}`, signal);
}
export function startPreflight(payload: PreflightRequest, csrf: string): Promise<Run> {
  return mutate("/preflights", payload, csrf);
}
export async function getRuns(scope: AutomationScope, cursor?: string, signal?: AbortSignal): Promise<RunPage> {
  return checkPage(await read<RunPage>(`${base}/runs?${pagedParams(cursor, scopedParams(scope))}`, signal));
}
export function getRun(runId: string, signal?: AbortSignal): Promise<Run> {
  return read(`${base}/runs/${id(runId)}`, signal);
}
export async function getRunSteps(runId: string, cursor?: string, signal?: AbortSignal): Promise<StepPage> {
  return checkPage(await read<StepPage>(`${base}/runs/${id(runId)}/steps?${pagedParams(cursor)}`, signal));
}
export async function getRunLogs(runId: string, attemptId: string, cursor?: string, signal?: AbortSignal): Promise<LogPage> {
  id(attemptId);
  return checkPage(await read<LogPage>(`${base}/runs/${id(runId)}/logs?${pagedParams(cursor, new URLSearchParams({ attempt_id: attemptId }))}`, signal));
}
export async function getRunReports(runId: string, signal?: AbortSignal): Promise<RunReports> {
  const value = await read<RunReports>(`${base}/runs/${id(runId)}/reports`, signal);
  if (!record(value) || !Array.isArray(value.items) || value.items.length > 50 || !record(value.evidence_status) ||
      value.evidence_status.version !== 1 || value.evidence_status.approval_eligible !== false) invalid();
  for (const link of value.items) {
    if (!record(link) || link.run_id !== runId || !positive(link.report_id) || link.report_url !== `/reports/${link.report_id}` ||
        link.approval_eligible !== false || !record(link.provenance) || link.provenance.version !== 1 ||
        link.provenance.kind !== "uploaded" || link.provenance.repository_source !== "unavailable") invalid();
  }
  return value;
}

export type Approval = Schemas["AutomationApprovalView"];
export type ApprovalPage = Schemas["AutomationApprovalPage"];
export type ApprovalReview = Schemas["ApprovalReviewPacket"];
export type ApprovalDecisionRequest = Schemas["DecisionRequest"];
export type AutomationAuditPage = Schemas["AutomationAuditPage"];

const digestPattern = /^sha256:[0-9a-f]{64}$/;
const commitPattern = /^[0-9a-f]{40}$/;
const utcPattern = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/;
const approvalStates = ["pending", "approved", "rejected", "invalidated", "expired", "superseded"];
const decisionKinds = ["independent-approval", "acknowledgement"];
const severities = ["low", "medium", "high", "critical"];
const policyStatuses = ["advisory", "warn", "soft-block", "hard-block"];
const actorRoles = ["admin", "maintainer", "reviewer", "contributor", "read-only", "coordinator"];
const identifier = (value: unknown): value is string => typeof value === "string" && identifierPattern.test(value);
const digestValue = (value: unknown): value is string => typeof value === "string" && digestPattern.test(value);
const commitValue = (value: unknown): value is string => typeof value === "string" && commitPattern.test(value);
const textValue = (value: unknown, maximum = 1024): value is string => typeof value === "string" && value.length <= maximum && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/.test(value);
const singleLineText = (value: unknown, maximum: number): value is string => textValue(value, maximum) && !/[\r\n\t\u2028\u2029]/.test(value);
const member = (value: unknown, choices: readonly string[]): value is string => typeof value === "string" && choices.includes(value);
const nullableText = (value: unknown, maximum = 1024) => value === null || value === undefined || textValue(value, maximum);
const textArray = (value: unknown, maximum = 50, length = 1024): value is string[] => Array.isArray(value) && value.length <= maximum && value.every((item) => textValue(item, length));
const onlyKeys = (value: Record<string, unknown>, names: readonly string[]) => Object.keys(value).every((key) => names.includes(key));
const unitScore = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
function utc(value: unknown): value is string {
  if (typeof value !== "string" || !utcPattern.test(value)) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString().replace(".000Z", "Z") === value;
}
function matchesScope(value: Record<string, unknown>, scope: AutomationScope): boolean {
  return value.project_id === scope.projectId && positive(value.workspace_id) && (scope.workspaceId === null || value.workspace_id === scope.workspaceId);
}
function checkBinding(value: unknown, scope: AutomationScope): asserts value is Schemas["DecisionBinding"] {
  if (!record(value) || value.version !== 1 || !matchesScope(value, scope) ||
      !member(value.authorization_kind, ["advisory_request", "exact_plan"]) ||
      !["workflow_id", "revision_id", "environment", "canonical_target", "receiver_id", "pipeline_repository_id", "pipeline_workflow_id"].every((key) => identifier(value[key])) ||
      !["workflow_revision_digest", "input_digest", "report_bytes_digest", "policy_digest", "unit_waves_digest", "payload_digest"].every((key) => digestValue(value[key])) ||
      !commitValue(value.pipeline_workflow_revision) || !positive(value.report_id) || value.report_schema_version !== "v2" ||
      !positive(value.policy_version) || value.policy_result !== "passed" || !positive(value.redaction_version) ||
      !positive(value.authorization_epoch) || !positive(value.restore_epoch) || !utc(value.evidence_deadline) || !utc(value.approval_deadline) ||
      !Array.isArray(value.screened_artifact_digests) || value.screened_artifact_digests.length < 1 || value.screened_artifact_digests.length > 50 || !value.screened_artifact_digests.every(digestValue)) invalid();
  const provenance = value.provenance;
  if (!record(provenance) || provenance.version !== 1 || provenance.authorization_kind !== value.authorization_kind || !record(provenance.source)) invalid();
  const source = provenance.source;
  if (source.version !== 1) invalid();
  if (source.kind === "collected") {
    if (!identifier(source.repository_id) || !identifier(source.collector_id) || !commitValue(source.commit_sha) || !digestValue(source.profile_digest) ||
        !digestValue(source.screened_transport_digest) || !positive(source.redaction_version) || source.redaction_version !== value.redaction_version ||
        !utc(source.collected_at) || !utc(source.source_deadline) || source.source_deadline <= source.collected_at ||
        Date.parse(source.source_deadline) - Date.parse(source.collected_at) > 3_600_000 || value.evidence_deadline > source.source_deadline ||
        !value.screened_artifact_digests.includes(source.screened_transport_digest)) invalid();
  } else if (source.kind === "uploaded") {
    if (value.authorization_kind !== "advisory_request" || source.repository_source !== "unavailable" || !textValue(source.limitation) || provenance.custody != null) invalid();
  } else invalid();
  const custody = provenance.custody;
  if (custody != null && (!record(custody) || custody.version !== 1 || !identifier(custody.handle) || !digestValue(custody.raw_local_digest) || !utc(custody.expires_at))) invalid();
  if (value.authorization_kind === "exact_plan" && (source.kind !== "collected" || !record(custody))) invalid();
}
function checkApproval(value: unknown, scope: AutomationScope, expectedId?: string): asserts value is Approval {
  if (!record(value) || !identifier(value.id) || (expectedId !== undefined && value.id !== expectedId) || !identifier(value.run_id) || !identifier(value.step_id) ||
      !matchesScope(value, scope) || !identifier(value.requested_by) || !(value.reviewer_id === null || identifier(value.reviewer_id)) ||
      !(value.decision_kind === null || member(value.decision_kind, decisionKinds)) || !positive(value.generation) || !positive(value.version) ||
      !member(value.status, approvalStates) || !nullableText(value.reason, 2048) || !digestValue(value.binding_digest) ||
      !utc(value.deadline_at) || !utc(value.created_at) || !(value.decided_at === null || utc(value.decided_at)) || !record(value.eligibility) ||
      typeof value.eligibility.eligible !== "boolean" || !textArray(value.eligibility.reasons, 50, 128) || !textArray(value.eligibility.limitations) || !textArray(value.eligibility.context_todos)) invalid();
  checkBinding(value.binding, scope);
  if (value.binding.project_id !== value.project_id || value.binding.workspace_id !== value.workspace_id) invalid();
  const boundDeadlines = [value.binding.evidence_deadline, value.binding.approval_deadline];
  if (value.binding.provenance.source.kind === "collected") boundDeadlines.push(value.binding.provenance.source.source_deadline);
  if (value.binding.provenance.custody) boundDeadlines.push(value.binding.provenance.custody.expires_at);
  if (value.deadline_at !== boundDeadlines.sort()[0]) invalid();
  if (member(value.status, ["approved", "rejected"]) && (value.reviewer_id === null || value.decision_kind === null || value.decided_at === null || !textValue(value.reason, 2048) || !value.reason.trim())) invalid();
  if (value.status === "pending" && (value.reviewer_id !== null || value.decision_kind !== null || value.decided_at !== null || value.reason !== null)) invalid();
}
function checkReview(value: unknown, approvalId: string, scope: AutomationScope): asserts value is ApprovalReview {
  if (!record(value) || !onlyKeys(value, ["version", "receipt", "report", "action", "context", "attribution", "can_export_audit", "screening_limited"]) || value.version !== 1 || typeof value.can_export_audit !== "boolean" || typeof value.screening_limited !== "boolean") invalid();
  checkApproval(value.receipt, scope, approvalId);
  const binding = value.receipt.binding;
  const report = value.report;
  if (!record(report) || report.report_id !== binding.report_id || report.schema_version !== "v2" || report.report_bytes_digest !== binding.report_bytes_digest ||
      report.report_url !== `/reports/${binding.report_id}` || !member(report.recommendation, ["go", "caution", "no-go"]) || !member(report.severity, severities) ||
      report.should_block !== false || typeof report.summary_limited !== "boolean" || !record(report.confidence) || !record(report.blast_radius) || !record(report.rollback)) invalid();
  const confidence = report.confidence, blast = report.blast_radius, rollback = report.rollback;
  if (!unitScore(confidence.score) || !unitScore(confidence.context_score) || !member(confidence.level, ["low", "medium", "high"]) ||
      !nullableText(confidence.uncertainty) || !textArray(confidence.context_todos, 20) || typeof confidence.partial_context !== "boolean" || typeof confidence.insufficient_context !== "boolean" ||
      !nonnegative(blast.direct_count) || !nonnegative(blast.transitive_count) || !nonnegative(blast.unmatched_resource_count) || !textArray(blast.affected_services, 20) || !nullableText(blast.warning) ||
      !member(rollback.complexity, ["low", "medium", "high"]) || !positive(rollback.complexity_score) || rollback.complexity_score > 5 || !textValue(rollback.explanation) ||
      !nullableText(rollback.warning) || !Array.isArray(rollback.steps) || rollback.steps.length > 20) invalid();
  for (const step of rollback.steps) if (!record(step) || !nonnegative(step.order) || !textValue(step.title) || !nonnegative(step.estimated_minutes) || typeof step.critical !== "boolean") invalid();
  const action = value.action;
  if (!record(action) || action.kind !== "registered_github_handoff" ||
      !["authorization_kind", "canonical_target", "environment", "receiver_id", "pipeline_repository_id", "pipeline_workflow_id", "pipeline_workflow_revision", "unit_waves_digest", "payload_digest"].every((key) => action[key] === binding[key as keyof typeof binding])) invalid();
  const source = binding.provenance.source;
  if (action.source_kind !== source.kind || action.source_repository_id !== (source.kind === "collected" ? source.repository_id : null) || action.source_commit_sha !== (source.kind === "collected" ? source.commit_sha : null)) invalid();
  const context = value.context;
  if (!record(context) || !onlyKeys(context, ["status", "can_submit", "evaluated_at", "decision_kind", "confirmation", "effective_deadline", "deadlines", "policy_status", "policy_passed", "reasons", "limitations", "context_todos"]) || !member(context.status, ["eligible", "blocked", "unavailable", "decided"]) || typeof context.can_submit !== "boolean" ||
      !(context.evaluated_at === null || utc(context.evaluated_at)) || (context.evaluated_at === null && context.status !== "unavailable") ||
      !(context.decision_kind === null || member(context.decision_kind, decisionKinds)) || !record(context.confirmation) || typeof context.confirmation.required !== "boolean" || !onlyKeys(context.confirmation, ["required", "approve_phrase", "reject_phrase"]) ||
      !nullableText(context.confirmation.approve_phrase, 256) || !nullableText(context.confirmation.reject_phrase, 256) ||
      !utc(context.effective_deadline) || !record(context.deadlines) || !onlyKeys(context.deadlines, ["run", "evidence", "approval", "source", "custody"]) || !utc(context.deadlines.run) || context.deadlines.evidence !== binding.evidence_deadline || context.deadlines.approval !== binding.approval_deadline ||
      context.deadlines.source !== (source.kind === "collected" ? source.source_deadline : null) || context.deadlines.custody !== (binding.provenance.custody?.expires_at ?? null) ||
      !(context.policy_status == null || member(context.policy_status, policyStatuses)) || !(context.policy_passed == null || typeof context.policy_passed === "boolean") ||
      !textArray(context.reasons, 50, 128) || !textArray(context.limitations) || !textArray(context.context_todos)) invalid();
  const deadlines = Object.values(context.deadlines).filter((item): item is string => item !== null);
  if (context.effective_deadline !== deadlines.sort()[0]) invalid();
  if (context.status === "decided" && value.receipt.status === "pending") invalid();
  if (context.status === "blocked" && context.reasons.length === 0) invalid();
  if (value.receipt.status !== "pending" && value.attribution === null) invalid();
  if (context.can_submit) {
    if (context.status !== "eligible" || value.receipt.status !== "pending" || context.reasons.length !== 0 || context.decision_kind === null || context.evaluated_at === null ||
        context.evaluated_at >= context.effective_deadline || context.policy_passed !== true || !member(context.policy_status, ["advisory", "warn"]) ||
        confidence.partial_context || confidence.insufficient_context || source.kind !== "collected") invalid();
    const requiresConfirmation = member(report.severity, ["high", "critical"]);
    const prefix = context.decision_kind === "acknowledgement" ? "ACKNOWLEDGE" : "APPROVE";
    if (context.confirmation.required !== requiresConfirmation || (requiresConfirmation &&
        (context.confirmation.approve_phrase !== `${prefix} ${binding.canonical_target}` || context.confirmation.reject_phrase !== `REJECT ${binding.canonical_target}`))) invalid();
  }
  const attribution = value.attribution;
  if (attribution !== null) {
    if (!record(attribution) || !identifier(attribution.event_id) || !identifier(attribution.principal_id) || !member(attribution.principal_type, ["human", "service"]) ||
        !member(attribution.role, actorRoles) || (attribution.principal_type === "service") !== (attribution.role === "coordinator") ||
        attribution.project_id !== value.receipt.project_id || attribution.workspace_id !== value.receipt.workspace_id || !textValue(attribution.reason, 2048) || !utc(attribution.occurred_at) ||
        !(attribution.before_digest === null || digestValue(attribution.before_digest)) || !digestValue(attribution.after_digest) || !(attribution.state_digest_version === null || attribution.state_digest_version === 1)) invalid();
    if (["approved", "rejected"].includes(value.receipt.status) &&
        (attribution.principal_type !== "human" || attribution.principal_id !== value.receipt.reviewer_id)) invalid();
  }
}

export async function getApprovals(scope: AutomationScope, cursor?: string, signal?: AbortSignal): Promise<ApprovalPage> {
  const page = checkPage(await read<ApprovalPage>(`${base}/approvals?${pagedParams(cursor, scopedParams(scope))}`, signal));
  for (const approval of page.items) checkApproval(approval, scope);
  return page;
}
export async function getApprovalReview(approvalId: string, scope: AutomationScope, signal?: AbortSignal): Promise<ApprovalReview> {
  const value = await read<ApprovalReview>(`${base}/approvals/${id(approvalId)}?${scopedParams(scope)}`, signal);
  checkReview(value, approvalId, scope);
  return value;
}
export async function submitApprovalDecision(approvalId: string, payload: ApprovalDecisionRequest, csrf: string): Promise<Approval> {
  id(approvalId);
  if (!record(payload) || Object.keys(payload).some((key) => !["reason", "expected_version", "binding_digest", "outcome", "confirmation"].includes(key)) ||
      !positive(payload.expected_version) || !digestValue(payload.binding_digest) || !["approve", "reject"].includes(payload.outcome) ||
      !singleLineText(payload.reason, 256) || !payload.reason.trim() || !(payload.confirmation == null || singleLineText(payload.confirmation, 256))) invalid();
  const result = await mutate<Approval>(`/approvals/${id(approvalId)}/decision`, payload, csrf);
  if (!record(result) || !positive(result.project_id) || !positive(result.workspace_id)) invalid();
  checkApproval(result, { projectId: result.project_id, workspaceId: result.workspace_id }, approvalId);
  if (result.binding_digest !== payload.binding_digest || result.version !== payload.expected_version + 1 || result.status !== (payload.outcome === "approve" ? "approved" : "rejected")) invalid();
  return result;
}
export async function getAutomationAudit(scope: AutomationScope, cursor?: string, signal?: AbortSignal): Promise<AutomationAuditPage> {
  const page = checkPage(await read<AutomationAuditPage>(`${base}/audit?${pagedParams(cursor, scopedParams(scope))}`, signal));
  for (const event of page.items) {
    if (!record(event) || !identifier(event.id) || event.project_id !== scope.projectId || !(event.workspace_id === null || positive(event.workspace_id)) ||
        (scope.workspaceId !== null && event.workspace_id !== scope.workspaceId) || !identifier(event.actor_principal_id) || !member(event.actor_type, ["human", "service"]) ||
        !member(event.actor_role, actorRoles) || (event.actor_type === "service") !== (event.actor_role === "coordinator") || !textValue(event.event_type, 64) || !event.event_type ||
        !identifier(event.target_id) || !textValue(event.reason, 256) || !utc(event.created_at) ||
        !(event.before_digest === null || digestValue(event.before_digest)) || !(event.after_digest === null || digestValue(event.after_digest))) invalid();
  }
  return page;
}
