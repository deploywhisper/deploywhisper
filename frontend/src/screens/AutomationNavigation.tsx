import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { GitBranch } from "lucide-react";
import { getProjects } from "../api/dashboard";
import { getCapabilities, getWorkspaces } from "../api/infraAutomation";
import { useIdentity } from "./IdentitySession";

export function AutomationNavItem({ projectId, active = false }: { projectId?: string | number; active?: boolean }) {
  const identity = useIdentity();
  const projects = useQuery({ queryKey: ["projects", identity.epoch], queryFn: getProjects, enabled: Boolean(identity.principal) });
  const project = projects.data?.find((item) => String(item.id) === String(projectId));
  const workspaces = useQuery({ queryKey: ["automation", "workspaces", identity.epoch, project?.id], queryFn: ({ signal }) => getWorkspaces(project!.project_key, signal), enabled: Boolean(identity.principal && project), retry: false, gcTime: 0 });
  const workspaceId = workspaces.data?.[0]?.id ?? null;
  const capabilities = useQuery({ queryKey: ["automation", "capabilities", identity.epoch, project?.id, workspaceId], queryFn: ({ signal }) => getCapabilities({ projectId: project!.id, workspaceId }, signal), enabled: Boolean(identity.principal && project && workspaces.isSuccess), retry: false, gcTime: 0 });
  if (!identity.principal || capabilities.isError || !capabilities.data?.execution_enabled) return null;
  return <Link className={`dw-nav-item${active ? " dw-nav-item-active" : ""}`} to={`/infra-automation?project_id=${project!.id}${workspaceId === null ? "" : `&workspace_id=${workspaceId}`}`}><GitBranch color={active ? "var(--dw-brand)" : "var(--dw-faint)"} size={17} /><span>Automation</span></Link>;
}
