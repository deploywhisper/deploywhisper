# Story 16.0 qualification evidence

Scope: governance and disposable synthetic qualification. The maintainer accepted RFC 0001, real Linux/tool/custody qualification passed, and version 1 contracts are frozen. Story16.0 is done; final repository checks and closure are recorded in [manifest.json](manifest.json).

## Evidence by packet

- [Maintainer decision](maintainer-decision-2026-10-09.md) and [governance record](governance.json): direct approval, actual PR154 chronology and explicit RFC-specific early-window exception. No second human review or GitHub approval event is fabricated.
- [Threat model and accepted ADRs](threat-model.md), [scope review corpus](scope-corpus.json): bounded Tier 0/1, trust limits and rejected modes. The scope corpus is a review inventory; executed negative vectors live in the qualification tests.
- [WP2 identity](wp2-identity.md): 18 methods, 2,000 permission outcomes and measured cryptographic/resource bounds.
- [WP3 SQLite](wp3-sqlite.md): 11 methods covering independent claims, fencing, epochs and abrupt restart.
- [WP4 real containment](wp4-containment.md): pinned OpenTofu1.13.1/external2.3.5 on non-root Linux ARM64, real hostile-source/resource/network/process probes.
- [WP5 synthetic receiver](wp5-receiver.md) and [actual saved-plan custody](wp5-real-custody.md): 12 fault methods plus real encrypted custody/separated identities/restart/tamper/replan evidence. The real Linux command shared by WP4/WP5 passed 3 methods and 6 subtests.
- [WP6 frozen contracts](wp6-contract-assessment.md), [normative v1 reference](../../../infra-automation/contract-v1.md), [content manifest](../../../../schemas/infra-automation/frozen-v1.json): 15 methods/185 subtests, 25 valid/28 invalid vectors, actual consumer probes and reviewed future compositions.
- [Technical review](technical-review.md), [WP7 readiness and sizing](wp7-readiness.md), [final readiness report](../../../../_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-10-infra-automation-v1.5.0.md): independent reruns, resolved findings, owners, estimates and dependency-qualified handoff.

## Reproduction

```sh
./.venv/bin/python -m pytest tests/test_infra/test_infra_automation_contract_qualification.py -q
DW16_REAL_LINUX=1 ./.venv/bin/python -m pytest tests/test_infra/test_infra_automation_real_linux_qualification.py -q
./.venv/bin/python -m unittest discover -q
./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short
bash scripts/ci-local.sh
./.venv/bin/ruff format --check .
```

The real run requires the exact local image/profile recorded in WP4. Ordinary CI opts out of Docker qualification; the separately executed real suite must pass before this evidence is accepted. Rebuilding to a new image identity requires review and requalification, not a silent fallback.

Keep generated accounts/tokens, databases, raw logs, binary plans/state and keys in private disposable stores. Commit only harmless sources/harnesses and screened summaries. Run-owned containers/volumes/network are cleaned; the qualified local image is retained for reproduction.

## Acceptance limits and handoff

This work qualifies the design and contracts, not production automation handlers or a v1.5.0 release. Anchored tmpfs proves process/receiver-container restart, not host power-loss persistence. Host/daemon/DB administrators and receiver-identity compromise remain trust limits. Capacity, universal redaction, production key/retention/network integration, composed browser proof and signed release/pilot remain assigned to later stories.

After final checks, only prepared dependency-satisfied foundations 16.1 and16.3 may advance. Other stories retain their dependencies;12.5 stays a separate release enabler. UI validation not applicable: no rendered surface changed. The raw React client probe is not browser/pixel proof.
