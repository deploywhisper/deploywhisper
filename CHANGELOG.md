# Changelog

## Unreleased

- No unreleased changes yet.

## v1.3.0 - 2026-06-26

- Added context-source freshness and confidence ledgers so reports, API output, CLI output, and the React report UI can show source freshness, scope, confidence, conflicts, limitations, and evidence-to-context provenance.
- Added scanner import support for SARIF 2.1.0 and Semgrep JSON, including project/workspace-scoped persistence, normalized external evidence, scanner import API contracts, OpenAPI updates, and scanner import documentation.
- Added scanner-aware report context so external scanner findings are clearly labeled as external context instead of being treated as DeployWhisper deterministic evidence or automatically escalating severity.
- Added scanner conflict handling across report synthesis, UI, API, CLI, and share/PR summary output so scanner-vs-deterministic disagreements surface source details, freshness, verification guidance, and confidence impact while preserving Evidence Law scoring.
- Improved shared protected report unlocks so comparison views preserve `compare=previous` and valid password unlocks are not blocked by optional comparison lookup failures.
- Strengthened local-first scanner safety with request-size bounds, path and URI validation, metadata allowlisting, redaction behavior, stable scanner source identity, and focused regression coverage for malformed scanner payloads.
- Updated report schema, CI advisory consumption docs, GitHub Action docs, scanner import docs, and release metadata for the new external evidence and conflict payloads.
- Expanded Python, React, API, CLI, migration, documentation, and composed Playwright coverage for the new context and scanner flows.

## v1.2.0 - 2026-06-17

- Phase 7 UI migration cutover: React now serves as the root web UI at `/`, legacy `/app/...` links redirect to root routes, retired UI code/tests/dependencies were removed, and the runtime image no longer includes the retired Python UI package. Final local image size moved from 310 MB to 210 MB.
- Phase 6 UI migration: added React `/app/settings`, `/app/incidents`, and `/app/skills` routes with provider/topology/custom-skill settings, incident ingestion list/detail, and skills catalog list/detail parity.
- Added backend-for-UI settings endpoints plus additive skills API metadata for Phase 6 while preserving existing retired UI behavior and keeping dashboard-duration settings retired.
- Phase 5 UI migration: added the React `/app/history` screen with server-side search, severity and verdict filters, compact TanStack Table rows, expanded details, rescan delta display, pagination, and bulk delete.
- Added a backend-for-UI `/api/v1/analyses` bulk delete wrapper around the existing analysis history deletion service so the Phase 5 screen can preserve the legacy bulk-delete behavior.
- Added the React dashboard, report, history, settings, incidents, and skills surfaces using the new frontend workspace and design primitives.
- Added dashboard KPI, verdict distribution, and project-list backend-for-UI endpoints, plus additive analysis-list fields required by the dashboard.
- Added the typed API client and generated OpenAPI schema for the React frontend workspace.
- Added composed-container frontend CI coverage for typecheck, Vitest, and production build.
- Improved local Ollama development defaults for faster local narrative testing with `qwen2.5-coder:3b`.
- Fixed project selection persistence, dashboard verdict-health GO/clear counts, dashboard time-of-day greeting, destructive history delete confirmation, settings success feedback, branding, favicon assets, and report blast-radius visualization.
