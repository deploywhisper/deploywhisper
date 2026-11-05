# Story 16.14 formal BMad code review

Date: 2026-11-04. Original outcome: **Changes requested**.

Current repair disposition: **R1–R4 resolved and independently verified**; root1766 tests and complete localCI3212 tests pass. See [repairs and fresh evidence](review-fixes.md). Original findings below remain as review history.

Reviewed the 53-file, 6032-line working diff against `4ff2c2dd68ba11bd8d4263857f58d6882c24c16a` on `feature/16-14-opentofu-terraform-collection-provenance`. Blind Hunter, Edge Case Hunter and Acceptance Auditor ran independently with the prescribed context separation. All three completed. The leader reproduced and triaged findings. This is a fresh review of the settled implementation; the earlier development review remains historical.

Triage: **three P1 and one P2 patch findings**, no decision-needed or deferred findings. The shorter-custody-TTL hypothesis was dismissed: the installed handler uses equal custody/source deadlines and the supported profile is explicit.

## R1 — P1: Known infrastructure credentials leak through JSON object keys

Location: `infra_automation/runner/collection_output.py:104–105`. Violates AC4 and IAU15-FR-024/NFR-003.

The host checks serialized text and then `redact_value(document, sensitive_values=...)`. The shared redactor does not apply supplied sensitive values to ordinary dictionary keys outside metadata. A known credential containing a quote, backslash or newline is escaped in the serialized text, so both checks miss it when the credential appears as a JSON key.

Reproduced with ordinary `json.dumps`, a synthetic known credential containing a quote, and `planned_values.outputs.value.value={credential: "innocent"}` with `sensitive=False`. `parse_collection_output` accepted it and the decoded screened JSON still contained the exact known credential key. No malicious JSON parser or unusual encoding is necessary.

Repair: screen decoded keys as well as decoded scalar values using the per-execution credential corpus before custody/output publication. Add quote/backslash/newline and Unicode key regressions. Preserve bounded traversal and fixed errors.

## R2 — P1: Authenticated task bearer can be persisted in a collected artifact

Location: `infra_automation/runner/claims.py:356–362`; `_secret_free` at lines192–201. Violates AC4 and the authenticated credential persistence boundary.

The server checks the outer serialized upload and each artifact's serialized JSON text for its known task/runner credentials. Artifact parsing does not apply those per-request credential values to the decoded JSON. Encoding the current task bearer as JSON Unicode escapes in a benign value therefore bypasses all checks.

Executable reproduction used `CollectionIntakeTests`' disposable authenticated runner/task fixture, the actual issued task token, a valid envelope and recomputed digests. Claim, upload and completion went through production service operations. Result: `succeeded`; reading the immutable manifest and decoding the artifact recovered the exact task bearer. Only this boolean result was printed; no token was logged. The fact that an authorized runner submits the value does not authorize retaining its bearer in artifacts/reports.

Repair: apply known task/runner/enrollment credential checks to decoded artifact keys and values in the same authenticated transaction before staging/persistence. Add escaped bearer persistence tests that assert no staged bytes, manifest or report survives rejection.

## R3 — P1: Saved-plan receiver rejects canonical production handoff payloads

Location: `infra_automation/receiver_runtime.py:322–328`; producer `infra_automation/targets.py:280`; digest guard `services/infra_automation_decisions.py:333–341`. Violates AC2/AC6 integration.

The new `saved_plan_receipt` mode requires top-level `receiver_action="saved_plan_receipt"`. Production `semantic_payload()` emits only `version`, `kind`, `decision` and `destination`. Adding the selector afterward changes the approved digest and fails DecisionService's canonical payload check. Thus a correctly configured production target cannot use the new receipt mode, even when the decision material ports are available.

The auditor reproduced this with valid exact-plan provenance and protected custody, generated the real `semantic_payload`, recomputed its legitimate binding, and invoked the real receiver. It raised `ReceiverConflict: Approved payload must select saved-plan receipt`; grant consume calls remained zero. The qualification script supplies a custom selector payload and manufactured binding instead, so its passing receipt check cannot detect this incompatibility.

Repair: integrate the explicit receipt selector into the canonical approved target/payload contract, or select the mode through an existing appropriate canonical field. Preserve exact digest binding. Add a regression from production semantic payload through receiver admission, with no apply or deployment action.

## R4 — P2: Failure completion waits behind a timed-out heartbeat

Location: `infra_automation/runner/collection_client.py:81–92,132–134`. Violates AC5's bounded cancellation/timeout behavior.

`send()` holds a normal lock throughout the transport call. ExecutionRunner's bounded callback supervisor can abandon a still-running heartbeat thread and return a failed result. CollectionHandler then calls `send("complete", state="failed")`, which waits on that same lock without a deadline. A stalled transport therefore prevents the handler from returning after the execution bound. The production transport has per-socket-operation timeouts, not an absolute operation deadline; repeated response progress can prolong the wait further.

Controlled reproduction exercised the production handler with a heartbeat held behind an event and the executor returning a failed result while that callback remained active. The handler stayed blocked after execution returned and completed only when the heartbeat transport was released. This is a bounded fault-model reproduction, not a claim of a reproduced live HTTPS stall.

Repair: bound lock/transport lifetime using the original task deadline and avoid issuing a new completion operation while a prior heartbeat remains ambiguous. Return a safe failure requiring fenced recovery, with no replacement sequence or authority. Add a blocked-heartbeat/cancellation regression.

## Verification and disposition

Fresh focused command:

```sh
./.venv/bin/python -m pytest tests/test_infra_automation/test_collection_client.py tests/test_infra_automation/test_collection_custody.py tests/test_infra_automation/test_collection_intake.py tests/test_infra_automation/test_collection_receiver.py tests/test_infra_automation/test_collection_qualification.py tests/test_infra_automation/test_collector_runtime.py tests/test_infra_automation/test_runner_isolation_qualification.py -q --tb=short
```

**51 tests, 117 subtests passed**, 4.82s. Those tests do not cover the four counterexamples. Existing qualification still establishes its recorded cases; it does not override these findings. Terraform/cloud restrictions and use of a local server adapter were not treated as defects by themselves.

Only review documentation and tracking changed. No runtime fixes, commit, push, PR, infrastructure action or new dependency occurred. Story and sprint status return to `in-progress`; R1–R4 must be repaired, reviewed and qualified before review/done advancement. BMad Help routes next to `bmad-dev-story` for these review follow-ups.
