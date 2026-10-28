import { requestData } from "./client";
import type { components } from "./schema";

export type IdentityPrincipal = components["schemas"]["VerifiedPrincipal"];
export interface IdentitySession { principal: IdentityPrincipal; csrf_token: string }
const authRequest = { credentials: "same-origin", cache: "no-store" } as const;

export function getIdentitySession(signal?: AbortSignal): Promise<IdentityPrincipal> {
  return requestData("/api/v1/auth/session", { ...authRequest, method: "GET", signal });
}
export function loginIdentity(username: string, password: string, signal?: AbortSignal): Promise<IdentitySession> {
  return requestData("/api/v1/auth/login", {
    ...authRequest, method: "POST", signal, headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}
export function logoutIdentity(csrfToken: string, signal?: AbortSignal): Promise<{ logged_out: boolean }> {
  return requestData("/api/v1/auth/logout", {
    ...authRequest, method: "POST", signal, headers: { "X-CSRF-Token": csrfToken },
  });
}

/** Return only to known read views. Never carry credentials or a mutation intent. */
export function safeAccountReturnTo(value: string | null | undefined): string {
  const fallback = "/infra-automation";
  if (!value || /[\\%#\u0000-\u0020\u007f]/.test(value) || !value.startsWith("/") || value.startsWith("//")) return fallback;
  const [path, query] = value.split("?");
  if (value.split("?").length > 2) return fallback;
  const identifier = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
  const positiveId = (item: string) => /^[1-9]\d*$/.test(item) && Number.isSafeInteger(Number(item));
  const report = /^\/reports\/([^/]+)$/.exec(path);
  const automation = /^\/infra-automation(?:\/(workflows|runs)(?:\/([^/]+))?)?$/.exec(path);
  const basic = /^(?:\/(?:history|settings|skills|incidents)?)$/.test(path);
  if (!(basic || (report && positiveId(report[1])) || (automation && (!automation[2] || identifier.test(automation[2]))))) return fallback;
  if (query !== undefined) {
    const seen = new Set<string>();
    if (!query || query.split("&").some((pair) => {
      const parts = pair.split("=");
      if (parts.length !== 2) return true;
      const [key, item] = parts;
      if (seen.has(key)) return true;
      seen.add(key);
      if (key === "project_id" || key === "workspace_id") return !positiveId(item);
      if (report && key === "private") return item !== "1";
      if (report && key === "automation_run") return !identifier.test(item);
      return true;
    })) return fallback;
  }
  return value;
}
