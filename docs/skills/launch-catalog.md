# Launch Skills Catalog

Story 4.7 seeds the public marketplace with 20 DeployWhisper-maintained launch skills so first-time visitors see a usable catalog instead of an empty browser.

## Included skills

- `helm` — Helm chart rollout, hooks, dependency drift, and values-file safety
- `argocd` — ArgoCD application sync, automation, and ApplicationSet blast radius
- `pulumi` — Pulumi stack aliases, protection flags, and secret handling
- `crossplane` — Crossplane compositions, XRD schema drift, and provider config safety
- `istio` — Istio routing, mTLS, authorization, and mesh policy coordination
- `nginx-ingress` — Nginx Ingress annotations, TLS, and route precedence
- `cert-manager` — Cert-Manager issuers, solver settings, and renewal safety
- `flux` — Flux reconciliation, pruning, HelmRelease config, and interval changes
- `tekton` — Tekton credentials, finally tasks, and workspace race conditions
- `opa-gatekeeper` — Gatekeeper deny-policy rollout, scope, and inventory sync
- `datadog-monitors` — Datadog threshold drift, no-data handling, and alert routing
- `prometheus-rules` — Prometheus alert timing, recording rules, and cardinality risks
- `aws-cdk` — AWS CDK logical IDs, removal policies, and synth-time drift
- `bicep` — Bicep deployment modes, target scope, and secret exposure
- `pulumi-gcp` — Pulumi GCP IAM authority, project targeting, and secret handling
- `pulumi-azure` — Pulumi Azure resource-group blast radius, identities, and recovery settings
- `kustomize` — Kustomize overlays, patch targeting, and namespace drift
- `helmfile` — Helmfile environment inheritance, release ordering, and shared values
- `tanka` — Tanka environment fan-out, cluster targeting, and apply semantics
- `jsonnet` — Jsonnet import graph drift, hidden defaults, and rendered secret leakage

## Launch verification

Every seeded skill ships with:

- a strict manifest v1 frontmatter block in `skills/<id>.md`
- a deterministic harness suite in `tests/skill-tests/<id>/`
- at least three scenarios covering tool selection, raw-file trigger selection, and non-match behavior
- risk-pattern guidance written for advisory-first review flows

Install from the bundled registry with:

```bash
deploywhisper skill install <skill-id>
```
