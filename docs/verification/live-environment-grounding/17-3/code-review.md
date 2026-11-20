# Story 17.3 code review

**2026-11-19 · Changes requested.** Blind Hunter, Edge Case Hunter, and Acceptance Auditor reviewed `64ef0fa...2606d68` on `feature/17-3-plan-directed-reflection`. Review action items return the story to `in-progress` before merge. The review used static inspection and offline tests.

## Findings

| Priority | Finding | Evidence and acceptance criterion |
| --- | --- | --- |
| P1 | Ordinary `no-op` entries authorize unrelated AWS reads. | `cloud/reflection.py:349` accepts them as reflected rows, and `cloud/reflection.py:518` emits their direct and reverse calls. Terraform includes ordinary unchanged resources in `resource_changes`. Those rows can also consume budget before changed resources. Filter ordinary no-ops before manifest generation and exercise the real collector boundary in the anti-enumeration regression. AC1, AC3, AC4 and LEG-FR-015. [Terraform plan JSON format](https://developer.hashicorp.com/terraform/internals/json-format#plan-representation) |
| P1 | Plan-known private values are lost before provider projection and retention. | `cloud/reflection.py:294` uses the plan's private-value set for identity screening, but `cloud/aws/projection.py:94` derives a new set from a single response and `services/cloud_context_service.py:747` does not supply the plan set to the snapshot redactor. A known private value in otherwise ordinary selected metadata can survive. Keep the plan set ephemeral through screening. Apply the same screening after decoding selected SQS redrive metadata and validate its leaf types before emission (`cloud/aws/projection.py:211`). LEG-FR-004. |
| P1 | Collection can finish beyond its deadline, and cancellation during finalization can go unreported. | `services/cloud_context_service.py:638` passes an absolute deadline to the reader, while local factory work, preparation, retention and unit-of-work completion remain synchronous. Tests explicitly accept 20 seconds under a 15-second deadline (`tests/test_services/test_cloud_plan_collection.py:121`, `:151`). The wrapper updates elapsed time alone, leaving the cancellation flag sampled by the collector before retention (`cloud/collection.py:256`). Bound the service operation and finalize cancellation at its return boundary. AC5, AC6 and LEG-NFR-003. |
| P2 | Regional batches can bypass the concurrency cap and backoff, and call accounting precedes dispatch. | `cloud/collection.py:138` starts a fresh reader per region. After a reader times out, its worker can still hold a process-wide slot (`cloud/aws/client.py:437`, `:517`). The next region can use another slot even with collection concurrency set to one, and its backoff starts over (`cloud/aws/client.py:452`). The worker increments the actual-call counter before copying operation parameters (`cloud/aws/client.py:389`), leaving a gap where cancellation can race with dispatch. Apply limits across the collection and prepare parameters before the final dispatch check. AC6 and LEG-FR-012. |
| P2 | Deposed Terraform objects can reject the plan or resolve to the current object. | `cloud/reflection.py:336` rejects duplicate addresses even when a distinct deposed object key disambiguates them. A solitary deposed delete can also take the current object's values at `:358`. Use deposed-object identity independently and preserve collection for unaffected siblings if the retained schema cannot represent both. AC1 and LEG-FR-013. [Terraform plan JSON format](https://developer.hashicorp.com/terraform/internals/json-format#plan-representation) |
| P2 | Unsupported rows can prevent collection of supported siblings. | `cloud/reflection.py:173` applies AWS ARN and region validation before `cloud/reflection.py:534` classifies unsupported families. Valid unsupported resources with accountless or foreign-provider ARNs can abort extraction. The collector also classifies missing or unsupported identities as `unreadable` even when there was no identity to query (`cloud/collection.py:210`). Retain address and type for these unknown observations. AC1 and AC5. |
| P2 | Region and identity resolution miss information already in valid AWS plans. | `cloud/reflection.py:188` chooses the region before parsing Lambda event mappings' function ARN (`:234`) and only provides a global-service fallback for IAM (`:193`), so these mappings and Route 53 records can be skipped for multi-region targets. SQS URL construction at `:218` uses the recorded queue name without reconciling a supplied queue ARN, allowing the selected facts and retained identity to describe different queues. Validate the full identity before dispatch. AC1 and LEG-FR-013. |
| P2 | Identity extraction omits recorded tags. | `cloud/reflection.py:250` drops tags when building `ResourceIdentity` and `:471` rejects tagged identities. Carry safely screened recorded tags as metadata while keeping the approved selectors authoritative. AC1 and LEG-FR-013. |
| P2 | Valid tag maps can fail projection because of a literal tag key. | `cloud/aws/projection.py:70` recognizes a string map and then recurses through it, interpreting literal keys such as `tags` or `tagset` as structural containers. Their string values then reject the otherwise valid response. Stop structural traversal at recognized tag maps and rows. AC5. |
| P2 | Multiple confirmed IAM denials collapse to one permission. | `cloud/collection.py:203` collects every denied action, but `:227` emits only the lexicographically first. The test accepts either singleton when both EC2 actions are denied (`tests/test_cloud/test_collection.py:163`). Preserve all capability-specific denials in additive diagnostics while retaining snapshot-v1 compatibility. AC5 and LEG-FR-006. |
| P3 | Runtime qualification evidence is difficult to reproduce from the checked-in packet. | `docs/verification/live-environment-grounding/17-3/README.md:36` cites temporary logs and omits the exact offline runtime harness invocation. The story's completion notes also describe the evidence both as completed and as future work. Reconcile the record and retain the reproduction command and results for the reviewed revision. |

## Scope decisions

- The frozen Route 53 catalog explicitly allows a single page and treats additional routing variants as incomplete. The review did not require pagination or a change to the approved request template.
- Story 17.3 covers budget serialization with trusted fixture outcomes. Production composition should bind those outcomes to the applicable plan and configuration when Story 17.9 installs the public paths. Live AWS and UI qualification remain in their owning stories.

## Review verification

- Focused pytest coverage for `tests/test_cloud` and the changed analysis, service, API and CLI test files passed with 146 tests and 333 subtests.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` passed with 838 tests, 1 skip and 2,474 subtests. The run set `LLM_API_BASE=http://127.0.0.1:1` to keep fallback local.
- `./.venv/bin/python -m unittest discover -q` passed with 2,314 tests run and 3 skips. `bash scripts/ci-local.sh` passed all 12 shards with 3,839 tests run and 3 skips, plus 172 isolation tests, skill scenarios and prompt-injection checks. Both runs used the same local fallback on Python 3.14.3.
- `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .` and `git diff --check` passed. Bandit reported no findings in the reviewed Python files.

## Closeout review on 2026-11-20

**Changes requested.** Blind Hunter, Edge Case Hunter, and Acceptance Auditor reviewed the local follow-up against `2606d68`. The focused re-run passed 166 tests and 339 subtests. Repo-wide Ruff lint and formatting and `git diff --check` passed. The working branch is based on `origin/develop` at `64ef0fa`.

| Priority | Finding | Evidence and required disposition |
| --- | --- | --- |
| P1 | Worker fact screening misses provider tag lists and some numeric equivalents. | The tag traversal at `cloud/aws/projection.py:75` recognizes `Tags` and `TagSet` but skips RDS `TagList`. Private values identified only by those tags can remain in other selected metadata. Worker scalar screening at `:266` also lacks the numeric equivalence checks used in snapshot redaction. Apply the screening before emitting facts. [RDS DB instance response](https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/API_DBInstance.html) · [RDS DB cluster response](https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/API_DBCluster.html) |
| P1 | IAM denial diagnostics bypass snapshot address screening. | `cloud/collection.py:218` copies the reflected address into the diagnostic and `:261` screens the snapshot separately. `services/cloud_context_service.py:909` applies account masking alone. A numeric private value screened from the snapshot address can survive in the direct collector result. Bind each diagnostic to the screened observation address and preserve that binding through service validation. |
| P2 | SDK calls can be counted before invocation and can begin after cancellation wins. | `cloud/aws/client.py:435` increments issued accounting under the progress lock, then `:440` invokes the SDK after that lock is released. A pause between them lets cancellation freeze and return the counter before that invocation starts. Align provider dispatch admission and accounting with the provider request boundary. |

The historical independent security approval applies to its recorded source hashes. The follow-up has three open items and needs a new independent disposition before merge. Git-flow closeout remains blocked.

### Fix verification

The three closeout items have implementation fixes and offline regression coverage. See the [verification packet](README.md#closeout-fix-verification) for the SDK boundary test, screening and retained-diagnostic proofs, and full regression results. Story 17.3 is back in review for independent closeout.

### Final independent disposition

**Approved on 2026-11-20.** Blind Hunter, Edge Case Hunter, and Acceptance Auditor found no remaining blocker after the three closeout fixes. Worker projection screens RDS tag lists and numeric equivalents. IAM denial diagnostics follow the validated screened identities through retained readback. Native SDK operation admission and transport both fence cancellation, including cancellation during signing.

Fresh verification passed 173 focused tests and 347 subtests, 17 pinned native SDK tests in network-disabled Python 3.11.17, and repo-wide Ruff lint, Ruff formatting and diff checks. The previously recorded full CI run passed across all 12 shards. The offline approval applies to the runtime identities below. Live AWS qualification belongs to Story 17.9.

| Runtime file | SHA-256 |
| --- | --- |
| `cloud/aws/client.py` | `c8242155d729e7ed0bb63af0880afa26816de3920f3bb254701aacb7ba21c0a0` |
| `cloud/aws/projection.py` | `a114caea8c5e5ed15104a4be0dae734a975ea567f222263bb1f0b5feb9b88d2f` |
| `cloud/aws/session.py` | `ca4af0009fe574cbaf2fd3a0a3579d654b9e0aa39bca34bc4b95da2d7a1a1105` |
| `cloud/collection.py` | `b9ec045734091f44e0e98d9b709adc5870d254cec1724a92785d000cb72375fe` |
| `cloud/redaction.py` | `9caaa30f64d5f5ae763f84597a0378f5731510b0815ea19f5128d13dcee638e8` |
| `cloud/reflection.py` | `6b85bd5cf1da85a32746b78207a458d58f77fba908699dc9e24f9b1f254768c5` |
| `services/cloud_context_service.py` | `4d60b65b77ba178678a4d11fd12b719c86c816295f22c91a09864bd9375cd989` |
