---
name: pulumi-azure
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [Pulumi.azure.yaml, pulumi-azure.ts]
token_budget: 1400
tags: [pulumi, azure, iac]
description: Pulumi Azure guidance for resource-group blast radius, identities, and recovery settings.
test_suite_path: tests/skill-tests/pulumi-azure
trigger_content_patterns: ["@pulumi/azure-native", "pulumi_azure_native"]
---

## Critical risk patterns

- Resource group replacement cascades to every contained Azure resource = CRITICAL
- Managed identity or role-assignment drift can break runtime access immediately = HIGH
- Key Vault soft-delete or purge-protection changes alter recovery guarantees = HIGH
- Regional SKU changes can require destructive replacement instead of in-place updates = HIGH

## Review cues

- Review resource-group scope, identity changes, and recovery settings together for Pulumi Azure updates.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
