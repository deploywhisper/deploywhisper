import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { emptyUnit, inventoryFromDraft, inventoryAccessKey, UnitWaves, UnitRunEvidence } from "./InfraAutomationInventory";
import type { AutomationContext } from "./InfraAutomationShared";
import type { UnitPlan, UnitRevision, UnitRunView } from "../api/infraAutomationUnits";
const digest = `sha256:${"a".repeat(64)}`;
const inventory = inventoryFromDraft([{ ...emptyUnit(), id: "network", environment: "test", target: "network-target", affected: false }, { ...emptyUnit(), id: "app", environment: "test", target: "app-target", prerequisites: "network" }]);
const plan: UnitPlan = { version: 1, inventory, waves: [["network"], ["app"]], map_digest: digest, waves_digest: digest, order_kind: "collection_review" };
const revision: UnitRevision = { inventory_id: "inv", revision_id: "rev", version: 1, project_id: 7, workspace_id: 9, map_digest: digest, waves_digest: digest, created_by: "admin", created_at: "2026-11-05T00:00:00Z", plan };
const view: UnitRunView = { run_id: "run", project_id: 7, workspace_id: 9, run_version: 2, available: true, snapshot: { revision, bindings: [], snapshot_digest: digest }, evidence: { status: "pending", combined_digest: null, items: [] }, locks: [{ unit_id: "app", canonical_target: "physical-target", status: "held" }, { unit_id: "network", canonical_target: "network-target", status: "not_requested" }] };
describe("declared inventory presentation", () => {
  it("preserves explicit declarations and does not infer prerequisites or repository commits", () => { expect(inventory.affected).toEqual(["app"]); expect(inventory.units[0].prerequisites).toEqual([]); expect(inventory.units[1].prerequisites).toEqual(["network"]); expect(inventory.units[1].source).toEqual({ kind: "uploaded", repository_source: "unavailable", path: "." }); const malformed = inventoryFromDraft([{ ...emptyUnit(), prerequisites: "known,,unknown" }]); expect(malformed.units[0].prerequisites).toEqual(["known", "", "unknown"]); });
  it("renders accessible server wave order and explicit provisioning limitation", () => { const html = renderToStaticMarkup(<UnitWaves plan={plan} />); expect(html).toContain("Declared preflight waves"); expect(html).toContain('scope="col"'); expect(html).toContain('scope="row"'); expect(html.indexOf("network")).toBeLessThan(html.indexOf("app")); expect(html).toContain("do not establish deployment order"); });
  it("labels affected/prerequisite scope, declared source and retained canonical locks separately", () => { const html = renderToStaticMarkup(<MemoryRouter><UnitRunEvidence value={view} stale={true} /></MemoryRouter>); for (const phrase of ["Prerequisite", "Affected", "physical-target", "held", "Historical unit evidence", "repository unavailable", "audited lock break does not create authorization", "recollect, reanalyze"]) expect(html).toContain(phrase); });
  it("does not fabricate an inventory for an older run", () => { expect(renderToStaticMarkup(<UnitRunEvidence value={{ ...view, available: false, snapshot: null, evidence: null, locks: [] }} stale={false} />)).toBe(""); });
  it("separates confirmation state across identity, membership and scope transitions", () => { const context = { identity: { epoch: 1, principal: { session_id: "session" } }, scope: { projectId: 7, workspaceId: 9 }, capabilities: { membership_version: 1 } } as AutomationContext; const key = inventoryAccessKey(context); for (const value of [{ ...context, scope: { projectId: 8, workspaceId: 9 } }, { ...context, scope: { projectId: 7, workspaceId: 10 } }, { ...context, identity: { ...context.identity, epoch: 2 } }, { ...context, capabilities: { ...context.capabilities, membership_version: 2 } }]) expect(inventoryAccessKey(value)).not.toBe(key); });
});

import { InventorySaveRequests, unitEvidenceReadOptions } from "./InfraAutomationInventory";
import { CollectionStartRequests } from "./InfraAutomation";
import { QueryClient, QueryObserver } from "@tanstack/react-query";
const saveIntent = { projectId: 7, workspaceId: 9, mapDigest: digest, creatorId: "admin", inventoryId: null, expectedVersion: 1, knownInventoryIds: [] };
describe("inventory continuity and live evidence", () => {
  it("notifies a remount when an earlier pending save settles after unmount", () => {
    const saves = new InventorySaveRequests(); const ticket = saves.begin("scope", saveIntent);
    const detach = saves.subscribe(() => {}); detach();
    let updates = 0; saves.subscribe(() => { updates++; });
    saves.succeed("scope", ticket, revision);
    expect(updates).toBe(1); expect(saves.get("scope")).toMatchObject({ kind: "confirmed", inventoryId: "inv", revisionId: "rev" });
    saves.clearConfirmed("scope", "different", "rev"); expect(saves.get("scope")).toBeDefined();
    saves.clearConfirmed("scope", "inv", "rev"); expect(saves.get("scope")).toBeUndefined();
  });
  it("never clears a genuinely ambiguous save or a newer marker from an older response", () => {
    const saves = new InventorySaveRequests(); const old = saves.begin("scope", saveIntent);
    saves.clearConfirmed("scope", "inv", "rev"); expect(saves.get("scope")).toBe(old);
    saves.reject("scope", old); const next = saves.begin("scope", saveIntent); saves.succeed("scope", old, revision); expect(saves.get("scope")).toBe(next);
  });
  it("only permits an explicit new preflight after durable success", () => {
    const starts = new CollectionStartRequests(); const old = starts.begin("scope", "one");
    starts.clearConfirmed("scope"); expect(starts.get("scope")).toBe(old);
    starts.succeed("scope", old, "run"); starts.clearConfirmed("scope");
    expect(starts.get("scope")).toBeUndefined(); expect(starts.begin("scope", "two").requestId).not.toBe(old.requestId);
  });
  it("refreshes changed evidence at the same immutable run version", async () => {
    expect(unitEvidenceReadOptions.refetchInterval).toBe(5000);
    expect(unitEvidenceReadOptions.refetchOnWindowFocus).toBe("always");
    const client = new QueryClient(); let state = view;
    const observer = new QueryObserver(client, { queryKey: ["run-units", "run", view.run_version], queryFn: async () => state, ...unitEvidenceReadOptions });
    await observer.refetch(); expect(observer.getCurrentResult().data?.evidence?.status).toBe("pending");
    state = { ...view, evidence: { status: "changed", combined_digest: null, items: [] } };
    await observer.refetch(); expect(observer.getCurrentResult().data?.run_version).toBe(view.run_version); expect(observer.getCurrentResult().data?.evidence?.status).toBe("changed"); client.clear();
  });
});

it("adopts only matching verified revision after a lost save response", () => {
  const saves = new InventorySaveRequests(); const pending = saves.begin("scope", saveIntent);
  for (const wrong of [{ ...revision, project_id: 8 }, { ...revision, workspace_id: 10 }, { ...revision, created_by: "other" }, { ...revision, map_digest: `sha256:${"b".repeat(64)}` }, { ...revision, version: 2 }]) { expect(saves.recover("scope", wrong)).toBe(false); expect(saves.get("scope")).toBe(pending); }
  expect(saves.canRecover("scope", revision)).toBe(true); expect(saves.get("scope")).toBe(pending);
  expect(saves.recover("scope", revision)).toBe(true); expect(saves.get("scope")).toBeUndefined();
  saves.begin("existing", { ...saveIntent, inventoryId: "inv", expectedVersion: 2 });
  expect(saves.recover("existing", revision)).toBe(false);
  expect(saves.recover("existing", { ...revision, version: 2, inventory_id: "other" })).toBe(false);
  expect(saves.recover("existing", { ...revision, version: 2 })).toBe(true);
  saves.begin("new", { ...saveIntent, knownInventoryIds: ["inv"] });
  expect(saves.recover("new", revision)).toBe(false);
});

import { UnitStartRequests, UnitErrorSummary, unitFieldErrors } from "./InfraAutomationInventory";
import type { UnitRunRequest } from "../api/infraAutomationUnits";
const startPayload: UnitRunRequest = { run: { workflow_id: "wf", revision_id: "wf-rev", workspace_id: 9, reason: "Review scope", idempotency_key: "fixed-key", total_timeout_seconds: 3600, inputs: {} }, revision_id: "rev", confirmed_map_digest: digest, bindings: [{ unit_id: "app", intake_step_id: "intake", analysis_step_id: "analysis", artifacts: [{ name: "plan.json", content: "original bytes" }] }] };
it("retains exact request bytes and identity across an unresolved run and remount", () => {
  const starts = new UnitStartRequests(); const ticket = starts.remember("scope", startPayload);
  startPayload.bindings[0].artifacts[0].content = "later edited";
  const retry = starts.pendingRequest("scope")!; expect(retry.run.idempotency_key).toBe("fixed-key"); expect(retry.bindings[0].artifacts[0].content).toBe("original bytes");
  retry.bindings[0].artifacts[0].content = "mutated returned view";
  expect(starts.pendingRequest("scope")!.bindings[0].artifacts[0].content).toBe("original bytes");
  expect(() => starts.remember("scope", startPayload)).toThrow(); expect(starts.pendingRequest("different-scope")).toBeUndefined();
  starts.succeed("scope", ticket, "run"); expect(starts.pendingRequest("scope")).toBeUndefined(); expect(starts.get("scope")).toMatchObject({ kind: "confirmed", runId: "run" });
});
it("links located prerequisite errors to their actual control, not a valid unit ID", () => {
  const rows = [{ ...emptyUnit(), id: "app", prerequisites: "missing" }];
  const errors = [{ code: "unknown_identity", message: "Prerequisite not declared", path: ["units", 0, "prerequisites", 0] }];
  expect(unitFieldErrors(errors, rows, 0, "id")).toEqual([]);
  expect(unitFieldErrors(errors, rows, 0, "prerequisites")).toEqual(errors);
  const html = renderToStaticMarkup(<UnitErrorSummary errors={errors} rows={rows} />);
  expect(html).toContain('href="#unit-0-prerequisites"');
  expect(html).not.toContain('href="#unit-0-id"');
});
