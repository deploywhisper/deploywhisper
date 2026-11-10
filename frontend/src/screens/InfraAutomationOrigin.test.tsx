import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { RunHistory } from "./InfraAutomation";
import { RunSummary } from "./InfraAutomationRun";
import type { AutomationContext } from "./InfraAutomationShared";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Run, RunOrigin } from "../api/infraAutomation";
import { RunOriginDetails, RunOriginSummary } from "./InfraAutomationOrigin";

const collected = { kind: "collected" as const, step_id: "collect", repository_id: "registered-repo", commit_sha: "a".repeat(40), profile_digest: `sha256:${"b".repeat(64)}` };
const uploaded = { kind: "uploaded" as const, step_id: "upload", repository_id: null, commit_sha: null, limitation: "Uploaded evidence does not establish repository identity or exact-plan custody." as const };
const machine: RunOrigin = { version: 1, kind: "pull_request", principal_id: "machine-principal", principal_type: "agent", key_id: "scoped-key", pr_ref: "refs/pull/12/head", sources: [collected] };

describe("run origin presentation", () => {
  it.each([undefined, null])("does not invent origin for a legacy run", (origin) => {
    expect(renderToStaticMarkup(<RunOriginSummary origin={origin} />)).toContain("Not recorded");
    const html = renderToStaticMarkup(<RunOriginDetails origin={origin} />);
    expect(html).toContain("Request origin was not recorded for this run.");
    expect(html).not.toContain("Authenticated principal type");
  });
  it("shows authenticated requester independently from subsequent human review", () => {
    const html = renderToStaticMarkup(<RunOriginDetails origin={machine} />);
    for (const value of ["Signed PR request", "Agent", "machine-principal", "scoped-key", "refs/pull/12/head", collected.repository_id, collected.commit_sha, collected.profile_digest]) expect(html).toContain(value);
    expect(html).toContain("Requested source pins");
    expect(html).toContain('scope="col"');
    expect(html).toContain('scope="row"');
    expect(html).not.toContain("Human acknowledgement");
    expect(html).toContain("does not establish collected provenance or approval");
  });
  it.each(["manual", "cli"] as const)("renders %s human origin without a fabricated signing key", (kind) => {
    const origin: RunOrigin = { version: 1, kind, principal_id: "human-principal", principal_type: "human", sources: [uploaded] };
    const html = renderToStaticMarkup(<RunOriginDetails origin={origin} />);
    expect(html).toContain(kind === "cli" ? "CLI channel" : "Manual");
    expect(html).toContain("Human");
    expect(html).toContain("Uploaded evidence");
    expect(html).toContain("Unavailable");
    expect(html).not.toContain("Signing key ID");
    expect(html).not.toContain("Declared PR reference");
  });
  it("keeps long principal IDs out of compact history text while retaining exact detail", () => {
    const origin = { ...machine, principal_id: "a".repeat(48) };
    const summary = renderToStaticMarkup(<RunOriginSummary origin={origin} />);
    const visible = summary.match(/^<span\b[^>]*>([^<]*)<\/span>$/)?.[1];
    expect(visible).toBe("Signed PR request · Agent");
    expect(visible).toContain("Signed PR request"); expect(visible).toContain("Agent");
    expect(visible).not.toContain(origin.principal_id);
    expect(renderToStaticMarkup(<RunOriginDetails origin={origin} />)).toContain(origin.principal_id);
  });
  it("keeps CLI channel and machine principal distinct in history", () => {
    const html = renderToStaticMarkup(<RunOriginSummary origin={{ ...machine, kind: "cli", pr_ref: null, principal_type: "service" }} />);
    expect(html).toContain("CLI channel");
    expect(html).toContain("Service");
    expect(html).toContain("machine-principal");
    expect(html).not.toContain("Human");
  });
});

const run: Run = { id: "machine-run", workflow_id: "workflow", revision_id: "revision", project_id: 7, workspace_id: 9, requested_by: "machine-principal", state: "waiting_approval", version: 1, snapshot_digest: "sha256:" + "a".repeat(64), definition_digest: "sha256:" + "a".repeat(64), input_digest: "sha256:" + "a".repeat(64), created_at: "2026-11-06T00:00:00Z", deadline_at: "2026-11-06T01:00:00Z", cancel_requested: false, cancellation_requested_at: null, origin: machine };
describe("origin integration in existing history and details", () => {
  it("shows machine origin after a later human decision changes run state", () => {
    for (const state of ["waiting_approval", "ready_handoff", "succeeded"] as const) {
      const html = renderToStaticMarkup(<MemoryRouter><RunSummary run={{ ...run, state }} /></MemoryRouter>);
      expect(html).toContain("Request origin"); expect(html).toContain("Agent"); expect(html).toContain("machine-principal");
      expect(html).toContain(collected.commit_sha); expect(html).not.toContain("Human acknowledgement");
    }
  });
  it("renders authenticated origin in the scoped history table", () => {
    const client = new QueryClient();
    const context = { identity: { epoch: 1 }, scope: { projectId: 7, workspaceId: 9 } } as AutomationContext;
    client.setQueryData(["automation", "runs", 1, 7, 9], { pages: [{ items: [run], cursor: { version: 1, limit: 25, snapshot_id: "snapshot", next_cursor: null, last_sequence: 1, truncated: false, gap: false } }], pageParams: [undefined] });
    const html = renderToStaticMarkup(<MemoryRouter><QueryClientProvider client={client}><RunHistory context={context} /></QueryClientProvider></MemoryRouter>);
    expect(html).toContain("Request origin"); expect(html).toContain("Signed PR request"); expect(html).toContain("Agent"); expect(html).toContain("machine-principal");
    client.clear();
  });
});
