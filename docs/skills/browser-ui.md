# Skills Browser UI

Story 4.5 adds a public browser experience for the shared skills catalog on the
same NiceGUI runtime:

- `/skills` for the searchable catalog
- `/skills/{id}` for the skill detail view

## Browser behavior

- Search filters across the shared registry metadata already used by the skills
  registry and installer surfaces.
- Tool and author filters use the same canonical metadata returned by the shared
  registry service.
- Sorting supports:
  - `popularity` using the seeded browser download/star snapshot in the shared
    registry service
  - `recency` using the manifest file update timestamp already exposed by the
    registry

## Detail page content

Each skill detail page surfaces:

- description
- install command
- latest harness summary and pass rate
- version history
- author
- contributors
- install count
- active issue count
- last updated timestamp
- analytics refresh timestamp

## Analytics note

Story 4.8 upgrades the browser to use the shared analytics snapshot in
`data/skill-analytics.json`. The browser now shows:

- install counts
- harness pass rate
- active issue count
- the daily snapshot refresh timestamp

The snapshot is refreshed by `.github/workflows/refresh-skill-analytics.yml`.
