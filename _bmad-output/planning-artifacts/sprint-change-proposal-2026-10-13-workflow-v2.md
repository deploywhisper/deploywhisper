# Sprint change: complete the workflow authoring contract

Date: 2026-10-13. Trigger: Story 16.3 implementation readiness. Scope: a direct
adjustment inside Epic 16; no new epic, requirement ID, runtime capability or
dependency. Disposition: user-authorized contract revision, followed by the
already requested Story 16.3 implementation.

## 1. Issue and authorization

The frozen Story 16.0 workflow prototype has `version: 1` and step-output refs,
but no input declarations, run/project references, environment or source/profile
selection. Story 16.3 and IAU15-FR-009/012/013 require those broader semantics.
Adding them to closed v1 violates its change-control rule; omitting them silently
would falsely claim acceptance.

The maintainer selected option **2**, “Revise the contract first to support the
broader requirements,” rather than the offered reduction to frozen v1. This
authorizes the contract correction and continuation of the requested development.
Using a new workflow-only major is the mechanical consequence of the existing
freeze policy. No additional permission is needed for reversible artifact updates
within that selected scope. This record does not invent another human approval
or rewrite the earlier RFC acceptance/review dates.

## 2. Impact

The current production workflow contract becomes explicit `workflow_version: 2`.
All files listed in `schemas/infra-automation/frozen-v1.json` retain their bytes.
Runner/enrollment, receiver, provenance, state, cursor and error messages remain
v1; report schema remains v2. Only receiver bindings directly carry opaque
workflow/input digests. Definition interpreters must explicitly support workflow2;
unchanged operation-message consumers do not gain a new workflow field.

Story 16.3 owns strict models, parser, references, graph validation, canonical
output, diagnostic bounds, corpus and measurement. Stories 16.4/16.5 consume the
new major at publication/start and resolve authorized concrete workspace scope
before machine operations. Story16.7 uses v2 editor templates. Decision/target,
runner/collection, signed-intake and restore/release owners retain their existing
scope and must qualify the mixed-version boundary during their own integration.

No existing human identity/membership work is rolled back. No workflow route,
table, collector, handler, receiver, approval or dispatch is installed by this
correction. UI validation remains inapplicable to the backend-only slice.

## 3. Chosen approach and alternatives

**Direct adjustment (selected):** add a workflow-only major2 contract, separate
schema/vectors/manifest and explicit consumer notes. Preserve all required typed
namespaces, input bounds and source/environment/profile semantics. Moderate
contract risk is controlled with independent schema/graph/security review and
cross-version rejection tests. The existing Story16.3 planning estimate remains
1–2 engineering person-weeks; this is not an elapsed-time promise. No resequencing
is needed; implementation resumes after the written contract is reviewed.

**Rollback (rejected):** identity/membership and feasibility work is compatible;
reverting it would not restore the missing authoring fields.

**MVP reduction (rejected by maintainer choice):** narrowing references to the
prototype would leave explicit FR-012 and environment/source expectations unmet.

**Modify v1 in place (rejected):** closed objects and canonical bytes are frozen.
Automatic conversion is also rejected: new scope/source choices cannot be guessed.

## 4. Concrete before → after changes

| Artifact | Before | After / reason |
| --- | --- | --- |
| Story16.3 AC1 and schema scope | `workflow_version: 1`, planned `workflow-v1.json` | Required `workflow_version: 2`, new `workflow-v2.json`; no reinterpretation of qualification bytes |
| Architecture §25.5 / §25.9 | Ambiguous workflow v1; globally version1 protocols | Explicit workflow2 and independent v1 operation protocols; exact symbolic lineage and nullable draft scope |
| Workflow contract | No declared inputs/metadata/environment/source/profile | Closed five-type inputs, four reference namespaces, explicit environment/source/profile, six fixed step variants |
| RFC0001 | Historical workflow-v1 selection | Dated workflow-only amendment; historical decision and exception preserved |
| Feature PRD / release plan / project context | Requirements broader than selected fixture | Current-contract reference/version matrix; all canonical FR/NFR text and IDs retained |
| Epic16 / Story16.4–16.5 | Stale gate/version language | Current foundation state and explicit publication/start consumer boundaries; no unrelated status promotion |
| Feature UX | Generic workflow schema | Workflow-v2 template/input/error contract; existing screens and visual scope retained |
| Readiness | Unresolved contract choice | Selected broader contract and explicit remaining implementation/qualification work |

The full normative field grammar, scalar/range rules, source variants, profile
catalog, symbolic equality, diagnostic/result boundary, canonicalization and
compatibility obligations are in
[workflow-contract-v2.md](../../docs/infra-automation/workflow-contract-v2.md).
New schema and fixture hashes belong to a separate workflow-v2 manifest.

## 5. Handoff and acceptance

Root owns contract integration, parser/reference/graph implementation handoff,
tracking and final verification. Bounded schema, qualification/docs and independent
review agents operate under the repository's ownership rules. Packet order remains
schema → parser/references → graph → qualification/docs; tests accompany each.

Independent contract review accepted the direction and required explicit nominal
identifier types, profile authorization checks for advisory paths, runtime metadata
scope equality, finite supplied-value/output maps, in-process error results rather
than mutation of error-v1, and a separate v2 manifest. Those corrections are now
part of the normative contract.

Success requires unchanged frozen-v1 hashes; schema/typed-reference/hostile corpus;
exact AND-prerequisite lineage and symbolic target/environment binding; no side
effects; registered test discovery; existing regression gates; and 100 warmups plus
1,000 measured correctness-checked validations of a 50-step corpus. Record actual
Linux 4-vCPU/8-GiB allocation, host limits, runtime/corpus identity and p50/p95/p99.
Full integrated release-load qualification remains Story16.19. No preparation
timing is claimed as a benchmark.

## 6. Checklist disposition

- [x] Trigger, Story16.3 evidence and maintainer choice recorded.
- [x] Epic and downstream impact assessed; no new/removed/reordered epics or IDs.
- [x] PRD, architecture, UX, contracts, tests/CI and publication consumers mapped.
- [x] Direct adjustment selected; rollback, narrowing and in-place v1 edits rejected.
- [x] Specific artifact changes and bounded implementation ownership identified.
- [x] User authorization applies to the selected revision and original dev-story task.
- [x] Detailed contract independently reviewed and corrections incorporated.
- [x] New schema/vectors frozen and implementation acceptance verified by Story16.3.

Implementation handoff: resume `bmad-dev-story` for16.3 after schema contract
qualification; keep story tasks unchecked until their actual tests pass.

Execution closure (2026-10-14): Story16.3 is ready for code review. Both manifests match; all regression gates pass. The standalone Linux 50-step benchmark is qualified at p95 42.562708 ms with zero failures; actual allocation and source/corpus identities are in [the measurement packet](../../docs/verification/infra-automation/16-3/README.md). Full integrated release qualification remains16.19.
