# Custom AI Skills

Place your team-specific skill files in this directory. They follow the same
markdown format as built-in skills, with YAML frontmatter.

**Custom skills override built-in skills with the same filename.** For example,
placing a `terraform.md` here will replace the built-in Terraform skill entirely.

## Quick start

```bash
# Create a custom skill for your internal modules
cat > terraform.md << 'EOF'
---
name: terraform
version: 1.0.0
author: Platform Team
license: Proprietary
triggers: [.tf, .tfvars]
token_budget: 500
tags: [terraform, internal, platform]
description: Internal Terraform guidance for the platform team.
test_suite_path: tests/skill-tests/terraform
---

## Internal module patterns
- Module `corp-vpc` v2.x requires NAT gateway — flag if nat_enabled = false
- Module `corp-rds` always sets multi_az in prod — flag if single-AZ detected
- Tag `team` is mandatory on all resources — flag if missing

## Naming conventions
- Production resources must match pattern: prod-{region}-{service}
- Security groups must have description field populated
EOF
```

## Adding a completely new skill

You can create skills for tools not covered by the built-in set:

```bash
cat > helm.md << 'EOF'
---
name: helm
version: 1.0.0
author: Platform Team
license: Proprietary
triggers: [Chart.yaml, values.yaml, .tpl]
token_budget: 800
tags: [helm, kubernetes, platform]
description: Helm chart review guidance for team-owned charts.
test_suite_path: tests/skill-tests/helm
---

## Helm chart risks
- values.yaml with `replicaCount: 1` in production = HIGH
- Missing `resources.limits` in chart templates = HIGH
- Chart dependency without version pin = MEDIUM
- Subchart with different namespace = check RBAC implications
EOF
```

The skill loader auto-discovers any `.md` file in this directory and loads it
when matching file extensions are detected in the upload.

## Frontmatter reference

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Skill identifier (lowercase, filename stem must match) |
| `version` | Yes | Skill version for tracking changes |
| `author` | Yes | Owner label for registry and attribution |
| `license` | Yes | Distribution license identifier |
| `triggers` | Yes | File extensions or names that activate this skill |
| `token_budget` | Yes | Max tokens allocated to the skill |
| `tags` | Yes | Search/filter tags |
| `description` | Yes | Human-readable description |
| `test_suite_path` | Yes | Repo-relative path for the skill test suite |
| `always_load` | No | If true, loads regardless of file detection |
| `trigger_content_patterns` | No | Strings to look for inside files for disambiguation |

Validate a manifest before sharing it:

```bash
deploywhisper skill lint skills/custom/terraform.md
```
