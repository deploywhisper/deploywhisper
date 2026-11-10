import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiClientError } from "../api/client";
import { getWorkspaces } from "../api/infraAutomation";
import { getAutomationSettings, getSettingsMemberships, getSettingsTargets, getSettingsTarget, saveAutomationSettings, settingsFields, validateAutomationSettings, type AutomationPolicy, type AutomationSettings } from "../api/infraAutomationSettings";
import { Button, Card, MonoRef } from "../components/ui";
import { useIdentity } from "./IdentitySession";

function message(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.status === 403) return "Project administrator access is required. Current permissions are checked for every save.";
    if (error.status === 401) return "Sign in again before changing automation settings.";
    if (error.status === 409) return "Settings changed or the requested reduction conflicts with retained usage. Refresh current settings and review limits before saving again.";
    if (error.status === 422) return "Settings were rejected. Check integer limits, lifetime floors and the change reason.";
    if (error.status === 429) return "Capacity is unavailable. Retained unknown work must be reconciled before retrying.";
  }
  return "The save response is unconfirmed. Refresh current settings before continuing; this page never automatically repeats a save.";
}
export function automationSettingsAccessKey(projectId: number, epoch: number, sessionId?: string) { return `${epoch}:${sessionId ?? "anonymous"}:${projectId}`; }
export function AutomationSettingsSection({ projectId, projectKey }: { projectId: number; projectKey: string }) {
  const identity = useIdentity();
  return <AutomationSettingsAccess key={automationSettingsAccessKey(projectId, identity.epoch, identity.principal?.session_id)} projectId={projectId} projectKey={projectKey} />;
}
function AutomationSettingsAccess({ projectId, projectKey }: { projectId: number; projectKey: string }) {
  const identity = useIdentity();
  const enabled = identity.status === "ready" && identity.principal?.principal_type === "human";
  const membership = useQuery({ queryKey: ["automation-settings-memberships", projectId, identity.epoch], queryFn: ({ signal }) => getSettingsMemberships(projectId, projectKey, signal), enabled, retry: false, staleTime: 0 });
  const isAdmin = !membership.isError && membership.data?.some((m) => m.principal_id === identity.principal?.principal_id && m.role === "admin" && m.enabled && m.workspace_id === null);
  const policy = useQuery({ queryKey: ["automation-settings", projectId, identity.epoch], queryFn: ({ signal }) => getAutomationSettings(projectId, signal), enabled: enabled && !!isAdmin, retry: false, staleTime: 0 });
  return <div className="dw-settings-account"><Card eyebrow="InfraFlow" title="Automation settings"><div className="dw-phase6-stack">
    <p>Project execution limits and evidence lifetimes. No infrastructure credentials are entered or stored by this form.</p>
    {!enabled && <p role="status">Sign in with a project administrator account to manage automation settings.</p>}
    {enabled && membership.isPending && <p role="status">Checking administrator access…</p>}
    {enabled && (membership.isError || (membership.data && !isAdmin)) && <p role="status">Project administrator access is required to manage automation settings.</p>}
    {isAdmin && policy.isPending && <p role="status">Loading automation settings…</p>}
    {isAdmin && policy.isError && <p role="alert">Automation settings are unavailable. <Button onClick={() => void policy.refetch()}>Refresh automation settings</Button></p>}
    {isAdmin && policy.data && !policy.isError && <AutomationSettingsForm key={`${policy.data.version}:${policy.data.authorization_epoch}`} policy={policy.data} editable={enabled && !!identity.csrfToken && !policy.isFetching && !membership.isFetching} refresh={() => policy.refetch()} />}
    {isAdmin && <RegisteredTargets key={projectId} projectId={projectId} projectKey={projectKey} />}
  </div></Card></div>;
}
function AutomationSettingsForm({ policy, editable, refresh }: { policy: AutomationPolicy; editable: boolean; refresh: () => Promise<unknown> }) {
  const identity = useIdentity(), queryClient = useQueryClient();
  const [form, setForm] = useState(policy.settings);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false), [blocked, setBlocked] = useState(false);
  const [errors, setErrors] = useState<string[]>([]), [note, setNote] = useState("");
  const summary = useRef<HTMLDivElement>(null), alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { if (note || errors.length) summary.current?.focus(); }, [note, errors]);
  const canEdit = editable && !busy && !blocked;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canEdit || !identity.csrfToken) return;
    const problems = validateAutomationSettings(form);
    if (!reason.trim()) problems.push("Enter a reason for this change.");
    if (problems.length) { setErrors(problems); setNote(""); return; }
    setBusy(true); setErrors([]); setNote("");
    try {
      const saved = await saveAutomationSettings(policy.project_id, policy.version, form, reason, identity.csrfToken);
      if (!alive.current) return;
      setForm(saved.settings); setReason(""); setNote(`Automation settings saved. Version ${saved.version}. ${saved.settings.enabled ? "Execution is enabled under current permissions and evidence checks." : "New execution is disabled. History and reconciliation remain available; accepted external work may continue."}`);
      // Preserve the receipt until an explicit refresh; invalidate other scoped consumers.
      void queryClient.invalidateQueries({ predicate: (q) => !q.queryKey.includes("automation-settings") && !q.queryKey.includes("automation-settings-memberships") });
      setBlocked(true);
    } catch (error) {
      if (!alive.current) return;
      setErrors([message(error)]); setBlocked(true);
    } finally { if (alive.current) setBusy(false); }
  }
  async function reload() {
    if (busy) return;
    setBusy(true);
    try { await refresh(); if (alive.current) { setBlocked(false); setErrors([]); setNote("Current settings refreshed. Review the values before saving."); setForm(policy.settings); setReason(""); } }
    finally { if (alive.current) setBusy(false); }
  }
  return <form className="dw-phase6-stack" onSubmit={(event) => void submit(event)} noValidate>
    <p>Loaded policy version {policy.version}. Authorization epoch {policy.authorization_epoch}. Disabling execution invalidates pending authority while preserving reads and reconciliation.</p>
    {!editable && <p role="status">Sign in again to obtain mutation protection before saving.</p>}
    <fieldset disabled={!canEdit} className="dw-phase6-stack" style={{ border: 0, padding: 0, minWidth: 0 }}><legend>Execution and retention controls</legend>
      <label className="dw-toggle"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />Enable automation execution</label>
      <div className="dw-phase6-grid">{settingsFields.map(({ key, label, min, max }) => <label className="dw-field" key={key}><span id={`automation-label-${key}`}>{label}</span><input aria-labelledby={`automation-label-${key}`} aria-describedby={`automation-bound-${key}`} type="number" min={min} max={max} step={1} required value={Number.isNaN(form[key]) ? "" : form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value === "" ? NaN : Number(e.target.value) })} /><small id={`automation-bound-${key}`}>{min.toLocaleString()}–{max.toLocaleString()}</small></label>)}</div>
      <p>Approval and credential lifetimes must fit within evidence lifetime. Reductions below retained usage are rejected. Pending evidence and unknown external operations remain protected.</p>
      <label className="dw-field"><span>Change reason</span><input maxLength={256} required value={reason} onChange={(e) => setReason(e.target.value)} /></label>
    </fieldset>
    {(note || errors.length > 0) && <div ref={summary} tabIndex={-1} role={errors.length ? "alert" : "status"}>{note && <p>{note}</p>}{errors.length > 0 && <ul>{errors.map((error) => <li key={error}>{error}</li>)}</ul>}</div>}
    <div className="dw-phase6-actions"><Button type="submit" disabled={!canEdit} variant="primary-gradient">{busy ? "Saving…" : "Save automation settings"}</Button><Button disabled={busy} onClick={() => void reload()}>Refresh automation settings</Button></div>
    <Link to={`/infra-automation?project_id=${policy.project_id}&view=runs`}>Read run history and reconcile external work</Link>
  </form>;
}
function RegisteredTargets({ projectId, projectKey }: { projectId: number; projectKey: string }) {
  const identity = useIdentity();
  const [workspace, setWorkspace] = useState<number | null>(null), [selected, setSelected] = useState(""), [cursor, setCursor] = useState<string>();
  const workspaces = useQuery({ queryKey: ["automation-settings-workspaces", projectId, identity.epoch], queryFn: ({ signal }) => getWorkspaces(projectKey, signal), retry: false });
  const targets = useQuery({ queryKey: ["automation-settings-targets", projectId, workspace, cursor, identity.epoch], queryFn: ({ signal }) => getSettingsTargets(projectId, workspace!, cursor, signal), enabled: workspace !== null, retry: false });
  const target = useQuery({ queryKey: ["automation-settings-target", projectId, workspace, selected, identity.epoch], queryFn: ({ signal }) => getSettingsTarget(selected, projectId, workspace!, signal), enabled: workspace !== null && !!selected && !targets.isError, retry: false });
  const detail = !targets.isError && !target.isError && target.data;
  return <section className="dw-phase6-stack" aria-label="Registered automation targets"><h3>Registered targets</h3><p>Inspect operator-registered destinations. Receiver and provider credentials stay in protected operator configuration.</p>
    <label className="dw-field"><span>Target workspace</span><select value={workspace ?? ""} onChange={(e) => { setWorkspace(e.target.value ? Number(e.target.value) : null); setSelected(""); setCursor(undefined); }}><option value="">Choose a workspace</option>{workspaces.data?.map((w) => <option key={w.id} value={w.id}>{w.display_name}</option>)}</select></label>
    {workspaces.isError && <p role="alert">Workspaces are unavailable.</p>}
    {targets.isFetching && workspace && <p role="status">Loading registered targets…</p>}
    {targets.isError && <p role="alert">Target administration is unavailable for this scope. Global administrator and current project permissions are required.</p>}
    {workspace && targets.data && !targets.isError && <><label className="dw-field"><span>Registered target</span><select value={selected} onChange={(e) => setSelected(e.target.value)}><option value="">Choose a registered target</option>{targets.data.items.map((t) => <option value={t.id} key={t.id}>{t.id} · {t.environment} · {t.enabled ? "enabled" : "disabled"}</option>)}</select></label>{targets.data.items.length === 0 && <p>No registered targets in this workspace.</p>}{cursor && <Button onClick={() => { setCursor(undefined); setSelected(""); }}>First target page</Button>}{targets.data.cursor.next_cursor && <Button onClick={() => { setCursor(targets.data!.cursor.next_cursor!); setSelected(""); }}>Next target page</Button>}</>}
    {target.isError && <p role="alert">Target details are unavailable. Refresh the target list before continuing.</p>}
    {detail && <dl className="dw-account-configuration"><div><dt>Canonical target</dt><dd><MonoRef>{detail.definition.canonical_target}</MonoRef></dd></div><div><dt>Environment</dt><dd>{detail.definition.environment}</dd></div><div><dt>Receiver</dt><dd>{detail.definition.receiver_id}</dd></div><div><dt>Pinned workflow revision</dt><dd><MonoRef>{detail.definition.pipeline_workflow_revision}</MonoRef></dd></div><div><dt>Target state</dt><dd>{detail.definition.enabled ? "Enabled" : "Disabled"} · version {detail.version}</dd></div><div><dt>Lock state</dt><dd>{detail.lock?.status ?? "No retained lock"}</dd></div></dl>}
  </section>;
}
