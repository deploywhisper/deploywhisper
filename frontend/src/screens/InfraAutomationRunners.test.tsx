import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { AutomationContext } from "./InfraAutomationShared";
import type { RunnerCapabilities, RunnerHealth } from "../api/infraAutomationRunners";
import { RunnerMutationStore } from "./runnerMutationState";
import { RunnerPanel, RunnerSecretPanel, runnerAccessKey, runnerMutationKey, visibleRunnerSecret, runnerSecretDeadline, parseRunnerTags, type RunnerSecret } from "./InfraAutomationRunners";

const digest = `sha256:${"a".repeat(64)}`, stamp = "2026-11-05T00:00:00Z";
const context = { scope: { projectId: 7, workspaceId: 9 }, identity: { epoch: 1, csrfToken: "csrf", status: "ready", principal: { session_id: "session-one", principal_id: "admin" } }, capabilities: { execution_enabled: true, membership_version: 1 }, fresh: true, ensureFresh: async () => ({}), refresh: async () => ({}) } as unknown as AutomationContext;
const capabilities: RunnerCapabilities = { version: 1, project_id: 7, workspace_id: 9, evaluated_at: stamp, can_read_health: true, can_enroll: true, can_rotate: true, can_revoke: true, production_eligible: true, execution_enabled: true, restriction: "none", profile_status: "available", configured_profiles: [{ profile_digest: digest, tool: "opentofu", tool_version: "1.13.1", runner_version: "1.0", tags: ["isolated"] }] };
const runner: RunnerHealth = { id: "runner-one", project_id: 7, workspace_id: 9, tags: ["isolated"], tool: "opentofu", tool_version: "1.13.1", runner_version: "1.0", profile_digest: digest, protocol_version: 1, generation: 1, status: "active", last_seen_at: stamp, credential_expires_at: "2026-11-05T00:15:00Z", isolation_qualified: false, current_task: { run_id: "run-one", step_id: "collect", attempt_id: "attempt-one" }, evaluated_at: stamp, connectivity: "stale", heartbeat_age_seconds: 90, online_threshold_seconds: 60, offline_threshold_seconds: 180, connectivity_reason: "heartbeat_stale", credential_status: "valid", profile_status: "registered" };
function render(caps = capabilities, rows = [runner], current = context) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const key = ["automation", "runners", runnerAccessKey(current)];
  client.setQueryData([...key, "capabilities"], caps);
  client.setQueryData([...key, "health", undefined], { items: rows, cursor: { version: 1, snapshot_id: "snapshot", next_cursor: null, limit: 25, last_sequence: 1, truncated: false, gap: false } });
  return renderToStaticMarkup(<MemoryRouter><QueryClientProvider client={client}><RunnerPanel context={current} /></QueryClientProvider></MemoryRouter>);
}

describe("runner health and transient authority", () => {
  it("shows server connectivity separately from registration, profile and trust", () => {
    const html = render();
    for (const value of ["Runner health", "stale", "active", "1.13.1", "Health does not certify isolation", "Open active run", "90 seconds"]) expect(html).toContain(value);
    expect(html).not.toContain("isolation verified");
  });
  it("hides admin actions on HTTPS-required and denied capability projections", () => {
    const html = render({ ...capabilities, can_read_health: false, can_enroll: false, can_rotate: false, can_revoke: false, production_eligible: false, restriction: "https_required", configured_profiles: [] });
    expect(html).toContain("HTTPS"); expect(html).not.toContain("runner-one"); expect(html).not.toContain("Issue enrollment");
  });
  it("renders an honest empty state and never invents a healthy runner", () => {
    const html = render(capabilities, []); expect(html).toContain("No runners registered"); expect(html).not.toContain("runner-one");
  });
  it("withholds mutation controls while current authority is unavailable", () => {
    const html = render(capabilities, [runner], { ...context, fresh: false });
    expect(html).toContain("disabled"); expect(html).toContain("Refresh access");
  });
  it("invalidates reveal across project, workspace, session, epoch and membership changes", () => {
    const key = runnerAccessKey(context);
    const secret: RunnerSecret = { key, kind: "enrollment", runnerId: "runner-one", token: "ephemeral-value", expiresAt: "2026-11-05T00:05:00Z", monotonicDeadline: 300_000 };
    expect(visibleRunnerSecret(secret, key, true, 1, Date.parse(stamp))).toBe(secret);
    const contexts = [ { ...context, scope: { projectId: 8, workspaceId: 9 } }, { ...context, scope: { projectId: 7, workspaceId: 10 } }, { ...context, identity: { ...context.identity, epoch: 2 } }, { ...context, identity: { ...context.identity, principal: { ...context.identity.principal!, session_id: "session-two" } } }, { ...context, capabilities: { ...context.capabilities, membership_version: 2 } } ];
    for (const changed of contexts) expect(visibleRunnerSecret(secret, runnerAccessKey(changed), true, 1, Date.parse(stamp))).toBeNull();
    expect(visibleRunnerSecret(secret, key, false, 1, Date.parse(stamp))).toBeNull();
    expect(visibleRunnerSecret(secret, key, true, 300_000, Date.parse(stamp))).toBeNull();
    expect(visibleRunnerSecret(secret, key, true, 1, Date.parse(secret.expiresAt))).toBeNull();
    expect(visibleRunnerSecret(null, key, true, 1, Date.parse(stamp))).toBeNull();
  });
  it("retains unresolved mutation continuity across same-session membership and epoch refresh while clearing the secret", () => {
    const changed = { ...context, identity: { ...context.identity, epoch: context.identity.epoch + 1 }, capabilities: { ...context.capabilities, membership_version: 2 } };
    expect(runnerAccessKey(changed)).not.toBe(runnerAccessKey(context));
    expect(runnerMutationKey(changed)).toBe(runnerMutationKey(context));
    const store = new RunnerMutationStore(2);
    const pending = store.begin("same-principal-session", runnerMutationKey(context), "enroll")!;
    store.unknown(pending);
    expect(store.read(runnerMutationKey(changed)).issuance?.status).toBe("unknown");
    expect(store.begin("same-principal-session", runnerMutationKey(changed), "enroll")).toBeNull();
    const secret: RunnerSecret = { key: runnerAccessKey(context), kind: "enrollment", runnerId: "runner-one", token: "transient", expiresAt: "2026-11-05T00:05:00Z", monotonicDeadline: 300_000 };
    expect(visibleRunnerSecret(secret, runnerAccessKey(changed), true, 1, Date.parse(stamp))).toBeNull();
    for (const different of [
      { ...context, scope: { projectId: 8, workspaceId: 9 } },
      { ...context, scope: { projectId: 7, workspaceId: 10 } },
      { ...context, identity: { ...context.identity, principal: { ...context.identity.principal!, session_id: "new-session" } } },
      { ...context, identity: { ...context.identity, principal: { ...context.identity.principal!, principal_id: "different-person" } } },
    ]) expect(runnerMutationKey(different)).not.toBe(runnerMutationKey(context));
  });
  it("anchors secret retention to server time even when the browser clock starts a day behind", () => {
    const key = runnerAccessKey(context), expiresAt = "2026-11-05T00:05:00Z";
    const deadline = runnerSecretDeadline(expiresAt, stamp, 1000, 2000);
    expect(deadline).toBe(300_000);
    const secret: RunnerSecret = { key, kind: "enrollment", runnerId: "runner-one", token: "ephemeral-value", expiresAt, monotonicDeadline: deadline! };
    const skewedWall = Date.parse(stamp) - 86_400_000;
    expect(visibleRunnerSecret(secret, key, true, 299_999, skewedWall)).toBe(secret);
    expect(visibleRunnerSecret(secret, key, true, 300_000, skewedWall)).toBeNull();
    // A client clock ahead can only shorten the reveal, never extend it.
    expect(visibleRunnerSecret(secret, key, true, 2000, Date.parse(expiresAt))).toBeNull();
  });
  it("subtracts server timestamp precision and rejects invalid or excessive reveal windows", () => {
    expect(runnerSecretDeadline("2026-11-05T00:00:01Z", stamp, 1000, 1000)).toBeNull();
    expect(runnerSecretDeadline("2026-11-06T00:00:00Z", stamp, 1000, 1000)).toBeNull();
    expect(runnerSecretDeadline("invalid", stamp, 1000, 2000)).toBeNull();
    expect(runnerSecretDeadline("2026-11-05T00:05:00Z", stamp, 2000, 1000)).toBeNull();
    expect(runnerSecretDeadline("2026-11-05T00:05:00Z", stamp, 1000, 301_000)).toBeNull();
  });
  it("reveals the complete enrollment metadata separately and clears it with the token", () => {
    const key = runnerAccessKey(context);
    const enrollment = { version: 1 as const, audience: "runner-enrollment-v1" as const, enrollment_id: "enrollment-one", runner_id: "runner-one", project_id: "7", workspace_id: "9", expires_at: "2026-11-05T00:05:00Z", one_use: true as const };
    const secret: RunnerSecret = { key, kind: "enrollment", runnerId: "runner-one", token: "ephemeral-token", expiresAt: enrollment.expires_at, monotonicDeadline: 300000, enrollment };
    const html = renderToStaticMarkup(<RunnerSecretPanel secret={secret} onClose={() => {}} />);
    expect(html).toContain("Enrollment JSON"); expect(html).toContain("enrollment-one"); expect(html).toContain("ephemeral-token");
    expect(html.slice(html.indexOf("<textarea"), html.indexOf("</textarea>"))).not.toContain("ephemeral-token");
    for (const filtered of [null, visibleRunnerSecret(secret, "different-scope", true, 1, Date.parse(stamp)), visibleRunnerSecret(secret, key, true, 300000, Date.parse(stamp))]) {
      const cleared = renderToStaticMarkup(<RunnerSecretPanel secret={filtered} onClose={() => {}} />);
      expect(cleared).not.toContain("enrollment-one"); expect(cleared).not.toContain("ephemeral-token");
    }
  });
  it("bounds tags before sending enrollment", () => {
    expect(parseRunnerTags("isolated, linux-arm64")).toEqual(["isolated", "linux-arm64"]);
    for (const raw of ["bad/path", "first,,second", Array.from({ length: 17 }, (_, i) => `tag-${i}`).join(",")]) expect(parseRunnerTags(raw)).toBeNull();
  });
});
