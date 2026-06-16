import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  GitCompare,
  History,
  Layers,
  Network,
  RotateCcw,
  Share2,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

import { ApiClientError } from "../api/client";
import { getReportDetail, submitFindingFeedback, unlockSharedReport, type ReportDetail } from "../api/report";
import {
  Button,
  Card,
  ConfidenceBadge,
  EvidenceTag,
  MonoRef,
  ScoreRing,
  SegmentedTabs,
  SeverityBadge,
  SkeletonCard,
  SkeletonLine,
  VerdictChip,
} from "../components/ui";
import type { Confidence, Severity, Verdict } from "../theme/tokens";
import { Phase6Shell } from "./Phase6Shell";
import "./report.css";

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "findings", label: "Findings" },
  { id: "confidence", label: "Confidence" },
  { id: "context", label: "Context" },
  { id: "rollback", label: "Rollback" },
  { id: "audit", label: "Audit" },
];

type Finding = NonNullable<ReportDetail["findings"]>[number];
type EvidenceItem = NonNullable<ReportDetail["evidence_items"]>[number];
type RollbackPlan = NonNullable<ReportDetail["rollback_plan"]>;
type BlastRadius = NonNullable<ReportDetail["blast_radius"]>;
type ContextCompleteness = NonNullable<ReportDetail["context_completeness"]>;
type ConfidenceLedger = NonNullable<ReportDetail["confidence_ledger"]>;
type FeedbackState = NonNullable<ReportDetail["feedback_state"]>;

function getFindings(report: ReportDetail): Finding[] {
  return report.findings ?? [];
}

function getEvidenceItems(report: ReportDetail): EvidenceItem[] {
  return report.evidence_items ?? [];
}

function getRollbackPlan(report: ReportDetail): RollbackPlan {
  return (
    report.rollback_plan ?? {
      steps: [],
      complexity: "low",
      complexity_score: 1,
      complexity_explanation: "Rollback detail was not persisted for this report.",
      warning: null,
    }
  );
}

function getBlastRadius(report: ReportDetail): BlastRadius {
  return (
    report.blast_radius ?? {
      direct_count: 0,
      transitive_count: 0,
      affected: [],
      warning: "Blast-radius context was not persisted for this report.",
      unmatched_resources: [],
      context_source: {},
      freshness: {
        status: "unknown",
        age_days: null,
        last_imported_at: null,
        warning: null,
      },
      context_state: "unknown",
      context_limitations: [],
    }
  );
}

function getContextCompleteness(report: ReportDetail): ContextCompleteness {
  return (
    report.context_completeness ?? {
      context_score: 0,
      confidence_level: "low",
      insufficient_context: true,
      topology_freshness_days: null,
      topology_last_imported_at: null,
      parser_success_rate: 0,
      parser_success_by_tool: {},
      incident_index_size: 0,
      incident_index_version: null,
      incident_index_freshness_status: null,
      evidence_success_rate: 0,
      context_todos: ["Context completeness was not persisted for this report."],
      partial_context: true,
    }
  );
}

function getConfidenceLedger(report: ReportDetail): ConfidenceLedger {
  return report.confidence_ledger ?? { why_not_lower: [], why_not_higher: [] };
}

function getFeedbackState(report: ReportDetail): FeedbackState {
  return report.feedback_state ?? { finding_feedback: {}, false_negative_by_finding: {}, false_negative_notes: [] };
}

function normalizeSeverity(value: string | null | undefined): Severity {
  const normalized = String(value || "LOW").toUpperCase();
  if (normalized === "CRITICAL" || normalized === "HIGH" || normalized === "MEDIUM" || normalized === "LOW") {
    return normalized;
  }
  return "LOW";
}

function normalizeVerdict(value: string | null | undefined): Verdict {
  const normalized = String(value || "PROCEED").toUpperCase();
  if (normalized === "NO-GO" || normalized === "NO_GO" || normalized === "NO GO") {
    return "NO-GO";
  }
  if (normalized === "CAUTION") {
    return "CAUTION";
  }
  return "PROCEED";
}

function confidenceLevel(value: number | null | undefined): Confidence {
  return (value ?? 0) >= 0.65 ? "HIGH" : "LOW";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDuration(seconds: number | null | undefined) {
  if (!seconds || seconds <= 0) {
    return "n/a";
  }
  return seconds < 60 ? `${Math.round(seconds)}s` : `${Math.round(seconds / 60)}m`;
}

function evidenceForFinding(report: ReportDetail, finding: Finding) {
  const refs = new Set(finding.evidence_refs ?? []);
  return getEvidenceItems(report).filter((item) => refs.has(item.evidence_id) || item.finding_id === finding.finding_id);
}

function firstEvidenceTag(items: EvidenceItem[]) {
  const first = items[0];
  if (!first) {
    return "evidence pending";
  }
  return first.location || first.source_ref || first.evidence_id;
}

function evidenceReference(item: EvidenceItem) {
  return item.location || item.source_ref || item.resource || item.evidence_id;
}

function findingCounts(report: ReportDetail) {
  const findings = getFindings(report);
  const high = findings.filter((finding) => ["high", "critical"].includes(finding.severity)).length;
  const medium = findings.filter((finding) => finding.severity === "medium").length;
  return { high, medium };
}

function totalRollbackMinutes(report: ReportDetail) {
  return (getRollbackPlan(report).steps ?? []).reduce((total, step) => total + (step.estimated_minutes ?? 0), 0);
}

function reportTitle(report: ReportDetail) {
  return report.top_risk || report.narrative_opening || report.parse_summary || `Report #${report.id}`;
}

function Toast({ message }: { message: string | null }) {
  if (!message) {
    return null;
  }
  return (
    <div className="dw-report-toast" role="status">
      <CheckCircle2 size={14} />
      {message}
    </div>
  );
}

function PasswordGate({
  reportId,
  onUnlocked,
}: {
  reportId: number;
  onUnlocked: () => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => unlockSharedReport(reportId, password),
    onSuccess: () => {
      setError(null);
      onUnlocked();
    },
    onError: () => setError("Incorrect password. Try again."),
  });

  return (
    <main className="dw-report-public-gate dw-ui">
      <Card eyebrow="Shared report" title="Password required">
        <p className="dw-report-muted">This shared report is protected by the owner.</p>
        <form
          className="dw-password-form"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <label htmlFor="share-password">Password</label>
          <input
            autoComplete="current-password"
            id="share-password"
            onChange={(event) => setPassword(event.currentTarget.value)}
            type="password"
            value={password}
          />
          {error && <div className="dw-report-error" role="alert">{error}</div>}
          <Button disabled={!password || mutation.isPending} type="submit" variant="primary-gradient">
            Open shared report
          </Button>
        </form>
      </Card>
    </main>
  );
}

function ReportHeader({
  report,
  activeTab,
  setActiveTab,
  publicView,
  copyBriefing,
}: {
  report: ReportDetail;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  publicView: boolean;
  copyBriefing: () => void;
}) {
  const navigate = useNavigate();
  const findings = getFindings(report);
  const evidenceItems = getEvidenceItems(report);
  const findingsTab = tabs.map((tab) => (tab.id === "findings" ? { ...tab, count: findings.length } : tab));
  const compareHref = publicView
    ? `/reports/${report.id}?compare=previous#report-comparison`
    : `/reports/${report.id}?private=1&compare=previous#report-comparison`;

  return (
    <header className="dw-report-header">
      <div className="dw-report-header-inner">
        <div className="dw-report-header-row">
          <button
            aria-label={publicView ? "Back to shared report" : "Back to dashboard"}
            className="dw-report-back"
            onClick={() => (publicView ? navigate(`/reports/${report.id}`) : navigate("/"))}
            type="button"
          >
            <ArrowLeft size={16} />
          </button>
          <ScoreRing score={report.score} size={62} />
          <div className="dw-report-title-block">
            <div className="dw-report-badges">
              <VerdictChip verdict={normalizeVerdict(report.verdict)} />
              <SeverityBadge level={normalizeSeverity(report.severity)} />
              <ConfidenceBadge level={confidenceLevel(report.confidence)} />
              <EvidenceTag>{evidenceItems.length} deterministic items</EvidenceTag>
            </div>
            <h1>{reportTitle(report)}</h1>
            <div className="dw-report-meta">
              <MonoRef>{report.pr_ref || report.trigger_ref || `report-${report.id}`}</MonoRef>
              <span>{report.project.name} - {report.env_label}</span>
              <span className="dw-report-dot">/</span>
              <span>{formatDate(report.created_at)}</span>
              <span className="dw-report-dot">/</span>
              <span className="dw-report-mono">{report.filenames.length} files - {formatDuration(report.analysis_duration_seconds)}</span>
            </div>
          </div>
          <div className="dw-report-actions">
            <Link className="dw-report-action-link" to={compareHref}>
              <GitCompare size={13} /> Compare
            </Link>
            {!publicView && (
              <>
                <Button variant="ghost">
                  <Share2 size={13} /> Share
                </Button>
                <Button onClick={copyBriefing} variant="dark">
                  <Copy size={13} /> Copy briefing
                </Button>
              </>
            )}
          </div>
        </div>
        <SegmentedTabs activeId={activeTab} label="Report sections" onChange={setActiveTab} tabs={findingsTab} />
      </div>
    </header>
  );
}

function DiffBlock({ evidence }: { evidence: EvidenceItem[] }) {
  const file = evidence[0]?.artifact || evidence[0]?.source_ref || "evidence";
  const lines = evidence.length ? evidence : [];
  return (
    <div className="dw-diff-block">
      <div className="dw-diff-title">
        <span className="dw-diff-dots"><span /><span /><span /></span>
        <span>{file}</span>
      </div>
      <div className="dw-diff-body">
        {lines.map((item, index) => (
          <div className={`dw-diff-line ${item.operation === "delete" ? "dw-diff-del" : item.operation === "create" ? "dw-diff-add" : ""}`} key={item.evidence_id}>
            <span className="dw-diff-num">{index + 1}</span>
            <span className="dw-diff-gutter">{item.operation === "delete" ? "-" : item.operation === "create" ? "+" : ""}</span>
            <pre>{item.summary}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}

function Narrative({ report }: { report: ReportDetail }) {
  return (
    <Card eyebrow="OPERATIONAL NARRATIVE" title="What changed, and why it's risky">
      <div className="dw-report-body-copy">
        {report.narrative_degraded && (
          <p className="dw-report-muted-notice">AI narrative unavailable - deterministic findings below are unaffected.</p>
        )}
        <p>{report.narrative_available ? report.narrative_opening : report.top_risk}</p>
        <p>{report.parse_summary}</p>
        {report.filenames.length > 0 && (
          <p>
            Files analyzed: {report.filenames.map((file) => <MonoRef key={file}>{file}</MonoRef>)}.
          </p>
        )}
      </div>
      <div className="dw-report-warning">
        <span><AlertCircle size={14} /></span>
        <div>
          <strong>Verify before deploying</strong>
          <p>{report.advisory.top_risk || report.top_risk}</p>
        </div>
      </div>
    </Card>
  );
}

function OverviewTab({ report, goFindings }: { report: ReportDetail; goFindings: () => void }) {
  const counts = findingCounts(report);
  const findings = getFindings(report);
  const rollback = getRollbackPlan(report);
  const blastRadius = getBlastRadius(report);
  const incident = Math.max(0, ...(report.incident_matches ?? []).map((match) => match.similarity ?? 0));
  const blast = (blastRadius.direct_count ?? 0) + (blastRadius.transitive_count ?? 0);
  const totalMinutes = totalRollbackMinutes(report);
  const context = getContextCompleteness(report);
  const decisionInputs: Array<{ Icon: LucideIcon; label: string; value: string; context: string }> = [
    {
      Icon: Network,
      label: "Blast radius",
      value: `${blast} services`,
      context: `${blastRadius.direct_count} direct - ${blastRadius.transitive_count} transitive`,
    },
    {
      Icon: History,
      label: "Incident match",
      value: incident ? `${Math.round(incident * 100)}%` : "0%",
      context: report.incident_matches?.[0]?.title || "no incident match",
    },
    {
      Icon: RotateCcw,
      label: "Rollback",
      value: `${rollback.steps?.length ?? 0} steps - ~${totalMinutes} min`,
      context: `complexity ${rollback.complexity_score}/5`,
    },
    {
      Icon: ShieldCheck,
      label: "Evidence Law",
      value: report.share_summary.json_payload.evidence_law_status,
      context: report.share_summary.json_payload.evidence_law_detail,
    },
  ];

  return (
    <div className="dw-report-overview-grid">
      <div className="dw-report-stack">
        <Narrative report={report} />
        <Card
          eyebrow="TOP FINDINGS"
          right={<button className="dw-link-button" onClick={goFindings} type="button">All findings <ChevronRight size={13} /></button>}
          title={`${findings.length} findings - ${counts.high} high, ${counts.medium} medium`}
        >
          {findings.length === 0 ? (
            <div className="dw-report-empty">No findings were persisted for this report.</div>
          ) : (
            <ul className="dw-top-findings">
              {findings.slice(0, 5).map((finding) => {
                const evidence = evidenceForFinding(report, finding);
                return (
                  <li key={finding.finding_id}>
                    <SeverityBadge level={normalizeSeverity(finding.severity)} />
                    <span>{finding.title}</span>
                    <EvidenceTag>{firstEvidenceTag(evidence)}</EvidenceTag>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
        {report.comparison && (
          <Card eyebrow="REPORT COMPARISON" title="Compare with previous">
            <pre className="dw-comparison-json" id="report-comparison">{JSON.stringify(report.comparison, null, 2)}</pre>
          </Card>
        )}
      </div>
      <div className="dw-report-stack">
        <Card eyebrow="DECISION INPUTS" title="At a glance">
          <ul className="dw-decision-list">
            {decisionInputs.map(({ Icon, label, value, context }) => (
              <li key={label}>
                <span className="dw-decision-icon"><Icon size={15} /></span>
                <div>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
                <em>{context}</em>
              </li>
            ))}
          </ul>
        </Card>
        <Card eyebrow="CONTEXT QUALITY" title="Completeness">
          <div className="dw-context-score">
            <strong>{context.context_score.toFixed(2)}</strong>
            <span>/1.00</span>
          </div>
          <div className="dw-context-track">
            <span style={{ width: `${Math.round(context.context_score * 100)}%` }} />
          </div>
          <p className="dw-report-muted">{report.share_summary.json_payload.context_completeness.summary}</p>
        </Card>
      </div>
    </div>
  );
}

function FindingsTab({
  report,
  publicView,
  setToast,
}: {
  report: ReportDetail;
  publicView: boolean;
  setToast: (message: string | null) => void;
}) {
  const findings = getFindings(report);
  const [openId, setOpenId] = useState(findings[0]?.finding_id ?? "");
  const queryClient = useQueryClient();
  const feedback = useMutation({
    mutationFn: submitFindingFeedback,
    onSuccess: async () => {
      setToast("Feedback saved.");
      await queryClient.invalidateQueries({ queryKey: ["report", report.id] });
    },
  });

  if (findings.length === 0) {
    return <Card title="Findings"><div className="dw-report-empty">No findings were persisted for this report.</div></Card>;
  }

  return (
    <div className="dw-findings-stack">
      {findings.map((finding) => {
        const open = openId === finding.finding_id;
        const evidence = evidenceForFinding(report, finding);
        const selected = getFeedbackState(report).finding_feedback?.[finding.finding_id]?.outcome_label;
        return (
          <article className={`dw-finding-card${open ? " dw-finding-open" : ""}`} key={finding.finding_id}>
            <button aria-expanded={open} className="dw-finding-summary" onClick={() => setOpenId(open ? "" : finding.finding_id)} type="button">
              <span className={`dw-finding-icon dw-finding-${finding.severity}`}><AlertTriangle size={16} /></span>
              <span className="dw-finding-main">
                <span className="dw-finding-title-row">
                  <strong>{finding.title}</strong>
                  <SeverityBadge level={normalizeSeverity(finding.severity)} />
                  {finding.skill_id && <span className="dw-cross-tool"><Layers size={10} /> Cross-tool</span>}
                </span>
                <span className="dw-finding-description">{finding.description || finding.explanation}</span>
                <span className="dw-finding-evidence">{evidence.map((item) => <EvidenceTag key={item.evidence_id}>{evidenceReference(item)}</EvidenceTag>)}</span>
              </span>
              <ChevronDown className="dw-finding-chevron" size={16} />
            </button>
            {open && (
              <div className="dw-finding-expanded">
                {evidence.length > 0 ? <DiffBlock evidence={evidence} /> : <p className="dw-report-muted">No inspectable evidence block was persisted for this finding.</p>}
                {!publicView && (
                  <div className="dw-feedback-row">
                    <span>Was this finding useful?</span>
                    {[
                      ["useful", "Useful"],
                      ["noisy", "Noisy"],
                      ["false_positive", "False positive"],
                    ].map(([outcome, label]) => (
                      <button
                        className={`dw-feedback-pill${selected === outcome ? " dw-feedback-selected" : ""}`}
                        disabled={feedback.isPending}
                        key={outcome}
                        onClick={() => feedback.mutate({ reportId: report.id, findingId: finding.finding_id, outcome: outcome as "useful" | "noisy" | "false_positive" })}
                        type="button"
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

function ConfidenceTab({ report }: { report: ReportDetail }) {
  const ledger = getConfidenceLedger(report);
  const evidenceItems = getEvidenceItems(report);
  const ledgerCard = (title: string, items: string[], hot = false) => (
    <Card eyebrow="CONFIDENCE LEDGER" title={title}>
      <ol className="dw-ledger-list">
        {(items.length ? items : ["No ledger entries were persisted for this boundary."]).map((item, index) => (
          <li key={`${title}-${index}`}>
            <span className={hot ? "dw-ledger-hot" : ""}>{index + 1}</span>
            <p>{item}</p>
          </li>
        ))}
      </ol>
    </Card>
  );

  return (
    <div className="dw-report-stack">
      <div className="dw-report-two">
        {ledgerCard("Why not lower", ledger.why_not_lower ?? [], true)}
        {ledgerCard("Why not higher", ledger.why_not_higher ?? [])}
      </div>
      <Card eyebrow="EVIDENCE REGISTER" title={`${evidenceItems.length} deterministic items`}>
        <div className="dw-evidence-register">
          {evidenceItems.map((item, index) => (
            <div key={item.evidence_id}>
              <span>{item.evidence_id || `EV-${String(index + 1).padStart(2, "0")}`}</span>
              <MonoRef>{evidenceReference(item)}</MonoRef>
              <p>{item.summary}</p>
              <em>{item.source_type}</em>
            </div>
          ))}
        </div>
        <p className="dw-register-foot"><ShieldCheck size={13} /> AI explains. Evidence decides - disable the narrative layer and this register still stands.</p>
      </Card>
    </div>
  );
}

function ContextTab({ report }: { report: ReportDetail }) {
  const context = getContextCompleteness(report);
  const blastRadius = getBlastRadius(report);
  const parserSuccessByTool = context.parser_success_by_tool ?? {};
  const contextTodos = context.context_todos ?? [];
  const rows = [
    ["Topology freshness", context.topology_freshness_days == null ? "unknown" : `${context.topology_freshness_days} days`, context.topology_last_imported_at || "snapshot metadata unavailable", !context.insufficient_context],
    ["Parser success", `${Math.round(context.parser_success_rate * 100)}%`, Object.keys(parserSuccessByTool).join(" - ") || "parser summary", context.parser_success_rate >= 1],
    ["Incident index", `${context.incident_index_size} incidents`, context.incident_index_freshness_status || context.incident_index_version || "index metadata", context.incident_index_size > 0],
    ["Evidence coverage", context.evidence_success_rate.toFixed(2), "material changes represented", context.evidence_success_rate >= 1],
    ["Open context TODOs", `${contextTodos.length}`, contextTodos[0] || "no open context TODOs", contextTodos.length === 0],
  ];
  const affected = blastRadius.affected ?? [];

  return (
    <div className="dw-report-stack">
      <Card eyebrow="CONTEXT COMPLETENESS" title={`${context.context_score.toFixed(2)} / 1.00 - ${context.confidence_level} context`}>
        <div className="dw-context-checklist">
          {rows.map(([label, value, hint, ok]) => (
            <div key={String(label)}>
              <span className={ok ? "dw-context-ok" : "dw-context-fail"}>{ok ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}</span>
              <strong>{label}</strong>
              <MonoRef>{value}</MonoRef>
              <em>{hint}</em>
            </div>
          ))}
        </div>
        <Button variant="ghost">+ Resolve open context TODO</Button>
      </Card>
      <Card eyebrow="BLAST RADIUS" title={`${affected.length || (blastRadius.direct_count + blastRadius.transitive_count)} services affected`}>
        <div className="dw-service-chips">
          {affected.map((node) => (
            <span className={node.depth === 0 ? "dw-direct-service" : ""} key={node.service_id}>
              <i />
              {node.label}
            </span>
          ))}
        </div>
        <p className="dw-report-muted">
          {blastRadius.direct_count} direct, {blastRadius.transitive_count} transitive - graph depth from topology - topology age {String(blastRadius.freshness?.age_days ?? "unknown")}.
        </p>
      </Card>
    </div>
  );
}

function RollbackTab({ report, setToast }: { report: ReportDetail; setToast: (message: string | null) => void }) {
  const rollback = getRollbackPlan(report);
  const steps = rollback.steps ?? [];
  const copyPlan = async () => {
    await navigator.clipboard.writeText(steps.map((step) => `${step.order}. ${step.title} - ${step.detail}`).join("\n"));
    setToast("Rollback plan copied.");
  };

  return (
    <Card
      eyebrow="ROLLBACK PLAN"
      right={<Button onClick={copyPlan} variant="ghost"><Copy size={13} /> Copy full plan</Button>}
      title={`${steps.length} steps - ~${totalRollbackMinutes(report)} min - complexity ${rollback.complexity_score}/5`}
    >
      <ol className="dw-rollback-timeline">
        {steps.map((step, index) => (
          <li key={`${step.order}-${step.title}`}>
            {index < steps.length - 1 && <span className="dw-rollback-line" />}
            <span className={step.critical ? "dw-rollback-critical" : ""}>{step.order}</span>
            <p>{step.title}</p>
            {step.critical && <strong>CRITICAL PATH</strong>}
            <em>~{step.estimated_minutes} min</em>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function AuditTab({ report }: { report: ReportDetail }) {
  const skills = report.skills_applied ?? [];
  const items = [
    ["Interface", report.audit.source_interface || "unknown"],
    ["Trigger", report.audit.trigger_type || "manual"],
    ["Provider", report.narrative_provider || report.audit.llm_provider || "none"],
    ["Model", report.narrative_model || report.audit.llm_model || "none"],
    ["Risk scoring", report.assessment_source || "heuristic-only"],
    ["Narrative source", report.narrative_source || "fallback"],
    ["Schema", report.report_schema_version],
    ["Files analyzed", String(report.filenames.length)],
    ["Skills applied", skills.join(" - ") || "none"],
    ["Report id", String(report.id)],
  ];
  return (
    <Card eyebrow="AUDIT METADATA" title="How this report was produced">
      <dl className="dw-audit-grid">
        {items.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="dw-report-muted">Advisory only - DeployWhisper produces intelligence, not authorization. The human reviewer decides.</p>
    </Card>
  );
}

function ReportLoading() {
  return (
    <main className="dw-report-page dw-ui">
      <div className="dw-report-content">
        <SkeletonCard />
        <div className="dw-report-two"><SkeletonCard /><SkeletonCard /></div>
      </div>
    </main>
  );
}

function reportProjectOption(report: ReportDetail) {
  return {
    id: String(report.project.id),
    name: report.project.display_name || report.project.project_key,
    env: report.env_label || report.project.default_branch || "default",
    description: report.project.description || report.project.repository_url || report.project.project_key,
  };
}

function ReportBody({
  active,
  copyBriefing,
  publicView,
  report,
  setActiveTab,
  setToast,
  toast,
}: {
  active: string;
  copyBriefing: () => void;
  publicView: boolean;
  report: ReportDetail;
  setActiveTab: (tab: string) => void;
  setToast: (message: string | null) => void;
  toast: string | null;
}) {
  return (
    <div className={`dw-report-page dw-ui${publicView ? "" : " dw-report-page-shell"}`}>
      <ReportHeader activeTab={active} copyBriefing={copyBriefing} publicView={publicView} report={report} setActiveTab={setActiveTab} />
      <main className="dw-report-content">
        <section aria-labelledby={`tab-${active}`} role="tabpanel">
          {active === "overview" && <OverviewTab goFindings={() => setActiveTab("findings")} report={report} />}
          {active === "findings" && <FindingsTab publicView={publicView} report={report} setToast={setToast} />}
          {active === "confidence" && <ConfidenceTab report={report} />}
          {active === "context" && <ContextTab report={report} />}
          {active === "rollback" && <RollbackTab report={report} setToast={setToast} />}
          {active === "audit" && <AuditTab report={report} />}
        </section>
      </main>
      <Toast message={toast} />
    </div>
  );
}

export function ReportScreen() {
  const params = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const publicView = location.pathname.startsWith("/reports/") && searchParams.get("private") !== "1";
  const reportId = Number(params.id);
  const [activeTab, setActiveTab] = useState(searchParams.get("tab") || "overview");
  const [toast, setToast] = useState<string | null>(null);
  const comparePrevious = searchParams.get("compare") === "previous";

  const reportQuery = useQuery({
    enabled: Number.isFinite(reportId),
    queryKey: ["report", reportId, publicView, comparePrevious],
    queryFn: () => getReportDetail(reportId, { publicView, comparePrevious }),
    retry: false,
  });

  const copyBriefing = async () => {
    if (!reportQuery.data) {
      return;
    }
    await navigator.clipboard.writeText(reportQuery.data.share_summary.markdown);
    setToast("Briefing copied.");
  };

  if (reportQuery.isLoading) {
    return <ReportLoading />;
  }
  if (reportQuery.error instanceof ApiClientError && reportQuery.error.status === 401 && publicView) {
    return <PasswordGate reportId={reportId} onUnlocked={() => void reportQuery.refetch()} />;
  }
  if (reportQuery.isError || !reportQuery.data) {
    return (
      <main className="dw-report-page dw-ui">
        <div className="dw-report-content">
          <Card title="Report unavailable">
            <div className="dw-report-error" role="alert">Report not found or unavailable.</div>
          </Card>
        </div>
      </main>
    );
  }

  const report = reportQuery.data;
  const active = tabs.some((tab) => tab.id === activeTab) ? activeTab : "overview";
  const body = (
    <ReportBody
      active={active}
      copyBriefing={copyBriefing}
      publicView={publicView}
      report={report}
      setActiveTab={setActiveTab}
      setToast={setToast}
      toast={toast}
    />
  );

  if (!publicView) {
    return (
      <Phase6Shell active="history" selectedProjectOverride={reportProjectOption(report)}>
        {() => body}
      </Phase6Shell>
    );
  }

  return body;
}
