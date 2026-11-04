import type { QueryClient } from "@tanstack/react-query";
import type { Project } from "../api/dashboard";

export type ProjectCreationState = {
  name: string; key: string; description: string; pending: boolean;
  uncertain: boolean; checking: boolean; message: string; created: Project | null;
};
export const emptyProjectCreation = (): ProjectCreationState => ({ name: "", key: "", description: "", pending: false, uncertain: false, checking: false, message: "", created: null });
function makeSession(epoch: number) {
  let state = emptyProjectCreation();
  let generation = 0;
  const listeners = new Set<() => void>();
  return {
    epoch,
    getSnapshot: () => state,
    generation: () => generation,
    reset() { generation++; state = emptyProjectCreation(); listeners.forEach((listener) => listener()); },
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    update(change: Partial<ProjectCreationState>) { state = { ...state, ...change }; listeners.forEach((listener) => listener()); },
  };
}
// Memory only, scoped to the application's query client and identity epoch.
// Requests and drafts survive route remounts, never account changes or reloads.
const sessions = new WeakMap<QueryClient, ReturnType<typeof makeSession>>();
export function projectCreationSession(client: QueryClient, epoch: number) {
  let session = sessions.get(client);
  if (!session || session.epoch !== epoch) { session = makeSession(epoch); sessions.set(client, session); }
  return session;
}

export function isCurrentProjectCreationSession(client: QueryClient, session: ReturnType<typeof projectCreationSession>) {
  return sessions.get(client) === session;
}
