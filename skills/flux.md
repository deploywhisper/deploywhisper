---
name: flux
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [gotk-sync.yaml, flux-kustomization.yaml, helmrelease.yaml]
token_budget: 1300
tags: [flux, gitops, kubernetes]
description: Flux GitOps guidance for reconciliation, pruning, and source-driven rollout safety.
test_suite_path: tests/skill-tests/flux
trigger_content_patterns: ["source.toolkit.fluxcd.io", "helm.toolkit.fluxcd.io", "kustomize.toolkit.fluxcd.io"]
---

## Critical risk patterns

- Flux Kustomization `prune: true` can delete manually-created but still-needed resources = HIGH
- Suspending or resuming the wrong source blocks reconciliation across multiple environments = HIGH
- HelmRelease `valuesFrom` changes can silently swap runtime configuration = MEDIUM
- Aggressive reconcile interval reductions can thundering-herd the control plane = MEDIUM

## Review cues

- Inspect source objects, reconciliation intervals, and pruning behavior together for Flux changes.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
