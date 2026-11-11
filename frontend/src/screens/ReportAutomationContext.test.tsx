import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { isAutomationRunIdentifier, verifiedReportRelation, ReportAutomationProvenance, ReportAutomationContext } from "./ReportAutomationContext";
import type { Run } from "../api/infraAutomation";
const runFixture: Run = { id: "run-one", workflow_id: "workflow-one", revision_id: "revision-one", project_id: 1, workspace_id: 2, requested_by: "principal-one", state: "succeeded", version: 3, snapshot_digest: "a".repeat(64), definition_digest: "b".repeat(64), input_digest: "c".repeat(64), created_at: "2026-10-28T00:00:00Z", deadline_at: "2026-10-28T01:00:00Z", cancel_requested: false, cancellation_requested_at: null };
import type { RunReports } from "../api/infraAutomation";

const link: RunReports["items"][number] = { id: "link-one", run_id: "run-one", attempt_id: "attempt-one", manifest_id: "manifest-one", report_id: 77, report_url: "/reports/77", provenance: { version: 1, kind: "uploaded", repository_source: "unavailable", limitation: "Repository and immutable commit were not verified for uploaded evidence." }, limitations: ["Source unverified"], context_todos: ["Review original artifacts"], approval_eligible: false };
const reports: RunReports = { items: [link], evidence_status: { version: 1, status: "stale", run_state: "succeeded", run_version: 3, attempt_id: null, attempt_state: null, manifest_present: true, report_available: true, evaluated_at: "2026-10-28T02:00:00Z", evidence_deadline: "2026-10-29T00:00:00Z", limitations: ["Evidence expired"], context_todos: ["Collect fresh evidence"], approval_eligible: false } };
describe("optional verified report context", () => {
  it("only accepts bounded backend identifiers", () => {
    expect(isAutomationRunIdentifier("run-one")).toBe(true);
    for (const id of ["", "../run", "https://other", "a".repeat(129), null]) expect(isAutomationRunIdentifier(id)).toBe(false);
  });
  it("requires exact report id, permanent URL, run id and report project", () => {
    expect(verifiedReportRelation(runFixture, reports, "run-one", 77, 1)).toBe(link);
    expect(verifiedReportRelation(runFixture, reports, "other-run", 77, 1)).toBeNull();
    expect(verifiedReportRelation(runFixture, reports, "run-one", 78, 1)).toBeNull();
    expect(verifiedReportRelation(runFixture, reports, "run-one", 77, 2)).toBeNull();
    expect(verifiedReportRelation(runFixture, { ...reports, items: [{ ...link, report_url: "https://other/reports/77" }] }, "run-one", 77, 1)).toBeNull();
  });
  it("renders protected provenance with an internal run link and uncertainty", () => {
    const html = renderToStaticMarkup(<MemoryRouter><ReportAutomationProvenance link={link} evidence={reports.evidence_status} /></MemoryRouter>);
    expect(html).toContain('href="/infra-automation/runs/run-one"');
    expect(html).toContain("Source unverified");
    expect(html).toContain("Evidence stale");
    expect(html).toContain("Collect fresh evidence");
    expect(html).toContain("Review original artifacts");
    expect(html).toContain("Repository and immutable commit were not verified");
  });
  it("identifies collected provenance without granting approval authority", () => {
    const digest = "sha256:" + "a".repeat(64);
    const collected: RunReports["items"][number] = { ...link, provenance: {
      version: 1, kind: "collected", repository_id: "synthetic-repo", commit_sha: "b".repeat(40), profile_digest: digest,
      tool: "opentofu", tool_version: "1.13.1", command_digest: digest, argv_digest: digest, raw_local_digest: digest, sanitized_digest: digest,
      redaction_version: 1, exit_code: 2, collected_at: "2026-10-28T00:00:00Z", source_deadline: "2026-10-28T01:00:00Z",
      custody: { version: 1, handle: "synthetic-custody", raw_local_digest: digest, expires_at: "2026-10-28T01:00:00Z" },
      scope: { version: 1, runner_id: "runner-one", project_id: "1", workspace_id: "2", run_id: "run-one", step_id: "collect", attempt: 1, fence: 1, coordinator_generation: 1, authorization_epoch: 1, restore_epoch: 1, lease_deadline: "2026-10-28T00:01:00Z", audience: "runner-task-v1" },
      limitation: "Collected provenance does not establish completeness or authorize an action."
    } };
    const html = renderToStaticMarkup(<MemoryRouter><ReportAutomationProvenance link={collected} evidence={reports.evidence_status} /></MemoryRouter>);
    expect(html).toContain("Collected preflight context");
    expect(html).toContain("Reports remain advisory");
    expect(html).toContain("Approval eligibility is checked separately");
    expect(html).not.toContain("Uploaded preflight context");
    expect(html).not.toContain("Uploaded evidence is advisory");
    expect(collected.approval_eligible).toBe(false);
  });
  it("suppresses optional context for public and absent links without requiring protected providers", () => {
    expect(renderToStaticMarkup(<MemoryRouter initialEntries={["/reports/77?automation_run=run-one"]}><ReportAutomationContext reportId={77} projectId={1} publicView /></MemoryRouter>)).toBe("");
    expect(renderToStaticMarkup(<MemoryRouter><ReportAutomationContext reportId={77} projectId={1} /></MemoryRouter>)).toBe("");
  });
});
