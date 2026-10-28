import { describe, expect, it } from "vitest";
import { initialWorkspaceSelection, scopeQuery } from "./InfraAutomationShared";

describe("explicit scope survives navigation", () => {
  it("round-trips a project-wide authoring selection without choosing a workspace", () => {
    expect(initialWorkspaceSelection(42, new URLSearchParams(scopeQuery({ projectId: 42, workspaceId: null }).slice(1)))).toBeNull();
  });
  it("restores a concrete workspace and defaults only for an unspecified project", () => {
    expect(initialWorkspaceSelection(42, new URLSearchParams("project_id=42&workspace_id=87"))).toBe(87);
    expect(initialWorkspaceSelection(42, new URLSearchParams())).toBeUndefined();
    expect(initialWorkspaceSelection(42, new URLSearchParams("project_id=99&workspace_id=87"))).toBeUndefined();
  });
});
