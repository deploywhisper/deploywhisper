# Skills Registry API

Story 4.1 introduces a read-only registry surface under `/api/v1/skills` that
normalizes the existing markdown-backed skills catalog into a stable API
contract.

## Endpoints

- `GET /api/v1/skills`
  Returns the current effective skill inventory with pagination plus optional
  `tool`, `tag`, `author`, and `search` filters.
- `GET /api/v1/skills/{id}`
  Returns the current effective record for a single skill id.
- `GET /api/v1/skills/{id}/content`
  Returns the raw markdown payload, manifest version, and SHA-256 checksum used
  by the installer CLI.
- `GET /api/v1/skills/{id}/versions`
  Returns the discoverable bundled-catalog version history for a single skill
  id.

## Notes

- The current implementation serves the bundled canonical catalog from
  `skills/*.md`.
- Installed or team-local cache files under `skills/custom/*.md` are excluded
  from this API so the browser and installer surfaces do not drift per
  instance.
- The content endpoint returns the exact markdown payload with frontmatter so
  installer clients can validate and cache the same artifact the registry
  publishes.
- Skills with invalid YAML frontmatter are skipped instead of failing the
  registry endpoints.
- The API contract is intentionally manifest-shaped so later stories can add the
  formal manifest schema, installer, validator, and public browser without
  rewriting the read surface.
