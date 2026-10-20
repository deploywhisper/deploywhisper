# Story 17.0: Adopt and Qualify the Grounding Contract

Status: ready-for-dev
Preparation: refined
Release: v1.5.0 (shared release train with Epic 16) | Priority: P0 within the independent Epic 17 lane

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

- [ ] **Packet 0.1: Governance and scope adoption — owner: maintainer.**
  - Owned write paths: `docs/rfcs/0002-live-environment-grounding.md`, `_bmad-output/planning-artifacts/`.
  - Output: recorded RFC decision, CODEOWNERS coverage for `cloud/`, scope agreement with parent PRD and architecture §26.
  - Acceptance proof: AC1, AC2 — decision record and readiness gate statement.
- [ ] **Packet 0.2: Dependency decision — owner: maintainer.**
  - Owned write paths: `docs/decisions/` or the RFC decision record.
  - Output: explicit approval or rejection of an AWS SDK runtime dependency, with the chosen option among runtime dependency, optional extra or thin signed-request client, plus supply-chain and lockfile impact.
  - Acceptance proof: AC7 — recorded dependency decision with rationale.
- [ ] **Packet 0.3: Trust-boundary spikes — owner: security-focused implementer.**
  - Owned write paths: disposable spike directory, evidence packet under `docs/verification/live-environment-grounding/17-0/`.
  - Output: allow-list refusal prototype, credential-free dry-run, confused-deputy and SSRF configuration corpus, secret-absence check across logs and outputs.
  - Acceptance proof: AC3, AC4, AC8 — recorded spike results.
- [ ] **Packet 0.4: Plan prior-state extraction spike — owner: implementer.**
  - Owned write paths: disposable spike directory, evidence packet.
  - Output: prior-state extraction across Terraform and OpenTofu plan format versions, with defined fallback when absent.
  - Acceptance proof: AC5.
- [ ] **Packet 0.5: Latency, call count and cost measurement — owner: implementer.**
  - Owned write paths: disposable spike directory, evidence packet.
  - Output: measured results on named hardware for a realistic large plan; proposed defaults for deadline, concurrency and call budget.
  - Acceptance proof: AC6.
- [ ] **Packet 0.6: Coverage freeze and readiness report — owner: maintainer.**
  - Owned write paths: `_bmad-output/planning-artifacts/implementation-readiness-report-<date>-live-environment-grounding.md`.
  - Output: frozen resource-family coverage list, per-capability permission map, all RFC unresolved questions closed, blocking-gap list.
  - Acceptance proof: AC7 — readiness report with no blocking gap or an explicit NOT READY verdict.

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
Planning preparation only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no governance decision, spike, qualification or runtime test performed.
- Commands and proofs above are future obligations, not results.

### File List
- `_bmad-output/implementation-artifacts/17-0-adopt-and-qualify-the-grounding-contract.md` (story specification only).
