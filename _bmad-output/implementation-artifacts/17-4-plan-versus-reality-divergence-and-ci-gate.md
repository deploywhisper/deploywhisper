# Story 17.4: Plan-Versus-Reality Divergence Detection and CI Gate

Status: backlog. **Highest standalone value in the epic; shippable without any UI.**
Preparation: refined
Release: v1.6.0 | Priority: P0 within the independent Epic 17 lane

## Story

As a reviewer or CI operator, I want to know when a plan was computed against stale reality before I approve it, so that I never approve a diff that is not the diff which will apply.

## Implementation gates

- Blocked until 17.3 lands plan-directed reflection, bounded collection and fail-safe degradation.
- Hard earlier dependencies: **17.3**. **No Epic 16 dependency.**
- This slice proves comparison, severity floor and gate semantics against **recorded divergence fixtures** covering out-of-band modification, deletion, recreation and tag-only change. UI presentation is owned by 17.8.
- This story is the first slice that delivers end-user value on its own. It must be shippable and demonstrable with the CLI alone.

## Acceptance Criteria

1. **AC1:** Given recorded plan prior state and live state, when comparison runs, then each touched resource is classified `match`, `diverged`, `unknown` or `unreadable`.
2. **AC2:** Given a diverged resource, when the report is produced, then a `plan_reality_divergence` finding carries per-attribute recorded, live and planned values linked to the snapshot digest and the specific resource.
3. **AC3:** Given a plan generated earlier than the configured threshold, when grounding runs, then plan freshness is computed and the stale plan is flagged.
4. **AC4:** Given divergence on a security-relevant or destructive attribute, when the recommendation is computed, then a severity floor applies and the recommendation is at least `caution`; no reason, acknowledgement or narrative can clear the floor.
5. **AC5:** Given `--fail-on-divergence`, when the CLI or API runs in CI, then the gate fails deterministically with a distinct documented exit code and requires no web UI.
6. **AC6:** Given an unreadable or unknown comparison, when results are rendered, then it is never reported as `match`.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-017 | Compare recorded plan prior state against observed live state and classify each touched resource as `match`, `diverged`, `unknown` or `unreadable`. | Comparison matrix over recorded divergence fixtures |
| LEG-FR-018 | Emit a `plan_reality_divergence` finding carrying per-attribute recorded, live and planned values, linked to the snapshot digest and the specific resource. | Finding shape and Evidence Law tests |
| LEG-FR-019 | Compute plan freshness and flag a plan generated earlier than the configured staleness threshold. | Plan-age fixture tests |
| LEG-FR-020 | Apply a severity floor for divergence on security-relevant or destructive attributes that no reason, acknowledgement or narrative can clear. | Floor-enforcement and override-attempt tests |
| LEG-FR-021 | Provide a deterministic `--fail-on-divergence` CI gate with a distinct documented exit code, usable without the web UI. | CLI gate tests and a documented exit-code contract |
| LEG-NFR-004 | Degradation must be fail-safe; unknown and unreadable are never presented as match. | Negative-path assertions |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-4-plan-reality-divergence`. Each packet owns the named paths.

- [ ] **Packet 4.1: Divergence fixture corpus — owner: test owner.**
  - Owned write paths: `tests/fixtures/` divergence corpus, `tests/test_analysis/`.
  - Output: synthetic recorded fixtures for out-of-band modification, deletion, recreation, tag-only change, unknown and unreadable.
  - Acceptance proof: fixture coverage underpinning AC1 and AC6.
- [ ] **Packet 4.2: Comparison engine — owner: analysis implementer.**
  - Owned write paths: `analysis/divergence.py`, `tests/test_analysis/`.
  - Output: four-way classification over recorded prior state versus live state, with attribute-level diffs.
  - Acceptance proof: AC1, AC6 — comparison matrix and negative-path assertions.
- [ ] **Packet 4.3: Finding emission and evidence linkage — owner: analysis implementer.**
  - Owned write paths: `analysis/divergence.py`, `evidence/` consumption only, `tests/test_analysis/`, `tests/test_evidence/`.
  - Output: `plan_reality_divergence` finding with recorded, live and planned attribute triples linked to the snapshot digest and the specific resource.
  - Acceptance proof: AC2 — finding shape and Evidence Law gate tests.
- [ ] **Packet 4.4: Plan freshness — owner: analysis implementer.**
  - Owned write paths: `analysis/divergence.py`, `services/` settings consumption, `tests/test_analysis/`.
  - Output: plan age computation against a configurable staleness threshold and a stale-plan flag.
  - Acceptance proof: AC3 — plan-age fixture tests.
- [ ] **Packet 4.5: Severity floor — owner: analysis implementer.**
  - Owned write paths: `analysis/risk_scorer.py` **additive floor application only**, `tests/test_analysis/`.
  - Output: an unclearable severity floor for security-relevant and destructive divergence, raising the recommendation to at least `caution`.
  - Acceptance proof: AC4 — floor-enforcement plus explicit override-attempt tests through reason, acknowledgement and narrative paths.
  - **Shared-file rule:** apply the floor additively; do not alter existing `ACTION_BASE_SEVERITY` or `CATEGORY_BASE_SEVERITY` semantics.
- [ ] **Packet 4.6: CI gate and exit-code contract — owner: CLI implementer and documenter.**
  - Owned write paths: `cli/`, `api/` additive fields, `tests/test_cli/`, `tests/test_api/`, `docs/live-environment-grounding/README.md`.
  - Output: `--fail-on-divergence` with a distinct documented exit code, deterministic in CI and usable with no web UI.
  - Acceptance proof: AC5 — gate tests and a published exit-code contract.

## Tasks note on value demonstration

Packets 4.2 through 4.6 are sufficient for a demonstrable release increment. Record a reproducible walkthrough: a recorded plan, an out-of-band change, and a CI gate failure with the exact exit code.

## Dev Notes

- Divergence is the capability no competing open-source pre-deployment tool provides as a first-class finding. Precision matters more than coverage; a false `diverged` erodes trust faster than a missed one.
- Narrative generation must never be able to soften a floored severity. Verify the floor holds through the LLM narrative path, not only in the scorer unit test.
- A tag-only change is an intentional fixture case. Decide and document whether it floors; do not leave the behaviour implicit.
- Unknown and unreadable are distinct from `match` and from each other. Collapsing them is a defect.
- Exit codes are a public contract once documented. Choose a code that does not collide with existing CLI exit codes, and record it in the operator guide in the same PR.
- Reuse the existing finding, evidence and confidence models. Do not bump the report schema version; the grounded block is additive and carries its own `live_context_version`.
- Respect Python 3.10-compatible code on a 3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. **No dependency installation is authorized by this story.**
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate capability; account-wide inventory; scheduled drift; cost estimation. Reports remain advisory with `should_block=False`; the CI gate is a caller-opted exit code, not a blocking report.
- Epic independence: no import from `infra_automation/` or `services/infra_automation_*`.

### Project Structure Notes

`analysis/divergence.py` is a new analysis module consuming grounding results from `services/cloud_context_service.py`. It must not construct connectors or issue calls directly.

### Testing requirements

- Before changing constructors or schema, search the entire repository for direct instantiations and fixtures; update all of them. `analysis/risk_scorer.py` is high-blast-radius.
- Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for the CLI gate and additive API fields.
- All fixtures are synthetic. Never commit real plans, real account identifiers, real ARNs or raw state.
- UI validation not applicable; divergence presentation is owned by 17.8.

### Completion and integration boundary

- Attach exact commands, results, versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice closes only divergence detection, plan freshness, the severity floor and the CI gate. It does not qualify a production AWS profile and does not deliver blast radius, recoverability or UI value.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Operator guide](../../docs/live-environment-grounding/README.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Planning preparation only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no implementation, qualification or runtime test performed.
- Commands and proofs above are future obligations, not results.

### File List
- `_bmad-output/implementation-artifacts/17-4-plan-versus-reality-divergence-and-ci-gate.md` (story specification only).
