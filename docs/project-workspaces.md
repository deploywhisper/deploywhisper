## Project Workspaces

DeployWhisper now scopes analyses and topology context to lightweight project/workspace records instead of treating all history as one global pile.

For setup-specific modeling guidance, see the [Project Model Guide](./concepts/project-model.md).

### What Changed

- Projects have a stable `project_key`, display name, optional description, repository URL, and default branch.
- Workspaces have a stable project-local `workspace_key`, display name, optional description, optional environment label, and timestamps.
- New analyses must attach to a project through the UI, API, CLI, or GitHub integration path.
- Persisted reports now carry project metadata plus optional workspace metadata, and history/report filters can scope by project and workspace.
- Topology uploads are stored per project, with legacy file-based topology continuing to resolve through the default `unassigned` project.
- Topology drift checks now run on a persisted cadence (daily by default), reuse the imported source reference when available, and surface per-project added/removed/modified resource reports in settings.
- Deployment outcome and reviewer feedback tables now exist with project foreign keys so later Epic 5 stories can extend the same isolation boundary without schema churn.
- Lightweight project roles are defined before enterprise auth exists: `admin`, `maintainer`, `reviewer`, `contributor`, and `read-only`.
- API and CLI project operations now have a shared authorization result contract so future auth adapters can deny a project action without revealing unrelated project metadata.

### User Flows

- Web UI: choose an existing project or create one before running a manual analysis, and switch the active project from the searchable full-width `Active Project` card directly below the fixed header when moving between dashboard, history, and other routed pages.
- API:
  - `POST /api/v1/projects` creates a project
  - `GET /api/v1/projects/roles` lists the lightweight role and capability contract
  - `GET /api/v1/projects/<project_key>/workspaces` lists workspace/environment records for a project
  - `POST /api/v1/projects/<project_key>/workspaces` creates a workspace/environment record
  - `POST /api/v1/analyses` requires multipart `project_key` or `project_id`
  - `POST /api/v1/analyses` also accepts optional `workspace_key` or `workspace_id` to attach a run to a project-local workspace/environment
  - `GET /api/v1/analyses?project_key=<key>&workspace_key=<workspace>` lists reports for one workspace
  - `GET /api/v1/analyses/<id>?project_key=<key>&workspace_key=<workspace>` returns a report only when the requested scope matches
  - Analysis submit/list/detail responses expose `meta.api_version`, `meta.report_schema_version`, project/workspace scope, evidence, findings, Evidence Law status, context completeness, narrative status, and the advisory recommendation contract.
  - `GET /api/v1/context/topology?project_key=<key>` reads project-scoped topology status
  - `POST /api/v1/context/topology` stores project-scoped topology JSON with `project_key` or `project_id`
  - Project, analysis, report, topology context, and deployment outcome routes accept `X-DeployWhisper-Project-Role` and `X-DeployWhisper-Project-Keys` as the lightweight actor contract. Omitting both preserves local self-hosted admin behavior.
- CLI:
  - `deploywhisper project create <key> <display-name>`
  - `deploywhisper project list`
  - `deploywhisper project roles`
  - `deploywhisper project workspace create <project-key> <workspace-key> <display-name>`
  - `deploywhisper project workspace list <project-key>`
  - `deploywhisper analyze --project <key> [--workspace <workspace>] <artifact...>` or `deploywhisper analyze --project-id <id> [--workspace-id <id>] <artifact...>` returns the same advisory JSON contract, including verdict, Evidence Law status, top findings, uncertainty, report schema version, and advisory posture.
  - `deploywhisper topology import --from custom --source <topology.json> --project <key>`
  - `deploywhisper topology import --from terraform --source <state-or-uri> --project <key>`
  - The topology import command now routes through a shared source registry and returns a normalized import result with accepted, skipped, partially parsed, and unsupported resources.
  - Project, analysis, topology import, and outcome record commands can read `DEPLOYWHISPER_PROJECT_ROLE` and `DEPLOYWHISPER_PROJECT_KEYS` for automation actors that need the same lightweight authorization behavior as API callers.
- GitHub App integration: respects `DEPLOYWHISPER_GITHUB_PROJECT_KEY` when set; otherwise derives an owner-safe default from the full repository slug and creates it on demand. Unknown, malformed, or blank explicit override values fail fast instead of falling back to the repository-derived default.

### Guardrails

- Shared workspace chrome now keeps project switching in a dedicated global card below the header, with searchable filtering, keyboard navigation, and current/default project context shown consistently across pages.
- Explicit `project_key` / `project_id` references now fail fast when they are unknown instead of silently falling back to `unassigned`.
- Explicit `workspace_key` / `workspace_id` references fail fast when unknown or when they do not belong to the supplied project.
- Report detail and history retrieval return the standard not-found envelope when the requested project/workspace scope does not match the report.
- New API and CLI analysis submissions without a project reference fail fast with `missing_project_scope` instead of silently falling back to `unassigned`.
- Authorization failures return `project_permission_denied`, `project_scope_forbidden`, or `invalid_project_role` with a generic message that does not include the denied project key.
- API project lists are filtered to the caller's allowed project keys when the lightweight actor scope is present, so unrelated project records are not returned.
- Analysis submission requires `analysis.submit`, report reads require `report.read`, report share configuration requires `report.share.manage`, topology status reads require `topology.read`, topology context changes require `topology.manage`, and deployment outcome reads/writes require `outcome.read` / `outcome.manage` when a lightweight actor role is supplied.
- Non-admin lightweight roles must include at least one allowed project key through the actor header or environment variable.
- Conflicting `project_key` and `project_id` inputs are rejected.
- In the current local/admin phase, omitted actor headers or CLI actor environment variables mean local admin behavior. Shared self-hosted installs must put DeployWhisper behind a trusted identity layer, proxy, or middleware that strips caller-supplied project actor headers and injects the verified role/scope before exposing project-scoped APIs. Full identity provider integration remains deferred.
- Repository-derived project keys include the owner segment when available to avoid collisions between unrelated repositories with the same leaf name.
- Topology import stores normalized graph metadata only. Raw source artifacts are not persisted, and unsupported resources degrade to explicit warnings instead of aborting the whole import.
- Drift cadence is persisted through the settings UI, and scheduled drift checks warn when more than 10% of mapped resources changed since the last import.

### Legacy Mapping

- Existing persisted reports are backfilled into the default `unassigned` project during migration `010_add_project_workspaces`; this legacy mapping does not apply to new API or CLI analysis submissions.
- First-class workspace/environment records are introduced by migration `014_add_project_workspace_records`.
- Existing file-based topology remains readable through the default project and new default-project topology updates continue to mirror the legacy file path for compatibility.

### Role Capabilities

- `admin`: full project administration, settings, role, topology, scanner, incident, outcome, report, feedback, and analysis capabilities.
- `maintainer`: operational management for workspaces, analysis submissions, reports, feedback, outcomes, incidents, topology, and scanner imports.
- `reviewer`: report review, topology status, outcome read, and feedback capabilities with project/workspace/report read access.
- `contributor`: analysis submission plus project/workspace/report/topology read and feedback creation.
- `read-only`: project, workspace, report, and topology status read access only.

### Non-Goals

- No SSO-backed RBAC enforcement
- No SSO
- No org/team hierarchy
- No hosted SaaS tenancy behavior

### Verification

- `./.venv/bin/ruff check .`
- `./.venv/bin/ruff format --check .`
- `./.venv/bin/python -m unittest discover -q`
- `bash scripts/ci-local.sh`
