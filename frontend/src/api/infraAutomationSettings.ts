import { ApiClientError, requestData } from "./client";
import type { components } from "./schema";
export type AutomationSettings = components["schemas"]["AutomationSettings"];
export type AutomationPolicy = components["schemas"]["AutomationPolicy"];
export type Membership = components["schemas"]["MembershipView"];
export type TargetPage = components["schemas"]["TargetPage"];
export type TargetView = components["schemas"]["TargetView"];
export const settingsFields: { key: Exclude<keyof AutomationSettings, "enabled">; label: string; min: number; max: number }[] = [
  { key: "max_workflows", label: "Workflow limit", min: 1, max: 1000 },
  { key: "max_revisions_per_workflow", label: "Revisions per workflow", min: 1, max: 1000 },
  { key: "max_active_runs", label: "Active run limit", min: 1, max: 10 },
  { key: "max_queued_runs", label: "Queued run limit", min: 1, max: 1000 },
  { key: "max_artifact_bytes", label: "Artifact byte limit", min: 1, max: 8388608 },
  { key: "retention_seconds", label: "Retention (seconds)", min: 86400, max: 31536000 },
  { key: "evidence_ttl_seconds", label: "Evidence lifetime (seconds)", min: 60, max: 3600 },
  { key: "approval_ttl_seconds", label: "Approval lifetime (seconds)", min: 60, max: 3600 },
  { key: "credential_ttl_seconds", label: "Credential lifetime (seconds)", min: 60, max: 3600 },
];
const positive = (n: unknown): n is number => typeof n === "number" && Number.isSafeInteger(n) && n > 0;
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const invalid = (): never => { throw new ApiClientError("Automation settings are unsupported. Refresh current state.", 422); };
const read = <T>(url: string, signal?: AbortSignal) => requestData<T>(url, { credentials: "same-origin", cache: "no-store", signal });
export function validateAutomationSettings(value: AutomationSettings): string[] {
  if (!record(value)) return ["Settings are unavailable."];
  const known = ["enabled", ...settingsFields.map(({ key }) => key)].sort();
  if (JSON.stringify(Object.keys(value).sort()) !== JSON.stringify(known)) return ["Settings fields are unsupported. Refresh current state."];
  const errors = settingsFields.filter(({ key, min, max }) => !Number.isSafeInteger(value[key]) || value[key] < min || value[key] > max).map(({ label, min, max }) => `${label} must be an integer from ${min} to ${max}.`);
  if (typeof value.enabled !== "boolean") errors.push("Execution enablement must be true or false.");
  if (Math.max(value.approval_ttl_seconds, value.credential_ttl_seconds) > value.evidence_ttl_seconds) errors.push("Approval and credential lifetimes cannot exceed evidence lifetime.");
  return errors;
}
function policy(value: AutomationPolicy, projectId: number) {
  if (!record(value) || value.project_id !== projectId || !Number.isSafeInteger(value.version) || value.version < 0 || !positive(value.authorization_epoch) || !positive(value.restore_epoch) || validateAutomationSettings(value.settings).length) invalid();
  return value;
}
export async function getAutomationSettings(projectId: number, signal?: AbortSignal) {
  if (!positive(projectId)) invalid();
  return policy(await read<AutomationPolicy>(`/api/v1/infra-automation/settings?project_id=${projectId}`, signal), projectId);
}
export async function saveAutomationSettings(projectId: number, version: number, settings: AutomationSettings, reason: string, csrf: string) {
  if (!csrf || csrf.length > 1024 || /[\r\n]/.test(csrf)) throw new ApiClientError("Sign in again before saving.", 403);
  if (!positive(projectId) || !Number.isSafeInteger(version) || version < 0 || validateAutomationSettings(settings).length || !reason.trim() || reason.length > 256 || /[\u0000-\u001f\u007f-\u009f\u2028\u2029]/.test(reason)) invalid();
  const value = await requestData<AutomationPolicy>("/api/v1/infra-automation/settings", { method: "PATCH", credentials: "same-origin", cache: "no-store", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ project_id: projectId, expected_version: version, settings, reason }) });
  const checked = policy(value, projectId);
  if (checked.version < version || JSON.stringify(Object.entries(checked.settings).sort()) !== JSON.stringify(Object.entries(settings).sort())) invalid();
  return checked;
}
export async function getSettingsMemberships(projectId: number, projectKey: string, signal?: AbortSignal) {
  if (!positive(projectId) || !projectKey) invalid();
  const value = await read<Membership[]>(`/api/v1/projects/${encodeURIComponent(projectKey)}/memberships`, signal);
  if (!Array.isArray(value) || value.some((m) => !record(m) || m.project_id !== projectId || typeof m.principal_id !== "string" || typeof m.enabled !== "boolean" || typeof m.role !== "string" || !(m.workspace_id === null || positive(m.workspace_id)) || !positive(m.authorization_version))) invalid();
  return value;
}
export async function getSettingsTargets(projectId: number, workspaceId: number, cursor?: string, signal?: AbortSignal) {
  if (!positive(projectId) || !positive(workspaceId) || (cursor && !/^[A-Za-z0-9_.:-]{1,128}$/.test(cursor))) invalid();
  const params = new URLSearchParams({ project_id: String(projectId), workspace_id: String(workspaceId), limit: "25" });
  if (cursor) params.set("cursor", cursor);
  const page = await read<TargetPage>(`/api/v1/infra-automation/targets?${params}`, signal);
  if (!record(page) || !Array.isArray(page.items) || page.items.length > 25 || !record(page.cursor) || page.items.some((t) => !record(t) || t.project_id !== projectId || t.workspace_id !== workspaceId || typeof t.id !== "string" || !positive(t.version) || typeof t.enabled !== "boolean" || typeof t.environment !== "string" || typeof t.receiver_id !== "string")) invalid();
  if (!(page.cursor.next_cursor === null || typeof page.cursor.next_cursor === "string")) invalid();
  return page;
}
export async function getSettingsTarget(id: string, projectId: number, workspaceId: number, signal?: AbortSignal) {
  if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(id) || !positive(projectId) || !positive(workspaceId)) invalid();
  const value = await read<TargetView>(`/api/v1/infra-automation/targets/${encodeURIComponent(id)}?project_id=${projectId}&workspace_id=${workspaceId}`, signal);
  if (!record(value) || value.id !== id || value.project_id !== projectId || value.workspace_id !== workspaceId || !positive(value.version) || !record(value.definition) || typeof value.definition.canonical_target !== "string" || typeof value.definition.enabled !== "boolean" || typeof value.definition.environment !== "string" || typeof value.definition.receiver_id !== "string" || typeof value.definition.pipeline_workflow_revision !== "string") invalid();
  return value;
}
