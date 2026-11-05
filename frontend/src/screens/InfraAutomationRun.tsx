import { Fragment, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiClientError } from "../api/client";
import { getRunHandoffs, reconcileHandoff, type ExternalHandoff, type RunHandoffs, getRun, getRunSteps, getRunLogs, getRunReports, type AutomationScope, type Run, type Step, type StepPage, type RunReports, type LogPage } from "../api/infraAutomation";
import { cancelCollectionRun, getCollectionView, validCollectionReason, isConfirmedCollectionRejection, type CollectionView, type CollectionObservation } from "../api/infraAutomationCollection";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { AutomationFrame, scopeQuery, type AutomationContext } from "./InfraAutomationShared";
import { ApprovalReviewPanel } from "./InfraAutomationApprovals";

export function runMatchesScope(run: Run, scope: AutomationScope): boolean {
  return run.project_id === scope.projectId && run.workspace_id === scope.workspaceId;
}
const protectedError = (error: unknown) => error instanceof ApiClientError && (error.status === 401 || error.status === 403);
// Match infra_automation/state.py; delivery_unknown remains active.
const terminalStates = new Set<Run["state"]>(["succeeded", "failed", "stopped_by_gate", "rejected", "expired", "timed_out", "cancelled"]);
export function runReadPolicy(run: Run | undefined): { interval: number | false; version: number | null } {
  return { interval: run && !terminalStates.has(run.state) ? 5000 : false, version: run?.version ?? null };
}

export function retainAttemptPage<T>(previous: T | undefined, previousKey: readonly unknown[] | undefined, currentKey: readonly unknown[], error: unknown, versionOffsetFromEnd = 2): T | undefined {
  if (protectedError(error) || !previousKey || previousKey.length !== currentKey.length) return undefined;
  // Only the declared run-version position may change. Identity, scope, run,
  // resource kind and any cursor must still match; non-auth errors retain historical reads only.
  return previousKey.every((value, index) => index === previousKey.length - versionOffsetFromEnd || value === currentKey[index]) ? previous : undefined;
}

export type CollectionRefreshHistory = { runVersion: number | null; attempted: Set<number> };
export function nextCollectionRefresh(runVersion: number | undefined, collectionVersion: number | undefined, busy: boolean, history: CollectionRefreshHistory): "run" | "collection" | null {
  if (busy || runVersion === undefined || collectionVersion === undefined) return null;
  if (history.runVersion !== runVersion) { history.runVersion = runVersion; history.attempted.clear(); }
  if (runVersion === collectionVersion || history.attempted.has(collectionVersion) || history.attempted.size >= 8) return null;
  history.attempted.add(collectionVersion);
  return collectionVersion < runVersion ? "collection" : "run";
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

export function EvidenceSummary({ reports, runId, stale = false }: { reports: RunReports; runId: string; stale?: boolean }) {
  const evidence = reports.evidence_status;
  return <Card eyebrow="Evidence and uncertainty" title={`${stale ? "Last-known evidence" : "Evidence"} ${evidence.status}`}>
    {stale && <p>Stored status only; current evidence freshness and authority are unavailable. Refresh before acting.</p>}
    <p>Briefings remain advisory. Approval eligibility depends on retained source evidence and current server checks.</p>
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
    {logs.error && <p role="alert">Screened logs unavailable. {logs.data && !protectedError(logs.error) && "Retaining last-known screened logs; refresh this page before treating them as current."} Refresh access or retry this page.</p>}
    {!protectedError(logs.error) && logs.data && <><ScreenedLogContent page={logs.data} />{logs.data.cursor.next_cursor && <Button onClick={() => setCursor(logs.data.cursor.next_cursor ?? undefined)}>Next log page</Button>}</>}
    {cursor && <Button onClick={() => setCursor(undefined)}>First log page</Button>}
    <Button disabled={logs.isFetching} onClick={() => void logs.refetch()}>Refresh logs</Button>
  </Card>;
}

export function reconciliationFailure(error: unknown): "denied" | "correctable" | "ambiguous" {
  if (protectedError(error)) return "denied";
  return error instanceof ApiClientError && [400, 404, 409, 422, 429].includes(error.status) && ["binding_conflict", "request_validation_failed", "quota_exceeded"].includes(error.code ?? "") ? "correctable" : "ambiguous";
}

export function HandoffFacts({ operation }: { operation: ExternalHandoff }) {
  return <section aria-label={`External handoff ${operation.id}`}>
    <h3>Handoff {operation.id}</h3>
    <dl className="dw-automation-facts">
      <dt>Operation state / version</dt><dd>{operation.state} / {operation.version}</dd>
      <dt>Dispatch acceptance</dt><dd>{operation.acceptance ? "Dispatch accepted — acceptance alone does not verify completion" : "No correlated dispatch acceptance recorded"}</dd>
      <dt>GitHub observation</dt><dd>{operation.observation ? `${operation.observation.status}${operation.observation.conclusion ? ` · ${operation.observation.conclusion}` : ""} — observation only` : "Not observed"}</dd>
      <dt>Verified receiver completion</dt><dd>{operation.verified_outcome ?? "Unknown — no verified terminal receiver proof"}</dd>
      <dt>Receiver state</dt><dd>{operation.receiver_state ?? "Not reported"}</dd>
      <dt>Target lock</dt><dd>{operation.lock_status}</dd>
      {operation.acceptance && <><dt>Pipeline workflow revision</dt><dd><code>{operation.acceptance.workflow_revision}</code></dd><dt>GitHub run</dt><dd><a href={operation.acceptance.html_url} target="_blank" rel="noopener noreferrer">Open GitHub run {operation.acceptance.run_id}</a></dd></>}
    </dl>
    {operation.cancel_requested && <p role="status">Cancellation requested. This does not confirm that external work has stopped.</p>}
    {operation.verified_outcome === null && <p>Review the registered GitHub run and receiver evidence. Unknown delivery retains its target lock; do not resend the dispatch. Pipeline workflow revision does not identify the infrastructure source commit.</p>}
    {operation.lock_status === "broken" && <p role="status">The target lock was broken by an operator; this does not prove external completion.</p>}
  </section>;
}

function HandoffControl({ operation, context, refresh, onDenied, pendingRequests }: { operation: ExternalHandoff; context: AutomationContext; refresh: () => Promise<unknown>; onDenied: () => void; pendingRequests: Map<string, number> }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const unknownVersion = pendingRequests.get(operation.id) ?? null;
  const setUnknownVersion = (version: number) => pendingRequests.set(operation.id, version);
  const blocked = unknownVersion !== null && operation.version <= unknownVersion;
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function reconcile() {
    if (busy || blocked || !context.fresh || !context.identity.csrfToken || !reason.trim()) return;
    setBusy(true); setMessage("");
    let submitted = false;
    try {
      await context.ensureFresh();
      if (!mounted.current) return;
      submitted = true;
      setUnknownVersion(operation.version);
      await reconcileHandoff(operation, context.scope, reason, context.identity.csrfToken);
      if (!mounted.current) return;
      setMessage("Reconciliation recorded. Refresh current outcome evidence.");
      setUnknownVersion(operation.version);
      await refresh();
    } catch (error) {
      if (!mounted.current) return;
      const kind = reconciliationFailure(error);
      if (kind === "denied") onDenied();
      else if (!submitted) setMessage("Current access could not be verified. Refresh access before a manual reconciliation request.");
      else if (kind === "correctable") {
        if (pendingRequests.get(operation.id) === operation.version) pendingRequests.delete(operation.id);
        setMessage("Reconciliation was rejected. Refresh current evidence, correct the reason if needed, then submit a manual request.");
      }
      else { setUnknownVersion(operation.version); setMessage("Reconciliation was not confirmed. Read current evidence before continuing; the request will not be resent automatically."); }
    } finally { if (mounted.current) setBusy(false); }
  }
  return <><HandoffFacts operation={operation} />{message && <p role="status">{message}</p>}
    {blocked && <p role="status">A previous request remains unconfirmed at this operation version. Refresh outcome evidence to resolve it.</p>}
    {operation.reconciliation_available && <div className="dw-automation-stack"><label>Reconciliation reason for {operation.id}<input value={reason} maxLength={1024} onChange={(event) => setReason(event.target.value)} disabled={busy || blocked} /></label>
      <Button aria-label={`Reconcile handoff ${operation.id}`} disabled={busy || blocked || !context.fresh || !context.identity.csrfToken || !reason.trim()} onClick={() => void reconcile()}>{busy ? "Reconciling…" : "Reconcile handoff"}</Button>
      <p className="dw-muted">Reads registered external outcome evidence. This does not dispatch again or manually declare success.</p>
    </div>}</>;
}

export function HandoffOutcomes({ handoffs, context, refresh, onDenied, pendingRequests }: { handoffs: RunHandoffs; context: AutomationContext; refresh: () => Promise<unknown>; onDenied: () => void; pendingRequests: Map<string, number> }) {
  return <Card eyebrow="External outcome evidence" title="External handoffs">
    {handoffs.items.length ? handoffs.items.map((operation) => <HandoffControl key={operation.id} operation={operation} context={context} refresh={refresh} onDenied={onDenied} pendingRequests={pendingRequests} />) : <p>No external handoffs recorded for this run.</p>}
    <Button onClick={() => void refresh()}>Refresh outcome evidence</Button>
  </Card>;
}


type CancellationTicket = { version: number };
export class CancellationRequests {
  private values = new Map<string, CancellationTicket>();
  private listeners = new Set<() => void>();
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  get = (key: string) => this.values.get(key);
  private changed() { this.listeners.forEach((listener) => listener()); }
  begin(key: string, version: number): CancellationTicket { const value = { version }; this.values.set(key, value); this.changed(); return value; }
  reject(key: string, ticket: CancellationTicket) { if (this.get(key) !== ticket) return; this.values.delete(key); this.changed(); }
}
const pendingCancellations = new CancellationRequests();
function observationCorrection(observation: CollectionObservation): string | null {
  if (observation.state !== "stale" && observation.state !== "timed_out") return null;
  if (observation.kind === "collection" || observation.kind === "analysis") return `The ${observation.kind} lease or execution deadline is no longer current. This does not confirm that owned processes stopped. Review runner recovery and request fresh collection and analysis.`;
  if (observation.kind === "screened_upload") return "Screened upload evidence expired or was superseded. Request fresh collection and analysis; do not reuse the old evidence for approval.";
  return null;
}
export function collectionAnnouncement(value: CollectionView): string {
  return value.items.map((item) => `${item.step_id}: ${item.observations.map((observation) => `${observation.kind.replaceAll("_", " ")} ${observation.state.replaceAll("_", " ")}`).join(", ")}`).join(". ");
}
export function CollectionTimeline({ value, stale = false }: { value: CollectionView; stale?: boolean }) {
  const signature = collectionAnnouncement(value);
  const previous = useRef(signature);
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => { if (!stale && previous.current !== signature) { previous.current = signature; setAnnouncement(signature); } }, [signature, stale]);
  return <Card eyebrow="Durable collection evidence" title="Collection progress">
    <p aria-live="polite" aria-atomic="true" className="sr-only">{announcement}</p>
    <p>Observed by the server at {value.observed_at}. Observation time is not a stage completion time. Unobserved stages are not assumed complete.</p>
    {value.items.map((item) => <section key={item.step_id} aria-label={`Collection ${item.step_id}`}>
      <h3>{item.step_id}</h3><dl className="dw-automation-facts"><dt>Bound repository</dt><dd>{item.repository_id}</dd><dt>Immutable source commit</dt><dd><code>{item.commit_sha}</code></dd><dt>Requested profile</dt><dd><code>{item.profile_digest}</code></dd><dt>Attempt</dt><dd>{item.attempt_number ?? "Not assigned"} · {item.attempt_state ?? "Not observed"}</dd><dt>Lease until</dt><dd>{item.lease_until ?? "Not observed"}</dd></dl>
      <ol className="dw-automation-attempts">{item.observations.map((observation) => <li key={observation.kind}><strong>{{ source_bound: "Source bound to run", collection: "Runner collection", screened_upload: "Server screening and upload", analysis: "Shared analysis" }[observation.kind]}</strong>: {observation.state.replaceAll("_", " ")}<p>{observation.event_at ? `Recorded event: ${observation.event_at}` : "Event time unavailable"}</p>{observationCorrection(observation) && <p>{observationCorrection(observation)}</p>}</li>)}</ol>
      {item.routing_failure && <p role="status">No eligible runner was available when this attempt was requested. The server did not wait or use a fallback.</p>}
      {!item.diagnosis.eligible && <p>{item.diagnosis.correction}</p>}
    </section>)}
    <p>No eligible runner waits are queued: the current finite wait is {value.finite_wait_seconds} seconds. Correct the reported configuration before requesting a new collection; there is no silent fallback.</p>
    <Uncertainty limitations={value.limitations} todos={[]} />
  </Card>;
}
export function CancelRunControl({ run, value, context, fresh, refresh, onDenied }: { run: Run; value: CollectionView; context: AutomationContext; fresh: boolean; refresh: () => Promise<unknown>; onDenied: () => void }) {
  const key = `${context.identity.epoch}:${context.scope.projectId}:${context.scope.workspaceId}:${run.id}`;
  const pending = useSyncExternalStore(pendingCancellations.subscribe, () => pendingCancellations.get(key), () => pendingCancellations.get(key));
  const blocked = pending !== undefined && run.version <= pending.version;
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const messageRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => { if (message) messageRef.current?.focus(); }, [message]);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function cancel() {
    if (busy || blocked || !fresh || !context.fresh || !context.identity.csrfToken || !value.cancellation.can_cancel || !validCollectionReason(reason)) return;
    setBusy(true); setMessage(""); let ticket: CancellationTicket | undefined; let committed = false;
    try {
      await context.ensureFresh();
      const current = await getCollectionView(run.id, context.scope);
      if (!mounted.current) return;
      if (current.run_version !== run.version || !current.cancellation.can_cancel) throw new ApiClientError("Cancellation state changed.", 409, { code: "binding_conflict" });
      const result = await cancelCollectionRun(run, context.scope, reason, context.identity.csrfToken, () => { ticket = pendingCancellations.begin(key, run.version); });
      committed = true;
      if (!mounted.current) return;
      setMessage(result.cancel_requested ? "Cancellation request recorded. Owned-process termination and external stop are not confirmed by this response." : "Current run state returned. No cancellation or external stop is inferred; review refreshed evidence.");
      setReason(""); await refresh();
    } catch (error) {
      if (ticket && !committed && isConfirmedCollectionRejection(error)) pendingCancellations.reject(key, ticket);
      if (!mounted.current) return;
      const failure = reconciliationFailure(error);
      if (failure === "denied") onDenied();
      else if (committed) setMessage("Cancellation response was received, but current evidence could not be refreshed. Read current server state; nothing is resent automatically.");
      else if (ticket && !isConfirmedCollectionRejection(error)) setMessage("Cancellation was not confirmed. Refresh server state before another request; nothing is resent automatically.");
      else setMessage("Cancellation was rejected or state changed. Refresh access and run evidence before a new request.");
    } finally { if (mounted.current) setBusy(false); }
  }
  return <Card eyebrow="Cancellation evidence" title="Cancellation">
    <dl className="dw-automation-facts"><dt>Request recorded</dt><dd>{value.cancellation.requested ? value.cancellation.requested_at ?? "Yes; timestamp unavailable" : "No"}</dd><dt>Owned-process termination</dt><dd>Not independently confirmed by this view</dd><dt>External stop</dt><dd>{value.cancellation.external_possible ? "Not confirmed; inspect verified external outcome evidence below" : "No external acceptance reported by this view"}</dd></dl>
    {value.cancellation.external_possible && <p>The external pipeline may already have accepted work. A cancellation request does not stop it or release retained target locks. Reconcile the recorded outcome; do not resend.</p>}
    {message && <p role="status" tabIndex={-1} ref={messageRef}>{message}</p>}
    {blocked && <p role="status">A cancellation request remains unconfirmed at this run version. Refresh current run evidence before continuing.</p>}
    {value.cancellation.can_cancel && <div className="dw-automation-form"><label className="dw-field">Cancellation reason<input value={reason} maxLength={256} disabled={busy || blocked} onChange={(event) => setReason(event.target.value)} /></label><div><Button disabled={busy || blocked || !fresh || !context.fresh || !context.identity.csrfToken || !validCollectionReason(reason)} onClick={() => void cancel()}>{busy ? "Requesting cancellation…" : "Request cancellation"}</Button></div></div>}
    {reason.length > 0 && !validCollectionReason(reason) && <p role="alert">Use a nonempty single-line cancellation reason of at most 256 characters; tabs and line separators are not accepted.</p>}
    <Button disabled={busy} onClick={() => void refresh()}>Refresh cancellation evidence</Button>
  </Card>;
}

export function RunContent({ context, runId }: { context: AutomationContext; runId: string }) {
  const [cursor, setCursor] = useState<string>();
  const [attempt, setAttempt] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);
  const [recovering, setRecovering] = useState(false);
  // Keep ambiguous writes blocked across child read errors and run-version changes.
  const pendingHandoffRequests = useRef(new Map<string, number>());
  const collectionRefreshHistory = useRef<CollectionRefreshHistory>({ runVersion: null, attempted: new Set() });
  const retainedSteps = useRef<{ key: readonly unknown[]; value: StepPage }>();
  const retainedReports = useRef<{ key: readonly unknown[]; value: RunReports }>();
  const retainedHandoffs = useRef<{ key: readonly unknown[]; value: RunHandoffs }>();
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
  const reportKey = [...key, "reports", readPolicy.version];
  const handoffKey = [...key, "handoffs", readPolicy.version];
  const reports = useQuery<RunReports>({ queryKey: reportKey, placeholderData: (previous, previousQuery) => retainAttemptPage(previous, previousQuery?.queryKey, reportKey, previousQuery?.state.error, 1), queryFn: ({ signal }) => getRunReports(runId, signal), enabled, retry: false, gcTime: 0, refetchInterval: enabled ? readPolicy.interval : false, refetchOnWindowFocus: false });
  const handoffs = useQuery<RunHandoffs>({ queryKey: handoffKey, placeholderData: (previous, previousQuery) => retainAttemptPage(previous, previousQuery?.queryKey, handoffKey, previousQuery?.state.error, 1), queryFn: ({ signal }) => getRunHandoffs(runId, context.scope, signal), enabled, retry: false, gcTime: 0, refetchInterval: (query) => enabled && !query.state.error ? readPolicy.interval : false, refetchOnWindowFocus: false });
  const collection = useQuery({ queryKey: [...key, "collection"], queryFn: ({ signal }) => getCollectionView(runId, context.scope, signal), enabled, retry: false, gcTime: 0, refetchInterval: enabled ? readPolicy.interval : false, refetchOnWindowFocus: false });
  useEffect(() => {
    if (!enabled || collection.error || run.error) return;
    const target = nextCollectionRefresh(run.data?.version, collection.data?.run_version, run.isFetching || collection.isFetching, collectionRefreshHistory.current);
    if (target === "collection") void collection.refetch();
    else if (target === "run") void run.refetch();
  }, [enabled, run.data?.version, collection.data?.run_version, run.isFetching, collection.isFetching, run.error, collection.error, run.refetch, collection.refetch]);
  useEvidenceDeadlineRefresh(enabled && !reports.error ? reports.data?.evidence_status : undefined, reports.refetch);
  const accessDenied = denied || [run.error, steps.error, reports.error, handoffs.error, collection.error].some(protectedError);
  // Placeholder data survives a version transition while pending, but React
  // Query drops it on error. Keep only the last authorized read of this exact
  // scope/resource/cursor so a transport failure cannot remove focused controls.
  const stepData = steps.data ?? retainAttemptPage(retainedSteps.current?.value, retainedSteps.current?.key, stepKey, steps.error);
  const reportData = reports.data ?? retainAttemptPage(retainedReports.current?.value, retainedReports.current?.key, reportKey, reports.error, 1);
  const handoffData = handoffs.data ?? retainAttemptPage(retainedHandoffs.current?.value, retainedHandoffs.current?.key, handoffKey, handoffs.error, 1);
  if (accessDenied || !matching) {
    retainedSteps.current = undefined; retainedReports.current = undefined; retainedHandoffs.current = undefined;
  } else {
    if (steps.data && !steps.isPlaceholderData && !steps.error) retainedSteps.current = { key: stepKey, value: steps.data };
    if (reports.data && !reports.isPlaceholderData && !reports.error) retainedReports.current = { key: reportKey, value: reports.data };
    if (handoffs.data && !handoffs.isPlaceholderData && !handoffs.error) retainedHandoffs.current = { key: handoffKey, value: handoffs.data };
  }
  useEffect(() => { if ([run.error, steps.error, reports.error, handoffs.error, collection.error].some(protectedError)) setDenied(true); }, [run.error, steps.error, reports.error, handoffs.error, collection.error]);
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
        () => handoffs.refetch({ throwOnError: true }),
        () => collection.refetch({ throwOnError: true }),
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
  if (!run.data || run.data.id !== runId || (run.error && !matching)) return <div role="alert"><h1>Run unavailable</h1><p>The run could not be read. Check your connection and access.</p><Button onClick={() => void run.refetch()}>Retry run</Button></div>;
  if (!matching) return <Card title="Run belongs to another scope"><p>Select the run’s project and workspace to read its details.</p>
    {run.data.project_id !== context.scope.projectId ? <Button onClick={() => context.selectProject(run.data.project_id)}>Use run project</Button> : <Button onClick={() => context.selectWorkspace(run.data.workspace_id)}>Use run workspace</Button>}
  </Card>;
  return <div className="dw-automation-stack dw-automation-run"><Link to={`/infra-automation${scopeQuery(context.scope)}&view=runs`}>← Run history</Link><h2 ref={runHeading} tabIndex={-1}>Preflight run</h2>
    {!context.fresh && <p role="status">Access is being refreshed. Current historical run data is read-only.</p>}
    {run.error && <p role="alert">Retaining last-known run evidence; current server state is unavailable and mutation controls are disabled. <Button onClick={() => void run.refetch()}>Retry run</Button></p>}
    <RunSummary run={run.data} />
    {collection.data && collection.data.run_version !== run.data.version && !collection.error && <p role="status">Collection observations are from a different run version. Refresh current evidence before acting. <Button onClick={() => { void Promise.all([run.refetch(), collection.refetch()]); }}>Refresh current collection evidence</Button></p>}
    {collection.error && <p role="alert">Collection observations unavailable. {collection.data && "Retaining last-known collection evidence; current authority is unavailable and mutation controls are disabled."} <Button onClick={() => void collection.refetch()}>Retry collection evidence</Button></p>}
    {collection.data && <>
      {collection.data.items.length > 0 && <CollectionTimeline value={collection.data} stale={!!run.error || !!collection.error || collection.data.run_version !== run.data.version} />}
      <CancelRunControl run={run.data} value={collection.data} context={context} fresh={!run.error && !collection.error && !run.isFetching && !collection.isFetching && collection.data.run_version === run.data.version} refresh={() => Promise.all([run.refetch(), collection.refetch()])} onDenied={() => setDenied(true)} />
    </>}
    {handoffs.isPending && <p role="status">Loading external outcome evidence…</p>}
    {handoffs.error && <p role="alert">External outcome evidence unavailable. {handoffData && "Retaining last-known external outcome evidence; reconciliation requires a fresh read."} <Button onClick={() => void handoffs.refetch()}>Retry outcome evidence</Button></p>}
    {handoffData && <HandoffOutcomes handoffs={handoffData} context={{ ...context, fresh: context.fresh && !run.error && !run.isFetching && !handoffs.error && !!handoffs.data && !handoffs.isPlaceholderData }} refresh={handoffs.refetch} onDenied={() => setDenied(true)} pendingRequests={pendingHandoffRequests.current} />}
    {steps.isPending && <p role="status">Loading step attempts…</p>}
    {steps.isPlaceholderData && <p role="status">Refreshing step attempts…</p>}
    {steps.error && <p role="alert">Step attempts unavailable. {stepData && "Retaining last-known step attempts; current lease and execution state are unavailable."} <Button onClick={() => void steps.refetch()}>Retry attempts</Button>{cursor && <Button onClick={() => setCursor(undefined)}>Reload current attempts</Button>}</p>}
    {stepData && <>
      <AttemptTimeline steps={stepData.items} onLogs={setAttempt} />
      {(stepData.cursor.gap || stepData.cursor.truncated) && <p role="status">Attempt history {stepData.cursor.gap ? "contains a sequence gap" : "is truncated"}.</p>}
      <div className="dw-automation-actions">{cursor && <Button onClick={() => setCursor(undefined)}>First attempt page</Button>}{stepData.cursor.next_cursor && <Button onClick={() => setCursor(stepData.cursor.next_cursor ?? undefined)}>Next attempt page</Button>}</div>
    </>}
    {attempt && <AttemptLogs key={attempt} runId={runId} attemptId={attempt} context={context} onDenied={() => setDenied(true)} />}
    {reports.isPending && <p role="status">Loading evidence status…</p>}
    {reports.error && <p role="alert">Evidence status unavailable. {reportData && "Retaining last-known report evidence; current freshness is unavailable."} <Button onClick={() => void reports.refetch()}>Retry evidence</Button></p>}
    {reportData && <EvidenceSummary reports={reportData} runId={runId} stale={!!run.error || !!reports.error || !reports.data || reports.isPlaceholderData} />}
  </div>;
}

export function InfraAutomationRunScreen() {
  const params = useParams();
  const [search] = useSearchParams();
  const approvals = search.getAll("approval_id");
  return <AutomationFrame>{(context) => {
    const key = `${context.identity.epoch}:${context.scope.projectId}:${context.scope.workspaceId}:${params.runId}`;
    if (approvals.length > 1) return <div role="alert"><h2>Review selection unavailable</h2><p>Choose one request from the scoped approval inbox.</p><Link to={`/infra-automation/approvals${scopeQuery(context.scope)}`}>Open approval inbox</Link></div>;
    if (approvals.length === 1) return <div className="dw-automation-stack" key={`${key}:${approvals[0]}`}>
      <div className="dw-automation-actions"><Link aria-label="Approval inbox" to={`/infra-automation/approvals${scopeQuery(context.scope)}`}>← Approval inbox</Link><Link to={`/infra-automation/runs/${encodeURIComponent(params.runId ?? "")}${scopeQuery(context.scope)}`}>View run timeline</Link></div>
      <ApprovalReviewPanel context={context} approvalId={approvals[0]} expectedRunId={params.runId ?? ""} />
    </div>;
    return <RunContent key={key} context={context} runId={params.runId ?? ""} />;
  }}</AutomationFrame>;
}
