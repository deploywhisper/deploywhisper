# InfraFlow v1.5.0 supported profile

This matrix defines the only profile eligible for v1.5.0 release qualification.
Anything not named here is unsupported until separately qualified. Tool licenses
remain independent; DeployWhisper does not redistribute OpenTofu or Terraform.

| Component | Supported profile | Evidence / limitation |
| --- | --- | --- |
| Application | One self-hosted FastAPI instance, Python 3.11, singleton SQLite, local artifact storage | No PostgreSQL, HA or multi-writer automation claim |
| Web UI | Production-built React SPA served by FastAPI at the same HTTPS origin | Composed keyboard/axe journeys at 1440/760; Node is build-only |
| Host allocation | Linux ARM64 container, 4-CPU quota, 8 GiB cgroup memory, Docker Desktop VM backed by local APFS solid-state storage | Virtualized reference profile, not dedicated bare metal |
| Collection tool | Operator-installed OpenTofu 1.13.1 | Offline immutable image/catalog/profile digest in the Story16.19 evidence |
| Runner | Linux ARM64 isolated Docker profile, runner protocol1, runner version1.0, twenty compatible processes for claim measurement | Other OS/architectures, remote fleets and alternate sandbox engines unqualified |
| Evidence transport | Screened collected-plan JSON over authenticated runner protocol; exact raw bytes remain in local protected custody | No raw state, credentials or binary plan in server/public artifacts |
| Receiver | Reference exact saved-plan receipt with durable consume/restart/duplicate fences and local protected custody | No claim that DeployWhisper applies infrastructure; broader hosted/cloud custody unqualified |
| Material authority | Co-located separate-UID authority/receiver process, Ed25519-signed monotonic ledger, public-key-only app verification and live Unix custody probe | Remote authority services unsupported; private signing key/raw custody must never enter the app process |
| Identity | Verified local human accounts/memberships over operator-configured HTTPS; distinct runner/service credentials | No SSO support claim |
| Trigger surfaces | Human UI/API/CLI and bounded signed trigger intake | Triggering never supplies human approval authority |
| Narrative | Optional; deterministic analysis remains usable with AI disabled or degraded | Canonical reports remain advisory (`should_block=false`) |

## Explicitly unsupported

- Apply, destroy, remediation, unattended approval or emergency bypass.
- Terraform binary support in the released matrix, cloud IAM/remote-state profiles,
  alternate providers and arbitrary scripts/plugins.
- Kubernetes/Helm/Ansible collectors, Git sync, generic package execution,
  PostgreSQL/HA/multi-worker automation and automatic unit inference.
- Universal secret-redaction, complete runner truth or host-power-loss durability.
- Epic 17 Live Environment Grounding, which was cut back to v1.6.0.

## Release-evidence limits

The independent human self-service pilot was **not executed**. The accountable
maintainer approved the bounded v1.5.0 waiver and accepted the residual runbook
usability risk. This is not human pilot evidence and does not expand this matrix.
Public release remains subject to the final signed-artifact, provenance, review,
performance and publication gates recorded by Story16.19.
