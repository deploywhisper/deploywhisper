# Story 17.2 code review

Date: 2026-11-17. Target: `dca73bb` relative to `8aa0809`.
Outcome: **Changes requested**. Three independent layers completed: diff-only Blind Hunter, Edge Case Hunter and Acceptance Auditor. Six raw findings merged into five patch findings; no decision-needed/deferred findings. No production code changed during review.

## Findings

1. **[P1][Patch] SDK-generated S3 requests bypass the allow-list, manifest and budget.** `cloud/aws/session.py:119` and `cloud/aws/client.py:204`. `total_max_attempts=1` does not disable botocore's S3 region redirect handler. With one `GetBucketVersioning` entry and call budget1, a synthetic301 causes GET, unallowlisted `HeadBucket`, then GET in another region. The hidden HEAD drops `ExpectedBucketOwner`. Result still says attempts1/recorded/partialFalse. Violates AC1, AC4/5 and LEG-FR-012. Disable implicit operation/region redirects or enforce scope, authorization and accounting before every SDK-generated request. Add real-SDK transport-level regression; Stubber alone does not exercise this path.
2. **[P1][Patch] Provider item failures are reported as complete observations.** `cloud/aws/client.py:218`. An ECS `DescribeClusters` response containing `clusters: []` and `failures: [{reason: MISSING}]` returns recorded/partialFalse. Missing or mismatched identities likewise pass because only pagination tokens are checked. Contradicts catalog's explicit missing-identity/incomplete contract. Validate per-operation failure and identity facts before returning complete metadata; response projection can remain in17.3. Sources: blind+edge; independently reproduced.
3. **[P2][Patch] All exceptions fabricate a missing-permission diagnosis.** `cloud/aws/client.py:237` and `cloud/aws/session.py:125`. Missing credentials, absent SDK, network failures and malformed requests all set missing_permission to the requested IAM action; session failures have already lost their safe category. Preserve sanitized cause categories and name a missing permission only for confirmed provider authorization denial. A fake session raising credential-unavailable reproduced attempts1 and missing_permission ec2:DescribeInstances despite no provider request.
4. **[P2][Patch] AWS session creation globally disables unrelated HTTP diagnostics.** `cloud/aws/session.py:25`. Source suppression permanently disables all existing urllib3 descendants and raises the namespace level aboveCRITICAL. Unrelated application HTTP clients lose warnings/errors after a cloud session is opened. Scope credential-bearing SDK log suppression or isolate it so unrelated transport diagnostics remain observable. Test both no-secret SDK logging and an unrelated urllib3 warning after session creation. Source: blind; verified process-global mutation in code.
5. **[P2][Patch] Exact wildcard DNS record identities are rejected.** `cloud/aws/client.py:79`. Generic name regex rejects `*.example.com.` and provider-escaped wildcard labels as Route53 StartRecordName. These are exact DNS record identities, distinct from inventory selectors. A valid record Call with HostedZoneId, StartRecordType A and MaxItems1 fails validation. Introduce capability/parameter-specific DNS validation and prove exact one-record scope. Source: edge; independently reproduced.

## Validation and proof limits

- Fresh focused command `./.venv/bin/python -m unittest discover -s tests/test_cloud/aws -q`:19passed. Existing tests do not cover the reproduced defects.
- Parent independently ran the auditor's S3 reproduction with pinned botocore1.44.1, synthetic transport responses and socket construction denied. Dry-run showed one call; actual requests were GET `s3.amazonaws.com/demo-bucket?versioning`, HEAD `s3.amazonaws.com/demo-bucket`, GET `s3.us-west-2.amazonaws.com/demo-bucket?versioning`.
- Existing full-suite results from implementation remain historical regression evidence; this review changes documentation/tracking only and does not claim another full-suite run.
- Shared-file secret corpus remains a proof limitation: a shared-file canary supplied in RoleName can be returned by dry-run, whose screening knows environment-backed values. No automatic credential-to-manifest flow was demonstrated, so this is not counted as an additional security defect. Strengthen the shared-file corpus and state its exact output-boundary scope.
- Initial env/trusted-shared-file-only qualification follows approved17.0/architecture26.7. Unsupported ambient mechanisms, production registration/raw-plan mapping, live AWS and composed egress are not misclassified as new implementation defects.
- UI validation not applicable. Branch is `feature/17-2-aws-read-only-session`; remote push not performed because review follow-up remains open.

## Offline S3 reproduction

Run with the approved optional SDK environment and repository on PYTHONPATH. This is a diagnostic reproduction of the unfixed defect, not a regression test or live-provider qualification.

```python
"""Review reproduction: pinned botocore hidden calls, zero real networking."""
import os
import socket
from unittest.mock import patch
from botocore.awsrequest import AWSResponse
from cloud.aws.client import AwsReader, Call, Limits, dry_run
from cloud.aws.session import AmbientSession

class Raw:
    def __init__(self, data):
        self.data = data
    def stream(self, amt=None, decode_content=False):
        yield self.data

requests = []
def send(self, request):
    requests.append((request.method, request.url))
    if len(requests) == 1:
        return AWSResponse(request.url, 301, {}, Raw(b'<Error><Code>PermanentRedirect</Code></Error>'))
    if request.method == 'HEAD':
        return AWSResponse(request.url, 200, {'x-amz-bucket-region': 'us-west-2'}, Raw(b''))
    return AWSResponse(request.url, 200, {}, Raw(b'<VersioningConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Status>Enabled</Status></VersioningConfiguration>'))

call = Call(capability='bucket_versioning', parameters={'Bucket': 'demo-bucket', 'ExpectedBucketOwner': '000000000000'})
with patch.dict(os.environ, {'AWS_ACCESS_KEY_ID': 'SYNTHETIC', 'AWS_SECRET_ACCESS_KEY': 'synthetic-secret'}, clear=True), patch.object(socket, 'socket', side_effect=AssertionError('NETWORK DENIED')), patch('botocore.httpsession.URLLib3Session.send', send):
    print('dry_run:', dry_run([call]))
    result = AwsReader(AmbientSession()).execute([call], limits=Limits(call_budget=1))
    print('result:', result)
    print('actual requests:', requests)
    assert result.attempts == 1 and result.partial is False
    assert [method for method, _ in requests] == ['GET', 'HEAD', 'GET']
    assert 'us-west-2' in requests[-1][1]

```
