---
title: Establish InfraFlow as the product feature name
type: bugfix
created: '2026-11-04'
status: done
route: one-shot
baseline_commit: 5c89788
---

# Establish InfraFlow as the product feature name

## Intent

**Problem:** Automation/Infrastructure Automation display labels obscure the selected InfraFlow identity.

**Approach:** Apply InfraFlow and the Workflow icon throughout current customer-facing code and guides, preserving stable routes and protocols. Keep the entry immediately before Settings.

## Suggested Review Order

- One navigation component supplies the InfraFlow label and Workflow icon everywhere.
  [AutomationNavigation.tsx:4](../../frontend/src/screens/AutomationNavigation.tsx#L4)

- Common feature headings and gated states expose the same approved name.
  [InfraAutomationShared.tsx:118](../../frontend/src/screens/InfraAutomationShared.tsx#L118)

- Customer-facing adapter errors use the product name.
  [infraAutomation.ts:35](../../frontend/src/api/infraAutomation.ts#L35)

- Current operator navigation guidance follows the new branding.
  [browser-ui.md:1](../../docs/infra-automation/browser-ui.md#L1)

- Browser checks retain the selected sidebar order and route behavior.
  [local-account.spec.ts:16](../../frontend/e2e/local-account.spec.ts#L16)
