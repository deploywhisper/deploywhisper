# Changelog

## Unreleased

- Phase 5 UI migration: added the React `/app/history` screen with server-side search, severity and verdict filters, compact TanStack Table rows, expanded details, rescan delta display, pagination, and bulk delete.
- Added a backend-for-UI `/api/v1/analyses` bulk delete wrapper around the existing analysis history deletion service so the Phase 5 screen can preserve the legacy bulk-delete behavior.
