import { afterEach, describe, expect, it, vi } from "vitest";
import { getUnitInventories, getUnitRevision, getRunUnits, validateUnitInventory, startUnitRun, type UnitMap, type UnitPlan, type UnitRevision, type UnitRunView } from "./infraAutomationUnits";
const scope = { projectId: 7, workspaceId: 9 }, digest = `sha256:${"a".repeat(64)}`;
export const map: UnitMap = { version: 1, units: [{ id: "network", source: { kind: "uploaded", repository_source: "unavailable", path: "." }, environment: "test", target: "target", prerequisites: [] }], affected: ["network"] };
export const plan: UnitPlan = { version: 1, inventory: map, waves: [["network"]], map_digest: digest, waves_digest: digest, order_kind: "collection_review" };
export const revision: UnitRevision = { inventory_id: "inventory", revision_id: "revision", version: 1, project_id: 7, workspace_id: 9, map_digest: digest, waves_digest: digest, created_by: "admin", created_at: "2026-11-05T00:00:00Z", plan };
export const runView: UnitRunView = { run_id: "run", project_id: 7, workspace_id: 9, run_version: 1, available: true, snapshot: { revision, bindings: [{ unit_id: "network", intake_step_id: "intake", analysis_step_id: "analysis" }], snapshot_digest: digest }, evidence: { status: "available", combined_digest: digest, items: [{ unit_id: "network", report_id: 1, manifest_digest: digest, report_digest: digest, source_digest: digest }] }, locks: [{ unit_id: "network", canonical_target: "target", status: "held" }] };
function response(data: unknown) { const fetcher = vi.fn().mockResolvedValue(Response.json({ data, meta: {} })); vi.stubGlobal("fetch", fetcher); return fetcher; }
afterEach(() => vi.unstubAllGlobals());
describe("declared inventory API boundary", () => {
  it("reads exact scope without caching and checks immutable digests", async () => { const fetcher = response({ items: [revision], truncated: false }); await expect(getUnitInventories(scope)).resolves.toMatchObject({ items: [revision] }); expect(fetcher.mock.calls[0][0]).toBe("/api/v1/infra-automation/units?project_id=7&workspace_id=9"); expect(fetcher.mock.calls[0][1]).toMatchObject({ cache: "no-store", credentials: "same-origin" }); response(revision); await expect(getUnitRevision("inventory", "revision", scope)).resolves.toEqual(revision); });
  it.each([{ ...revision, workspace_id: 10 }, { ...revision, map_digest: `sha256:${"b".repeat(64)}` }, { ...revision, plan: { ...plan, waves: [["other"]] } }, { ...revision, revision_id: "other" }])("rejects cross-scope or incoherent revision", async (value) => { response(value); await expect(getUnitRevision("inventory", "revision", scope)).rejects.toMatchObject({ status: 422 }); });
  it("retains located unknown/cycle errors without computing a browser graph", async () => { const errors = [{ code: "unknown_identity", message: "Unknown prerequisite.", path: ["units", 0, "prerequisites", 0] }]; const fetcher = response({ valid: false, plan: null, errors }); await expect(validateUnitInventory(map, scope, "csrf")).resolves.toEqual({ valid: false, plan: null, errors }); expect(new Headers(fetcher.mock.calls[0][1].headers).get("X-CSRF-Token")).toBe("csrf"); });
  it("rejects validation claiming success without a complete plan", async () => { response({ valid: true, plan: null, errors: [] }); await expect(validateUnitInventory(map, scope, "csrf")).rejects.toMatchObject({ status: 422 }); });
  it("supports historical runs without inventing inventory", async () => { response({ ...runView, available: false, snapshot: null, evidence: null, locks: [] }); await expect(getRunUnits("run", scope)).resolves.toMatchObject({ available: false }); response(runView); await expect(getRunUnits("run", scope)).resolves.toEqual(runView); });
  it.each([{ ...runView, run_id: "other" }, { ...runView, workspace_id: 1 }, { ...runView, evidence: { ...runView.evidence, combined_digest: null } }, { ...runView, locks: [] }, { ...runView, locks: [{ unit_id: "network", canonical_target: "target", status: "expired" }] }])("rejects unsupported evidence/lock state", async (value) => { response(value); await expect(getRunUnits("run", scope)).rejects.toMatchObject({ status: 422 }); });
  it("never submits missing-CSRF or oversized artifact bodies", async () => { const fetcher = response({}); const payload = { run: { workflow_id: "wf", revision_id: "rev", workspace_id: 9, reason: "Review units", idempotency_key: "request", inputs: {}, total_timeout_seconds: 3600 }, revision_id: "revision", confirmed_map_digest: digest, bindings: [{ unit_id: "network", intake_step_id: "intake", analysis_step_id: "analysis", artifacts: [{ name: "main.tf", content: "a".repeat(131072) }] }] }; let submitted = false; await expect(startUnitRun(payload, scope, "csrf", () => { submitted = true; })).rejects.toMatchObject({ status: 422 }); expect(submitted).toBe(false); await expect(startUnitRun(payload, scope, "")).rejects.toMatchObject({ status: 403 }); expect(fetcher).not.toHaveBeenCalled(); });
});

import { saveUnitInventory } from "./infraAutomationUnits";
import { isConfirmedCollectionRejection } from "./infraAutomationCollection";
describe("successful mutation response ambiguity", () => {
  it("keeps malformed success bodies distinct from rejected HTTP writes", async () => {
    const payload = { run: { workflow_id: "wf", revision_id: "rev", workspace_id: 9, reason: "Review units", idempotency_key: "request", inputs: {}, total_timeout_seconds: 3600 }, revision_id: "revision", confirmed_map_digest: digest, bindings: [{ unit_id: "network", intake_step_id: "intake", analysis_step_id: "analysis", artifacts: [] }] };
    for (const operation of [() => saveUnitInventory(map, scope, "csrf", "Confirm units"), () => startUnitRun(payload, scope, "csrf")]) {
      response({}); const failure = await operation().catch((error) => error);
      expect(failure).toMatchObject({ status: 422 });
      expect(failure.code).toBeUndefined();
      expect(isConfirmedCollectionRejection(failure)).toBe(false);
    }
  });
  it("retains confirmed server rejections without turning them into decode ambiguity", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ error: { code: "request_validation_failed", details: {} } }, { status: 422 })));
    const failure = await saveUnitInventory(map, scope, "csrf", "Confirm units").catch((error) => error);
    expect(isConfirmedCollectionRejection(failure)).toBe(true);
  });
});

  it("rejects duplicated available evidence and impossible pending digests", async () => {
    const other = { ...map.units[0], id: "other" };
    const two = { ...runView, snapshot: { ...runView.snapshot!, revision: { ...revision, plan: { ...plan, inventory: { ...map, units: [...map.units, other], affected: ["network", "other"] }, waves: [["network", "other"]] } }, bindings: [...runView.snapshot!.bindings, { unit_id: "other", intake_step_id: "other-intake", analysis_step_id: "other-analysis" }] }, locks: [...runView.locks, { unit_id: "other", canonical_target: "other-target", status: "held" }], evidence: { ...runView.evidence!, items: [runView.evidence!.items[0], runView.evidence!.items[0]] } };
    response(two); await expect(getRunUnits("run", scope)).rejects.toMatchObject({ status: 422 });
    for (const status of ["pending", "changed"]) { response({ ...runView, evidence: { ...runView.evidence, status } }); await expect(getRunUnits("run", scope)).rejects.toMatchObject({ status: 422 }); }
  });

import { InventorySaveRequests } from "../screens/InfraAutomationInventory";
it("recovers a persisted save through a verified GET after its POST response is lost", async () => {
  const saves = new InventorySaveRequests();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Connection lost")));
  await expect(saveUnitInventory(map, scope, "csrf", "Confirm units", undefined, () => { saves.begin("scope", { projectId: 7, workspaceId: 9, mapDigest: digest, creatorId: "admin", inventoryId: null, expectedVersion: 1, knownInventoryIds: [] }); })).rejects.toThrow();
  expect(saves.get("scope")?.kind).toBe("pending");
  response(revision); const observed = await getUnitRevision("inventory", "revision", scope);
  expect(saves.canRecover("scope", observed)).toBe(true); expect(saves.get("scope")?.kind).toBe("pending");
  expect(saves.recover("scope", observed)).toBe(true); expect(saves.get("scope")).toBeUndefined();
});
