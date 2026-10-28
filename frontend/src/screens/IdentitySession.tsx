import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiClientError } from "../api/client";
import { getIdentitySession, loginIdentity, logoutIdentity, type IdentityPrincipal } from "../api/identity";

export interface IdentityContextValue {
  principal: IdentityPrincipal | null;
  csrfToken: string | null;
  loading: boolean;
  epoch: number;
  status: "signed-out" | "ready" | "expired" | "unavailable";
  error: string | null;
  signIn(username: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  refresh(): Promise<IdentityPrincipal | null>;
  expire(): void;
}
const unavailable = async () => { throw new Error("Account access is unavailable."); };
const IdentityContext = createContext<IdentityContextValue>({
  principal: null, csrfToken: null, loading: false, epoch: 0, status: "signed-out", error: null,
  signIn: unavailable, signOut: unavailable, refresh: async () => null, expire: () => {},
});
export const useIdentity = () => useContext(IdentityContext);

export function IdentityProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<Pick<IdentityContextValue, "principal" | "csrfToken" | "loading" | "epoch" | "status" | "error">>({
    principal: null, csrfToken: null, loading: true, epoch: 0, status: "signed-out", error: null,
  });
  const current = useRef(state);
  current.current = state;
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const clearProtectedData = useCallback(() => {
    // Cancellation reaches query AbortSignals before cached protected data is removed.
    void queryClient.cancelQueries();
    queryClient.clear();
  }, [queryClient]);
  const expire = useCallback(() => {
    // Anonymous password challenges and disabled identity are not human-session loss.
    if (!current.current.principal && !current.current.csrfToken) return;
    generation.current += 1;
    pending.current?.abort();
    clearProtectedData();
    const next = { principal: null, csrfToken: null, loading: false, epoch: current.current.epoch + 1, status: "expired" as const, error: "Your session expired or access was revoked. Sign in again before continuing." };
    current.current = next;
    setState(next);
  }, [clearProtectedData]);
  const refresh = useCallback(async (): Promise<IdentityPrincipal | null> => {
    // A session read does not restore CSRF material lost on page reload.
    const operation = ++generation.current;
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    try {
      const principal = await getIdentitySession(controller.signal);
      if (operation !== generation.current) return null;
      const previous = current.current;
      const changed = previous.principal?.session_id !== principal.session_id;
      if (changed) clearProtectedData();
      setState({ principal, csrfToken: changed ? null : previous.csrfToken, loading: false, epoch: previous.epoch + (changed ? 1 : 0), status: "ready", error: null });
      return principal;
    } catch (error) {
      if (operation !== generation.current) return null;
      if (error instanceof ApiClientError && error.status === 401) {
        if (current.current.principal) expire();
        else setState((previous) => ({ ...previous, loading: false, status: previous.status === "expired" ? "expired" : "signed-out" }));
      } else if (error instanceof TypeError || (error instanceof ApiClientError && error.status === 503)) {
        // A transport failure is not evidence that the identity changed. Keep
        // same-scope form state, but withhold fresh authority until reverified.
        setState((previous) => ({ ...previous, loading: false, status: "unavailable", error: "Account access could not be verified. Verify access again before making changes; your unsaved edits remain on this page." }));
      } else {
        const hadAuthority = Boolean(current.current.principal || current.current.csrfToken);
        if (hadAuthority) clearProtectedData();
        setState((previous) => ({ principal: null, csrfToken: null, loading: false, epoch: previous.epoch + (hadAuthority ? 1 : 0), status: "unavailable", error: "Account access is unavailable. Ask the application operator to check identity configuration and availability." }));
      }
      return null;
    }
  }, [clearProtectedData, expire]);
  const signIn = useCallback(async (username: string, password: string) => {
    const operation = ++generation.current;
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    clearProtectedData();
    setState((previous) => ({ principal: null, csrfToken: null, loading: true, epoch: previous.epoch + 1, status: "signed-out", error: null }));
    try {
      const issued = await loginIdentity(username, password, controller.signal);
      if (operation !== generation.current) throw new Error("Account access changed. Sign in again.");
      clearProtectedData();
      setState((previous) => ({ principal: issued.principal, csrfToken: issued.csrf_token, loading: false, epoch: previous.epoch + 1, status: "ready", error: null }));
    } catch (error) {
      if (operation !== generation.current) throw new Error("Account access changed. Sign in again.");
      const message = error instanceof ApiClientError && error.status === 429
        ? "Too many sign-in attempts. Wait before trying again."
        : error instanceof ApiClientError && error.status === 401
          ? "Sign-in failed. Check your username and password."
          : "Sign-in is unavailable. Ask the application operator to check identity configuration and availability.";
      setState((previous) => ({ ...previous, loading: false, error: message }));
      throw new Error(message);
    }
  }, [clearProtectedData]);
  const signOut = useCallback(async () => {
    if (current.current.status !== "ready") throw new Error("Verify access again or sign in before signing out. Your server session has not been logged out.");
    const csrf = current.current.csrfToken;
    if (!csrf) throw new Error("Sign in again to obtain mutation protection before signing out. Your server session has not been logged out.");
    const operation = ++generation.current;
    pending.current?.abort();
    clearProtectedData();
    setState((previous) => ({ ...previous, loading: true, epoch: previous.epoch + 1, error: null }));
    try {
      await logoutIdentity(csrf);
      if (operation !== generation.current) return;
      clearProtectedData();
      setState((previous) => ({ principal: null, csrfToken: null, loading: false, epoch: previous.epoch + 1, status: "signed-out", error: null }));
    } catch (error) {
      if (operation !== generation.current) return;
      if (error instanceof ApiClientError && error.status === 401) { expire(); return; }
      const message = "Sign-out was not confirmed. Your server session may still be active. Sign in again or contact the operator.";
      setState((previous) => ({ ...previous, csrfToken: null, loading: false, error: message }));
      throw new Error(message);
    }
  }, [clearProtectedData, expire]);
  useEffect(() => {
    void refresh();
    const check = () => { if (document.visibilityState === "visible" && !current.current.loading) void refresh(); };
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("dw:identity-expired", expire);
    return () => { generation.current += 1; pending.current?.abort(); window.removeEventListener("focus", check); document.removeEventListener("visibilitychange", check); window.removeEventListener("dw:identity-expired", expire); };
  }, [refresh, expire]);
  useEffect(() => {
    if (!state.principal) return;
    const remaining = Date.parse(state.principal.expires_at) - Date.now();
    if (!Number.isFinite(remaining) || remaining <= 0) { expire(); return; }
    const timer = window.setTimeout(expire, Math.min(remaining, 2_147_483_647));
    return () => window.clearTimeout(timer);
  }, [state.principal, expire]);
  return <IdentityContext.Provider value={{ ...state, signIn, signOut, refresh, expire }}>{children}</IdentityContext.Provider>;
}
