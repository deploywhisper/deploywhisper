---
name: tekton
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [pipeline.yaml, pipelinerun.yaml, task.yaml]
token_budget: 1250
tags: [tekton, ci-cd, kubernetes]
description: Tekton pipeline guidance for credentials, finally tasks, and shared-workspace safety.
test_suite_path: tests/skill-tests/tekton
trigger_content_patterns: ["tekton.dev/"]
---

## Critical risk patterns

- Mounting shared credentials into every task leaks secrets far beyond the intended build step = HIGH
- Changes to `finally` tasks can skip cleanup, approval, or promotion gates = HIGH
- Shared PVC workspaces across concurrent runs create artifact races and nondeterministic builds = MEDIUM
- Floating task image tags change pipeline behavior outside code review = HIGH

## Review cues

- Review credential scope, shared workspace usage, and finally-task behavior together for Tekton changes.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
