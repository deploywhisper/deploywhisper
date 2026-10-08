# Story 16.14: OpenTofu/Terraform Collection and Provenance

Status: backlog
Preparation: refined
Release: v1.5.0 | Priority: P0, highest-priority feature

## Story

As a reviewer, I want screened plan evidence bound to the exact protected local saved plan, so that the qualified receiver verifies approved bytes without exposing secrets.

## Implementation gates

- Earlier dependencies: 16.6 authenticated intake/shared analysis, 16.11 qualified receiver and exact-byte admission, 16.13 isolated execution; 12.5 before runner distribution.
- Blocked until Story 16.0 public RFC acceptance and executable identity/fencing/isolation/custody/receiver qualification close the readiness gates; documentation refinement does not satisfy those gates.
- Recheck actual prerequisite records before execution. Downstream release acceptance is not a prerequisite for an earlier owned slice; test-double proofs remain explicitly limited.
- Promote to ready-for-dev only after dependency evidence, final interfaces and packet estimates are independently reviewed. Keep unchecked tasks and backlog until then.

## Acceptance Criteria

1. **Given an admitted immutable repository commit and qualified pinned OpenTofu/Terraform profile, when fixed argv collects plan and JSON, then exit 0 records no-change, exit 2 records change, and other exits record failure; only screened JSON reaches DeployWhisper and the report uses the shared analysis core.**
2. **Given a saved binary plan, when custody finalizes it, then an opaque handle names immutable owner-restricted local bytes with raw digest/expiry, separate from the screened JSON digest; the receiver verifies the actual protected file handle against the approved digest before action.**
3. **Given a symlink, overwritten plan, changed source SHA, expired custody, stale attempt/fence or tampered transport digest, when ingestion or receiver admission runs, then it rejects without minting replacement authority; replanning needs new evidence and approval.**
4. **Given credentials, state, binary plans, inline secrets or sensitive streamed chunks, when collection screens output/errors/metadata/logs, then the versioned corpus has zero known-secret leaks in persisted/transmitted surfaces; mandatory failed/partial/stale collection prevents eligibility and reports limitations.**
5. **Given timeout, cancellation, disk-full, output cap, partial upload or disallowed egress, when collection stops, then owned descendants terminate, unfinished upload staging cleans up atomically and no partial output becomes approval eligible.**
6. **Given the supported real-tool matrix, when the isolated runner-to-analysis-to-receiver acceptance runs, then both actual tool compatibility and hostile/sensitive fixtures pass; dummy fixtures alone never qualify exact-plan support.**

### Requirement Traceability

Coverage intent: Delta against released v1.4.0; full canonical mappings below are acceptance obligations, not delivered proof.

| Requirement | Full canonical requirement | Required proof |
| --- | --- | --- |
| IAU15-FR-024 | Screen inputs, metadata, streamed logs, errors and artifacts before persistence or analysis; reject state/credential/key/binary-plan uploads and inline secret-looking values. | Secret corpus including chunk boundaries and blocked-file tests |
| IAU15-FR-025 | Record authenticated collection provenance with runner/task attempt, command/argv digest, source SHA, exit code, time, raw-local digest, sanitized digest and redaction version; recompute received digests. | Tampered digest, stale attempt and redaction-provenance tests |
| IAU15-FR-026 | Invoke the existing shared analysis core without duplicating risk logic; provenance alone cannot turn inferred output into deterministic evidence. | Cross-surface report parity and Evidence Law fixtures |
| IAU15-FR-028 | Expose missing/partial/stale collection as confidence limitations and context TODOs; failed or incomplete mandatory collection cannot make approval eligible. | Partial/error/stale collection eligibility tests |
| IAU15-FR-041 | Authorize exact-plan handoff only when the qualified self-hosted receiver can verify the original immutable saved-plan bytes in protected local custody by opaque handle, raw digest and expiry; no server/public-artifact plan storage, and replanning requires fresh evidence/approval. Upload-only advisory receipts never authorize apply or require invented repository provenance. | Real custody access/restart/overwrite/symlink/expiry/replan spike and receiver tests |
| IAU15-FR-049 | Qualify OpenTofu/Terraform plan and JSON extraction for declared pinned versions, distinguishing exit 0/no-change, 2/change and error; retain the sensitive binary plan locally and transport screened JSON only. | Real-tool compatibility smoke and hostile/sensitive plan fixtures |
| IAU15-FR-050 | Resolve infrastructure credentials only in the operator-owned runner/receiver execution identities under an environment allow-list and least privilege; never send or persist their values in DeployWhisper. | Credential inheritance/transport/persistence corpus and separated-identity spike |
| IAU15-FR-051 | Enforce task CPU/time/disk/output/egress caps and atomic bounded uploads with cleanup after failure; cancellation must terminate the entire owned process tree. | Limit, partial-upload, disk-full, egress and descendant-process tests |
| IAU15-NFR-003 | The versioned sensitive-data corpus must yield zero known secret patterns in stored artifacts/logs/metadata/errors/audit or transmitted narrative summaries; no universal-redaction claim follows. | Stored/output corpus scans including chunk boundaries |
| IAU15-NFR-004 | Automation-originated fixture reports must produce zero Evidence Law violations and preserve deterministic/inferred labels and advisory report semantics. | Evidence Law and cross-surface contract CI results |

## Tasks / Subtasks

Execute one bounded packet at a time on the story feature branch. Each packet owns the named paths; coordinate shared paths and do not revert other edits. Re-estimate after 16.0 spikes; split packets into reviewable PRs without renumbering the canonical story.

- [ ] Packet 14.1: Collector argv and tool qualification — owner: Runner implementer.
  - Owned write paths: `infra_automation/runner/ collector catalog and tests/test_infra_automation/ real-tool smoke`.
  - Output: pinned operator-installed tool manifests; fixed argv; exit-code classification.
  - Acceptance proof: AC1,6: real no-change/change/error smoke, option injection and source-admission tests.
- [ ] Packet 14.2: Custody integration — owner: Runner/receiver implementer.
  - Owned write paths: `infra_automation/runner/ local custody and examples/infra-automation/ receiver contract tests`.
  - Output: atomic finalize, no-follow descriptor reads, opaque handle/digest/TTL with separated identities.
  - Acceptance proof: AC2,3,6: real restart/access/overwrite/symlink/expiry/replan tests using 16.11 receiver.
- [ ] Packet 14.3: Screened provenance intake — owner: Service implementer.
  - Owned write paths: `services/infra_automation_service.py; infra_automation/ typed provenance; tests/test_services/ and tests/test_infra_automation/`.
  - Output: authenticated runner/task/attempt, argv digest, commit SHA, exit/time/redaction metadata; server transport digest recomputation.
  - Acceptance proof: AC1,3,4: stale/tampered input denial, corpus scans and report parity.
- [ ] Packet 14.4: Limits and operator guide — owner: Runner implementer/documenter.
  - Owned write paths: `infra_automation/runner/; docs/infra-automation/collection.md; tests/test_infra_automation/`.
  - Output: bounded upload cleanup/cancellation and named compatibility/licensing/custody limits.
  - Acceptance proof: AC4–6: disk-full/egress/tree-kill proof plus repeatable real collection guide.

## Dev Notes

- Reuse: Reuse services/intake_service.py:is_sensitive_file, total_upload_bytes, build_parse_batch and trusted_relative_artifact_path; parsers/terraform_parser.py:parse_terraform; services/analysis_service.py:analyze_uploaded_files. Existing sensitive-file checks need the automation binary-plan/state/screening contract, not a parallel scoring engine.
- Owned entities: Extend 16.6 artifact manifests/provenance and 16.12 task records only where required; local custody index belongs to runner/receiver, not a server plan-blob table.
- Respect Python 3.10-compatible code/3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. No dependency installation is authorized by this story. Inspect migration head before allocating changes.
- No apply/destroy/remediation, arbitrary shell/plugins, automatic approval, new AI Composer, Ansible/Kubernetes/Helm collectors, Git sync, PostgreSQL/HA or broad infrastructure engine. Existing reports remain advisory with `should_block=False`.
- OpenTofu/Terraform licenses remain independent; operator supplies pinned tools. Do not bundle proprietary binaries or claim MIT relicensing. Never commit/transport real state, credentials or saved binary plans; test files are synthetic and protected local real-tool custody is disposable.
- Prior-story intelligence: preceding Epic 16 capabilities are planned dependencies, not claimed implemented. Read their actual Dev Agent Records and contracts before coding. Recent release commits emphasize independently verified artifact identity, signing and separate security regression checks; reuse that evidence discipline.

### Testing requirements

- Before changing constructors/schema, search the entire repository for direct instantiations/fixtures; update affected contracts and run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` plus the automation shard registered in CI.
- Register `tests/test_infra_automation/` explicitly in `scripts/ci-local.sh` and affected GitHub shards; root discovery skips some directories. Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`. Keep deterministic fixtures separate from real tool/receiver acceptance.
- UI validation not applicable to the collector-only owned slice; if implementation changes a rendered surface, add the full composed-app Playwright/axe/keyboard task before review.

### Completion and integration boundary

- Attach exact command/results, source/build/tool versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before review/done advancement.
- A slice may close only its owned contract; future integration or production support claims wait for their explicit real-profile gates. Any missing mandatory proof keeps the relevant status blocked/backlog or in progress. Public GitHub writes, real credential setup and release publication require authority for those actions unless already explicitly authorized in the session; do not request the same authority again.

### References

- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md)
- [Requirement text and proof map](../planning-artifacts/infra-automation-requirement-dispositions.json)
- [Epic 16 story](../planning-artifacts/epics.md)
- [Architecture Section 25](../planning-artifacts/architecture.md)
- [Feature UX contract](../../docs/design/infra-automation-ux.md)
- [Readiness report](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Planning refinement only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no feature implementation, qualification, public RFC acceptance, release publication or runtime tests performed.
- Implementation and validation commands above are future obligations, not test results.

### File List
- `_bmad-output/implementation-artifacts/16-14-opentofu-terraform-collection-and-provenance.md` (story specification only).
