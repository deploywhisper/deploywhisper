import { Fragment, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ApiClientError } from "../api/client";
import { getRun, getRunSteps, getRunLogs, getRunReports, type AutomationScope, type Run, type Step, type StepPage, type RunReports, type LogPage } from "../api/infraAutomation";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { AutomationFrame, scopeQuery, type AutomationContext } from "./InfraAutomationShared";

export function runMatchesScope(run: Run, scope: AutomationScope): boolean {
  return run.project_id === scope.projectId && run.workspace_id === scope.workspaceId;
}
const protectedError = (error: unknown) => error instanceof ApiClientError && (error.status === 401 || error.status === 403);
// Match infra_automation/state.py; delivery_unknown remains active.
const terminalStates = new Set<Run["state"]>(["succeeded", "failed", "stopped_by_gate", "rejected", "expired", "timed_out", "cancelled"]);
export function runReadPolicy(run: Run | undefined): { interval: number | false; version: number | null } {
  return { interval: run && !terminalStates.has(run.state) ? 5000 : false, version: run?.version ?? null };
}

export function retainAttemptPage(previous: StepPage | undefined, previousKey: readonly unknown[] | undefined, currentKey: readonly unknown[], error: unknown): StepPage | undefined {
  if (error || !previousKey || previousKey.length !== currentKey.length) return undefined;
  // Only the penultimate key (run version) may change. Identity, scope, run and cursor must match.
  return previousKey.every((value, index) => index === previousKey.length - 2 || value === currentKey[index]) ? previous : undefined;
}

export function evidenceRefreshDelay(evidence: RunReports["evidence_status"] | undefined, now = Date.now(), deadlineChecks: ReadonlySet<string> = new Set()): number | null {
  if (!evidence || evidence.status !== "available") return null;
  const remaining = Date.parse(evidence.evidence_deadline) - now;
  if (!Number.isFinite(remaining)) return null;
  if (remaining > 0) return Math.min(remaining + 100, 2_147_483_647);
  return deadlineChecks.has(evidence.evidence_deadline) ? 5000 : 100;
}

export function useEvidenceDeadlineRefresh(evidence: RunReports["evidence_status"] | undefined, refresh: () => Promise<unknown>) {
  const deadlineChecks = useRef(new Set<string>());
  const [cycle, setCycle] = useState(0);
  useEffect(() => {
    const delay = evidenceRefreshDelay(evidence, Date.now(), deadlineChecks.current);
    if (delay === null) return;
    let cancelled = false;
    // Only the server decides freshness. Clock differences may require another bounded read.
    const timer = setTimeout(() => {
      if (evidence && Date.now() >= Date.parse(evidence.evidence_deadline)) {
        deadlineChecks.current.add(evidence.evidence_deadline);
      }
      void refresh().catch(() => {}).finally(() => {
        if (!cancelled) setCycle((previous) => previous + 1);
      });
    }, delay);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [evidence?.evidence_deadline, evidence?.status, evidence?.evaluated_at, refresh, cycle]);
}

export async function recoverAutomationRunAccess(refresh: () => Promise<unknown>, reads: Array<() => Promise<unknown>>): Promise<void> {
  const access = await refresh();
  if (access && typeof access === "object" && "isError" in access && access.isError) throw new Error("Access unavailable");
  await Promise.all(reads.map((read) => read()));
}

export function RunSummary({ run }: { run: Run }) {
  return <Card eyebrow="Immutable run" title={run.id} right={<span className="dw-automation-status">{run.state}</span>}>
    <dl className="dw-automation-facts">
      <dt>Created at</dt><dd>{run.created_at}</dd><dt>Execution deadline</dt><dd>{run.deadline_at}</dd>
      <dt>Workflow</dt><dd><Link to={`/infra-automation/workflows/${encodeURIComponent(run.workflow_id)}${scopeQuery({ projectId: run.project_id, workspaceId: run.workspace_id })}`}>{run.workflow_id}</Link></dd>
      <dt>Revision ID</dt><dd>{run.revision_id}</dd><dt>Run version</dt><dd>{run.version}</dd>
      <dt>Requester ID</dt><dd>{run.requested_by}</dd><dt>Project ID</dt><dd>{run.project_id}</dd><dt>Workspace ID</dt><dd>{run.workspace_id}</dd>
      <dt>Snapshot digest</dt><dd><code>{run.snapshot_digest}</code></dd>
      <dt>Workflow definition digest</dt><dd><code>{run.definition_digest}</code></dd>
      <dt>Scalar input digest</dt><dd><code>{run.input_digest}</code></dd>
      {run.cancel_requested && <><dt>Cancellation requested at</dt><dd>{run.cancellation_requested_at ?? "Time unavailable"}</dd></>}
    </dl>
    <p className="dw-muted">Digests above describe the run snapshot, workflow definition and scalar inputs. Artifact digests are shown with their attempt outputs.</p>
  </Card>;
}

export function AttemptTimeline({ steps, onLogs }: { steps: Step[]; onLogs: (id: string) => void }) {
  return <Card eyebrow="Server-ordered timeline" title="Step attempts">
    <p className="dw-muted">Start and finish times unavailable. Deadlines and leases are execution bounds.</p>
    {steps.length === 0 ? <p>No step attempts available yet.</p> : <ol className="dw-automation-attempts">{steps.map((step) => <li key={step.id}>
      <h3>{step.step_id} <span className="dw-automation-status">{step.state}</span></h3>
      <p>Attempt {step.attempt_number} · ID <code>{step.id}</code></p>
      <dl className="dw-automation-facts"><dt>Deadline</dt><dd>{step.deadline_at}</dd><dt>Lease until</dt><dd>{step.lease_until ?? "Unavailable"}</dd>
        <dt>Version / fence / generation</dt><dd>{step.version} / {step.fence} / {step.generation}</dd>
        {distinctOutputs(step).map((output, index) => <Fragment key={`${output.reference}:${index}`}>
          <dt>{output.kind === "screened_artifacts" ? "Artifact output digest" : `${output.kind} output digest`}</dt><dd><code>{output.digest}</code></dd>
          <dt>Output reference</dt><dd><code>{output.reference}</code></dd>
        </Fragment>)}
      </dl>
      <Button onClick={() => onLogs(step.id)}>View screened logs for attempt {step.attempt_number} ({step.step_id})</Button>
    </li>)}</ol>}
  </Card>;
}

export function distinctOutputs(step: Step) {
  const seen = new Set<string>();
  return [...(step.output ? [step.output] : []), ...(step.uploads ?? [])].filter((output) => {
    const key = JSON.stringify([output.kind, output.reference, output.digest]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function ScreenedLogContent({ page }: { page: LogPage }) {
  return <><p className="dw-muted">Log timestamps unavailable. Each page is bounded to {page.cursor.limit} chunks.</p>
    {page.cursor.gap && <p role="status">Gap reported in the retained log sequence.</p>}
    {page.cursor.truncated && <p role="status">Log output is truncated; this page does not represent the complete output.</p>}
    {!page.items.length && <p>No screened log chunks on this page.</p>}
    {page.items.map((chunk) => <div key={chunk.sequence}><h3>Sequence {chunk.sequence}</h3><pre className="dw-automation-log">{chunk.text}</pre></div>)}
    <p className="dw-muted">Last sequence: {page.cursor.last_sequence}</p>
  </>;
}

export function EvidenceSummary({ reports, runId }: { reports: RunReports; runId: string }) {
  const evidence = reports.evidence_status;
  return <Card eyebrow="Evidence and uncertainty" title={`Evidence ${evidence.status}`}>
    <p>Uploaded evidence is advisory and not eligible for approval. Repository identity and immutable commit are unverified.</p>
    <dl className="dw-automation-facts"><dt>Evaluated at</dt><dd>{evidence.evaluated_at}</dd><dt>Evidence deadline</dt><dd>{evidence.evidence_deadline}</dd>
      <dt>Manifest present</dt><dd>{evidence.manifest_present ? "Yes" : "No"}</dd><dt>Evidence basis</dt><dd>Run {evidence.run_state}, version {evidence.run_version}; attempt {evidence.attempt_id ?? "unavailable"}, {evidence.attempt_state ?? "unavailable"}</dd>
    </dl>
    <Uncertainty limitations={evidence.limitations} todos={evidence.context_todos} />
    {reports.items.length ? <ul>{reports.items.map((link) => <li key={link.id}>
      <Link to={`${link.report_url}?private=1&automation_run=${encodeURIComponent(runId)}`}>Open permanent briefing #{link.report_id}</Link>
      <p>{link.provenance.limitation}</p><Uncertainty limitations={link.limitations} todos={link.context_todos} />
    </li>)}</ul> : <p>No permanent briefing is available for this run.</p>}
  </Card>;
}

export function Uncertainty({ limitations, todos }: { limitations: string[]; todos: string[] }) {
  return <>{limitations.length > 0 && <><h3>Limitations</h3><ul>{limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
    {todos.length > 0 && <><h3>Context to review</h3><ul>{todos.map((item, index) => <li key={index}>{item}</li>)}</ul></>}</>;
}

export function AttemptLogs({ runId, attemptId, context, onDenied }: { runId: string; attemptId: string; context: AutomationContext; onDenied: () => void }) {
  const [cursor, setCursor] = useState<string>();
  const logs = useQuery({ queryKey: ["automation", context.identity.epoch, context.scope.projectId, context.scope.workspaceId, "logs", runId, attemptId, cursor], queryFn: ({ signal }) => getRunLogs(runId, attemptId, cursor, signal), retry: false, gcTime: 0, refetchOnWindowFocus: false });
  useEffect(() => { if (protectedError(logs.error)) onDenied(); }, [logs.error, onDenied]);
  return <Card eyebrow="Requested screened logs" title={`Attempt ${attemptId}`}>
    {logs.isPending && <p role="status">Loading screened logs…</p>}
    {logs.error && <p role="alert">Screened logs unavailable. Refresh access or retry this page.</p>}
    {!logs.error && logs.data && <><ScreenedLogContent page={logs.data} />{logs.data.cursor.next_cursor && <Button onClick={() => setCursor(logs.data.cursor.next_cursor ?? undefined)}>Next log page</Button>}</>}
    {cursor && <Button onClick={() => setCursor(undefined)}>First log page</Button>}
    <Button disabled={logs.isFetching} onClick={() => void logs.refetch()}>Refresh logs</Button>
  </Card>;
}

export function RunContent({ context, runId }: { context: AutomationContext; runId: string }) {
  const [cursor, setCursor] = useState<string>();
  const [attempt, setAttempt] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);
  const [recovering, setRecovering] = useState(false);
  const runHeading = useRef<HTMLHeadingElement>(null);
  const focusedRun = useRef<string | null>(null);
  const key = ["automation", context.identity.epoch, context.scope.projectId, context.scope.workspaceId, "run", runId];
  const run = useQuery({ queryKey: key, queryFn: ({ signal }) => getRun(runId, signal), retry: false, gcTime: 0, refetchInterval: (query) => query.state.error ? false : runReadPolicy(query.state.data).interval, refetchOnWindowFocus: false });
  const matching = !!run.data && run.data.id === runId && runMatchesScope(run.data, context.scope);
  const enabled = matching && !run.error && !denied;
  const readPolicy = runReadPolicy(run.data);
  // Versioned child keys force a final read when the run reaches a terminal version.
  const stepKey = [...key, "steps", readPolicy.version, cursor];
  const steps = useQuery<StepPage>({ queryKey: stepKey, placeholderData: (previous, previousQuery) => retainAttemptPage(previous, previousQuery?.queryKey, stepKey, previousQuery?.state.error), queryFn: ({ signal }) => getRunSteps(runId, cursor, signal), enabled, retry: false, gcTime: 0, refetchInterval: enabled ? readPolicy.interval : false, refetchOnWindowFocus: false });
  const reports = useQuery({ queryKey: [...key, "reports", readPolicy.version], queryFn: ({ signal }) => getRunReports(runId, signal), enabled, retry: false, gcTime: 0, refetchInterval: enabled ? readPolicy.interval : false, refetchOnWindowFocus: false });
  useEvidenceDeadlineRefresh(enabled && !reports.error ? reports.data?.evidence_status : undefined, reports.refetch);
  const accessDenied = denied || [run.error, steps.error, reports.error].some(protectedError);
  useEffect(() => {
    if (matching && !accessDenied && !run.error && runHeading.current && focusedRun.current !== runId) {
      focusedRun.current = runId;
      runHeading.current.focus();
    }
  }, [runId, matching, accessDenied, run.error]);
  async function recoverAccess() {
    setDenied(true);
    setRecovering(true);
    try {
      await recoverAutomationRunAccess(context.refresh, [
        () => run.refetch({ throwOnError: true }),
        () => steps.refetch({ throwOnError: true }),
        () => reports.refetch({ throwOnError: true }),
      ]);
      setDenied(false);
    } catch {
      // Keep protected data hidden until every required live read succeeds.
      setDenied(true);
    } finally {
      setRecovering(false);
    }
  }
  if (accessDenied || recovering) return <div role="alert"><h1>Run access unavailable</h1><p>Your session or permission changed. Protected run details have been cleared.</p><Button disabled={recovering} onClick={() => void recoverAccess()}>{recovering ? "Refreshing access…" : "Refresh access"}</Button></div>;
  if (run.isPending) return <p role="status">Loading immutable run…</p>;
  if (run.error || !run.data || run.data.id !== runId) return <div role="alert"><h1>Run unavailable</h1><p>The run could not be read. Check your connection and access.</p><Button onClick={() => void run.refetch()}>Retry run</Button></div>;
  if (!matching) return <Card title="Run belongs to another scope"><p>Select the run’s project and workspace to read its details.</p>
    {run.data.project_id !== context.scope.projectId ? <Button onClick={() => context.selectProject(run.data.project_id)}>Use run project</Button> : <Button onClick={() => context.selectWorkspace(run.data.workspace_id)}>Use run workspace</Button>}
  </Card>;
  return <div className="dw-automation-stack"><Link to={`/infra-automation${scopeQuery(context.scope)}&view=runs`}>← Run history</Link><h2 ref={runHeading} tabIndex={-1}>Preflight run</h2>
    {!context.fresh && <p role="status">Access is being refreshed. Current historical run data is read-only.</p>}
    <RunSummary run={run.data} />
    {steps.isPending && <p role="status">Loading step attempts…</p>}
    {steps.isPlaceholderData && <p role="status">Refreshing step attempts…</p>}
    {steps.error ? <p role="alert">Step attempts unavailable. <Button onClick={() => void steps.refetch()}>Retry attempts</Button>{cursor && <Button onClick={() => setCursor(undefined)}>Reload current attempts</Button>}</p> : steps.data && <>
      <AttemptTimeline steps={steps.data.items} onLogs={setAttempt} />
      {(steps.data.cursor.gap || steps.data.cursor.truncated) && <p role="status">Attempt history {steps.data.cursor.gap ? "contains a sequence gap" : "is truncated"}.</p>}
      <div className="dw-automation-actions">{cursor && <Button onClick={() => setCursor(undefined)}>First attempt page</Button>}{steps.data.cursor.next_cursor && <Button onClick={() => setCursor(steps.data.cursor.next_cursor ?? undefined)}>Next attempt page</Button>}</div>
    </>}
    {attempt && <AttemptLogs key={attempt} runId={runId} attemptId={attempt} context={context} onDenied={() => setDenied(true)} />}
    {reports.isPending && <p role="status">Loading evidence status…</p>}
    {reports.error ? <p role="alert">Evidence status unavailable. <Button onClick={() => void reports.refetch()}>Retry evidence</Button></p> : reports.data && <EvidenceSummary reports={reports.data} runId={runId} />}
  </div>;
}

export function InfraAutomationRunScreen() {
  const params = useParams();
  return <AutomationFrame>{(context) => <RunContent key={`${context.identity.epoch}:${context.scope.projectId}:${context.scope.workspaceId}:${params.runId}`} context={context} runId={params.runId ?? ""} />}</AutomationFrame>;
}
