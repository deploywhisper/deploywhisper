# Connector credential handling and redaction audit

Story 12.3 protects context before it reaches topology/incident/scanner storage,
public validation, API responses, reports or structured model prompts. It extends
[artifact screening](secrets-and-artifact-boundaries.md) and
[provider administration](provider-settings-administration.md); it keeps the
shared analysis core and advisory verdict semantics unchanged.

## Audited boundaries

| Boundary | Protection | Regression evidence |
| --- | --- | --- |
| Terraform state | Full snapshot sensitivity paths/masks are collected before projection, including discarded fields and marked instance keys. Their values cannot reappear through sibling identity fields or other resources. | `tests/test_services/test_topology_credentials.py` |
| Kubernetes discovery | Kubectl handles authentication through local credential references. Auth values, env/annotations and raw API objects are excluded. Sensitive selector pairs are omitted from persisted keys while local selector matching is retained. | topology credential/service suites |
| Operational context references | Credential-bearing source refs are rejected before dispatch. Public status, drift caches, validation previews and older context reads are screened. Unsafe graph IDs are rejected rather than collapsing distinct identities to a marker. | topology credential/service suites |
| Incident intake | Full batch filenames and content supply locally detected values before aliasing, field projection and scope validation. Filename credentials, including encoded declarations and URL userinfo, protect echoes in the same document and sibling files. Screening protects DB writes, source labels, import results and legacy reads. Stable source aliases survive content changes and respect workspace scope; alias lookups select source names without loading incident documents. Caller-declared redaction flags are not the sole control. | connector import, incident submission/review and source alias query suites |
| Scanner intake | Messages, metadata and repeatedly encoded tool/rule labels are screened before database writes. SARIF regions retain validated coordinates, excluding raw snippets and arbitrary fields. Stable raw-input hashes preserve deduplication while readable references are screened. | connector import/scanner review suites |
| Scope-error output | Incident reindex and SARIF/Semgrep API permission checks preserve authorization order. Public scope errors screen credentials detected in submitted content and filenames, including lowercase/normalized key echoes; denied callers retain bounded 403 responses. Direct incident ingestion uses the same scope-error screen. | `tests/test_api/test_connector_scope_security.py`, incident/scanner review suites |
| Syntax/validation errors | YAML/frontmatter errors expose syntax locations, not source excerpts. Rejected inputs still protect public field/source errors. | connector import/API suites |
| GitHub transport | Authenticated requests require HTTPS and permitted same-origin redirects. Raw file fallback uses the configured Contents API rather than forwarding installation tokens to supplied download URLs. Upstream error bodies, CLI stderr and command arguments are omitted from public failures. | `tests/test_services/test_github_credential_security.py` |
| Scaffold and OAuth output | Static URLs must be credential-free before generation/publication. Workflow credentials use GitHub Secrets references. OAuth codes, state and access tokens are excluded from rendered metadata; unsafe callback links fall back to safe targets. | GitHub credential/API suites |
| Configured console logs | Shared screening masks configured connector values and sensitive query parameters, including encoded names and bounded repeated value decoding before sibling screening. Query collection preserves literal plus values and also recognizes form-encoded spaces. Exceptions retain classes only; SDK payload dumps and SQL parameter logs stay suppressed. | connector content/logging suites |
| Reports and model prompts | Existing shared screens now include configured connector values as well as provider keys. Inputs remain local; outbound model calls receive screened structured summaries. | connector content, content-boundary and report suites |
| Telemetry | This app has no outbound telemetry exporter. External proxies, tracing/debug agents and custom handlers require operator controls below. | code inspection and logging tests |

The shared string screen checks up to nine percent-decoded candidates for
credential echoes, including retained incident narratives, scanner messages and
permitted metadata. Harmless encoded prose retains its original spelling.
If a decoded candidate contains sensitive content, or encoding remains unresolved
at the bound, the complete string is replaced with `[REDACTED]`. Plaintext
continues to use readable lexical redaction. This is bounded screening rather
than arbitrary encoding detection; other encodings require operator controls.

Retained incident prose fields are converted to text while the original batch
sensitivity is available. This protects numeric credential echoes before
Markdown normalization and keeps stored/imported/listed titles and redaction
status consistent. Severity values keep the shared protocol exemption; healthy
numeric text and missing-field validation retain their existing behavior.

## Credential references and scope

Use process/container secrets and least-privilege local references. The shared
registry recognizes supported provider variables plus GitHub/App/workflow tokens,
AWS credential values, Kubernetes bearer variables, Azure secret values, Google
OAuth access tokens and Terraform Cloud `TF_TOKEN_*`/`TFC_TOKEN`/`TFE_TOKEN` values.
Unused aliases remain sensitive even when another key wins precedence.

`KUBECONFIG`, `AWS_SHARED_CREDENTIALS_FILE`, `GOOGLE_APPLICATION_CREDENTIALS` and
GitHub private-key paths remain secure file references; screening never reads
these files to build a credential registry. Mount them read-only with restricted
permissions. Do not place credentials in filenames, resource IDs, source labels,
URLs, selectors, repository references or wizard inputs. Instance credentials
remain instance-scoped; context/report access retains existing project/workspace
permission checks.

GitHub App installation/OAuth tokens and JWTs are used in memory, not stored as
settings. Signing currently materializes a restricted temporary key file and
unlinks it in `finally`; use protected temporary storage and restrict access.
Trust the configured GitHub Enterprise endpoints. Generated workflows, setup
notes, README text and PR bodies are published artifacts: use secret references,
never literal values. Share/outcome management tokens are not interchangeable
with a workflow's analysis API credential.

## Operator controls and limits

Disable query capture for OAuth callback/start URLs in reverse proxies, tracing,
request recorders and third-party telemetry. Exclude Authorization headers,
webhook signatures, code/state parameters and request/response bodies from debug
exports. The configured console handler is covered by tests; custom handlers,
HTTP debug printing and external collectors must enforce equivalent controls.
Rotate/revoke credentials and review retained exports after an exposure.

This is deterministic defense in depth, not a comprehensive secrets scanner.
Unlabelled opaque credentials, private business identifiers and custom encodings
may require manual redaction before import or a hosted-provider call. Explicit
Terraform sensitivity and named secret fields are honored, but a declared
`redacted` status alone does not prove a document safe.

Legacy reads are screened; historical database rows, topology mirrors, snapshots
and backups are not automatically rewritten or deleted. Operator-led retention
cleanup and rotation remain necessary for material stored before these controls.
No schema migration, dependency, telemetry exporter or enforcement feature is
introduced. The external Marketplace Action runtime remains in
`deploywhisper/analyze-action`; this repository documents its credential contract.

## Verification

Run `bash scripts/ci-local.sh`, root unittest discovery and the affected GitHub
API/CLI/infra pytest shard. Browser verification uses the production Compose app
at `http://localhost:8080/`; seed only synthetic context through APIs and run
`BASE_URL=http://localhost:8080 CONNECTOR_SECURITY_TEST_DISPOSABLE=1 npm run test:ui-review`.
Enable this flag only with disposable storage: the test creates persistent fixtures.
It checks scanner identity/redaction through its import API and a matched imported
incident through the saved report and rendered page. Scanner imports are currently
standalone evidence; automatic report attachment is a separate existing gap.
Capture screenshots, then stop Compose while retaining operator volumes. See
[CI guidance](../ci.md) for the disposable Compose override and provider test controls.
