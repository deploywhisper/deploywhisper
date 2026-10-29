import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { IdentityProvider, useIdentity, type IdentityContextValue } from "./IdentitySession";
import { ApiClientError } from "../api/client";
import { getIdentitySession, loginIdentity, logoutIdentity, type IdentityPrincipal } from "../api/identity";

function Consumer() {
  const identity = useIdentity();
  return <span>{JSON.stringify({ principal: identity.principal, csrfToken: identity.csrfToken, loading: identity.loading, epoch: identity.epoch })}</span>;
}
describe("identity default context", () => {
  it("preserves safe signed-out rendering outside provider", () => {
    const html = renderToStaticMarkup(<Consumer />);
    expect(html).toContain("&quot;principal&quot;:null");
    expect(html).toContain("&quot;csrfToken&quot;:null");
    expect(html).toContain("&quot;loading&quot;:false");
  });
});

// Exercise the actual provider callbacks with deterministic hook state; no browser
// renderer is installed in this node-only test lane.
const harness = vi.hoisted(() => ({
  state: undefined as unknown, refs: [] as { current: unknown }[], refIndex: 0,
  effects: [] as (() => unknown)[], captureEffects: false,
  cache: { cancelQueries: vi.fn().mockResolvedValue(undefined), clear: vi.fn() },
}));
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => {
    if (harness.state === undefined) harness.state = initial;
    return [harness.state, (next: unknown) => { harness.state = typeof next === "function" ? next(harness.state) : next; }];
  },
  useRef: (initial: unknown) => {
    const index = harness.refIndex++;
    return harness.refs[index] ?? (harness.refs[index] = { current: initial });
  },
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => unknown) => { if (harness.captureEffects) harness.effects.push(effect); },
}));
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => harness.cache }));
vi.mock("../api/identity", () => ({ getIdentitySession: vi.fn(), loginIdentity: vi.fn(), logoutIdentity: vi.fn() }));

const principal = { principal_id: "p1", session_id: "s1", expires_at: "2099-01-01T00:00:00Z" } as IdentityPrincipal;
function provider() {
  harness.refIndex = 0;
  return IdentityProvider({ children: null }).props.value as IdentityContextValue;
}
beforeEach(() => {
  harness.state = undefined;
  harness.refs = [];
  harness.effects = [];
  harness.captureEffects = false;
  vi.clearAllMocks();
});
afterEach(() => vi.unstubAllGlobals());

describe("identity provider cache boundary", () => {
  it.each([403, 503])("preserves anonymous cached screens when session read fails with %s", async (status) => {
    vi.mocked(getIdentitySession).mockRejectedValue(new ApiClientError("denied", status));
    await provider().refresh();
    await provider().refresh();
    expect(provider().status).toBe("unavailable");
    expect(provider().epoch).toBe(0);
    expect(harness.cache.cancelQueries).not.toHaveBeenCalled();
    expect(harness.cache.clear).not.toHaveBeenCalled();
  });
  it("ignores repeated anonymous unauthorized events without clearing public caches", async () => {
    const browser = new EventTarget();
    vi.stubGlobal("window", browser);
    vi.stubGlobal("document", Object.assign(new EventTarget(), { visibilityState: "visible" }));
    vi.mocked(getIdentitySession).mockRejectedValue(new ApiClientError("anonymous", 401));
    harness.captureEffects = true;
    provider();
    harness.captureEffects = false;
    const cleanup = harness.effects[0]() as () => void;
    await Promise.resolve();
    provider();
    browser.dispatchEvent(new Event("dw:identity-expired"));
    browser.dispatchEvent(new Event("dw:identity-expired"));
    expect(provider().status).toBe("signed-out");
    expect(provider().epoch).toBe(0);
    expect(harness.cache.clear).not.toHaveBeenCalled();
    cleanup();
  });
  it("expires a live human once for a burst of unauthorized events", async () => {
    const browser = new EventTarget();
    vi.stubGlobal("window", browser);
    vi.stubGlobal("document", Object.assign(new EventTarget(), { visibilityState: "visible" }));
    vi.mocked(getIdentitySession).mockResolvedValueOnce(principal);
    harness.captureEffects = true;
    provider();
    harness.captureEffects = false;
    const cleanup = harness.effects[0]() as () => void;
    await Promise.resolve();
    expect(provider().principal).toBe(principal);
    vi.clearAllMocks();
    browser.dispatchEvent(new Event("dw:identity-expired"));
    browser.dispatchEvent(new Event("dw:identity-expired"));
    expect(provider().status).toBe("expired");
    expect(provider().principal).toBeNull();
    expect(harness.cache.cancelQueries).toHaveBeenCalledOnce();
    expect(harness.cache.clear).toHaveBeenCalledOnce();
    cleanup();
  });
  it("clears protected caches and expires an existing human on session 401", async () => {
    vi.mocked(getIdentitySession).mockResolvedValueOnce(principal);
    await provider().refresh();
    provider();
    vi.clearAllMocks();
    vi.mocked(getIdentitySession).mockRejectedValueOnce(new ApiClientError("revoked", 401));
    await provider().refresh();
    expect(provider().status).toBe("expired");
    expect(provider().principal).toBeNull();
    expect(harness.cache.cancelQueries).toHaveBeenCalledOnce();
    expect(harness.cache.clear).toHaveBeenCalledOnce();
    expect(harness.cache.cancelQueries.mock.invocationCallOrder[0]).toBeLessThan(harness.cache.clear.mock.invocationCallOrder[0]);
  });
  it.each([new ApiClientError("unavailable", 503), new TypeError("Network unavailable")])("preserves same-scope edits but requires fresh verification on transient session loss: %s", async (error) => {
    vi.mocked(getIdentitySession).mockResolvedValueOnce(principal);
    await provider().refresh();
    const before = provider();
    vi.clearAllMocks();
    vi.mocked(getIdentitySession).mockRejectedValueOnce(error);
    expect(await before.refresh()).toBeNull();
    expect(provider().principal).toBe(principal);
    expect(provider().epoch).toBe(before.epoch);
    expect(provider().status).toBe("unavailable");
    expect(provider().error).toContain("Verify access again");
    expect(harness.cache.cancelQueries).not.toHaveBeenCalled();
    expect(harness.cache.clear).not.toHaveBeenCalled();
    vi.mocked(getIdentitySession).mockResolvedValueOnce(principal);
    expect(await provider().refresh()).toBe(principal);
    expect(provider().status).toBe("ready");
    expect(provider().epoch).toBe(before.epoch);
    expect(harness.cache.clear).not.toHaveBeenCalled();
  });
  it("keeps CSRF only in memory through transient failure and blocks unverified logout", async () => {
    vi.mocked(loginIdentity).mockResolvedValueOnce({ principal, csrf_token: "memory-only" });
    await provider().signIn("operator", "password");
    const before = provider();
    vi.clearAllMocks();
    vi.mocked(getIdentitySession).mockRejectedValueOnce(new TypeError("offline"));
    await before.refresh();
    expect(provider().csrfToken).toBe("memory-only");
    expect(provider().epoch).toBe(before.epoch);
    await expect(provider().signOut()).rejects.toThrow("Verify access again");
    expect(logoutIdentity).not.toHaveBeenCalled();
    expect(harness.cache.clear).not.toHaveBeenCalled();
  });
  it("still expires an unavailable last-known session at its absolute deadline", async () => {
    const expiredPrincipal = { ...principal, expires_at: new Date(Date.now() - 100).toISOString() };
    vi.mocked(getIdentitySession).mockResolvedValueOnce(expiredPrincipal);
    await provider().refresh();
    provider();
    vi.mocked(getIdentitySession).mockRejectedValueOnce(new TypeError("offline"));
    await provider().refresh();
    expect(provider().status).toBe("unavailable");
    harness.effects = [];
    harness.captureEffects = true;
    provider();
    harness.captureEffects = false;
    harness.effects[1]();
    expect(provider().status).toBe("expired");
    expect(provider().principal).toBeNull();
  });
  it("never returns authority from a superseded session read", async () => {
    let finishStale!: (value: IdentityPrincipal) => void;
    const stale = new Promise<IdentityPrincipal>((resolve) => { finishStale = resolve; });
    vi.mocked(getIdentitySession).mockReturnValueOnce(stale).mockResolvedValueOnce(principal);
    const oldRead = provider().refresh();
    const freshRead = provider().refresh();
    expect(await freshRead).toBe(principal);
    finishStale({ ...principal, session_id: "stale-session" });
    expect(await oldRead).toBeNull();
    expect(provider().principal).toBe(principal);
  });
  it("clears prior human authority on definite session denial", async () => {
    vi.mocked(getIdentitySession).mockResolvedValueOnce(principal);
    await provider().refresh();
    const before = provider();
    vi.clearAllMocks();
    vi.mocked(getIdentitySession).mockRejectedValueOnce(new ApiClientError("denied", 403));
    await before.refresh();
    expect(provider().principal).toBeNull();
    expect(provider().epoch).toBe(before.epoch + 1);
    expect(harness.cache.clear).toHaveBeenCalledOnce();
  });
});
