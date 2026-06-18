import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { ReportDetail } from "../api/report";
import { ReportScreen } from "./Report";

const report = {
  id: 77,
  project: {
    id: 1,
    project_key: "checkout",
    display_name: "Checkout",
    description: "Checkout platform",
    repository_url: null,
    default_branch: "main",
    is_default: true,
    created_at: "2026-06-16T00:00:00Z",
    updated_at: "2026-06-16T00:00:00Z",
    name: "Checkout",
    env_label: "prod",
  },
  workspace: null,
  risk_score: 82,
  severity: "HIGH",
  recommendation: "CAUTION",
  confidence: 0.88,
  top_risk: "Deployment widens checkout ingress",
  report_schema_version: "v2",
  tool_mix: ["kubernetes"],
  analysis_status: "degraded",
  top_risk_contributors: [],
  parse_summary: "1 Kubernetes manifest parsed",
  narrative_opening: "CAUTION: checkout ingress changed during rollout.",
  narrative_available: false,
  narrative_degraded: true,
  narrative_failure_notice: "raw provider timeout text must not render",
  assessment_source: "heuristic-only",
  narrative_source: "fallback",
  narrative_provider: null,
  narrative_model: null,
  narrative_local_mode: null,
  advisory: {
    advisory_only: true,
    should_block: false,
    requires_attention: true,
    severity: "high",
    recommendation: "caution",
    top_risk: "Ingress widened",
    partial_context: false,
    narrative_degraded: true,
    uncertainty_flags: [],
  },
  skills_applied: ["kubernetes-risk"],
  created_at: "2026-06-16T09:30:00Z",
  warnings: [],
  findings: [
    {
      finding_id: "finding-ingress",
      analysis_id: 77,
      title: "Ingress exposes checkout service",
      description: "Service ingress changed to a broader source range.",
      explanation: "The change increases reachable network surface.",
      guidance: ["Review allowed source ranges."],
      severity: "high",
      category: "network",
      deterministic: true,
      confidence: 0.9,
      uncertainty_note: null,
      evidence_classification: "deterministic",
      evidence_refs: ["ev-ingress"],
      skill_id: "kubernetes-risk",
    },
  ],
  evidence_items: [
    {
      evidence_id: "ev-ingress",
      analysis_id: 77,
      finding_id: "finding-ingress",
      source_type: "kubernetes",
      source_ref: "checkout-platform.yaml",
      artifact: "checkout-platform.yaml",
      location: "spec.rules[0]",
      resource: "ingress/checkout",
      operation: "update",
      project_id: 1,
      project_key: "checkout",
      workspace_id: null,
      workspace_key: null,
      source_kind: "artifact",
      determinism_level: "deterministic",
      redaction_status: "none",
      summary: "Ingress rule became broader.",
      severity_hint: "high",
      deterministic: true,
      confidence: 0.9,
      context_source: {
        source_id: "topology:kubernetes:current-context",
        source_type: "topology",
        source_ref: "current-context",
        scope: "project:checkout",
        freshness_status: "current",
        last_observed_at: "2026-06-14T00:00:00Z",
        age_days: 2,
        confidence: 0.9,
        conflicts: [],
        limitations: [],
      },
      related_change_ids: [],
    },
  ],
  incident_matches: [],
  contributors: [],
  confidence_ledger: {
    why_not_lower: ["Deterministic manifest evidence references the changed ingress."],
    why_not_higher: ["Topology context has no live traffic sample."],
  },
  dashboard_display_duration_seconds: null,
  dashboard_remaining_seconds: null,
  analysis_duration_seconds: 16,
  submission_manifest: null,
  submission_manifest_fallback: [],
  audit: {
    actor: "react_dashboard",
    source_interface: "api",
    trigger_type: "manual",
    files_analyzed: ["checkout-platform.yaml"],
    redaction_status: "none",
    llm_provider: null,
    llm_model: null,
  },
  context_completeness: {
    context_score: 0.72,
    confidence_level: "medium",
    insufficient_context: false,
    topology_freshness_days: 2,
    topology_last_imported_at: "2026-06-14T00:00:00Z",
    parser_success_rate: 1,
    parser_success_by_tool: { kubernetes: 1 },
    incident_index_size: 0,
    incident_index_version: null,
    incident_index_freshness_status: null,
    evidence_success_rate: 1,
    context_sources: [
      {
        source_id: "topology:kubernetes:current-context",
        source_type: "topology",
        source_ref: "current-context",
        scope: "project:checkout",
        freshness_status: "current",
        last_observed_at: "2026-06-14T00:00:00Z",
        age_days: 2,
        confidence: 0.9,
        conflicts: [],
        limitations: [],
      },
      {
        source_id: "incident:index:checkout",
        source_type: "incident",
        source_ref: "incidents:empty",
        scope: "project:checkout",
        freshness_status: "empty",
        last_observed_at: null,
        age_days: null,
        confidence: 0,
        conflicts: ["missing_incident_history"],
        limitations: ["missing_incident_history", "empty_incident_index", "incident_pack_missing", "incident_dates_unknown", "incident_scope_unverified"],
      },
    ],
    context_todos: [],
    partial_context: false,
  },
  blast_radius: {
    affected: [{ service_id: "checkout", label: "checkout", depth: 0 }],
    direct_count: 1,
    transitive_count: 0,
    warning: null,
    unmatched_resources: [],
    context_state: "current",
    context_limitations: [],
    freshness: {
      status: "current",
      age_days: 2,
      last_imported_at: "2026-06-14T00:00:00Z",
      warning: null,
    },
  },
  rollback_plan: {
    steps: [{ order: 1, title: "Revert ingress manifest", detail: "Restore previous source range.", estimated_minutes: 5, critical: true }],
    complexity: "low",
    complexity_score: 1,
    complexity_explanation: "Single manifest revert.",
    warning: null,
  },
  share_summary: {
    advisory_only: true,
    should_block: false,
    headline: "Ingress widened",
    blast_radius_summary: "1 service affected",
    rollback_summary: "1 rollback step",
    uncertainty_summary: "Topology context has no live traffic sample.",
    markdown: "## DeployWhisper briefing",
    plain_text: "DeployWhisper briefing",
    severity: "high",
    recommendation: "caution",
    json_payload: {
      version: "v1",
      report_schema_version: "v2",
      report_id: 77,
      report_link: "http://127.0.0.1:8080/reports/77",
      rollback_link: "http://127.0.0.1:8080/reports/77#rollback",
      verdict_banner: "CAUTION",
      evidence_law_status: "Satisfied",
      evidence_law_detail: "High-risk claim has deterministic evidence.",
      headline: "Ingress widened",
      top_findings: [],
      evidence_count: 1,
      blast_radius_summary: "1 service affected",
      rollback_summary: "1 rollback step",
      context_completeness: { score: 0.72, label: "medium", summary: "Context mostly complete." },
      advisory_summary: "Human review recommended.",
    },
  },
  share: {
    share_url: "http://127.0.0.1:8080/reports/77",
    password_protected: false,
    redact_filenames: false,
  },
  feedback_state: {
    finding_feedback: {},
  },
  comparison: null,
  score: 82,
  verdict: "CAUTION",
  filenames: ["checkout-platform.yaml"],
  workspace_label: "prod",
  env_label: "prod",
  trigger_ref: "manual",
  pr_ref: "PR #42",
} satisfies ReportDetail;

function renderReport(path = "/reports/77?private=1", detail: ReportDetail = report) {
  const client = new QueryClient();
  const publicView = path.startsWith("/reports/") && !path.includes("private=1");
  client.setQueryData(["report", detail.id, publicView, false], detail);

  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<ReportScreen />} path="/reports/:id" />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ReportScreen", () => {
  it("renders Part B3 header and overview from persisted report data", () => {
    const markup = renderReport();

    expect(markup).toContain("Deployment widens checkout ingress");
    expect(markup).toContain("CAUTION");
    expect(markup).toContain("Evidence Law");
    expect(markup).toContain("Ingress exposes checkout service");
    expect(markup).toContain("AI narrative unavailable - deterministic findings below are unaffected.");
    expect(markup).not.toContain("raw provider timeout text");
  });

  it("hides mutable report actions on the public route", () => {
    const markup = renderReport("/reports/77");

    expect(markup).toContain("Compare");
    expect(markup).not.toContain("Copy briefing");
    expect(markup).not.toContain("Share");
  });

  it("renders the blast radius as a visual impact map on the context tab", () => {
    const markup = renderReport("/reports/77?private=1&tab=context");

    expect(markup).toContain("BLAST RADIUS");
    expect(markup).toContain("CONTEXT SOURCES");
    expect(markup).toContain("topology:kubernetes:current-context");
    expect(markup).toContain("current-context");
    expect(markup).toContain("90%");
    expect(markup).toContain("missing_incident_history");
    expect(markup.match(/>missing_incident_history</g)?.length).toBe(1);
    expect(markup).toContain("incident_pack_missing");
    expect(markup).toContain("incident_dates_unknown");
    expect(markup).toContain("incident_scope_unverified");
    expect(markup).not.toContain("+2 more");
    expect(markup).toContain("Contained radius");
    expect(markup).toContain("checkout");
    expect(markup).toContain("Direct");
    expect(markup).toContain("Transitive");
  });

  it("renders context sources with duplicate source ids as separate rows", () => {
    const duplicateSourceReport = {
      ...report,
      context_completeness: {
        ...report.context_completeness,
        context_sources: [
          ...report.context_completeness.context_sources,
          {
            ...report.context_completeness.context_sources[0],
            source_ref: "current-context-shadow",
            scope: "project:checkout/workspace:shadow",
            freshness_status: "stale",
            confidence: 0.4,
          },
        ],
      },
    } satisfies ReportDetail;

    const markup = renderReport(
      "/reports/77?private=1&tab=context",
      duplicateSourceReport,
    );

    expect(markup.match(/data-testid="context-source-row"/g)?.length).toBe(3);
    expect(markup).toContain("current-context");
    expect(markup).toContain("current-context-shadow");
    expect(markup).toContain("project:checkout/workspace:shadow");
    expect(markup).toContain("stale - 40%");
  });

  it("renders note-only duplicate context sources with distinct row identities", () => {
    const noteOnlyDuplicateReport = {
      ...report,
      context_completeness: {
        ...report.context_completeness,
        context_sources: [
          ...report.context_completeness.context_sources,
          {
            ...report.context_completeness.context_sources[0],
            limitations: ["note_only_shadow"],
          },
        ],
      },
    } satisfies ReportDetail;

    const markup = renderReport(
      "/reports/77?private=1&tab=context",
      noteOnlyDuplicateReport,
    );

    expect(markup.match(/data-testid="context-source-row"/g)?.length).toBe(3);
    expect(markup).toContain("note_only_shadow");
    expect(markup).toContain("data-context-source-identity");
  });

  it("encodes selector-sensitive context source row identities", () => {
    const encodedIdentityReport = {
      ...report,
      context_completeness: {
        ...report.context_completeness,
        context_sources: [
          {
            ...report.context_completeness.context_sources[0],
            source_ref: "current|context\"]",
            scope: "project:checkout|workspace:prod]",
            limitations: ["note|with]delimiter"],
          },
        ],
      },
    } satisfies ReportDetail;

    const markup = renderReport(
      "/reports/77?private=1&tab=context",
      encodedIdentityReport,
    );

    expect(markup).toContain("current|context&quot;]");
    expect(markup).toContain("note|with]delimiter");
    expect(markup).toContain("current%7Ccontext%5C%22%5D");
    expect(markup).toContain("note%7Cwith%5Ddelimiter");
  });

  it("renders evidence context source references on the confidence tab", () => {
    const markup = renderReport("/reports/77?private=1&tab=confidence");

    expect(markup).toContain("EVIDENCE REGISTER");
    expect(markup).toContain("topology:kubernetes:current-context (current)");
  });

  it("renders a green safe state when the blast radius is zero", () => {
    const safeReport = {
      ...report,
      blast_radius: {
        ...report.blast_radius,
        affected: [],
        direct_count: 0,
        transitive_count: 0,
        warning: null,
      },
    } satisfies ReportDetail;

    const markup = renderReport("/reports/77?private=1&tab=context", safeReport);

    expect(markup).toContain("No services affected");
    expect(markup).toContain("No mapped impact");
    expect(markup).toContain("No affected components found in the active topology.");
  });
});
