/** Bounded nonsecret request continuity across same-session route remounts. */
export type RunnerMutationAction = "enroll" | "rotate" | "revoke";
export type RunnerMutationMarker = Readonly<{ identity: string; key: string; action: RunnerMutationAction; runnerId?: string; operation: symbol; issuanceOperation?: symbol; status: "pending" | "unknown" }>;
export type RunnerMutationOutcome = Readonly<{ action: RunnerMutationAction; kind: "issued" | "revoked" | "rejected"; runnerId?: string; credentialCleared?: boolean }>;
type Snapshot = Readonly<{ identity?: string; issuance?: RunnerMutationMarker; revocations?: ReadonlyMap<string, RunnerMutationMarker>; outcome?: RunnerMutationOutcome }>;
const empty: Snapshot = Object.freeze({});

export class RunnerMutationStore {
  private entries = new Map<string, Snapshot>();
  private listeners = new Set<() => void>();
  constructor(private readonly maximum = 64, private readonly maximumRevocations = 100) {}
  read = (key: string): Snapshot => this.entries.get(key) ?? empty;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private changed() { for (const listener of this.listeners) listener(); }
  private active(marker: RunnerMutationMarker): Snapshot | null {
    const current = this.read(marker.key);
    const slot = marker.action === "revoke" ? current.revocations?.get(marker.runnerId ?? "") : current.issuance;
    return current.identity === marker.identity && slot?.operation === marker.operation ? current : null;
  }
  begin(identity: string, key: string, action: RunnerMutationAction, runnerId?: string): RunnerMutationMarker | null {
    const current = this.read(key);
    if (current.identity && current.identity !== identity) return null;
    if (action === "revoke") {
      if (!runnerId || current.revocations?.has(runnerId) || (current.revocations?.size ?? 0) >= this.maximumRevocations) return null;
    } else if (current.issuance) return null;
    if (!this.entries.has(key) && this.entries.size >= this.maximum) {
      for (const [oldKey, item] of this.entries) {
        if (!item.issuance && !item.revocations?.size) { this.entries.delete(oldKey); break; }
      }
      if (this.entries.size >= this.maximum) return null;
    }
    const marker: RunnerMutationMarker = { identity, key, action, runnerId, operation: Symbol("runner-operation"), issuanceOperation: action === "revoke" && current.issuance?.runnerId === runnerId ? current.issuance?.operation : undefined, status: "pending" };
    const next = { ...current, identity, outcome: undefined };
    if (action === "revoke") this.entries.set(key, { ...next, revocations: new Map(current.revocations).set(runnerId!, marker) });
    else this.entries.set(key, { ...next, issuance: marker });
    this.changed(); return marker;
  }
  unknown(marker: RunnerMutationMarker) {
    const current = this.active(marker); if (!current) return;
    const unknown = { ...marker, status: "unknown" as const };
    this.entries.set(marker.key, marker.action === "revoke"
      ? { ...current, revocations: new Map(current.revocations).set(marker.runnerId!, unknown) }
      : { ...current, issuance: unknown });
    this.changed();
  }
  verified(marker: RunnerMutationMarker, outcome: Omit<RunnerMutationOutcome, "action">) {
    const current = this.active(marker); if (!current) return;
    const next: { identity?: string; issuance?: RunnerMutationMarker; revocations?: ReadonlyMap<string, RunnerMutationMarker>; outcome?: RunnerMutationOutcome } = { ...current, outcome: { action: marker.action, kind: outcome.kind, runnerId: outcome.runnerId, credentialCleared: outcome.credentialCleared } };
    if (marker.action === "revoke") {
      if (outcome.kind === "revoked" && outcome.runnerId !== marker.runnerId) return;
      const revocations = new Map(current.revocations);
      revocations.delete(marker.runnerId!); next.revocations = revocations;
      // A revoke cannot identify a lost enrollment whose response never named a runner.
      if (outcome.kind === "revoked" && outcome.runnerId && next.issuance?.runnerId === outcome.runnerId && next.issuance.operation === marker.issuanceOperation) delete next.issuance;
    } else delete next.issuance;
    this.entries.set(marker.key, next); this.changed();
  }
  clearReveal(key: string) {
    const current = this.read(key);
    if (current.outcome?.kind !== "issued" || current.outcome.credentialCleared) return;
    this.entries.set(key, { ...current, outcome: { ...current.outcome, credentialCleared: true } }); this.changed();
  }
  pruneSettledOtherIdentities(identity: string) {
    let changed = false;
    for (const [key, item] of this.entries) {
      if (item.identity !== identity && !item.issuance && !item.revocations?.size) { this.entries.delete(key); changed = true; }
    }
    if (changed) this.changed();
  }
}
export const runnerMutationStore = new RunnerMutationStore();
