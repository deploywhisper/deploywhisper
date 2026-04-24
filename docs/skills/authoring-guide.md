# Skills Authoring Guide

Story 4.2 formalizes the DeployWhisper skill manifest into a versioned v1
contract. New community or local skills should use the v1 frontmatter shape even
though the analysis runtime still tolerates older lightweight markdown files for
backward compatibility.

## Manifest v1

Publish the schema at:

- Filesystem: `schemas/skill-manifest-v1.json`
- Runtime URL: `/schemas/skill-manifest-v1.json`

Required frontmatter fields:

- `name`: lowercase skill id. It must match the markdown filename stem.
- `version`: semantic version such as `1.0.0`.
- `author`: person, team, or organization that owns the skill.
- `license`: distribution license identifier such as `MIT`.
- `triggers`: filenames or extensions that activate the skill.
- `token_budget`: positive integer budget for narrator context assembly.
- `tags`: search/filter tags used by the registry and browser experiences.
- `description`: short summary shown in registry and authoring surfaces.
- `test_suite_path`: repo-relative path for the skill harness introduced by the
  next story.

Optional extension fields supported today:

- `always_load`: include the skill even without trigger matches.
- `tool`: explicit tool family for registry filtering when it differs from
  `name`.
- `trigger_content_patterns`: content markers for disambiguating shared
  extensions such as `.yaml`.

## Example

```md
---
name: terraform
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [.tf, terraform-plan.json]
token_budget: 1800
tags: [terraform, iac, infrastructure]
description: Deep Terraform risk knowledge for stateful infrastructure changes.
test_suite_path: tests/skill-tests/terraform
---

## Critical risk patterns

- RDS instance without deletion protection = CRITICAL
- IAM policy with wildcard action/resource = CRITICAL
```

## Validation

Use the CLI authoring check before opening a PR or copying a local skill into
`skills/custom/`:

```bash
deploywhisper skill lint path/to/my-skill.md
```

Validation fails when:

- required manifest fields are missing
- the markdown body is empty after frontmatter stripping
- `name` does not match the filename stem
- `version` is not semantic version format
- `token_budget` is not a positive integer
- `test_suite_path` is absolute or escapes the repo with `..`
- `test_suite_path` does not exist under the current repository root

## Authoring rules

- Keep the skill body focused on deterministic review guidance, not executable
  steps.
- Prefer explicit severity signals and concrete risk patterns over vague prose.
- Keep sensitive examples synthetic; do not embed real credentials, internal
  account ids, or production hostnames.
- Treat `skills/custom/` as a local cache/override surface. Registry-facing
  manifests should use the same v1 schema even if runtime loading can still read
  older markdown.
