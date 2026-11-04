import { Link } from "react-router-dom";
import { GitBranch } from "lucide-react";

export function AutomationNavItem({ projectId, active = false }: { projectId?: string | number; active?: boolean }) {
  const query = projectId ? `?${new URLSearchParams({ project_id: String(projectId) })}` : "";
  return <Link className={`dw-nav-item${active ? " dw-nav-item-active" : ""}`} to={`/infra-automation${query}`}><GitBranch color={active ? "var(--dw-brand)" : "var(--dw-faint)"} size={17} /><span>Automation</span></Link>;
}
