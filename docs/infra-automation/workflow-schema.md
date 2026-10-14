# Authoring and validating workflow major 2

Story 16.3 provides an in-process, effect-free validator. Its normative authoring
contract is [workflow-contract-v2.md](workflow-contract-v2.md), with generated
[JSON Schema](../../schemas/infra-automation/workflow-v2.json) and a separate
[manifest](../../schemas/infra-automation/workflow-v2-manifest.json). It installs
no API, UI, database tables, task handlers or execution engine.

Use the public validation port, not `Workflow.model_validate`, when accepting a
definition. Constructing a typed model alone does not check graph or exact lineage.

```python
from infra_automation.contracts import ValidationLimits
from infra_automation.workflow_validation import validate_workflow

result = validate_workflow(
    b'''workflow_version: 2
project_id: project-demo
workspace_id: workspace-prod
environment: production
steps:
  - id: intake
    kind: uploaded_intake
    depends_on: []
    source:
      kind: uploaded
''',
    limits=ValidationLimits(max_errors=10),
)
assert result.valid
assert result.definition.workflow_version == 2
canonical_bytes = result.canonical_bytes
content_digest = result.digest
```

JSON and YAML enter through this same bytes-only port. Complete JSON documents
retain JSON numeric and Unicode semantics; other input uses the bounded YAML
parser. Equivalent escaped/literal JSON Unicode has identical canonical content. Success returns immutable
canonical bytes, their `sha256:` digest, `tuple-json-utf8-v1`, and a deterministic
topological order. Each `definition` access returns a fresh typed view, so mutation
of a retrieved list or map cannot alter the authoritative bytes. Array order is
significant in the digest; ready-node order is lexicographic. All typed defaults
and nulls are materialized before hashing. No Unicode normalization is performed.

Failure has no definition, canonical bytes, digest or partial execution order.
Inspect `errors` for fixed codes/messages and sanitized field paths, optional
step indices and parser line/column. `truncated` reports omitted diagnostics.
Do not reflect submitted YAML, unknown keys, exception text or Pydantic inputs.
This result is an in-process contract. Story 16.4 must map it explicitly into the
existing response envelope; frozen `error-v1` does not acquire arbitrary fields.

## Inputs, references and admitted profiles

Definitions require strict integer `workflow_version: 2`, literal project scope,
a literal or identifier-input environment, and 1–50 steps. Nullable workspace
supports project drafts; a later run must bind an authorized concrete workspace
before machine messages. Fields are closed at every object boundary.

There are six fixed step kinds: `uploaded_intake`, `admitted_collection`,
`shared_analysis`, `policy_evaluation`, `human_decision` and
`registered_github_handoff`. Their fixed domain ports are screened artifacts,
report, action binding and decision receipt. A plain scalar cannot impersonate
a domain output. A handoff must consume a decision for its exact gate binding;
that gate must consume analysis of the exact intake/collection ancestry. All
`depends_on` entries are mandatory AND-success prerequisites.

Input declarations support only identifier, commit SHA, bounded string, bounded
integer and boolean types. References are whole-value objects:

```yaml
inputs:
  stage:
    type: identifier
    required: false
    default: production
  timeout:
    type: integer
    minimum: 1
    maximum: 120
environment: {ref: input, name: stage}
# Inside intake/collection parameters:
# timeout_seconds: {ref: input, name: timeout}
# A downstream analysis artifact port:
# artifact: {ref: step, step_id: intake, output: screened_artifacts}
```

The reference objects `project.id`, `project.workspace_id`, `run.project_id`,
`run.workspace_id` and `run.environment` use `{ref: project|run, field: ...}`.
They are exact metadata aliases, not string expressions. No nested access,
interpolation, functions, arbitrary objects or callbacks are supported. Required
identifier slots cannot resolve null workspace. Equal input defaults do not make
different symbolic references equivalent.

Uploaded evidence has a fixed limitation and cannot establish repository identity
or saved-plan custody. It permits advisory requests only. Collected evidence
specifies repository/commit constraints and a literal profile digest. No profile
is admitted by default. The application must supply trusted immutable catalog data:

```python
from infra_automation.contracts import ProfileContract, RegistryContract

# qualified_profile_digest must come from qualified server configuration.
registry = RegistryContract(profiles=(ProfileContract(
    digest=qualified_profile_digest,
    tool="opentofu",
    authorization_kinds=("advisory_request", "exact_plan"),
),))
result = validate_workflow(definition_bytes, registry_contract=registry)
```

The fixture profile from Story 16.0 is synthetic structural test input here; its
presence does not qualify or install production collection. Registry records are
data, never handler/plugin registrations. Source truth, profile admission and
actual execution quotas remain independently verified runtime obligations.

After successful structural validation, the trusted run owner may prepare typed
substitution using the public helper ports:

```python
from infra_automation.workflow_schema import InputReference
from infra_automation.workflow_validation import prepare_resolution, resolve_value

# Use a validated definition declaring the `stage` input above.
context = prepare_resolution(
    result.definition,
    supplied_inputs={"stage": "production", "timeout": 60},
    metadata={
        "project_id": "project-demo",
        "workspace_id": "workspace-prod",
        "environment": "production",
    },
    supplied_outputs=[],
    registry_contract=registry,  # Required when the definition uses collection.
)
stage = resolve_value(InputReference(ref="input", name="stage"), context)
```

The helper rechecks complete scalar, graph, lineage and profile semantics before
substitution. Pass the same trusted registry used for validation; its default
empty catalog admits uploaded workflows only. Unknown/missing inputs and incorrect
types reject; optional defaults materialize.
Output records have exactly `{step_id, output, handle}` and copy bounded opaque
handles. Only outputs currently referenced need exist. The copied immutable
context accepts no arbitrary output objects. `ResolutionError` contains fixed
sanitized diagnostics. Resolving a handle never establishes producer success,
authorization, source provenance, admission, freshness or permission to dispatch.

## Resource configuration and compatibility

The pure default ceilings are 131,072 raw/canonical UTF-8 bytes, nesting 16,
50 steps, 32 inputs and 50 diagnostics. Applications can lower them through
`ValidationLimits`; raising them rejects. YAML anchors, aliases, merges,
recursive structures, duplicate/non-string keys, explicit tags/directives,
implicit timestamps, nonfinite/fractional numbers and unsafe integers reject.
Container-depth counting starts with root mapping at one. Parsing budgets apply
before domain model construction.

The application adapter `config.workflow_validation_limits()` reads these settings:

| Environment setting | Default / maximum |
| --- | ---: |
| `DEPLOYWHISPER_WORKFLOW_MAX_BYTES` | 131072 |
| `DEPLOYWHISPER_WORKFLOW_MAX_DEPTH` | 16 |
| `DEPLOYWHISPER_WORKFLOW_MAX_STEPS` | 50 |
| `DEPLOYWHISPER_WORKFLOW_MAX_INPUTS` | 32 |
| `DEPLOYWHISPER_WORKFLOW_MAX_ERRORS` | 50 |

Pass the returned limits into `validate_workflow`; importing the pure validator
reads no application configuration or environment variables. Invalid settings
fail closed. Actual collection quotas may only lower the intake parameters'
8-MiB/600-second hard ceilings.

Major 2 is a deliberate breaking workflow revision. Definitions with missing,
v1, unknown, boolean or string versions reject. There is no automatic v1
conversion: environment, input declarations and source/profile choices require
explicit authoring. Frozen v1 schemas, fixtures, prototype and manifest remain
byte-identical historical evidence. Runner, enrollment, receiver, provenance,
state, cursor and error protocols remain v1; report remains v2. Future definition
consumers must admit major 2 explicitly. A digest-only receiver does not gain the
ability to interpret workflow bytes. Publication/run authority and version
negotiation belong to later stories, not this validator.

## Reproducing standalone qualification

The [Story 16.3 measured evidence](../verification/infra-automation/16-3/README.md)
records the qualified Linux run, actual allocation and source/corpus identities.

The maintained valid/invalid corpora are under
`tests/fixtures/infra_automation/workflow_v2/`. The fifty-step case combines
uploaded and collected evidence, typed references, exact decisions and AND fan-in.
The standalone script needs the installed `infra_automation` package plus its
normal Pydantic/PyYAML dependencies; it never imports tests. Mount/pass the corpus
explicitly when running in a production Python container. `PYTHONPATH=.` supports
a source checkout; omit it when the package is installed:

```sh
PYTHONPATH=. python scripts/benchmark_workflow_validation.py \
  --corpus tests/fixtures/infra_automation/workflow_v2/valid.json \
  --output workflow-benchmark.json
```

The script preloads and encodes the corpus, constructs its registry, and validates
an initial correctness oracle before timing. It performs 100 warmups and 1,000
measured validations, checking canonical content, digest, ordering and errors on
every iteration. Only `validate_workflow` is timed. JSON evidence records
nearest-rank p50/p95/p99, failures, file/canonical/source digests, OS/CPU/runtime
versions, affinity, cgroup controls and address-space limits. `--warmup` and
`--samples` permit small diagnostic runs, which cannot qualify.

`qualified: true` requires exactly that schedule, zero failures, p95 below 500 ms,
Linux, a recorded four-CPU ceiling, and an eight-GiB memory ceiling. A Mac run or
unbounded container is explicitly unqualified regardless of latency. Report the
actual host/virtualization allocation alongside the artifact. The command exits
nonzero for correctness failures; inspect `qualified` and `qualification_failures`
for the performance/resource verdict. This qualifies only the standalone pure
validator; production isolation and mixed-version release-load qualification
remain Story 16.19. No UI validation applies to this slice.
