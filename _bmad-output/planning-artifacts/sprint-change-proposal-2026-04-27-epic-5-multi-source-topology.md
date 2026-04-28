# Sprint Change Proposal: Epic 5 Multi-Source Topology Correction

Date: 2026-04-27
Project: deploywhisper
Workflow: bmad-correct-course

## 1. Issue Summary

Epic 5 was intended to create a context moat through topology automation, deployment outcomes, feedback, and calibration. The current story design over-indexed on Terraform state: `E5-S1` was Terraform-focused, and later topology coverage split into GCP/Azure Terraform provider stories.

That conflicts with the product scope already stated in the PRD, README, architecture, and parser baseline: DeployWhisper analyzes Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation as a multi-tool pre-deployment intelligence layer. If Epic 5 only builds topology automation around Terraform state, blast-radius context becomes uneven and the context moat excludes common CloudFormation, Kubernetes manifest, and Ansible workflows.

## 2. Change Navigation Checklist

| Item | Status | Finding |
| --- | --- | --- |
| 1.1 Trigger story | Done | `E5-S1: Terraform state import` revealed the scope mismatch. |
| 1.2 Core problem | Done | Misunderstanding of original requirements: topology automation was narrowed to Terraform state despite multi-tool product scope. |
| 1.3 Supporting evidence | Done | PRD and README define multi-tool intake; architecture lists Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation parsers; Epic 5 only had Terraform-state topology stories. |
| 2.1 Current epic viability | Done | Epic 5 remains viable if topology import is redesigned around a shared source registry plus source-specific connectors. |
| 2.2 Epic-level changes | Done | Modify Epic 5 topology stories and exit criteria. |
| 2.3 Future epic impact | Done | Epic 6 benchmark coverage already expects Terraform/Kubernetes and expanded multi-tool scenarios; broader Epic 5 topology context strengthens it. |
| 2.4 New epic need | Done | No new epic required. Add and reshape stories inside Epic 5. |
| 2.5 Priority/order | Done | Add a foundation story before source-specific connectors. |
| 3.1 PRD conflicts | Done | PRD Phase 2 needed to say multi-source topology, not Terraform-only topology. |
| 3.2 Architecture conflicts | Done | CLI topology import command needed a source-agnostic form. |
| 3.3 UI/UX conflicts | Done | Topology admin flow needed to mention import from supported source families, not only upload/replace manual topology. |
| 3.4 Secondary artifacts | Done | Sprint status needed story key updates. |
| 4.1 Direct adjustment | Viable | Moderate effort, lower risk than replanning. |
| 4.2 Rollback | Not viable | No completed Epic 5 topology implementation needs rollback. |
| 4.3 MVP review | Not viable | MVP/Phase 2 scope remains achievable; this corrects implementation slicing. |
| 4.4 Recommended path | Done | Direct adjustment inside Epic 5. |

## 3. Impact Analysis

### Epic Impact

Epic 5 remains the correct epic. The change is not a pivot away from the context moat; it restores the intended multi-tool shape of the moat.

The topology portion of Epic 5 now becomes:

- `E5-S1`: shared topology import foundation and source registry
- `E5-S9`: Terraform state topology source for AWS/GCP/Azure representative coverage
- `E5-S10`: CloudFormation topology source
- `E5-S13`: Kubernetes manifest topology source
- `E5-S14`: Ansible inventory/playbook topology source
- `E5-S15`: custom topology source boundary for other tools and future connectors

### Story Impact

`5-1-terraform-state-import.md` was replaced by `5-1-topology-import-foundation.md`. The ready-for-dev story now defines the shared CLI shape, source registry, normalized import result, topology-change contract, source-agnostic diff behavior, and warning model.

The previous GCP/Azure Terraform provider stories were merged into a single Terraform connector story. CloudFormation, Kubernetes, Ansible, and custom source stories were added as backlog entries in Epic 5.

### Artifact Conflicts

PRD Phase 2 and Open Questions were updated to describe multi-source topology connectors. Architecture CLI guidance was updated from Terraform-specific `--state` to source-agnostic `--source`. UX topology management flow now covers importing from Terraform, CloudFormation, Kubernetes, and Ansible sources.

### Technical Impact

Implementation should avoid separate one-off import paths per tool. The corrected design requires:

- shared topology source registry
- normalized topology-change contract
- consistent import result/warning model
- source-specific parsing isolated behind connector boundaries
- no raw IaC persistence
- drift, freshness, and diff behavior shared across all imported source types

## 4. Detailed Change Proposals

### Story: E5-S1

Section: Story identity and acceptance criteria

OLD:

```text
E5-S1: Terraform state import
I want to import AWS topology from Terraform state
CLI: deploywhisper topology import --from terraform --state s3://my-bucket/terraform.tfstate
Supports AWS Terraform provider resources needed for the initial topology graph
```

NEW:

```text
E5-S1: Topology import foundation and source registry
I want one topology import framework for supported source types
CLI: deploywhisper topology import --from <source> --source <uri-or-path>
Supported source identifiers include terraform, cloudformation, kubernetes, ansible, and custom
Import result records accepted, skipped, partially parsed, and unsupported resources without storing raw source artifacts
```

Rationale: Foundation-first sequencing prevents Terraform-only architecture and gives every connector the same graph, diff, warning, and local-first behavior.

### Stories: E5-S9 and E5-S10

OLD:

```text
E5-S9: GCP Terraform state import
E5-S10: Azure Terraform state import
```

NEW:

```text
E5-S9: Terraform state topology source
E5-S10: CloudFormation topology source
```

Rationale: Terraform provider coverage belongs inside the Terraform connector story. CloudFormation needs first-class coverage because it is part of the supported tool intake and common AWS topology source.

### New Stories: E5-S13 to E5-S15

NEW:

```text
E5-S13: Kubernetes manifest topology source
E5-S14: Ansible inventory and playbook topology source
E5-S15: Custom topology source boundary
```

Rationale: Kubernetes and Ansible are supported product inputs and should enrich topology context. A custom boundary gives "other tools" a safe extension point without bloating Epic 5 with every possible tool-specific connector.

### PRD

OLD:

```text
Topology auto-discovery from Terraform state
```

NEW:

```text
Topology auto-discovery from Terraform state, CloudFormation, Kubernetes manifests, Ansible inventory/playbooks, and extensible source connectors
```

Rationale: Phase 2 scope should match DeployWhisper's multi-tool positioning.

### Architecture

OLD:

```text
deploywhisper topology import --from terraform --state <uri>
```

NEW:

```text
deploywhisper topology import --from <source> --source <uri-or-path>
deploywhisper topology import --from terraform --source s3://my-bucket/terraform.tfstate
deploywhisper topology import --from cloudformation --source stack-template.yaml
deploywhisper topology import --from kubernetes --source manifests/
deploywhisper topology import --from ansible --source inventory.yaml
```

Rationale: CLI design should expose source selection without baking Terraform-specific flags into the core topology command.

## 5. Recommended Approach

Use direct adjustment inside Epic 5.

This is a moderate backlog correction, not a major replan. No completed Epic 5 implementation needs rollback. The safest path is to implement the foundation story first, then create source-specific connector stories from the updated Epic 5 backlog.

Suggested sequence:

1. Implement `5-1-topology-import-foundation`.
2. Create/dev `E5-S9` Terraform state connector using AWS/GCP/Azure representative fixtures.
3. Create/dev `E5-S10` CloudFormation connector.
4. Create/dev `E5-S13` Kubernetes manifest connector.
5. Create/dev `E5-S14` Ansible inventory/playbook connector.
6. Create/dev `E5-S15` custom topology source boundary if "other tools" must be supported before Phase 3.
7. Continue with drift, freshness, outcome, feedback, calibration, and trend stories once shared topology context is stable.

Effort impact:

- Epic 5 estimate increases from 7-8 solo weeks to 9-11 solo weeks.
- With parallel help, estimate increases from 4-5 weeks to 5-7 weeks.
- Risk is moderate because the corrected design adds breadth, but risk is reduced by making `E5-S1` a source-agnostic foundation before parser-specific work.

## 6. Implementation Handoff

Scope classification: Moderate.

Recommended handoff:

- Product Owner / Developer: keep updated Epic 5 backlog and sprint status aligned.
- Developer: implement `5-1-topology-import-foundation` first.
- Architect review: verify the normalized topology-change contract before source-specific connectors are implemented.

Success criteria:

- Topology import command is source-agnostic.
- Source-specific connectors do not duplicate diff, warning, freshness, or graph update behavior.
- Raw IaC/source artifacts are not persisted.
- Terraform, CloudFormation, Kubernetes, Ansible, and custom payload coverage can be added without changing the core report format.
