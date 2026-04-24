---
name: terragrunt
version: 1.0.0
author: Infrastructure Guild Community
maintainer: Terragrunt Maintainers
featured: true
license: MIT
tool: terraform
triggers: [terragrunt.hcl]
token_budget: 1400
tags: [terragrunt, terraform, iac, community]
description: Community-authored Terragrunt guidance for include hierarchy drift, dependency output coupling, and run-all blast radius review.
test_suite_path: tests/skill-tests/terragrunt
---

## Critical risk patterns

- `run-all apply` or root include changes can fan out across many stacks at once = HIGH
- Dependency output contract changes can break downstream stacks even when the local diff looks small = HIGH
- Backend, remote state, or generate block changes can orphan state or rewrite provider configuration = CRITICAL
- Deep include hierarchy overrides can silently change locals, inputs, or hooks for every child module = HIGH

## Review cues

- Review parent includes, dependency blocks, and generated provider files together before approving Terragrunt changes.
- Prefer stack-by-stack blast-radius notes over generic Terraform advice when the change alters shared Terragrunt scaffolding.
