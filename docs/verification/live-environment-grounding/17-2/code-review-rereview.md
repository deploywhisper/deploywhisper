# Story17.2 re-review

Date:2026-11-17. Target:`7119277`; full story baseline:`8aa0809`. Outcome:**Changes requested**.

Three independent layers completed: diff-only Blind Hunter, Edge Case Hunter and Acceptance Auditor. Original five fixes are resolved. Seven candidate reports deduplicated into four P2 patch findings; no decision-needed or deferred items. No production code changed during this review.

## Findings

1. **R2-1 [P2] Enforce the qualified commercial partition at configuration admission.** `cloud/aws/session.py:19`. Region regex accepts `us-gov-west-1`, `us-iso-east-1` and `us-isob-east-1`, although `catalog.json:4` restricts this profile to AWS commercial partition. ID-based EC2 reads do not require an arn:aws parameter that might otherwise catch the mismatch. Reproduced directly with validate_config; all accepted. Reject noncommercial partitions before session/client construction. AC4 and frozen17.0 scope. Sources:blind+auditor.
2. **R2-2 [P2] Prevent S3 bucket-name parameters from overriding the configured region.** `cloud/aws/client.py:95` and `cloud/aws/session.py:194`. Generic `${name}` validator accepts an access-point ARN as Bucket. With reader region us-east-1 and Bucket `arn:aws:s3:us-west-2:000000000000:accesspoint/example`, the pinned SDK resolves and sends to `example-000000000000.s3-accesspoint.us-west-2.amazonaws.com`. Current fences still permit this single allowed operation because redirection happens in endpoint resolution, not retry handling. This is a current name/transport validation issue, not a requirement to build17.3 plan mapping. Constrain supported bucket names and explicitly disallow ARN-region overrides; regression should inspect the actual pre-send endpoint. AC4/frozen authorized-region scope. Sources:edge+auditor; parent reproduced with socket creation denied and HTTP transport stubbed. Actual live-provider support or success for the access-point operation is not claimed; the unexpected endpoint is observed before provider acceptance.
3. **R2-3 [P2] Fail closed for unselected Route53 routing identities.** `cloud/aws/response_status.py:155-163`. Completion checks compare Name and Type but ignore SetIdentifier. A single, nontruncated weighted record carrying SetIdentifier blue returns complete for a manifest with no selected routing identifier. The frozen catalog postcondition explicitly requires exact Name/Type/SetIdentifier; no later mapping can recover a selector absent from this manifest. Until the contract carries an expected variant identity, label variant-bearing responses incomplete. Sources:edge+auditor; parent reproduced.
4. **R2-4 [P2] Reject late successful futures before publishing complete status.** `cloud/aws/client.py:361-368`. Done futures are popped and published before per-call timeouts are checked on the remaining pending futures. A valid instance read sleeping4ms under a valid1ms per-call limit repeatedly returns recorded/partialFalse after roughly5ms. Compare trusted completion time to individual and total deadlines before accepting a successful result. This finding concerns truthful timeout labels, not hard thread cancellation or zero scheduling latency. LEG-FR-012/Packet2.5. Source:edge; parent reproduced three consecutive times.

## Validation and boundaries

Fresh targeted checks passed:28AWS unit tests;11pinned SDK tests;65cloud tests;118SDK-free isolation tests; repo-wide Ruff lint and format684files. Existing tests do not cover the four reproductions. The recent full-suite results in review-fixes.md remain historical implementation evidence; this documentation-only re-review did not repeat fullCI.

Pinned SDK checks across all12catalog services also preserved one-send behavior on modeled HTTP500 errors (including DynamoDB endpoint discovery). No new implicit retry/read-only action bypass was established. Provider-specific realistic identity fixtures would improve coverage, but the generic fixture vocabulary is not counted as another functional finding.

Initial env/trusted-shared-file credential restrictions follow approved17.0. Production connector registration, raw-plan mapping and live AWS/composed-egress qualification remain later-story responsibilities. UI validation not applicable. Branch remains `feature/17-2-aws-read-only-session`. No push performed because follow-up work remains open; story returned to in-progress.

## Reproduction

Direct partition probe:

```python
from cloud.aws.session import validate_config
for region in ('us-gov-west-1', 'us-iso-east-1', 'us-isob-east-1'):
    print(validate_config({'region': region}))  # currently accepted
```

Run the following with the approved optional SDK environment and repository on PYTHONPATH:

`PYTHONPATH="$PWD:$PWD/.venv/lib/python3.14/site-packages" /tmp/dw17-2-sdk/bin/python /tmp/story17-2-rereview-edge-repro.py`

This is a diagnostic reproduction of the unfixed behaviors. Socket construction is denied; HTTP transport is synthetic. No real AWS requests occur.

```python
from unittest.mock import Mock, patch
import time
import socket
from botocore.awsrequest import AWSResponse
from cloud.aws.client import AwsReader, Call, Limits
from cloud.aws.session import AmbientSession
from cloud.aws.response_status import response_complete

class Raw:
    def stream(self, amt=None, decode_content=False):
        yield b'<VersioningConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/"/>'

requests = []
def send(self, request):
    requests.append(request.url)
    return AWSResponse(request.url, 200, {}, Raw())

env = {'AWS_ACCESS_KEY_ID': 'AKIA' + 'A' * 16, 'AWS_SECRET_ACCESS_KEY': 'synthetic-secret'}
with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')), patch.dict('os.environ', env, clear=True), patch('botocore.httpsession.URLLib3Session.send', send):
    call = Call(capability='bucket_versioning', parameters={'Bucket': 'arn:aws:s3:us-west-2:000000000000:accesspoint/example', 'ExpectedBucketOwner': '000000000000'})
    result = AwsReader(AmbientSession(), config={'region': 'us-east-1'}).execute([call])
    print('S3 ARN:', requests, result)
    assert requests and '.us-west-2.' in requests[0]

source = Mock()
def slow_read(*args):
    time.sleep(.004)
    return {'Reservations': [{'Instances': [{'InstanceId': 'i-00000000000000001'}]}]}
source.create_client.return_value._make_api_call.side_effect = slow_read
call = Call(capability='instance', parameters={'InstanceIds': ['i-00000000000000001']})
for _ in range(3):
    result = AwsReader(source).execute([call], limits=Limits(per_call_timeout=.001, total_deadline=1))
    print('Late result:', result)
    assert not result.partial and result.elapsed_seconds > .001

parameters = {'HostedZoneId': 'Z123', 'StartRecordName': 'weighted.example.com.', 'StartRecordType': 'A', 'MaxItems': '1'}
response = {'ResourceRecordSets': [{'Name': 'weighted.example.com.', 'Type': 'A', 'SetIdentifier': 'blue', 'Weight': 100, 'TTL': 300, 'ResourceRecords': [{'Value': '192.0.2.1'}]}], 'IsTruncated': False, 'MaxItems': '1'}
complete = response_complete('record', parameters, response)
print('Unselected routing identity complete:', complete)
assert complete

```
