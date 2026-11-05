import { useEffect, useRef, useState, useSyncExternalStore, type Ref } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiClientError } from "../api/client";
import { enrollRunner, getRunnerCapabilities, getRunnerHealth, revokeRunner, rotateRunner, type RunnerCapabilities, type RunnerHealth, type EnrollmentReveal } from "../api/infraAutomationRunners";
import { Button, Card, SkeletonLine } from "../components/ui";
import { runnerMutationStore, type RunnerMutationMarker } from "./runnerMutationState";
import { AutomationFrame, automationError, scopeQuery, type AutomationContext } from "./InfraAutomationShared";

export type RunnerSecret = { key: string; kind: "enrollment" | "credential"; runnerId: string; token: string; expiresAt: string; monotonicDeadline: number; enrollment?: EnrollmentReveal["enrollment"] };
export function runnerAccessKey(context: AutomationContext): string {
  return JSON.stringify([context.identity.epoch, context.identity.principal?.principal_id, context.identity.principal?.session_id, context.scope.projectId, context.scope.workspaceId, context.capabilities.membership_version]);
}
export function runnerMutationKey(context: AutomationContext): string {
  // A refresh of local access metadata cannot settle a previous server effect.
  return JSON.stringify([context.identity.principal?.principal_id, context.identity.principal?.session_id, context.scope.projectId, context.scope.workspaceId]);
}
export function runnerSecretDeadline(expiresAt: string, evaluatedAt: string, readStarted: number, monotonicNow: number): number | null {
  const serverWindow = Date.parse(expiresAt) - Date.parse(evaluatedAt);
  const elapsed = monotonicNow - readStarted;
  // Capture before the authority read: round-trip and issuance time consume the
  // window. Server timestamps have second precision, so expire one second early.
  const remaining = serverWindow - elapsed - 1000;
  if (![serverWindow, readStarted, monotonicNow, remaining].every(Number.isFinite) || readStarted < 0 || elapsed < 0 || remaining <= 0 || remaining > 3_600_000) return null;
  return monotonicNow + remaining;
}
export function visibleRunnerSecret(secret: RunnerSecret | null, key: string, fresh: boolean, monotonicNow: number, wallNow: number): RunnerSecret | null {
  return secret && secret.key === key && fresh && monotonicNow < secret.monotonicDeadline && wallNow < Date.parse(secret.expiresAt) ? secret : null;
}
export function parseRunnerTags(value: string): string[] | null {
  if (!value.trim()) return [];
  const tags = value.split(",").map((tag) => tag.trim());
  return tags.length <= 16 && tags.every((tag) => /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(tag)) && new Set(tags).size === tags.length ? tags : null;
}
const reasonValid = (value: string) => value.trim().length > 0 && value.length <= 256 && !/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/.test(value);
const stamp = (value: string | null) => value ? value.replace("T", " ").replace("Z", " UTC") : "Not recorded";
function restriction(value: RunnerCapabilities): string | null {
  if (value.restriction === "https_required") return "Runner health and credential administration require the HTTPS identity profile. This local HTTP session cannot manage runner credentials. Open the operator-configured HTTPS application.";
  if (value.restriction === "privileged_role_required") return "Runner health requires a project administrator or maintainer. Ask your project administrator for the appropriate access.";
  if (value.restriction === "administrator_required") return "You can inspect runner health. Enrollment, rotation and revocation require a project administrator.";
  if (value.restriction === "execution_disabled") return "Collection execution is disabled. Enrollment and rotation are unavailable; administrators may still revoke credentials.";
  return null;
}

export function RunnerPanel({ context }: { context: AutomationContext }) {
  const queryClient = useQueryClient();
  const key = runnerAccessKey(context), mutationKey = runnerMutationKey(context), queryKey = ["automation", "runners", key];
  const [cursor, setCursor] = useState<string>();
  const [profileDigest, setProfileDigest] = useState("");
  const [runnerTags, setRunnerTags] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [secret, setSecret] = useState<RunnerSecret | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mutations = useSyncExternalStore(runnerMutationStore.subscribe, () => runnerMutationStore.read(mutationKey), () => runnerMutationStore.read(mutationKey));
  const uncertain = !!mutations.issuance;
  const identityKey = JSON.stringify([context.identity.principal?.principal_id, context.identity.principal?.session_id]);
  const generation = useRef(0), active = useRef(key), latest = useRef(context);
  active.current = key; latest.current = context;
  const noticeRef = useRef<HTMLDivElement>(null), secretRef = useRef<HTMLDivElement>(null);
  const capabilities = useQuery({ queryKey: [...queryKey, "capabilities"], queryFn: ({ signal }) => getRunnerCapabilities(context.scope, signal), enabled: context.scope.workspaceId !== null, retry: false, gcTime: 0, refetchInterval: 10_000, refetchOnWindowFocus: true });
  const allowed = capabilities.isSuccess && !capabilities.isError && capabilities.data.can_read_health;
  const health = useQuery({ queryKey: [...queryKey, "health", cursor], queryFn: ({ signal }) => getRunnerHealth(context.scope, cursor, signal), enabled: allowed, retry: false, gcTime: 0, refetchInterval: 10_000 });
  const cap = capabilities.isSuccess && !capabilities.isError ? capabilities.data : undefined;
  const denied = [capabilities.error, health.error].some((value) => value instanceof ApiClientError && [401, 403].includes(value.status));
  const fresh = context.fresh && !!cap && !denied && !capabilities.isError && !health.isError;
  const currentAuthority = useRef({ fresh, key });
  currentAuthority.current = { fresh, key };
  const mayManage = fresh && !!context.identity.csrfToken && !!cap?.production_eligible;
  const visible = visibleRunnerSecret(secret, key, fresh && !!(cap?.can_enroll || cap?.can_rotate), typeof performance === "undefined" ? 0 : performance.now(), Date.now());
  const profiles = cap?.configured_profiles ?? [];
  const profile = profiles.find((item) => item.profile_digest === profileDigest) ?? profiles[0];
  const parsedTags = parseRunnerTags(runnerTags ?? profile?.tags.join(", ") ?? "");
  const actionReady = mayManage && !busy && reasonValid(reason);
  const rows = allowed && !denied ? health.data?.items : undefined;

  useEffect(() => () => { active.current = "disposed"; generation.current += 1; runnerMutationStore.clearReveal(mutationKey); }, [key]);
  useEffect(() => { runnerMutationStore.pruneSettledOtherIdentities(identityKey); }, [identityKey]);
  useEffect(() => {
    if (!fresh || !cap || (!cap.can_enroll && !cap.can_rotate)) { setSecret(null); runnerMutationStore.clearReveal(mutationKey); }
    if (context.identity.status !== "ready" || (cap && !cap.can_enroll && !cap.can_rotate && !cap.can_revoke)) { generation.current += 1; setBusy(null); }
  }, [fresh, cap?.can_enroll, cap?.can_rotate, cap?.can_revoke, context.identity.status, key]);
  useEffect(() => {
    if (!secret) return;
    const clearExpired = () => { if (!visibleRunnerSecret(secret, active.current, true, performance.now(), Date.now())) { setSecret(null); runnerMutationStore.clearReveal(mutationKey); } };
    const delay = Math.max(1, Math.min(secret.monotonicDeadline - performance.now(), Date.parse(secret.expiresAt) - Date.now()));
    const timer = window.setTimeout(() => { setSecret(null); runnerMutationStore.clearReveal(mutationKey); }, delay);
    document.addEventListener("visibilitychange", clearExpired);
    window.addEventListener("focus", clearExpired);
    return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", clearExpired); window.removeEventListener("focus", clearExpired); };
  }, [secret]);
  useEffect(() => { if (secret && visible) secretRef.current?.focus(); }, [secret]);
  useEffect(() => { if (error || notice) noticeRef.current?.focus(); }, [error, notice]);

  async function perform(action: "enroll" | "rotate" | "revoke", target?: RunnerHealth) {
    if (!actionReady || !cap || (uncertain && action !== "revoke") || (action === "enroll" && (!profile || parsedTags === null))) return;
    const operation = ++generation.current, expected = key;
    const requestedReason = reason, selectedProfile = profile, selectedTags = parsedTags ?? [];
    setSecret(null); runnerMutationStore.clearReveal(mutationKey); setError(null); setNotice(null); setBusy(action === "enroll" ? "enroll" : `${action}:${target?.id}`);
    let submitted = false;
    let marker: RunnerMutationMarker | null = null;
    try {
      await context.ensureFresh();
      const capabilityReadStarted = performance.now();
      const current = await getRunnerCapabilities(context.scope);
      if (active.current !== expected || generation.current !== operation || latest.current.identity.status !== "ready") return;
      queryClient.setQueryData([...queryKey, "capabilities"], current);
      if (!(action === "enroll" ? current.can_enroll : action === "rotate" ? current.can_rotate : current.can_revoke)) throw new ApiClientError("Runner administration unavailable.", 403);
      if (action === "enroll" && !current.configured_profiles.some((item) => item.profile_digest === selectedProfile?.profile_digest && item.tool === selectedProfile.tool && item.tool_version === selectedProfile.tool_version && item.runner_version === selectedProfile.runner_version)) throw new ApiClientError("Collection profile changed.", 409);
      marker = runnerMutationStore.begin(identityKey, mutationKey, action, target?.id);
      if (!marker) throw new ApiClientError("A runner administration request remains unresolved. Review current registrations before another request.", 409);
      submitted = true;
      if (action === "revoke" && target) {
        await revokeRunner(target.id, requestedReason, context.identity.csrfToken!);
        runnerMutationStore.verified(marker, { kind: "revoked", runnerId: target.id });
        if (active.current !== expected || generation.current !== operation) return;
        setNotice("Runner credential revoked. This does not confirm that previously accepted external work has stopped.");
      } else {
        const result = action === "enroll" ? await enrollRunner(context.scope, selectedProfile!, selectedTags, requestedReason, context.identity.csrfToken!) : await rotateRunner(target!.id, requestedReason, context.identity.csrfToken!);
        const enrollment = "enrollment" in result ? result.enrollment : null;
        const expiresAt = enrollment ? enrollment.expires_at : (result as { expires_at: string }).expires_at;
        const runnerId = enrollment?.runner_id ?? target!.id;
        const monotonicDeadline = runnerSecretDeadline(expiresAt, current.evaluated_at, capabilityReadStarted, performance.now());
        const stillCurrent = active.current === expected && generation.current === operation;
        const mayReveal = stillCurrent && latest.current.identity.status === "ready" && currentAuthority.current.fresh && monotonicDeadline !== null;
        const revealed: RunnerSecret | null = monotonicDeadline === null ? null : { key: expected, kind: enrollment ? "enrollment" : "credential", runnerId, token: result.token, expiresAt, monotonicDeadline, ...(enrollment ? { enrollment } : {}) };
        const display = mayReveal ? visibleRunnerSecret(revealed, expected, true, performance.now(), Date.now()) : null;
        runnerMutationStore.verified(marker, { kind: "issued", runnerId, credentialCleared: !display });
        if (!stillCurrent) return;
        if (!display) {
          setError("The credential was issued but its secret was cleared because current access or expiry could not be verified. Review the recorded runner before reissuing.");
          return;
        }
        setSecret(display);
      }
      setReason(""); void health.refetch().catch(() => undefined);
    } catch (failure) {
      const ambiguous = submitted && (!(failure instanceof ApiClientError) || ![400, 401, 403, 404, 409, 422, 429].includes(failure.status));
      if (marker) {
        if (ambiguous) runnerMutationStore.unknown(marker);
        else runnerMutationStore.verified(marker, { kind: "rejected", runnerId: target?.id });
      }
      if (active.current !== expected || generation.current !== operation) return;
      if (ambiguous) { setError("The credential request outcome is unknown. It will not be retried. Review current runner registrations and ask an administrator to revoke uncertain authority before issuing new credentials."); }
      else setError(automationError(failure));
      setSecret(null);
    } finally { if (active.current === expected && generation.current === operation) setBusy(null); }
  }

  function closeSecret() { generation.current += 1; setSecret(null); runnerMutationStore.clearReveal(mutationKey); setNotice("Secret closed and cleared. It cannot be revealed again; revoke uncertain authority before reissuing."); }
  if (context.scope.workspaceId === null) return <Card title="Runner health"><p>Select a concrete workspace to view or administer its runners.</p></Card>;
  return <div className="dw-automation-stack dw-automation-run">
    <Card title="Runner health" eyebrow="Collection infrastructure" right={<Button disabled={capabilities.isFetching || !!busy} onClick={() => { void Promise.all([context.refresh(), capabilities.refetch(), ...(allowed ? [health.refetch()] : [])]).catch(() => undefined); }}>Refresh runner health</Button>}>
      <p>Health does not certify isolation or trustworthy evidence. Connectivity, credential validity and the configured collection profile are separate facts.</p>
      {(error || notice) && <div ref={noticeRef} tabIndex={-1} className={`dw-automation-error-summary${error ? "" : " dw-automation-success"}`} role={error ? "alert" : "status"}>{error ?? notice}</div>}
      {allowed && !denied && mutations.outcome && <p className="dw-automation-notice" role="status">{mutations.outcome.kind === "issued" ? `Credential issuance completed for ${mutations.outcome.runnerId}. ${mutations.outcome.credentialCleared ? "The one-time secret was cleared and is not retained. Review or revoke this runner before deliberately issuing another credential." : "The credential is shown only in the current one-time view."}` : mutations.outcome.kind === "revoked" ? `Revocation confirmed for ${mutations.outcome.runnerId}.` : "The runner administration request was rejected; no retry was sent."}</p>}
      {!context.fresh && <p className="dw-automation-notice">Current authority is unavailable. Refresh access before managing runners.</p>}
      {capabilities.isLoading && <div role="status"><SkeletonLine />Loading runner permissions…</div>}
      {capabilities.isError && <p className="dw-automation-notice" role="alert">{automationError(capabilities.error)}</p>}
      {cap && restriction(cap) && <p className="dw-automation-notice">{restriction(cap)}</p>}
      {allowed && health.isLoading && <div role="status"><SkeletonLine />Loading runner health…</div>}
      {allowed && health.isError && <p className="dw-automation-notice" role="alert">{automationError(health.error)} Retained same-scope health, if shown, is not current authority.</p>}
      {rows && rows.length === 0 && <p>No runners registered in this workspace. An administrator can issue enrollment for an operator-installed collection profile.</p>}
      {rows && rows.length > 0 && <div className="dw-automation-table-wrap" role="region" aria-label="Runner health table" tabIndex={0}><table><caption>Server-observed connectivity and configuration for this workspace. Online means a heartbeat within 60 seconds; stale is up to 180 seconds.</caption><thead><tr><th scope="col">Runner and connection</th><th scope="col">Versions and profile</th><th scope="col">Active attempt</th><th scope="col">Administration</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><strong>{row.id}</strong><p><span className="dw-automation-status">{row.connectivity}</span> · Registration {row.status}</p><p>Last heartbeat: {stamp(row.last_seen_at)}<br />{row.heartbeat_age_seconds === null ? "Heartbeat age unavailable" : `${row.heartbeat_age_seconds} seconds at evaluation`}<br />Observed: {stamp(row.evaluated_at)}</p>{row.connectivity_reason === "clock_unavailable" && <p>Clock observation unavailable; check the runner and server clocks.</p>}</td><td>{row.tool} {row.tool_version ?? "Version unavailable"}<br />Runner {row.runner_version} · Protocol {row.protocol_version}<br /><span>Profile {row.profile_status.replaceAll("_", " ")}</span><details><summary>Profile digest and tags</summary><code>{row.profile_digest}</code><p>Tags: {row.tags.join(", ") || "None"}</p></details><p>Credential {row.credential_status}<br />Expires: {stamp(row.credential_expires_at)}</p></td><td>{row.current_task ? <><Link to={`/infra-automation/runs/${encodeURIComponent(row.current_task.run_id)}${scopeQuery(context.scope)}`}>Open active run</Link><p>Step {row.current_task.step_id}<br />Attempt {row.current_task.attempt_id}</p></> : "No active attempt"}</td><td><Button disabled={!actionReady || uncertain || !cap?.can_rotate || row.status === "revoked"} onClick={() => void perform("rotate", row)}>Rotate credential for {row.id}</Button><Button disabled={!actionReady || !!mutations.revocation || !cap?.can_revoke || row.status === "revoked"} onClick={() => void perform("revoke", row)}>Revoke runner {row.id}</Button></td></tr>)}</tbody></table></div>}
      {rows && health.data && <div className="dw-automation-actions">{(health.data.cursor.gap || health.data.cursor.truncated) && <span>Health listing is incomplete. Refresh or load the next page.</span>}<Button disabled={!cursor || health.isFetching} onClick={() => setCursor(undefined)}>First page</Button><Button disabled={!health.data.cursor.next_cursor || health.isFetching} onClick={() => setCursor(health.data?.cursor.next_cursor ?? undefined)}>Next page</Button></div>}
    </Card>
    {cap?.production_eligible && (cap.can_enroll || cap.can_rotate || cap.can_revoke) && <Card title="Runner administration">
      <p>Planning can execute repository and provider code. Use an approved source and an isolated runner with limited credentials.</p>
      <form className="dw-automation-form" onSubmit={(event) => { event.preventDefault(); void perform("enroll"); }}>
        <label className="dw-field" htmlFor="runner-admin-reason"><span>Administration reason</span><input id="runner-admin-reason" maxLength={256} value={reason} onChange={(event) => setReason(event.target.value)} disabled={!!busy} autoComplete="off" /></label>
        {cap.can_enroll && <><label className="dw-field" htmlFor="runner-profile"><span>Configured collection profile</span><select id="runner-profile" value={profile?.profile_digest ?? ""} disabled={!mayManage || !!busy || !profiles.length} onChange={(event) => { setProfileDigest(event.target.value); setRunnerTags(null); }}>{!profiles.length && <option value="">No configured profiles</option>}{profiles.map((item) => <option key={item.profile_digest} value={item.profile_digest}>{item.tool} {item.tool_version} · {item.profile_digest}</option>)}</select></label><label className="dw-field" htmlFor="runner-tags"><span>Runner tags (comma separated)</span><input id="runner-tags" maxLength={2063} value={runnerTags ?? profile?.tags.join(", ") ?? ""} onChange={(event) => setRunnerTags(event.target.value)} disabled={!!busy} autoComplete="off" /></label>{parsedTags === null && <p role="alert">Use at most 16 distinct identifier tags, separated by commas.</p>}<Button type="submit" variant="primary-gradient" disabled={!actionReady || uncertain || !profile || parsedTags === null}>Issue enrollment</Button></>}
        {cap.profile_status !== "available" && <p className="dw-automation-notice">Configured collection profiles are {cap.profile_status.replaceAll("_", " ")}. Ask the operator to install and verify the protected profile manifest before enrollment.</p>}
      </form>
      {busy && <p role="status">Submitting runner administration request…</p>}
      {(uncertain || mutations.revocation) && <p className="dw-automation-notice">No automatic resend is available. Refresh health and revoke uncertain credentials. Unresolved enrollment or rotation remains blocked across same-session navigation until its outcome is verified. A fresh health read alone does not resolve an uncertain request.</p>}
    </Card>}
    <RunnerSecretPanel secret={visible} onClose={closeSecret} revealRef={secretRef} />
  </div>;
}

export function RunnerSecretPanel({ secret, onClose, revealRef }: { secret: RunnerSecret | null; onClose: () => void; revealRef?: Ref<HTMLDivElement> }) {
  if (!secret) return null;
  return <Card title="One-time credential reveal"><div ref={revealRef} tabIndex={-1} role="region" aria-label="One-time runner secret"><p>This {secret.kind === "enrollment" ? "enrollment token" : "runner credential"} is shown once for runner {secret.runnerId}. It is cleared when closed, expired, or account/scope access changes.</p>
    {secret.enrollment && <label className="dw-field" htmlFor="runner-enrollment-json"><span>Enrollment JSON</span><textarea id="runner-enrollment-json" readOnly rows={8} value={JSON.stringify(secret.enrollment, null, 2)} autoComplete="off" spellCheck={false} /></label>}
    <label className="dw-field" htmlFor="runner-secret"><span>{secret.kind === "enrollment" ? "One-time enrollment token" : "One-time runner credential"}</span><input id="runner-secret" readOnly value={secret.token} autoComplete="off" spellCheck={false} /></label>
    {secret.enrollment && <p>Your operator needs both Enrollment JSON and the separate token for runner enrollment. Store them only in owner-restricted local files on the runner host.</p>}
    <p>Expires: {stamp(secret.expiresAt)}. Copy only deliberately into the operator-owned runner setup; clipboard history may retain copied values.</p><Button onClick={onClose}>Close and clear secret</Button></div></Card>;
}

export function InfraAutomationRunnersScreen() {
  return <AutomationFrame>{(context) => <RunnerPanel key={runnerAccessKey(context)} context={context} />}</AutomationFrame>;
}
