## Project Model Guide

DeployWhisper uses projects and workspaces to keep reports, topology, outcomes,
feedback, and future connector data scoped to the right operational boundary.
This guide helps self-hosted operators choose those boundaries before shared
usage hardens.

DeployWhisper does not require a SaaS control plane. The examples below assume a
self-hosted install where your own UI, API, CLI, GitHub integration, or trusted
internal automation supplies project and workspace keys.

### Modeling Rules

- Use a project for the durable ownership and context boundary: product, service
  group, repository group, platform area, or deployment domain.
- Use a workspace for deployable variants inside that boundary: environment,
  Terraform workspace, Kubernetes cluster, namespace, cloud account, region, or
  GitOps application.
- Keep one project when the same owners, incidents, topology, retention, and
  review expectations apply.
- Split projects when teams should not see each other's reports, incidents,
  topology, deployment outcomes, or future connector credentials.
- Prefer stable lowercase keys such as `payments-api`, `platform-networking`,
  `prod-us-east`, or `cluster-blue`. Renaming a project later is more expensive
  once reports and outcomes depend on it.

### Recommended Mappings

| Infrastructure setup | Recommended project mapping | Recommended workspace mapping | Example keys |
| --- | --- | --- | --- |
| Monorepo with several services owned by one platform or product group | Use one project for the repository or product area when incidents, topology, and review ownership are shared. Split into multiple projects only when service groups require separate access boundaries. | Use workspaces for environments, deploy targets, or service slices that need separate history filters. | Project `commerce-platform`; workspaces `checkout-prod`, `catalog-prod`, `shared-staging` |
| Multi-repo product with one deployment domain | Use one project for the product or service group, even when source lives in multiple repositories. This keeps cross-repo reports, topology, and outcomes together. For GitHub App automation across several repositories, set `DEPLOYWHISPER_GITHUB_PROJECT_KEY` to the shared project key instead of relying on the repo-derived default. | Use workspaces for environment, account, region, or deployment lane. | Project `payments`; workspaces `dev`, `staging`, `prod-us-east` |
| Independent multi-repo services with different owners | Use one project per service or bounded context so reports and feedback do not leak across teams. Repo-derived GitHub project keys are a reasonable default for this pattern. | Use each service's environment, account, namespace, or region as the workspace. | Projects `billing-api`, `ledger-worker`; workspaces `prod`, `staging` |
| Terraform workspace based delivery | Use a project for the Terraform stack or platform domain. Avoid making every Terraform workspace a project unless ownership or visibility differs. | Map each Terraform workspace to a DeployWhisper workspace. | Project `platform-networking`; workspaces `tf-dev`, `tf-staging`, `tf-prod` |
| Kubernetes cluster based delivery | Use a project for the application group, cluster ownership area, or platform capability. Split projects when cluster teams and app teams need separate report boundaries. | Map clusters, namespaces, or GitOps applications to workspaces depending on how deployments are reviewed. | Project `customer-portal`; workspaces `cluster-blue`, `cluster-green`, `prod-namespace` |
| Platform team shared infrastructure | Use one project per platform capability when context and credentials should stay separate, such as networking, identity, observability, or CI/CD. | Use workspaces for cloud accounts, clusters, regions, or maturity stages. | Projects `platform-identity`, `platform-observability`; workspaces `prod-account`, `sandbox-account` |

### Pattern Guidance

#### Monorepo

For a monorepo, start with the smallest number of projects that preserves review
ownership. A single project works well when the repository has shared platform
ownership and a common topology graph. Add workspaces for deployable service
slices or environments when users need filtered history without separate
authorization boundaries.

Use separate projects inside a monorepo when service teams should not see each
other's reports or when incidents, scanner imports, topology, and deployment
outcomes are managed independently.

#### Multi-Repo

For a multi-repo product, choose the project boundary by operational domain, not
by Git repository count. Several repositories can share one project when they
ship one product or depend on the same incident memory and topology context.

When using the GitHub App integration for a shared multi-repo project, set
`DEPLOYWHISPER_GITHUB_PROJECT_KEY` in that automation path. Without the
override, the integration derives an owner-safe project key from each repository
slug, which is better suited to independent service projects.
Treat the override as required configuration when present: an unknown, malformed,
or blank project key stops GitHub artifact loading and analysis instead of
falling back to the repo-derived default.

Use separate projects for independent services, regulated domains, or platform
areas with different maintainers. This keeps future RBAC, retention, connector
credentials, and report search boundaries clear.

#### Terraform Workspaces

Treat a Terraform workspace as a DeployWhisper workspace when it represents an
environment, account, region, or tenant under one stack. This keeps plan history
and outcomes grouped under the owning project while still allowing `dev`,
`staging`, and `prod` filtering.

Create separate DeployWhisper projects only when Terraform workspaces represent
separate ownership boundaries rather than deployment variants.

#### Kubernetes Clusters

For Kubernetes, decide whether reviewers reason about risk by application,
cluster, namespace, or GitOps application. Use that decision to pick workspace
keys. For example, an application team might use one project with `dev-cluster`
and `prod-cluster` workspaces, while a platform team might use one project per
cluster capability.

Keep topology imports aligned with the same project/workspace choice so blast
radius and context freshness remain understandable.

#### Platform Teams

Platform teams often own shared infrastructure where cross-service context is the
point. Model each platform capability as its own project when credentials,
topology, or incident history must remain distinct. Use workspaces for accounts,
regions, clusters, or rollout stages.

When a platform team supports many application teams, avoid a single global
catch-all project unless all participants should share the same reports and
outcomes. Separate projects make future RBAC and connector scoping safer.

### Self-Hosted Authorization Notes

In local self-hosted mode, omitted lightweight actor headers and CLI actor
environment variables preserve admin behavior. Before exposing project-scoped
APIs in a shared self-hosted install, put DeployWhisper behind a trusted identity
layer, proxy, or middleware that strips caller-supplied actor headers and injects
verified role and project scope.

This keeps DeployWhisper local-first while making the future path to shared-team
RBAC explicit.

### Quick Checklist

- Can every report, topology import, deployment outcome, and feedback event name
  exactly one project?
- Are workspaces deployment variants inside the same ownership boundary?
- Would two teams be surprised to see each other's reports? If yes, use separate
  projects.
- Would two environments share incident memory and topology? If yes, use
  workspaces under one project.
- Are project and workspace keys stable enough for API, CLI, and automation use?
