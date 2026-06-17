import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { buildHistoryQueryParams, type HistoryReport } from "../api/history";
import { DeleteAnalysisDialog, HistoryTable, formatRescanDelta } from "./History";

const project = {
  id: 1,
  project_key: "payments",
  display_name: "Payments",
  description: "Payment service",
  repository_url: null,
  default_branch: "main",
  is_default: true,
  created_at: "2026-06-16T00:00:00Z",
  updated_at: "2026-06-16T00:00:00Z",
  name: "Payments",
  env_label: "prod / main",
};

const report: HistoryReport = {
  id: 42,
  project,
  workspace: null,
  risk_score: 78,
  severity: "HIGH",
  recommendation: "CAUTION",
  confidence: 0.82,
  top_risk: "Database ingress widened",
  report_schema_version: "v2",
  tool_mix: ["terraform"],
  analysis_status: "degraded",
  parse_summary: "1 Terraform plan parsed",
  narrative_opening: "CAUTION: RDS ingress widened during rollout.",
  narrative_available: false,
  narrative_degraded: true,
  narrative_failure_notice: "AI narrative unavailable - deterministic findings below are unaffected.",
  assessment_source: "heuristic-only",
  narrative_source: "fallback",
  advisory: {
    advisory_only: true,
    should_block: false,
    requires_attention: true,
    severity: "high",
    recommendation: "caution",
    top_risk: "Database ingress widened",
    partial_context: false,
    narrative_degraded: true,
  },
  created_at: "2026-06-16T09:30:00Z",
  warnings: [],
  findings: [],
  evidence_items: [],
  incident_matches: [],
  contributors: [],
  dashboard_display_duration_seconds: null,
  dashboard_remaining_seconds: null,
  analysis_duration_seconds: 14,
  submission_manifest: null,
  submission_manifest_fallback: [],
  audit: { actor: "react_dashboard", files_analyzed: ["terraform/rds.tf"], redaction_status: "none" },
  blast_radius: {
    affected: [],
    direct_count: 3,
    transitive_count: 5,
    warning: null,
    unmatched_resources: [],
    context_state: "current",
    context_limitations: [],
    freshness: { updated_at: "2026-06-16T09:00:00Z", age_days: 0 },
  },
  rollback_plan: {
    steps: [],
    complexity: "medium",
    complexity_score: 3,
    complexity_explanation: "Rollback requires validation.",
    warning: null,
  },
  score: 78,
  verdict: "CAUTION",
  filenames: ["terraform/rds.tf"],
  workspace_label: "prod",
  env_label: "prod",
  trigger_ref: "manual",
  pr_ref: "PR #2847",
  previous_scan_diff: {
    previous_report_id: 41,
    previous_created_at: "2026-06-15T09:30:00Z",
    score_delta: 12,
    score_direction: "up",
    previous_severity: "medium",
    current_severity: "high",
    previous_recommendation: "go",
    current_recommendation: "caution",
  },
};

function renderHistoryTable(expanded = false) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <HistoryTable
        expanded={expanded ? { "0": true } : {}}
        reports={[report]}
        selectedIds={new Set([42])}
        onExpandedChange={() => undefined}
        onOpenReport={() => undefined}
        onToggleSelectPage={() => undefined}
        onToggleSelected={() => undefined}
      />
    </MemoryRouter>,
  );
}

describe("history API filters", () => {
  it("serializes the server-side Phase 5 filters", () => {
    const params = buildHistoryQueryParams({
      projectId: 7,
      severity: "high",
      recommendation: "caution",
      search: " ingress ",
      page: 2,
      pageSize: 25,
    });

    expect(params.toString()).toBe("project_id=7&severity=high&recommendation=caution&search=ingress&page=2&page_size=25");
  });
});

describe("HistoryTable", () => {
  it("renders compact rows with badges, score, tools, and rescan delta", () => {
    const markup = renderHistoryTable();

    expect(markup).toContain("Database ingress widened");
    expect(markup).toContain("High");
    expect(markup).toContain("CAUTION");
    expect(markup).toContain("terraform");
    expect(markup).toContain("+12 risk vs #41");
    expect(markup).not.toContain("CAUTION: RDS ingress widened during rollout.");
  });

  it("renders the summary once in expanded detail", () => {
    const markup = renderHistoryTable(true);

    expect(markup).toContain("Summary");
    expect(markup).toContain("CAUTION: RDS ingress widened during rollout.");
    expect(markup).toContain("Open report");
  });

  it("formats reports without prior scans as first scans", () => {
    expect(formatRescanDelta({ ...report, previous_scan_diff: null })).toBe("First scan");
  });
});

describe("DeleteAnalysisDialog", () => {
  it("renders a destructive confirmation before report deletion", () => {
    const markup = renderToStaticMarkup(
      <DeleteAnalysisDialog count={1} deleting={false} onCancel={() => undefined} onConfirm={() => undefined} />,
    );

    expect(markup).toContain("Destructive action");
    expect(markup).toContain("Delete 1 selected analysis report(s)? This delete cannot be undone.");
    expect(markup).toContain("permanently removed");
    expect(markup).toContain("dw-button-danger");
  });
});
