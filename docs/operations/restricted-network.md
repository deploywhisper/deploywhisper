# Restricted-network core analysis

## Installation boundary

Core parsing, scoring and evidence generation run locally. Narrative generation may degrade when no local model is available; that must remain visible in report uncertainty. [The recorded offline CLI exercise](../verification/operations/core-offline-results.json) ran actual analysis with Docker network disabled and obtained a persisted advisory report with explicit narrative degradation. It used an already available production image on an installed Docker host; it does not establish cold OS/Docker installation or independent human self-service acceptance.

On a connected staging host, obtain the approved image by immutable digest and its release-matched checksums/signatures/provenance. Transfer a `docker save` archive through the approved medium, verify its digest on the destination, then `docker load`. Match CPU architecture and operating-system support. Do not run `docker pull`, `pip install`, `npm install` or a source build on a disconnected host and assume caches will exist. The production image includes built SPA assets and does not require runtime Node.

For a source-based installation, prepare and verify the complete locked Python wheelhouse for the exact interpreter/platform, frontend build inputs and all transitive dependencies before transfer. Missing platform wheels or native build tools block that path. No cold source-installation qualification is claimed by the image exercise. Install the operating system and Docker separately using their approved offline procedures.

## Launch and analysis

Use private persistent storage owned by the image's nonroot user. Configure database and identity settings through private operator mechanisms; do not copy examples containing real credentials. Apply migrations with the release-matched tooling, bootstrap authorized accounts/project membership where required, and run a synthetic CLI analysis before accepting real data. Use `python -m cli.analyze analyze --project <project-key> --agent-json <artifact>` inside the prepared image. The project must already exist and the caller must have applicable permissions.

For a strict offline verification, run in an isolated Docker network with no external route (`--network none`), use `docker exec` for loopback access when needed, and keep the application data volume separate from test fixtures. Verify a report is persisted, deterministic findings/evidence are present, `advisory_only` remains true and narrative/provider failure is honestly reported. This test does not require a provider key. Never weaken authentication or permit provider credentials merely to suppress a narrative-degraded warning.

## Optional services and limitations

| Feature | Offline expectation |
| --- | --- |
| Deterministic analysis | Local artifacts and existing context remain usable; missing context still lowers certainty |
| Narrative providers | Cloud providers unavailable; a local Ollama service also needs its model installed beforehand and an approved local route |
| Skill registry and updates | Remote discovery/download unavailable; transfer reviewed local-source skills and dependencies separately |
| GitHub/cloud/connectors | Remote context and API actions unavailable; use authorized local snapshots without claiming freshness |
| Tool caches | Pre-stage exact operator-approved versions and digests; see [runner network/cache rules](../infra-automation/network.md) |
| Updates | Import a separately verified release; retain prior image and coordinated backup; do not silently use mutable tags |
| Time | Maintain trusted local time; clock rollback or expired authority must fail closed |

For restricted rather than fully disconnected networks, document exact destinations, DNS/proxy/CA ownership, credentials and failure behavior. Egress permission is not authorization for an infrastructure action. Local-only operation does not qualify remote runners, receivers or provider support.

## Acceptance record

Record image/source identity, platform, installation source, network policy, schema, synthetic input digest, CLI exit code, persisted report/evidence and degraded-service behavior. Exclude secrets and raw infrastructure material. Repeat after upgrades and test restore/rotation using [data lifecycle](data-lifecycle.md) and the coordinated InfraFlow runbook. Separate operator review and cold-installation coverage remain outstanding where required; existing cached-image proof must not be relabelled as those exercises.
