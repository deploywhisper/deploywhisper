import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { AnalysisReport, Project, StatsSummary, VerdictDistribution } from "../api/dashboard";
import {
  DashboardScreen,
  DropzoneCard,
  RecentAnalysesTable,
  dashboardGreeting,
  isSupportedArtifact,
  verdictHealthCounts,
} from "./Dashboard";

const project: Project = {
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
  env_label: "prod · main",
};

const stats: StatsSummary = {
  totals: {
    analyses: 4,
    clean_verdict_rate: 25,
    open_high_critical_count: 2,
    avg_time_to_verdict_seconds: 12,
  },
  total_analyses: 4,
  clean_verdict_rate: 25,
  open_high_critical_count: 2,
  avg_time_to_verdict_seconds: 12,
  series: {
    analyses: [1, 1, 2, 2, 3, 3, 4].map((value, index) => ({ date: `2026-06-${10 + index}`, value })),
    clean_verdict_rate: [0, 0, 20, 20, 25, 25, 25].map((value, index) => ({ date: `2026-06-${10 + index}`, value })),
    open_high_critical_count: [0, 1, 1, 2, 2, 2, 2].map((value, index) => ({ date: `2026-06-${10 + index}`, value })),
    avg_time_to_verdict_seconds: [18, 16, 15, 14, 13, 12, 12].map((value, index) => ({ date: `2026-06-${10 + index}`, value })),
  },
};

const report: AnalysisReport = {
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
  incident_matches: [
    {
      incident_id: 17,
      match_type: "organization_incident",
      title: "Connection pool exhausted",
      severity: "high",
      source_file: "incident.md",
      incident_date: null,
      similarity: 0.89,
      confidence: 0.9,
      confidence_label: "high",
      reason: "Similar database exposure",
      evidence: [],
      summary: "Similar exposure pattern.",
    },
  ],
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
};

const distribution: VerdictDistribution = {
  days: 30,
  window_start: "2026-05-17T00:00:00Z",
  window_end: "2026-06-16T00:00:00Z",
  counts: { CAUTION: 3, PROCEED: 1, "NO-GO": 1 },
  total: 5,
};

function renderWithQuery(node: React.ReactElement, client?: QueryClient) {
  return renderToStaticMarkup(
    <QueryClientProvider client={client ?? new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DashboardScreen", () => {
  it("renders dashboard hook data from preloaded TanStack Query state", () => {
    const client = new QueryClient();
    client.setQueryData(["dashboard", "projects"], [project]);
    client.setQueryData(["dashboard", "stats", 1], stats);
    client.setQueryData(["dashboard", "analyses", 1], [report]);
    client.setQueryData(["dashboard", "distribution", 1], distribution);

    const markup = renderWithQuery(<DashboardScreen />, client);

    expect(markup).toMatch(/(Good morning|Good afternoon|Good evening|Working late), DW/);
    expect(markup).toContain("Evidence Law enforced");
    expect(markup).toContain("Total analyses");
    expect(markup).toContain("4");
    expect(markup).toContain("CAUTION: RDS ingress widened during rollout.");
    expect(markup).toContain("Workspace");
    expect(markup).toContain("Payments");
  });
});

describe("dashboardGreeting", () => {
  it("uses local time buckets for the dashboard header", () => {
    expect(dashboardGreeting(new Date(2026, 5, 17, 8))).toBe("Good morning, DW");
    expect(dashboardGreeting(new Date(2026, 5, 17, 13))).toBe("Good afternoon, DW");
    expect(dashboardGreeting(new Date(2026, 5, 17, 19))).toBe("Good evening, DW");
    expect(dashboardGreeting(new Date(2026, 5, 17, 2))).toBe("Working late, DW");
  });
});

describe("verdictHealthCounts", () => {
  it("counts real API verdict keys as clear reports", () => {
    expect(
      verdictHealthCounts({
        days: 30,
        window_start: "2026-05-18T00:00:00Z",
        window_end: "2026-06-17T00:00:00Z",
        counts: { go: 6, caution: 1, "no-go": 2 },
        total: 9,
      }),
    ).toEqual({ high: 2, caution: 1, clear: 6, total: 9 });
  });
});

describe("RecentAnalysesTable", () => {
  it("renders report rows with compact B2 fields", () => {
    const markup = renderToStaticMarkup(<RecentAnalysesTable analyses={[report]} onOpen={() => undefined} />);

    expect(markup).toContain("terraform/rds.tf");
    expect(markup).toContain("PR #2847");
    expect(markup).toContain("CAUTION");
    expect(markup).toContain("prod");
  });
});

describe("DropzoneCard", () => {
  it("filters supported deployment artifacts", () => {
    expect(isSupportedArtifact({ name: "plan.json" })).toBe(true);
    expect(isSupportedArtifact({ name: "checkout.yaml" })).toBe(true);
    expect(isSupportedArtifact({ name: "Jenkinsfile" })).toBe(true);
    expect(isSupportedArtifact({ name: "notes.txt" })).toBe(false);
  });

  it("renders disabled analyze state with the selected workspace", () => {
    const markup = renderWithQuery(<DropzoneCard project={{ id: "1", name: "Payments", env: "prod", description: "" }} />);

    expect(markup).toContain("New analysis");
    expect(markup).toContain("Payments");
    expect(markup).toContain("0 files staged");
    expect(markup).toContain("disabled");
  });
});
