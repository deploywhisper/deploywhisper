# Changelog

## Unreleased

- Phase 6 UI migration: added React `/app/settings`, `/app/incidents`, and `/app/skills` routes with provider/topology/custom-skill settings, incident ingestion list/detail, and skills catalog list/detail parity.
- Added backend-for-UI settings endpoints plus additive skills API metadata for Phase 6 while preserving existing NiceGUI behavior and keeping dashboard-duration settings retired.
- Phase 5 UI migration: added the React `/app/history` screen with server-side search, severity and verdict filters, compact TanStack Table rows, expanded details, rescan delta display, pagination, and bulk delete.
- Added a backend-for-UI `/api/v1/analyses` bulk delete wrapper around the existing analysis history deletion service so the Phase 5 screen can preserve the legacy bulk-delete behavior.
