# Evidence-bound decisions

Story 16.8 adds a backend decision boundary. Canonical reports remain advisory:
`should_block=False` and `go`, `caution`, `no-go` retain their existing meanings.
Workflow policy is a separate result; `insufficient_context` is a separate flag.

A decision binds one immutable workflow revision and input digest, source identity,
project/workspace/environment, report ID/schema/exact export bytes, artifacts,
unit plan, policy version/result/digest, target/receiver/pipeline revision, payload,
custody and authorization/restore epochs. Closed version-1 values reject unknown
fields and versions. The workflow remains v2 and reports remain v2.

Report export captures `_serialize_report` once and stores sorted compact UTF-8
JSON without a trailing newline. Fractional report numbers remain intact. Every
later identity check hashes the stored bytes; reformatting or a newline changes
the digest. Snapshots over 8 MiB are ineligible. Tuple identity independently uses
`tuple-json-utf8-v1`; report bytes never pass through its safe-integer rules.

Requests persist a finite deadline and one active generation per run/decision
step. Decisions use compare-and-swap versions; restart never turns a pending
request into approval. Shared-mode requesters cannot approve their own requests.
Server-selected single-operator mode records acknowledgement, not independent
review. Human rejection and a policy gate stopping work have distinct outcomes.

Eligibility uses the earliest evidence, approval, source and custody deadline,
with the run total deadline as an additional hard ceiling. A consumer must also
reject a clock before the run or receipt's last observed durable timestamp.
The exact deadline is expired, not a final opportunity to approve. Evidence has
at most 60 minutes of validity; stricter policy may shorten it. Longer approval
validity cannot extend evidence. Call the same eligibility checks at decision,
dispatch and receiver consumption; this story does not install a dispatcher or
receiver. Changed evidence/action identity, policy, membership, feature state or
epoch requires a fresh decision. Missing, failed, stale or incomplete mandatory
evidence denies with typed reasons and recovery guidance. Optional narrative
failure preserves deterministic evidence.

Runtime graph checks reuse the static workflow-v2 validator. Every handoff follows
its exact artifact → analysis → policy → decision lineage, with successful
mandatory prerequisites. A decision on an unrelated target/branch cannot cover
another handoff. Skipped or failed prerequisite states never supply authority.

Target/custody material comes from a server-owned scoped port whose default is
unavailable. Tests may install bounded synthetic facts to exercise exact-plan
contract cases. This is not production collector admission, target registration,
remote dispatch or receiver qualification. Those belong to Stories 16.10–16.14.
Unknown uploaded repository provenance remains advisory and ineligible for
approval; neither a fabricated commit nor a client-provided binding supplies
missing authority. Approval grants and bypass/delegation endpoints are absent.

The HTTP boundary uses verified human sessions and live project/report capability
checks, with CSRF/Origin enforcement on decisions. Approval reads do not reveal
raw stored report bytes. Inaccessible objects use the existing generic denial;
stale versions or binding changes require re-reading current evidence. Authority
checking and mutation share one transaction. Browser approval screens belong to
Story 16.9; UI validation is not applicable to this backend slice.

The HTTP operation contract is `GET /api/v1/infra-automation/approvals` with
project/workspace scope and existing signed snapshot pagination, and
`POST /api/v1/infra-automation/approvals/{id}/decision` with `expected_version`,
`binding_digest`, `outcome` (`approve` or `reject`) and a bounded reason. Requester,
reviewer, roles, acknowledgement mode and bypass flags are server-owned. Pending
and approved list projections never imply current dispatch authority: consumers
must call `DecisionService.recheck_approved` inside their independently
authenticated transaction and retain it through the effect.

Policy identity binds the canonical combined object `{automation, advisory}`
containing both captured settings models, plus the current durable automation
policy version. The service resolves the actual report's exact analysis and
collection lineage, and derives recommendation, insufficient context and policy
interpretation from the captured report rather than accepting target-port claims.
Raw unknown recommendation/severity values fail before legacy display normalization.
The existing policy adapter interprets severity thresholds without changing the
canonical advisory `should_block=False`. Partial evidence and failed collection
exit codes deny even when optional narrative is available. Captured freshness and
approval TTLs may shorten the default hour, never extend evidence validity.

Decisions record the reviewer's live authentication and membership generations;
rechecks compare them with current enabled scoped authority and also recheck the
original requester's captured policy stamp. An approved receipt supplies only its
own matching human-decision step. The run remains waiting until every required
human decision is approved and current. No background handler resumes a human
pause or issues remote authority automatically. Invalidations persist typed
reason codes and derive their limitations and recovery TODOs through the shared
eligibility vocabulary. The caller receives a conflict after invalidation commits.

Runtime graph checks accept serial and mandatory prerequisite human decisions.
A request checks its own gate and successful prerequisite ancestry; a later
handoff-only prerequisite cannot prevent creation of an earlier human request.
Each latest approved receipt must pass live evidence, reviewer-generation and
binding checks before it supplies a successful human-step fact. The final
handoff check then evaluates the complete immutable DAG, including additional
mandatory human prerequisites. This keeps receipt validation independent of
recursive handoff evaluation while retaining every required gate.

Review-time boundary handling keeps temporary unavailability distinct from invalid
identity: a material-port 503 is retryable, never authorizes, and preserves the
pending request. Re-read current evidence before retrying. A request made before
its mandatory human predecessor finishes returns a conflict without consuming
quota or stopping an otherwise viable run; failed mandatory evidence still stops
at the gate. Material and receipt callbacks finish before the authorization clock
is sampled. Expiry retains the actual evidence/source/custody/approval reason,
including recollection guidance; a total run timeout has its own typed reason.
The effective decision window shown to reviewers must also respect the run's
absolute deadline, even before background reconciliation updates its state.

This slice qualifies pre-handoff review paths. Staged execution that resumes
human decisions after an external handoff needs the later fixed handoff/receiver
integration; a statically valid graph alone does not admit an external handler.
