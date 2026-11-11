import { isValidElement, type ReactElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AutomationSettingsSection, automationSettingsAccessKey } from "./AutomationSettingsSection";
import { ApiClientError } from "../api/client";
import { saveAutomationSettings, type AutomationPolicy } from "../api/infraAutomationSettings";

// This repository's unit runner has no DOM renderer. Exercise the real form
// callbacks with persistent hook slots; composed Playwright covers the browser.
const harness = vi.hoisted(() => ({
  state: [] as unknown[], accessState: [] as unknown[], scope: "form", stateIndex: 0, refs: [] as { current: unknown }[], refIndex: 0,
  policy: {} as Record<string, unknown>, membership: {} as Record<string, unknown>,
  invalidate: vi.fn(),
}));
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => {
    const index = harness.stateIndex++;
    const state = harness.scope === "access" ? harness.accessState : harness.state;
    if (!(index in state)) state[index] = initial;
    return [state[index], (next: unknown) => { state[index] = typeof next === "function" ? next(state[index]) : next; }];
  },
  useRef: (initial: unknown) => {
    const index = harness.refIndex++;
    return harness.refs[index] ?? (harness.refs[index] = { current: initial });
  },
  useEffect: () => {},
}));
vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey }: { queryKey: string[] }) => queryKey[0] === "automation-settings-memberships" ? harness.membership : harness.policy,
  useQueryClient: () => ({ invalidateQueries: harness.invalidate }),
}));
vi.mock("./IdentitySession", () => ({ useIdentity: () => ({ status: "ready", epoch: 1, csrfToken: "csrf", principal: { principal_id: "admin", principal_type: "human", session_id: "session" } }) }));
vi.mock("../api/infraAutomationSettings", async (original) => ({ ...await original<typeof import("../api/infraAutomationSettings")>(), saveAutomationSettings: vi.fn() }));

type Element = ReactElement<Record<string, unknown>>;
const policy: AutomationPolicy = { project_id: 7, version: 1, authorization_epoch: 1, restore_epoch: 1, settings: { enabled: false, max_workflows: 100, max_revisions_per_workflow: 100, max_active_runs: 10, max_queued_runs: 100, max_artifact_bytes: 8388608, retention_seconds: 604800, evidence_ttl_seconds: 3600, approval_ttl_seconds: 900, credential_ttl_seconds: 900 } };
function elements(node: ReactNode): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
function access() {
  harness.scope = "access"; harness.stateIndex = 0; harness.refIndex = 0;
  const element = AutomationSettingsSection({ projectId: 7, projectKey: "project" });
  return (element.type as (props: typeof element.props) => ReactNode)(element.props);
}
function formElement(): Element | undefined {
  const form = elements(access()).find((element) => typeof element.type === "function" && element.type.name === "AutomationSettingsForm");
  if (!form) { harness.state = []; harness.refs = []; }
  return form;
}
function renderForm(element: Element): Element[] {
  harness.scope = "form"; harness.stateIndex = 0; harness.refIndex = 0;
  return elements((element.type as (props: typeof element.props) => ReactNode)(element.props));
}
function field(tree: Element[], key: string) { return tree.find((element) => element.props["aria-labelledby"] === `automation-label-${key}`)!; }
function reason(tree: Element[]) { return tree.find((element) => element.props.maxLength === 256)!; }
function change(element: Element, value: string) { (element.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } }); }
async function submit(tree: Element[]) { await (tree[0].props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({ preventDefault: () => {} }); }
async function refresh(tree: Element[]) {
  const button = tree.find((element) => element.props.children === "Refresh automation settings")!;
  await (button.props.onClick as () => Promise<void>)();
}
beforeEach(() => {
  harness.state = []; harness.accessState = []; harness.refs = []; harness.stateIndex = 0; harness.refIndex = 0;
  harness.policy = { data: policy, isSuccess: true, isError: false, isPending: false, isFetching: false, refetch: vi.fn().mockResolvedValue({ data: policy, isSuccess: true }) };
  harness.membership = { data: [{ principal_id: "admin", role: "admin", enabled: true, workspace_id: null }], isSuccess: true, isError: false, isPending: false, isFetching: false, refetch: vi.fn().mockResolvedValue({ isSuccess: true, data: [{ principal_id: "admin", role: "admin", enabled: true, workspace_id: null }] }) };
  vi.clearAllMocks();
});
describe("operator settings access lifetime", () => {
  it("remounts drafts and target state after selected scope, session or identity epoch changes", () => {
    const original = automationSettingsAccessKey(7, 1, "session");
    expect(automationSettingsAccessKey(8, 1, "session")).not.toBe(original);
    expect(automationSettingsAccessKey(7, 2, "session")).not.toBe(original);
    expect(automationSettingsAccessKey(7, 1, "other-session")).not.toBe(original);
  });
  it("does not remount a same-scope draft when policy version or authorization epochs advance", () => {
    const original = formElement()!;
    harness.policy.data = { ...policy, version: 2, authorization_epoch: 2, restore_epoch: 2 };
    expect(formElement()!.key).toBe(original.key);
  });
  it.each(["policy", "membership"] as const)("retains a draft but pauses saves after a transient %s refetch failure", (source) => {
    const original = formElement()!;
    harness[source] = { ...harness[source], isSuccess: false, isError: true, error: new ApiClientError("unavailable", 503) };
    expect(formElement()?.type).toBe(original.type);
    expect(formElement()?.props.editable).toBe(false);
  });
  it.each([["policy", 401], ["policy", 403], ["membership", 401], ["membership", 403]] as const)("clears a draft on definite %s authorization denial %s", (source, status) => {
    harness[source] = { ...harness[source], isSuccess: false, isError: true, error: new ApiClientError("denied", status) };
    expect(formElement()).toBeUndefined();
  });
  it("clears a draft when fresh membership removes administrator permission", () => {
    harness.membership.data = [{ principal_id: "admin", role: "viewer", enabled: true, workspace_id: null }];
    expect(formElement()).toBeUndefined();
  });
  it.each(["version", "authorization_epoch", "restore_epoch"] as const)("retains edited values and reason while blocking a new server %s instead of rebasing the draft", async (key) => {
    const original = formElement()!;
    change(field(renderForm(original), "max_active_runs"), "7");
    change(reason(renderForm(original)), "Unsaved capacity decision");
    harness.policy.data = { ...policy, [key]: policy[key] + 1, settings: { ...policy.settings, max_queued_runs: 90 } };
    const tree = renderForm(formElement()!);
    expect(field(tree, "max_active_runs").props.value).toBe(7);
    expect(reason(tree).props.value).toBe("Unsaved capacity decision");
    await submit(tree);
    expect(saveAutomationSettings).not.toHaveBeenCalled();
    expect(tree.find((element) => element.props.type === "submit")!.props.disabled).toBe(true);
    expect(tree.some((element) => typeof element.props.children === "string" && element.props.children.includes("changed on the server"))).toBe(true);
  });
  it("explicit refresh replaces values and base version with the returned fresh policy, then saves that version", async () => {
    const element = formElement()!;
    change(field(renderForm(element), "max_active_runs"), "7");
    change(reason(renderForm(element)), "Unsaved old reason");
    const fresh = { ...policy, version: 2, settings: { ...policy.settings, max_active_runs: 8 } };
    vi.mocked(harness.policy.refetch as ReturnType<typeof vi.fn>).mockResolvedValue({ isSuccess: true, data: fresh });
    await refresh(renderForm(element));
    expect(field(renderForm(element), "max_active_runs").props.value).toBe(8);
    expect(reason(renderForm(element)).props.value).toBe("");
    harness.policy.data = fresh;
    change(reason(renderForm(formElement()!)), "Reviewed latest settings");
    vi.mocked(saveAutomationSettings).mockResolvedValue({ ...fresh, version: 3 });
    await submit(renderForm(formElement()!));
    expect(saveAutomationSettings).toHaveBeenCalledWith(7, 2, fresh.settings, "Reviewed latest settings", "csrf");
  });
  it.each(["policy", "membership"] as const)("keeps values and reason when explicit %s refresh fails", async (source) => {
    const element = formElement()!;
    change(field(renderForm(element), "max_active_runs"), "7");
    change(reason(renderForm(element)), "Keep this unsaved reason");
    vi.mocked(harness[source].refetch as ReturnType<typeof vi.fn>).mockResolvedValue({ isSuccess: false, error: new ApiClientError("unavailable", 503) });
    await refresh(renderForm(element));
    expect(field(renderForm(element), "max_active_runs").props.value).toBe(7);
    expect(reason(renderForm(element)).props.value).toBe("Keep this unsaved reason");
    expect(saveAutomationSettings).not.toHaveBeenCalled();
    if (source === "membership") expect(harness.policy.refetch).not.toHaveBeenCalled();
  });
  it.each([401, 403])("clears a draft on save-side denial %s until both explicit fresh access and policy checks succeed", async (status) => {
    const element = formElement()!;
    change(field(renderForm(element), "max_active_runs"), "7");
    change(reason(renderForm(element)), "Must clear after a definite authorization denial");
    vi.mocked(saveAutomationSettings).mockRejectedValue(new ApiClientError("denied", status));
    await submit(renderForm(element));
    expect(harness.policy.isSuccess).toBe(true); expect(harness.membership.isSuccess).toBe(true);
    expect(formElement()).toBeUndefined();
    // Cached and unrelated background success must not regrant the denied form.
    expect(formElement()).toBeUndefined();
    vi.mocked(harness.membership.refetch as ReturnType<typeof vi.fn>).mockResolvedValue({ isSuccess: false });
    await refresh(elements(access()));
    expect(formElement()).toBeUndefined();
    expect(harness.policy.refetch).not.toHaveBeenCalled();
    vi.mocked(harness.membership.refetch as ReturnType<typeof vi.fn>).mockResolvedValue({ isSuccess: true, data: harness.membership.data });
    vi.mocked(harness.policy.refetch as ReturnType<typeof vi.fn>).mockResolvedValue({ isSuccess: false });
    await refresh(elements(access()));
    expect(formElement()).toBeUndefined();
    const fresh = { ...policy, version: 2, settings: { ...policy.settings, max_active_runs: 8 } };
    harness.policy.data = fresh;
    vi.mocked(harness.policy.refetch as ReturnType<typeof vi.fn>).mockResolvedValue({ isSuccess: true, data: fresh });
    await refresh(elements(access()));
    await vi.waitFor(() => expect(formElement()).toBeDefined());
    expect(field(renderForm(formElement()!), "max_active_runs").props.value).toBe(8);
    expect(reason(renderForm(formElement()!)).props.value).toBe("");
  });
  it.each([409, 422, 503])("retains a draft after save-side %s without treating it as permission revocation", async (status) => {
    const element = formElement()!;
    change(field(renderForm(element), "max_active_runs"), "7");
    change(reason(renderForm(element)), "Keep this draft after a non-auth save failure");
    vi.mocked(saveAutomationSettings).mockRejectedValue(new ApiClientError("rejected", status));
    await submit(renderForm(element));
    const tree = renderForm(formElement()!);
    expect(field(tree, "max_active_runs").props.value).toBe(7);
    expect(reason(tree).props.value).toBe("Keep this draft after a non-auth save failure");
    expect(tree.find((element) => element.props.type === "submit")!.props.disabled).toBe(true);
  });
});
