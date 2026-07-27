# Skills Installer CLI

Story 9.4 completes configured-source install lifecycle commands under
`deploywhisper skill ...` so users can manage local skill cache files without
copying markdown by hand.

## Commands

Install the configured version of a Skill into `skills/custom/`:

```bash
deploywhisper skill install helm
```

List currently installed custom skills:

```bash
deploywhisper skill list
```

List the shared registry catalog with analytics signals:

```bash
deploywhisper skill list --catalog
```

Update an installed custom Skill from the configured source:

```bash
deploywhisper skill update helm
```

Remove an installed custom skill:

```bash
deploywhisper skill remove helm
```

## Source resolution

Set `DEPLOYWHISPER_SKILLS_SOURCE_DIR` to a local directory containing
`<skill-id>.md` files for private, organization-owned, or air-gapped Skills.
When configured, this local source takes precedence and install/update commands
do not make a registry request.

Without a local source directory, the installer fetches metadata and raw
markdown from the configured Skills Registry API. It resolves the base URL in
this order:

1. `DEPLOYWHISPER_SKILLS_REGISTRY_URL`
2. `APP_BASE_URL`
3. `PUBLIC_APP_URL`

If neither a local source nor a registry URL is configured, install and update
commands fail with a clear configuration error instead of guessing a source.

## Install location and precedence

- Installed skills are written to `skills/custom/<skill>.md`
- Files in `skills/custom/` override bundled `skills/<skill>.md` entries with
  the same filename
- Skill ids must use lowercase letters, digits, and hyphens only
- `deploywhisper skill install` refuses to overwrite an existing custom file;
  use `deploywhisper skill update` when you intentionally want to refresh from
  the currently configured source
- `deploywhisper skill update` also restores the configured source copy when
  the installed file has drifted locally but still reports the same version;
  with a local source configured, it does not fall back to the registry

## Validation behavior

- Registry and local-source payloads are validated against manifest v1 before
  being written to disk
- The installer verifies the registry-provided SHA-256 checksum before saving
- Local source paths must be regular UTF-8 files inside the configured
  directory; symlinks and special files are rejected, and reads are anchored
  to the validated directory to prevent path-swap races
- Local source files are limited to 1 MiB and are read with a bounded buffer
- Skill Markdown is parsed as data and is never imported, evaluated, or
  executed, including on validation errors
- `deploywhisper skill list` reports both active installed skills and ignored
  files when a custom manifest is invalid
- `deploywhisper skill list --catalog` shows registry analytics including
  install count, harness pass rate, last updated, and active issues using the
  same shared registry metadata exposed by the browser

## Daily analytics snapshot

- Registry analytics live in `data/skill-analytics.json`
- `.github/workflows/refresh-skill-analytics.yml` refreshes the snapshot daily
- `scripts/refresh_skill_analytics.py` refreshes active issue counts from
  GitHub issue search and reads install/star popularity from
  `DEPLOYWHISPER_SKILL_ANALYTICS_URL`, or from the default public feed at
  `https://deploywhisper.github.io/skills-registry/skill-popularity.json`
- the refresh job fails explicitly if the popularity feed is missing or omits a
  built-in skill, rather than silently carrying stale metrics forward
