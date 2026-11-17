# Live Environment Grounding — Operator Guide

> **Operator features remain planned.** Story 17.1 implements the SDK-free connector/snapshot/evidence foundation and a network-free reference provider for qualification. AWS/Azure/GCP collection, operator settings, CLI flags and the report UI described below are delivered by later stories. The foundation does not claim live-provider support. See the [implemented connector contract](connector-contract.md).
>
> Governance: [RFC 0002](../rfcs/0002-live-environment-grounding.md) (Accepted 2026-10-19; acceptance authorizes Story 17.0 qualification only) · Target release: v1.6.0, independent of Epic 16 after the approved 2026-11-11 cut-back · Requirements: [feature PRD](../../_bmad-output/planning-artifacts/prd-live-environment-grounding.md) · Architecture: [§26](../../_bmad-output/planning-artifacts/architecture.md)

## What this is

DeployWhisper analyzes a proposed infrastructure change before it is applied. Today it reasons from the change artifact and whatever context you have authored by hand. Live Environment Grounding lets it also read — **read only** — the small set of resources your change actually touches, so that its conclusions are grounded in your real environment rather than in resource-type categories.

It answers four questions that cannot be answered from a plan file alone:

1. **What does this actually affect?** Real dependency edges instead of a "no topology mapping found" warning.
2. **Was this plan computed against current reality?** If something changed out of band since the plan was generated, the diff you are approving is not the diff that will apply.
3. **Can this destruction actually be undone?** Verified from deletion protection, backup configuration, snapshot age and versioning — not inferred from the resource type.
4. **Is this really the environment you think it is?** Grounded in the real account, tags and network placement rather than a name heuristic.

## What this is not

Grounding is strictly read-only and strictly advisory. It will never:

- apply, destroy, modify, tag, provision or remediate anything;
- enable a backup, create a snapshot or toggle a protection setting it reports on;
- inventory your account or region — it reads only what your change touches, plus one hop of real dependents;
- run on a schedule as a drift daemon;
- estimate cost;
- block your deployment. Reports stay advisory. The only gate is a CI exit code you explicitly opt into.

## Safety model

Grounding is **opt-in per project and disabled by default**. No cloud call is issued for a project that has not explicitly enabled a configured connector.

Read-only access is enforced in four independent layers:

| Layer | Mechanism |
| --- | --- |
| In code | A deny-by-default action allow-list evaluated **before a call is constructed**. A non-allow-listed action is refused, not attempted. |
| In CI | An automated test asserts every allow-listed action matches the provider read-only verb set. Introducing a mutating verb fails the build. |
| In IAM | A published minimal policy covering exactly the allow-listed actions and nothing more. See [`aws-read-only-policy.json`](aws-read-only-policy.json). |
| Before you trust it | A dry-run that enumerates the exact calls that would be issued for your plan, **without resolving or using credentials at all**. |

### Credentials

DeployWhisper resolves credentials **only** from your ambient provider chain — profile, SSO, environment, instance role or IRSA. It will not accept credentials as a request parameter, will not persist them, will not log them and will not echo them through the API, the CLI or the UI. The Settings surface shows the credential *source*, never the secret.

Connector configuration cannot retarget the client at an arbitrary endpoint, host, role or account. Endpoints resolve only through provider-canonical resolution.

### Where the data goes

Nowhere. Calls go directly from your environment to your cloud provider. There is no DeployWhisper-hosted service, no relay and no third-party intermediary. The product remains local-first.

Observations are stored as a redacted, digest-bound snapshot scoped to your project. Snapshots never contain secret values, credential material, user data, raw state or plan bytes. Account identifiers can be masked by configuration.

### When it cannot read something

Degradation is fail-safe and explicit. An unreachable, partial, throttled, expired or unauthorized context will **never** lower a severity and **never** raise a confidence score. It triggers `insufficient_context`, and unreadable resources carry a sanitized cause. Only a confirmed provider authorization denial names a missing permission; credential, transport and request failures do not imply that broader IAM access would help.

Partial coverage is labelled partial. Completeness is never implied from a partial read, and `unknown` is never presented as `match` or as `recoverable`.

## Getting started (intended workflow)

1. Review [`aws-read-only-policy.json`](aws-read-only-policy.json) and confirm you are comfortable granting it.
2. Attach the policy to the identity DeployWhisper will run as. Do not create a long-lived access key if your environment supports SSO, an instance role or IRSA.
3. Enable grounding for a single project in Settings → Cloud Context.
4. Run **dry-run** first. It will list the exact calls that would be issued for a recorded plan, using no credentials. Read that list before enabling live reads.
5. Run **test connection**, then submit a plan and open the **Live Context** tab on the report.

## CI usage

The divergence gate is usable from the CLI alone and needs no web UI:

```
deploywhisper analyze <plan.json> --ground --fail-on-divergence
```

If the plan was computed against stale reality, the command exits with a distinct documented exit code. The exact code is published as part of Story 17.4 and is a stable contract once released.

## Restricted and air-gapped networks

If the host that analyzes plans has no cloud connectivity, collect on a connected host and analyze on the disconnected one:

```
deploywhisper ground export --project <id> --out snapshot.json
# transfer snapshot.json
deploywhisper ground import --project <id> --in snapshot.json
```

Imported snapshots produce identical grounding semantics to a live read. They are explicitly labelled `imported`, are subject to an age check that can mark them `stale`, and are rejected if the digest does not verify or if the snapshot came from a different project or provider scope.

This is the supported path for private-network operators. It does **not** require the Epic 16 runner.

## Provider support

| Provider | Intended status |
| --- | --- |
| AWS | The first and only provider targeted for v1.6.0, qualified in Story 17.9 |
| Azure | Registered stub that fails explicitly, like the existing unimplemented topology sources |
| GCP | Registered stub that fails explicitly |

Azure and GCP fail honestly rather than partially. Adding a provider does not require modifying core analysis — see the [connector contract guide](connector-contract.md).

## Budget and cost

Grounding is plan-directed, not an account scan. Scope derives from your change, not your estate. Every collection is bounded by a per-call timeout, a total deadline, a concurrency cap and a call budget, supports cancellation, and reports the actual call count, elapsed time and budget consumption with the result.

Measured defaults are established in Story 17.0 against a realistic large plan on named hardware. This guide will carry the measured values once that story closes; until then no latency or cost figure is claimed.

## Related documents

- [RFC 0002 — Live Environment Grounding](../rfcs/0002-live-environment-grounding.md)
- [Connector contributor guide](connector-contract.md)
- [Minimal AWS read-only policy](aws-read-only-policy.json)
- [Feature PRD](../../_bmad-output/planning-artifacts/prd-live-environment-grounding.md)
- [Architecture §26](../../_bmad-output/planning-artifacts/architecture.md)
- [Epic 16 / Epic 17 boundary plan](../../_bmad-output/planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)


## AWS access primitives — Story 17.2

The optional `cloud.aws` boundary now enforces the frozen 17.0 catalog (42
request capabilities, 33 IAM actions). It remains separate from the provider
registry: a production AWS connector and plan-to-manifest construction belong
to 17.3. No live account or production profile is qualified by these fixtures.

`Call` accepts one exact frozen capability and parameter shape. `dry_run(calls)`
returns the exact service, operation, IAM action and parameters of a recorded
manifest without importing the SDK, resolving credentials or constructing a
client. It does not parse a raw Terraform plan. `AwsReader.execute` consumes the
same revalidated manifest and returns only execution metadata; it discards raw
provider responses. Later connectors must project selected response fields.

Deny-by-default action authorization precedes client construction. Refusals log
a fixed `action_refused` event, never caller text. Unknown parameters, empty
selectors, pagination overrides and wildcard selectors are refused. Caller
configuration permits only a canonical commercial-partition region; endpoint,
host, account, role, profile, proxy, CA and credential overrides are rejected.
SDK endpoint/model data comes only from the pinned installed package. TLS
verification is required, configured endpoints/proxies are ignored, and SDK
retries are disabled. There is no intermediary egress service.

The approved 17.0 credential disposition is preserved: ambient environment is
the default, with an explicitly operator-selected shared credentials file/profile
available only through the trusted server constructor. SSO, IRSA, container and
instance roles, credential processes and role chains remain refused pending
separate qualification. Request inputs cannot select a credential mechanism.
No credential contents are persisted or returned. Missing credentials or the
optional SDK fails closed. The default application dependency locks are unchanged.

Limits default to 2 seconds per call, 15 seconds total, four concurrent calls,
and 100 attempted calls. Bounds may only be lowered. Provider failures apply
bounded interruptible backoff before later calls; this layer does not retry an
ambiguous call. Cancellation/deadlines stop scheduling and late results are
ignored. A process-wide four-slot fence retains slots for hung transport calls;
daemon workers cannot block process exit. Python cannot kill an in-flight thread,
so cancellation does not promise that an already-issued request stopped. The
SDK connect/read timeout halves bound normal transport phases; fixtures prove
scheduler deadlines without claiming live network qualification. Each result
reports attempted calls, elapsed time and labelled partial/unreadable outcomes.

The [minimal IAM policy](aws-read-only-policy.json) is exactly the approved
17.0 action/resource template, tested for equality. Substitute the operator's
actual authorized scope for template variables before use; it is not a ready-to-
attach production policy. Production IAM qualification remains 17.9.

### Required permissions per capability

| Resource family | Required IAM actions |
| --- | --- |
| `aws_instance` | `ec2:DescribeInstanceAttribute`, `ec2:DescribeInstances` |
| `aws_security_group` | `ec2:DescribeNetworkInterfaces`, `ec2:DescribeSecurityGroups` |
| `aws_network_interface` | `ec2:DescribeNetworkInterfaces` |
| `aws_subnet` | `ec2:DescribeNetworkInterfaces`, `ec2:DescribeSubnets` |
| `aws_vpc` | `ec2:DescribeNetworkInterfaces`, `ec2:DescribeVpcs` |
| `aws_route_table` | `ec2:DescribeRouteTables` |
| `aws_ebs_volume` | `ec2:DescribeSnapshots`, `ec2:DescribeVolumes` |
| `aws_ebs_snapshot` | `ec2:DescribeSnapshots` |
| `aws_lb` | `elasticloadbalancing:DescribeLoadBalancerAttributes`, `elasticloadbalancing:DescribeLoadBalancers`, `elasticloadbalancing:DescribeTargetGroups` |
| `aws_lb_target_group` | `elasticloadbalancing:DescribeTargetGroups`, `elasticloadbalancing:DescribeTargetHealth` |
| `aws_lb_listener` | `elasticloadbalancing:DescribeListeners` |
| `aws_autoscaling_group` | `autoscaling:DescribeAutoScalingGroups` |
| `aws_db_instance` | `rds:DescribeDBInstances`, `rds:DescribeDBSnapshots` |
| `aws_rds_cluster` | `rds:DescribeDBClusterSnapshots`, `rds:DescribeDBClusters` |
| `aws_s3_bucket` | `s3:GetBucketTagging`, `s3:GetBucketVersioning` |
| `aws_iam_role` | `iam:GetRole` |
| `aws_iam_instance_profile` | `iam:GetInstanceProfile` |
| `aws_ecs_cluster` | `ecs:DescribeClusters` |
| `aws_ecs_service` | `ecs:DescribeServices` |
| `aws_eks_cluster` | `eks:DescribeCluster` |
| `aws_lambda_function` | `lambda:GetFunctionConcurrency`, `lambda:ListEventSourceMappings`, `lambda:ListTags` |
| `aws_lambda_event_source_mapping` | `lambda:ListEventSourceMappings` |
| `aws_dynamodb_table` | `dynamodb:DescribeContinuousBackups`, `dynamodb:DescribeTable` |
| `aws_sqs_queue` | `lambda:ListEventSourceMappings`, `sqs:GetQueueAttributes` |
| `aws_route53_record` | `route53:ListResourceRecordSets` |

Each of the 42 individual request capabilities and exact parameter/resource templates is recorded in [`cloud/aws/catalog.json`](../../cloud/aws/catalog.json). Tests assert its equality to the approved 17.0 contract and exercise permission failures for every capability.

Dry-run lists intended calls. Cancellation, timeout, budget, permission refusal
or deadline can reduce actual issued calls; execution never expands the manifest.
SDK payload logging is suppressed at source to prevent debug signing records
from exposing credentials, including credentials obtained from trusted files.
Unrelated urllib3 warnings and errors remain enabled.

Each SDK client permits one catalog operation. An operation-specific guard runs
before parameter construction; another guard terminates redirect/error handling
before SDK handlers can issue a hidden operation or retry in another region.
S3 region redirects return a partial unreadable result instead of issuing
`HeadBucket` or expanding the reviewed manifest.

A successful HTTP status alone does not establish complete metadata. Completion
checks reject provider item failures, missing or mismatched requested identities,
and pagination. Filtered relation lists may legitimately be empty. Exact Route53
record identity checks include the name and type; a leading wildcard DNS label
(such as `*.example.com.`) identifies one record and does not enable inventory.
Failure causes use a fixed vocabulary; provider messages and raw payloads are
never returned. Only verified authorization failures set `missing_permission`.
