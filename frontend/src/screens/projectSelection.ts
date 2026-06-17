import { useMemo, useState } from "react";

import type { Project } from "../api/dashboard";
import type { ProjectOption } from "../components/ui";

export const PROJECT_SELECTION_STORAGE_KEY = "deploywhisper.selectedProjectId";

export function projectToOption(project: Project): ProjectOption {
  return {
    id: String(project.id),
    name: project.name || project.display_name || project.project_key,
    env: project.env_label || project.default_branch || "default",
    description: project.description || project.repository_url || project.project_key,
  };
}

export function readStoredProjectId() {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(PROJECT_SELECTION_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeSelectedProjectId(projectId: string) {
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(PROJECT_SELECTION_STORAGE_KEY, projectId);
    }
  } catch {
    // Storage can be blocked in private contexts; keep in-memory selection working.
  }
}

export function selectProjectById<T extends { id: number | string }>(projects: T[], selectedProjectId: string | null) {
  if (projects.length === 0) {
    return undefined;
  }
  return projects.find((project) => String(project.id) === selectedProjectId) ?? projects[0];
}

export function usePersistentProjectSelection<T extends { id: number | string }>(projects: T[]) {
  const [selectedProjectId, setSelectedProjectIdState] = useState<string | null>(() => readStoredProjectId());
  const selectedProject = useMemo(() => selectProjectById(projects, selectedProjectId), [projects, selectedProjectId]);

  return {
    selectedProject,
    selectedProjectId,
    setSelectedProjectId(projectId: string) {
      setSelectedProjectIdState(projectId);
      storeSelectedProjectId(projectId);
    },
  };
}
