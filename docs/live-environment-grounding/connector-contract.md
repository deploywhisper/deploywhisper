# Cloud Connector Contract — Contributor Guide

> **Foundation implemented by Story 17.1.** The provider-neutral contract, registry, immutable screened snapshots and network-free reference conformance seed are available. AWS, Azure and GCP remain explicitly unimplemented. Production provider enforcement and the complete conformance suite remain with their owning later stories, including 17.9.
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

A connector implements the `CloudConnector` protocol in `cloud/base.py`. It receives an immutable tuple of `ResourceIdentity` values and keyword-only `project_id` and server-issued opaque `scope_id`, and returns a `LiveContextSnapshot`. The maskable `scope` display is distinct from authorization identity. The digest binds the normalized UTC read window, provider/project/scope identity, sorted resource results, selected scalar facts, action set, completeness and screening status.

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

## Implemented foundation integration

`cloud.base` supplies deeply frozen identities, scalar facts, per-resource read states and snapshots. `build_snapshot` creates a canonical observation; `validate_snapshot` requires and rechecks the retained digest, including tampered model-copy instances. Raw bodies, state, plans, user-data aliases and credential echoes are screened by `cloud.redaction` before persistence. Removed sensitive facts make the read partial. Display account masking never rewrites the opaque authorized scope identity.

`cloud.reference.ReferenceCloudConnector` is a pure pre-seeded fixture provider. It is absent from the default registry and must be injected by trusted server/test code. Its missing observations have explicit causes; it never invents a successful empty response for a nonempty request. Production provider slots remain unimplemented.

`CloudContextService` is an internal integration boundary. Its constructor accepts a server-installed authorization unit-of-work port; absence is unavailable, not default-allow. The port owns an explicit SQLite `BEGIN IMMEDIATE`, commits/rollbacks, and current project/operation authorization. Request objects must never supply a port, role claim, permission boolean, endpoint or credential. Disabled/unconfigured projects return before connector construction. No default analysis hook, UI or provider SDK is added by this foundation.

Enabling a configuration initializes the independently versioned cloud schema under that checked transaction. `models.cloud_snapshots` has its own metadata, and `cloud.schema` checks its own table/guard/version namespace. The core migration head and qualified shared model sources stay unchanged. Schema, marker and project setting creation are atomic; absent, partial or unknown namespace states are not silently adopted. Schema installation requires the real SQLite transaction and foreign-key enforcement.

Use `admit_evidence(project_id, digest)` for publication. It keeps the same authorization transaction open while the caller obtains `evidence_for(resource_address, fact_name, finding_id, ...)` and persists the report through its yielded session with `commit=False`. Evidence summaries derive from retained observed facts. Unreadable, partial, absent, corrupted or purged observations cannot mint a grounded claim. Publication checks private expected values, real report/workspace ownership, all live-state rows and same-report references before the UOW commits. Existing live-state rows must retain their complete stored values throughout admission; edits, deletions and source relabelling are rejected, including rows in other projects. Session and SQLAlchemy Connection commits (including explicit SQL COMMIT/END) are blocked until validation finishes; a caught early-commit error still invalidates the admission. Integral floating-point account facts are masked under the same policy as integer account facts. The current profile admits one snapshot per publication; unrelated artifact evidence can coexist. Direct ORM calls outside this boundary are not cloud evidence admission.

Snapshots expire seven days after observation when unreferenced. Existing retained report/evidence references extend payload lifetime; disabling or rotating current configuration preserves authorized historical inspection. An admission reserved before expiry publishes its report reference atomically. Duplicate observations never reset age, and a purged observation cannot be resurrected or returned as a retained collection result. Lawful expiry clears the body once while keeping nonsecret provenance. Explicit project deletion cascades snapshots and removes the project cloud setting; ID reuse cannot inherit opt-in.

The SQLite snapshot table is `WITHOUT ROWID`, rejects conflicting inserts/REPLACE and arbitrary updates/deletes, and verifies retained canonical payloads/digests on read. Database-owner DDL tampering is outside this application-level admission boundary and causes namespace validation failure when detected.

Reference-profile isolation runs with provider SDK imports, unrelated execution-module imports and networking blocked:

```sh
./.venv/bin/python scripts/verify_cloud_isolation.py
./.venv/bin/python -m pytest tests/test_cloud tests/test_evidence tests/test_models/test_cloud_snapshot_storage.py -v --tb=short
```

Future provider-specific SDK suites need a separate qualification profile; preserve the SDK-free foundation and independent import-graph checks. Production-scale admission metadata scans and live transport/cancellation remain later collector qualification obligations. A new production provider must still satisfy every hard requirement above.
