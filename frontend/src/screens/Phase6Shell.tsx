import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, History, LayoutGrid, Settings, ShieldCheck, Zap } from "lucide-react";

import { getProjects, type Project } from "../api/dashboard";
import { ProjectSwitcher, SkeletonLine, type ProjectOption } from "../components/ui";
import { useQuery } from "@tanstack/react-query";
import "./dashboard.css";

export function projectToOption(project: Project): ProjectOption {
  return {
    id: String(project.id),
    name: project.name || project.display_name || project.project_key,
    env: project.env_label || project.default_branch || "default",
    description: project.description || project.repository_url || project.project_key,
  };
}

export function useSelectedProject() {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const projects = projectsQuery.data ?? [];
  const projectOptions = useMemo(() => projects.map(projectToOption), [projects]);
  const selectedProject =
    projects.find((project) => String(project.id) === selectedProjectId) ?? projects[0];
  const selectedOption = selectedProject ? projectToOption(selectedProject) : undefined;

  return {
    projectsQuery,
    projects,
    projectOptions,
    selectedProject,
    selectedOption,
    setSelectedProject(option: ProjectOption) {
      setSelectedProjectId(option.id);
    },
  };
}

function Sidebar({ active, selectedProject }: { active: string; selectedProject?: ProjectOption }) {
  const nav = [
    { label: "Dashboard", icon: LayoutGrid, href: "/", key: "dashboard" },
    { label: "Skills", icon: Zap, href: "/skills", key: "skills" },
    { label: "Incidents", icon: AlertTriangle, href: "/incidents", key: "incidents" },
    { label: "History", icon: History, href: "/history", key: "history" },
    { label: "Settings", icon: Settings, href: "/settings", key: "settings" },
  ];

  return (
    <aside className="dw-sidebar">
      <div className="dw-brand">
        <span className="dw-brand-tile">
          <ShieldCheck size={18} />
        </span>
        <div>
          <div className="dw-brand-wordmark">
            Deploy<span>Whisper</span>
          </div>
          <div className="dw-brand-eyebrow">Evidence Engine</div>
        </div>
      </div>
      <nav className="dw-sidebar-nav" aria-label="Primary">
        {nav.map(({ label, icon: Icon, href, key }) => {
          const isActive = active === key;
          return (
            <Link key={key} className={`dw-nav-item${isActive ? " dw-nav-item-active" : ""}`} to={href}>
              <Icon color={isActive ? "var(--dw-brand)" : "var(--dw-faint)"} size={17} />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="dw-active-project-card">
        <div className="dw-active-project-inner">
          <div className="dw-active-project-row">
            <span className="dw-active-dot" />
            Active Project
          </div>
          {selectedProject ? (
            <>
              <div className="dw-active-project-name">{selectedProject.name}</div>
              <div className="dw-active-project-env">{selectedProject.env}</div>
            </>
          ) : (
            <SkeletonLine width="80%" />
          )}
          <div className="dw-active-project-chip">
            <ShieldCheck size={11} />
            Evidence Law enforced
          </div>
        </div>
      </div>
    </aside>
  );
}

function TopBar({
  projects,
  selectedProject,
  onProjectChange,
}: {
  projects: ProjectOption[];
  selectedProject?: ProjectOption;
  onProjectChange: (project: ProjectOption) => void;
}) {
  return (
    <header className="dw-topbar">
      <div className="dw-global-search" aria-label="Global search">
        <span>Search analyses, services...</span>
      </div>
      <div className="dw-topbar-spacer" />
      {selectedProject && (
        <ProjectSwitcher
          onChange={onProjectChange}
          projects={projects}
          selectedProject={selectedProject}
        />
      )}
      <span className="dw-topbar-divider" />
      <div className="dw-avatar">DW</div>
    </header>
  );
}

export function Phase6Shell({
  active,
  children,
}: {
  active: "settings" | "incidents" | "skills";
  children: (context: ReturnType<typeof useSelectedProject>) => ReactNode;
}) {
  const projectContext = useSelectedProject();

  return (
    <div className="dw-app-shell dw-phase6-shell dw-ui">
      <Sidebar active={active} selectedProject={projectContext.selectedOption} />
      <main className="dw-main">
        <TopBar
          onProjectChange={projectContext.setSelectedProject}
          projects={projectContext.projectOptions}
          selectedProject={projectContext.selectedOption}
        />
        {children(projectContext)}
      </main>
    </div>
  );
}
