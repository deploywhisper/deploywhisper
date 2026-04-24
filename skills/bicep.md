---
name: bicep
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [main.bicep, infra.bicep, .bicep]
token_budget: 1300
tags: [azure, bicep, iac]
description: Azure Bicep guidance for deployment modes, secret exposure, and subscription-target drift.
test_suite_path: tests/skill-tests/bicep
---

## Critical risk patterns

- Resource or module renames can change deployment identity and trigger destructive replacement = HIGH
- `existing` resources pointed at the wrong subscription or resource group create broken references = HIGH
- Key Vault secrets or sensitive outputs emitted as plain strings leak credentials = CRITICAL
- Complete-mode deployments delete unmanaged resources in the target scope = CRITICAL

## Review cues

- Review Bicep deployment mode, target scope, and secret handling together before approving.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
