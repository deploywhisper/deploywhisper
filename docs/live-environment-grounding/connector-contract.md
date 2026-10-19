# Cloud Connector Contract — Contributor Guide

> **Status: planned, not implemented.** This guide specifies the contract that Epic 17 will publish so a community contributor can add a cloud provider without maintainer-specific knowledge. The executable conformance suite referenced here is delivered by Story 17.9. Nothing in this document is a capability claim.
>
> Governance: [RFC 0002](../rfcs/0002-live-environment-grounding.md) · Requirements: [feature PRD](../../_bmad-output/planning-artifacts/prd-live-environment-grounding.md) · Architecture: [§26](../../_bmad-output/planning-artifacts/architecture.md)

## Design intent

A connector supplies **read-only, plan-directed observations** of the resources a proposed change touches. It does not analyze, score, decide or render. All reasoning stays in the existing analysis core.

The contract exists so that adding AWS, Azure, GCP or anything else requires **no change to core analysis, scoring, blast radius or report code** (`LEG-NFR-010`). If your provider requires a core change, the contract is wrong and the fix belongs in the contract, not in a special case.

The pattern deliberately mirrors two existing extension points you should read first:

- `parsers/registry.py` — the registration shape.
- `services/topology_service.py`, specifically `TOPOLOGY_SOURCE_REGISTRY`, `_read_kubernetes_live_state` (the live-source precedent, including its explicit degradation warnings) and `_build_unimplemented_source_handler` (the honest-failure precedent).

## Where code lives

```
cloud/
  base.py          # CloudConnector protocol, ResourceIdentity, ReadStatus, LiveContextSnapshot
  registry.py      # provider registration; explicit unimplemented and unknown behaviour
  redaction.py     # snapshot redaction built on services/content_security.py
  reflection.py    # plan-directed identity extraction and one-hop expansion
  portability.py   # snapshot export and import
  <provider>/      # your connector
tests/test_cloud/
  conformance/     # the suite your connector must pass
  <provider>/
```

`tests/test_cloud/` must be explicitly registered in `scripts/ci-local.sh` and the relevant GitHub shard. Recursive root discovery skips directories that are not Python packages.

## The contract

A connector implements the `CloudConnector` protocol in `cloud/base.py`. It receives a set of `ResourceIdentity` values derived from the parsed change and returns a `LiveContextSnapshot`.

### Hard requirements

These are not style guidance. A connector that violates any of them fails conformance.

1. **Read-only.** Every action you issue must be non-mutating and must appear in your connector's deny-by-default allow-list. The allow-list is evaluated **before a call is constructed**, and CI asserts every entry matches the provider's read-only verb set. A connector that can mutate is not mergeable at any severity of justification.
2. **No enumeration.** Never scan an account, a subscription, a project or a region. Read only the identities you were given, plus exactly one reverse hop of real dependents, each with a recorded bound and reason. A connector that enumerates fails conformance even if it discards the results.
3. **Ambient credentials only.** Resolve credentials from the operator's ambient provider chain. Never accept credentials as a parameter, never persist them, never log them, never place them in a snapshot.
4. **No caller-controlled targeting.** Configuration must not let a caller retarget your client at an arbitrary endpoint, host, role, account, subscription or project. Use provider-canonical resolution only.
5. **Bounded execution.** Honour the per-call timeout, total deadline, concurrency cap and call budget you are given. Support cancellation. Return partial labelled results rather than exceeding the deadline.
6. **Honest degradation.** Label partial reads as partial. Enumerate every unreadable resource with the **exact** missing permission or failure cause, not a generic error. Never imply completeness from a partial read. Never return a successful empty result when you actually failed.
7. **Deterministic snapshots.** The same observation must yield the same content digest. Record provider, scope, regions, read window, per-resource read status and the exact set of actions you issued.
8. **Redaction before persistence.** Route your snapshot through `cloud/redaction.py`. No secret values, credential material, user data, raw state or plan bytes. Account identifiers must be maskable by configuration.
9. **Classify, do not fail, on absence.** An identity with no physical counterpart — a pure create — is `no_live_counterpart`. That is a success classification, not an error and not `unreadable`.
10. **Published minimal policy.** Ship a minimal provider policy covering exactly your allow-listed actions, plus a per-capability permission map. The equivalence between the policy and the allow-list is asserted by test.

### Must-not list

Connectors must never: write, apply, destroy, tag, provision or remediate; create a snapshot or enable a backup; call a DeployWhisper-operated relay or any third-party intermediary; introduce a parallel freshness vocabulary; lower a severity or raise a confidence value; or reach into analysis, scoring or reporting code.

### Vocabulary reuse

Use the existing vocabulary in `evidence/models.py`. Do not invent parallel states.

- Freshness: `current`, `stale`, `missing`, `incomplete`, `conflicting`, `unknown`.
- Determinism: grounded observations are `deterministic`.
- Evidence source: `live_state`.

Disagreement between a declared value and a live value is `conflicting`. Do not silently prefer one source.

## Registration

Register your provider in `cloud/registry.py`. Providers that are not implemented must be registered as **explicit stubs that fail honestly**, exactly as `cloudformation` and `ansible` do in `TOPOLOGY_SOURCE_REGISTRY`. Partial support shipped as "experimental" is not acceptable: an operator must be able to tell the difference between "this provider is unsupported" and "this provider found nothing".

Unknown and unregistered providers must fail explicitly and must never silently no-op into a successful empty result.

## Conformance

Your connector must pass `tests/test_cloud/conformance/` without modification to that suite and without any diff to core analysis. The suite covers:

| Area | What is checked |
| --- | --- |
| Read-only enforcement | Non-allow-listed action refused before construction; allow-list verbs asserted non-mutating |
| Anti-enumeration | An enumerating connector is rejected |
| Credential hygiene | No credential material in logs, snapshots, API responses or CLI output |
| Targeting | Caller-supplied endpoint, host, role and account are rejected |
| Bounded execution | Deadline, cancellation and slow-provider fault injection |
| Degradation | Unreachable, partial, denied, throttled and expired cases never improve a verdict |
| Snapshot | Digest reproducibility, redaction, partial labelling, `no_live_counterpart` |
| Core isolation | No diff to core analysis, scoring, blast radius or report code |

Run it as part of the registered `tests/test_cloud/` shard:

```
./.venv/bin/python -m pytest tests/test_cloud -v --tb=short
bash scripts/ci-local.sh
./.venv/bin/ruff check . && ./.venv/bin/ruff format --check .
```

## Contribution checklist

- [ ] Connector lives entirely under `cloud/<provider>/`; no core analysis diff.
- [ ] Deny-by-default allow-list present; every entry non-mutating; verb assertion passes.
- [ ] Minimal provider policy published; equivalence to the allow-list asserted by test.
- [ ] Per-capability permission map documented.
- [ ] Credential-free dry-run enumerates intended calls.
- [ ] Conformance suite passes unmodified.
- [ ] Fixtures are synthetic; no real account identifiers, resource identifiers or captured state committed.
- [ ] Degradation paths produce exact missing-permission causes, not generic errors.
- [ ] Documentation updated alongside the code.

## Security reporting

A connector defect that could enable a mutating call, credential disclosure or cross-account targeting is a security issue, not a bug. Report it through the project's security policy rather than opening a public issue.

## Related documents

- [RFC 0002 — Live Environment Grounding](../rfcs/0002-live-environment-grounding.md)
- [Operator guide](README.md)
- [Minimal AWS read-only policy](aws-read-only-policy.json)
- [Architecture §26](../../_bmad-output/planning-artifacts/architecture.md)
