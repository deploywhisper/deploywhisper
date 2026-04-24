# Skills Installer CLI

Story 4.4 adds registry-backed install lifecycle commands under
`deploywhisper skill ...` so users can manage local skill cache files without
copying markdown by hand.

## Commands

Install the latest published version of a skill into `skills/custom/`:

```bash
deploywhisper skill install helm
```

List currently installed custom skills:

```bash
deploywhisper skill list
```

Update an installed custom skill to the latest registry version:

```bash
deploywhisper skill update helm
```

Remove an installed custom skill:

```bash
deploywhisper skill remove helm
```

## Registry URL resolution

The installer fetches metadata and raw markdown from the configured Skills
Registry API. It resolves the base URL in this order:

1. `DEPLOYWHISPER_SKILLS_REGISTRY_URL`
2. `APP_BASE_URL`
3. `PUBLIC_APP_URL`

If none of those are configured, install and update commands fail with a clear
configuration error instead of guessing a remote endpoint.

## Install location and precedence

- Installed skills are written to `skills/custom/<skill>.md`
- Files in `skills/custom/` override bundled `skills/<skill>.md` entries with
  the same filename
- Skill ids must use lowercase letters, digits, and hyphens only
- `deploywhisper skill install` refuses to overwrite an existing custom file;
  use `deploywhisper skill update` when you intentionally want the latest
  registry version
- `deploywhisper skill update` also restores the canonical registry copy when
  the installed file has drifted locally but still reports the same version

## Validation behavior

- Registry payloads are validated against manifest v1 before being written to
  disk
- The installer verifies the registry-provided SHA-256 checksum before saving
- `deploywhisper skill list` reports both active installed skills and ignored
  files when a custom manifest is invalid
