# Registered GitHub adapter — Story 16.11 Packet 1

This internal integration is an addition to the Story 16.10 handoff boundary.
It does not install a delivery port, expose a receiver endpoint or authorize an
external action. The receiver, custody, callback and UI packets remain separate
work. Frozen receiver-v1 messages and target snapshots are unchanged.

## Trusted inputs and configuration

`GithubInfraAutomationAdapter` takes a `PinnedGithubTransport`, a server-owned
`target_resolver(operation_id)` returning the operation's captured
`TargetSnapshot`, and an optional operator-owned API-to-web-origin mapping.
Callers must obtain snapshots and credentials through their own live authorized
service boundary. Payload fields cannot select a different registry target.

Reuse the existing settings in [handoff-contract-v1.md](handoff-contract-v1.md):
`DEPLOYWHISPER_INFRA_ALLOWED_ORIGINS` constrains the transport, and
`DEPLOYWHISPER_INFRA_DISPATCH_CREDENTIALS` resolves the captured `credential_ref`.
No arbitrary environment-variable names, ambient GitHub CLI authentication or
legacy GitHub App credentials are used. Missing credentials deny delivery.
There are no new dependencies or configuration defaults.

The built-in API/web mapping is `https://api.github.com` to
`https://github.com`. A custom origin needs an explicit canonical HTTPS web
mapping and the existing exact origin/private-address operator policy. API paths
remain fixed repository, workflow, branch, tag reference/object, ruleset and run
resources; response URLs are checked as correlation facts, never followed.

## Operations

- `protected_revision(snapshot, credential)` verifies the registered numeric
  repository/workflow identities, active workflow and reviewed branch/tag SHA.
  Same-name branch/tag ambiguity denies. Branches require protection. Tags
  require active applicable rules protecting both updates and deletion without
  bypass actors, aggregating protections across qualified rulesets; unsupported pattern/condition semantics and incomplete bounded
  enumeration deny. This is a current admission check, not a lease preventing
  later ref changes.
- `dispatch(envelope, credential)` validates exact semantic payload and frozen
  consume-message correlation before network access. It uses the protected
  reviewed workflow ref, independently of the IaC source SHA. Inputs contain
  only `operation_id` and `binding_digest`. The returned `DispatchAcceptance`
  records an accepted run; it grants no permission to consume or begin work.
- `poll(snapshot, acceptance, credential)` reads the fixed accepted run resource
  and verifies captured repository, workflow, revision, ref, event, run ID and
  exact API/web URLs. Reads remain possible after the current ref moves or the
  target is disabled. The receiver must still perform current admission before
  any new action. A GitHub conclusion is a `GithubRunObservation`, not a verified
  receiver terminal outcome or proof that a deployment stopped.

The adapter pins API `2026-03-10`. Dispatch requires HTTP 200 with a correlated
run ID and URLs; HTTP 204 does not establish acceptance for this contract.
Legacy GitHub App calls retain their existing `2022-11-28` version. See the
[GitHub dispatch contract](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).
Protection checks use [branch metadata](https://docs.github.com/en/rest/branches/branches#get-a-branch)
and [repository rulesets](https://docs.github.com/en/rest/repos/rules#get-a-repository-ruleset).

## Failure and qualification

Transport retains its existing TLS verification, pinned DNS/peer policy, fixed
overall deadline, response/body bounds and no redirects, proxies or retries.
Metadata traversal is bounded, including tag depth and ruleset enumeration.
Each request has a deadline; this adapter does not supply a polling scheduler.

`GithubAdapterError` exposes a screened code and `may_have_sent`. A dispatch
failure after a possible POST, malformed acceptance or dropped response must
remain uncertain. Never automatically repeat that dispatch. Metadata failure
before the POST does not itself mean a dispatch was sent. The durable outbox and
later reconciliation owner determine the retained operation state.

Grant bearers, receiver credentials and raw saved-plan bytes never enter workflow
inputs or acceptance/observation DTOs. A separately authenticated private
receiver rendezvous remains required in later packets. Local doubles qualify
adapter correlation and transport policy only. Actual sandbox execution is an
outstanding Packet 1 acceptance gate; see
[entry-readiness.md](../verification/infra-automation/16-11/entry-readiness.md).

## Explicit sandbox invocation

Run only in the operator-selected qualification runner, with a harmless
dispatchable workflow accepting the two inputs above. Obtain the matching
captured snapshot and operation-bound envelope through the trusted preparation
boundary; keep them and credentials in memory. This is the integration call,
not a production delivery-port installation:

```python
from config import handoff_allowed_origins, handoff_credentials
from infra_automation.target_transport import PinnedGithubTransport
from integrations.github.infra_automation_adapter import GithubInfraAutomationAdapter

assert snapshot.definition.github_owner == selected_sandbox_owner
assert snapshot.definition.github_repository == selected_sandbox_repository
assert snapshot.definition.github_workflow == selected_sandbox_workflow
assert snapshot.definition.workflow_ref == selected_protected_ref
assert snapshot.definition.pipeline_workflow_revision == selected_reviewed_sha
assert snapshot.definition.credential_ref == selected_dispatch_credential_ref

def captured_target(operation_id):
    if operation_id != envelope.operation_id:
        raise ValueError("Unknown qualification operation")
    return snapshot

adapter = GithubInfraAutomationAdapter(
    PinnedGithubTransport(allowed_origins=handoff_allowed_origins()),
    target_resolver=captured_target,
    web_origins={snapshot.definition.api_origin: selected_https_web_origin},
)
credential = handoff_credentials("dispatch")[selected_dispatch_credential_ref]
accepted = adapter.dispatch(envelope, credential)
observed = adapter.poll(snapshot, accepted, credential)
```

Record only the screened acceptance/observation DTOs, timestamps, exact
registered numeric IDs, reviewed ref/SHA, command/version and actual result.
Check the dispatched event contains only the two correlation inputs. Do not
serialize the envelope, semantic payload, grant or credentials. A lost dispatch
response requires reconciliation; this procedure must not be rerun to create a
replacement operation. GitHub acceptance alone satisfies neither receiver
admission nor successful external execution.
