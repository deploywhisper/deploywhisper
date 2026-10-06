# Connector credential handling and redaction audit

Story 12.3 protects context before it reaches topology/incident/scanner storage,
public validation, API responses, reports or structured model prompts. It extends
[artifact screening](secrets-and-artifact-boundaries.md) and
[provider administration](provider-settings-administration.md); it keeps the
shared analysis core and advisory verdict semantics unchanged.

## Audited boundaries

| Boundary | Protection | Regression evidence |
| --- | --- | --- |
| Terraform state | Only normalized context is retained. Marked-sensitive identity paths/masks and credential-bearing identity values are omitted; their values cannot reappear through other allowlisted keys. | `tests/test_services/test_topology_credentials.py` |
| Kubernetes discovery | Kubectl handles authentication through local credential references. Auth values, env/annotations and raw API objects are excluded. Sensitive selector pairs are omitted from persisted keys while local selector matching is retained. | topology credential/service suites |
| Operational context references | Credential-bearing source refs are rejected before dispatch. Public status, drift caches, validation previews and older context reads are screened. Unsafe graph IDs are rejected rather than collapsing distinct identities to a marker. | topology credential/service suites |
| Incident intake | Full raw input supplies locally detected values before field projection. Actual content screening protects sibling prose, DB writes, source labels, import results and legacy reads; caller-declared redaction flags are not the sole control. | `tests/test_services/test_connector_import_security.py` |
| Scanner intake | Messages and metadata are screened. SARIF regions retain validated coordinates, excluding raw snippets and arbitrary fields. Stable raw-input hashes preserve deduplication while readable references are screened. | connector import/scanner suites |
| Syntax/validation errors | YAML/frontmatter errors expose syntax locations, not source excerpts. Rejected inputs still protect public field/source errors. | connector import/API suites |
| GitHub transport | Authenticated requests require HTTPS and permitted same-origin redirects. Raw file fallback uses the configured Contents API rather than forwarding installation tokens to supplied download URLs. Upstream error bodies, CLI stderr and command arguments are omitted from public failures. | `tests/test_services/test_github_credential_security.py` |
| Scaffold and OAuth output | Static URLs must be credential-free before generation/publication. Workflow credentials use GitHub Secrets references. OAuth codes, state and access tokens are excluded from rendered metadata; unsafe callback links fall back to safe targets. | GitHub credential/API suites |
| Configured console logs | Shared screening masks configured connector values and sensitive query parameters, including encoded parameter names. Exceptions retain classes only; SDK payload dumps and SQL parameter logs stay suppressed. | connector content/logging suites |
| Reports and model prompts | Existing shared screens now include configured connector values as well as provider keys. Inputs remain local; outbound model calls receive screened structured summaries. | connector content, content-boundary and report suites |
| Telemetry | This app has no outbound telemetry exporter. External proxies, tracing/debug agents and custom handlers require operator controls below. | code inspection and logging tests |

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
`BASE_URL=http://localhost:8080 npm run test:ui-review`. The connector browser test
checks imported context and rendered incident/report surfaces. Use disposable
storage for fixtures, capture screenshots, then stop Compose while retaining
operator volumes. See [CI guidance](../ci.md) for provider test mutation controls.
