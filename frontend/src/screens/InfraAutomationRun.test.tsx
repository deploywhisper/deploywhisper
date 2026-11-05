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
  it("checks an elapsed evidence deadline once promptly then spaces retries while the server still says available", () => {
    const evidence = { ...evidenceFixture.evidence_status, status: "available" as const };
    const deadline = Date.parse(evidence.evidence_deadline);
    expect(evidenceRefreshDelay(evidence, deadline - 1000)).toBe(1100);
    expect(evidenceRefreshDelay(evidence, deadline)).toBe(100);
    const checks = new Set([evidence.evidence_deadline]);
    expect(evidenceRefreshDelay(evidence, deadline, checks)).toBe(5000);
    expect(evidenceRefreshDelay({ ...evidence, evaluated_at: "later-server-evaluation" }, deadline + 1000, checks)).toBe(5000);
    for (const status of ["pending", "stale", "failed", "missing", "interrupted"] as const) {
      expect(evidenceRefreshDelay({ ...evidence, status }, deadline + 1000, checks)).toBeNull();
    }
    expect(evidenceRefreshDelay(undefined, deadline + 1000, checks)).toBeNull();
  });
  it("retains earlier evidence as explicitly last-known when refresh fails and offers manual retry", () => {
    const client = new QueryClient();
    const key = ["automation", 1, 1, 2, "run", "run-one"];
    client.setQueryData(key, runFixture);
    const reportKey = [...key, "reports", 3];
    client.setQueryData(reportKey, { ...evidenceFixture, evidence_status: { ...evidenceFixture.evidence_status, status: "available", limitations: ["Old available evidence"] } });
    client.getQueryCache().find({ queryKey: reportKey })?.setState({ error: new Error("connection lost"), status: "error" });
    const html = render(<QueryClientProvider client={client}><RunContent context={context} runId="run-one" /></QueryClientProvider>);
    expect(html).toContain("Evidence status unavailable");
    expect(html).toContain("Retry evidence");
    expect(html).toContain("Old available evidence");
    expect(html).toContain("Last-known evidence available");
    expect(html).toContain("current evidence freshness and authority are unavailable");
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
    expect(html).toContain("Approval eligibility depends on retained source evidence and current server checks");
    expect(html).not.toContain("Uploaded evidence is advisory");
    expect(html).not.toContain("Repository identity and immutable commit are unverified");
  });
});

import { HandoffFacts, HandoffOutcomes, reconciliationFailure } from "./InfraAutomationRun";
const externalFixture: import("../api/infraAutomation").ExternalHandoff = {
  id: "handoff-one", version: 3, state: "running", receiver_state: "running", lock_status: "held", cancel_requested: false,
  verified_outcome: null, reconciliation_available: true,
  acceptance: { version: 1, api_version: "2026-03-10", state: "accepted", operation_id: "handoff-one", binding_digest: `sha256:${"a".repeat(64)}`, repository_id: "repo-one", workflow_id: "workflow-one", workflow_revision: "b".repeat(40), workflow_ref: "main", run_id: 56, run_url: "https://api.github.com/repos/owner/repo/actions/runs/56", html_url: "https://github.com/owner/repo/actions/runs/56" },
  observation: null,
};

describe("external handoff evidence", () => {
  it("separates accepted dispatch, GitHub conclusion and verified receiver completion", () => {
    const { state: _state, operation_id: _operation, binding_digest: _binding, ...common } = externalFixture.acceptance!;
    const html = render(<HandoffFacts operation={{ ...externalFixture, observation: { ...common, status: "completed", conclusion: "success" } }} />);
    expect(html).toContain("Dispatch accepted");
    expect(html).toContain("completed · success — observation only");
    expect(html).toContain("Unknown — no verified terminal receiver proof");
    expect(html).toContain("do not resend");
    expect(html).toContain("does not identify the infrastructure source commit");
  });
  it("never claims a cancellation request stopped the external work", () => {
    const html = render(<HandoffFacts operation={{ ...externalFixture, cancel_requested: true, lock_status: "broken" }} />);
    expect(html).toContain("does not confirm that external work has stopped");
    expect(html).toContain("does not prove external completion");
  });
  it("clears protected handoff facts when handoff reads are revoked", () => {
    const client = new QueryClient();
    const key = ["automation", 1, 1, 2, "run", "run-one"];
    client.setQueryData(key, runFixture);
    const childKey = [...key, "handoffs", 3];
    client.setQueryData(childKey, { version: 1, run_id: "run-one", project_id: 1, workspace_id: 2, items: [externalFixture] });
    client.getQueryCache().find({ queryKey: childKey })?.setState({ error: new ApiClientError("denied", 403), status: "error" });
    const context = { scope: { projectId: 1, workspaceId: 2 }, identity: { epoch: 1 }, fresh: true } as AutomationContext;
    const html = render(<QueryClientProvider client={client}><RunContent context={context} runId="run-one" /></QueryClientProvider>);
    expect(html).toContain("Run access unavailable");
    expect(html).not.toContain("handoff-one");
    expect(html).not.toContain(runFixture.snapshot_digest);
  });
  it("blocks ambiguous manual reconciliation through equal-version reads and permits advancing evidence", () => {
    const context = { scope: { projectId: 1, workspaceId: 2 }, identity: { epoch: 1, csrfToken: "synthetic-csrf" }, fresh: true } as AutomationContext;
    const pendingRequests = new Map([[externalFixture.id, externalFixture.version]]);
    const handoffs = { version: 1 as const, run_id: "run-one", project_id: 1, workspace_id: 2, items: [externalFixture] };
    const draw = (version: number) => render(<HandoffOutcomes handoffs={{ ...handoffs, items: [{ ...externalFixture, version }] }} context={context} pendingRequests={pendingRequests} refresh={async () => {}} onDenied={() => {}} />);
    expect(draw(externalFixture.version)).toContain("previous request remains unconfirmed");
    expect(draw(externalFixture.version)).toContain('disabled=""');
    expect(draw(externalFixture.version + 1)).not.toContain("previous request remains unconfirmed");
    // Recreating a child after a read failure does not discard the scoped marker.
    expect(draw(externalFixture.version)).toContain("previous request remains unconfirmed");
  });
  it("distinguishes correctable manual rejection from ambiguous submission and revoked access", () => {
    for (const code of [400, 404, 409, 422, 429]) expect(reconciliationFailure(new ApiClientError("rejected", code, { code: "request_validation_failed" }))).toBe("correctable");
    for (const code of [401, 403]) expect(reconciliationFailure(new ApiClientError("denied", code))).toBe("denied");
    for (const error of [new Error("network"), new ApiClientError("malformed successful response", 422), new ApiClientError("unavailable", 503)]) expect(reconciliationFailure(error)).toBe("ambiguous");
  });
});

import { CollectionTimeline, CancelRunControl, collectionAnnouncement } from "./InfraAutomationRun";
import type { CollectionView } from "../api/infraAutomationCollection";
const collectionView: CollectionView = { version: 1, run_id: "run-one", project_id: 1, workspace_id: 2, run_version: 3, observed_at: "2026-11-05T00:00:00Z", finite_wait_seconds: 0, limitations: ["Collection internals are not independently observed."], cancellation: { requested: true, requested_at: "2026-11-05T00:00:00Z", owned_processes: "not_confirmed", external_stop: "not_confirmed", external_possible: true, can_cancel: false }, items: [{ step_id: "collect", repository_id: "repo", commit_sha: "a".repeat(40), profile_digest: `sha256:${"b".repeat(64)}`, attempt_id: "attempt", attempt_number: 1, attempt_state: "running", lease_until: "2026-11-05T00:01:00Z", routing_failure: "no_eligible_runner", diagnosis: { code: "heartbeat_stale", eligible: false, correction: "Reconnect the runner." }, observations: [{ kind: "source_bound", state: "bound", event_at: "2026-11-04T23:59:00Z" }, { kind: "collection", state: "running", event_at: null }, { kind: "screened_upload", state: "not_observed", event_at: null }, { kind: "analysis", state: "not_observed", event_at: null }] }] };
describe("truthful collection and cancellation views", () => {
  it("shows retained source and screening facts without invented event times or percentages", () => {
    const html = render(<CollectionTimeline value={collectionView} />);
    expect(html).toContain("Source bound to run");
    expect(html).toContain("Server screening and upload");
    expect(html).toContain("not observed");
    expect(html).toContain("Event time unavailable");
    expect(html).toContain("Reconnect the runner.");
    expect(html).toContain("did not wait or use a fallback");
    expect(html).not.toContain("100%");
  });
  it("announces stage changes but excludes read timestamps and log chunks from announcements", () => {
    const before = collectionAnnouncement(collectionView);
    expect(collectionAnnouncement({ ...collectionView, observed_at: "2026-11-05T00:00:05Z" })).toBe(before);
    expect(collectionAnnouncement({ ...collectionView, items: [{ ...collectionView.items[0], observations: collectionView.items[0].observations.map((x) => x.kind === "screened_upload" ? { ...x, state: "received" } : x) }] })).not.toBe(before);
  });
  it("does not equate cancellation request with owned or external termination", () => {
    const context = { scope: { projectId: 1, workspaceId: 2 }, identity: { epoch: 1, csrfToken: "csrf" }, fresh: true } as AutomationContext;
    const html = render(<CancelRunControl run={runFixture} value={collectionView} context={context} fresh refresh={async () => {}} onDenied={() => {}} />);
    expect(html).toContain("Not independently confirmed by this view");
    expect(html).toContain("Not confirmed; inspect verified external outcome evidence");
    expect(html).toContain("do not resend");
    expect(html).not.toContain("Cancellation reason");
  });
  it("hides all collection data when its scoped read is denied", () => {
    const client = new QueryClient();
    const key = ["automation", 1, 1, 2, "run", "run-one"];
    client.setQueryData(key, runFixture); client.setQueryData([...key, "collection"], collectionView);
    client.getQueryCache().find({ queryKey: [...key, "collection"] })?.setState({ error: new ApiClientError("denied", 403), status: "error" });
    const context = { scope: { projectId: 1, workspaceId: 2 }, identity: { epoch: 1 }, fresh: true } as AutomationContext;
    const html = render(<QueryClientProvider client={client}><RunContent context={context} runId="run-one" /></QueryClientProvider>);
    expect(html).toContain("Run access unavailable"); expect(html).not.toContain(collectionView.items[0].commit_sha);
  });
});

import { nextCollectionRefresh, type CollectionRefreshHistory } from "./InfraAutomationRun";
describe("late collection response correction", () => {
  it("corrects a preterminal response that arrives after terminal polling stops", () => {
    const history: CollectionRefreshHistory = { runVersion: null, attempted: new Set() };
    expect(nextCollectionRefresh(2, undefined, true, history)).toBeNull();
    expect(nextCollectionRefresh(3, undefined, true, history)).toBeNull();
    // The initial collection request finishes only after the run becomes terminal.
    expect(nextCollectionRefresh(3, 2, false, history)).toBe("collection");
    expect(nextCollectionRefresh(3, 2, true, history)).toBeNull();
    expect(nextCollectionRefresh(3, 3, false, history)).toBeNull();
  });
  it("does not loop on a repeated stale response and bounds changing mismatches", () => {
    const history: CollectionRefreshHistory = { runVersion: null, attempted: new Set() };
    expect(nextCollectionRefresh(20, 2, false, history)).toBe("collection");
    expect(nextCollectionRefresh(20, 2, false, history)).toBeNull();
    for (let version = 3; version <= 9; version++) expect(nextCollectionRefresh(20, version, false, history)).toBe("collection");
    expect(nextCollectionRefresh(20, 10, false, history)).toBeNull();
    expect(nextCollectionRefresh(21, 20, false, history)).toBe("collection");
  });
  it("refreshes the run when collection is newer instead of re-reading the newer child", () => {
    const history: CollectionRefreshHistory = { runVersion: null, attempted: new Set() };
    expect(nextCollectionRefresh(3, 4, false, history)).toBe("run");
    expect(nextCollectionRefresh(3, 4, false, history)).toBeNull();
    expect(nextCollectionRefresh(4, 4, false, history)).toBeNull();
  });
});

import { CancellationRequests } from "./InfraAutomationRun";
describe("late cancellation request settlement", () => {
  it("notifies a remounted listener when a definite rejection releases its marker", () => {
    const requests = new CancellationRequests();
    const ticket = requests.begin("scope", 3);
    const unsubscribe = requests.subscribe(() => {}); unsubscribe();
    let notified = 0; requests.subscribe(() => { notified++; });
    requests.reject("scope", ticket);
    expect(requests.get("scope")).toBeUndefined(); expect(notified).toBe(1);
  });
  it("does not clear newer cancellation uncertainty with an older response", () => {
    const requests = new CancellationRequests();
    const old = requests.begin("scope", 3), current = requests.begin("scope", 4);
    requests.reject("scope", old); expect(requests.get("scope")).toBe(current);
  });
  it("retains same-scope cancellation fields and disables mutation on a nonauth collection read error", () => {
    const client = new QueryClient(), key = ["automation", 1, 1, 2, "run", "run-one"];
    client.setQueryData(key, { ...runFixture, state: "running" });
    client.setQueryData([...key, "collection"], { ...collectionView, cancellation: { ...collectionView.cancellation, can_cancel: true } });
    client.getQueryCache().find({ queryKey: [...key, "collection"] })?.setState({ error: new ApiClientError("unavailable", 503), status: "error" });
    const context = { scope: { projectId: 1, workspaceId: 2 }, identity: { epoch: 1, csrfToken: "csrf" }, fresh: true } as AutomationContext;
    const html = render(<QueryClientProvider client={client}><RunContent context={context} runId="run-one" /></QueryClientProvider>);
    expect(html).toContain("Cancellation reason"); expect(html).toContain("last-known collection evidence");
    expect(html).toContain("Request cancellation"); expect(html).toContain("disabled");
  });
  it("explains stale lease and upload evidence separately even when a runner is eligible", () => {
    const item = collectionView.items[0];
    const value = { ...collectionView, items: [{ ...item, diagnosis: { code: "eligible" as const, eligible: true, correction: "Available" }, observations: item.observations.map((x) => ({ ...x, state: x.kind === "source_bound" ? x.state : "stale" as const })) }] };
    const html = render(<CollectionTimeline value={value} />);
    expect(html).toContain("lease or execution deadline"); expect(html).toContain("does not confirm that owned processes stopped");
    expect(html).toContain("expired or was superseded"); expect(html).toContain("fresh collection and analysis");
  });
});

describe("last-known run recovery", () => {
  it("retains same-scope collection and cancellation panels on run503 while disabling mutations", () => {
    const client = new QueryClient(), key = ["automation", 1, 1, 2, "run", "run-one"];
    client.setQueryData(key, { ...runFixture, state: "running" });
    client.setQueryData([...key, "collection"], { ...collectionView, cancellation: { ...collectionView.cancellation, can_cancel: true } });
    client.setQueryData([...key, "handoffs", 3], { version: 1, run_id: "run-one", project_id: 1, workspace_id: 2, items: [externalFixture] });
    client.getQueryCache().find({ queryKey: key })?.setState({ error: new ApiClientError("unavailable", 503), status: "error" });
    const context = { scope: { projectId: 1, workspaceId: 2 }, identity: { epoch: 1, csrfToken: "csrf" }, fresh: true } as AutomationContext;
    const html = render(<QueryClientProvider client={client}><RunContent context={context} runId="run-one" /></QueryClientProvider>);
    expect(html).toContain("last-known run evidence");
    expect(html).toContain("Cancellation reason");
    expect(html).toContain("Collection progress");
    expect(html).toContain("Retry run");
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Request cancellation<\/button>/);
    expect(html).not.toContain("Run unavailable</h1>");
  });
  it("still clears cached details on run401/403 and never retains a different scope after read failure", () => {
    for (const [status, projectId] of [[401, 1], [403, 1], [503, 4]]) {
      const client = new QueryClient(), key = ["automation", 1, 1, 2, "run", "run-one"];
      client.setQueryData(key, { ...runFixture, project_id: projectId });
      client.setQueryData([...key, "collection"], collectionView);
      client.getQueryCache().find({ queryKey: key })?.setState({ error: new ApiClientError("unavailable", status), status: "error" });
      const context = { scope: { projectId: 1, workspaceId: 2 }, identity: { epoch: 1 }, fresh: true } as AutomationContext;
      const html = render(<QueryClientProvider client={client}><RunContent context={context} runId="run-one" /></QueryClientProvider>);
      expect(html).not.toContain("Cancellation reason"); expect(html).not.toContain(collectionView.items[0].commit_sha);
      expect(html).toContain(status === 503 ? "Run unavailable" : "Run access unavailable");
    }
  });
});

describe("retained read panels during network faults", () => {
  const page = { items: [{ id: "attempt-one", run_id: "run-one", step_id: "collect", attempt_number: 1, state: "running" as const, version: 1, fence: 1, generation: 1, deadline_at: runFixture.deadline_at, lease_until: runFixture.deadline_at, output: null, uploads: [] }], cursor: { version: 1, limit: 25, snapshot_id: "snapshot", next_cursor: null, last_sequence: 1, gap: false, truncated: false } };
  const context = { scope: { projectId: 1, workspaceId: 2 }, identity: { epoch: 1, csrfToken: "csrf" }, fresh: true } as AutomationContext;
  it("retains step log controls and reconciliation fields when their authorized reads return503", () => {
    const client = new QueryClient(), key = ["automation", 1, 1, 2, "run", "run-one"];
    client.setQueryData(key, { ...runFixture, state: "running" });
    client.setQueryData([...key, "steps", 3, undefined], page);
    client.setQueryData([...key, "handoffs", 3], { version: 1, run_id: "run-one", project_id: 1, workspace_id: 2, items: [externalFixture] });
    for (const suffix of [["steps", 3, undefined], ["handoffs", 3]]) client.getQueryCache().find({ queryKey: [...key, ...suffix] })?.setState({ error: new ApiClientError("unavailable", 503), status: "error" });
    const html = render(<QueryClientProvider client={client}><RunContent context={context} runId="run-one" /></QueryClientProvider>);
    expect(html).toContain("last-known step attempts"); expect(html).toContain("View screened logs for attempt");
    expect(html).toContain("last-known external outcome evidence"); expect(html).toContain("Reconciliation reason for handoff-one");
    expect(html).toMatch(/<input[^>]*value=""(?![^>]*disabled)[^>]*>/);
    expect(html).toMatch(/<button[^>]*aria-label="Reconcile handoff handoff-one"[^>]*disabled/);
  });
  it("retains same-attempt screened logs on503 but clears them synchronously on403", () => {
    for (const status of [503, 403]) {
      const client = new QueryClient();
      const key = ["automation", 1, 1, 2, "logs", "run-one", "attempt-one", undefined];
      client.setQueryData(key, { ...page, items: [{ sequence: 1, text: "retained screened event" }] });
      client.getQueryCache().find({ queryKey: key })?.setState({ error: new ApiClientError("unavailable", status), status: "error" });
      const html = render(<QueryClientProvider client={client}><AttemptLogs runId="run-one" attemptId="attempt-one" context={context} onDenied={() => {}} /></QueryClientProvider>);
      if (status === 503) { expect(html).toContain("retained screened event"); expect(html).toContain("last-known screened logs"); }
      else expect(html).not.toContain("retained screened event");
    }
  });
  it("retains only exact-scope versioned read data after a nonauth failure", () => {
    const old = ["automation", 1, 1, 2, "run", "run-one", "handoffs", 3];
    const current = [...old]; current[7] = 4;
    expect(retainAttemptPage(page, old, current, new ApiClientError("unavailable", 503), 1)).toBe(page);
    expect(retainAttemptPage(page, old, current, new ApiClientError("denied", 403), 1)).toBeUndefined();
    current[2] = 9; expect(retainAttemptPage(page, old, current, null, 1)).toBeUndefined();
  });
});
