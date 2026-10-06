## Terraform State Connector

DeployWhisper can import a local Terraform state file as read-only topology context for a project or workspace. The connector normalizes managed resources and dependency edges into the same project-scoped topology graph used by blast-radius and context-completeness analysis.

### Import

Use a local `terraform.tfstate` file:

```bash
deploywhisper topology import --from terraform --source ./terraform.tfstate --project payments
```

For workspace-scoped context:

```bash
deploywhisper topology import --from terraform --source ./terraform.tfstate --project payments --workspace prod
```

The import stores normalized resource identities and relationships only. Raw Terraform state JSON and full resource attributes are not persisted.

Terraform `sensitive_attributes` paths and `sensitive_values` masks exclude marked identity fields. Recognizable credentials in identity fields or resource keys are omitted; credential-bearing graph identities and source paths are rejected rather than renamed. Keep credentials out of resource names and local snapshot filenames. Source references, import notes, custom topology labels/owners, cached drift, and legacy topology reads are screened before returning context to APIs or analysis.

These controls do not classify every opaque string as a secret. Supply accurate Terraform sensitivity markers and use synthetic state in examples/tests. Historical database rows and operator-owned source files are not rewritten by read-time screening; operators should remove or replace historical sensitive copies under their retention policy.

### What Is Mapped

- Managed Terraform resources become topology services keyed by Terraform address, such as `aws_db_instance.primary`.
- Resource keys include the Terraform address and stable identity fields when present, including `id`, `arn`, `name`, `resource_id`, and `self_link`.
- Terraform state dependencies are reversed into downstream topology edges so a change to a dependency can surface dependent resources in blast-radius analysis.
- Terraform data sources are skipped because they are not managed infrastructure resources.

### Degraded States

Missing, unreadable, malformed, or structurally incomplete state files return explicit import warnings and do not replace active topology context. Stale local state files still import, but the resulting context carries a warning so analysis remains deterministic while surfacing freshness limits.

The connector does not contact Terraform Cloud, object storage, or provider APIs. Remote state retrieval should happen outside DeployWhisper and pass a local read-only state snapshot into the import command.
