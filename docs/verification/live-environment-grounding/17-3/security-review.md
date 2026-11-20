# Story 17.3 independent security review

Date: 2026-11-18. Packet 3.7. Reviewer did not implement production code.

**Final disposition: PASSED for the offline fixture/fault-injection slice.**
Both P1 paths below were repaired by the implementer and independently reproduced
again against the repaired source. No remaining P1/P2 finding was identified.
The original findings and pre-fix results remain below as the decision record.

## Independent repair verification

The reviewer inspected the repaired projection and reran both exact reproduction
scripts retained below. Results:

- ECS: `SERVICE_RESULT_LEAK False`, `READBACK_LEAK False`.
- Lambda: `SECRET_KEY_RETAINED False`; the published facts contain only safe
  bounded expansion metadata, with the credential-bearing tag name removed.
- Additional direct projection probes using an actual plan-built manifest tested
  `Key`/`Value`, `key`/`value`, `KEY`/`VALUE`, and `kEy`/`VaLuE`. A secret tag
  containing numeric text `8675309`, its owner-tag echo, and an integer echo in
  selected `runningTasksCount` were absent from projected output in all four
  cases, and each result was incomplete.

The fix normalizes tag pairs before whole-response secret discovery, rejects
malformed/ambiguous tag shapes, reuses shared metadata screening to cover numeric
echoes and dynamic keys, and independently screens dynamic keys and final fact
names against the discovered sensitive values before worker publication.

Fresh checks against repaired source:

```sh
./.venv/bin/python -m unittest discover -s tests/test_cloud -q
./.venv/bin/python -m unittest tests.test_cloud.aws.test_projection tests.test_cloud.test_collection tests.test_services.test_cloud_plan_collection -q
```

Results: **119 cloud tests passed**, **32 focused projection/collector/authorized
service tests passed**. Focused output: `/tmp/17-3-security-rereview-tests.log`.
The original reproduction scripts were extracted from this report and executed
unchanged using the same local interpreter. An initial additional probe used an
incomplete hand-written ECS request and was correctly rejected before projection;
the passing four-case probe used the actual frozen plan-built manifest.

Repaired `cloud/aws/projection.py` SHA-256:
`5890bfb0287e61ad26c40b356caa54b32982b2c5b8e83c97c13e6a5f378d727f`.
The other source identities in the pre-repair table below are unchanged.
This repair verification closes both P1 findings for this slice. Broad repository
validation and release qualification remain the leader's separate checks.

## Closed P1 — ECS lowercase tag credentials escape worker projection and retained readback

Location: `cloud/aws/projection.py`, `_tags` and `project_response`.

The frozen `ecs_cluster` response fields include `clusters[].tags[].key` and
`clusters[].tags[].value`. ECS uses lowercase `key`/`value`, but `_tags` only
recognizes uppercase `Key`/`Value`. The generic content screener does not infer
that a lowercase tag object's `value` is a credential from its sibling `key`.
A `password` tag and a separate echo of its value therefore become ordinary
flattened scalar facts. Later snapshot screening cannot recover the tag-pair
meaning from names such as `ecs_cluster.clusters.0.tags.0.value`.

This leaks an explicitly secret-labelled value before SDK-worker publication,
through `AwsPlanCollector`, through the authorized `CloudContextService` return,
and through persisted `get_snapshot` readback. Account masking does not remove
the credential. The direct collector additionally labels this response complete.
No malicious trusted factory or forged authorization is needed: the input is a
normal provider response containing a secret-labelled tag.

Reproduce entirely offline from the repository root:

```sh
./.venv/bin/python - <<'PY'
from unittest.mock import Mock
from cloud.collection import AwsPlanCollector
from cloud.reflection import ReflectionTarget
from services.cloud_context_service import CloudContextService
from tests.test_cloud.conformance.helpers import ReferenceFixture
from tests.test_cloud.test_reflection import plan

fixture = ReferenceFixture()
try:
    arn = 'arn:aws:ecs:us-east-1:000000000000:cluster/example'
    sdk = Mock()
    sdk.create_client.return_value._make_api_call.return_value = {
        'clusters': [{'clusterArn': arn, 'tags': [
            {'key': 'password', 'value': 'offline-private-canary'},
            {'key': 'owner', 'value': 'offline-private-canary'},
        ]}]
    }
    collector = AwsPlanCollector(
        target=ReflectionTarget(account_id='000000000000', regions=('us-east-1',)),
        session=sdk, clock=lambda: fixture.now,
    )
    service = CloudContextService(
        unit_of_work=fixture, plan_collector_factory=lambda *args: collector,
        clock=lambda: fixture.now,
    )
    service.configure(1, enabled=True, provider='aws')
    result = service.collect_plan(1, plan('aws_ecs_cluster', {'id': arn}))
    print('SERVICE_RESULT_LEAK', 'offline-private-canary' in result.model_dump_json())
    retained = service.get_snapshot(1, result.snapshot.digest)
    print('READBACK_LEAK', 'offline-private-canary' in retained.model_dump_json())
finally:
    fixture.close()
PY
```

Observed: `SERVICE_RESULT_LEAK True` and `READBACK_LEAK True`.
The identifiers and canary above are synthetic; no credentials or network were used.

Required disposition: recognize all selected tag encodings before flattening;
discover sensitive values across the whole response and screen sibling echoes;
mark screened results incomplete. Add regressions at worker projection and
authorized retention/readback boundaries. Re-review the fixed source before
advancing the independent security gate.

## Closed P1 — Lambda tag dictionary keys echo discovered secrets into fact names

Location: `cloud/aws/projection.py`, `project_response.scalar`.

For the actual selected `function_tags` response shape, `Tags` is a dictionary.
`redact_value(raw, sensitive_values=known)` discovers secret values and screens
scalar echoes, but its general dictionary-key handling does not apply known
secret values outside metadata dictionaries. Projection then validates dynamic
keys using a fresh `redact_value({key: 'probe'})` without the response's known
secret set. A known credential used as a tag key becomes part of a published
fact name; removing the original password tag discards the provenance needed
for later snapshot screening.

Offline reproduction:

```sh
./.venv/bin/python - <<'PY'
from unittest.mock import Mock
from cloud.collection import AwsPlanCollector
from cloud.reflection import ReflectionTarget, extract_resources, build_manifest
from tests.test_cloud.test_reflection import plan

arn = 'arn:aws:lambda:us-east-1:000000000000:function:example'
target = ReflectionTarget(account_id='000000000000', regions=('us-east-1',))
resources = extract_resources(
    plan('aws_lambda_function', {'id': 'example', 'arn': arn}), target=target,
)
manifest = build_manifest(resources, target=target)
sdk = Mock()
def response(operation, parameters):
    if operation == 'ListTags':
        return {'Tags': {'password': 'offline-private-canary',
                         'offline-private-canary': 'public'}}
    if operation == 'GetFunctionConcurrency':
        return {'ResponseMetadata': {'HTTPStatusCode': 200}}
    return {'EventSourceMappings': []}
sdk.create_client.return_value._make_api_call.side_effect = response
result = AwsPlanCollector(target=target, session=sdk).collect_manifest(
    manifest, resources=resources, project_id=1, scope_id='offline-scope',
)
print('SECRET_KEY_RETAINED', 'offline-private-canary' in result.model_dump_json())
print([(f.name, f.value) for f in result.snapshot.resources[0].facts])
PY
```

Observed: `SECRET_KEY_RETAINED True`, including fact
`('function_tags.Tags.offline-private-canary', 'public')`.

Required disposition: screen dynamic keys and final fact names against the same
whole-response known secret set before publication; drop unsafe names, preserve
the incomplete label and cover projection, collection and retained readback.
This is distinct from lowercase ECS tag-pair recognition and remains exploitable
if that pair-specific defect alone is fixed.

## Reviewed boundaries and evidence

Read the complete 17.3 story, project context, approved 17.0 and 17.2 stories and
scope evidence, full tracked diff, and untracked reflection/collection/projection,
degradation and test modules. Review covered the whole implemented fixture slice.

- Request scope: exact regeneration from private original plan resources rejects
  broadened selectors, rebound manifests, second-hop descriptors and coherent
  replacement resource sets. Request templates remain the frozen read catalog;
  response endpoints do not schedule requests. No new account/region inventory
  or write capability was found.
- Projection: direct identity checks and exact Lambda/Route53 postfilters are
  present; one-hop descriptors retain reason/bounds. The P1 above defeats secret
  absence despite the selected-field projection.
- Bounds/accounting: original absolute deadline propagates through service,
  collector and reader. Reservations and actual API invocations have separate
  counters; canceled construction consumes a reservation without inventing a
  call. Late results cannot mutate returned snapshots. Global fact count/byte and
  identity bounds are present. Elapsed time includes preparation and UOW
  finalization; synchronous preparation/storage may finish after the call
  deadline, and the tests explicitly record that limitation.
- Authorization/storage: constructor-only UOW and collector ports remain trusted
  server composition, with no HTTP principal/permission/target injection added.
  Live checks bracket extraction, collection, retention and readback within the
  authorized transaction. Revocation rollback coverage passes. Malicious
  in-process factory substitution is outside the untrusted HTTP input boundary.
- Degradation: unavailable/partial/denied/throttled/expired evidence uses the
  shared uncertainty policy and explicit severity/score/confidence floors.
  Analysis receives operational metadata, without inventing retained factual
  admission or snapshot reference authority. Additive API/CLI budgets pass.

Executed:

```sh
./.venv/bin/python -m unittest discover -s tests/test_cloud -q
./.venv/bin/python -m unittest tests.test_services.test_cloud_plan_collection tests.test_analysis.test_cloud_grounding tests.test_services.test_analysis_cloud_grounding tests.test_api.test_cloud_collection_budget tests.test_cli.test_cloud_collection_budget -q
```

Results: **115 cloud tests passed**; **25 service/analysis/API/CLI tests passed**.
Both the direct collector and authorized persistence reproductions above then
confirmed the gap. The separate Lambda-key reproduction also confirmed its leak.
Passing existing tests does not dispose of either P1 path.

Environment: Python 3.14.3, Pydantic 2.14.1, SQLAlchemy 2.0.54. boto3/botocore
are absent from this environment. No installation, credentials, network access,
live AWS calls, or optional real-SDK qualification was performed. UI validation
not applicable. No code modifications were made by this reviewer.

Reviewed SHA-256 source identities before repairs:

| Source | SHA-256 |
| --- | --- |
| `cloud/reflection.py` | `c896d836a2722cab9cfb758fd5d6499ea704d553d81a76fd7386da8c62b5208a` |
| `cloud/collection.py` | `1d30cb4f3db50bb20c87dd77d45030f4dd8935f09fef66ed830519eba21feb9c` |
| `cloud/aws/projection.py` | `7027646d326a5cfaf9299877dbb14e84617b85daa143197d1f2fdf934af0cd2b` |
| `cloud/aws/client.py` | `b2e3224ee7d36fa942d15fee0dba78c9bb82066f557c04034d3ce3cb4efdc20b` |
| `services/cloud_context_service.py` | `3559bb9fdfbc809c3a974209f70dd5e07352ad03c874e2430fbe2a437457a8ba` |
| `analysis/cloud_grounding.py` | `a849e37bc3875eee7c9a288399f13c71da30e67e8d0ea92d357553a1c8e7d8cb` |

This is an offline fixture/fault-injection review. The intentionally unavailable
default AWS registry and constructor-only plan factory are not defects in this
slice. Production operator composition, AWS profile support, live IAM/transport
and release-wide qualification remain later-story obligations. No production AWS
support is claimed. The passed independent security gate applies only to the
reviewed offline slice and repaired source identified above.

## Closeout disposition

The [final independent review](code-review.md#final-independent-disposition) approved the follow-up runtime source for the offline slice and records its source hashes and native SDK checks.
