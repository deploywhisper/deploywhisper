import type { ApiEnvelope } from "./client";
import { requestData, requestEnvelope } from "./client";
import type { components } from "./schema";

export type Project = components["schemas"]["ProjectData"];
export type SettingsSummary = components["schemas"]["SettingsSummaryData"];
export type ProviderSettingsRequest = components["schemas"]["ProviderSettingsRequest"];
export type ProviderSettingsSave = components["schemas"]["ProviderSettingsSaveData"];
export type TopologyUploadRequest = components["schemas"]["TopologyUploadRequest"];
export type TopologyValidation = components["schemas"]["TopologyValidationData"];
export type TopologyDriftCadence = components["schemas"]["TopologyDriftCadenceData"];
export type CustomSkillStatus = components["schemas"]["CustomSkillStatusData"];
export type CustomSkillUpload = components["schemas"]["CustomSkillUploadData"];
export type SkillRegistryItem = components["schemas"]["SkillRegistryData"];
export type SkillRegistryVersion = components["schemas"]["SkillRegistryVersionData"];

export type IncidentSource = {
  import_source: string;
  title?: string | null;
  freshness_status?: string | null;
  scope_label?: string | null;
  indexed_count: number;
  rejected_count: number;
  redaction_status: string;
  last_indexed_at?: string | null;
  failure_summaries?: {
    source_file: string;
    message: string;
    correction_path?: string | null;
  }[];
};

export type IncidentIngestionStatus = {
  project_id: number;
  workspace_id?: number | null;
  indexed_count: number;
  rejected_count: number;
  redaction_status: string;
  freshness_status: string;
  last_indexed_at?: string | null;
  sources: IncidentSource[];
};

export type SkillListEnvelope = ApiEnvelope<
  SkillRegistryItem[],
  components["schemas"]["SkillRegistryListMetaPayload"]
>;

function scopedParams(scope: { projectId?: number } = {}) {
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

export function getSettingsSummary(projectId?: number): Promise<SettingsSummary> {
  return requestData<SettingsSummary>(withQuery("/api/v1/settings", scopedParams({ projectId })));
}

export function saveProviderSettings(payload: ProviderSettingsRequest): Promise<ProviderSettingsSave> {
  return requestData<ProviderSettingsSave>("/api/v1/settings/provider", {
    method: "PUT",
    body: JSON.stringify(payload),
    headers: { "Content-Type": "application/json" },
  });
}

export function previewTopology(payload: TopologyUploadRequest): Promise<TopologyValidation> {
  return requestData<TopologyValidation>("/api/v1/settings/topology/preview", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: { "Content-Type": "application/json" },
  });
}

export function saveTopology(payload: TopologyUploadRequest): Promise<TopologyValidation> {
  return requestData<TopologyValidation>("/api/v1/settings/topology", {
    method: "PUT",
    body: JSON.stringify(payload),
    headers: { "Content-Type": "application/json" },
  });
}

export function saveDriftCadence(intervalHours: number): Promise<TopologyDriftCadence> {
  return requestData<TopologyDriftCadence>("/api/v1/settings/topology/drift-cadence", {
    method: "PUT",
    body: JSON.stringify({ interval_hours: intervalHours }),
    headers: { "Content-Type": "application/json" },
  });
}

export function uploadCustomSkill(filename: string, content: string): Promise<CustomSkillUpload> {
  return requestData<CustomSkillUpload>("/api/v1/settings/custom-skills", {
    method: "POST",
    body: JSON.stringify({ filename, content }),
    headers: { "Content-Type": "application/json" },
  });
}

export function getIncidentStatus(projectId?: number): Promise<IncidentIngestionStatus> {
  return requestData<IncidentIngestionStatus>(
    withQuery("/api/v1/incidents/ingestion", scopedParams({ projectId })),
  );
}

export function getSkills(filters: {
  search?: string;
  tool?: string;
  tag?: string;
  author?: string;
  sort?: "popularity" | "recency";
  page?: number;
  pageSize?: number;
} = {}): Promise<SkillListEnvelope> {
  const params = new URLSearchParams();
  if (filters.search?.trim()) {
    params.set("search", filters.search.trim());
  }
  if (filters.tool?.trim()) {
    params.set("tool", filters.tool.trim());
  }
  if (filters.tag?.trim()) {
    params.set("tag", filters.tag.trim());
  }
  if (filters.author?.trim()) {
    params.set("author", filters.author.trim());
  }
  if (filters.sort) {
    params.set("sort", filters.sort);
  }
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 50));
  return requestEnvelope<SkillListEnvelope>(withQuery("/api/v1/skills", params));
}

export function getSkill(skillId: string): Promise<SkillRegistryItem> {
  return requestData<SkillRegistryItem>(`/api/v1/skills/${encodeURIComponent(skillId)}`);
}

export function getSkillVersions(skillId: string): Promise<SkillRegistryVersion[]> {
  return requestData<SkillRegistryVersion[]>(`/api/v1/skills/${encodeURIComponent(skillId)}/versions`);
}
