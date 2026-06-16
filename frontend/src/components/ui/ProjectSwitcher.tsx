import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronsUpDown, FolderGit2, Plus, Search } from "lucide-react";

export type ProjectOption = {
  id: string;
  name: string;
  env: string;
  description: string;
};

export const demoProjects: ProjectOption[] = [
  { id: "payments-api", name: "payments-api", env: "prod · main", description: "Core payment processing" },
  { id: "test1", name: "test1", env: "test", description: "Key test workspace" },
  { id: "checkout-infra", name: "checkout-infra", env: "staging", description: "Checkout Terraform stack" },
  { id: "data-platform", name: "data-platform", env: "prod", description: "Airflow + warehouse IaC" },
];

export function ProjectSwitcher({
  projects = demoProjects,
  selectedProject,
  onChange,
  onNewProject,
  initialOpen = false,
  initialQuery = "",
  suppressBackdrop = false,
  openSignal,
}: {
  projects?: ProjectOption[];
  selectedProject?: ProjectOption;
  onChange?: (project: ProjectOption) => void;
  onNewProject?: (query: string) => void;
  initialOpen?: boolean;
  initialQuery?: string;
  suppressBackdrop?: boolean;
  openSignal?: number;
}) {
  const [open, setOpen] = useState(initialOpen);
  const [query, setQuery] = useState(initialQuery);
  const inputRef = useRef<HTMLInputElement>(null);
  const current = selectedProject ?? projects[0];
  const filteredProjects = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return projects;
    }
    return projects.filter((project) => {
      return `${project.name} ${project.env} ${project.description}`.toLowerCase().includes(normalized);
    });
  }, [projects, query]);

  useEffect(() => {
    if (!open) {
      return;
    }

    inputRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    if (openSignal === undefined || openSignal <= 0) {
      return;
    }
    setOpen(true);
  }, [openSignal]);

  const selectProject = (project: ProjectOption) => {
    onChange?.(project);
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="dw-project-switcher">
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        className={`dw-project-trigger${open ? " dw-project-trigger-open" : ""}`}
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <span className="dw-project-trigger-icon">
          <FolderGit2 size={12} />
        </span>
        <span className="dw-project-trigger-name">{current.name}</span>
        <span className="dw-project-trigger-env">{current.env.split(" ")[0]}</span>
        <ChevronsUpDown color="var(--dw-faint)" size={13} />
      </button>

      {open && (
        <>
          {!suppressBackdrop && (
            <button aria-label="Close project switcher" className="dw-project-backdrop" onClick={() => setOpen(false)} type="button" />
          )}
          <div aria-label="Projects" className="dw-project-popover" role="listbox">
            <div className="dw-project-search-row">
              <Search color="var(--dw-faint)" size={14} />
              <input
                ref={inputRef}
                className="dw-project-search"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search projects..."
                value={query}
              />
            </div>
            <div className="dw-project-list">
              <div className="dw-project-list-eyebrow">PROJECTS · {filteredProjects.length}</div>
              {filteredProjects.length === 0 && (
                <div className="dw-project-empty">No project matches &quot;{query}&quot;. Create it below.</div>
              )}
              {filteredProjects.map((project) => {
                const selected = project.id === current.id;
                return (
                  <button
                    key={project.id}
                    aria-selected={selected}
                    className={`dw-project-option${selected ? " dw-project-option-selected" : ""}`}
                    onClick={() => selectProject(project)}
                    role="option"
                    type="button"
                  >
                    <span className="dw-project-option-tile">
                      <FolderGit2 size={13} />
                    </span>
                    <span className="dw-project-option-copy">
                      <span className="dw-project-option-title">
                        <span className="dw-project-option-name">{project.name}</span>
                        <span className="dw-project-option-env">{project.env}</span>
                      </span>
                      <span className="dw-project-option-desc">{project.description}</span>
                    </span>
                    {selected && <Check color="var(--dw-brand)" size={15} />}
                  </button>
                );
              })}
            </div>
            <button className="dw-project-new" onClick={() => onNewProject?.(query)} type="button">
              <span className="dw-project-new-icon">
                <Plus size={13} />
              </span>
              New project
            </button>
          </div>
        </>
      )}
    </div>
  );
}
