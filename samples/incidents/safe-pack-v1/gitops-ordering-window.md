# Sample incident: GitOps sync ordering exposed stale configuration

Sample data: yes
Provenance: Synthetic scenario authored for public documentation and demos.
Permission: Original synthetic documentation content approved for public sample use.
Contains real customer data: no
Contains real organization names: no
Contains non-public postmortem content: no

Limitations:
- This record is a fictional GitOps ordering example.
- The sequence is condensed to keep demos short and understandable.

Date: 2026-04-18
Severity: low

## Summary

A configuration map update reached the cluster before the deployment that understood the new key. The service stayed online, but feature flags briefly used stale defaults.

## Root cause

The sync wave placed configuration ahead of application rollout without a compatibility check for old pods.

## Trigger change

`checkout-flags` added a required setting before `checkout-api` pods with the matching parser were available.

## Affected services

- checkout-api
- feature-router

## Rollback path

Revert the configuration map to the prior compatible key set, wait for pods to converge, and apply the application update before reintroducing the setting.

## Prevention notes

Review GitOps ordering, verify backward compatibility for configuration keys, and include sync-wave assumptions in the deployment report.
