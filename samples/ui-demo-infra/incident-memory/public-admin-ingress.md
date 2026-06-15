---
title: Checkout admin ingress exposure during release
severity: high
incident_date: "2026-04-02"
affected_services:
  - checkout-api
  - edge-gateway
source:
  system: manual
  reference: DEMO-INC-001
redaction:
  status: redacted
  contains_sensitive_data: false
---

# Checkout admin ingress exposure during release

## Root cause

A temporary troubleshooting rule opened administrative SSH ingress to the public
internet and remained in the deployment plan after the release window closed.

## Trigger change

`aws_security_group.checkout_admin` changed the SSH ingress CIDR from a trusted
operator range to `0.0.0.0/0`.

## Rollback path

Restore the trusted CIDR, rerun network exposure checks, and verify that the
checkout API remains reachable only through the public application ingress.

## Prevention notes

Require expiry and owner evidence for public administrative ingress, keep
temporary access in a separate review, and verify topology impact before
approval.
