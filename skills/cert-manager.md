---
name: cert-manager
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [cert-manager-certificate.yaml, clusterissuer.yaml, issuer.yaml]
token_budget: 1250
tags: [cert-manager, tls, kubernetes]
description: Cert-Manager issuance and renewal guidance for issuer, solver, and secret-rotation changes.
test_suite_path: tests/skill-tests/cert-manager
trigger_content_patterns: ["cert-manager.io/"]
---

## Critical risk patterns

- Replacing a ClusterIssuer can break renewals for every dependent certificate = CRITICAL
- DNS01 or HTTP01 solver changes can stall issuance and leave certificates to expire = HIGH
- Secret name rotation without workload coordination causes immediate TLS outages = HIGH
- Certificate durations outside issuer policy can trigger noisy renewal loops = MEDIUM

## Review cues

- Review issuer scope, solver reachability, and secret consumers together for cert-manager changes.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
