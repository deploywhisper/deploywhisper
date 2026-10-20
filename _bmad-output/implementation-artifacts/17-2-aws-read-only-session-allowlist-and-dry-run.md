# Story 17.2: AWS Read-Only Session, Allow-List Enforcement and Dry-Run

Status: backlog
Preparation: refined
Release: v1.5.0 (shared release train with Epic 16) | Priority: P0 within the independent Epic 17 lane

## Story

As a security-conscious operator, I want DeployWhisper's AWS access to be mechanically read-only, credential-free at rest and reviewable before I grant anything, so that I can authorize grounding without expanding my risk surface.

## Implementation gates

- Blocked until 17.0 records the approved dependency decision and 17.1 lands the connector contract, registry and snapshot model.
- Hard earlier dependencies: **17.0, 17.1**. **No Epic 16 dependency; do not import from `infra_automation/` or `services/infra_automation_*`.**
- This slice proves credential, allow-list, targeting and dry-run contracts using **recorded provider fixtures and a local credential harness**. Production reads against a live account are owned by 17.3 and 17.9.
- The read-only guarantee is the single highest-stakes property in Epic 17. Any finding that weakens it is a blocking gap, not a follow-up.

## Acceptance Criteria

1. **AC1:** Given an action absent from the allow-list, when the connector is asked to issue it, then the call is refused before construction and the refusal is recorded.
2. **AC2:** Given the allow-list, when CI runs, then every entry is asserted non-mutating against the provider read-only verb set, and a deliberately introduced mutating verb fails the build.
3. **AC3:** Given ambient credentials from profile, SSO, environment, instance role or IRSA, when a session is resolved, then no credential material appears in any log, snapshot, API response, CLI output or persisted record.
4. **AC4:** Given caller-supplied connector configuration, when a client is constructed, then endpoint, host, role and account cannot be retargeted, and only provider-canonical resolution is used.
5. **AC5:** Given dry-run, when it executes for a recorded plan, then it enumerates the exact calls that would be issued **without resolving or using credentials**.
6. **AC6:** Given the published minimal IAM policy, when it is compared to the allow-list, then they are equivalent, and each capability has a documented required-permission map.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-008 | Resolve credentials only from the operator's ambient provider chain; never accept, persist, log or echo credential material. | Secret-corpus regression across logs, snapshots, API and CLI |
| LEG-FR-009 | Enforce read-only access through a deny-by-default action allow-list evaluated before any call is constructed, backed by a published minimal IAM policy covering exactly the allow-listed actions. | Refusal tests and policy-to-allow-list equivalence test |
| LEG-FR-010 | Provide a dry-run mode that enumerates the exact API calls that would be issued for a given plan without resolving or using credentials. | Dry-run executed with no credentials available |
| LEG-FR-011 | Reject caller-controlled endpoint, host, role or account targeting; use provider-canonical resolution only. | Confused-deputy and SSRF configuration corpus |
| LEG-FR-012 | Bound every collection with per-call timeout, total deadline, concurrency cap, call budget, backoff and cancellation. | Bounded-execution tests against recorded fixtures |
| LEG-NFR-001 | The read-only guarantee must be mechanically enforced; introducing a mutating verb fails CI. | Verb assertion with a deliberate failing case |
| LEG-NFR-002 | No credential material may appear in any output, log or persisted record. | Secret-corpus regression |
| LEG-NFR-005 | Access must be minimal-privilege with a documented per-capability permission map. | Per-capability denial tests |
| LEG-NFR-007 | Calls go directly from the operator's environment to the provider with no DeployWhisper-operated intermediary. | Egress inspection in the composed app |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-2-aws-read-only-session`. Each packet owns the named paths.

- [ ] **Packet 2.1: Allow-list and refusal path — owner: security-focused implementer.**
  - Owned write paths: `cloud/aws/allowlist.py`, `tests/test_cloud/aws/`.
  - Output: deny-by-default action allow-list evaluated before call construction; recorded refusals; per-capability permission map.
  - Acceptance proof: AC1, AC6 — refusal tests and permission-map coverage.
- [ ] **Packet 2.2: Mechanical verb assertion in CI — owner: security-focused implementer.**
  - Owned write paths: `tests/test_cloud/aws/`, `scripts/ci-local.sh` registration.
  - Output: a test asserting every allow-list entry matches the provider read-only verb set (`Describe*`, `Get*`, `List*`, `BatchGet*`, `Head*`), plus a deliberate failing case proving the assertion bites.
  - Acceptance proof: AC2 — LEG-NFR-001 evidence including the failing case.
- [ ] **Packet 2.3: Ambient session resolution and secret absence — owner: implementer.**
  - Owned write paths: `cloud/aws/session.py`, `config.py` **additive redaction entries only**, `tests/test_cloud/aws/`.
  - Output: ambient-chain-only resolution across profile, SSO, environment, instance role and IRSA; no credential acceptance, persistence, logging or echo.
  - Acceptance proof: AC3 — secret-corpus regression over logs, snapshots, API and CLI.
  - **Shared-file rule:** `config.py` edits are additive redaction entries only; extend the existing AWS redaction set rather than replacing it.
- [ ] **Packet 2.4: Targeting hardening — owner: security-focused implementer.**
  - Owned write paths: `cloud/aws/session.py`, `tests/test_cloud/aws/`.
  - Output: rejection of caller-supplied endpoint, host, role and account targeting; provider-canonical resolution only.
  - Acceptance proof: AC4 — confused-deputy and SSRF configuration corpus.
- [ ] **Packet 2.5: Bounded execution primitives — owner: implementer.**
  - Owned write paths: `cloud/aws/client.py`, `tests/test_cloud/aws/`.
  - Output: per-call timeout, total deadline, concurrency cap, call budget, backoff and cancellation using the 17.0 measured defaults.
  - Acceptance proof: AC1–AC5 bounded behaviour; LEG-FR-012 evidence.
- [ ] **Packet 2.6: Dry-run and published policy — owner: implementer and documenter.**
  - Owned write paths: `cloud/aws/`, `docs/live-environment-grounding/aws-read-only-policy.json`, `docs/live-environment-grounding/README.md`.
  - Output: credential-free dry-run enumerating intended calls; published minimal IAM policy; policy-to-allow-list equivalence test.
  - Acceptance proof: AC5, AC6.

## Dev Notes

- `config.py` already redacts `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_SECRET_KEY` and `AWS_SECURITY_TOKEN`. Extend that set; do not build a parallel mechanism.
- Reuse `services/content_security.py` for redaction. The secret-corpus regression must cover log records, persisted snapshots, API responses and CLI stdout and stderr.
- Dry-run must work on a machine with no credentials configured at all. If dry-run resolves credentials, AC5 fails regardless of whether a call is issued.
- The published policy is operator-facing security documentation. If the allow-list changes, the policy and the equivalence test must change in the same PR.
- Direct egress only: calls go from the operator's environment to the provider. No DeployWhisper-operated proxy, relay or intermediary may be introduced.
- Respect Python 3.10-compatible code on a 3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. Dependency changes are limited to the option approved in 17.0 Packet 0.2; no other dependency installation is authorized.
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate capability; account-wide inventory; scheduled drift; cost estimation. Reports remain advisory with `should_block=False`.
- Epic independence: a grep for `infra_automation` under `cloud/` must return nothing.

### Project Structure Notes

`cloud/aws/` holds the AWS connector per architecture §26.3; `tests/test_cloud/aws/` must be reachable from the registered `tests/test_cloud/` shard in `scripts/ci-local.sh`.

### Testing requirements

- Before changing constructors or schema, search the entire repository for direct instantiations and fixtures; update all of them.
- Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for any serializer, settings or CLI contract change.
- Record the deliberate-failing-verb demonstration as explicit evidence; a passing assertion alone does not prove the assertion bites.
- Never use real production credentials against a production account without explicit operator authority. Never commit credentials, real account identifiers or real ARNs.
- UI validation not applicable.

### Completion and integration boundary

- Attach exact commands, results, versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice closes only the credential, allow-list, targeting, bounded-execution and dry-run contracts. It does not qualify a production AWS profile and must not claim live AWS grounding works.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Operator guide and minimal policy](../../docs/live-environment-grounding/README.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Planning preparation only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no implementation, security review, qualification or runtime test performed.
- Commands and proofs above are future obligations, not results.

### File List
- `_bmad-output/implementation-artifacts/17-2-aws-read-only-session-allowlist-and-dry-run.md` (story specification only).
