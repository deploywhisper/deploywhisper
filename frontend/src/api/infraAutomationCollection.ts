import { ApiClientError, requestData } from "./client";
import type { AutomationScope, Run } from "./infraAutomation";
import type { components } from "./schema";

export type CollectedRunRequest = components["schemas"]["RunRequest"];
const base = "/api/v1/infra-automation";
const identifier = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
const runStates = new Set(["queued", "running", "waiting_approval", "ready_handoff", "handing_off", "external_running", "delivery_unknown", "succeeded", "failed", "stopped_by_gate", "rejected", "expired", "timed_out", "cancelled"]);
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const positive = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value > 0;
function date(value: unknown): value is string {
  if (typeof value !== "string" || !/^[0-9]{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(value) || value.startsWith("0000")) return false;
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().replace(".000Z", "Z") === value;
}
const text = (value: unknown, max = 1024): value is string => typeof value === "string" && value.length <= max && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/.test(value);
function invalid(): never { throw new ApiClientError("Collection request or response is unsupported. Refresh current state.", 422); }
function id(value: string) { if (!identifier.test(value)) invalid(); return encodeURIComponent(value); }
function query(scope: AutomationScope) {
  if (!positive(scope.projectId) || !positive(scope.workspaceId)) invalid();
  return new URLSearchParams({ project_id: String(scope.projectId), workspace_id: String(scope.workspaceId) });
}
export function validCollectionReason(value: unknown): value is string { return typeof value === "string" && !!value.trim() && text(value, 256) && !/[\r\n\t\u2028\u2029]/.test(value); }
function reason(value: string) { if (!validCollectionReason(value)) invalid(); }
export function isConfirmedCollectionRejection(error: unknown): boolean {
  return error instanceof ApiClientError && [400, 401, 403, 404, 409, 422, 429].includes(error.status) && ["authentication_required", "permission_denied", "binding_conflict", "request_validation_failed", "quota_exceeded"].includes(error.code ?? "");
}
function run(value: unknown, scope: AutomationScope): Run {
  if (!record(value) || value.project_id !== scope.projectId || value.workspace_id !== scope.workspaceId ||
    !positive(value.version) || typeof value.state !== "string" || !runStates.has(value.state) ||
    ![value.id, value.workflow_id, value.revision_id, value.requested_by].every((x) => typeof x === "string" && identifier.test(x)) ||
    !date(value.created_at) || !date(value.deadline_at) || typeof value.cancel_requested !== "boolean" ||
    !(value.cancellation_requested_at === null || date(value.cancellation_requested_at)) ||
    ![value.snapshot_digest, value.definition_digest, value.input_digest].every((x) => typeof x === "string" && /^[a-f0-9]{64}$/.test(x))) invalid();
  return value as Run;
}
async function mutation(path: string, payload: unknown, csrf: string, onSubmit?: () => void): Promise<unknown> {
  if (!csrf || csrf.length > 1024 || /[\r\n]/.test(csrf)) throw new ApiClientError("Fresh sign-in required.", 403);
  let body: string, headers: Headers;
  try { body = JSON.stringify(payload); headers = new Headers({ "Content-Type": "application/json", "X-CSRF-Token": csrf }); } catch { return invalid(); }
  onSubmit?.();
  return requestData(path, { method: "POST", credentials: "same-origin", cache: "no-store", headers, body });
}
export async function cancelCollectionRun(current: Run, scope: AutomationScope, why: string, csrf: string, onSubmit?: () => void): Promise<Run> {
  query(scope); reason(why); run(current, scope);
  const result = run(await mutation(`${base}/runs/${id(current.id)}/cancel`, { expected_version: current.version, reason: why }, csrf, onSubmit), scope);
  if (result.id !== current.id || result.workflow_id !== current.workflow_id || result.revision_id !== current.revision_id || result.version < current.version) invalid();
  return result;
}
export async function startCollectedRun(payload: CollectedRunRequest, scope: AutomationScope, csrf: string, onSubmit?: () => void): Promise<Run> {
  query(scope); reason(payload.reason); id(payload.workflow_id); id(payload.revision_id); id(payload.idempotency_key);
  if (payload.workspace_id !== scope.workspaceId) invalid();
  const result = run(await mutation(`${base}/runs`, payload, csrf, onSubmit), scope);
  if (result.workflow_id !== payload.workflow_id || result.revision_id !== payload.revision_id) invalid();
  return result;
}

const kinds = ["source_bound", "collection", "screened_upload", "analysis"] as const;
const stages = ["not_observed", "bound", "pending", "claimed", "running", "received", "finalized", "succeeded", "failed", "timed_out", "cancelled", "stale"] as const;
const diagnoses = ["execution_disabled", "eligible", "profile_unavailable", "no_runner", "runner_inactive", "profile_mismatch", "tool_mismatch", "runner_version_mismatch", "protocol_mismatch", "tags_mismatch", "credential_unavailable", "heartbeat_stale", "runner_busy", "details_unavailable"] as const;
export type CollectionDiagnosis = { code: typeof diagnoses[number]; correction: string; eligible: boolean };
export type CollectionObservation = { kind: typeof kinds[number]; state: typeof stages[number]; event_at: string | null };
export type CollectionItem = { step_id: string; repository_id: string; commit_sha: string; profile_digest: string; attempt_id: string | null; attempt_number: number | null; attempt_state: string | null; lease_until: string | null; routing_failure: "no_eligible_runner" | null; observations: CollectionObservation[]; diagnosis: CollectionDiagnosis };
export type CollectionView = { version: 1; run_id: string; project_id: number; workspace_id: number; run_version: number; observed_at: string; finite_wait_seconds: 0; items: CollectionItem[]; cancellation: { requested: boolean; requested_at: string | null; owned_processes: "not_confirmed"; external_stop: "not_confirmed"; external_possible: boolean; can_cancel: boolean }; limitations: string[] };
export type ReadinessSource = { step_id: string; repository_id: string | null; commit_sha: string | null; profile_digest: string; inputs_required: boolean; diagnosis: CollectionDiagnosis };
export type CollectionReadiness = { version: 1; workflow_id: string; revision_id: string; project_id: number; workspace_id: number; observed_at: string; finite_wait_seconds: 0; execution_enabled: boolean; can_request: boolean; items: ReadinessSource[] };
const digest = (x: unknown) => typeof x === "string" && /^sha256:[a-f0-9]{64}$/.test(x);
const commit = (x: unknown) => typeof x === "string" && /^[a-f0-9]{40}$/.test(x);
const identity = (x: unknown) => typeof x === "string" && identifier.test(x);
function checkDiagnosis(value: unknown): value is CollectionDiagnosis {
  return record(value) && typeof value.code === "string" && diagnoses.includes(value.code as CollectionDiagnosis["code"]) && text(value.correction, 1024) && value.eligible === (value.code === "eligible");
}
function common(value: unknown, scope: AutomationScope): value is Record<string, unknown> {
  return record(value) && value.version === 1 && value.project_id === scope.projectId && value.workspace_id === scope.workspaceId && date(value.observed_at) && value.finite_wait_seconds === 0 && Array.isArray(value.items) && value.items.length <= 50;
}
export async function getCollectionView(runId: string, scope: AutomationScope, signal?: AbortSignal): Promise<CollectionView> {
  const value = await requestData<unknown>(`${base}/runs/${id(runId)}/collection?${query(scope)}`, { credentials: "same-origin", cache: "no-store", signal });
  if (!common(value, scope) || value.run_id !== runId || !positive(value.run_version) || !Array.isArray(value.items) || !Array.isArray(value.limitations) || value.limitations.length > 8 || !value.limitations.every((x) => text(x)) || !record(value.cancellation)) invalid();
  const c = value.cancellation;
  if (typeof c.requested !== "boolean" || !(c.requested_at === null || date(c.requested_at)) || c.owned_processes !== "not_confirmed" || c.external_stop !== "not_confirmed" || typeof c.external_possible !== "boolean" || typeof c.can_cancel !== "boolean") invalid();
  const ids = new Set();
  for (const item of value.items) {
    if (!record(item) || !identity(item.step_id) || ids.has(item.step_id) || !identity(item.repository_id) || !commit(item.commit_sha) || !digest(item.profile_digest) || !(item.attempt_id === null || identity(item.attempt_id)) || !(item.attempt_number === null || positive(item.attempt_number)) || !(item.attempt_state === null || typeof item.attempt_state === "string" && ["pending", "claimed", "running", "succeeded", "failed", "timed_out", "cancelled", "expired", "interrupted", "delivery_unknown"].includes(item.attempt_state)) || !(item.lease_until === null || date(item.lease_until)) || !(item.routing_failure === null || item.routing_failure === "no_eligible_runner") || !checkDiagnosis(item.diagnosis) || !Array.isArray(item.observations) || item.observations.length !== 4) invalid();
    ids.add(item.step_id);
    for (const [index, observation] of item.observations.entries()) if (!record(observation) || observation.kind !== kinds[index] || typeof observation.state !== "string" || !stages.includes(observation.state as CollectionObservation["state"]) || !(observation.event_at === null || date(observation.event_at))) invalid();
  }
  return value as CollectionView;
}
export async function getCollectionReadiness(workflowId: string, revisionId: string, scope: AutomationScope, signal?: AbortSignal): Promise<CollectionReadiness> {
  const value = await requestData<unknown>(`${base}/workflows/${id(workflowId)}/revisions/${id(revisionId)}/collection?${query(scope)}`, { credentials: "same-origin", cache: "no-store", signal });
  if (!common(value, scope) || value.workflow_id !== workflowId || value.revision_id !== revisionId || typeof value.execution_enabled !== "boolean" || typeof value.can_request !== "boolean" || !Array.isArray(value.items)) invalid();
  const ids = new Set();
  for (const item of value.items) {
    if (!record(item) || !identity(item.step_id) || ids.has(item.step_id) || !(item.repository_id === null || identity(item.repository_id)) || !(item.commit_sha === null || commit(item.commit_sha)) || !digest(item.profile_digest) || typeof item.inputs_required !== "boolean" || !checkDiagnosis(item.diagnosis)) invalid();
    ids.add(item.step_id);
  }
  return value as CollectionReadiness;
}

export function validCollectedReportProvenance(value: unknown, runId: string): boolean {
  if (!record(value) || value.kind !== "collected" || value.version !== 1 || !record(value.scope) || !record(value.custody)) return false;
  const scope = value.scope, custody = value.custody;
  return scope.version === 1 && scope.run_id === runId && scope.audience === "runner-task-v1" &&
    [scope.runner_id, scope.step_id].every(identity) && [scope.project_id, scope.workspace_id].every((x) => typeof x === "string" && /^[1-9]\d*$/.test(x) && Number.isSafeInteger(Number(x))) &&
    [scope.attempt, scope.fence, scope.coordinator_generation, scope.authorization_epoch, scope.restore_epoch].every(positive) && date(scope.lease_deadline) &&
    identity(value.repository_id) && commit(value.commit_sha) && [value.profile_digest, value.command_digest, value.argv_digest, value.raw_local_digest, value.sanitized_digest].every(digest) &&
    (value.tool === "opentofu" || value.tool === "terraform") && typeof value.tool_version === "string" && /^\d+\.\d+\.\d+$/.test(value.tool_version) &&
    value.redaction_version === 1 && (value.exit_code === 0 || value.exit_code === 2) && date(value.collected_at) && date(value.source_deadline) &&
    custody.version === 1 && identity(custody.handle) && custody.raw_local_digest === value.raw_local_digest && date(custody.expires_at) &&
    Date.parse(value.collected_at) < Date.parse(value.source_deadline) && Date.parse(value.source_deadline) <= Date.parse(custody.expires_at) && Date.parse(custody.expires_at) - Date.parse(value.collected_at) <= 3_600_000 && text(value.limitation);
}
