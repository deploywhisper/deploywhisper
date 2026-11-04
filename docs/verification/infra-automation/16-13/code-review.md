# Story 16.13 — BMad code review

Date: 2026-11-04. Initial outcome: **Changes requested**.

Current repair disposition: **R1–R5 resolved and verified; story ready for re-review**. See [repairs and fresh test evidence](review-fixes.md). The original findings and counterexamples below are retained as review history.

## Scope and method

Reviewed all 30 uncommitted story files against HEAD on `feature/16-13-isolated-runner-execution-profile`. Full diff: 7,834 lines, 7,556 additions / 30 removals; excluding the detailed qualification result leaves 5,698 diff lines. All three independent layers completed: Blind Hunter (diff only), Edge Case Hunter (diff/project) and Acceptance Auditor (diff/story/context/qualification record). No review layer failed.

Triage: **one P1 and four P2 patch findings; zero decision-needed, zero deferred**. No runtime code was changed. Prior passing development review and qualification establish their recorded cases, not coverage of the new cases below.

## R1 — P1: Bootstrap restarts the execution budget after setup

**Resolved:** Original absolute deadline and remaining budget now cross the private bootstrap boundary; actual delayed-setup/controller-death qualification stops at 6.092s against 6s plus 0.75s observation tolerance.

Location: `infra_automation/runner/execution.py:310–359` and `infra_automation/runner/bootstrap.py:263–286`. Violates AC5's original execution-time bound and the documented independent watchdog guarantee.

The host establishes its deadline before container creation, but sends the original `profile.timeout_seconds` rather than the remaining/original execution deadline. The bootstrap starts a new full duration when it starts. If creation/setup consumes time and the host controller then dies, the container runs past the original deadline; the separate lease only caps this if it is earlier.

**Actual Linux reproduction:** exact pinned image, timeout 6s / lease 60s, three-second delay in the host create adapter. The controller was SIGKILLed after observing descendants at t+3.86s. The container was still running at t+6.31s, beyond the original deadline, and exited124 only at t+9.50s. Production recovery succeeded and no container remained. See [recorded timings](review-deadline-repro.json). This was not a mocked container result.

**Repair:** carry and enforce the same original execution deadline across host and bootstrap, bounded by the original lease; do not reset elapsed setup/delivery time. Add delayed-setup/controller-death qualification and rebuild/requalify the bootstrap image.

## R2 — P2: OpenTofu-specific files bypass source module admission

**Resolved:** All four configuration formats share module validation and byte bounds; actual negative admission and positive vendored OpenTofu cases pass.

Location: `infra_automation/runner/source.py:415`, `:491–499`. Violates AC1/AC3 and the documented contained vendored-module restriction.

Both parser selection paths inspect only `.tf` and `.tf.json`. The pinned OpenTofu 1.13.1 also evaluates `.tofu` and `.tofu.json`, which consequently bypass module validation and the per-configuration byte bound.

**Actual Linux reproduction:** a protected immutable source contained `main.tofu` with `module "outside" { source = "/opt/deploywhisper/source" }`. Production materialization and `ExecutionRunner` accepted it, resolved the collector credential once, executed the external module/provider and returned `succeeded`, `finalizable=True`, with cleanup complete. The module was outside the admitted source root. Equivalent `.tf` input was rejected. This demonstrates an admission/pinning bypass, not a claimed host escape.

**Repair:** validate every configuration syntax recognized by the pinned tool, or explicitly reject unsupported extensions before credential resolution. Cover `.tofu` and `.tofu.json`, escaping/remote module references and configuration-size limits, then rerun real qualification.

## R3 — P2: Snapshot permissions can disclose a private repository

**Resolved:** Private 0700 staging/envelope and held directory identities prevent host-public publication and redirecting creation or cleanup.

Location: `infra_automation/runner/source.py:540`, `:674–680`, and `infra_automation/runner/catalog.py:98`. Violates the private operator-source boundary in AC3/AC4.

Destination validation accepts an owner-controlled 0755 directory because it rejects writable-by-group/other modes but does not require privacy. Materialization then makes the snapshot directories 0555 and files 0444. A valid caller can therefore copy a private 0700 repository into publicly traversable/readable staging, exposing all copied contents to other host users until cleanup.

**Local reproduction:** production materialization accepted a 0755 staging directory under canonical `/private/tmp`. The original repository was 0700; resulting snapshot was 0555 and files 0444. All snapshot ancestors had other-execute permission and the copied files had other-read permission. The qualification fixture's 0700 parent masks this case. Only synthetic source was used and cleanup completed.

**Repair:** enforce a private destination parent (or equivalent complete traversal protection) before broadening snapshot permissions. Add regression coverage for public/group-readable staging and replacement races while preserving non-root container readability.

## R4 — P2: Ambiguous creation is declared cleaned up too early

**Resolved:** Unacknowledged creates remain durably pending through empty/foreign lookups; immutable acknowledged IDs support safe removal/recovery. Late-create fault-model and actual cleanup-race regressions pass.

Location: `infra_automation/runner/sandbox.py:236–251` and `infra_automation/runner/execution.py` cleanup's `not pending_creation` branch. Violates AC5's honest bounded cleanup/recovery requirement.

After a create error/timeout, failed inspection followed by one empty listing discards `_attempted`. The execution journal can then be finalized with `cleanup_complete=True`. A client timeout does not establish that an accepted daemon operation can no longer finish; if create becomes visible later, the owned container is omitted from pending recovery.

**Evidence level:** a controlled transport reproduction exercised the real create/ownership logic with `create -> IsolationError`, `inspect -> IsolationError`, `ps -> empty`; the reservation was cleared and the caller considered cleanup complete. The specific late-commit Docker-daemon timing was **not** reproduced. The finding concerns the unsupported assumption that a point-in-time empty listing resolves an outstanding ambiguous mutation.

**Repair:** distinguish definitive rejection from ambiguous accepted/in-flight creation and retain the nonce/task reservation until safely reconciled. Test a delayed daemon completion after the initial empty lookup; preserve the existing protections against deleting a foreign name collision.

## R5 — P2: An advertised catalog command always fails

**Resolved:** Unsupported standalone provider_probe removed. The internal provider helper remains, and both advertised commands pass actual launcher qualification.

Location: `infra_automation/runner/catalog.py:184–185`, `infra_automation/runner/bootstrap.py:221–224`, and `tests/fixtures/infra_automation/qualification/16_13/provider_probe.py:98`. Violates the fixed usable catalog behavior in AC3.

`provider_probe` is accepted as a standalone command. Its script unconditionally calls `json.load(sys.stdin)`, while `managed_command` always supplies DEVNULL to task stdin. Every direct invocation therefore fails with EOF/JSONDecodeError before returning evidence. The successful real-provider qualification uses `qualification_probe(mode="plan")`, so it does not cover this advertised entry.

**Reproduction:** the unchanged provider script launched with DEVNULL returned exit 1, empty stdout and JSONDecodeError. No credentials were involved.

**Repair:** remove the unsupported standalone entry or give it the fixed input contract it requires without accepting arbitrary server stdin. Test every advertised catalog command end to end and update qualification/documentation consistently.

## Verification and disposition

Fresh focused source/catalog/sandbox/execution/boundary/evidence suite: **43 passed, 83 subtests**, 14.57s. Evidence-drift subset: three tests / 15 subtests. Repo-wide Ruff check and format check (532 files), plus `git diff --check`, passed. These existing tests omit the reproduced findings.

The real `.tofu` admission and delayed-setup watchdog reproductions used only private synthetic fixtures and the pinned image, with owned-container cleanup verified. No production credentials or unrelated containers were used. Read-only review did not alter runtime source or the historical 130-assertion record.

The offline profile limitation and future 16.14 collector/custody obligations are correctly disclosed and were not treated as missing 16.13 implementation. Source changes for these repairs require fresh qualification and corresponding drift evidence.

The original review recorded five unchecked patch actions and in-progress status. The repair follow-up has now resolved and checked all five, with fresh validation and review status. No commit or push was performed by the repair task. The current feature branch is Git Flow compliant. BMad help routes the next step to development fixes, then code review again. **Implementation repairs are complete; formal re-review and Git Flow publication remain separate next steps.**
