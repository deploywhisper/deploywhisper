---
name: kustomize
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [kustomization.yaml, kustomization.yml]
token_budget: 1250
tags: [kustomize, kubernetes, gitops]
description: Kustomize overlay guidance for name transforms, patch targeting, and namespace drift.
test_suite_path: tests/skill-tests/kustomize
---

## Critical risk patterns

- NamePrefix or NameSuffix changes rewrite object identities and can break references = HIGH
- Broad strategic merge or JSON patches can mutate unintended resources = HIGH
- Image tag swaps without digest pinning reintroduce unreviewed drift = MEDIUM
- Namespace transformer changes can re-home shared resources unexpectedly = HIGH

## Review cues

- Review Kustomize overlays as graph-wide mutations rather than isolated file edits.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
