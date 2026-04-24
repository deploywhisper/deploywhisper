---
name: helmfile
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [helmfile.yaml, helmfile.yml]
token_budget: 1300
tags: [helmfile, helm, gitops]
description: Helmfile guidance for environment inheritance, release targeting, and shared values safety.
test_suite_path: tests/skill-tests/helmfile
---

## Critical risk patterns

- Environment value inheritance can change many releases at once = HIGH
- `helmDefaults.atomic: false` leaves partial failed rollouts behind = MEDIUM
- Release selector or ordering changes can affect unintended workloads = HIGH
- Shared secret or values file path changes break multiple environments together = HIGH

## Review cues

- Review environment inheritance and release targeting together before approving Helmfile changes.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
