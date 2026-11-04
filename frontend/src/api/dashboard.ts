import type { ApiEnvelope } from "./client";
import { ApiClientError, requestData, requestEnvelope } from "./client";
import type { components } from "./schema";

export type AnalysisReport = components["schemas"]["PersistedReportData"];
export type AnalysisRun = components["schemas"]["AnalysisRunData"];
export type Project = components["schemas"]["ProjectData"];
export type StatsSummary = components["schemas"]["StatsSummaryData"];
export type VerdictDistribution = components["schemas"]["VerdictDistributionData"];

export type AnalysisRunEnvelope = ApiEnvelope<AnalysisRun, components["schemas"]["AnalysisRunMetaPayload"]>;

export type DashboardScope = {
  projectId?: number;
};

function scopedParams(scope: DashboardScope = {}) {
  const params = new URLSearchParams();
  if (scope.projectId) {
    params.set("project_id", String(scope.projectId));
  }
  return params;
}

function withQuery(path: string, params: URLSearchParams) {
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function getProjects(options?: { signal?: AbortSignal }): Promise<Project[]> {
  return requestData<Project[]>("/api/v1/projects", { signal: options?.signal });
}

export async function getProjectsForCreation(): Promise<Project[]> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try { return await getProjects({ signal: controller.signal }); }
  finally { clearTimeout(timeout); }
}

export type NewProject = Pick<components["schemas"]["ProjectCreateRequest"], "project_key" | "display_name" | "description">;

export async function createProject(input: NewProject, csrfToken?: string | null): Promise<Project> {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(input.project_key)) {
    throw new ApiClientError("Project key must use lowercase letters, numbers and hyphens.", 422);
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  let project: Project;
  try {
    project = await requestData<Project>("/api/v1/projects", {
    method: "POST", credentials: "same-origin", cache: "no-store", signal: controller.signal,
    headers: { "Content-Type": "application/json", ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}) },
    body: JSON.stringify({ project_key: input.project_key, display_name: input.display_name, ...(input.description ? { description: input.description } : {}) }),
  });
  } finally { clearTimeout(timeout); }
  // HTTP success alone does not confirm a usable created project.
  if (!project || !Number.isSafeInteger(project.id) || project.id <= 0 || typeof project.project_key !== "string" || project.project_key !== input.project_key || typeof project.display_name !== "string") {
    throw new ApiClientError("Unexpected API response.", 200);
  }
  return project;
}

export function getStatsSummary(scope: DashboardScope = {}): Promise<StatsSummary> {
  return requestData<StatsSummary>(withQuery("/api/v1/stats/summary", scopedParams(scope)));
}

export function getVerdictDistribution(scope: DashboardScope = {}): Promise<VerdictDistribution> {
  const params = scopedParams(scope);
  params.set("days", "30");
  return requestData<VerdictDistribution>(withQuery("/api/v1/stats/verdict-distribution", params));
}

export function getRecentAnalyses(scope: DashboardScope = {}): Promise<AnalysisReport[]> {
  const params = scopedParams(scope);
  params.set("page_size", "5");
  return requestData<AnalysisReport[]>(withQuery("/api/v1/analyses", params));
}

export function createAnalysis({
  files,
  projectId,
}: {
  files: File[];
  projectId: number;
}): Promise<AnalysisRunEnvelope> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
    form.append("artifact_paths", file.webkitRelativePath || file.name);
  }
  form.append("project_id", String(projectId));

  return requestEnvelope<AnalysisRunEnvelope>("/api/v1/analyses", {
    method: "POST",
    body: form,
    headers: {
      "X-DeployWhisper-Trigger-Type": "dashboard_upload",
      "X-DeployWhisper-Actor": "react_dashboard",
    },
  });
}
