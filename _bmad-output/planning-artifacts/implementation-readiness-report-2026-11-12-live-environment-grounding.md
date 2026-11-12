# Story 17.0 implementation readiness — 2026-11-12

Verdict: **READY — Story 17.0 governance and feasibility qualified**. Formal BMad findings R1–R8 were repaired, independently re-reviewed and tested. The original changes-requested report remains historical evidence; the resolution record supersedes its open findings.

## Authority and boundary

RFC 0002 was accepted on 2026-10-19. On 2026-11-12 the maintainer explicitly approved choosing the best SDK/design and completing the story, then explicitly requested all review findings fixed and properly tested. Scope agrees with the parent PRD and architecture §26: local-first, advisory-only, disabled-by-default read-only grounding. Every write, apply, destroy, tag, provision and remediate capability, account inventory, hosted collection service and Epic 16 dependency is excluded from the product contract. Existing wildcard CODEOWNERS covers cloud/. Local producer fixtures used only built-in terraform_data in temporary directories, never a cloud provider.

This record proves scoped governance/feasibility. It does not implement product LEG-FR requirements or qualify live AWS IAM, transport, production credentials or release-wide behavior.

## Six resolved RFC questions

| Question | Adopted decision and proof |
| --- | --- |
| SDK | Optional boto3 extra; no mandatory default SDK or custom signer. Approved dependency decision, exact seven-package hash lock, Python 3.10 metadata/resolution compatibility and advisory scan are in the [packet](../../docs/verification/live-environment-grounding/17-0/dependency-decision.md). Current probes run on Python 3.13/3.14; a Python 3.10 runtime execution is not claimed. Product packaging is owned by 17.2. |
| Coverage and permissions | Frozen 25 families, 42 static request templates, 33 IAM actions and selected response fields. Exact version/family membership, operation references, policy resources/actions and packaged SDK shapes are executable checks. [Permission map](../../docs/verification/live-environment-grounding/17-0/coverage/permission-map.md). |
| Bounds and cost | 15 seconds total, 4 concurrent reads, 100 attempts, 2 seconds per call, zero hidden retries. Mixed 1,000-resource primary-read replay measures 50/200/1000ms scenarios, throttling, cancellation and deadline completion accounting. [Results](../../docs/verification/live-environment-grounding/17-0/bounded-measurement-results.json) now contain a provider-based request-fee estimate using dated official regional S3/SQS tariffs and explicitly labelled control-plane billing-meter inferences. Unknown operations, regions and unsupported profiles never silently become free. Arbitrary-rate sensitivity is separate. Network/tax/free-tier/resource-hour exclusions remain explicit. |
| Prior state | Four checksum-verified real producer profiles: Terraform 1.17.2/1.16.7, OpenTofu 1.13.9/1.12.12, plan format 1.2 (embedded state format 1.0 is distinct). Nested recorded state, absent/null prior state, change.before fallback and pure-create/no-counterpart paths pass. [Producer proof](../../docs/verification/live-environment-grounding/17-0/producer-results.json). Older synthetic shape probes are historical, not qualified producer profiles. |
| Retention | Seven days from observation when unreferenced; live report references extend retention. Import never resets age. Purged payload retains only nonsecret digest/provenance and freshness becomes missing. [Decision table and tests](../../docs/verification/live-environment-grounding/17-0/retention/README.md). Product storage/reference accounting remains 17.1. |
| Shared-host credentials | Initial admitted mechanisms: environment by default, trusted operator-selected shared credentials opt-in. No metadata/container/process/role/SSO/webidentity fallthrough. No caller endpoint/role/account/profile/credential overrides. Packaged SDK models, canonical HTTPS/TLS and safe error projection are proven by [SDK probes](../../docs/verification/live-environment-grounding/17-0/sdk/README.md). Other mechanisms need separate qualification. |

## Acceptance proof

AC1: accepted governance, scope agreement and ownership. AC2: executable fail-closed readiness predicate. AC3: deny-before-construction, deliberate mutation rejection and exact policy equivalence. AC4: credential-free dry-run with no SDK import, no credentials and no network requests. AC5: four real producer exports and fallback checks. AC6: named dynamically detected hardware, measured bounded replay, accurate finished-result counts and sourced provider request-fee estimate. AC7: approved SDK decision, resolved six questions and exact coverage freeze. AC8: documented threat dispositions plus credential, endpoint, model-injection, sensitive-output and resource-bound tests.

Response filters enforce Lambda UUID/function/event-source identity and Route 53 name/type/SetIdentifier, including simple records. Static plan-derived first-page requests never recursively schedule calls from response IDs. Unsupported reverse relations, missing identities, pagination or budget truncation remain unknown/incomplete; no inventory fallback or improvement of severity/confidence is allowed.

## Independent review and validation

[Resolution verification](../../docs/verification/live-environment-grounding/17-0/review-fix-verification.md) records all eight fixes. A separate reviewer restored each bug in memory and confirmed its targeted regression failed, then verified the fixed suites, fixture hash and both official regional tariff downloads. No blocking findings remain.

Final validation: 68 qualification checks passed; fresh root discovery passed 2,128 tests (3 skipped); full local CI passed 3,603 tests across 10 shards (3 skipped), plus skill scenarios and 8 prompt-injection tests with 96 subtests. Repo-wide Ruff lint/format (647 files), Bandit medium/high gate, compilation, Python 3.10 syntax and fixture/link checks passed. UI validation not applicable. Exact commands, source hashes and results are in [final-verification.json](../../docs/verification/live-environment-grounding/17-0/final-verification.json).

## Remaining downstream obligations

17.1 implements retained snapshots/reference accounting. 17.2 packages the optional SDK and production account/region guards. 17.3 requires independent production security review and qualification of real transport interruption/live reads before merge. 17.9 owns end-to-end AWS/operator and release-wide NFR qualification. Unsupported profiles remain denied. These later obligations are not substituted with fixture proof and are not represented as done by this story.

Story 17.0 is closed only for governance and feasibility; no downstream story is automatically promoted or marked done.
