import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import type { Project } from "../api/dashboard";
import { ApiClientError } from "../api/client";
import { getCapabilities, getWorkspaces, type AutomationScope, type Capabilities, type Workspace } from "../api/infraAutomation";
import { Button, SkeletonLine } from "../components/ui";
import { useIdentity } from "./IdentitySession";
import { Phase6Shell, type ShellProjectContext } from "./Phase6Shell";
import { projectToOption } from "./projectSelection";
import "./infra-automation.css";

export interface AutomationContext {
  scope: AutomationScope;
  project: Project;
  workspace: Workspace | null;
  capabilities: Capabilities;
  fresh: boolean;
  identity: ReturnType<typeof useIdentity>;
  refresh: () => Promise<unknown>;
  ensureFresh: () => Promise<Capabilities>;
  selectProject: (id: number) => void;
  selectWorkspace: (id: number | null) => void;
}

export function scopeQuery(scope: AutomationScope): string {
  const params = new URLSearchParams({ project_id: String(scope.projectId) });
  if (scope.workspaceId !== null) params.set("workspace_id", String(scope.workspaceId));
  return `?${params}`;
}

export function initialWorkspaceSelection(projectId: number, params: URLSearchParams): number | null | undefined {
  if (params.get("project_id") !== String(projectId)) return undefined;
  return params.has("workspace_id") ? Number(params.get("workspace_id")) : null;
}

export function automationError(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.status === 401) return "Your session expired or was revoked. Sign in again.";
    if (error.status === 403) return "This operation or scope is unavailable for your account.";
    if (error.status === 409) return "Current state changed. Reload server state and review again before continuing.";
    if (error.status === 422) return "The request or response is unsupported. Validate the current definition and inputs.";
    if (error.status === 429) return "A request or storage limit was reached. Review the current state before trying again.";
  }
  return "The connection or current authority could not be verified. Refresh before making changes.";
}

export function AccountLink({ children = "Sign in again" }: { children?: ReactNode }) {
  const location = useLocation();
  return <Link to={`/settings/account?returnTo=${encodeURIComponent(location.pathname + location.search)}`}>{children}</Link>;
}

function ScopeWorkspace({ shell, project, children }: { shell: ShellProjectContext; project: Project; children: (context: AutomationContext) => ReactNode }) {
  const identity = useIdentity();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const [chosen, setChosen] = useState<number | null | undefined>(() => initialWorkspaceSelection(project.id, params));
  const routeWorkspace = params.get("workspace_id");
  const lastRouteWorkspace = useRef<string | null | undefined>(undefined);
  const routeChanged = lastRouteWorkspace.current !== routeWorkspace;
  const effectiveChosen = routeChanged ? initialWorkspaceSelection(project.id, params) : chosen;
  const [online, setOnline] = useState(() => typeof navigator === "undefined" || navigator.onLine);
  const workspaces = useQuery({ queryKey: ["automation", "workspaces", identity.epoch, project.id], queryFn: ({ signal }) => getWorkspaces(project.project_key, signal), retry: false, gcTime: 0 });
  const workspaceId = effectiveChosen === undefined ? workspaces.data?.[0]?.id ?? null : effectiveChosen;
  const scope = { projectId: project.id, workspaceId };
  const key = `${identity.epoch}:${project.id}:${workspaceId}`;
  const active = useRef(key);
  active.current = key;
  const capabilities = useQuery({ queryKey: ["automation", "capabilities", identity.epoch, project.id, workspaceId], queryFn: ({ signal }) => getCapabilities(scope, signal), enabled: workspaces.isSuccess, retry: false, gcTime: 0, refetchOnWindowFocus: true });
  // Probe only an authorized read; a denial never becomes project-wide authority.
  const projectCapabilities = useQuery({ queryKey: ["automation", "project-capabilities", identity.epoch, project.id], queryFn: ({ signal }) => getCapabilities({ projectId: project.id, workspaceId: null }, signal), enabled: workspaces.isSuccess, retry: false, gcTime: 0 });
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update); window.addEventListener("offline", update);
    return () => { active.current = "disposed"; window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);
  useEffect(() => {
    if (!routeChanged) return;
    lastRouteWorkspace.current = routeWorkspace;
    setChosen(initialWorkspaceSelection(project.id, params));
  }, [routeChanged, routeWorkspace, project.id, params]);
  useEffect(() => {
    if (routeChanged) return;
    if (!workspaces.isSuccess) return;
    const next = new URLSearchParams(params);
    next.set("project_id", String(project.id));
    if (workspaceId === null) next.delete("workspace_id"); else next.set("workspace_id", String(workspaceId));
    if (next.toString() !== params.toString()) {
      const initialSelection = chosen === undefined && params.get("project_id") === String(project.id);
      setParams(next, { replace: params.get("project_id") === null || initialSelection });
    }
  }, [project.id, workspaceId, workspaces.isSuccess, params, setParams, routeChanged, chosen]);
  const fresh = online && !identity.loading && identity.status === "ready" && capabilities.isSuccess && !capabilities.isFetching && !capabilities.isError;
  async function refreshAccess() {
    const expected = key;
    if (!online || identity.loading) throw new ApiClientError("Fresh account verification required.", 503);
    const verified = await identity.refresh();
    if (!verified || verified.principal_id !== identity.principal?.principal_id || verified.session_id !== identity.principal?.session_id) throw new ApiClientError("Fresh account verification required.", 503);
    const result = await capabilities.refetch();
    if (result.error || !result.data) throw result.error ?? new ApiClientError("Access unavailable.", 503);
    const value = result.data;
    if (active.current !== expected) throw new ApiClientError("Scope changed.", 409);
    return value;
  }
  async function ensureFresh() {
    if (!identity.csrfToken) throw new ApiClientError("Fresh sign-in required.", 403);
    return refreshAccess();
  }
  const selectedWorkspace = workspaces.data?.find((workspace) => workspace.id === workspaceId) ?? null;
  const inaccessible = [workspaces.error, capabilities.error].some((error) => error instanceof ApiClientError && [401, 403].includes(error.status));
  const context: AutomationContext | undefined = capabilities.data && !inaccessible ? {
    scope, project, workspace: selectedWorkspace, capabilities: capabilities.data, fresh, identity,
    refresh: refreshAccess, ensureFresh,
    selectProject: (id) => { const value = shell.projects.find((candidate) => candidate.id === id); if (value) shell.setSelectedProject(projectToOption(value)); },
    selectWorkspace: (id) => { if (id === null ? projectCapabilities.isSuccess : workspaces.data?.some((workspace) => workspace.id === id)) setChosen(id); },
  } : undefined;
  return <div className="dw-automation">
    <div className="dw-automation-heading"><div><p className="dw-automation-eyebrow">Project workspace</p><h1>Infrastructure Automation</h1><p>Review published workflows, preflight evidence and human decisions.</p></div><Link to="/settings/account">{identity.principal?.username} · Account</Link></div>
    <div className="dw-automation-scope">
      <label className="dw-field" htmlFor="automation-workspace"><span>Workspace</span><select id="automation-workspace" disabled={!workspaces.isSuccess} value={workspaceId ?? "project"} onChange={(event) => setChosen(event.target.value === "project" ? null : Number(event.target.value))}>
        {projectCapabilities.isSuccess && <option value="project">Project-wide authoring and history</option>}
        {workspaces.data?.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.display_name}</option>)}
      </select></label>
      <span>Project: {project.display_name}</span>
      <Button disabled={capabilities.isFetching || !online} onClick={() => { void refreshAccess().catch(() => undefined); }}>Refresh access</Button>
    </div>
    {workspaces.isLoading || capabilities.isLoading ? <div role="status"><SkeletonLine />Loading current scope and permissions…</div> : null}
    {workspaces.isError || capabilities.isError ? <div className="dw-automation-notice" role="alert">{automationError(workspaces.error ?? capabilities.error)} <AccountLink /></div> : null}
    {!online && <p className="dw-automation-notice" role="alert">Connection lost. Same-scope edits stay in this page; consequential controls are disabled until access is refreshed.</p>}
    {identity.status === "unavailable" && identity.principal && <p className="dw-automation-notice" role="alert">Current account access could not be verified. Your same-scope edits are retained; refresh access before making changes.</p>}
    {context && !context.capabilities.execution_enabled && <p className="dw-automation-notice" role="status">Automation execution is disabled for this project. Authorized workflow and run history remain available; new runs cannot start. Contact your project administrator about enablement.</p>}
    {context && !identity.csrfToken && <p className="dw-automation-notice">This restored session permits reading. <AccountLink /> before making changes or submitting a decision.</p>}
    {context && <nav className="dw-automation-actions dw-automation-nav" aria-label="Automation sections">
      <Link to={`/infra-automation${scopeQuery(scope)}`} aria-current={location.pathname === "/infra-automation/approvals" || params.has("approval_id") ? undefined : "page"}>Workflows and runs</Link>
      <Link to={`/infra-automation/approvals${scopeQuery(scope)}`} aria-current={location.pathname === "/infra-automation/approvals" || params.has("approval_id") ? "page" : undefined}>Approvals</Link>
    </nav>}
    {context && children(context)}
  </div>;
}

function ProjectScope({ shell, children }: { shell: ShellProjectContext; children: (context: AutomationContext) => ReactNode }) {
  const [params] = useSearchParams();
  const routeProject = params.get("project_id");
  const lastRouteProject = useRef<string | null | undefined>(undefined);
  const routeChanged = lastRouteProject.current !== routeProject;
  const target = Number(routeProject);
  const requested = shell.projects.find((project) => project.id === target);
  useEffect(() => {
    if (!shell.projectsQuery.isSuccess || !routeChanged) return;
    lastRouteProject.current = routeProject;
    if (requested && requested.id !== shell.selectedProject?.id) shell.setSelectedProject(projectToOption(requested));
  }, [requested, shell, routeChanged, routeProject]);
  if (shell.projectsQuery.isLoading || (routeChanged && requested && requested.id !== shell.selectedProject?.id)) return <p role="status">Loading authorized project…</p>;
  if (shell.projectsQuery.isError) return <p role="alert">Project access could not be verified.</p>;
  if (routeProject !== null && !requested) return <div role="alert"><p>This project or operation is unavailable for your account.</p><Link to="/infra-automation">Open an authorized project workspace</Link></div>;
  if (!shell.selectedProject) return <div className="dw-automation"><h1>No permitted projects</h1><p>Ask your project administrator for project membership.</p></div>;
  return <ScopeWorkspace key={shell.selectedProject.id} shell={shell} project={shell.selectedProject}>{children}</ScopeWorkspace>;
}

export function AutomationFrame({ children }: { children: (context: AutomationContext) => ReactNode }) {
  const identity = useIdentity();
  return <Phase6Shell key={identity.epoch} active="automation">{(shell) => {
    if (identity.loading) return <div className="dw-automation" role="status">Checking your verified account…</div>;
    if (!identity.principal) return <div className="dw-automation"><h1>Account access required</h1><p>{identity.error || "Sign in with your named local account to open permitted project workflows."}</p><AccountLink>Sign in</AccountLink></div>;
    return <ProjectScope shell={shell}>{children}</ProjectScope>;
  }}</Phase6Shell>;
}
