# Changelog

## Unreleased

- Phase 7 UI migration cutover: React now serves as the root web UI at `/`, legacy `/app/...` links redirect to root routes, retired UI code/tests/dependencies were removed, and the runtime image no longer includes the retired Python UI package. Final local image size moved from 310 MB to 210 MB.
- Phase 6 UI migration: added React `/app/settings`, `/app/incidents`, and `/app/skills` routes with provider/topology/custom-skill settings, incident ingestion list/detail, and skills catalog list/detail parity.
- Added backend-for-UI settings endpoints plus additive skills API metadata for Phase 6 while preserving existing retired UI behavior and keeping dashboard-duration settings retired.
- Phase 5 UI migration: added the React `/app/history` screen with server-side search, severity and verdict filters, compact TanStack Table rows, expanded details, rescan delta display, pagination, and bulk delete.
- Added a backend-for-UI `/api/v1/analyses` bulk delete wrapper around the existing analysis history deletion service so the Phase 5 screen can preserve the legacy bulk-delete behavior.
