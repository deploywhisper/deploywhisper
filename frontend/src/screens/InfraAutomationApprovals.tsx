import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiClientError } from "../api/client";
import { getApprovals, getApprovalReview, submitApprovalDecision, getAutomationAudit, type Approval, type ApprovalReview } from "../api/infraAutomation";
import { Button, Card, SkeletonLine, SeverityBadge, VerdictChip, EvidenceTag } from "../components/ui";
import { AccountLink, AutomationFrame, automationError, scopeQuery, type AutomationContext } from "./InfraAutomationShared";

type Outcome = "approve" | "reject";
type RecordedStatus = "all" | "pending" | "expired" | "decided";
type Uncertain = { version: number; digest: string; serial: number };
const uncertain = new Map<string, Uncertain>();
let serial = 0;
export function approvalScopeKey(context: Pick<AutomationContext, "scope" | "identity">, id: string): string {
  return `${context.identity.epoch}:${context.scope.projectId}:${context.scope.workspaceId}:${id}`;
}
export function markApprovalUncertain(key: string, receipt: Pick<Approval, "version" | "binding_digest">): void {
  uncertain.set(key, { version: receipt.version, digest: receipt.binding_digest, serial: ++serial });
}
export function approvalIsUncertain(key: string): boolean { return uncertain.has(key); }
export async function recoverApprovalRead(key: string, read: () => Promise<ApprovalReview>): Promise<ApprovalReview> {
  const previous = uncertain.get(key);
  const packet = await read();
  if (previous && uncertain.get(key)?.serial === previous.serial && packet.receipt.version >= previous.version && packet.receipt.binding_digest === previous.digest) uncertain.delete(key);
  return packet;
}
export function approvalFingerprint(packet: ApprovalReview): string {
  return JSON.stringify([packet.receipt.id, packet.receipt.generation, packet.receipt.version, packet.receipt.binding_digest,
    packet.context.decision_kind, packet.context.confirmation, packet.context.effective_deadline,
    packet.receipt.binding.policy_version, packet.receipt.binding.policy_digest]);
}
export function remainingApprovalTime(packet: ApprovalReview, elapsed = 0): number | null {
  const evaluated = packet.context.evaluated_at;
  if (!evaluated) return null;
  const duration = Date.parse(packet.context.effective_deadline) - Date.parse(evaluated) - elapsed;
  return Number.isFinite(duration) ? Math.max(0, duration) : null;
}
export function validApprovalReason(value: string): boolean {
  return value.trim().length > 0 && value.length <= 256 && !/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/.test(value);
}
export function approvalMatchesRun(packet: ApprovalReview, runId?: string): boolean { return !runId || packet.receipt.run_id === runId; }
export function approvalCanRestoreFocus(target: HTMLElement | null): target is HTMLElement {
  return Boolean(target?.isConnected && !target.matches(":disabled"));
}
export function approvalReadAdvances(previous: ApprovalReview | undefined, next: ApprovalReview): boolean {
  if (!previous) return true;
  const old = previous.receipt, current = next.receipt;
  return current.id === old.id && current.binding_digest === old.binding_digest && current.generation === old.generation && current.version >= old.version &&
    !(old.status !== "pending" && current.status === "pending");
}
export function filterRecordedApprovals(rows: Approval[], status: RecordedStatus): Approval[] {
  return rows.filter((row) => status === "all" || (status === "decided" ? ["approved", "rejected"].includes(row.status) : row.status === status));
}
function utc(value: string | null): string { return value ? value.replace("T", " ").replace(/Z$/, " UTC") : "Unavailable"; }
function approvalUrl(row: Pick<Approval, "id" | "run_id" | "project_id" | "workspace_id">): string {
  return `/infra-automation/runs/${encodeURIComponent(row.run_id)}${scopeQuery({ projectId: row.project_id, workspaceId: row.workspace_id })}&approval_id=${encodeURIComponent(row.id)}`;
}
const severityLabel = { low: "LOW", medium: "MEDIUM", high: "HIGH", critical: "CRITICAL" } as const;
const verdictLabel = { go: "PROCEED", caution: "CAUTION", "no-go": "NO-GO" } as const;
const denied = (error: unknown) => error instanceof ApiClientError && [401, 403].includes(error.status);

export function InfraAutomationApprovalsScreen() {
  return <AutomationFrame>{(context) => <ApprovalInbox key={approvalScopeKey(context, "inbox")} context={context} />}</AutomationFrame>;
}
export function ApprovalInbox({ context }: { context: AutomationContext }) {
  const [cursor, setCursor] = useState<string>();
  const [status, setStatus] = useState<RecordedStatus>("all");
  const [older, setOlder] = useState<Approval[]>([]);
  const query = useQuery({ queryKey: ["automation", context.identity.epoch, context.scope.projectId, context.scope.workspaceId, "approvals", cursor], queryFn: ({ signal }) => getApprovals(context.scope, cursor, signal), retry: false, gcTime: 0, refetchOnWindowFocus: true });
  const rows = query.isError ? [] : [...older, ...(query.data?.items ?? [])];
  const shown = filterRecordedApprovals(rows, status);
  return <Card eyebrow="Human decisions" title="Approval inbox" right={<Button disabled={query.isFetching} onClick={() => { setOlder([]); setCursor(undefined); void query.refetch(); }}>Refresh inbox</Button>}>
    <p>Open a packet to check current evidence and reviewer eligibility before making a decision.</p>
    <label className="dw-field dw-approval-filter" htmlFor="approval-status"><span>Recorded status</span><select id="approval-status" value={status} onChange={(event) => setStatus(event.target.value as RecordedStatus)}><option value="all">All</option><option value="pending">Pending</option><option value="expired">Expired</option><option value="decided">Decided</option></select></label>
    <p className="dw-muted">Filters apply to loaded records. Recorded status does not establish current eligibility.</p>
    {query.isLoading && <div role="status"><SkeletonLine />Loading approval requests…</div>}
    {query.isError && <div role="alert" className="dw-automation-notice">{automationError(query.error)} {denied(query.error) && <AccountLink />}</div>}
    {query.isSuccess && <div className="dw-automation-table-wrap"><table><caption>{shown.length} matching requests from {rows.length} loaded records</caption><thead><tr><th scope="col">Request</th><th scope="col">Environment / target</th><th scope="col">Recorded status</th><th scope="col">Receipt deadline</th><th scope="col">Review</th></tr></thead><tbody>{shown.map((row) => <tr key={row.id}><td><code>{row.id}</code><br />Generation {row.generation}</td><td>{row.binding.environment}<br /><strong>{row.binding.canonical_target}</strong></td><td><span className="dw-automation-status">{row.status}</span></td><td><time dateTime={row.deadline_at}>{utc(row.deadline_at)}</time></td><td><Link aria-label={`Review packet ${row.id}`} to={approvalUrl(row)}>Review packet</Link></td></tr>)}</tbody></table>{shown.length === 0 && <p>No matching requests in the loaded records.</p>}</div>}
    {query.data?.cursor.next_cursor && !query.isError && <Button disabled={query.isFetching} onClick={() => { setOlder(rows); setCursor(query.data!.cursor.next_cursor!); }}>Load older approvals</Button>}
  </Card>;
}

export function ApprovalReviewPanel({ context, approvalId, expectedRunId }: { context: AutomationContext; approvalId: string; expectedRunId?: string }) {
  const key = approvalScopeKey(context, approvalId);
  return <ApprovalReviewContent key={`${key}:run:${expectedRunId ?? "none"}`} context={context} approvalId={approvalId} expectedRunId={expectedRunId} guardKey={key} />;
}
function ApprovalReviewContent({ context, approvalId, expectedRunId, guardKey }: { context: AutomationContext; approvalId: string; expectedRunId?: string; guardKey: string }) {
  const client = useQueryClient();
  const queryKey = ["automation", context.identity.epoch, context.scope.projectId, context.scope.workspaceId, "approval", approvalId];
  const active = useRef(guardKey); active.current = guardKey;
  const heading = useRef<HTMLHeadingElement>(null), receiptHeading = useRef<HTMLHeadingElement>(null), errorSummary = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null), reasonInput = useRef<HTMLInputElement>(null), trigger = useRef<HTMLElement | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [reason, setReason] = useState(""), [phrase, setPhrase] = useState("");
  const [message, setMessage] = useState(""), [busy, setBusy] = useState(false), [expired, setExpired] = useState(false);
  const [pendingProof, setPendingProof] = useState(() => approvalIsUncertain(guardKey));
  const prepared = useRef<string | null>(null), entered = useRef(false), focusedReceipt = useRef<string | null>(null);
  const query = useQuery({ queryKey, queryFn: async ({ signal }) => {
    const value = await recoverApprovalRead(guardKey, () => getApprovalReview(approvalId, context.scope, signal));
    if (!approvalReadAdvances(client.getQueryData<ApprovalReview>(queryKey), value)) throw new ApiClientError("The approval read regressed. Reload current state.", 422);
    return value;
  }, retry: false, gcTime: 0, refetchOnWindowFocus: true, refetchInterval: (value) => value.state.data?.receipt.status === "pending" ? 5000 : false });
  const packet = query.data;
  const wrongRun = Boolean(packet && !approvalMatchesRun(packet, expectedRunId));
  const protectedDenied = denied(query.error);
  const fresh = context.fresh && query.isSuccess && !query.isFetching && !query.isError && !wrongRun && !expired;
  const mutable = Boolean(packet && fresh && packet.context.can_submit && context.identity.csrfToken && !pendingProof && !busy);
  const knownFingerprint = packet ? approvalFingerprint(packet) : null;
  useEffect(() => () => { active.current = "disposed"; }, []);
  useEffect(() => { if (query.isSuccess && !query.isFetching) setPendingProof(approvalIsUncertain(guardKey)); }, [query.dataUpdatedAt, query.isFetching, query.isSuccess, guardKey]);
  useEffect(() => {
    if (!packet || !query.isSuccess || query.isFetching || query.isError) return;
    const fingerprint = approvalFingerprint(packet);
    const remaining = remainingApprovalTime(packet);
    setExpired(remaining === 0 && packet.receipt.status === "pending");
    if (prepared.current && prepared.current !== fingerprint) { setPhrase(""); setMessage("The decision packet changed. Review the current packet before confirming again."); prepared.current = null; }
    if (remaining === null || packet.receipt.status !== "pending" || packet.context.status !== "eligible") return;
    const timer = window.setTimeout(() => { setExpired(true); setPhrase(""); void query.refetch(); }, Math.min(remaining + 30, 2_147_483_647));
    return () => clearTimeout(timer);
  }, [query.dataUpdatedAt, query.isFetching, query.isError]);
  useEffect(() => {
    if (!packet || wrongRun || query.isError || query.isFetching) return;
    if (packet.receipt.status !== "pending") {
      const stamp = `${packet.receipt.id}:${packet.receipt.version}`;
      if (focusedReceipt.current !== stamp) {
        dialog.current?.close(); setOutcome(null); setPhrase(""); setReason(""); prepared.current = null;
        focusedReceipt.current = stamp; receiptHeading.current?.focus();
      }
    } else if (!entered.current) {
      heading.current?.focus();
    }
    entered.current = true;
  }, [query.dataUpdatedAt, packet?.receipt.status, wrongRun, query.isError, query.isFetching]);
  useEffect(() => {
    if (!outcome) return;
    const element = dialog.current;
    if (element && !element.open) element.showModal();
    if (packet?.receipt.status === "pending") reasonInput.current?.focus();
    const wrapTab = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || !element?.open) return;
      const focusable = Array.from(element.querySelectorAll<HTMLElement>("a[href], button, input, select, textarea, [tabindex]")).filter((node) => node.tabIndex >= 0 && !node.matches(":disabled") && node.getClientRects().length > 0);
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (!first || !last) { event.preventDefault(); element.focus(); return; }
      const current = document.activeElement;
      if (!focusable.includes(current as HTMLElement) || (event.shiftKey ? current === first : current === last)) {
        event.preventDefault(); (event.shiftKey ? last : first).focus();
      }
    };
    document.addEventListener("keydown", wrapTab, true);
    return () => document.removeEventListener("keydown", wrapTab, true);
  }, [outcome]);
  useEffect(() => {
    if (!protectedDenied) return;
    setOutcome(null); setReason(""); setPhrase("");
    if (query.error instanceof ApiClientError && query.error.status === 401) context.identity.expire();
  }, [protectedDenied]);
  function closeDialog() {
    dialog.current?.close(); setOutcome(null); setPhrase(""); prepared.current = null;
    const target = trigger.current;
    if (approvalCanRestoreFocus(target)) target.focus();
    else if (packet?.receipt.status !== "pending") receiptHeading.current?.focus();
    else heading.current?.focus();
  }
  function fail(text: string) { setMessage(text); queueMicrotask(() => errorSummary.current?.focus()); }
  async function reload(): Promise<ApprovalReview | null> {
    const expected = active.current;
    try {
      const result = await query.refetch({ throwOnError: true });
      if (active.current !== expected || expected === "disposed") return null;
      if (!result.data) throw new ApiClientError("Current approval is unavailable.", 503);
      setPendingProof(approvalIsUncertain(guardKey));
      return result.data;
    } catch (error) { if (active.current === expected) fail(automationError(error)); return null; }
  }
  function open(value: Outcome, target: HTMLElement) {
    if (!mutable || !packet) return;
    prepared.current = approvalFingerprint(packet); trigger.current = target; setOutcome(value); setPhrase(""); setMessage("");
  }
  async function submit() {
    if (!packet || !outcome || !mutable || !validApprovalReason(reason)) return;
    const selected = outcome, expected = active.current, fingerprint = prepared.current;
    setBusy(true); setMessage("");
    try {
      await context.ensureFresh();
      if (active.current !== expected || expected === "disposed") return;
      const verified = await query.refetch({ throwOnError: true });
      if (active.current !== expected) return;
      const current = verified.data;
      if (prepared.current !== fingerprint) return;
      if (!current || !approvalMatchesRun(current, expectedRunId) || !current.context.can_submit || prepared.current !== fingerprint || approvalFingerprint(current) !== fingerprint || remainingApprovalTime(current) === 0) {
        prepared.current = null; setPhrase(""); fail("Current evidence or authority changed. Review the refreshed packet before submitting."); return;
      }
      const confirmation = current.context.confirmation;
      const required = selected === "approve" ? confirmation.approve_phrase : confirmation.reject_phrase;
      if (confirmation.required && phrase !== required) { fail("Type the exact confirmation phrase shown for this decision."); return; }
      markApprovalUncertain(guardKey, current.receipt); setPendingProof(true);
      await submitApprovalDecision(approvalId, { expected_version: current.receipt.version, binding_digest: current.receipt.binding_digest, outcome: selected, reason: reason.trim(), confirmation: confirmation.required ? phrase : null }, context.identity.csrfToken!);
      if (active.current !== expected) return;
      const recovered = await reload();
      if (recovered) { setMessage(""); setReason(""); }
    } catch (error) {
      if (active.current !== expected) return;
      if (denied(error)) {
        dialog.current?.close(); setOutcome(null); setReason(""); setPhrase("");
        if (error instanceof ApiClientError && error.status === 401) context.identity.expire();
      }
      fail(error instanceof ApiClientError && error.status === 409 ? "The decision changed concurrently. Reloading its durable receipt before another submission." : automationError(error));
      // Reads only: a response loss never resends the mutation.
      await reload();
    } finally { if (active.current === expected) setBusy(false); }
  }
  async function downloadAudit() {
    if (!packet?.can_export_audit || !fresh || busy) return;
    setBusy(true);
    try {
      await context.refresh();
      if (active.current !== guardKey) return;
      const pages = [];
      let cursor: string | undefined;
      const seen = new Set<string>();
      do {
        const page = await getAutomationAudit(context.scope, cursor);
        if (active.current !== guardKey) return;
        pages.push(page);
        cursor = page.cursor.next_cursor ?? undefined;
        if (cursor && seen.has(cursor)) throw new ApiClientError("Audit pagination could not be verified.", 422);
        if (cursor) seen.add(cursor);
      } while (cursor && pages.length < 100);
      const blob = new Blob([JSON.stringify({ project_id: context.scope.projectId, workspace_id: context.scope.workspaceId, approval_id: approvalId, pages, complete: !cursor }, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob), anchor = document.createElement("a"); anchor.href = url; anchor.download = `approval-audit-${approvalId}.json`; anchor.click(); URL.revokeObjectURL(url);
      setMessage(cursor ? "Downloaded 100 scoped audit pages. Older events remain available through the scoped export API." : "Downloaded the scoped audit JSON.");
    } catch (error) { fail(automationError(error)); } finally { if (active.current === guardKey) setBusy(false); }
  }
  if (protectedDenied) return <div role="alert" className="dw-automation-notice"><h2>Approval access unavailable</h2><p>{automationError(query.error)}</p><AccountLink /></div>;
  if (wrongRun) return <div role="alert" className="dw-automation-notice"><h2>Approval does not match this run</h2><p>Open the request from the scoped approval inbox.</p><Link to={`/infra-automation/approvals${scopeQuery(context.scope)}`}>Open approval inbox</Link></div>;
  if (!packet) return query.isError ? <div role="alert" className="dw-automation-notice">{automationError(query.error)} <Button onClick={() => { void reload(); }}>Reload approval</Button></div> : <div role="status"><SkeletonLine />Loading the immutable approval packet…</div>;
  const acknowledge = packet.context.decision_kind === "acknowledgement";
  const action = outcome === "reject" ? "rejection" : acknowledge ? "acknowledgement" : "approval";
  const expectedPhrase = outcome === "reject" ? packet.context.confirmation.reject_phrase : packet.context.confirmation.approve_phrase;
  const formValid = validApprovalReason(reason) && (!packet.context.confirmation.required || phrase === expectedPhrase);
  return <div className="dw-approval-review">
    <header className="dw-approval-heading"><div><p className="dw-automation-eyebrow">Exact evidence and action</p><h2 ref={heading} tabIndex={-1}>Review approval</h2><p><code>{packet.receipt.id}</code> · Generation {packet.receipt.generation} · {packet.receipt.status}</p></div><Button disabled={busy || query.isFetching} onClick={() => { void reload(); }}>Reload approval</Button></header>
    {message && !outcome && <div tabIndex={-1} ref={errorSummary} className="dw-automation-error-summary" role="alert">{message}</div>}
    {query.isError && <p role="alert" className="dw-automation-notice">Refresh failed. Displayed evidence is read-only until current access is verified. {automationError(query.error)}</p>}
    {pendingProof && <p role="alert" className="dw-automation-notice">The previous submission is unconfirmed. Reload its durable receipt before another submission. No automatic replay occurs.</p>}
    <Card eyebrow={packet.action.authorization_kind === "exact_plan" ? "Exact-plan handoff" : "Advisory request"} title={`${packet.action.environment} · ${packet.action.canonical_target}`} right={<div className="dw-approval-signals">{packet.report.severity === "low" ? <EvidenceTag>Low severity</EvidenceTag> : <SeverityBadge level={severityLabel[packet.report.severity]} />}{packet.report.recommendation === "go" ? <EvidenceTag>PROCEED</EvidenceTag> : packet.report.recommendation === "caution" ? <span className="dw-automation-status">CAUTION</span> : <VerdictChip size="sm" verdict={verdictLabel[packet.report.recommendation]} />}</div>}>
      <dl className="dw-automation-facts"><dt>Requested action</dt><dd>{packet.action.authorization_kind === "exact_plan" ? "Handoff of the exact retained plan to the registered pipeline" : "Advisory review request; exact saved-plan execution is not authorized"}</dd><dt>Receiver</dt><dd>{packet.action.receiver_id}</dd><dt>Pipeline</dt><dd>{packet.action.pipeline_repository_id} / {packet.action.pipeline_workflow_id}</dd><dt>Pipeline revision</dt><dd><code>{packet.action.pipeline_workflow_revision}</code></dd><dt>Source repository</dt><dd>{packet.action.source_repository_id ?? "Unavailable for uploaded evidence"}</dd><dt>IaC commit</dt><dd><code>{packet.action.source_commit_sha ?? "Unavailable"}</code></dd><dt>Requester</dt><dd>{packet.receipt.requested_by}</dd><dt>Effective deadline</dt><dd><time dateTime={packet.context.effective_deadline}>{utc(packet.context.effective_deadline)}</time></dd><dt>Evaluated by server</dt><dd>{utc(packet.context.evaluated_at)}</dd><dt>Workflow policy</dt><dd>Version {packet.receipt.binding.policy_version} · {packet.context.policy_status ?? "Current evaluation unavailable"} · {packet.context.policy_passed === true ? "Passed" : "Current eligibility not established"}</dd></dl>
      <p><Link to={`${packet.report.report_url}?private=1`}>Open permanent report {packet.report.report_id}</Link> · Canonical report remains advisory.</p>
      {packet.report.recommendation === "no-go" && <p className="dw-automation-notice">The canonical report recommends no-go. Review its findings and explain your decision. Workflow policy is evaluated separately.</p>}
      {packet.screening_limited && <p className="dw-automation-notice">Some summary details were screened or limited. Review the retained report and full fingerprints.</p>}
    </Card>
    <div className="dw-approval-evidence-grid"><Card title="Confidence and context"><p className="dw-approval-value">{Math.round(packet.report.confidence.score * 100)}% <span>{packet.report.confidence.level} confidence</span></p><p>Context completeness {Math.round(packet.report.confidence.context_score * 100)}%</p><p>{packet.report.confidence.insufficient_context ? "Insufficient mandatory context" : packet.report.confidence.partial_context ? "Partial context" : "Retained context complete"}</p>{packet.report.confidence.uncertainty && <p>{packet.report.confidence.uncertainty}</p>}<ul>{packet.report.confidence.context_todos.map((todo, index) => <li key={index}>{todo}</li>)}</ul></Card><Card title="Blast radius and rollback"><p>{packet.report.blast_radius.direct_count} direct · {packet.report.blast_radius.transitive_count} transitive · {packet.report.blast_radius.unmatched_resource_count} unmatched resources</p><p>{packet.report.blast_radius.affected_services.join(", ") || "No affected service labels recorded."}</p>{packet.report.blast_radius.warning && <p>{packet.report.blast_radius.warning}</p>}<h3>Rollback: {packet.report.rollback.complexity}</h3><p>{packet.report.rollback.explanation}</p>{packet.report.rollback.warning && <p>{packet.report.rollback.warning}</p>}<ol>{packet.report.rollback.steps.map((step) => <li key={step.order}>{step.title} · {step.estimated_minutes} minutes{step.critical ? " · critical step" : ""}</li>)}</ol></Card></div>
    <details className="dw-approval-fingerprints"><summary>Full evidence fingerprints and deadline components</summary><dl className="dw-automation-facts"><dt>Binding</dt><dd><code>{packet.receipt.binding_digest}</code></dd><dt>Report bytes ({packet.report.schema_version})</dt><dd><code>{packet.report.report_bytes_digest}</code></dd><dt>Workflow revision</dt><dd><code>{packet.receipt.binding.workflow_revision_digest}</code></dd><dt>Inputs</dt><dd><code>{packet.receipt.binding.input_digest}</code></dd><dt>Policy</dt><dd><code>{packet.receipt.binding.policy_digest}</code></dd><dt>Units</dt><dd><code>{packet.action.unit_waves_digest}</code></dd><dt>Payload</dt><dd><code>{packet.action.payload_digest}</code></dd><dt>Artifacts</dt><dd>{packet.receipt.binding.screened_artifact_digests.map((value) => <div key={value}><code>{value}</code></div>)}</dd><dt>Saved-plan custody</dt><dd>{packet.receipt.binding.provenance.custody?.handle ?? "Unavailable"}</dd><dt>Raw-local identity</dt><dd><code>{packet.receipt.binding.provenance.custody?.raw_local_digest ?? "Unavailable"}</code></dd>{Object.entries(packet.context.deadlines).map(([name, deadline]) => <div className="dw-approval-fact-pair" key={name}><dt>{name} deadline</dt><dd>{utc(deadline)}</dd></div>)}</dl></details>
    {packet.receipt.status === "pending" ? <section className="dw-approval-decision" aria-labelledby="decision-actions"><h2 id="decision-actions">{acknowledge ? "Authenticated acknowledgement" : "Independent human decision"}</h2>{acknowledge && <p>This records your authenticated acknowledgement. It does not record independent review.</p>}{(!packet.context.can_submit || expired) && <div className="dw-automation-notice" role="status"><strong>Decision unavailable</strong><ul>{packet.context.limitations.map((value, index) => <li key={index}>{value}</li>)}</ul><ul>{packet.context.context_todos.map((value, index) => <li key={index}>{value}</li>)}</ul>{expired && <p>The effective deadline has elapsed. Reload current evidence before continuing.</p>}</div>}{!context.identity.csrfToken && <p><AccountLink /> before submitting a decision.</p>}<div className="dw-automation-actions"><Button variant="primary-gradient" disabled={!mutable} onClick={(event) => open("approve", event.currentTarget)}>{acknowledge ? "Acknowledge handoff" : "Approve handoff"}</Button><Button disabled={!mutable} onClick={(event) => open("reject", event.currentTarget)}>Reject handoff</Button></div></section> : <section className="dw-approval-receipt" aria-labelledby="approval-receipt"><h2 id="approval-receipt" ref={receiptHeading} tabIndex={-1}>Decision receipt</h2><p><strong>{packet.receipt.status}</strong> · Generation {packet.receipt.generation} · Version {packet.receipt.version}</p><p>{packet.receipt.decision_kind === "acknowledgement" ? "Authenticated acknowledgement recorded; independent review was not recorded." : packet.receipt.decision_kind === "independent-approval" ? "Independent approval model recorded." : "The request closed without an approving human decision."}</p>{packet.attribution ? <dl className="dw-automation-facts"><dt>Verified principal / type</dt><dd>{packet.attribution.principal_id} · {packet.attribution.principal_type}</dd><dt>Role at decision</dt><dd>{packet.attribution.role}</dd><dt>Scope</dt><dd>Project {packet.attribution.project_id} · workspace {packet.attribution.workspace_id}</dd><dt>Reason</dt><dd>{packet.attribution.reason}</dd><dt>Recorded at</dt><dd>{utc(packet.attribution.occurred_at)}</dd><dt>Before digest</dt><dd><code>{packet.attribution.before_digest ?? "No prior state digest recorded"}</code></dd><dt>After digest</dt><dd><code>{packet.attribution.after_digest}</code></dd><dt>Audit scheme</dt><dd>{packet.attribution.state_digest_version === 1 ? "Decision state v1" : "Legacy binding attribution; no state digest invented"}</dd></dl> : <p>Retained attribution is unavailable.</p>}<p>Application audit is append-only. Database and host administrators remain trusted.</p></section>}
    {packet.can_export_audit && <Button disabled={!fresh || busy} onClick={() => { void downloadAudit(); }}>Download scoped audit JSON</Button>}
    {outcome && <dialog ref={dialog} className="dw-approval-dialog" aria-labelledby="confirmation-heading" onCancel={(event) => { event.preventDefault(); closeDialog(); }} onClose={() => setOutcome(null)}><form onSubmit={(event) => { event.preventDefault(); void submit(); }}><h2 id="confirmation-heading">Confirm {action}</h2><p>Target <strong>{packet.action.canonical_target}</strong> · {packet.action.environment}. This records the exact retained evidence and action.</p>{acknowledge && outcome === "approve" && <p>This records your authenticated acknowledgement. It does not record independent review.</p>}<label className="dw-field" htmlFor="approval-reason"><span>Reason</span><input ref={reasonInput} id="approval-reason" readOnly={busy} value={reason} maxLength={256} required onChange={(event) => setReason(event.target.value)} autoComplete="off" /></label>{packet.context.confirmation.required && <label className="dw-field" htmlFor="approval-confirmation"><span id="approval-confirmation-label">Type the confirmation phrase</span><code id="approval-required-phrase">{expectedPhrase}</code><input aria-labelledby="approval-confirmation-label" aria-describedby="approval-required-phrase" id="approval-confirmation" value={phrase} maxLength={256} required autoComplete="off" spellCheck={false} onChange={(event) => setPhrase(event.target.value)} /></label>}{message && <div tabIndex={-1} ref={errorSummary} role="alert" className="dw-automation-error-summary">{message}</div>}{(expired || !packet.context.can_submit) && <div className="dw-automation-notice" role="status">{expired && <p>The effective deadline has elapsed. Your reason is retained.</p>}{packet.context.limitations.map((value, index) => <p key={`limitation-${index}`}>{value}</p>)}{packet.context.context_todos.map((value, index) => <p key={`todo-${index}`}>{value}</p>)}</div>}{busy && <p role="status">A request already sent may still complete. Reload its receipt before retrying after closing this dialog.</p>}{(!mutable || !prepared.current || knownFingerprint !== prepared.current) && <p role="status">Current evidence and authority must be reviewed again before submission.</p>}<div className="dw-automation-actions"><Button onClick={closeDialog}>{busy ? "Close confirmation" : "Cancel"}</Button><Button type="submit" variant="primary-gradient" disabled={!mutable || !formValid || !prepared.current || knownFingerprint !== prepared.current}>Confirm {action}</Button></div></form></dialog>}
  </div>;
}
