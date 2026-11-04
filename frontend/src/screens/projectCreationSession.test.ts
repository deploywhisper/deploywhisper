import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { emptyProjectCreation, isCurrentProjectCreationSession, projectCreationSession } from "./projectCreationSession";

describe("project creation session", () => {
  it("retains pending intent and input across same-identity switcher remounts", () => {
    const client = new QueryClient();
    const dashboard = projectCreationSession(client, 1);
    dashboard.update({ name: "Synthetic", key: "synthetic", pending: true, uncertain: true });
    const history = projectCreationSession(client, 1);
    expect(history).toBe(dashboard);
    expect(history.getSnapshot()).toMatchObject({ key: "synthetic", pending: true, uncertain: true });
  });
  it("clears checking, pending, uncertainty and draft on identity changes, fencing late results", () => {
    const client = new QueryClient();
    const old = projectCreationSession(client, 1);
    old.update({ name: "Private draft", checking: true, pending: true, uncertain: true });
    const next = projectCreationSession(client, 2);
    expect(next.getSnapshot()).toEqual(emptyProjectCreation());
    expect(isCurrentProjectCreationSession(client, old)).toBe(false);
    old.update({ checking: false, name: "Late result" });
    expect(next.getSnapshot()).toEqual(emptyProjectCreation());
  });
  it("resolving a reread clears old intent so another project can be created", () => {
    const session = projectCreationSession(new QueryClient(), 0);
    session.update({ key: "synthetic", uncertain: true });
    session.reset();
    expect(session.getSnapshot()).toEqual(emptyProjectCreation());
  });
});

it("acknowledges confirmed creation without a visibility grant and fences late refreshes", () => {
  const session = projectCreationSession(new QueryClient(), 0);
  const generation = session.generation();
  session.update({ created: { id: 9 } as never, checking: true });
  session.reset();
  expect(session.getSnapshot()).toEqual(emptyProjectCreation());
  expect(session.generation()).not.toBe(generation);
});
