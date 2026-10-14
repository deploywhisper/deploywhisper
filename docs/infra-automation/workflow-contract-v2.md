# Closed workflow contract — major 2

Decision date: 2026-10-13. The maintainer selected revision of the contract to
fulfil Story 16.3's broader requirements, rather than reducing them to the
Story 16.0 prototype. This is a **workflow-only major revision**. The frozen
v1 manifest, schemas, prototype and hashed fixtures remain unchanged historical
qualification evidence. This document is the normative production authoring
contract for Story 16.3; a valid definition is not permission to execute.

## Version and implementation boundary

- Require the explicit strict integer `workflow_version: 2`. Reject missing,
  boolean, string, old or unknown versions. Nested workflow objects have no
  independent `version` field. Unknown fields are rejected everywhere.
- Retain `tuple-json-utf8-v1` canonicalization. Workflow major and canonicalization
  algorithm versions are independent. A changed major changes content and digest.
- Do not automatically translate v1: environment, inputs and source/profile choices
  cannot be recovered from it safely. Historical v1 remains inspectable as history,
  not an executable input to the new validator.
- Runner/enrollment, receiver, provenance, state, error and cursor protocols remain
  v1; reports remain v2. Only the receiver binding directly carries opaque workflow
  revision/input digests. Other protocols retain their own scope/profile/source
  fields. Consumers must validate the workflow major before interpreting its bytes.
- This slice installs no routes, tables, handlers, collector, network client,
  credential issuer, approval or dispatch mechanism. Registry entries are data.

## Closed definition

The root contains exactly `workflow_version`, `project_id`, `workspace_id`,
`environment`, `inputs` and `steps`. `project_id` is a literal identifier.
`workspace_id` is a literal identifier or null, default null. `environment` is a
literal identifier or an input reference whose declared type is `identifier`.
It cannot refer back to run metadata. `inputs` defaults to an empty object.
`steps` contains 1–50 discriminated typed steps with unique identifiers.

A null definition workspace supports project-scoped drafts. Before a later
machine operation, its owner must resolve a concrete authorized workspace and
bind that scope in the immutable run snapshot; null must never enter a v1 runner
or receiver message. Pure validation neither chooses a workspace nor grants one.

Identifiers are 1–128 ASCII characters matching
`^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$`. Git commits are exactly 40 lowercase hexadecimal
characters. Digests are `sha256:` followed by 64 lowercase hexadecimal characters.
There are no arbitrary object/list inputs, paths, command strings or plugins.

Every step requires `id`, `kind`, and `depends_on` (0–50 unique step IDs). The
remaining fields and output contracts are closed by kind:

| Kind | Additional fields | Output |
| --- | --- | --- |
| `uploaded_intake` | `source: UploadedSource`, optional `parameters` | `screened_artifacts` |
| `admitted_collection` | `source: CollectedSource`, optional `parameters` | `screened_artifacts` |
| `shared_analysis` | `artifact: StepReference` | `report` |
| `policy_evaluation` | `report: StepReference`, `target_id`, `environment`, `authorization_kind` | `action_binding` |
| `human_decision` | `binding: StepReference` | `decision_receipt` |
| `registered_github_handoff` | `binding: StepReference`, `decision: StepReference`, `target_id`, `environment`, `authorization_kind` | none |

`authorization_kind` is exactly `advisory_request` or `exact_plan`. `target_id`
and step `environment` accept literal identifiers, identifier-typed input references,
or identifier-valued project/run metadata reference objects.
`human_decision` inherits its exact target/environment/action from the referenced
binding, rather than carrying independently editable copies.

Intake/collection `parameters` is a closed object. `max_artifact_bytes` defaults
to 8,388,608 and is a strict positive integer no larger than that value;
`timeout_seconds` defaults to 600 and is a strict positive integer no larger than
600. Each may instead be an integer input reference whose entire declared range
fits that parameter's bounds. Actual runtime/profile quotas may only lower these
ceilings. No other step accepts parameters.

`UploadedSource` contains `kind: uploaded`, `repository_id: null`,
`commit_sha: null`, and a fixed `limitation` value:
`Uploaded evidence does not establish repository identity or exact-plan custody.`
The latter three values materialize as defaults. They cannot claim a repository,
collector or saved-plan identity.

`CollectedSource` contains `kind: collected`, `repository_id` (identifier literal
or scalar reference), `commit_sha` (commit literal or commit input reference), and
a literal `profile_digest`. It describes immutable source constraints, not observed
collection provenance. It contains no raw artifact, credential, tool command,
filesystem location, custody handle or claimed collector identity.

## Input declarations and substitution

`inputs` is a map of at most 32 identifier keys to closed type-specific declarations:

| `type` | Value and declaration bounds |
| --- | --- |
| `identifier` | Identifier syntax/length above |
| `commit_sha` | 40 lowercase hexadecimal characters |
| `string` | `max_length` 1–1,024, default 1,024; empty values allowed |
| `integer` | `minimum`/`maximum` within ±(2^53−1), default those endpoints; minimum ≤ maximum |
| `boolean` | Strict boolean only |

Each declaration has `required` (strict boolean, default true) and `default`.
Required declarations have null default; optional declarations must have a
non-null default of exactly their declared type and bounds. Defaults materialize
in canonical output. No coercion, float, list/object value or implicit absent
optional value is allowed. Unused declarations are permitted but confer no
capability; their supplied values still enter the later immutable input snapshot.

References are whole-value objects, never strings interpreted as expressions:

| Reference | Exact fields | Meaning/type |
| --- | --- | --- |
| Input | `{ref: input, name: <declared identifier>}` | The declaration's exact scalar type/range |
| Step | `{ref: step, step_id: <identifier>, output: <output enum>}` | The exact producer's opaque domain output |
| Project | `{ref: project, field: id\|workspace_id}` | Root scope identifier aliases |
| Run | `{ref: run, field: project_id\|workspace_id\|environment}` | Immutable scope/environment aliases |

Project/run metadata is supplied by the trusted run owner, never by author-defined
fields that claim authority. For structural matching, metadata aliases normalize
to the root project/workspace/environment value. A null workspace is not an
identifier and cannot fill a required identifier slot. `run.id`, arbitrary nested
access, functions, conversions, interpolation and concatenation are unsupported.
Literal strings remain data; no expression syntax is ever evaluated.

Only `identifier` input declarations and identifier-valued project/run aliases can
fill identifier slots. A `string` input is not an identifier even if its default
looks like one. Only input references of the appropriate nominal type can fill
commit/integer slots. Step references fill only
the named domain-output slots in the step table. A scalar that looks like a report
ID cannot become a report, action binding, artifact set or decision receipt.

The pure substitution port revalidates nominal references, graph lineage and
profile admission using the supplied registry, rather than accepting a shape-only
model as sufficient. It validates supplied input values/defaults and returns
only already supplied typed values. Supplied domain outputs identify their producer
and fixed output type and are bounded opaque handles, not arbitrary Python objects
or executable callbacks. Unknown/missing values, wrong types and unsupported
references fail closed. Step success, trustworthy output production and metadata
authenticity are runtime obligations; resolving a value never establishes them.

The substitution context contains exactly `project_id`, `workspace_id` and
`environment` as identifier values (workspace may be null). Project and resolved
root environment must equal the definition, and a non-null definition workspace
must equal the context workspace. Refining a null definition workspace to a
concrete authorized workspace is the only permitted scope refinement; the runtime
owner must authorize it before constructing this immutable context.

Supplied input values are a map of at most 32 declared names to their exact
bounded scalar types. Reject unknown names and materialize validated defaults;
reject missing required input values. Supplied outputs contain at most 50 closed
records `{step_id, output, handle}`. IDs/handles use the identifier bounds above,
`output` uses the four fixed output names, and duplicate producer/output pairs or
unknown producer/output keys reject. Only the currently referenced output must
be present: early steps do not require outputs from future steps. A resolved
value is a copied scalar or frozen output-handle record; later mutation of supplied
maps cannot change it. There are no arbitrary nested output objects or callbacks.

## Registry, profile and resource bounds

The registry contract is immutable application-supplied data, not a field of a
workflow or an extension/plugin mechanism. Its six kind/input/output contracts
are fixed above and cannot be overridden. Its admitted profile records contain
only a unique literal digest, tool (`opentofu` or `terraform`) and nonempty allowed
authorization kinds. At most 16 profiles may be supplied. An empty catalog is
valid and denies every collection profile. Tests may use explicitly synthetic
catalogs; production catalogs must come from qualified server configuration.

The Story 16.0 digest
`sha256:b38c7304938ee5d5ad082e74c05b1d325e30145f1fb9e3d16bc42cc47d116772`
identifies its disposable qualified OpenTofu profile only. Its use in a structural
fixture does not install a collector or qualify production execution. No default
production profile is silently admitted by importing the validator.

Retain raw UTF-8 size ≤131,072 bytes, nesting ≤16, 50 steps and zero YAML anchors,
aliases, merge keys, duplicate/non-string keys, recursive objects or implicit
timestamps. Reject nonfinite/fractional numbers and integers outside the safe
range. Byte and structural parsing budgets apply before constructing typed
domain models. JSON definitions use the same bounded YAML-compatible intake.
Multiple documents, explicit YAML tags and YAML version/tag directives reject.
Preflight counts container nesting with the root mapping at depth 1; scalars do
not add depth. Decoded strings must remain valid UTF-8.

Aggregate returned errors default to 50, with a hard ceiling of 50. Both raw input and materialized canonical output must fit the configured byte
ceiling; default expansion is checked before success. Configuration may lower
resource/error ceilings but cannot raise them beyond this contract.
Locations use only known schema field names, bounded indices and a fixed marker
for unrecognized keys. Do not return submitted values, raw unknown keys, YAML
excerpts, Pydantic input/context, exception text or credential-like identifiers.
Parser line/column is one-based. A truncated error list is explicitly marked.

## Exact lineage and execution boundary

All dependencies are unconditional **AND success prerequisites**. Reject cycles,
missing/self/duplicate dependencies and references to non-ancestors. Resolve every
local shape/type before following another node's fields. Return lexicographically
ordered ready-node topological order independently of canonical content order.

For each handoff, trace its binding to gate G, its decision to human decision D,
G's report to analysis A, and A's artifacts to intake/collection S. D must consume
the exact same `G.action_binding`. Each reference must be a transitive prerequisite
and have both the producer's fixed output type and the consumer's expected type.

Gate and handoff must have identical symbolic target, environment and authorization
kind. Their environment must match the root environment. Equal literals or the
same input reference match, after normalizing metadata aliases. Different input
references never match merely because their defaults are equal; an input reference
does not match a literal based on a default value. Uploaded lineage permits only
advisory-request gates/handoffs. Exact-plan gates/handoffs require collected lineage
and an admitted profile allowing exact-plan authorization. Every gate/handoff
using collected evidence must select an authorization kind allowed by that profile,
including advisory-request gates without any handoff.

AND fan-in does not require the gate on every individual graph edge path. The exact
typed chain and mandatory successful prerequisites together prevent an unrelated
ancestor from authorizing handoff. There are no `when`, OR, skip, loop,
continue-on-error, failure/finally, script/plugin, unattended approval, apply,
destroy or remediation fields or kinds. Domain output values alone cannot claim
that a predecessor succeeded. Runtime owners must still check every prerequisite's
actual success, live authority, target admission, source/profile truth, immutable
evidence, freshness and decision binding before effects.

## Canonical result, compatibility and qualification

Success returns a typed definition, its canonical UTF-8 bytes, SHA-256 digest,
`tuple-json-utf8-v1`, and deterministic topological order. Canonical bytes are
sorted-string-key compact JSON, `ensure_ascii=False`, `allow_nan=False`, with all
typed defaults/nulls, safe integer numbers, no BOM/newline or Unicode normalization.
Array order remains significant; do not reorder the steps/dependencies for hashing.
Returned canonical content must remain consistent with its digest despite caller
mutation of a retrieved typed view. Failure returns bounded, sanitized field/step
errors and no executable or partly valid workflow. This is a new **in-process**
validation result, not an extension of frozen error-v1. Story 16.4 owns its future
API mapping using the existing data/meta and error-v1 boundaries; detailed validator
errors must not be silently inserted into the closed error-v1 message.

Fixed diagnostic codes are `invalid_input`, `resource_limit`, `yaml_syntax`,
`yaml_duplicate_key`, `yaml_key_type`, `yaml_feature_forbidden`, `schema_version`,
`schema_field`, `scope_unsupported`, `dependency_invalid`, `graph_cycle`,
`reference_invalid`, `reference_type`, `binding_mismatch`, `profile_unsupported`,
`input_value_invalid`, `metadata_mismatch`, and `output_invalid`. Each code maps to
one fixed non-reflective message (maximum 160 characters). Paths contain at most 20
segments: known schema fields, indices 0–131072, or the fixed `<unknown>` / `<input>`
markers. Optional `step_index` is 0–49; optional line/column are 1–131073. `truncated`
means at least one detected diagnostic was omitted because of the configured cap.

Publication and start consume this explicit major; no interpreting historical v1
bytes as v2. Start validates/snapshots input values, authorized scope/environment,
source constraints and the qualified profile independently of structural validity.
Receiver-v1 digest fields bind the exact v2 canonical revision/input bytes; runner
and provenance retain their independently versioned operation/source contracts.
No v1 frozen artifact is regenerated or rehashed by this revision. Publish a
separate `schemas/infra-automation/workflow-v2-manifest.json` hashing this contract,
the v2 schema, and its valid/invalid vectors. Definition-interpreting consumers
must explicitly admit major 2 and test rejected v1/unknown-major inputs; digest-only
v1 receiver bindings gain no interpretation capability merely by carrying a digest.
Receivers/runners handling only their unchanged operation messages do not acquire
an invented workflow-version field.

Story 16.3 qualification requires hostile and valid v2 vectors, exact boundary and
one-over cases, zero execution/network/filesystem effects during validation, and
100 warmups followed by 1,000 correctness-checked validations of a declared 50-step
corpus. Record corpus digest, p50/p95/p99, failures, OS/CPU/runtime versions and
resource quotas. The standalone validator target is p95 <500 ms on the declared
Linux 4-vCPU/8-GiB reference allocation; report actual host/virtualization limits.
Mac measurements cannot be relabeled Linux qualification. Full mixed-version
runtime/20-runner/10-workflow/30-minute release-load qualification stays in 16.19.
