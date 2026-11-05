import { ApiClientError, requestData } from "./client";
import type { AutomationScope, Run } from "./infraAutomation";
import type { CollectedRunRequest } from "./infraAutomationCollection";

export type UnitSource = { kind: "uploaded"; repository_source: "unavailable"; path: string } | { kind: "declared_repository"; repository_id: string; commit_sha: string; path: string };
export type DeclaredUnit = { id: string; source: UnitSource; environment: string; target: string; prerequisites: string[] };
export type UnitMap = { version: 1; units: DeclaredUnit[]; affected: string[] };
export type UnitPlan = { version: 1; inventory: UnitMap; waves: string[][]; map_digest: string; waves_digest: string; order_kind: "collection_review" };
export type UnitError = { code: string; message: string; path: (string | number)[] };
export type UnitValidation = { valid: boolean; plan: UnitPlan | null; errors: UnitError[] };
export type UnitRevisionSummary = { inventory_id: string; revision_id: string; version: number; project_id: number; workspace_id: number; map_digest: string; waves_digest: string; created_by: string; created_at: string };
export type UnitRevision = UnitRevisionSummary & { plan: UnitPlan };
export type UnitBinding = { unit_id: string; intake_step_id: string; analysis_step_id: string };
export type UnitRunRequest = { run: CollectedRunRequest; revision_id: string; confirmed_map_digest: string; bindings: (UnitBinding & { artifacts: { name: string; content: string }[] })[] };
export type UnitRunView = { run_id: string; project_id: number; workspace_id: number; run_version: number; available: boolean; snapshot: { revision: UnitRevision; bindings: UnitBinding[]; snapshot_digest: string } | null; evidence: { status: "pending" | "available" | "changed"; combined_digest: string | null; items: { unit_id: string; manifest_digest: string; report_id: number; report_digest: string; source_digest: string }[] } | null; locks: { unit_id: string; canonical_target: string; status: "held" | "resolved" | "broken" | "not_requested" }[] };
const base = "/api/v1/infra-automation";
const record = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const identifier = (v: unknown): v is string => typeof v === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(v);
const digest = (v: unknown): v is string => typeof v === "string" && /^sha256:[a-f0-9]{64}$/.test(v);
const positive = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v > 0;
const texts = (v: unknown, maximum = 25): v is string[] => Array.isArray(v) && v.length <= maximum && v.every(identifier);
const text = (v: unknown, maximum = 1024): v is string => typeof v === "string" && v.length <= maximum && !/[\u0000-\u001f\u007f-\u009f]/.test(v);
function invalid(): never { throw new ApiClientError("Inventory response is unsupported. Refresh current state.", 422); }
function id(v: string) { if (!identifier(v)) invalid(); return encodeURIComponent(v); }
function scopeParams(scope: AutomationScope) { if (!positive(scope.projectId) || !positive(scope.workspaceId)) invalid(); return new URLSearchParams({ project_id: String(scope.projectId), workspace_id: String(scope.workspaceId) }); }
function scoped(v: Record<string, unknown>, scope: AutomationScope) { return v.project_id === scope.projectId && v.workspace_id === scope.workspaceId; }
function checkPlan(v: unknown): v is UnitPlan {
  if (!record(v) || v.version !== 1 || v.order_kind !== "collection_review" || !digest(v.map_digest) || !digest(v.waves_digest) || !record(v.inventory)) return false;
  const map = v.inventory;
  if (map.version !== 1 || !Array.isArray(map.units) || !map.units.length || map.units.length > 25 || !texts(map.affected) || !map.affected.length || !Array.isArray(v.waves) || !v.waves.length || v.waves.length > 25 || !v.waves.every((w) => texts(w) && w.length > 0)) return false;
  for (const u of map.units) {
    if (!record(u) || !identifier(u.id) || !identifier(u.environment) || !identifier(u.target) || !texts(u.prerequisites) || !record(u.source) || !text(u.source.path, 512) || !u.source.path.length) return false;
    if (u.source.kind === "uploaded") { if (u.source.repository_source !== "unavailable") return false; }
    else if (u.source.kind !== "declared_repository" || !identifier(u.source.repository_id) || typeof u.source.commit_sha !== "string" || !/^[a-f0-9]{40}$/.test(u.source.commit_sha)) return false;
  }
  const ids = map.units.map((u) => u.id), waves = v.waves.flat();
  return new Set(ids).size === ids.length && waves.length === ids.length && new Set(waves).size === ids.length && waves.every((x) => ids.includes(x)) && map.affected.every((x) => ids.includes(x));
}
function checkSummary(v: unknown, scope: AutomationScope): v is UnitRevisionSummary {
  return record(v) && scoped(v, scope) && [v.inventory_id, v.revision_id, v.created_by].every(identifier) && positive(v.version) && v.version <= 32 && digest(v.map_digest) && digest(v.waves_digest) && typeof v.created_at === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(v.created_at) && Number.isFinite(Date.parse(v.created_at));
}
function revision(v: unknown, scope: AutomationScope): UnitRevision {
  if (!record(v) || !checkPlan(v.plan)) invalid();
  const plan = v.plan;
  if (!checkSummary(v, scope) || v.map_digest !== plan.map_digest || v.waves_digest !== plan.waves_digest) invalid();
  return v as UnitRevision;
}
async function mutate(path: string, payload: unknown, csrf: string, onSubmit?: () => void): Promise<unknown> {
  if (!csrf || csrf.length > 1024 || /[\r\n]/.test(csrf)) throw new ApiClientError("Fresh sign-in required.", 403);
  const body = JSON.stringify(payload), headers = new Headers({ "Content-Type": "application/json", "X-CSRF-Token": csrf });
  if (new TextEncoder().encode(body).length > 131072) throw new ApiClientError("Inventory request exceeds 128 KiB. Reduce the declared input or artifacts.", 422);
  onSubmit?.();
  return requestData(`${base}${path}`, { method: "POST", credentials: "same-origin", cache: "no-store", headers, body });
}
export async function getUnitInventories(scope: AutomationScope, signal?: AbortSignal): Promise<{ items: UnitRevisionSummary[]; truncated: false }> {
  const value = await requestData<unknown>(`${base}/units?${scopeParams(scope)}`, { credentials: "same-origin", cache: "no-store", signal });
  if (!record(value) || value.truncated !== false || !Array.isArray(value.items) || value.items.length > 25 || !value.items.every((x) => checkSummary(x, scope))) invalid();
  return value as { items: UnitRevisionSummary[]; truncated: false };
}
export async function getUnitRevision(inventoryId: string, revisionId: string, scope: AutomationScope, signal?: AbortSignal): Promise<UnitRevision> {
  const value = revision(await requestData(`${base}/units/${id(inventoryId)}/revisions/${id(revisionId)}?${scopeParams(scope)}`, { credentials: "same-origin", cache: "no-store", signal }), scope);
  if (value.inventory_id !== inventoryId || value.revision_id !== revisionId) invalid(); return value;
}
export async function validateUnitInventory(map: UnitMap, scope: AutomationScope, csrf: string): Promise<UnitValidation> {
  scopeParams(scope);
  const v = await mutate("/units/validate", { project_id: scope.projectId, workspace_id: scope.workspaceId, map }, csrf);
  if (!record(v) || typeof v.valid !== "boolean" || !Array.isArray(v.errors) || v.errors.length > 50 || !v.errors.every((e) => record(e) && text(e.code) && text(e.message) && Array.isArray(e.path) && e.path.length <= 16 && e.path.every((p) => typeof p === "string" && text(p) || Number.isSafeInteger(p)))) invalid();
  if (v.valid ? !checkPlan(v.plan) || v.errors.length > 0 : v.plan !== null || !v.errors.length) invalid();
  return v as UnitValidation;
}
export async function saveUnitInventory(map: UnitMap, scope: AutomationScope, csrf: string, reason: string, current?: UnitRevision, onSubmit?: () => void): Promise<UnitRevision> {
  scopeParams(scope);
  return revision(await mutate("/units", { project_id: scope.projectId, workspace_id: scope.workspaceId, inventory_id: current?.inventory_id ?? null, expected_version: current?.version ?? 0, map, reason }, csrf, onSubmit), scope);
}
export async function startUnitRun(payload: UnitRunRequest, scope: AutomationScope, csrf: string, onSubmit?: () => void): Promise<Run> {
  scopeParams(scope); id(payload.run.workflow_id); id(payload.run.revision_id); id(payload.revision_id);
  if (payload.run.workspace_id !== scope.workspaceId) invalid();
  const v = await mutate("/units/runs", payload, csrf, onSubmit);
  if (!record(v) || !scoped(v, scope) || !identifier(v.id) || !positive(v.version) || v.workflow_id !== payload.run.workflow_id || v.revision_id !== payload.run.revision_id || typeof v.state !== "string" || !["queued", "running", "waiting_approval", "ready_handoff", "handing_off", "external_running", "delivery_unknown", "succeeded", "failed", "stopped_by_gate", "rejected", "expired", "timed_out", "cancelled"].includes(v.state)) invalid();
  return v as Run;
}
export async function getRunUnits(runId: string, scope: AutomationScope, signal?: AbortSignal): Promise<UnitRunView> {
  const v = await requestData<unknown>(`${base}/runs/${id(runId)}/units?${scopeParams(scope)}`, { credentials: "same-origin", cache: "no-store", signal });
  if (!record(v) || !scoped(v, scope) || v.run_id !== runId || !positive(v.run_version) || typeof v.available !== "boolean" || !Array.isArray(v.locks) || v.locks.length > 25) invalid();
  if (!v.available) { if (v.snapshot !== null || v.evidence !== null || v.locks.length) invalid(); return v as UnitRunView; }
  if (!record(v.snapshot) || !digest(v.snapshot.snapshot_digest) || !Array.isArray(v.snapshot.bindings)) invalid();
  const rev = revision(v.snapshot.revision, scope), ids = rev.plan.inventory.units.map((u) => u.id);
  if (v.snapshot.bindings.length !== ids.length || new Set(v.snapshot.bindings.map((b) => b.unit_id)).size !== ids.length || !v.snapshot.bindings.every((b) => record(b) && ids.includes(b.unit_id as string) && identifier(b.intake_step_id) && identifier(b.analysis_step_id))) invalid();
  if (!record(v.evidence) || !["pending", "available", "changed"].includes(v.evidence.status as string) || !(v.evidence.combined_digest === null || digest(v.evidence.combined_digest)) || !Array.isArray(v.evidence.items) || v.evidence.items.length > 25 || !v.evidence.items.every((e) => record(e) && ids.includes(e.unit_id as string) && positive(e.report_id) && [e.manifest_digest, e.report_digest, e.source_digest].every(digest))) invalid();
  if (new Set(v.evidence.items.map((item) => item.unit_id)).size !== v.evidence.items.length) invalid();
  if (v.evidence.status === "available" ? v.evidence.combined_digest === null || v.evidence.items.length !== ids.length : v.evidence.combined_digest !== null) invalid();
  if (v.locks.length !== ids.length || new Set(v.locks.map((l) => l.unit_id)).size !== ids.length || !v.locks.every((l) => record(l) && ids.includes(l.unit_id as string) && identifier(l.canonical_target) && ["held", "resolved", "broken", "not_requested"].includes(l.status as string))) invalid();
  return v as UnitRunView;
}
