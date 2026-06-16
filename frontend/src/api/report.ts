import type { ApiEnvelope } from "./client";
import { requestData, requestEnvelope } from "./client";
import type { components } from "./schema";

export type ReportDetail = components["schemas"]["AnalysisDetailData"];
export type FindingFeedbackEvent = components["schemas"]["FeedbackEventData"];

export type ReportScope = {
  publicView?: boolean;
  comparePrevious?: boolean;
};

function reportPath(reportId: number, scope: ReportScope = {}) {
  const base = scope.publicView
    ? `/api/v1/analyses/${reportId}/shared`
    : `/api/v1/analyses/${reportId}`;
  if (scope.publicView && scope.comparePrevious) {
    return `${base}?compare=previous`;
  }
  return base;
}

export function getReportDetail(reportId: number, scope: ReportScope = {}): Promise<ReportDetail> {
  return requestData<ReportDetail>(reportPath(reportId, scope));
}

export function unlockSharedReport(reportId: number, password: string): Promise<ReportDetail> {
  return requestData<ReportDetail>(`/api/v1/analyses/${reportId}/shared/unlock`, {
    method: "POST",
    body: JSON.stringify({ password }),
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export function submitFindingFeedback({
  reportId,
  findingId,
  outcome,
}: {
  reportId: number;
  findingId: string;
  outcome: "useful" | "noisy" | "false_positive";
}): Promise<ApiEnvelope<FindingFeedbackEvent>> {
  return requestEnvelope<ApiEnvelope<FindingFeedbackEvent>>(
    `/api/v1/analyses/${reportId}/findings/${encodeURIComponent(findingId)}/feedback`,
    {
      method: "POST",
      body: JSON.stringify({ outcome }),
      headers: {
        "Content-Type": "application/json",
      },
    },
  );
}
