import type { ApiEnvelope } from "./client";
import { requestEnvelope } from "./client";
import type { components } from "./schema";

export type HistoryReport = components["schemas"]["AnalysisReportData"] & {
  previous_scan_diff?: {
    previous_report_id: number;
    previous_created_at: string;
    score_delta: number;
    score_direction: "up" | "down" | "flat";
    previous_severity: string;
    current_severity: string;
    previous_recommendation: string;
    current_recommendation: string;
  } | null;
};

export type HistoryMeta = components["schemas"]["CountMetaPayload"];
export type HistoryEnvelope = ApiEnvelope<HistoryReport[], HistoryMeta>;

export type HistoryFilters = {
  projectId?: number;
  severity?: string;
  recommendation?: string;
  search?: string;
  page: number;
  pageSize: number;
};

export type DeleteAnalysesEnvelope = ApiEnvelope<
  {
    requested_count: number;
    deleted_count: number;
    deleted_ids: number[];
  },
  components["schemas"]["MetaPayload"]
>;

export function buildHistoryQueryParams(filters: HistoryFilters) {
  const params = new URLSearchParams();
  if (filters.projectId) {
    params.set("project_id", String(filters.projectId));
  }
  if (filters.severity && filters.severity !== "all") {
    params.set("severity", filters.severity);
  }
  if (filters.recommendation && filters.recommendation !== "all") {
    params.set("recommendation", filters.recommendation);
  }
  const search = filters.search?.trim();
  if (search) {
    params.set("search", search);
  }
  params.set("page", String(filters.page));
  params.set("page_size", String(filters.pageSize));
  return params;
}

export function getHistory(filters: HistoryFilters): Promise<HistoryEnvelope> {
  const params = buildHistoryQueryParams(filters);
  return requestEnvelope<HistoryEnvelope>(`/api/v1/analyses?${params.toString()}`);
}

export function deleteAnalyses(ids: number[]): Promise<DeleteAnalysesEnvelope> {
  return requestEnvelope<DeleteAnalysesEnvelope>("/api/v1/analyses", {
    method: "DELETE",
    body: JSON.stringify({ ids }),
    headers: {
      "Content-Type": "application/json",
    },
  });
}
