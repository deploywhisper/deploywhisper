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
