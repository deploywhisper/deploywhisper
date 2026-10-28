import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiClientError } from "../api/client";
import type { AutomationContext } from "./InfraAutomationShared";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { Run, Step, RunReports } from "../api/infraAutomation";
import { RunContent, RunSummary, AttemptTimeline, ScreenedLogContent, runMatchesScope, EvidenceSummary, runReadPolicy, evidenceRefreshDelay, recoverAutomationRunAccess, AttemptLogs, retainAttemptPage, distinctOutputs } from "./InfraAutomationRun";

export const runFixture: Run = { id: "run-one", workflow_id: "workflow-one", revision_id: "revision-one", project_id: 1, workspace_id: 2, requested_by: "principal-one", state: "succeeded", version: 3, snapshot_digest: "a".repeat(64), definition_digest: "b".repeat(64), input_digest: "c".repeat(64), created_at: "2026-10-28T00:00:00Z", deadline_at: "2026-10-28T01:00:00Z", cancel_requested: false, cancellation_requested_at: null };
export const evidenceFixture: RunReports = { items: [], evidence_status: { version: 1, status: "missing", run_state: "succeeded", run_version: 3, attempt_id: null, attempt_state: null, manifest_present: true, report_available: false, evaluated_at: "2026-10-28T02:00:00Z", evidence_deadline: "2026-10-29T00:00:00Z", limitations: ["Mandatory evidence is missing"], context_todos: ["Collect fresh evidence"], approval_eligible: false } };
const render = (content: React.ReactNode) => renderToStaticMarkup(<MemoryRouter>{content}</MemoryRouter>);

describe("immutable automation run details", () => {
  it("shows one artifact digest when an attempt output is also listed as an upload", () => {
    const output = { kind: "screened_artifacts" as const, reference: "manifest-one", digest: `sha256:${"a".repeat(64)}` };
    const step: Step = { id: "attempt-one", run_id: runFixture.id, step_id: "intake", attempt_number: 1, state: "succeeded", version: 1, fence: 1, generation: 1, deadline_at: runFixture.deadline_at, lease_until: null, output, uploads: [output] };
    expect(distinctOutputs(step)).toEqual([output]);
    const html = render(<AttemptTimeline steps={[step]} onLogs={() => {}} />);
    expect(html.split(output.digest)).toHaveLength(2);
  });
  it("retains an authorized attempt page only across versions of the exact same run and cursor", () => {
    const page = { items: [], cursor: { version: 1, limit: 25, snapshot_id: "snapshot", next_cursor: null, last_sequence: 0, gap: false, truncated: false } };
    const oldKey = ["automation", 1, 1, 2, "run", "run-one", "steps", 2, undefined];
    const nextKey = [...oldKey]; nextKey[7] = 3;
    expect(retainAttemptPage(page, oldKey, nextKey, null)).toBe(page);
    for (const index of [1, 2, 3, 5, 8]) {
      const changed = [...nextKey]; changed[index] = "changed";
      expect(retainAttemptPage(page, oldKey, changed, null)).toBeUndefined();
    }
    expect(retainAttemptPage(page, oldKey, nextKey, new ApiClientError("denied", 403))).toBeUndefined();
  });
  it("polls only nonterminal runs using the backend terminal-state classification", () => {
    for (const state of ["queued", "running", "waiting_approval", "ready_handoff", "handing_off", "external_running", "delivery_unknown"] as const) {
      expect(runReadPolicy({ ...runFixture, state }).interval).toBe(5000);
    }
    for (const state of ["succeeded", "failed", "stopped_by_gate", "rejected", "expired", "timed_out", "cancelled"] as const) {
      expect(runReadPolicy({ ...runFixture, state }).interval).toBe(false);
    }
    expect(runReadPolicy(undefined).interval).toBe(false);
  });
  it("changes dependent read snapshots on the final run version so pending evidence is fetched again", () => {
    const active = runReadPolicy({ ...runFixture, state: "running", version: 2 });
    const final = runReadPolicy(runFixture);
    expect(final.version).not.toBe(active.version);
    expect(final.version).toBe(3);
    expect(final.interval).toBe(false);
  });
  it("reads the terminal version's evidence instead of the earlier pending response", () => {
    const client = new QueryClient();
    const key = ["automation", 1, 1, 2, "run", "run-one"];
    client.setQueryData(key, runFixture);
    client.setQueryData([...key, "reports", 2], { ...evidenceFixture, evidence_status: { ...evidenceFixture.evidence_status, status: "pending", limitations: ["Earlier pending response"] } });
    client.setQueryData([...key, "reports", 3], evidenceFixture);
    const html = render(<QueryClientProvider client={client}><RunContent context={context} runId="run-one" /></QueryClientProvider>);
    expect(html).toContain("Mandatory evidence is missing");
    expect(html).not.toContain("Earlier pending response");
  });
  it("schedules one server freshness read even when evidence arrives expired without looping on server clock differences", () => {
    const evidence = evidenceFixture.evidence_status;
    const deadline = Date.parse(evidence.evidence_deadline);
    expect(evidenceRefreshDelay(evidence, deadline - 1000)).toBe(1100);
    expect(evidenceRefreshDelay(evidence, deadline)).toBe(0);
    const refreshed = new Set([evidence.evidence_deadline]);
    expect(evidenceRefreshDelay(evidence, deadline, refreshed)).toBeNull();
    expect(evidenceRefreshDelay({ ...evidence, evaluated_at: "later-server-evaluation" }, deadline + 1000, refreshed)).toBeNull();
    expect(evidenceRefreshDelay({ ...evidence, status: "stale" }, deadline - 1000)).toBeNull();
    expect(evidenceRefreshDelay(undefined, deadline - 1000)).toBeNull();
  });
  const context = { scope: { projectId: 1, workspaceId: 2 }, identity: { epoch: 1 }, fresh: true, refresh: async () => {}, selectProject: () => {}, selectWorkspace: () => {} } as unknown as AutomationContext;
  function renderCachedRun(value: Run, error?: Error) {
    const client = new QueryClient();
    const key = ["automation", 1, 1, 2, "run", "run-one"];
    client.setQueryData(key, value);
    if (error) client.getQueryCache().find({ queryKey: key })?.setState({ error, status: "error" });
    return render(<QueryClientProvider client={client}><RunContent context={context} runId="run-one" /></QueryClientProvider>);
  }
  it("offers an explicit refresh even for successfully loaded empty logs", () => {
    const client = new QueryClient();
    client.setQueryData(["automation", 1, 1, 2, "logs", "run-one", "attempt-one", undefined], { items: [], cursor: { version: 1, limit: 25, snapshot_id: "snapshot", next_cursor: null, last_sequence: 0, gap: false, truncated: false } });
    const html = render(<QueryClientProvider client={client}><AttemptLogs runId="run-one" attemptId="attempt-one" context={context} onDenied={() => {}} /></QueryClientProvider>);
    expect(html).toContain("No screened log chunks");
    expect(html).toContain("Refresh logs");
  });
  it("refreshes access before every protected recovery read, and waits for all of them", async () => {
    const calls: string[] = [];
    let release!: () => void;
    const lastRead = new Promise<void>((resolve) => { release = resolve; });
    let completed = false;
    const recovery = recoverAutomationRunAccess(async () => { calls.push("access"); }, [
      async () => { calls.push("run"); }, async () => { calls.push("steps"); }, async () => { calls.push("reports"); await lastRead; },
    ]).then(() => { completed = true; });
    await Promise.resolve();
    expect(calls).toEqual(["access", "run", "steps", "reports"]);
    expect(completed).toBe(false);
    release();
    await recovery;
    expect(completed).toBe(true);
  });
  it("keeps recovery denied when live access or any protected read fails", async () => {
    let reads = 0;
    await expect(recoverAutomationRunAccess(async () => ({ isError: true }), [async () => { reads++; }])).rejects.toThrow();
    expect(reads).toBe(0);
    await expect(recoverAutomationRunAccess(async () => ({}), [async () => { throw new ApiClientError("denied", 403); }])).rejects.toThrow();
  });
  it("provides a named run receipt heading that can receive keyboard focus", () => {
    const html = renderCachedRun(runFixture);
    expect(html).toContain('<h2 tabindex="-1">Preflight run</h2>');
  });
  it("clears protected cached details after denied refreshes", () => {
    for (const code of [401, 403]) {
      const html = renderCachedRun(runFixture, new ApiClientError("unsafe server detail", code));
      expect(html).toContain("Run access unavailable");
      expect(html).not.toContain(runFixture.snapshot_digest);
      expect(html).not.toContain(runFixture.requested_by);
      expect(html).not.toContain("unsafe server detail");
    }
  });
  it("shows an explicit scope switch without displaying another scope's run details", () => {
    const html = renderCachedRun({ ...runFixture, project_id: 9 });
    expect(html).toContain("Use run project");
    expect(html).not.toContain(runFixture.snapshot_digest);
    expect(html).not.toContain(runFixture.requested_by);
  });
  it("requires the exact selected project and workspace before showing a run", () => {
    expect(runMatchesScope(runFixture, { projectId: 1, workspaceId: 2 })).toBe(true);
    expect(runMatchesScope(runFixture, { projectId: 1, workspaceId: null })).toBe(false);
    expect(runMatchesScope(runFixture, { projectId: 9, workspaceId: 2 })).toBe(false);
  });
  it("renders complete distinct digests and actual persisted times", () => {
    const html = render(<RunSummary run={runFixture} />);
    expect(html).toContain("a".repeat(64));
    expect(html).toContain("b".repeat(64));
    expect(html).toContain("c".repeat(64));
    expect(html).toContain("2026-10-28T00:00:00Z");
    expect(html).toContain("succeeded");
    expect(html).not.toContain("100%");
    expect(html).not.toContain("Finished at");
  });
  it("keeps server order and attempt numbers with explicit unavailable timing", () => {
    const make = (id: string, attempt: number): Step => ({ id, run_id: runFixture.id, step_id: id, attempt_number: attempt, state: "failed", version: 1, fence: 1, generation: 1, deadline_at: runFixture.deadline_at, lease_until: null, uploads: [] });
    const html = render(<AttemptTimeline steps={[make("analysis", 3), make("intake", 1)]} onLogs={() => {}} />);
    expect(html.indexOf("analysis")).toBeLessThan(html.indexOf("intake"));
    expect(html).toContain("Attempt 3");
    expect(html).toContain("Start and finish times unavailable");
  });
  it("renders escaped screened logs with sequence and bounded-page warnings", () => {
    const html = render(<ScreenedLogContent page={{ items: [{ sequence: 7, text: "<script>screened</script>" }], cursor: { version: 1, limit: 25, snapshot_id: "snapshot", next_cursor: null, last_sequence: 7, gap: true, truncated: true } }} />);
    expect(html).toContain("Sequence 7");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("Gap");
    expect(html).toContain("truncated");
    expect(html).toContain("Log timestamps unavailable");
  });
  it("shows durable uncertainty without a report", () => {
    const html = render(<EvidenceSummary reports={evidenceFixture} runId={runFixture.id} />);
    expect(html).toContain("missing");
    expect(html).toContain("Mandatory evidence is missing");
    expect(html).toContain("Collect fresh evidence");
    expect(html).toContain("No permanent briefing");
    expect(html).toContain("not eligible for approval");
  });
});
