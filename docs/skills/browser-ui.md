# Skills Browser UI

The shared skills catalog is exposed through the React SPA:

- `/skills` for the searchable catalog
- `/skills/{id}` for the skill detail view

## Browser behavior

- Search filters across the shared registry metadata already used by the skills
  registry and installer surfaces.
- Tool and author filters use the same canonical metadata returned by the shared
  registry service.
- Every catalog result exposes its manifest trust level and deterministic harness
  status. The detail view repeats both values alongside the install command.
- Source labels distinguish registry content from organization-owned content:
  - `Public registry` identifies bundled/public registry Skills.
  - `Local override` identifies a private Skill replacing a registry Skill.
  - `Private local` identifies a private Skill available only in the self-hosted
    installation.
- Sorting supports:
  - `popularity` using the seeded browser download/star snapshot in the shared
    registry service
  - `recency` using the manifest file update timestamp already exposed by the
    registry

## Detail page content

Each skill detail page surfaces:

- description
- trust label (`Experimental trust`, `Verified trust`, `Core trust`, or `Deprecated trust`)
- deterministic test status (`Tests passing`, `Tests failing`, or `Tests missing`)
- source (`Public registry`, `Local override`, or `Private local`)
- editorial badges for `Official` and curated-community `Featured` states
- install command
- latest harness summary and pass rate
- version history
- author
- maintainer
- contributors
- install count
- active issue count
- last updated timestamp
- analytics refresh timestamp

The shipped catalog now includes at least one real featured community skill so
the badge state is visible in the live browser, not only in synthetic tests.

## Analytics note

Story 4.8 upgrades the browser to use the shared analytics snapshot in
`data/skill-analytics.json`. The browser now shows:

- install counts
- harness pass rate
- active issue count
- the daily snapshot refresh timestamp

The snapshot is refreshed by `.github/workflows/refresh-skill-analytics.yml`.
