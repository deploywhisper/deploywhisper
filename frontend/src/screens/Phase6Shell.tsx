import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, History, LayoutGrid, Search, Settings, ShieldCheck, Zap } from "lucide-react";

import { getProjects } from "../api/dashboard";
import { ProjectSwitcher, SkeletonLine, type ProjectOption } from "../components/ui";
import { useQuery } from "@tanstack/react-query";
import { AppBrand } from "./AppBrand";
import { projectToOption, usePersistentProjectSelection } from "./projectSelection";
import "./dashboard.css";

export type ShellProjectContext = ReturnType<typeof useSelectedProject> & {
  selectedOption?: ProjectOption;
};

export function useSelectedProject() {
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const projects = projectsQuery.data ?? [];
  const projectOptions = useMemo(() => projects.map(projectToOption), [projects]);
  const { selectedProject, setSelectedProjectId } = usePersistentProjectSelection(projects);
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
      <AppBrand />
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
        <Search size={15} />
        <span>Search analyses, services...</span>
        <kbd>⌘K</kbd>
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
  selectedProjectOverride,
}: {
  active: "dashboard" | "history" | "settings" | "incidents" | "skills";
  children: (context: ShellProjectContext) => ReactNode;
  selectedProjectOverride?: ProjectOption;
}) {
  const projectContext = useSelectedProject();
  const selectedOption = selectedProjectOverride ?? projectContext.selectedOption;
  const projectOptions = useMemo(() => {
    if (!selectedProjectOverride) {
      return projectContext.projectOptions;
    }
    const hasOverride = projectContext.projectOptions.some((project) => project.id === selectedProjectOverride.id);
    return hasOverride ? projectContext.projectOptions : [selectedProjectOverride, ...projectContext.projectOptions];
  }, [projectContext.projectOptions, selectedProjectOverride]);
  const shellContext = { ...projectContext, selectedOption };

  return (
    <div className="dw-app-shell dw-phase6-shell dw-ui">
      <Sidebar active={active} selectedProject={selectedOption} />
      <div className="dw-main-pane">
        <TopBar
          onProjectChange={projectContext.setSelectedProject}
          projects={projectOptions}
          selectedProject={selectedOption}
        />
        <main className="dw-dashboard-scroll">
          {children(shellContext)}
        </main>
      </div>
    </div>
  );
}
