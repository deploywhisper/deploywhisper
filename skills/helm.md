---
name: helm
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [Chart.yaml, values.yaml, values-production.yaml]
token_budget: 1400
tags: [helm, kubernetes, gitops]
description: Helm chart rollout guidance covering hooks, chart drift, and value-driven production failures.
test_suite_path: tests/skill-tests/helm
trigger_content_patterns: ["apiVersion: v2", "dependencies:"]
---

## Critical risk patterns

- `post-install` or `pre-upgrade` hooks that mutate shared databases can turn a chart upgrade into a production outage = HIGH
- Service selector or immutable field changes force resource replacement and can strand live traffic = HIGH
- Floating chart dependencies or `image.tag: latest` break reproducibility between environments = MEDIUM
- Scaling critical workloads to zero through values files removes live capacity immediately = HIGH

## Review cues

- Review rendered manifests, hooks, and dependency updates together before approving a Helm rollout.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
