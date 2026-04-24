---
name: argocd
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [argocd-application.yaml, app-of-apps.yaml, argocd-project.yaml]
token_budget: 1350
tags: [argocd, gitops, kubernetes]
description: ArgoCD sync and application-set guidance for GitOps delivery changes across shared clusters.
test_suite_path: tests/skill-tests/argocd
trigger_content_patterns: ["argoproj.io/v1alpha1"]
---

## Critical risk patterns

- `syncPolicy.automated.prune: true` in shared namespaces can delete resources outside the immediate change set = HIGH
- `selfHeal: true` can instantly revert emergency hotfixes and confuse incident response = MEDIUM
- ApplicationSet generator changes fan out to every generated application and can widen blast radius cluster-wide = CRITICAL
- ArgoCD Project repository or destination allowlists widened to `*` remove key deployment guardrails = HIGH

## Review cues

- Check whether ArgoCD automation settings change the blast radius beyond the named application.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
