# Story 17.1 bounded implementation plan

Prerequisite: Story17.0 closed and merged via PR221, develop commitd8439a6. Its final readiness report is READY. Current task is implementation against a network-free reference provider only; no provider SDK/dependency installation or cloud credentials.

## Packets and interfaces for independent review

1. Contract/registry: frozen Pydantic2 resource identity and per-resource read-result models, CloudConnector Protocol, direct typed registry and explicit unknown/unimplemented errors. Estimated100–200source lines plus focused tests.
2. Snapshot/redaction: immutable nested tuples/typed scalar facts, provider/project/scope/regions/UTC read window/actions/partial status, deterministic canonical digest. Shared content_security screening, forbidden raw plan/state/user-data payload rejection/removal, configurable account masking BEFOREdigest. Estimated200–350source lines plus hostile corpus tests.
3. Evidence: append live_state to existing source Literals only; reuse deterministic classification, ContextSourceMetadata freshness, EvidenceItem and existing Evidence Law gates. No fields/defaults added to existing report constructors. Verify retained digest/project before minting evidence. Estimated50–100source lines plus gate/freshness tests.
4. Service/persistence: AppSetting per-project opt-in record (scope-checked, defaultfalse), one minimal project-FK immutable snapshot table in independent model metadata and a version-1 cloud-owned initializer, repository canonical/digest validation; core migration history stays unchanged. Internal cloud service takes a server-constructed authorized-session/unit-of-work port; no role claims, booleans or per-operation authorization callbacks. Absence denies effects; disabled/unconfigured projects with a valid installed port return before provider construction. This avoids copying authorization logic or importing Epic16-coupled wrappers. No public routes or default analysis hook are added. Estimated250–450source lines plus persistence/scope/rollback/immutability tests.
5. Reference provider: only supplied synthetic deterministic observations, no SDK/network. Conformance seed proves extension without core analysis diff; future production connector suite remains17.9. Estimated50–100source lines plus tests.
6. Compatibility: register cloud/evidence tests explicitly in localCI/GitHub, add cloud to package/static-check targets, document implemented foundation versus future providers. Run root smoke, full localCI, exact API/CLI/infra pytest shard for new schema/storage integration and focused security checks. UI validation not applicable.

Packets execute sequentially where interfaces/files depend on predecessors. Independent read-only review/test preparation may overlap. Shared evidence/models.py changes are additive source-Literal members only. No analysis/scoring/report serializer diff; no new schema fields in legacy outputs; no provider SDK imported. Cloud import graph must reject/omit Epic16 modules and provider SDKs in isolation tests.

## Risks and review decisions

- Existing project authorization wrappers lazily import Epic16 recovery/worker modules. An explicit trusted server-side authorization port is required for this independent slice; missing production adapter is unavailable, never default-allow. Reference qualification injects an isolated trusted test port. Later surfaces adapt existing app authorization outside this component; they cannot pass claimed roles/request callbacks.
- Existing report ContextSnapshot and EvidenceItem rows cannot hold standalone snapshot bodies without changing their semantics. The minimal new project-FK table is needed; no full future grounding schema or report migration is introduced.
- Frozen Pydantic attributes alone do not freeze nested dicts. Snapshot fields must be deeply immutable and canonicalized/revalidated on persistence/read, including tampered copy() models.
- Generic credential redaction is not arbitrary user-data classification. The snapshot boundary must reject raw content/user_data shapes and constrain structured facts before shared redaction; keys and embedded account identifiers need screening too.
- Grounding remains disconnected from existing analysis by default. Existing API/CLI/agent payload serialization and advisory should_block behavior stay untouched. Existing source enum schemas expand additively as explicitly required.

Independent interface review: READY for core packets1.1/1.2, with required corrections below. No product code was modified before this review.

## Independent interface-review constraints

- Screen factname/value pairs in their semantic key/value context and collect secrets before dropping raw facts, so sibling echoes and keys cannot leak.
- Separate required opaque authorized scope identity (scope_id) from maskable account/scope display. Bind scope_id in the digest; the trusted server adapter rotates it when the authorized account binding changes. Never derive authority from a masked display value.
- Keep the same project/operation-authorized transaction through persistence/evidence admission; no per-request auth callback or claimed principal. Missing installed authorization port is explicitly unavailable.
- Insert-only database guards must permit legitimate project-FK cascades without allowing direct snapshot deletion. Reference-held retention must use durable report/EvidenceItem references, not TTL alone; do not purge payload while referenced.
- Revalidate deep snapshot state/digest/project and resource read status before evidence minting; digest excludes storage timestamps and retention metadata.

## Storage correction after full-suite evidence

The global043/shared-model approach was rejected after actual baseline qualification/recovery failures. See [minor correction](../../../../_bmad-output/planning-artifacts/sprint-change-proposal-2026-11-13-cloud-storage-isolation.md). The snapshot entity now belongs to separate model metadata and a cloud-owned schema/version initializer, installed on explicit opt-in under the same server UOW. Core Alembic head42 and both shared qualified source files stay byte-identical. ACs, SDK-free reference scope and all immutable/publication protections are unchanged.

Final storage isolation implementation was independently re-reviewed: both qualified shared source files are byte-identical, core initializer restarts with the opt-in cloud namespace, and all strict namespace/rollback/immutable/publication regressions pass. Product acceptance criteria remain unchanged.
