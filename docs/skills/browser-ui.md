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
- latest harness summary
- version history
- author
- contributors
- download count
- star count
- last updated timestamp

## Analytics note

The current browser page uses seeded preview download/star counts from the
shared registry service so the public UI can present sort and comparison
signals before Story 4.8 introduces live daily-updated analytics.
