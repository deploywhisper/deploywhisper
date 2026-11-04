import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ApiClientError } from "../api/client";
import { AutomationNavItem } from "./AutomationNavigation";
import { ProjectMenu, projectCreationError, projectPrefill } from "./ProjectMenu";

describe("shared project action", () => {
  it("prefills friendly editable names and stable keys", () => {
    expect(projectPrefill("  Checkout Infra!  ")).toEqual({ name: "Checkout Infra!", key: "checkout-infra" });
    expect(projectPrefill(" !!! ")).toEqual({ name: "!!!", key: "" });
  });
  it("renders labeled native form with no automatic submission", () => {
    const html = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><ProjectMenu projects={[{ id: "1", name: "Synthetic", env: "default", description: "fixture" }]} /></QueryClientProvider>);
    expect(html).toContain("<dialog");
    expect(html).toContain("aria-labelledby=");
    expect(html).toContain("Project name<input");
    expect(html).toContain("Project key<input");
    expect(html).toContain("Workspace setup and project access are managed separately.");
  });
  it.each([400, 401, 403, 409, 422, 429])("uses fixed safe copy for definite HTTP rejection %s", (status) => {
    expect(projectCreationError(new ApiClientError("private-server-value", status))).toBeTypeOf("string");
    expect(projectCreationError(new ApiClientError("private-server-value", status))).not.toContain("private");
  });
  it.each([new TypeError("private-url"), new ApiClientError("malformed", 200), new ApiClientError("uncertain", 503)])("treats ambiguous responses as uncertain", (error) => {
    expect(projectCreationError(error)).toBeNull();
  });
  it("exposes the existing setup route while signed out without protected fetches", () => {
    const html = renderToStaticMarkup(<MemoryRouter><AutomationNavItem projectId={7} /></MemoryRouter>);
    expect(html).toContain('href="/infra-automation?project_id=7"');
    expect(html).toContain("InfraFlow");
    expect(renderToStaticMarkup(<MemoryRouter><AutomationNavItem /></MemoryRouter>)).toContain('href="/infra-automation"');
  });
});
