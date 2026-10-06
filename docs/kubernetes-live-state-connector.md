## Kubernetes Live-State Connector

DeployWhisper can import optional read-only Kubernetes live-state context for a project or workspace. The connector shells out to the local `kubectl` already configured by the operator, reads supported object summaries, and normalizes them into the same topology graph used by blast-radius and context-completeness analysis.

### Import

Use the active Kubernetes context:

```bash
deploywhisper topology import --from kubernetes --source current-context --project payments
```

Use a named Kubernetes context:

```bash
deploywhisper topology import --from kubernetes --source context:prod-cluster --project payments
```

For workspace-scoped context:

```bash
deploywhisper topology import --from kubernetes --source context:prod-cluster --project payments --workspace prod
```

The import stores normalized object identities, namespace relationships, service selectors, and workload-to-service edges only. Raw Kubernetes API output, full object metadata, and `managedFields` are not persisted.

### What Is Mapped

- Namespaces become topology services keyed as `Namespace/<name>`.
- Workloads become topology services keyed as `Deployment/<namespace>/<name>`, `StatefulSet/<namespace>/<name>`, or `DaemonSet/<namespace>/<name>`.
- Kubernetes Services become topology services keyed as `Service/<namespace>/<name>`.
- Resource keys use namespace-aware refs such as `Deployment/payments/api`; parsed manifests only match live-state objects when the manifest declares the same namespace. Namespace-less manifests remain unscoped because the effective apply namespace can come from CLI flags, Helm/Kustomize, or kubeconfig state outside the file.
- Namespace nodes point downstream to mapped workloads and services in that namespace.
- Service selectors are matched against workload template labels; matching workloads point downstream to the selecting Service so blast-radius analysis can surface live service impact.
- Import timestamps and topology metadata provide freshness signals for reports and drift checks.

### Degraded States

Missing `kubectl`, source-context resolution failures, total command timeout, or complete live-state read failure produce explicit Kubernetes live-state context TODO warnings and do not replace active topology context. Partial per-resource failures preserve successfully read live context with warnings, and an empty successful snapshot clears stale topology for that project or workspace. The connector timeout is bounded to keep deterministic analysis from blocking on cluster access.

The connector does not store kubeconfig content, tokens, raw API responses, or provider credentials. Kubernetes access should be configured outside DeployWhisper through the operator's local `kubectl` environment.

Credentials must not appear in Kubernetes context names or resource identities. Credential-bearing source references, including the resolved current context, are rejected before resource reads. Subprocess failures use bounded messages instead of returning command stdout/stderr. Selectors containing recognizable credentials or sensitive keys are used locally for service/workload matching but omitted from persisted resource keys. Labels/owners in custom topology, source metadata, legacy topology reads, and drift output are screened at the shared service boundary.

Opaque credentials without recognizable patterns or sensitivity labels cannot be reliably identified. Keep all credentials in the external kubectl authentication configuration. Read-time screening does not rewrite historical database rows or operator-owned files; remove or replace old sensitive copies under your retention policy.

Credential discovery examines the complete local snapshot before normalization. Values found in discarded selectors, annotations, environment fields, or other named credential fields also protect identities and import notes across all objects. A credential echoed into an object identity causes a safe rejection; successful imports still match selectors locally using their original values.
