import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AutomationFrame, initialWorkspaceSelection, scopeQuery } from "./InfraAutomationShared";

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

it("explains named accounts and project access before opening protected InfraFlow", () => {
  const html = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><MemoryRouter><AutomationFrame>{() => <p>Protected workflow details</p>}</AutomationFrame></MemoryRouter></QueryClientProvider>);
  expect(html).toContain("Your application operator must configure named accounts and grant project access before you can use InfraFlow.");
  expect(html).not.toContain("Protected workflow details");
});
