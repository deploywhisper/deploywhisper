## Project Workspaces

DeployWhisper now scopes analyses and topology context to lightweight project/workspace records instead of treating all history as one global pile.

### What Changed

- Projects have a stable `project_key`, display name, optional description, repository URL, and default branch.
- New analyses can attach to a project through the UI, API, CLI, or GitHub integration path.
- Persisted reports now carry project metadata and history filters can scope by project.
- Topology uploads are stored per project, with legacy file-based topology continuing to resolve through the default `unassigned` project.
- Deployment outcome and reviewer feedback tables now exist with project foreign keys so later Epic 5 stories can extend the same isolation boundary without schema churn.

### User Flows

- Web UI: choose an existing project or create one before running a manual analysis, and switch the active project from the searchable full-width `Active Project` card directly below the fixed header when moving between dashboard, history, and other routed pages.
- API:
  - `POST /api/v1/projects` creates a project
  - `POST /api/v1/analyses` accepts multipart `project_key` or `project_id`
  - `GET /api/v1/context/topology?project_key=<key>` reads project-scoped topology status
  - `POST /api/v1/context/topology` stores project-scoped topology JSON with `project_key` or `project_id`
- CLI:
  - `deploywhisper project create <key> <display-name>`
  - `deploywhisper project list`
  - `deploywhisper analyze --project <key> <artifact...>`
  - `deploywhisper topology import --from custom --source <topology.json> --project <key>`
  - `deploywhisper topology import --from terraform --source <state-or-uri> --project <key>`
  - The topology import command now routes through a shared source registry and returns a normalized import result with accepted, skipped, partially parsed, and unsupported resources.
- GitHub App integration: respects `DEPLOYWHISPER_GITHUB_PROJECT_KEY` when set; otherwise derives an owner-safe default from the full repository slug and creates it on demand.

### Guardrails

- Shared workspace chrome now keeps project switching in a dedicated global card below the header, with searchable filtering, keyboard navigation, and current/default project context shown consistently across pages.
- Explicit `project_key` / `project_id` references now fail fast when they are unknown instead of silently falling back to `unassigned`.
- Conflicting `project_key` and `project_id` inputs are rejected.
- Repository-derived project keys include the owner segment when available to avoid collisions between unrelated repositories with the same leaf name.
- Topology import stores normalized graph metadata only. Raw source artifacts are not persisted, and unsupported resources degrade to explicit warnings instead of aborting the whole import.

### Legacy Mapping

- Existing persisted reports are backfilled into the default `unassigned` project during migration `010_add_project_workspaces`.
- Existing file-based topology remains readable through the default project and new default-project topology updates continue to mirror the legacy file path for compatibility.

### Non-Goals

- No RBAC
- No SSO
- No org/team hierarchy
- No hosted SaaS tenancy behavior

### Verification

- `./.venv/bin/ruff check .`
- `./.venv/bin/ruff format --check .`
- `./.venv/bin/python -m unittest discover -q`
- `bash scripts/ci-local.sh`
