## Project Workspaces

DeployWhisper now scopes analyses and topology context to lightweight project/workspace records instead of treating all history as one global pile.

### What Changed

- Projects have a stable `project_key`, display name, optional description, repository URL, and default branch.
- Workspaces have a stable project-local `workspace_key`, display name, optional description, optional environment label, and timestamps.
- New analyses must attach to a project through the UI, API, CLI, or GitHub integration path.
- Persisted reports now carry project metadata and history filters can scope by project.
- Topology uploads are stored per project, with legacy file-based topology continuing to resolve through the default `unassigned` project.
- Topology drift checks now run on a persisted cadence (daily by default), reuse the imported source reference when available, and surface per-project added/removed/modified resource reports in settings.
- Deployment outcome and reviewer feedback tables now exist with project foreign keys so later Epic 5 stories can extend the same isolation boundary without schema churn.

### User Flows

- Web UI: choose an existing project or create one before running a manual analysis, and switch the active project from the searchable full-width `Active Project` card directly below the fixed header when moving between dashboard, history, and other routed pages.
- API:
  - `POST /api/v1/projects` creates a project
  - `GET /api/v1/projects/<project_key>/workspaces` lists workspace/environment records for a project
  - `POST /api/v1/projects/<project_key>/workspaces` creates a workspace/environment record
  - `POST /api/v1/analyses` requires multipart `project_key` or `project_id`
  - `GET /api/v1/context/topology?project_key=<key>` reads project-scoped topology status
  - `POST /api/v1/context/topology` stores project-scoped topology JSON with `project_key` or `project_id`
- CLI:
  - `deploywhisper project create <key> <display-name>`
  - `deploywhisper project list`
  - `deploywhisper project workspace create <project-key> <workspace-key> <display-name>`
  - `deploywhisper project workspace list <project-key>`
  - `deploywhisper analyze --project <key> <artifact...>` or `deploywhisper analyze --project-id <id> <artifact...>`
  - `deploywhisper topology import --from custom --source <topology.json> --project <key>`
  - `deploywhisper topology import --from terraform --source <state-or-uri> --project <key>`
  - The topology import command now routes through a shared source registry and returns a normalized import result with accepted, skipped, partially parsed, and unsupported resources.
- GitHub App integration: respects `DEPLOYWHISPER_GITHUB_PROJECT_KEY` when set; otherwise derives an owner-safe default from the full repository slug and creates it on demand.

### Guardrails

- Shared workspace chrome now keeps project switching in a dedicated global card below the header, with searchable filtering, keyboard navigation, and current/default project context shown consistently across pages.
- Explicit `project_key` / `project_id` references now fail fast when they are unknown instead of silently falling back to `unassigned`.
- New API and CLI analysis submissions without a project reference fail fast with `missing_project_scope` instead of silently falling back to `unassigned`.
- Conflicting `project_key` and `project_id` inputs are rejected.
- In the current local/admin phase, unauthorized analysis scope means an unknown, conflicting, or otherwise invalid project reference. Full membership and role enforcement is intentionally deferred to the lightweight RBAC story.
- Repository-derived project keys include the owner segment when available to avoid collisions between unrelated repositories with the same leaf name.
- Topology import stores normalized graph metadata only. Raw source artifacts are not persisted, and unsupported resources degrade to explicit warnings instead of aborting the whole import.
- Drift cadence is persisted through the settings UI, and scheduled drift checks warn when more than 10% of mapped resources changed since the last import.

### Legacy Mapping

- Existing persisted reports are backfilled into the default `unassigned` project during migration `010_add_project_workspaces`; this legacy mapping does not apply to new API or CLI analysis submissions.
- First-class workspace/environment records are introduced by migration `014_add_project_workspace_records`.
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
