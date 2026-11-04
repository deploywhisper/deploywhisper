import { useEffect, useId, useRef, useState, useSyncExternalStore, type ComponentProps, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiClientError } from "../api/client";
import { createProject, getProjectsForCreation, type Project } from "../api/dashboard";
import { Button, ProjectSwitcher } from "../components/ui";
import { useIdentity } from "./IdentitySession";
import { projectToOption } from "./projectSelection";
import { isCurrentProjectCreationSession, projectCreationSession } from "./projectCreationSession";
import "./project-menu.css";

export function projectPrefill(query: string) {
  return { name: query.trim(), key: query.trim().toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "") };
}
export function projectCreationError(error: unknown) {
  if (error instanceof ApiClientError) {
    if ([401, 403].includes(error.status)) return "Project creation requires current administrator access. Sign in again or contact the operator.";
    if ([400, 409, 422].includes(error.status)) return "Check the project key and name. The key may already be in use.";
    if (error.status === 429) return "Too many requests. Wait before trying again.";
  }
  return null;
}

type Props = Omit<ComponentProps<typeof ProjectSwitcher>, "onNewProject">;
export function ProjectMenu(props: Props) {
  const identity = useIdentity();
  const queryClient = useQueryClient();
  const id = useId();
  const host = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const firstInput = useRef<HTMLInputElement>(null);
  const mounted = useRef(false);
  const epoch = useRef(identity.epoch);
  epoch.current = identity.epoch;
  const [open, setOpen] = useState(false);
  const session = projectCreationSession(queryClient, identity.epoch);
  const { name, key, description, pending, uncertain, message, created, checking } = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  const update = session.update;
  const current = () => isCurrentProjectCreationSession(queryClient, session);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { dialog.current?.close(); setOpen(false); }, [identity.epoch]);
  useEffect(() => {
    if (!open) return;
    dialog.current?.showModal(); firstInput.current?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || !dialog.current?.open) return;
      const nodes = Array.from(dialog.current.querySelectorAll<HTMLElement>("button, input, textarea")).filter((node) => !node.matches(":disabled"));
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (event.shiftKey ? document.activeElement === first : document.activeElement === last) {
        event.preventDefault(); (event.shiftKey ? last : first)?.focus();
      }
    };
    document.addEventListener("keydown", trap, true);
    return () => document.removeEventListener("keydown", trap, true);
  }, [open]);
  function close() {
    // A confirmed response can be acknowledged even without a visibility grant.
    if (session.getSnapshot().created) session.reset();
    dialog.current?.close(); setOpen(false);
    host.current?.querySelector<HTMLButtonElement>(".dw-project-trigger")?.focus();
  }
  function launch(query: string) {
    if (!uncertain && !created && !pending && !name && !key && !description) {
      const prefill = projectPrefill(query); update({ name: prefill.name, key: prefill.key, description: "", message: "" });
    }
    setOpen(true);
  }
  async function refreshProjects(expected: number, confirmed?: Project) {
    const generation = session.generation();
    // An older background list read must not overwrite the post-create list.
    await queryClient.cancelQueries({ queryKey: ["projects", expected], exact: true });
    if (!mounted.current || epoch.current !== expected || session.generation() !== generation) return;
    const projects = await getProjectsForCreation();
    if (!mounted.current || epoch.current !== expected || session.generation() !== generation) return;
    queryClient.setQueryData(["projects", expected], projects);
    if (confirmed && projects.some((project) => project.id === confirmed.id && project.project_key === confirmed.project_key)) {
      props.onChange?.(projectToOption(confirmed)); session.reset(); close();
    } else if (confirmed) {
      update({ message: "Project creation was confirmed, but it is not visible in your current project list. Contact the operator to check project access. Close to finish without selecting it." });
    } else if (projects.some((project) => project.project_key === key)) {
      const existing = projects.find((project) => project.project_key === key)!;
      props.onChange?.(projectToOption(existing)); session.reset(); close();
    } else {
      update({ uncertain: false, message: "The project is not currently listed. Check the key before choosing Create project again; the previous request may still complete." });
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    const state = session.getSnapshot();
    if (state.pending || state.uncertain || state.created || !key.trim() || !name.trim()) return;
    // Mark before sending: unmounting or opening another screen cannot replay it.
    update({ pending: true, uncertain: true, message: "Creation is pending. Closing this form does not cancel the server request." });
    const expected = identity.epoch;
    const generation = session.generation();
    let result: Project;
    try {
      result = await createProject({ project_key: key.trim(), display_name: name.trim(), description: description.trim() }, identity.csrfToken);
    } catch (error) {
      if (!current() || session.generation() !== generation) return;
      const definite = projectCreationError(error);
      update({ pending: false, uncertain: !definite, message: definite ?? "Creation could not be confirmed. Do not resubmit yet. Check the project list before another attempt." });
      return;
    }
    if (!current() || session.generation() !== generation) return;
    update({ pending: false, created: result, message: "Project creation was confirmed. Refresh the project list to select it; do not create it again." });
    if (!mounted.current) return;
    update({ checking: true });
    try { await refreshProjects(expected, result); }
    catch { if (current() && session.generation() === generation) update({ message: "Project creation was confirmed. Refresh the project list to select it; do not create it again." }); }
    finally { if (current() && session.generation() === generation) update({ checking: false }); }
  }
  async function checkProjects() {
    if (session.getSnapshot().checking || session.getSnapshot().pending) return;
    const expected = identity.epoch; const generation = session.generation(); update({ checking: true });
    try { await refreshProjects(expected, created ?? undefined); }
    catch { if (current() && session.generation() === generation) update({ message: "The project list could not be refreshed. Keep this form and try checking again. No new creation request was sent." }); }
    finally { if (current() && session.generation() === generation) update({ checking: false }); }
  }
  const locked = pending || checking || uncertain || Boolean(created);
  return <div ref={host} className="dw-project-menu">
    <ProjectSwitcher {...props} onNewProject={launch} />
    <dialog ref={dialog} className="dw-project-dialog dw-ui" aria-labelledby={`${id}-title`} aria-describedby={`${id}-hint`} onCancel={(event) => { event.preventDefault(); close(); }}>
      <form onSubmit={(event) => void submit(event)}>
        <h2 id={`${id}-title`}>New project</h2>
        <p id={`${id}-hint`}>Create a project to organize your analyses. Workspace setup and project access are managed separately.</p>
        <label htmlFor={`${id}-name`}>Project name<input ref={firstInput} id={`${id}-name`} value={name} onChange={(event) => update({ name: event.target.value })} required disabled={locked} /></label>
        <label htmlFor={`${id}-key`}>Project key<input id={`${id}-key`} value={key} onChange={(event) => update({ key: event.target.value })} required pattern="[a-z0-9]+(-[a-z0-9]+)*" disabled={locked} aria-describedby={`${id}-key-hint`} /></label>
        <p id={`${id}-key-hint`}>Use lowercase letters, numbers and hyphens. This key identifies the project.</p>
        <label htmlFor={`${id}-description`}>Description (optional)<textarea id={`${id}-description`} value={description} onChange={(event) => update({ description: event.target.value })} disabled={locked} rows={3} /></label>
        {message && <p role="alert">{message}</p>}
        <div className="dw-project-dialog-actions">
          <Button onClick={close}>{uncertain || created ? "Close" : "Cancel"}</Button>
          {(uncertain || created) ? <Button onClick={() => void checkProjects()} disabled={checking || pending}>{checking ? "Checking…" : "Refresh project list"}</Button> : <Button type="submit" variant="primary-gradient" disabled={pending || checking || !key.trim() || !name.trim()}>{pending ? "Creating…" : "Create project"}</Button>}
        </div>
      </form>
    </dialog>
  </div>;
}
