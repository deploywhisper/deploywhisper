import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { getRun, getRunReports, type AutomationScope, type Run, type RunReports } from "../api/infraAutomation";
import { Card } from "../components/ui/Card";
import { useIdentity } from "./IdentitySession";
import { scopeQuery } from "./InfraAutomationShared";
import { Uncertainty, useEvidenceDeadlineRefresh } from "./InfraAutomationRun";

export function isAutomationRunIdentifier(value: string | null): value is string {
  return value !== null && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value);
}

export function verifiedReportRelation(run: Run, reports: RunReports, runId: string, reportId: number, projectId: number): RunReports["items"][number] | null {
  if (run.id !== runId || run.project_id !== projectId) return null;
  return reports.items.find((link) => link.run_id === runId && link.report_id === reportId && link.report_url === `/reports/${reportId}`) ?? null;
}

export function ReportAutomationProvenance({ link, evidence, scope }: { scope?: AutomationScope; link: RunReports["items"][number]; evidence?: RunReports["evidence_status"] }) {
  return <Card eyebrow="Verified run relation" title="Uploaded preflight context">
    <p><Link to={`/infra-automation/runs/${encodeURIComponent(link.run_id)}${scope ? scopeQuery(scope) : ""}`}>Back to run {link.run_id}</Link></p>
    <p>{link.provenance.limitation}</p><p>Uploaded evidence is advisory and not eligible for approval.</p>
    <Uncertainty limitations={link.limitations} todos={link.context_todos} />
    {evidence && <><p>Evidence {evidence.status} · evaluated {evidence.evaluated_at} · deadline {evidence.evidence_deadline}</p><Uncertainty limitations={evidence.limitations.filter((item) => !link.limitations.includes(item))} todos={evidence.context_todos.filter((item) => !link.context_todos.includes(item))} /></>}
  </Card>;
}

function ProtectedReportContext({ runId, reportId, projectId }: { runId: string; reportId: number; projectId: number }) {
  const identity = useIdentity();
  const relation = useQuery({
    queryKey: ["automation", identity.epoch, projectId, "report-context", reportId, runId],
    queryFn: async ({ signal }) => {
      const [run, reports] = await Promise.all([getRun(runId, signal), getRunReports(runId, signal)]);
      const link = verifiedReportRelation(run, reports, runId, reportId, projectId);
      return link ? { link, evidence: reports.evidence_status, scope: { projectId: run.project_id, workspaceId: run.workspace_id } } : null;
    },
    enabled: identity.status === "ready" && !!identity.principal && !identity.loading,
    retry: false, gcTime: 0, refetchOnWindowFocus: true,
  });
  useEvidenceDeadlineRefresh(!relation.error && identity.status === "ready" ? relation.data?.evidence : undefined, relation.refetch);
  // Context is optional: denial or an unrelated URL must never obscure the canonical report.
  if (identity.status !== "ready" || identity.loading || relation.error || !relation.data) return null;
  return <ReportAutomationProvenance link={relation.data.link} evidence={relation.data.evidence} scope={relation.data.scope} />;
}

export function ReportAutomationContext({ reportId, projectId, publicView = false }: { reportId: number; projectId: number; publicView?: boolean }) {
  const [params] = useSearchParams();
  const runId = params.get("automation_run");
  if (publicView || params.getAll("automation_run").length !== 1 || !isAutomationRunIdentifier(runId)) return null;
  return <ProtectedReportContext key={`${reportId}:${projectId}:${runId}`} runId={runId} reportId={reportId} projectId={projectId} />;
}
