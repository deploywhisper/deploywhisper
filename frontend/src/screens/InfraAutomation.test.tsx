import { describe, expect, it } from "vitest";
import { uploadWorkflowTemplate, parseRunInputs, validateArtifactFiles } from "./InfraAutomation";

describe("uploaded workflow authoring boundaries", () => {
  it("binds the template to the selected real scope and supported executable steps", () => {
    const value = uploadWorkflowTemplate({ projectId: 42, workspaceId: 87 });
    expect(value).toContain('project_id: "42"');
    expect(value).toContain('workspace_id: "87"');
    expect(value).toContain("kind: uploaded_intake");
    expect(value).toContain("kind: shared_analysis");
    expect(value).not.toContain("handoff");
    expect(uploadWorkflowTemplate({ projectId: 42, workspaceId: null })).toContain("workspace_id: null");
  });
  it("accepts bounded scalar inputs while rejecting unsafe integers, arrays and objects", () => {
    expect(parseRunInputs('{"environment":"review","replicas":2,"enabled":true}')).toEqual({ environment: "review", replicas: 2, enabled: true });
    for (const value of ["[]", "null", '{"a":{}}', '{"a":1.5}', '{"a":9007199254740992}', '{"a":null}', '{"a":"' + "x".repeat(1025) + '"}']) expect(() => parseRunInputs(value)).toThrow();
  });
  it("bounds upload count/size and rejects duplicate, state, binary and credential file selections", () => {
    const file = (name: string, size = 12) => ({ name, size }) as File;
    expect(() => validateArtifactFiles([file("main.tf"), file("plan.json")])).not.toThrow();
    for (const files of [[], [file("main.tf", 0)], [file("plan.tfstate")], [file("saved.tfplan")], [file("private.pem")], [file("main.tf"), file("main.tf")], [file("main.tf", 8_388_609)]]) expect(() => validateArtifactFiles(files)).toThrow();
  });
});

import { collectionCanRequest } from "./InfraAutomation";
import type { CollectionReadiness } from "../api/infraAutomationCollection";
describe("collection start eligibility", () => {
  const value: CollectionReadiness = { version: 1, workflow_id: "wf", revision_id: "rev", project_id: 1, workspace_id: 2, observed_at: "2026-11-05T00:00:00Z", finite_wait_seconds: 0, can_request: true, execution_enabled: true, items: [{ step_id: "collect", repository_id: null, commit_sha: null, profile_digest: `sha256:${"a".repeat(64)}`, inputs_required: true, diagnosis: { code: "eligible", eligible: true, correction: "Server rechecks authority." } }] };
  it("allows server-admitted scalar source inputs but blocks known unavailable runners", () => {
    expect(collectionCanRequest(value)).toBe(true);
    expect(collectionCanRequest({ ...value, items: [{ ...value.items[0], diagnosis: { code: "no_runner", eligible: false, correction: "Enroll a runner." } }] })).toBe(false);
    expect(collectionCanRequest({ ...value, can_request: false })).toBe(false);
    expect(collectionCanRequest({ ...value, execution_enabled: false })).toBe(false);
    expect(collectionCanRequest({ ...value, items: [] })).toBe(false);
  });
  it("does not turn hidden runner details into loss of an explicitly granted request capability", () => {
    expect(collectionCanRequest({ ...value, items: [{ ...value.items[0], diagnosis: { code: "details_unavailable", eligible: false, correction: "Ask administrator." } }] })).toBe(true);
  });
});

import { CollectionStartRequests } from "./InfraAutomation";
describe("late collection request settlement", () => {
  it("settles a late success after unmount and exposes its known run to a remount", async () => {
    const requests = new CollectionStartRequests();
    const ticket = requests.begin("scope", "request-one");
    const first = requests.subscribe(() => {}); first();
    let notified = 0; requests.subscribe(() => { notified++; });
    requests.succeed("scope", ticket, "run-one");
    expect(requests.get("scope")).toMatchObject({ kind: "confirmed", runId: "run-one" });
    expect(notified).toBe(1);
  });
  it("clears a late confirmed rejection but cannot erase a newer request", () => {
    const requests = new CollectionStartRequests();
    const old = requests.begin("scope", "request-one"); requests.reject("scope", old);
    expect(requests.get("scope")).toBeUndefined();
    const current = requests.begin("scope", "request-two"); requests.reject("scope", old);
    expect(requests.get("scope")).toBe(current);
  });
});
