import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { IdentityContextValue } from "./IdentitySession";
import { AccountAccessContent } from "./AccountAccess";

const { state } = vi.hoisted(() => ({ state: { value: {} as IdentityContextValue } }));
vi.mock("./IdentitySession", () => ({ useIdentity: () => state.value }));
beforeEach(() => {
  state.value = { principal: null, csrfToken: null, loading: false, epoch: 0, status: "signed-out", error: null, signIn: vi.fn(), signOut: vi.fn(), refresh: vi.fn(), expire: vi.fn() };
});
function render() { return renderToStaticMarkup(<MemoryRouter><AccountAccessContent /></MemoryRouter>); }
describe("account access", () => {
  it("provides labeled local credentials and operator-held recovery guidance", () => {
    const html = render();
    expect(html).toContain('for="account-username"');
    expect(html).toContain('for="account-password"');
    expect(html).toContain('type="password"');
    expect(html).toContain('autoComplete="current-password"');
    expect(html).toContain("trusted application host");
    expect(html).toContain("python -m cli.identity");
  });
  it.each(["Sign-in failed. Check your username and password.", "Your session expired or access was revoked. Sign in again before continuing.", "Account access is unavailable."])("announces readable failure: %s", (message) => {
    state.value.error = message;
    const html = render();
    expect(html).toContain(`role="alert">${message}`);
    expect(html).toContain('tabindex="-1"');
  });
  it("requires signing in again after read-only cookie restoration without pretending logout", () => {
    state.value.principal = { username: "operator", principal_id: "1", principal_type: "human", is_admin: false, enabled: true, authentication_version: 1, credential_audience: "human", session_id: "session", expires_at: "2026-10-28T18:00:00Z", security_profile: "local-development", production_eligible: false };
    const html = render();
    expect(html).toContain("Your session was restored for reading");
    expect(html).toContain("Sign in again");
    expect(html).not.toContain(">Sign out</button>");
    expect(html).toContain('type="password"');
  });
  it("offers server logout only with live in-memory mutation protection", () => {
    state.value.principal = { username: "operator" } as IdentityContextValue["principal"];
    state.value.status = "ready";
    state.value.csrfToken = "never-render-this-secret";
    const html = render();
    expect(html).toContain(">Sign out</button>");
    expect(html).not.toContain("never-render-this-secret");
    expect(html).not.toContain('type="password"');
  });
  it("labels last-known identity as unverified and offers verification or re-login", () => {
    state.value.principal = { username: "operator" } as IdentityContextValue["principal"];
    state.value.csrfToken = "never-render-this-secret";
    state.value.status = "unavailable";
    const html = render();
    expect(html).toContain("Last verified account");
    expect(html).toContain(">Verify access again</button>");
    expect(html).toContain('type="password"');
    expect(html).not.toContain("Signed in as");
    expect(html).not.toContain(">Sign out</button>");
    expect(html).not.toContain("never-render-this-secret");
  });

});
