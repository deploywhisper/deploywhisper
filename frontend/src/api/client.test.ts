import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClientError, requestData } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("API transport", () => {
  it("preserves the legacy provider failure label without reflecting query or body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(Response.json({ error: { message: "private-server-value" } }, { status: 403 }))));
    await expect(requestData("/api/v1/settings/provider?token=private-query-value")).rejects.toMatchObject({ message: "Request failed: /api/v1/settings/provider", status: 403 });
    const failure = await requestData("/api/v1/settings/provider").catch((error: Error) => error);
    expect(String(failure)).not.toContain("private");
  });

  it.each([
    "/api/v1/analyses/15/shared",
    "/api/v1/analyses/15/shared?compare=previous",
    "/api/v1/analyses/15/shared/unlock?compare=previous",
    "/api/v1/auth/login",
    "/api/v1/auth/session",
  ])("does not expire identity for an independently handled challenge: %s", async (path) => {
    const dispatchEvent = vi.fn();
    vi.stubGlobal("window", { dispatchEvent });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({}, { status: 401 })));
    await expect(requestData(path)).rejects.toMatchObject({ status: 401 });
    expect(dispatchEvent).not.toHaveBeenCalled();
  });

  it("dispatches one identity-expired event for a protected automation 401", async () => {
    const dispatchEvent = vi.fn();
    vi.stubGlobal("window", { dispatchEvent });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({}, { status: 401 })));
    await expect(requestData("/api/v1/infra-automation/runs?project_id=1")).rejects.toMatchObject({ status: 401 });
    expect(dispatchEvent).toHaveBeenCalledTimes(1);
    expect(dispatchEvent.mock.calls[0][0].type).toBe("dw:identity-expired");
  });

  it.each([new Headers({ "X-CSRF-Token": "transient" }), [["X-CSRF-Token", "transient"]] as [string, string][]])("merges HeadersInit with Accept", async (headers) => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ data: 1, meta: {} }));
    vi.stubGlobal("fetch", fetcher);
    await expect(requestData("/api/test", { headers })).resolves.toBe(1);
    const sent = new Headers(fetcher.mock.calls[0][1].headers);
    expect(sent.get("Accept")).toBe("application/json");
    expect(sent.get("X-CSRF-Token")).toBe("transient");
  });

  it("preserves status on non-JSON failures without exposing body or URL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private server output", { status: 503 })));
    await expect(requestData("/api/private-token")).rejects.toMatchObject({ name: "ApiClientError", status: 503 });
    await expect(requestData("/api/private-token")).rejects.toThrow(/^Request failed\.$/);
  });

  it("projects only recognized error metadata", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ error: {
      code: "binding_conflict", message: "raw secret", details: { retryable: false, correlation_id: "a".repeat(32), raw: "secret" },
    } }, { status: 409 })));
    const error = await requestData("/api/test").catch((failure: unknown) => failure);
    expect(error).toMatchObject({ status: 409, code: "binding_conflict", retryable: false, correlationId: "a".repeat(32) });
    expect(JSON.stringify(error)).not.toContain("secret");
  });

  it("discards unrecognized metadata and malformed success bodies", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ error: { code: "private-value", details: { retryable: "yes", correlation_id: "private-value" } } }, { status: 403 })));
    await expect(requestData("/api/test")).rejects.toMatchObject({ code: undefined, retryable: undefined, correlationId: undefined });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not JSON", { status: 200 })));
    await expect(requestData("/api/test")).rejects.toBeInstanceOf(ApiClientError);
    expect(new ApiClientError("legacy", 403).message).toBe("legacy");
  });
});
