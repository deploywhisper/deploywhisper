---
title: 'Pause unwanted automatic update PRs'
type: 'chore'
created: '2026-10-27'
status: 'done'
route: 'one-shot'
---

# Pause unwanted automatic update PRs

## Intent

**Problem:** Weekly Dependabot checks opened 15 unwanted dependency PRs alongside
Story16.5 PR195. Closing the PRs alone would allow later automated replacements.

**Approach:** Close bot-owned PRs180–194 while preserving195; pause all seven
version-update feeds with zero PR limits. Security-update PRs are already
disabled. Disable the analytics workflow in GitHub and remove its cron trigger,
retaining explicit manual dispatch. Keep CI, audits and security scanners active.
Existing branches and closed PR history are retained because closure succeeded.

## Suggested Review Order

1. [Dependency PR pause](../../.github/dependabot.yml): all seven limits zero.
2. [Manual-only analytics](../../.github/workflows/refresh-skill-analytics.yml):
   remove its scheduled source of commits or optional PRs.
3. [Existing configuration tests](../../tests/test_infra/test_supply_chain_remediation.py)
   and [analytics contract](../../tests/test_infra/test_skill_contribution_workflow.py):
   enforce the new maintainer policy.
4. [Maintenance guide](../../docs/dependency-maintenance.md): pause, resume,
   deliberate updates and the separate Vite audit blocker.

Independent adversarial review found no concrete defects. Remote API checks
confirmed only PR195 open, analytics disabled_manually, and security-update
PRs disabled. No dependencies were added or upgraded; UI validation not applicable.
