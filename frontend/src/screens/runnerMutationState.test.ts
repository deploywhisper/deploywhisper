import { describe, expect, it } from "vitest";
import { RunnerMutationStore } from "./runnerMutationState";

describe("nonsecret runner mutation continuity", () => {
  it("retains pending and unknown issuance through same-session route remount", () => {
    const store = new RunnerMutationStore(2);
    const marker = store.begin("session", "scope", "enroll");
    expect(marker).not.toBeNull();
    // A remounted view reads the same module-memory marker; reads cannot settle it.
    expect(store.read("scope").issuance?.status).toBe("pending");
    expect(store.begin("session", "scope", "rotate", "runner-one")).toBeNull();
    store.unknown(marker!);
    expect(store.read("scope").issuance?.status).toBe("unknown");
    store.pruneSettledOtherIdentities("new-session");
    expect(store.read("scope").issuance?.status).toBe("unknown");
    expect(store.read("other-scope").issuance).toBeUndefined();
  });
  it("retains a token-free verified late outcome and never lets an old response settle a new request", () => {
    const store = new RunnerMutationStore(2);
    const first = store.begin("session", "scope", "enroll")!;
    const reply = { kind: "issued" as const, runnerId: "runner-one", credentialCleared: true, token: "must-not-retain" };
    store.verified(first, reply);
    expect(store.read("scope").issuance).toBeUndefined();
    expect(store.read("scope").outcome).toMatchObject({ action: "enroll", runnerId: "runner-one", credentialCleared: true });
    expect(JSON.stringify(store.read("scope"))).not.toContain("token");
    expect(JSON.stringify(store.read("scope"))).not.toContain("must-not-retain");
    const second = store.begin("session", "scope", "rotate", "runner-one")!;
    store.verified(first, { kind: "issued", runnerId: "runner-one", credentialCleared: true });
    expect(store.read("scope").issuance?.operation).toBe(second.operation);
  });
  it("permits recovery revocation without replacing unknown issuance and only settles matching known authority", () => {
    const store = new RunnerMutationStore(2);
    const enrollment = store.begin("session", "scope", "enroll")!;
    store.unknown(enrollment);
    const revoke = store.begin("session", "scope", "revoke", "runner-one")!;
    store.verified(revoke, { kind: "revoked", runnerId: "runner-one" });
    expect(store.read("scope").issuance?.operation).toBe(enrollment.operation);
    store.verified(enrollment, { kind: "rejected" });
    const rotation = store.begin("session", "scope", "rotate", "runner-two")!;
    store.unknown(rotation);
    const recovery = store.begin("session", "scope", "revoke", "runner-two")!;
    store.verified(recovery, { kind: "revoked", runnerId: "runner-two" });
    expect(store.read("scope").issuance).toBeUndefined();
  });
  it("bounds metadata without evicting unresolved authority", () => {
    const store = new RunnerMutationStore(2);
    const first = store.begin("old-session", "scope-one", "enroll")!;
    store.begin("old-session", "scope-two", "enroll");
    expect(store.begin("new-session", "scope-three", "enroll")).toBeNull();
    store.verified(first, { kind: "rejected" });
    expect(store.begin("new-session", "scope-three", "enroll")).not.toBeNull();
    expect(store.read("scope-two").issuance).toBeDefined();
  });
});
