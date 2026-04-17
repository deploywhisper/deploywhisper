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
skill: terraform
version: 1.0
triggers: [.tf, .tfvars]
token_budget: 500
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
skill: helm
version: 1.0
triggers: [Chart.yaml, values.yaml, .tpl]
token_budget: 800
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
| `skill` | Yes | Skill identifier (lowercase, no spaces) |
| `version` | Yes | Skill version for tracking changes |
| `triggers` | Yes | File extensions or names that activate this skill |
| `token_budget` | No | Max tokens for this skill (default: 1500) |
| `description` | No | Human-readable description |
| `always_load` | No | If true, loads regardless of file detection |
| `trigger_content_patterns` | No | Strings to look for inside files for disambiguation |
