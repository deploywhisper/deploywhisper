---
name: prometheus-rules
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [prometheus-rules.yaml, alerting-rules.yaml]
token_budget: 1250
tags: [prometheus, monitoring, alerts]
description: Prometheus rule guidance for alert timing, recording rules, and query-cardinality safety.
test_suite_path: tests/skill-tests/prometheus-rules
trigger_content_patterns: ["kind: PrometheusRule"]
---

## Critical risk patterns

- Extending alert `for:` windows delays paging and can hide fast-burning incidents = HIGH
- Recording rule renames break downstream dashboards, alerts, and SLO calculations = MEDIUM
- Unbounded joins or label expansions can overload Prometheus and remote-write pipelines = HIGH
- Severity label downgrades reduce response urgency even when the underlying blast radius is unchanged = HIGH

## Review cues

- Review Prometheus rule semantics, cardinality impact, and downstream consumers before merging.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
