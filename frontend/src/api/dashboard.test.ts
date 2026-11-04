import { afterEach, describe, expect, it, vi } from "vitest";
import { createProject, getProjects, getProjectsForCreation } from "./dashboard";

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
const project = { id: 7, project_key: "synthetic", display_name: "Synthetic" };
describe("project creation", () => {
  it.each([null, "transient-csrf"])("posts only supported fields and current CSRF (%s)", async (csrf) => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ data: project, meta: {} }));
    vi.stubGlobal("fetch", fetcher);
    await expect(createProject({ project_key: "synthetic", display_name: "Synthetic", description: "Synthetic fixture" }, csrf)).resolves.toEqual(project);
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [path, init] = fetcher.mock.calls[0];
    expect(path).toBe("/api/v1/projects");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(JSON.parse(init.body)).toEqual({ project_key: "synthetic", display_name: "Synthetic", description: "Synthetic fixture" });
    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe(csrf);
    expect(headers.has("X-DeployWhisper-Project-Role")).toBe(false);
    expect(headers.has("X-DeployWhisper-Actor")).toBe(false);
  });
  it.each([{}, null, { ...project, id: "7" }, { ...project, id: -1 }, { ...project, project_key: null }, { ...project, project_key: "unrelated" }])("rejects malformed success without retrying", async (data) => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ data, meta: {} }));
    vi.stubGlobal("fetch", fetcher);
    await expect(createProject({ project_key: "synthetic", display_name: "Synthetic" })).rejects.toMatchObject({ status: 200 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it.each([" Uppercase ", "with_underscore", "trailing-", ""]) ("rejects noncanonical keys before POST: %s", async (project_key) => {
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
    await expect(createProject({ project_key, display_name: "Synthetic" })).rejects.toMatchObject({ status: 422 });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("bounds a stalled POST and leaves timeout ambiguous without replay", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn((_path, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal!.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    vi.stubGlobal("fetch", fetcher);
    const result = createProject({ project_key: "synthetic", display_name: "Synthetic" }).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(await result).toMatchObject({ name: "AbortError" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("does not retry failed creation or reflect server text", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ error: { message: "sensitive-internal-detail" } }, { status: 400 }));
    vi.stubGlobal("fetch", fetcher);
    await expect(createProject({ project_key: "synthetic", display_name: "Synthetic" })).rejects.toMatchObject({ status: 400, message: "Request failed." });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

describe("project recovery reads", () => {
  it("forwards query cancellation to the actual fetch", async () => {
    const controller = new AbortController();
    const fetcher = vi.fn().mockResolvedValue(Response.json({ data: [], meta: {} }));
    vi.stubGlobal("fetch", fetcher);
    await getProjects({ signal: controller.signal });
    expect(fetcher.mock.calls[0][1].signal).toBe(controller.signal);
  });
  it("aborts a stalled recovery read without creating or replaying a project", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn((_path, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal!.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    vi.stubGlobal("fetch", fetcher);
    const outcome = getProjectsForCreation().catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(await outcome).toMatchObject({ name: "AbortError" });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/projects");
    expect(fetcher.mock.calls[0][1].method).toBeUndefined();
    expect(vi.getTimerCount()).toBe(0);
  });
});
