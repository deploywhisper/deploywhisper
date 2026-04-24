---
name: istio
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [virtualservice.yaml, destinationrule.yaml, authorizationpolicy.yaml]
token_budget: 1350
tags: [istio, service-mesh, kubernetes]
description: Istio traffic-management and policy guidance for routing, mTLS, and authorization changes.
test_suite_path: tests/skill-tests/istio
trigger_content_patterns: ["networking.istio.io", "security.istio.io"]
---

## Critical risk patterns

- VirtualService host, match, or gateway rewrites can blackhole traffic across multiple services = CRITICAL
- DestinationRule TLS mode mismatches commonly surface as cascading 503 errors = HIGH
- AuthorizationPolicy allow rules with broad principals or namespaces expand lateral access = HIGH
- PeerAuthentication set to `STRICT` before workloads are mesh-ready can trigger downtime = HIGH

## Review cues

- Review Istio routing and policy changes together because safe config depends on mesh-wide consistency.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
