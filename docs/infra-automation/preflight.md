# Uploaded artifact preflight (Story 16.6)

## Contract and trust boundary

This runner-less advisory slice consumes a published workflow v2 containing
uploaded_intake and shared_analysis only. Provenance remains independently v1;
report v2, its serializers, and frozen schemas remain unchanged. No approval,
exact-plan custody, collector admission, receiver or infrastructure action is granted.

POST `/api/v1/infra-automation/preflights` admits a human RunRequest plus a bounded
list of UTF-8 artifacts (name/content) using a closed JSON request. It authenticates
mutation credentials and automation.request, screens the complete bounded body,
and atomically creates the run and immutable screened manifest. Request identity
binds the artifact digest as well as the original run request: changed artifact
replays conflict. Bytes never enter workflow scalar inputs or snapshot source.
Maximum 32 artifacts, 8 MiB aggregate (also constrained by workflow and policy);
transport JSON is bounded separately before parsing. Unsupported, sensitive,
traversal, binary, inline known-secret or duplicate input is rejected with fixed
errors before any persistence or analysis. Chunked input is buffered within its
bound and screened only after joining. This is a versioned known-pattern guarantee,
not universal detection of arbitrary secrets.

Manifests bind exact run/intake-step/project/workspace/requester and contain only
screened UTF-8 artifact bytes and their recomputed canonical manifest digest.
The digest uses existing sorted compact UTF-8 JSON canonicalization over the
ordered list of name/content pairs. Filenames must be canonical trusted relative
paths. No client selects a handler, lease, fence, actor or analysis result.

## Worker operation and persistence

Only the spawned worker wrapper owns the private AttemptHandle. A wrapper-installed
internal context authenticates that exact capability with claims._attempt and live
policy in each operation transaction. It permits only exact-scope project/workspace
metadata, analysis context reads and analysis.submit. It never authorizes global
settings, arbitrary scopes, human decisions, role administration or handoff. Snapshot
stamps, requester IDs and the disabled engine audit actor are not credentials.
No human cookie or CSRF token is persisted or sent to the child.

CPU/LLM analysis uses the existing analyze_uploaded_files shared pipeline outside
SQLite write reservations. Only final persistence, live fence verification,
immutable report link creation and typed committed output share one short reserved
transaction. Failed/cancelled/stale attempts cannot commit orphan reports. Report
links and manifests are immutable and scoped by foreign keys and SQLite guards.
Linked reports protect their parent scope using existing 16.2 guards and cannot be
deleted or rewritten by ordinary SQL. Existing share/export routes still require
verified report membership; share passwords/tokens and role headers grant no bypass.

GET `/runs/{id}/reports` requires live automation.read and report.read and returns
relational provenance plus canonical `/reports/{report_id}` URLs. Provenance is
outside the report serializer/hash. Upload provenance says repository/commit unknown,
trust unverified and advisory_request; no fabricated Git SHA, raw saved-plan handle
or exact-plan grant. Confidence limitations/context TODOs remain visible on the
link, including missing/partial/stale evidence; eligibility is always false in this
upload-only slice. Deterministic findings and Evidence Law labels remain unchanged.

The relation also returns `evidence_status`, a separately versioned v1 read
projection of the persisted run state/version, latest analysis (or intake)
attempt, immutable snapshot/policy and manifest/report presence. Fixed versioned
limitations and context TODOs render pending, failed, timed-out, cancelled,
expired and mandatory-missing evidence even when no report could be created.
Those facts survive restart; no optional log or stale worker credential is needed
to read them. Unknown states fail closed, no numerical confidence is invented,
and `approval_eligible` is always false. The projection identifies its basis and
`evaluated_at`; `evidence_deadline` follows captured policy evidence TTL, separately
from a shorter execution timeout. A stale report remains readable with explicit
freshness/recollection guidance. Specific exception or revocation causes are not
inferred from a generic persisted failure.

Link metadata is a bounded summary: at most 50 entries per list and 16 KiB for the
exact returned relation, including its opaque ID. Overflow messages state omitted
counts and direct the member to the full report, which retains complete diagnostic
detail. Quotas count the retained manifest, canonical report/link payloads and the
additional actual snapshot files/sidecar bytes. Replay does not charge copies twice;
a quota or final COMMIT failure compensates the report, linkage and snapshot files.

## Synthetic collection contract proof

A service-only typed envelope binds project/workspace/run/step/attempt/fence,
command-source/argv digest, collector/profile/source SHA, exit status, times,
raw-local digest metadata, sanitized manifest digest and redaction version.
Storage recomputes the sanitized digest and checks the current private capability,
lease, immutable source and expected server-side command identity. Stale, tampered,
wrong-scope and mismatched command/source envelopes fail closed. This is authenticated
synthetic proof only: no machine issuer, admitted collector, real saved-plan custody
or production collection route is provided. Frozen descriptive provenance v1 is
retained; the operational envelope has its own v1 rather than extending that schema.

## Verification boundaries

Use temporary SQLite databases, known synthetic sensitive-data patterns, actual
shared analysis, spawned workers, API/CLI compatibility fixtures and migration
checks. UI validation not applicable: no rendered React surface changes.
Production collector, browser workflow UI, policy decisions and snapshot exports
remain 16.14, 16.7, 16.8–16.9 respectively.


## Operator request and response

Enable verified identity and project membership, enable the project's automation
policy, and publish a two-step workflow (`uploaded_intake` followed by its dependent
`shared_analysis`). This entrypoint supports exactly one artifact set and one
analysis; future multi-unit admission is outside this slice. Authenticate with the
existing human session, exact Origin and CSRF header, then POST this shape:

```json
{
  "run": {
    "workflow_id": "published-workflow-id",
    "revision_id": "immutable-revision-id",
    "workspace_id": 1,
    "inputs": {},
    "idempotency_key": "review-request-1",
    "reason": "Review uploaded evidence"
  },
  "artifacts": [
    {"name": "main.tf", "content": "resource \"aws_s3_bucket\" \"logs\" {}"}
  ]
}
```

Admission returns the existing typed run envelope in queued state. Poll the run
and steps, then GET its reports relation; `items` is empty until a report commits.
Repeat the same request/key to recover the original run; changed artifacts under
the same key conflict. JSON transport is capped at 12 MiB, independent of the 8 MiB
aggregate decoded UTF-8 artifact ceiling and any tighter published/policy ceiling.
No raw uploaded content is returned by run/link APIs. Existing authenticated report
artifact reads remain available through report membership.

Migration033 follows032 and installs immutable manifest/link/report guards.
Back up the local database before upgrading using the normal upgrade workflow;
partial migration families/guards fail startup for operator recovery. Retention
and restore tooling remain their owning story. Stored synthetic collected-envelope
proof is a local service-only test interface; it is not an HTTP collector receiver.
