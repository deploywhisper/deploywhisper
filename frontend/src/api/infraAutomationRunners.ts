import { ApiClientError, requestData } from "./client";
import type { AutomationScope } from "./infraAutomation";

export type RunnerProfile = { profile_digest: string; tool: "opentofu" | "terraform"; tool_version: string; runner_version: string; tags: string[] };
export type RunnerCapabilities = { version: 1; project_id: number; workspace_id: number; evaluated_at: string; can_read_health: boolean; can_enroll: boolean; can_rotate: boolean; can_revoke: boolean; production_eligible: boolean; execution_enabled: boolean; restriction: "none" | "https_required" | "privileged_role_required" | "administrator_required" | "execution_disabled"; profile_status: "available" | "not_configured" | "unavailable"; configured_profiles: RunnerProfile[] };
export type RunnerHealth = { id: string; project_id: number; workspace_id: number; tags: string[]; tool: string; tool_version: string | null; profile_digest: string; runner_version: string; protocol_version: 1; generation: number; status: "pending" | "active" | "revoked"; last_seen_at: string | null; credential_expires_at: string | null; isolation_qualified: false; current_task: { run_id: string; step_id: string; attempt_id: string } | null; evaluated_at: string; connectivity: "online" | "stale" | "offline"; heartbeat_age_seconds: number | null; online_threshold_seconds: 60; offline_threshold_seconds: 180; connectivity_reason: "heartbeat_current" | "heartbeat_stale" | "heartbeat_missing" | "heartbeat_expired" | "clock_unavailable"; credential_status: "pending" | "valid" | "expired" | "revoked" | "unavailable"; profile_status: "registered" | "not_registered" | "unavailable" };
export type RunnerCursor = { version: 1; snapshot_id: string; next_cursor: string | null; limit: number; last_sequence: number; truncated: boolean; gap: boolean };
export type RunnerHealthPage = { items: RunnerHealth[]; cursor: RunnerCursor };
export type EnrollmentReveal = { enrollment: { version: 1; audience: "runner-enrollment-v1"; enrollment_id: string; runner_id: string; project_id: string; workspace_id: string; expires_at: string; one_use: true }; token: string };
export type CredentialReveal = { runner_id: string; token: string; expires_at: string; generation: number; audience: "runner-task-v1" };
export type RunnerRegistration = Pick<RunnerHealth, "id" | "project_id" | "workspace_id" | "tags" | "tool" | "profile_digest" | "runner_version" | "protocol_version" | "generation" | "status" | "last_seen_at" | "credential_expires_at" | "isolation_qualified">;

const base = "/api/v1/infra-automation";
const identifier = (value: unknown): value is string => typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value) && !/(?:runner|enroll)-v1-/.test(value);
const digest = (value: unknown): value is string => typeof value === "string" && /^sha256:[a-f0-9]{64}$/.test(value);
const positive = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value > 0;
const nonnegative = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const member = (value: unknown, options: readonly string[]) => typeof value === "string" && options.includes(value);
const tags = (value: unknown, maximum = 16): value is string[] => Array.isArray(value) && value.length <= maximum && value.every(identifier);
const onlyKeys = (value: Record<string, unknown>, allowed: readonly string[]) => Object.keys(value).every((key) => allowed.includes(key));
const registrationKeys = ["id", "project_id", "workspace_id", "tags", "tool", "profile_digest", "runner_version", "protocol_version", "generation", "status", "last_seen_at", "credential_expires_at", "isolation_qualified"];
const utc = (value: unknown): value is string => typeof value === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().replace(".000Z", "Z") === value;
const nullableUtc = (value: unknown) => value === null || utc(value);
const token = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 256 && /^[\x21-\x7e]+$/.test(value) && value !== "**********";
const version = (value: unknown): value is string => typeof value === "string" && value.length <= 64 && /^\d+\.\d+\.\d+$/.test(value);
function invalid(): never { throw new ApiClientError("Runner request or response is unsupported. Refresh current state.", 422); }
function invalidMutationResponse(): never { throw new ApiClientError("Runner mutation response could not be verified. Refresh current state without repeating the request.", 502); }
function scopeQuery(scope: AutomationScope): URLSearchParams { if (!positive(scope.projectId) || !positive(scope.workspaceId)) invalid(); return new URLSearchParams({ project_id: String(scope.projectId), workspace_id: String(scope.workspaceId) }); }
function id(value: string) { if (!identifier(value)) invalid(); return encodeURIComponent(value); }
function profile(value: unknown): value is RunnerProfile { return record(value) && digest(value.profile_digest) && member(value.tool, ["opentofu", "terraform"]) && version(value.tool_version) && identifier(value.runner_version) && tags(value.tags, 32) && onlyKeys(value, ["profile_digest", "tool", "tool_version", "runner_version", "tags"]); }
function validReason(value: string) { return value.trim().length > 0 && value.length <= 256 && !/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/.test(value); }
function registration(value: unknown): value is RunnerRegistration {
  return record(value) && identifier(value.id) && positive(value.project_id) && positive(value.workspace_id) && tags(value.tags) && identifier(value.tool) && digest(value.profile_digest) && identifier(value.runner_version) && value.protocol_version === 1 && positive(value.generation) && member(value.status, ["pending", "active", "revoked"]) && nullableUtc(value.last_seen_at) && nullableUtc(value.credential_expires_at) && value.isolation_qualified === false;
}
function health(value: unknown, scope: AutomationScope): value is RunnerHealth {
  if (!registration(value) || value.project_id !== scope.projectId || value.workspace_id !== scope.workspaceId) return false;
  const row = value as unknown as Record<string, unknown>, task = row.current_task;
  return onlyKeys(row, [...registrationKeys, "current_task", "evaluated_at", "connectivity", "heartbeat_age_seconds", "online_threshold_seconds", "offline_threshold_seconds", "connectivity_reason", "credential_status", "profile_status", "tool_version"]) && utc(row.evaluated_at) && row.online_threshold_seconds === 60 && row.offline_threshold_seconds === 180 && member(row.connectivity_reason, ["heartbeat_current", "heartbeat_stale", "heartbeat_missing", "heartbeat_expired", "clock_unavailable"]) && member(row.connectivity, ["online", "stale", "offline"]) && (row.heartbeat_age_seconds === null || nonnegative(row.heartbeat_age_seconds)) && member(row.credential_status, ["pending", "valid", "expired", "revoked", "unavailable"]) && member(row.profile_status, ["registered", "not_registered", "unavailable"]) && (row.tool_version === null || version(row.tool_version)) && (task === null || (record(task) && onlyKeys(task, ["run_id", "step_id", "attempt_id"]) && identifier(task.run_id) && identifier(task.step_id) && identifier(task.attempt_id)));
}
function read<T>(path: string, signal?: AbortSignal) { return requestData<T>(path, { cache: "no-store", credentials: "same-origin", signal }); }
export function isConfirmedRunnerRejection(failure: unknown): boolean {
  if (!(failure instanceof ApiClientError)) return false;
  const codes: Record<number, string> = { 400: "request_validation_failed", 401: "authentication_required", 403: "permission_denied", 404: "permission_denied", 409: "binding_conflict", 422: "request_validation_failed", 429: "quota_exceeded" };
  return codes[failure.status] !== undefined && failure.code === codes[failure.status];
}
function mutate<T>(path: string, payload: unknown, csrf: string, onSubmit?: () => void): Promise<T> {
  if (!csrf || csrf.length > 1024 || /[\r\n]/.test(csrf)) return Promise.reject(new ApiClientError("Sign in again before managing runners.", 403));
  let body: string, headers: Headers;
  try { body = JSON.stringify(payload); headers = new Headers({ "Content-Type": "application/json", "X-CSRF-Token": csrf }); } catch { return invalid(); }
  onSubmit?.();
  return requestData<T>(`${base}${path}`, { method: "POST", cache: "no-store", credentials: "same-origin", headers, body });
}
export async function getRunnerCapabilities(scope: AutomationScope, signal?: AbortSignal): Promise<RunnerCapabilities> {
  const value = await read<RunnerCapabilities>(`${base}/runner-capabilities?${scopeQuery(scope)}`, signal);
  if (!record(value) || !onlyKeys(value, ["version", "project_id", "workspace_id", "evaluated_at", "can_read_health", "can_enroll", "can_rotate", "can_revoke", "production_eligible", "execution_enabled", "restriction", "profile_status", "configured_profiles"]) || value.version !== 1 || value.project_id !== scope.projectId || value.workspace_id !== scope.workspaceId || !utc(value.evaluated_at) || ![value.can_read_health, value.can_enroll, value.can_rotate, value.can_revoke, value.production_eligible, value.execution_enabled].every((item) => typeof item === "boolean") || !member(value.restriction, ["none", "https_required", "privileged_role_required", "administrator_required", "execution_disabled"]) || !member(value.profile_status, ["available", "not_configured", "unavailable"]) || !Array.isArray(value.configured_profiles) || value.configured_profiles.length > 16 || !value.configured_profiles.every(profile)) invalid();
  if (new Set(value.configured_profiles.map((item) => item.profile_digest)).size !== value.configured_profiles.length) invalid();
  if ((value.can_read_health || value.can_enroll || value.can_rotate || value.can_revoke) && !value.production_eligible) invalid();
  if (!value.can_read_health && (value.can_enroll || value.can_rotate || value.can_revoke || value.configured_profiles.length > 0)) invalid();
  if ((value.can_enroll || value.can_rotate) && !value.execution_enabled) invalid();
  return value;
}
export async function getRunnerHealth(scope: AutomationScope, cursor?: string, signal?: AbortSignal): Promise<RunnerHealthPage> {
  const query = scopeQuery(scope); query.set("limit", "25"); if (cursor) { if (!identifier(cursor)) invalid(); query.set("cursor", cursor); }
  const value = await read<RunnerHealthPage>(`${base}/runners?${query}`, signal);
  if (!record(value) || !onlyKeys(value, ["items", "cursor"]) || !Array.isArray(value.items) || !record(value.cursor)) invalid();
  const page = value.cursor;
  if (!onlyKeys(page, ["version", "snapshot_id", "next_cursor", "limit", "last_sequence", "truncated", "gap"]) || page.version !== 1 || !identifier(page.snapshot_id) || !(page.next_cursor === null || identifier(page.next_cursor)) || !positive(page.limit) || page.limit > 100 || value.items.length > page.limit || !nonnegative(page.last_sequence) || typeof page.truncated !== "boolean" || typeof page.gap !== "boolean" || !value.items.every((row) => health(row, scope))) invalid();
  if (new Set(value.items.map((item) => item.id)).size !== value.items.length) invalid();
  return value;
}
export async function enrollRunner(scope: AutomationScope, selected: RunnerProfile, runnerTags: string[], reason: string, csrf: string, onSubmit?: () => void): Promise<EnrollmentReveal> {
  scopeQuery(scope); if (!profile(selected) || !tags(runnerTags) || !validReason(reason)) invalid();
  const value = await mutate<EnrollmentReveal>("/runners/enrollments", { project_id: scope.projectId, workspace_id: scope.workspaceId, tags: runnerTags, tool: selected.tool, profile_digest: selected.profile_digest, runner_version: selected.runner_version, reason }, csrf, onSubmit);
  if (!record(value) || !onlyKeys(value, ["enrollment", "token"]) || !record(value.enrollment) || !token(value.token) || !value.token.startsWith("enroll-v1-")) invalidMutationResponse();
  const result = value.enrollment;
  if (!onlyKeys(result, ["version", "audience", "enrollment_id", "runner_id", "project_id", "workspace_id", "expires_at", "one_use"]) || result.version !== 1 || result.audience !== "runner-enrollment-v1" || !identifier(result.enrollment_id) || !identifier(result.runner_id) || result.project_id !== String(scope.projectId) || result.workspace_id !== String(scope.workspaceId) || !utc(result.expires_at) || result.one_use !== true) invalidMutationResponse();
  return value;
}
export async function rotateRunner(runnerId: string, reason: string, csrf: string, onSubmit?: () => void): Promise<CredentialReveal> {
  const encoded = id(runnerId); if (!validReason(reason)) invalid();
  const value = await mutate<CredentialReveal>(`/runners/${encoded}/rotate`, { reason }, csrf, onSubmit);
  if (!record(value) || !onlyKeys(value, ["runner_id", "token", "expires_at", "generation", "audience"]) || value.runner_id !== runnerId || !token(value.token) || !value.token.startsWith("runner-v1-") || !utc(value.expires_at) || !positive(value.generation) || value.audience !== "runner-task-v1") invalidMutationResponse();
  return value;
}
export async function revokeRunner(runnerId: string, reason: string, csrf: string, onSubmit?: () => void): Promise<RunnerRegistration> {
  const encoded = id(runnerId); if (!validReason(reason)) invalid();
  const value = await mutate<RunnerRegistration>(`/runners/${encoded}/revoke`, { reason }, csrf, onSubmit);
  if (!registration(value) || !onlyKeys(value, registrationKeys) || value.id !== runnerId || value.status !== "revoked") invalidMutationResponse();
  return value;
}
