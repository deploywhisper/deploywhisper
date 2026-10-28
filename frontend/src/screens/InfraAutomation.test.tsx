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
