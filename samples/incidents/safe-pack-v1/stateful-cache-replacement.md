# Sample incident: cache cluster replacement during release

Sample data: yes
Provenance: Synthetic scenario authored for public documentation and demos.
Permission: Original synthetic documentation content approved for public sample use.
Contains real customer data: no
Contains real organization names: no
Contains non-public postmortem content: no

Limitations:
- This record is not a real cache outage report.
- The resource names and operational details are simplified for demonstration.

Date: 2026-04-09
Severity: medium

## Summary

A release replaced `cache_primary` without a warm-up window. Checkout pages remained available, but response latency increased while the cache rebuilt from backing services.

## Root cause

The infrastructure change treated a stateful cache replacement as a routine update and did not include a capacity or warm-up verification step.

## Trigger change

The plan replaced `cache_primary` after a configuration change to node sizing and maintenance timing.

## Affected services

- checkout-api
- catalog-query

## Rollback path

Pause the rollout, restore the prior cache configuration, and confirm the rebuilt cache has reached the expected hit ratio before continuing.

## Prevention notes

Treat stateful cache replacement as a risk pattern, confirm restore or warm-up behavior, and call out degraded-cache effects in the deployment briefing.
