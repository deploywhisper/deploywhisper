# Story 17.0: Adopt and Qualify the Grounding Contract

Status: done
Preparation: refined
Release: v1.6.0 (independent release train) | Priority: P0 within the independent Epic 17 lane

## Story

As a maintainer, I want to settle the read-only grounding contract with governance, an explicit dependency decision and executable feasibility evidence, so that implementation starts with a proven trust boundary rather than assumptions about credentials, provider behaviour, latency and cost.

## Implementation gates

- Governance source: [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md), **Accepted 2026-10-19**. Acceptance authorizes this story only; a recorded Story 17.0 close is still required before any downstream Epic 17 story is promoted.
- AC1 is partially satisfied by the recorded RFC acceptance. Packet 0.1 must still confirm CODEOWNERS coverage for `cloud/` and scope agreement with the parent PRD and architecture §26.
- Canonical requirements: [feature PRD](../planning-artifacts/prd-live-environment-grounding.md), `LEG-FR-001..040` and `LEG-NFR-001..012`.
- Hard earlier dependencies: the current released baseline only. **This story has no Epic 16 dependency and must not acquire one.**
- This story is governance and feasibility qualification. It does **not** implement the product feature and does not mark any downstream story done.
- Promote downstream stories only after the RFC decision, the approved dependency decision, recorded spike evidence and an independent readiness review.

## Acceptance Criteria

1. **AC1:** Given RFC 0002 and the parent PRD, when governance review completes, then a maintainer decision is recorded, feature scope agrees with the parent PRD and architecture §26, and the exclusion of every write, apply, destroy, tag, provision and remediate capability is stated in reviewable terms.
2. **AC2:** Given a missing RFC decision, missing approved dependency decision or missing feasibility result, when implementation readiness is evaluated, then the gate remains NOT READY and no downstream Epic 17 story is promoted.
3. **AC3:** Given an executable spike, when deny-by-default allow-list enforcement is exercised, then a non-allow-listed action is refused before call construction, and a published policy can be shown equivalent to the allow-list.
4. **AC4:** Given an executable spike, when dry-run runs with **no credentials available in the environment**, then it enumerates the exact intended calls for a recorded plan and issues none.
5. **AC5:** Given recorded Terraform and OpenTofu plan JSON across supported format versions, when prior-state extraction is exercised, then recorded prior state is reliably extracted and the fallback behaviour when it is absent is defined and demonstrated.
6. **AC6:** Given a realistic large plan fixture on named hardware, when a measurement spike runs, then total latency, call count and estimated provider cost are recorded, and defensible default deadline, concurrency cap and call-budget values are proposed with evidence.
7. **AC7:** Given the spike results, when the readiness report is written, then every unresolved question in RFC 0002 is closed by evidence, the AWS SDK dependency decision is explicitly approved or rejected with rationale, and the initial resource-family coverage list and per-capability permission map are frozen.
8. **AC8:** Given a threat model review, when it completes, then credential handling, confused-deputy and SSRF exposure, snapshot data sensitivity, and shared-host instance-role escalation are each assessed with a recorded disposition.

### Requirement Traceability

Coverage intent: this story **verifies feasibility** of the requirements below. Verification is not implementation.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-009 | Enforce read-only access through a deny-by-default action allow-list evaluated before any call is constructed, backed by a published minimal IAM policy covering exactly the allow-listed actions. | Prototype refusing a non-allow-listed action; policy-to-allow-list equivalence spike |
| LEG-FR-010 | Provide a dry-run mode that enumerates the exact API calls that would be issued for a given plan without resolving or using credentials. | Credential-free dry-run spike against a recorded plan |
| LEG-NFR-001 | The read-only guarantee must be mechanically enforced; introducing a mutating verb fails CI. | Verb-assertion prototype including a deliberate failing case |
| LEG-NFR-003 | Collection must be bounded and interruptible, returning partial labelled results within the total deadline. | Measured latency, call count and cost on a named large plan fixture |
| LEG-NFR-005 | Access must be minimal-privilege with a documented per-capability permission map. | Frozen coverage list and per-capability permission map |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on the story feature branch `feature/17-0-grounding-contract`. Each packet owns the named paths.

- [x] **Packet 0.1: Governance and scope adoption — owner: maintainer.**
  - Owned write paths: `docs/rfcs/0002-live-environment-grounding.md`, `_bmad-output/planning-artifacts/`.
  - Output: recorded RFC decision, CODEOWNERS coverage for `cloud/`, scope agreement with parent PRD and architecture §26.
  - Acceptance proof: AC1, AC2 — decision record and readiness gate statement.
- [x] **Packet 0.2: Dependency decision — owner: maintainer.**
  - Owned write paths: `docs/decisions/` or the RFC decision record.
  - Output: explicit approval or rejection of an AWS SDK runtime dependency, with the chosen option among runtime dependency, optional extra or thin signed-request client, plus supply-chain and lockfile impact.
  - Acceptance proof: AC7 — recorded dependency decision with rationale.
- [x] **Packet 0.3: Trust-boundary spikes — owner: security-focused implementer.**
  - Owned write paths: disposable spike directory, evidence packet under `docs/verification/live-environment-grounding/17-0/`.
  - Output: allow-list refusal prototype, credential-free dry-run, confused-deputy and SSRF configuration corpus, secret-absence check across logs and outputs.
  - Acceptance proof: AC3, AC4, AC8 — recorded spike results.
- [x] **Packet 0.4: Plan prior-state extraction spike — owner: implementer.**
  - Owned write paths: disposable spike directory, evidence packet.
  - Output: prior-state extraction across Terraform and OpenTofu plan format versions, with defined fallback when absent.
  - Acceptance proof: AC5.
- [x] **Packet 0.5: Latency, call count and cost measurement — owner: implementer.**
  - Owned write paths: disposable spike directory, evidence packet.
  - Output: measured results on named hardware for a realistic large plan; proposed defaults for deadline, concurrency and call budget.
  - Acceptance proof: AC6.
- [x] **Packet 0.6: Coverage freeze and readiness report — owner: maintainer.**
  - Owned write paths: `_bmad-output/planning-artifacts/implementation-readiness-report-<date>-live-environment-grounding.md`.
  - Output: frozen resource-family coverage list, per-capability permission map, all RFC unresolved questions closed, blocking-gap list.
  - Acceptance proof: AC7 — readiness report with no blocking gap or an explicit NOT READY verdict.

### Review Findings

- [x] [Review][Patch][P2] R1: Validate mandatory response postfilters [`docs/verification/live-environment-grounding/17-0/measurement/benchmark.py:206`]
- [x] [Review][Patch][P2] R2: Match Route53 routing variants by SetIdentifier [`docs/verification/live-environment-grounding/17-0/measurement/benchmark.py:197`]
- [x] [Review][Patch][P2] R3: Restrict benchmark SDK model loading to installed package data [`docs/verification/live-environment-grounding/17-0/measurement/benchmark.py:236`]
- [x] [Review][Patch][P2] R4: Drain completed results during throttle backoff [`docs/verification/live-environment-grounding/17-0/measurement/benchmark.py:305`]
- [x] [Review][Patch][P2] R5: Provide a provider-based request-cost estimate for AC6 [`docs/verification/live-environment-grounding/17-0/measurement/benchmark.py:413`]
- [x] [Review][Patch][P2] R6: Detect or explicitly label benchmark hardware identity [`docs/verification/live-environment-grounding/17-0/measurement/benchmark.py:382`]
- [x] [Review][Patch][P2] R7: Validate the frozen family set and operation references [`docs/verification/live-environment-grounding/17-0/coverage/validate_contract.py:60`]
- [x] [Review][Patch][P3] R8: Reject fractional and non-finite measurement bounds [`docs/verification/live-environment-grounding/17-0/measurement/benchmark.py:264`]

## Dev Notes

- Spikes are **disposable prototypes**. They must not introduce product APIs, migrations, routes or persisted entities, and they do not mark any downstream story done.
- No dependency installation is authorized before Packet 0.2 records an approved decision. Preserve the repository Python floor and existing locked dependencies.
- Spikes must never use real production credentials against a production account without explicit operator authority. Prefer a disposable sandbox account or recorded fixtures. Never commit credentials, account identifiers, ARNs from a real estate, or raw state.
- The read-only boundary is the highest-stakes property in this epic. Treat any spike finding that weakens it as a blocking gap, not a follow-up.
- Reuse existing facilities: `services/content_security.py` for redaction, `config.py` for the existing AWS environment redaction set, `evidence/models.py` for determinism and freshness vocabulary. Do not invent parallel models.
- This story must remain independent of Epic 16. Do not read, import or depend on `infra_automation/` or `services/infra_automation_*`.

### Testing requirements

- Spike evidence is recorded output, not product test coverage. Record exact commands, versions, hardware and results in the evidence packet.
- Run `./.venv/bin/python -m unittest discover -q` and `bash scripts/ci-local.sh` to confirm the repository remains green; this story changes documentation and disposable spikes only.
- Run `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .` if any Python file is added.
- UI validation not applicable.

### Completion and integration boundary

- Attach exact commands, results, versions and artifact locations per AC. Independent review resolves findings before advancement.
- This slice closes only governance and feasibility. It does not qualify a production provider profile, does not claim any `LEG-FR` is implemented, and does not authorize downstream implementation beyond the recorded decision.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Codex with bounded native agents for producer, SDK, measurement and coverage qualifications; separate independent read-only readiness reviewer.

### Debug Log References
- Evidence and reproduction: `docs/verification/live-environment-grounding/17-0/README.md`.
- Approved dependency and scan: `dependency-decision.md`, `sdk-requirements.lock`, `sdk-versions.json`, `sdk-audit.json` in that packet.
- Exact packet commands/results: `producer-results.json`, `sdk-results.json`, `bounded-measurement-results.json`, `coverage/results.json`, `retention/README.md`.
- Fresh repository regression logs: `/tmp/story17-0-approved-unittest.log`, `/tmp/story17-0-approved-ci.log`; final summaries retained in packet README.

### Implementation Plan
- Maintainer continuation explicitly approved choosing the best SDK/design and completing all qualification. Adopt optional boto3; install only isolated qualification dependencies; preserve default application locks and Python floor.
- Generate checksum-verified real producer exports in temporary directories using local built-in terraform_data. No cloud provider, production state or credentials.
- Exercise real SDK credential/endpoint/model-loader trust boundaries; freeze exact25-family request/action/field/permission map; use the same map for benchmark requests.
- Measure a realistic1000-resource mixed synthetic plan on named hardware with bounded response replay and explicit cost-rate input; record no live AWS claims.
- Adopt reference-bound retention and fixed credential mechanisms with executable tests. Independently review evidence and correct findings before advancing story status.

### Completion Notes List
- Packets0.1–0.6 completed for story-scoped governance and feasibility. Explicit maintainer approval recorded in RFC/dependency decision; optional boto3 selected, custom signer and mandatory default dependency rejected.
- Qualified seven-package SDK set is Python3.10-compatible by metadata/resolution, hash-locked and scanned with no known advisories. Default app dependencies and locks unchanged.
- Terraform1.17.2/1.16.7 and OpenTofu1.13.9/1.12.12 emitted actual planformat1.2; nested prior-state and absent/null/change.before/create fallbacks verified. Raw local state/binary plans discarded. Older synthetic shape probes remain historical, not qualified producer support.
- Real SDK probes constrain credentials to environment or trusted operator-selected shared files; deny all other fallthrough, caller overrides and external model data. Tests discovered and corrected AWS_PROFILE and AWS_DATA_PATH/home model injection paths.
- Frozen25families/42requesttemplates/33IAMactions; published exact policy/action/resource equality and response field map. Static plan-derived manifests, bounded filtered first pages, no account inventory/recursive expansion; absent facts remain unknown/incomplete.
- Large mixed1000-resource fixture yields900intended requests; deadline/concurrency/budget/cancellation/backoff and SDK request shapes verified.15s/4concurrent/100attempts/2spercall defaults supported by controlled50ms/200ms/1000ms scenarios. Cost estimate uses explicit sensitivity input, not universal AWS pricing.
- Snapshot retention adopted: seven days unreferenced from observation, extended by live report references; no import age reset; payload purge preserves nonsecret digest and reports missing evidence. Five decision tests pass.
- Independent review found benchmark operation drift; eliminated duplicate catalog and rendered frozen templates, adding exact membership, Lambda parent/UUID and SQS URL regressions. Independent re-review verified the fix and final fixture hash, with no blocking findings.43qualification checks pass.
- No product LEG-FR implementation, live AWS production profile or later security/release qualification claimed. No Epic16 dependency or downstream story completion introduced.
- UI validation not applicable. Application routes, persistence, runtime behavior and default dependency footprint unchanged.

- Fresh root validation passed2,128tests (3skips); full localCI passed3,603tests (3skips) plus skill/prompt-injection checks. Repo-wide Ruff lint/format passed645files; Bandit medium/high passed (eight low informational findings). Story moved to review; no downstream promotion.

- BMad code review requested changes:8patch findings, recorded in `docs/verification/live-environment-grounding/17-0/code-review.md`; story returned to in-progress. Implementation unchanged during review.

- Review findings R1–R8 repaired and independently closed. 68 qualification checks passed; fresh root discovery passed 2,128 tests (3 skipped); full local CI passed 3,603 tests across 10 shards (3 skipped), plus skill scenarios and 8 prompt-injection tests with 96 subtests. Repo-wide Ruff lint/format (647 files), Bandit medium/high gate, compilation, Python 3.10 syntax and fixture/link checks passed. Code review approved; story marked done for governance/feasibility only.

### File List
- `_bmad-output/implementation-artifacts/17-0-adopt-and-qualify-the-grounding-contract.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/architecture.md`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-11-12-live-environment-grounding.md`
- `docs/rfcs/0002-live-environment-grounding.md`
- `docs/verification/live-environment-grounding/17-0/README.md`
- `docs/verification/live-environment-grounding/17-0/bounded-measurement-results.json`
- `docs/verification/live-environment-grounding/17-0/code-review.md`
- `docs/verification/live-environment-grounding/17-0/coverage/coverage.json`
- `docs/verification/live-environment-grounding/17-0/coverage/iam-reference-evidence.json`
- `docs/verification/live-environment-grounding/17-0/coverage/permission-map.md`
- `docs/verification/live-environment-grounding/17-0/coverage/policy.json`
- `docs/verification/live-environment-grounding/17-0/coverage/results.json`
- `docs/verification/live-environment-grounding/17-0/coverage/test_contract.py`
- `docs/verification/live-environment-grounding/17-0/coverage/validate_contract.py`
- `docs/verification/live-environment-grounding/17-0/dependency-decision.md`
- `docs/verification/live-environment-grounding/17-0/final-verification.json`
- `docs/verification/live-environment-grounding/17-0/independent-review.md`
- `docs/verification/live-environment-grounding/17-0/measurement/README.md`
- `docs/verification/live-environment-grounding/17-0/measurement/benchmark.py`
- `docs/verification/live-environment-grounding/17-0/measurement/cost-rates.json`
- `docs/verification/live-environment-grounding/17-0/measurement/cost_model.py`
- `docs/verification/live-environment-grounding/17-0/measurement/large-plan.json`
- `docs/verification/live-environment-grounding/17-0/measurement/pricing-evidence.json`
- `docs/verification/live-environment-grounding/17-0/measurement/test_benchmark.py`
- `docs/verification/live-environment-grounding/17-0/measurement/test_cost_model.py`
- `docs/verification/live-environment-grounding/17-0/measurement-results.json`
- `docs/verification/live-environment-grounding/17-0/producer/README.md`
- `docs/verification/live-environment-grounding/17-0/producer/generate.py`
- `docs/verification/live-environment-grounding/17-0/producer/terraform-1.16.7.json`
- `docs/verification/live-environment-grounding/17-0/producer/terraform-1.17.2.json`
- `docs/verification/live-environment-grounding/17-0/producer/test_producers.py`
- `docs/verification/live-environment-grounding/17-0/producer/tofu-1.12.12.json`
- `docs/verification/live-environment-grounding/17-0/producer/tofu-1.13.9.json`
- `docs/verification/live-environment-grounding/17-0/producer-results.json`
- `docs/verification/live-environment-grounding/17-0/retention/README.md`
- `docs/verification/live-environment-grounding/17-0/retention/retention_spike.py`
- `docs/verification/live-environment-grounding/17-0/retention/test_retention.py`
- `docs/verification/live-environment-grounding/17-0/review-fix-verification.md`
- `docs/verification/live-environment-grounding/17-0/sdk/README.md`
- `docs/verification/live-environment-grounding/17-0/sdk/boundary.py`
- `docs/verification/live-environment-grounding/17-0/sdk/test_boundary.py`
- `docs/verification/live-environment-grounding/17-0/sdk-audit.json`
- `docs/verification/live-environment-grounding/17-0/sdk-requirements.lock`
- `docs/verification/live-environment-grounding/17-0/sdk-results.json`
- `docs/verification/live-environment-grounding/17-0/sdk-versions.json`
- `docs/verification/live-environment-grounding/17-0/spike/coverage.json`
- `docs/verification/live-environment-grounding/17-0/spike/plan-opentofu-1.0.json`
- `docs/verification/live-environment-grounding/17-0/spike/plan-opentofu-1.1.json`
- `docs/verification/live-environment-grounding/17-0/spike/plan-opentofu-1.2.json`
- `docs/verification/live-environment-grounding/17-0/spike/plan-terraform-1.0.json`
- `docs/verification/live-environment-grounding/17-0/spike/plan-terraform-1.1.json`
- `docs/verification/live-environment-grounding/17-0/spike/plan-terraform-1.2.json`
- `docs/verification/live-environment-grounding/17-0/spike/plan.json`
- `docs/verification/live-environment-grounding/17-0/spike/policy.json`
- `docs/verification/live-environment-grounding/17-0/spike/qualification.py`
- `docs/verification/live-environment-grounding/17-0/spike/test_qualification.py`
- `docs/verification/live-environment-grounding/17-0/spike-results.json`
- `docs/verification/live-environment-grounding/17-0/threat-model.md`

## Change Log

- 2026-11-12: Initial offline packet retained NOT READY gates. Maintainer then explicitly approved selecting and completing outstanding decisions. Added approved SDK qualification, real producer exports, frozen coverage/permissions, mixed-plan replay measurements and retention proof; independent review corrections integrated.
- 2026-11-12: Final independent readiness review and all validation passed; story and sprint status moved to review.
- 2026-11-12: BMad three-layer review found8patch items; readiness withdrawn pending fixes and story/sprint status set in-progress.
- 2026-11-12: Fixed all eight formal review findings; added25 qualification checks, regenerated evidence, independently re-reviewed and passed fresh root/full-CI runs. Review approved and story marked done.
