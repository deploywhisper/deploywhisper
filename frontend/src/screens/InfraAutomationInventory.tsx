import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "../components/ui";
import { getWorkflows, getRevisions } from "../api/infraAutomation";
import { ApiClientError } from "../api/client";
import { validCollectionReason, isConfirmedCollectionRejection } from "../api/infraAutomationCollection";
import { getUnitInventories, getUnitRevisionHistory, getUnitRevision, validateUnitInventory, saveUnitInventory, startUnitRun, getRunUnits, type DeclaredUnit, type UnitMap, type UnitPlan, type UnitRevision, type UnitError, type UnitRunView, type UnitRunRequest, type UnitRevisionSummary } from "../api/infraAutomationUnits";
import { AutomationFrame, automationError, scopeQuery, type AutomationContext } from "./InfraAutomationShared";
import { CollectionStartRequests, parseRunInputs, validateArtifactFiles } from "./InfraAutomation";

export function inventoryAccessKey(context: AutomationContext) { return `${context.identity.epoch}:${context.identity.principal?.session_id}:${context.scope.projectId}:${context.scope.workspaceId}:${context.capabilities.membership_version}`; }
export type UnitDraft = { id: string; sourceKind: "uploaded" | "declared_repository"; repository: string; commit: string; path: string; environment: string; target: string; prerequisites: string; affected: boolean };
export function emptyUnit(): UnitDraft { return { id: "", sourceKind: "uploaded", repository: "", commit: "", path: ".", environment: "", target: "", prerequisites: "", affected: true }; }
export function inventoryFromDraft(rows: UnitDraft[]): UnitMap { return { version: 1, units: rows.map((u) => ({ id: u.id, source: u.sourceKind === "uploaded" ? { kind: "uploaded", repository_source: "unavailable", path: u.path } : { kind: "declared_repository", repository_id: u.repository, commit_sha: u.commit, path: u.path }, environment: u.environment, target: u.target, prerequisites: u.prerequisites.trim() ? u.prerequisites.split(",").map((s) => s.trim()) : [] })), affected: rows.filter((u) => u.affected).map((u) => u.id) }; }
function draftFromInventory(map: UnitMap): UnitDraft[] { return map.units.map((u) => ({ id: u.id, sourceKind: u.source.kind, repository: u.source.kind === "declared_repository" ? u.source.repository_id : "", commit: u.source.kind === "declared_repository" ? u.source.commit_sha : "", path: u.source.path, environment: u.environment, target: u.target, prerequisites: u.prerequisites.join(", "), affected: map.affected.includes(u.id) })); }
export function UnitWaves({ plan }: { plan: UnitPlan }) { return <section className="dw-automation-section" aria-label="Collection and review waves"><h3>Collection/review order</h3><p>These waves order evidence collection and review. They do not establish deployment order or prove upstream provisioning is complete.</p><div className="dw-automation-table-wrap"><table className="dw-automation-table"><caption>Declared preflight waves</caption><thead><tr><th scope="col">Wave</th><th scope="col">Units</th></tr></thead><tbody>{plan.waves.map((wave, index) => <tr key={index}><th scope="row">{index + 1}</th><td>{wave.join(", ")}</td></tr>)}</tbody></table></div><p>Map digest: <code>{plan.map_digest}</code></p><p>Wave digest: <code>{plan.waves_digest}</code></p></section>; }
type StartTicket = ReturnType<CollectionStartRequests["begin"]>;
export class UnitStartRequests extends CollectionStartRequests {
  private requests = new Map<string, { ticket: StartTicket; payload: UnitRunRequest }>();
  remember(key: string, payload: UnitRunRequest): StartTicket {
    if (this.get(key)?.kind === "pending") throw new Error("A run request is already unresolved.");
    const retained = structuredClone(payload);
    const ticket = this.begin(key, retained.run.idempotency_key);
    this.requests.set(key, { ticket, payload: retained });
    return ticket;
  }
  pendingRequest(key: string): UnitRunRequest | undefined { const value = this.requests.get(key); return value && this.get(key) === value.ticket && value.ticket.kind === "pending" ? structuredClone(value.payload) : undefined; }
  override succeed(key: string, ticket: StartTicket, runId: string) { if (this.get(key) === ticket) this.requests.delete(key); super.succeed(key, ticket, runId); }
  override reject(key: string, ticket: StartTicket) { if (this.get(key) === ticket) this.requests.delete(key); super.reject(key, ticket); }
}
const starts = new UnitStartRequests();
type SaveIntent = { projectId: number; workspaceId: number; mapDigest: string; creatorId: string; inventoryId: string | null; expectedVersion: number; knownInventoryIds: string[] };
type SaveOutcome = { kind: "pending"; operation: symbol; intent: SaveIntent } | { kind: "confirmed"; operation: symbol; inventoryId: string; revisionId: string };
export class InventorySaveRequests {
  private values = new Map<string, SaveOutcome>();
  private listeners = new Set<() => void>();
  get = (key: string) => this.values.get(key);
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private changed() { this.listeners.forEach((listener) => listener()); }
  begin(key: string, intent: SaveIntent): SaveOutcome { if (this.get(key)?.kind === "pending") throw new Error("A save is already unresolved."); const value: SaveOutcome = { kind: "pending", operation: Symbol("inventory-save"), intent: { ...intent, knownInventoryIds: [...intent.knownInventoryIds] } }; this.values.set(key, value); this.changed(); return value; }
  succeed(key: string, ticket: SaveOutcome, revision: UnitRevision) { if (this.get(key) !== ticket) return; this.values.set(key, { kind: "confirmed", operation: ticket.operation, inventoryId: revision.inventory_id, revisionId: revision.revision_id }); this.changed(); }
  reject(key: string, ticket: SaveOutcome) { if (this.get(key) !== ticket) return; this.values.delete(key); this.changed(); }
  canRecover(key: string, revision: UnitRevision): boolean {
    const value = this.get(key); if (value?.kind !== "pending") return false;
    const intent = value.intent;
    return revision.project_id === intent.projectId && revision.workspace_id === intent.workspaceId && revision.created_by === intent.creatorId && revision.map_digest === intent.mapDigest && revision.version === intent.expectedVersion && (intent.inventoryId === null ? !intent.knownInventoryIds.includes(revision.inventory_id) : revision.inventory_id === intent.inventoryId);
  }
  recover(key: string, revision: UnitRevision): boolean { if (!this.canRecover(key, revision)) return false; this.values.delete(key); this.changed(); return true; }
  clearConfirmed(key: string, inventoryId: string, revisionId: string) { const value = this.get(key); if (value?.kind !== "confirmed" || value.inventoryId !== inventoryId || value.revisionId !== revisionId) return; this.values.delete(key); this.changed(); }
}
const saves = new InventorySaveRequests();
export const unitEvidenceReadOptions = { retry: false, gcTime: 0, refetchInterval: 5000, refetchOnWindowFocus: "always" as const };
function can(context: AutomationContext, permission: "automation.draft" | "automation.request") { return context.fresh && !!context.identity.csrfToken && context.capabilities.capabilities.includes(permission); }

type UnitField = "id" | "affected" | "sourceKind" | "repository" | "commit" | "path" | "environment" | "target" | "prerequisites";
function errorControl(error: UnitError, rows: UnitDraft[]): { row: number; field: UnitField } | null {
  if (error.path[0] === "affected") { const affected = rows.flatMap((row, i) => row.affected ? [i] : []); return { row: typeof error.path[1] === "number" ? affected[error.path[1]] ?? 0 : 0, field: "affected" }; }
  if (error.path[0] !== "units" || typeof error.path[1] !== "number" || !rows[error.path[1]]) return null;
  const fields: [string, UnitField][] = [["prerequisites", "prerequisites"], ["repository_id", "repository"], ["commit_sha", "commit"], ["path", "path"], ["environment", "environment"], ["target", "target"], ["id", "id"], ["source", "sourceKind"]];
  const field = fields.find(([name]) => error.path.slice(2).includes(name))?.[1];
  return field ? { row: error.path[1], field } : null;
}
export function unitFieldErrors(errors: UnitError[], rows: UnitDraft[], row: number, field: UnitField) { return errors.filter((error) => { const target = errorControl(error, rows); return target?.row === row && target.field === field; }); }
function controlId(row: number, field: UnitField) { return `unit-${row}-${field}`; }
export function UnitErrorSummary({ errors, rows }: { errors: UnitError[]; rows: UnitDraft[] }) { return <ul>{errors.map((error, i) => { const target = errorControl(error, rows), label = `${error.path.join(".") || "Inventory"}: ${error.message}`; return <li key={i}>{target ? <a href={`#${controlId(target.row, target.field)}`} onClick={(event) => { event.preventDefault(); document.getElementById(controlId(target.row, target.field))?.focus(); }}>{label}</a> : label}</li>; })}</ul>; }
function UnitRowErrors({ errors, rows, row }: { errors: UnitError[]; rows: UnitDraft[]; row: number }) { const fields: UnitField[] = ["id", "affected", "sourceKind", "repository", "commit", "path", "environment", "target", "prerequisites"]; return <>{fields.map((field) => { const located = unitFieldErrors(errors, rows, row, field); return located.length ? <ul key={field} id={`${controlId(row, field)}-errors`}>{located.map((error, i) => <li key={i}>{error.message}</li>)}</ul> : null; })}</>; }

export function InventoryEditor({ context }: { context: AutomationContext }) {
  const key = inventoryAccessKey(context), mounted = useRef(true), messageRef = useRef<HTMLDivElement>(null);
  const [rows, setRows] = useState<UnitDraft[]>([emptyUnit()]), [plan, setPlan] = useState<UnitPlan | null>(null), [errors, setErrors] = useState<UnitError[]>([]), [message, setMessage] = useState("");
  const [current, setCurrent] = useState<UnitRevision>(), [saved, setSaved] = useState<UnitRevision>(), [confirmed, setConfirmed] = useState(false), [reason, setReason] = useState(""), [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(false);
  const [history, setHistory] = useState<{ inventoryId: string; items: UnitRevisionSummary[] }>();
  const saveOutcome = useSyncExternalStore(saves.subscribe, () => saves.get(key), () => saves.get(key));
  const uncertain = saveOutcome?.kind === "pending";
  const inventories = useQuery({ queryKey: ["automation", "units", key], queryFn: ({ signal }) => getUnitInventories(context.scope, signal), retry: false, gcTime: 0 });
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (message || errors.length) messageRef.current?.focus(); }, [message, errors]);
  useEffect(() => { if (!context.fresh) setConfirmed(false); }, [context.fresh]);
  function clear() { setPlan(null); setErrors([]); setConfirmed(false); setSaved(undefined); setMessage(""); }
  function edit(index: number, patch: Partial<UnitDraft>) { clear(); setRows((values) => values.map((row, i) => i === index ? { ...row, ...patch } : row)); }
  function failed(error: unknown) { if (!mounted.current) return; if (error instanceof ApiClientError && [401, 403].includes(error.status)) { setDenied(true); setRows([emptyUnit()]); setCurrent(undefined); setSaved(undefined); setPlan(null); setHistory(undefined); } setConfirmed(false); setMessage(automationError(error)); }
  async function validate() { if (busy || !can(context, "automation.draft")) return; setBusy(true); clear(); try { await context.ensureFresh(); if (!mounted.current) return; const result = await validateUnitInventory(inventoryFromDraft(rows), context.scope, context.identity.csrfToken!); if (!mounted.current) return; setPlan(result.plan); setErrors(result.errors); setMessage(result.valid ? "Inventory validated. Review the exact scope and collection/review waves before saving." : "Correct the located inventory errors and validate again."); } catch (error) { failed(error); } finally { if (mounted.current) setBusy(false); } }
  async function load(inventory: string, revision: string) { if (busy) return; setBusy(true); try { const result = await getUnitRevision(inventory, revision, context.scope); if (!mounted.current) return; setRows(draftFromInventory(result.plan.inventory)); setCurrent(result); setSaved(result); setPlan(result.plan); setErrors([]); setConfirmed(false); setReason(""); setMessage("Saved revision loaded. Edits require validation and a new revision."); saves.clearConfirmed(key, result.inventory_id, result.revision_id); } catch (error) { failed(error); } finally { if (mounted.current) setBusy(false); } }
  async function loadHistory(inventoryId: string) { if (busy) return; setBusy(true); try { const result = await getUnitRevisionHistory(inventoryId, context.scope); if (mounted.current) setHistory({ inventoryId, items: result.items }); } catch (error) { failed(error); } finally { if (mounted.current) setBusy(false); } }
  function fieldAttributes(row: number, field: UnitField) { const invalid = unitFieldErrors(errors, rows, row, field).length > 0, id = controlId(row, field); return { id, "aria-invalid": invalid || undefined, "aria-describedby": invalid ? `${id}-errors` : undefined }; }
  async function save() {
    if (!plan || !confirmed || busy || uncertain || !can(context, "automation.draft") || !validCollectionReason(reason)) return;
    setBusy(true); setMessage(""); let ticket: SaveOutcome | undefined;
    try { await context.ensureFresh(); const baseline = await inventories.refetch({ throwOnError: true }); if (!mounted.current) return;
      const creatorId = context.identity.principal?.principal_id;
      if (!creatorId || context.scope.workspaceId === null || !baseline.data) throw new ApiClientError("Current save authority unavailable.", 403);
      const intent: SaveIntent = { projectId: context.scope.projectId, workspaceId: context.scope.workspaceId, mapDigest: plan.map_digest, creatorId, inventoryId: current?.inventory_id ?? null, expectedVersion: (current?.version ?? 0) + 1, knownInventoryIds: baseline.data.items.map((item) => item.inventory_id) };
      const result = await saveUnitInventory(plan.inventory, context.scope, context.identity.csrfToken!, reason, current, () => { ticket = saves.begin(key, intent); }); if (ticket) saves.succeed(key, ticket, result); if (!mounted.current) return; setCurrent(result); setSaved(result); setPlan(result.plan); setConfirmed(false); setMessage("Immutable inventory revision saved. Review its workflow bindings before requesting a run."); saves.clearConfirmed(key, result.inventory_id, result.revision_id); await inventories.refetch(); }
    catch (error) { if (ticket && isConfirmedCollectionRejection(error)) saves.reject(key, ticket); if (mounted.current) { failed(error); if (saves.get(key)?.kind === "pending") setMessage("Save outcome is unresolved. Refresh inventory history and inspect the persisted revision before another save. Nothing is resent automatically."); } }
    finally { if (mounted.current) setBusy(false); }
  }
  const readDenied = denied || inventories.error instanceof ApiClientError && [401, 403].includes(inventories.error.status);
  if (readDenied) return <div role="alert"><h2>Inventory access unavailable</h2><p>Protected inventory details have been cleared. Refresh access and reopen this scope.</p></div>;
  const editable = can(context, "automation.draft") && !busy && !uncertain;
  return <div className="dw-automation-stack dw-unit-inventory"><h2>Declared unit inventory</h2><p>Declare affected units and their exact prerequisites. No identities or dependencies are inferred.</p>
    <section className="dw-automation-section"><h3>Saved inventories</h3>{saveOutcome?.kind === "confirmed" && <p role="status">An earlier save was confirmed. <Button disabled={busy} onClick={() => void load(saveOutcome.inventoryId, saveOutcome.revisionId)}>Open confirmed saved revision</Button></p>}{inventories.isPending && <p role="status">Loading saved inventories…</p>}{inventories.error && <p role="alert">{automationError(inventories.error)}</p>}{inventories.data?.items.length === 0 && <p>No inventories saved in this workspace.</p>}
      <ul>{inventories.data?.items.map((item) => <li key={item.inventory_id}><Button disabled={busy} onClick={() => void load(item.inventory_id, item.revision_id)}>Open inventory {item.inventory_id} · revision {item.version}</Button><Button disabled={busy} onClick={() => void loadHistory(item.inventory_id)}>Read revision history for {item.inventory_id}</Button></li>)}</ul><Button disabled={busy} onClick={() => void inventories.refetch()}>Refresh inventories</Button>
      {history && <section aria-label="Saved inventory revision history"><h4>Revision history for {history.inventoryId}</h4><ul>{history.items.map((item) => <li key={item.revision_id}><Button disabled={busy} onClick={() => void load(item.inventory_id, item.revision_id)}>Open historical revision {item.version}</Button></li>)}</ul></section>}
      <Button disabled={!editable} onClick={() => { clear(); setRows([emptyUnit()]); setCurrent(undefined); setReason(""); }}>New inventory</Button>
    </section>
    <section className="dw-automation-section"><h3>{current ? `Edit revision ${current.version}` : "Declare units"}</h3><p>At most 25 units and 200 explicit prerequisite edges. Paths are human declarations; current collected evidence supports only the repository root (.). Uploaded evidence has no verified repository or commit.</p>
      <div className="dw-automation-table-wrap"><table className="dw-automation-table"><caption>Affected and prerequisite scope</caption><thead><tr><th scope="col">Unit and affected scope</th><th scope="col">Declared source</th><th scope="col">Environment and target</th><th scope="col">Prerequisites</th></tr></thead><tbody>{rows.map((row, i) => {
        const label = `Unit ${i + 1}`;
        return <tr key={i}><td><label className="dw-field">{label} ID<input value={row.id} maxLength={128} disabled={!editable} {...fieldAttributes(i, "id")} onChange={(e) => edit(i, { id: e.target.value })} /></label><label><input {...fieldAttributes(i, "affected")} type="checkbox" checked={row.affected} disabled={!editable} onChange={(e) => edit(i, { affected: e.target.checked })} /> {label} affected</label><Button disabled={!editable || rows.length === 1} onClick={() => { clear(); setRows(rows.filter((_, index) => index !== i)); }}>Remove unit {i + 1}</Button><UnitRowErrors errors={errors} rows={rows} row={i} /></td>
        <td><label className="dw-field">{label} source kind<select {...fieldAttributes(i, "sourceKind")} value={row.sourceKind} disabled={!editable} onChange={(e) => edit(i, { sourceKind: e.target.value as UnitDraft["sourceKind"] })}><option value="uploaded">Uploaded evidence</option><option value="declared_repository">Declared repository</option></select></label>{row.sourceKind === "declared_repository" && <><label className="dw-field">{label} repository<input {...fieldAttributes(i, "repository")} value={row.repository} maxLength={128} disabled={!editable} onChange={(e) => edit(i, { repository: e.target.value })} /></label><label className="dw-field">{label} commit<input {...fieldAttributes(i, "commit")} value={row.commit} maxLength={40} disabled={!editable} onChange={(e) => edit(i, { commit: e.target.value })} /></label></>}<label className="dw-field">{label} path<input {...fieldAttributes(i, "path")} value={row.path} maxLength={1024} disabled={!editable} onChange={(e) => edit(i, { path: e.target.value })} /></label></td>
        <td><label className="dw-field">{label} environment<input {...fieldAttributes(i, "environment")} value={row.environment} maxLength={128} disabled={!editable} onChange={(e) => edit(i, { environment: e.target.value })} /></label><label className="dw-field">{label} target<input {...fieldAttributes(i, "target")} value={row.target} maxLength={128} disabled={!editable} onChange={(e) => edit(i, { target: e.target.value })} /></label></td>
        <td><label className="dw-field">{label} prerequisites<input {...fieldAttributes(i, "prerequisites")} aria-label={`${label} prerequisites`} value={row.prerequisites} maxLength={3224} disabled={!editable} onChange={(e) => edit(i, { prerequisites: e.target.value })} /><span>Comma-separated explicit unit IDs</span></label></td></tr>;
      })}</tbody></table></div><div className="dw-automation-actions"><Button disabled={!editable || rows.length >= 25} onClick={() => { clear(); setRows([...rows, emptyUnit()]); }}>Add unit</Button><Button disabled={!editable} onClick={() => void validate()}>Validate inventory</Button></div>
      {(message || errors.length > 0) && <div ref={messageRef} tabIndex={-1} role={errors.length ? "alert" : "status"}><p>{message}</p>{errors.length > 0 && <UnitErrorSummary errors={errors} rows={rows} />}</div>}
      {plan && <><UnitWaves plan={plan} /><p>Affected units: {plan.inventory.affected.join(", ")}. Prerequisite-only units: {plan.inventory.units.filter((u) => !plan.inventory.affected.includes(u.id)).map((u) => u.id).join(", ") || "None"}.</p><label><input type="checkbox" checked={confirmed} disabled={!editable} onChange={(e) => setConfirmed(e.target.checked)} /> I confirm this exact affected and prerequisite scope</label><label className="dw-field">Revision reason<input value={reason} maxLength={256} disabled={!editable} onChange={(e) => setReason(e.target.value)} /></label><Button disabled={!editable || !confirmed || !validCollectionReason(reason)} onClick={() => void save()}>Save revision</Button></>}
      {uncertain && <div role="alert"><p>An earlier save remains unresolved. Inspect refreshed inventory history; this page will not repeat it.</p>{current && saves.canRecover(key, current) ? <><p>This verified revision matches the submitted scope, creator, version and map. Using it adopts the persisted result without sending another save.</p><Button disabled={busy || !context.fresh} onClick={() => { if (saves.recover(key, current)) { setConfirmed(false); setMessage("Verified persisted revision adopted. No save was repeated."); } }}>Use this verified revision</Button></> : current && <p>The loaded revision does not match the unresolved save.</p>}</div>}
    </section>{saved && <UnitRunStart key={saved.revision_id} revision={saved} context={context} />}
  </div>;
}

function UnitRunStart({ revision, context }: { revision: UnitRevision; context: AutomationContext }) {
  const navigate = useNavigate(), mounted = useRef(true), summary = useRef<HTMLParagraphElement>(null);
  const key = `${inventoryAccessKey(context)}:${revision.revision_id}`, [workflow, setWorkflow] = useState(""), [workflowRevision, setWorkflowRevision] = useState(""), [cursor, setCursor] = useState<string>(), [revisionCursor, setRevisionCursor] = useState<string>();
  const [generation, setGeneration] = useState(0);
  const [inputs, setInputs] = useState("{}"), [reason, setReason] = useState(""), [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [bindings, setBindings] = useState<Record<string, { intake: string; analysis: string; files: File[] }>>({});
  const outcome = useSyncExternalStore(starts.subscribe, () => starts.get(key), () => starts.get(key));
  const workflows = useQuery({ queryKey: ["automation", "unit-workflows", key, cursor], queryFn: ({ signal }) => getWorkflows(context.scope, cursor, signal), retry: false, gcTime: 0 });
  const revisions = useQuery({ queryKey: ["automation", "unit-revisions", key, workflow, revisionCursor], queryFn: ({ signal }) => getRevisions(workflow, revisionCursor, signal), enabled: !!workflow, retry: false, gcTime: 0 });
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (!context.fresh) setConfirmed(false); }, [context.fresh]);
  useEffect(() => { if (error) summary.current?.focus(); }, [error]);
  function bind(id: string, value: Partial<{ intake: string; analysis: string; files: File[] }>) { setConfirmed(false); setBindings((current) => ({ ...current, [id]: { ...(current[id] ?? { intake: "", analysis: "", files: [] }), ...value } })); }
  const complete = revision.plan.inventory.units.every((u) => bindings[u.id]?.intake && bindings[u.id]?.analysis && (u.source.kind !== "uploaded" || bindings[u.id].files.length > 0));
  async function start() {
    if (busy || outcome || !confirmed || !complete || !workflow || !workflowRevision || !can(context, "automation.request") || !context.capabilities.execution_enabled || !validCollectionReason(reason)) return;
    setBusy(true); setError(""); let ticket: ReturnType<CollectionStartRequests["begin"]> | undefined;
    try {
      const values = parseRunInputs(inputs), permission = await context.ensureFresh(); if (!mounted.current) return;
      if (!permission.execution_enabled || !permission.capabilities.includes("automation.request") || context.scope.workspaceId === null) throw new ApiClientError("Current permission unavailable.", 403);
      const mapped = await Promise.all(revision.plan.inventory.units.map(async (u) => { const b = bindings[u.id]; if (u.source.kind === "uploaded") validateArtifactFiles(b.files); return { unit_id: u.id, intake_step_id: b.intake, analysis_step_id: b.analysis, artifacts: u.source.kind === "uploaded" ? await Promise.all(b.files.map(async (file) => ({ name: file.name, content: await file.text() }))) : [] }; }));
      if (!mounted.current) return;
      const requestId = crypto.randomUUID(); const payload: UnitRunRequest = { run: { workflow_id: workflow, revision_id: workflowRevision, workspace_id: context.scope.workspaceId, inputs: values, idempotency_key: requestId, total_timeout_seconds: 3600, reason }, revision_id: revision.revision_id, confirmed_map_digest: revision.map_digest, bindings: mapped };
      const run = await startUnitRun(payload, context.scope, context.identity.csrfToken!, () => { ticket = starts.remember(key, payload); });
      if (ticket) starts.succeed(key, ticket, run.id); if (mounted.current) navigate(`/infra-automation/runs/${encodeURIComponent(run.id)}${scopeQuery(context.scope)}`);
    } catch (failure) { if (ticket && isConfirmedCollectionRejection(failure)) starts.reject(key, ticket); if (mounted.current) { setConfirmed(false); setError(ticket && !isConfirmedCollectionRejection(failure) ? "Run request outcome is unresolved. Inspect run history before another request; nothing is resent automatically." : automationError(failure)); } }
    finally { if (mounted.current) setBusy(false); }
  }
  async function retryStart() {
    const ticket = starts.get(key), payload = starts.pendingRequest(key);
    if (busy || ticket?.kind !== "pending" || !payload || !can(context, "automation.request")) return;
    setBusy(true); setError("");
    try {
      const permission = await context.ensureFresh();
      if (!mounted.current || starts.get(key) !== ticket) return;
      if (!permission.execution_enabled || !permission.capabilities.includes("automation.request")) throw new ApiClientError("Current permission unavailable.", 403);
      const run = await startUnitRun(payload, context.scope, context.identity.csrfToken!);
      starts.succeed(key, ticket, run.id);
      if (mounted.current) navigate(`/infra-automation/runs/${encodeURIComponent(run.id)}${scopeQuery(context.scope)}`);
    } catch (failure) {
      // A rejected retry does not prove that the original request never committed.
      if (mounted.current) setError(`${automationError(failure)} Run outcome remains unresolved. The original request identity and exact evidence are retained.`);
    } finally { if (mounted.current) setBusy(false); }
  }
  const editable = !busy && !outcome;
  return <section className="dw-automation-section"><h3>Run saved revision {revision.version}</h3><p>Bind every declared unit to its existing workflow intake and analysis step. The server verifies exact coverage and prerequisite order before admission.</p>
    <label className="dw-field">Workflow<select value={workflow} disabled={!editable || workflows.isPending || !!workflows.error} onChange={(e) => { setConfirmed(false); setWorkflow(e.target.value); setWorkflowRevision(""); setRevisionCursor(undefined); setBindings({}); }}><option value="">Choose a workflow</option>{workflows.data?.items.filter((w) => !w.archived).map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
    {workflows.error && <p role="alert">{automationError(workflows.error)}</p>}<div className="dw-automation-actions">{cursor && <Button disabled={!editable} onClick={() => { setConfirmed(false); setWorkflow(""); setWorkflowRevision(""); setCursor(undefined); }}>First workflow page</Button>}{workflows.data?.cursor.next_cursor && <Button disabled={!editable} onClick={() => { setConfirmed(false); setWorkflow(""); setWorkflowRevision(""); setCursor(workflows.data!.cursor.next_cursor!); }}>Next workflow page</Button>}</div>
    {workflow && <><label className="dw-field">Workflow revision<select value={workflowRevision} disabled={!editable || revisions.isPending || !!revisions.error} onChange={(e) => { setConfirmed(false); setWorkflowRevision(e.target.value); }}><option value="">Choose a published revision</option>{revisions.data?.items.map((r) => <option key={r.id} value={r.id}>Revision {r.revision_number}</option>)}</select></label>{revisions.error && <p role="alert">{automationError(revisions.error)}</p>}{revisionCursor && <Button disabled={!editable} onClick={() => { setConfirmed(false); setWorkflowRevision(""); setRevisionCursor(undefined); }}>First revision page</Button>}{revisions.data?.cursor.next_cursor && <Button disabled={!editable} onClick={() => { setConfirmed(false); setWorkflowRevision(""); setRevisionCursor(revisions.data!.cursor.next_cursor!); }}>Next revision page</Button>}</>}
    {revision.plan.inventory.units.map((unit: DeclaredUnit) => <fieldset key={`${unit.id}:${generation}`} disabled={!editable}><legend>{unit.id} evidence binding</legend><label className="dw-field">{unit.id} intake step<input maxLength={128} value={bindings[unit.id]?.intake ?? ""} onChange={(e) => bind(unit.id, { intake: e.target.value })} /></label><label className="dw-field">{unit.id} analysis step<input maxLength={128} value={bindings[unit.id]?.analysis ?? ""} onChange={(e) => bind(unit.id, { analysis: e.target.value })} /></label>{unit.source.kind === "uploaded" ? <label className="dw-field">{unit.id} artifacts<input type="file" multiple onChange={(e) => bind(unit.id, { files: Array.from(e.target.files ?? []) })} /></label> : <p>Collected repository {unit.source.repository_id} at {unit.source.commit_sha}. Only root path (.) is supported by the current collector.</p>}</fieldset>)}
    <label className="dw-field">Run inputs (JSON)<textarea rows={3} value={inputs} disabled={!editable} onChange={(e) => { setConfirmed(false); setInputs(e.target.value); }} /></label><label className="dw-field">Run reason<input value={reason} maxLength={256} disabled={!editable} onChange={(e) => { setConfirmed(false); setReason(e.target.value); }} /></label>
    <label><input type="checkbox" checked={confirmed} disabled={!editable || !context.fresh} onChange={(e) => setConfirmed(e.target.checked)} /> I confirm this saved revision and collection/review order</label><p>Changed infrastructure requires recollection, reanalysis and a new approval. Confirmation does not authorize deployment.</p>
    <Button disabled={!editable || !confirmed || !complete || !workflowRevision || !can(context, "automation.request") || !context.capabilities.execution_enabled || !validCollectionReason(reason)} onClick={() => void start()}>Start preflight run</Button>
    {error && <p role="alert" tabIndex={-1} ref={summary}>{error}</p>}{outcome?.kind === "pending" && <p role="status">Request unresolved. <Link to={`/infra-automation${scopeQuery(context.scope)}&view=runs`}>Read run history</Link>. <Button disabled={busy || !can(context, "automation.request")} onClick={() => void retryStart()}>Retry original run request</Button> The same request identity and exact evidence are reused; no new run request is generated.</p>}{outcome?.kind === "confirmed" && <><Link to={`/infra-automation/runs/${encodeURIComponent(outcome.runId!)}${scopeQuery(context.scope)}`}>Open confirmed run</Link><Button onClick={() => { starts.clearConfirmed(key); setConfirmed(false); setBindings({}); setGeneration((value) => value + 1); setReason(""); setError(""); }}>Prepare another preflight</Button></>}
  </section>;
}

export function UnitRunEvidence({ value, stale }: { value: UnitRunView; stale: boolean }) {
  if (!value.available || !value.snapshot || !value.evidence) return null;
  const { revision } = value.snapshot, evidence = value.evidence;
  return <section className="dw-automation-section"><h3>Declared unit evidence</h3>{stale && <p role="status">Historical unit evidence; current freshness and lock status are unavailable.</p>}<p>Inventory revision {revision.version} · evidence {evidence.status}</p>{evidence.status === "changed" && <p role="alert">Review required again. Recollect, reanalyze and obtain a new approval.</p>}<UnitWaves plan={revision.plan} /><div className="dw-automation-table-wrap"><table className="dw-automation-table"><caption>Unit scope, evidence and canonical locks</caption><thead><tr><th scope="col">Unit</th><th scope="col">Scope</th><th scope="col">Declared source/path</th><th scope="col">Evidence</th><th scope="col">Canonical target / lock</th></tr></thead><tbody>{revision.plan.inventory.units.map((u) => { const item = evidence.items.find((e) => e.unit_id === u.id), lock = value.locks.find((l) => l.unit_id === u.id); return <tr key={u.id}><th scope="row">{u.id}</th><td>{revision.plan.inventory.affected.includes(u.id) ? "Affected" : "Prerequisite"}</td><td>{u.source.kind === "uploaded" ? "Uploaded; repository unavailable" : `Declared ${u.source.repository_id} at ${u.source.commit_sha}`}<br />Path: {u.source.path}</td><td>{item ? <Link to={`/reports/${item.report_id}`}>Report {item.report_id}</Link> : "Pending"}</td><td>{lock?.canonical_target ?? "Unavailable"} / {lock?.status ?? "unavailable"}</td></tr>; })}</tbody></table></div>{evidence.combined_digest && <p>Combined evidence digest: <code>{evidence.combined_digest}</code></p>}<p>Unknown external work retains canonical locks. Cancellation or expiry does not release uncertainty. An audited lock break does not create authorization.</p><p>After infrastructure, source, map or evidence changes, recollect, reanalyze and obtain a new approval.</p></section>;
}
export function RunUnitsPanel({ context, runId, runVersion, onDenied }: { context: AutomationContext; runId: string; runVersion: number; onDenied: () => void }) {
  const units = useQuery({ queryKey: ["automation", "run-units", inventoryAccessKey(context), runId, runVersion], queryFn: ({ signal }) => getRunUnits(runId, context.scope, signal), ...unitEvidenceReadOptions });
  useEffect(() => { if (units.error instanceof ApiClientError && [401, 403].includes(units.error.status)) onDenied(); }, [units.error, onDenied]);
  if (units.error) return <p role="alert">Unit evidence unavailable. <Button onClick={() => void units.refetch()}>Retry unit evidence</Button></p>;
  if (units.isPending) return <p role="status">Loading declared unit evidence…</p>;
  return <div><p>Unit evidence is an observation. Refresh before relying on current state.</p><Button disabled={units.isFetching} onClick={() => void units.refetch()}>Refresh unit evidence</Button><UnitRunEvidence value={units.data} stale={!context.fresh || units.isFetching || units.data.run_version !== runVersion} /></div>;
}
export function InfraAutomationInventoryScreen() { return <AutomationFrame>{(context) => context.scope.workspaceId === null ? <p>Select a concrete workspace to declare inventory.</p> : <InventoryEditor key={inventoryAccessKey(context)} context={context} />}</AutomationFrame>; }
