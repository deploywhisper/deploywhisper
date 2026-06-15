# DeployWhisper UI Demo Infrastructure Samples

This folder contains synthetic infrastructure artifacts for a team demo. The
files are realistic enough to exercise DeployWhisper reports, evidence links,
blast-radius context, rollback guidance, incident matching, and topology
visualization without using real customer infrastructure, secrets, or state.

## Folder Map

- `analysis-artifacts/terraform/checkout-platform.tf` - Terraform source for a checkout service stack.
- `analysis-artifacts/terraform/checkout-risk-plan.json` - Terraform plan JSON with review-worthy network, IAM, storage, and database changes.
- `analysis-artifacts/kubernetes/checkout-platform.yaml` - Kubernetes deployment, service, ingress, and policy manifests.
- `analysis-artifacts/cloudformation/payments-edge-stack.yaml` - CloudFormation edge stack with public ingress and permissive bucket settings.
- `analysis-artifacts/ansible/ops-rollback-playbook.yml` - Operational rollback playbook with tasks reviewers can inspect.
- `analysis-artifacts/jenkins/Jenkinsfile` - CI/CD pipeline stages for build, scan, approval, deploy, and smoke test.
- `topology/service-topology.json` - Service topology context that maps resources to application services.
- `incident-memory/public-admin-ingress.md` - Optional synthetic incident memory for demonstrating incident matches.

## Recommended Demo Flow

1. Start DeployWhisper and open the UI.
2. Go to `Settings` and upload `topology/service-topology.json` in the topology section.
3. On the dashboard, upload the files under `analysis-artifacts/`.
4. Run the analysis in local-only mode first to show deterministic report behavior without an AI provider.
5. If an AI provider is configured, run the same artifact set again with AI enabled and compare the narrative.
6. Open the persisted report from `History` and show the verdict, evidence inspector, findings, context completeness, topology freshness, blast radius, rollback guidance, and report comparison.

## Suggested Upload Sets

For a full demo, upload all of these files together:

```text
analysis-artifacts/terraform/checkout-risk-plan.json
analysis-artifacts/terraform/checkout-platform.tf
analysis-artifacts/kubernetes/checkout-platform.yaml
analysis-artifacts/cloudformation/payments-edge-stack.yaml
analysis-artifacts/ansible/ops-rollback-playbook.yml
analysis-artifacts/jenkins/Jenkinsfile
```

For a shorter topology-focused demo, upload only:

```text
analysis-artifacts/terraform/checkout-risk-plan.json
analysis-artifacts/kubernetes/checkout-platform.yaml
```

For a low-noise pipeline demo, upload only:

```text
analysis-artifacts/jenkins/Jenkinsfile
analysis-artifacts/ansible/ops-rollback-playbook.yml
```

## Expected Talking Points

- Terraform opens administrative ingress from `0.0.0.0/0`, marks an RDS instance as publicly accessible, relaxes S3 public access controls, and changes an IAM policy.
- Kubernetes introduces a privileged checkout API pod, a public load balancer service, an ingress without TLS, and an allow-all egress policy.
- CloudFormation provides another public edge and storage exposure example.
- Jenkins and Ansible show how rollout and rollback artifacts appear in the same report as infrastructure artifacts.
- The topology file maps changed resources to Checkout API, Payments Worker, Edge Gateway, Data Store, and Customer Web, so blast-radius panels have direct and transitive service context.

## Optional Incident Memory Demo

To demonstrate incident matching, import
`incident-memory/public-admin-ingress.md` into the active project from the
Incidents workflow or API before running the full upload set. The record is
synthetic and intentionally mirrors the public admin ingress risk in the
Terraform plan.

## Safety Notes

- These samples are fictional and use placeholder names only.
- No real credentials, customer data, private incident content, or Terraform state are included.
- Do not apply these files to a real cloud account or cluster. They are for upload and analysis demonstrations only.
