import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiClientError } from "../api/client";
import {
  createWorkflow, getWorkflow, getWorkflows, getRuns, getRevisions, getRevision,
  validateWorkflow, validateDraft, saveWorkflowDraft, publishWorkflow, startPreflight,
  type AutomationScope, type WorkflowDetail, type Validation,
} from "../api/infraAutomation";
import { Button, SegmentedTabs } from "../components/ui";
import { AutomationFrame, AccountLink, automationError, scopeQuery, type AutomationContext } from "./InfraAutomationShared";

const denied = (error: unknown) => error instanceof ApiClientError && [401, 403].includes(error.status);

export function uploadWorkflowTemplate(scope: AutomationScope): string {
  return `workflow_version: 2\nproject_id: "${scope.projectId}"\nworkspace_id: ${scope.workspaceId === null ? "null" : `"${scope.workspaceId}"`}\nenvironment: review\ninputs: {}\nsteps:\n  - id: artifacts\n    kind: uploaded_intake\n    depends_on: []\n    source:\n      kind: uploaded\n  - id: analysis\n    kind: shared_analysis\n    depends_on: [artifacts]\n    artifact:\n      ref: step\n      step_id: artifacts\n      output: screened_artifacts\n`;
}

export function parseRunInputs(text: string): Record<string, string | number | boolean> {
  let value: unknown;
  try { value = JSON.parse(text); } catch { throw new Error("Run inputs must be a JSON object containing bounded scalar values."); }
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length > 32) throw new Error("Run inputs must be a JSON object with at most 32 fields.");
  for (const [name, scalar] of Object.entries(value)) {
    if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(name) ||
      !(typeof scalar === "boolean" || (typeof scalar === "string" && scalar.length <= 1024) || (typeof scalar === "number" && Number.isSafeInteger(scalar)))) throw new Error("Run inputs require valid field names and bounded strings, booleans or safe integers.");
  }
  return value as Record<string, string | number | boolean>;
}

export function validateArtifactFiles(files: Pick<File, "name" | "size">[]): void {
  if (!files.length || files.length > 32 || files.reduce((total, file) => total + file.size, 0) > 8_388_608 ||
    files.some((file) => !file.size || /[\\/\u0000]/.test(file.name) || !/\.(tf|hcl|tfvars|json|ya?ml)$/i.test(file.name) || /\.tfstate(?:\.|$)/i.test(file.name)) ||
    new Set(files.map((file) => file.name)).size !== files.length) throw new Error("Choose 1–32 distinct, nonempty supported UTF-8 artifacts, at most 8 MiB total. State, credentials and binary plans are not accepted.");
}

export function WorkflowList({ context }: { context: AutomationContext }) {
  const navigate = useNavigate();
  const query = useInfiniteQuery({ queryKey: ["automation", "workflows", context.identity.epoch, context.scope.projectId, context.scope.workspaceId], initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getWorkflows(context.scope, pageParam, signal), getNextPageParam: (page) => page.cursor.next_cursor ?? undefined, retry: false, gcTime: 0 });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const canCreate = context.fresh && Boolean(context.identity.csrfToken) && context.capabilities.capabilities.includes("automation.draft") && query.isSuccess && !query.isFetching;
  return <section aria-labelledby="automation-index-tab-workflows" id="automation-index-panel-workflows" role="tabpanel" tabIndex={0}>
    <div className="dw-automation-actions"><h2>Workflows</h2><Button disabled={!canCreate} onClick={() => navigate(`/infra-automation/workflows/new${scopeQuery(context.scope)}`)} variant="primary-gradient">Create workflow</Button><Button onClick={() => { void query.refetch(); }} disabled={query.isFetching}>Refresh workflows</Button></div>
    {!context.capabilities.capabilities.includes("automation.draft") && <p>Workflow authoring is not permitted for your account in this scope.</p>}
    {query.isPending && <p role="status">Loading workflows…</p>}
    {query.isError && <p className="dw-automation-notice" role="alert">{automationError(query.error)}</p>}
    {!denied(query.error) && <>
      {!query.isPending && !items.length && <p>No workflows in this scope. A permitted author can create a validated draft.</p>}
      {items.length > 0 && <div className="dw-automation-table-wrap" role="region" aria-label="Workflow table" tabIndex={0}><table><caption>Workflows in the selected project and workspace</caption><thead><tr><th scope="col">Workflow</th><th scope="col">Draft version</th><th scope="col">State</th><th scope="col">Updated</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><Link to={`/infra-automation/workflows/${encodeURIComponent(item.id)}${scopeQuery(context.scope)}`}>{item.name}</Link></td><td>{item.draft_version}</td><td>{item.archived ? "Archived" : "Draft / published history"}</td><td>{item.updated_at}</td></tr>)}</tbody></table></div>}
      {query.data?.pages.some((page) => page.cursor.gap) && <p role="status">The retained list has a gap. Refresh to read current history.</p>}
      {query.hasNextPage && <Button disabled={query.isFetchingNextPage} onClick={() => { void query.fetchNextPage(); }}>More workflows</Button>}
    </>}
  </section>;
}

export function RunHistory({ context }: { context: AutomationContext }) {
  const query = useInfiniteQuery({ queryKey: ["automation", "runs", context.identity.epoch, context.scope.projectId, context.scope.workspaceId], initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getRuns(context.scope, pageParam, signal), getNextPageParam: (page) => page.cursor.next_cursor ?? undefined, retry: false, gcTime: 0 });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return <section aria-labelledby="automation-index-tab-runs" id="automation-index-panel-runs" role="tabpanel" tabIndex={0}>
    <div className="dw-automation-actions"><h2>Run history</h2><Button disabled={query.isFetching} onClick={() => { void query.refetch(); }}>Refresh runs</Button></div>
    {query.isPending && <p role="status">Loading runs…</p>}{query.isError && <p role="alert">{automationError(query.error)}</p>}
    {!denied(query.error) && <>{!query.isPending && !items.length && <p>No uploaded preflight runs in this scope.</p>}
      {items.length > 0 && <div className="dw-automation-table-wrap" role="region" aria-label="Run history table" tabIndex={0}><table><caption>Immutable runs in the selected scope</caption><thead><tr><th scope="col">Run</th><th scope="col">Recorded state</th><th scope="col">Revision</th><th scope="col">Created at</th></tr></thead><tbody>{items.map((run) => <tr key={run.id}><td><Link to={`/infra-automation/runs/${encodeURIComponent(run.id)}${scopeQuery(context.scope)}`}>{run.id}</Link></td><td><span className="dw-automation-status">{run.state}</span></td><td><code>{run.revision_id}</code></td><td>{run.created_at}</td></tr>)}</tbody></table></div>}
      {query.data?.pages.some((page) => page.cursor.gap) && <p role="status">The retained run list has a gap. Refresh to read current history.</p>}
      {query.hasNextPage && <Button disabled={query.isFetchingNextPage} onClick={() => { void query.fetchNextPage(); }}>More runs</Button>}
    </>}
  </section>;
}

function IndexContent({ context }: { context: AutomationContext }) {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "runs" ? "runs" : "workflows";
  return <><SegmentedTabs activeId={view} idPrefix="automation-index" label="Automation sections" tabs={[{ id: "workflows", label: "Workflows" }, { id: "runs", label: "Runs" }]} onChange={(id) => { const next = new URLSearchParams(params); next.set("view", id); setParams(next, { replace: true }); }} />
    {view === "runs" ? <><RunHistory context={context} /><section hidden id="automation-index-panel-workflows" aria-labelledby="automation-index-tab-workflows" role="tabpanel" /></> : <><WorkflowList context={context} /><section hidden id="automation-index-panel-runs" aria-labelledby="automation-index-tab-runs" role="tabpanel" /></>}</>;
}

export function InfraAutomationScreen() {
  return <AutomationFrame>{(context) => <IndexContent key={`${context.identity.epoch}:${context.scope.projectId}:${context.scope.workspaceId}`} context={context} />}</AutomationFrame>;
}

function WorkflowEditor({ context, workflowId }: { context: AutomationContext; workflowId: string }) {
  const isNew = workflowId === "new";
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = ["automation", "workflow", context.identity.epoch, context.scope.projectId, context.scope.workspaceId, workflowId];
  const workflowQuery = useQuery({ queryKey: key, queryFn: ({ signal }) => getWorkflow(workflowId, signal), enabled: !isNew, retry: false, gcTime: 0 });
  const [record, setRecord] = useState<WorkflowDetail | null>(null);
  const [name, setName] = useState("");
  const [definition, setDefinition] = useState(() => uploadWorkflowTemplate(context.scope));
  const [reason, setReason] = useState("");
  const [dirty, setDirty] = useState(isNew);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [validatedText, setValidatedText] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"error" | "success">("error");
  const [conflict, setConflict] = useState(false);
  const [needsReview, setNeedsReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const summary = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const alive = useRef(true);
  const [revisionId, setRevisionId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [inputs, setInputs] = useState("{}");
  const [runReason, setRunReason] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const revisions = useInfiniteQuery({ queryKey: ["automation", "revisions", context.identity.epoch, context.scope.projectId, context.scope.workspaceId, workflowId], initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getRevisions(workflowId, pageParam, signal), getNextPageParam: (page) => page.cursor.next_cursor ?? undefined, enabled: !isNew, retry: false, gcTime: 0 });
  const revisionItems = revisions.data?.pages.flatMap((page) => page.items) ?? [];
  const selected = useQuery({ queryKey: ["automation", "revision", context.identity.epoch, context.scope.projectId, context.scope.workspaceId, workflowId, revisionId], queryFn: ({ signal }) => getRevision(workflowId, revisionId, signal), enabled: !isNew && Boolean(revisionId), retry: false, gcTime: 0 });
  function loadRecord(value: WorkflowDetail) { setRecord(value); setName(value.name); setDefinition(JSON.stringify(value.definition, null, 2)); setDirty(false); setConflict(false); setNeedsReview(false); setValidation(null); setValidatedText(null); setFiles([]); setUncertain(false); }
  useEffect(() => { if (workflowQuery.data && !record) loadRecord(workflowQuery.data); else if (!busy && workflowQuery.data && record && workflowQuery.data.draft_version !== record.draft_version) { setConflict(true); setNeedsReview(true); setValidation(null); setValidatedText(null); } }, [workflowQuery.data, record, busy]);
  useEffect(() => { if (!revisionId && revisionItems[0]) setRevisionId(revisionItems[0].id); }, [revisionId, revisionItems]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { if (isNew || record?.id) heading.current?.focus(); }, [isNew, record?.id]);
  useEffect(() => { if (message || (validation && !validation.valid)) summary.current?.focus(); }, [message, validation]);
  const permittedDraft = context.capabilities.capabilities.includes("automation.draft");
  const permittedPublish = context.capabilities.capabilities.includes("automation.publish");
  const permittedRequest = context.capabilities.capabilities.includes("automation.request");
  const mutable = context.fresh && Boolean(context.identity.csrfToken) && !busy && !conflict && !record?.archived && (isNew || (workflowQuery.isSuccess && !workflowQuery.isFetching));
  const validCandidate = validation?.valid && validatedText === definition;
  async function failure(error: unknown, ambiguous = false) {
    if (!alive.current) return;
    setMessageKind("error");
    setValidation(null); setValidatedText(null);
    if (error instanceof ApiClientError && error.status === 409 && !isNew) {
      setConflict(true);
      const current = await workflowQuery.refetch();
      if (alive.current && current.data && !current.error) { loadRecord(current.data); setConflict(true); setNeedsReview(true); setMessage("Current state changed. Server state was reloaded; validate and review again."); }
      else setMessage("Current state changed and could not be reloaded. Refresh server state before continuing.");
    } else { setMessage(automationError(error)); if (ambiguous && !(error instanceof ApiClientError && error.status >= 400 && error.status < 500)) setUncertain(true); }
  }
  async function fresh(permission: "automation.draft" | "automation.publish" | "automation.request") {
    const value = await context.ensureFresh();
    if (!alive.current || !value.capabilities.includes(permission)) throw new ApiClientError("Current permission unavailable.", 403);
    return value;
  }
  async function validate() {
    setBusy(true); setMessage(null);
    try { await fresh("automation.draft"); const value = isNew ? await validateWorkflow(context.scope, definition, context.identity.csrfToken!) : await validateDraft(workflowId, record!.draft_version, definition, context.identity.csrfToken!); if (alive.current) { setValidation(value); setValidatedText(definition); if (value.valid) { setConflict(false); setNeedsReview(false); } } }
    catch (error) { await failure(error); } finally { if (alive.current) setBusy(false); }
  }
  async function save() {
    setBusy(true); setMessage(null);
    let submitted = false;
    try {
      await fresh("automation.draft");
      submitted = true;
      const value = isNew ? await createWorkflow({ project_id: context.scope.projectId, workspace_id: context.scope.workspaceId, name, definition, reason }, context.identity.csrfToken!) : await saveWorkflowDraft(workflowId, { expected_version: record!.draft_version, definition, reason }, context.identity.csrfToken!);
      if (!alive.current) return;
      if (isNew) navigate(`/infra-automation/workflows/${encodeURIComponent(value.id)}${scopeQuery(context.scope)}`, { replace: true });
      else { queryClient.setQueryData(key, value); loadRecord(value); setMessageKind("success"); setMessage("Draft saved. Publication is a separate action."); }
    } catch (error) { await failure(error, submitted); } finally { if (alive.current) setBusy(false); }
  }
  async function publish() {
    setBusy(true); setMessage(null);
    let submitted = false;
    try {
      await fresh("automation.publish");
      submitted = true;
      const value = await publishWorkflow(workflowId, { expected_version: record!.draft_version, idempotency_key: crypto.randomUUID(), reason }, context.identity.csrfToken!);
      if (!alive.current) return;
      setRevisionId(value.id); await revisions.refetch();
      const current = await workflowQuery.refetch();
      if (alive.current && current.data && !current.error) { loadRecord(current.data); setMessageKind("success"); setMessage(`Revision ${value.revision_number} published immutably. It is ready for a permitted uploaded preflight.`); }
    } catch (error) { await failure(error, submitted); } finally { if (alive.current) setBusy(false); }
  }
  async function start() {
    setBusy(true); setMessage(null);
    let artifacts: { name: string; content: string }[];
    let runInputs: Record<string, string | number | boolean>;
    try {
      validateArtifactFiles(files);
      runInputs = parseRunInputs(inputs);
      artifacts = await Promise.all(files.map(async (file) => ({ name: file.name, content: new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()) })));
    } catch (error) {
      if (alive.current) { setMessage(error instanceof Error && (error.message.startsWith("Run inputs") || error.message.startsWith("Choose 1")) ? error.message : "Artifacts must be supported nonempty UTF-8 text. Review the selected files."); setBusy(false); }
      return;
    }
    let submitted = false;
    try {
      const capability = await fresh("automation.request");
      if (!capability.execution_enabled || context.scope.workspaceId === null || !selected.data) throw new ApiClientError("Run start unavailable.", 403);
      if (!alive.current) return;
      submitted = true;
      const run = await startPreflight({ run: { workflow_id: workflowId, revision_id: revisionId, workspace_id: context.scope.workspaceId, inputs: runInputs, idempotency_key: crypto.randomUUID(), reason: runReason, total_timeout_seconds: 3600 }, artifacts }, context.identity.csrfToken!);
      if (alive.current) navigate(`/infra-automation/runs/${encodeURIComponent(run.id)}${scopeQuery(context.scope)}`);
    } catch (error) { await failure(error, submitted); }
    finally { if (alive.current) setBusy(false); }
  }
  if (!isNew && workflowQuery.isPending) return <p role="status">Loading current workflow…</p>;
  if (denied(workflowQuery.error) || denied(revisions.error) || denied(selected.error)) return <p role="alert">Workflow or revision unavailable for your current account and scope.</p>;
  if (record && (record.project_id !== context.scope.projectId || (record.workspace_id !== null && record.workspace_id !== context.scope.workspaceId))) return <div role="status"><p>This workflow belongs to a different selected scope. Prior forms and eligibility have been cleared.</p><Button onClick={() => context.selectProject(record.project_id)}>Use workflow project</Button><Button onClick={() => context.selectWorkspace(record.workspace_id)}>Use workflow workspace</Button><p><Link to={`/infra-automation${scopeQuery(context.scope)}`}>Open selected project workflows</Link></p></div>;
  if (isNew && !permittedDraft) return <p role="alert">Workflow authoring is not permitted in this scope.</p>;
  const steps = selected.data?.definition.steps;
  const uploadOnly = steps?.length === 2 && steps.filter((step) => step.kind === "uploaded_intake").length === 1 && steps.filter((step) => step.kind === "shared_analysis").length === 1;
  const canStart = mutable && !needsReview && permittedRequest && context.capabilities.execution_enabled && context.scope.workspaceId !== null && selected.isSuccess && !selected.isFetching && uploadOnly && files.length > 0 && Boolean(runReason.trim()) && !uncertain;
  return <div className="dw-automation-stack">
    <Link to={`/infra-automation${scopeQuery(context.scope)}`}>Back to workflows</Link>
    <div className="dw-automation-section"><h2 ref={heading} tabIndex={-1}>{isNew ? "Create workflow" : record?.name ?? "Workflow"}</h2>
      {record && <p>Draft version {record.draft_version} · {record.archived ? "Archived" : "Current draft"} · Updated {record.updated_at}</p>}
      {(message || validation?.errors.length) ? <div className={`dw-automation-error-summary${messageKind === "success" && !validation?.errors.length ? " dw-automation-success" : ""}`} role={validation?.valid === false ? "alert" : "status"} tabIndex={-1} ref={summary}>
        {message && <p>{message}</p>}{validation && !validation.valid && <><strong>Definition validation failed</strong><ul>{validation.errors.map((error, index) => <li key={index}><a href="#workflow-yaml">{error.message} · {error.path.join(".") || "definition"}{error.step_index !== null && error.step_index !== undefined ? ` · step ${error.step_index + 1}` : ""}{error.line ? ` · line ${error.line}, column ${error.column ?? "unavailable"}` : ""}</a></li>)}</ul>{validation.truncated && <p>Additional diagnostics were omitted; correct these errors and validate again.</p>}</>}
      </div> : null}
      {(workflowQuery.isError || revisions.isError || selected.isError) && <p role="alert">{automationError(workflowQuery.error ?? revisions.error ?? selected.error)}</p>}
      {conflict && <p role="alert">The saved version changed. Validate the current server draft before saving, publishing or starting.</p>}
      {!isNew && <Button onClick={async () => { const value = await workflowQuery.refetch(); if (value.data && !value.error) { const review = conflict || needsReview; loadRecord(value.data); setNeedsReview(review); setMessage(review ? "Current server draft reloaded. Validate before continuing." : "Current server draft reloaded."); } }}>Reload server state</Button>}
      <div className="dw-automation-form">
        <label className="dw-field" htmlFor="workflow-name"><span>Workflow name</span><input id="workflow-name" required maxLength={120} disabled={!isNew || !permittedDraft || busy} value={name} onChange={(event) => setName(event.target.value)} /></label>
        <div className="dw-automation-actions"><span>Supported template: uploaded artifact review</span><Button disabled={!permittedDraft || busy || Boolean(record?.archived)} onClick={() => { setDefinition(uploadWorkflowTemplate(context.scope)); setDirty(true); setValidation(null); setValidatedText(null); }}>Use upload template</Button></div>
        <div className="dw-field"><label htmlFor="workflow-yaml">Workflow YAML</label><textarea id="workflow-yaml" rows={19} spellCheck={false} maxLength={131072} readOnly={!permittedDraft || Boolean(record?.archived)} disabled={busy} aria-invalid={validation?.valid === false} aria-describedby="workflow-yaml-help" value={definition} onChange={(event) => { setDefinition(event.target.value); setDirty(true); setValidation(null); setValidatedText(null); }} /></div>
        <p id="workflow-yaml-help">Server validation checks the closed workflow-v2 schema and step references. Saving a draft does not publish a revision.</p>
        <label className="dw-field" htmlFor="workflow-reason"><span>Reason</span><input id="workflow-reason" maxLength={256} value={reason} disabled={busy || !permittedDraft} onChange={(event) => setReason(event.target.value)} placeholder="Why are you making this change?" /></label>
        {validation?.valid && <p role="status">Definition valid. {validation.digest}</p>}
        <div className="dw-automation-actions"><Button disabled={!context.fresh || !context.identity.csrfToken || busy || !permittedDraft || Boolean(record?.archived) || (!isNew && !record)} onClick={() => { void validate(); }}>Validate</Button><Button variant="primary-gradient" disabled={!mutable || !permittedDraft || !validCandidate || !name.trim() || !reason.trim() || uncertain} onClick={() => { void save(); }}>Save draft</Button><Button disabled={isNew || !mutable || !permittedPublish || needsReview || dirty || !reason.trim() || uncertain} onClick={() => { void publish(); }}>Publish revision</Button></div>
        <p>A workflow name, reason and successful validation are required before saving.</p>
        {!permittedPublish && <p>Publishing is not permitted for this account. A permitted project author must publish an immutable revision.</p>}
        {uncertain && <p role="alert">The last mutation was not confirmed. Inspect current workflow/revision/run history before creating another request; automatic replay is disabled.</p>}
      </div>
    </div>
    {!isNew && <section className="dw-automation-section"><h2>Immutable published revisions</h2>
      {!revisionItems.length && <p>No published revisions. Save and publish a validated draft before starting a run.</p>}
      {revisionItems.length > 0 && <div className="dw-field"><label htmlFor="published-revision">Published revision</label><select id="published-revision" value={revisionId} disabled={busy || revisions.isFetching} onChange={(event) => { setRevisionId(event.target.value); setFiles([]); }}>
        {revisionItems.map((item) => <option key={item.id} value={item.id}>Revision {item.revision_number} · {item.created_at}</option>)}
      </select></div>}
      {selected.data && <dl className="dw-automation-facts"><dt>Revision ID</dt><dd>{selected.data.id}</dd><dt>Immutable definition digest</dt><dd><code>{selected.data.digest}</code></dd><dt>Published by</dt><dd>{selected.data.published_by}</dd><dt>Environment</dt><dd>{typeof selected.data.definition.environment === "string" ? selected.data.definition.environment : "Typed input reference; resolved at admission"}</dd></dl>}
      {revisions.hasNextPage && <Button onClick={() => { void revisions.fetchNextPage(); }}>More revisions</Button>}
      <Button disabled={revisions.isFetching} onClick={() => { void revisions.refetch(); }}>Refresh revisions</Button>
    </section>}
    {!isNew && <section className="dw-automation-section"><h2>Start uploaded preflight</h2><p>Uploaded evidence has unverified repository provenance and remains advisory. No apply or deployment action is authorized.</p>
      {!context.capabilities.execution_enabled && <p>New starts are disabled by project policy.</p>}{!permittedRequest && <p>Requesting runs is not permitted for this account.</p>}{context.scope.workspaceId === null && <p>Select an authorized concrete workspace before starting.</p>}{selected.data && !uploadOnly && <p>This revision is not supported by the uploaded preflight entrypoint. Use a two-step uploaded-intake/shared-analysis revision.</p>}
      <div className="dw-automation-form"><label className="dw-field" htmlFor="preflight-artifacts"><span>Uploaded artifacts</span><input id="preflight-artifacts" type="file" multiple accept=".tf,.tfvars,.hcl,.json,.yaml,.yml" disabled={busy || !permittedRequest} onChange={(event) => { setFiles(Array.from(event.target.files ?? [])); setMessage(null); }} /></label><p>Up to 32 distinct UTF-8 files and 8 MiB total. Never upload state, saved binary plans or credentials. The server screens every artifact.</p>
        <div className="dw-field"><label htmlFor="preflight-inputs">Run inputs (JSON)</label><textarea id="preflight-inputs" rows={3} spellCheck={false} value={inputs} disabled={busy || !permittedRequest} onChange={(event) => setInputs(event.target.value)} /></div>
        <label className="dw-field" htmlFor="preflight-reason"><span>Run reason</span><input id="preflight-reason" maxLength={256} value={runReason} disabled={busy || !permittedRequest} onChange={(event) => setRunReason(event.target.value)} /></label>
        <div><Button variant="primary-gradient" disabled={!canStart} onClick={() => { void start(); }}>Start preflight</Button></div>
        {(!context.identity.csrfToken || !context.fresh) && <p>Fresh account and scope verification is required. <AccountLink /></p>}
      </div>
    </section>}
  </div>;
}

export function InfraWorkflowScreen() {
  const { workflowId = "new" } = useParams();
  return <AutomationFrame>{(context) => <WorkflowEditor key={`${context.identity.epoch}:${context.scope.projectId}:${context.scope.workspaceId}:${workflowId}`} context={context} workflowId={workflowId} />}</AutomationFrame>;
}
