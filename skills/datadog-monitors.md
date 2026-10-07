---
name: datadog-monitors
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [datadog-monitor.json, datadog-monitor.yaml]
token_budget: 1200
tags: [datadog, monitoring, alerts]
description: Datadog monitor guidance for threshold drift, no-data handling, and alert-routing changes.
test_suite_path: tests/skill-tests/datadog-monitors
supported_toolchains: [datadog-monitors, datadog]
trust_level: core
scenario_references: [tests/skill-tests/datadog-monitors]
documentation_links: [docs/skills/authoring-guide.md, docs/skills/test-harness.md]
---

## Critical risk patterns

- Loosening alert thresholds or evaluation windows can suppress paging on real incidents = HIGH
- Disabling `notify_no_data` on heartbeat-style monitors hides telemetry loss = HIGH
- Removing renotify behavior on sev1 services lengthens incident response = MEDIUM
- Composite monitor dependency changes can invert alert logic for multiple downstream teams = HIGH

## Review cues

- Review query logic, no-data handling, and alert routing together for Datadog monitor changes.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
