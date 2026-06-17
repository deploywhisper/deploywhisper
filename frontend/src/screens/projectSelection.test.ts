import { describe, expect, it } from "vitest";

import type { Project } from "../api/dashboard";
import { projectToOption, selectProjectById } from "./projectSelection";

const projects = [
  { id: 1, name: "Payments" },
  { id: 7, name: "Checkout" },
  { id: 9, name: "Settings" },
];

const project = {
  id: 7,
  project_key: "checkout",
  display_name: "Checkout API",
  description: "Checkout platform",
  repository_url: null,
  default_branch: "main",
  is_default: false,
  created_at: "2026-06-16T00:00:00Z",
  updated_at: "2026-06-16T00:00:00Z",
  name: "Checkout",
  env_label: "prod",
} satisfies Project;

describe("project selection", () => {
  it("keeps the explicitly selected project when the project list reloads", () => {
    expect(selectProjectById(projects, "7")).toEqual({ id: 7, name: "Checkout" });
  });

  it("falls back to the first project only when there is no matching stored selection", () => {
    expect(selectProjectById(projects, null)).toEqual({ id: 1, name: "Payments" });
    expect(selectProjectById(projects, "404")).toEqual({ id: 1, name: "Payments" });
  });

  it("maps API projects to switcher options consistently", () => {
    expect(projectToOption(project)).toEqual({
      id: "7",
      name: "Checkout",
      env: "prod",
      description: "Checkout platform",
    });
  });
});
