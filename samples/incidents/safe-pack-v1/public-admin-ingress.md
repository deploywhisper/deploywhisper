# Sample incident: public SSH ingress during checkout deploy

Sample data: yes
Provenance: Synthetic scenario authored for public documentation and demos.
Permission: Original synthetic documentation content approved for public sample use.
Contains real customer data: no
Contains real organization names: no
Contains non-public postmortem content: no

Limitations:
- This record is not evidence that any real team experienced this failure.
- The service names and timeline are fictional and intentionally generic.

Date: 2026-04-02
Severity: high

## Summary

An infrastructure-as-code change opened SSH ingress on port 22 from `0.0.0.0/0` while preparing a checkout-api deployment. The review missed the rule because the change was bundled with unrelated tag updates.

## Root cause

The security group rule used a broad CIDR for temporary troubleshooting and the rollback checklist did not include a network exposure check.

## Trigger change

`cloud_security_group_rule.checkout_admin_ssh` changed `cidr_blocks` to `["0.0.0.0/0"]` for port 22.

## Affected services

- checkout-api
- deployment-runner

## Rollback path

Replace the public CIDR with the documented trusted access range and rerun the network policy check before redeploying.

## Prevention notes

Require evidence for public administrative ingress, keep temporary access time-boxed, and verify report warnings before approval.
