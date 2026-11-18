# Story 17.2 offline access proof

This packet proves local access primitives, not live AWS grounding. Production
connector registration, raw-plan mapping and selected response projection remain
17.3; live-account/IAM/egress qualification remains 17.9. The AWS registry slot
remains unavailable. Default dependency locks are unchanged.

## Commands and results

- RED: `./.venv/bin/python -m unittest tests.test_cloud.aws.test_access -q`
  failed before `allowlist.py` existed; corresponding session/client module
  commands also failed before those implementations existed.
- GREEN: `./.venv/bin/python -m unittest discover -s tests/test_cloud/aws -q`:
  19 tests passed, including 42 per-capability denial subcases and seven secret
  corpus subcases. The default cloud shard already recursively discovers `aws/`
  because it is a package; no duplicate CI registration was added.
- Deliberate mutation: `./.venv/bin/python -c 'from cloud.aws.allowlist import
  ALLOWLIST, assert_read_only; assert_read_only((*ALLOWLIST,
  "ec2:TerminateInstances"))'` exited **1** with
  `ValueError: Non-read-only AWS action`, as required. Passing negative regression
  `test_mutation_rejected` retains this assertion in CI.
- `./.venv/bin/ruff check .`: passed.
- `./.venv/bin/ruff format --check .`: passed (681 files at this stage).
- Optional SDK environment: `./.venv/bin/python -m venv --system-site-packages
  /tmp/dw17-2-sdk`, then `/tmp/dw17-2-sdk/bin/python -m pip install --require-hashes
  -r docs/verification/live-environment-grounding/17-0/sdk-requirements.lock`.
  Only the approved seven-package SDK set installed in that temporary venv;
  boto3/botocore 1.44.1. Application venv remains SDK-free.
- `PYTHONPATH="$PWD/.venv/lib/python3.14/site-packages:$PWD"
  /tmp/dw17-2-sdk/bin/python -m unittest discover -s
  docs/verification/live-environment-grounding/17-2 -q`: **5 passed**.
  Python 3.14.3 local harness; this is not Python3.11/live runtime qualification.

The optional SDK suite uses real pinned botocore, Stubber and socket denial.
It verifies environment-only credentials, explicit trusted shared-file selection,
missing-credential denial without host fallback, hostile endpoint/proxy/CA/profile
settings ignored, canonical endpoint, exact modeled request and safe errors.
A signing-only regression enables SDK DEBUG loggers before construction and
captures raw LogRecords to verify no credential header/token emission. An
independent reviewer discovered the initial SDK signing debug leak; the fixed
boundary suppresses SDK/urllib3 logs at source before credential resolution and
after client construction, rather than relying on a presentation formatter.

## Acceptance mapping

| AC | Proof |
| --- | --- |
| 1 | `test_access.py`: refused action logs fixed event before constructor; `test_client.py`: frozen request shapes, no wildcard/inventory fallback |
| 2 | read-only assertion over all33actions; deliberate mutation exit1 above |
| 3 | `test_session.py`, optional `test_sdk.py`, and `test_secret_surfaces.py`: no credential request fields, safe SDK errors, signing raw-record regression, seven-key corpus through logs, JSON encoding/CLI streams and actual SQLite snapshot persistence |
| 4 | targeting override corpus; real SDK canonical endpoint/transport probe; package-only model Loader copied from approved17.0 boundary |
| 5 | dry-run with mocked session untouched; exact manifest shared by execution; no optional SDK import at module load |
| 6 | exact policy equality to approved17.0 action/resource template, permission map coverage; runtime permission-denial proof for every42capability |

No new HTTP or CLI adapter is introduced: secret surface tests exercise shared
serialization/stream/persistence boundaries without claiming a new user flow.
UI validation not applicable.

## Bounds and limitations

Scheduler tests exercise call budget, concurrency, timeout, cancellation and
safe provider failures. SDK retries are one total attempt. This layer applies
interruptible backoff before subsequent requests, never retries ambiguous calls.
Timed-out calls retain one of four process-global slots until their daemon worker
returns; late results are discarded. Python threads cannot terminate an
already-issued request. SDK connect/read phase bounds plus the scheduler bound
normal return paths; this packet does not claim hard cancellation of a live
network request or production egress inspection.

The approved17.0 credential disposition deliberately refuses unqualified SSO,
IRSA, instance/container roles, process and assume-role chains. Trusted operator
shared-file/profile selection is constructor-only. This follows the approved
qualification decision rather than silently broadening credential authority.

The catalog is a frozen copy of the approved17.0 contract; an equivalence test
prevents silent drift. Callers supply an already selected exact manifest, not
raw plans or response-derived IDs. Production plan ownership/authorized account
binding remains the next connector slice; these primitives are not registered
as a production connector.

Dry-run enumerates **intended** calls for the supplied recorded manifest. Actual
execution may issue fewer calls because of cancellation, budget, timeout,
permission refusal or deadline; it never expands the manifest. The per-result
status and attempted-call count distinguish those outcomes. This is not a
promise that all listed calls will be issued.

Final focused checks after the SDK-log fix: repo-wide Ruff lint and formatting
passed681files; Bandit over `cloud/aws` found no issues (409lines). Constructor
search covered all new Call/Limits/AwsReader/AmbientSession instantiations in
cloud, tests and this optional SDK packet; no existing constructor changed.

Parent verification additionally passed cloud56tests, SDK-free isolation109tests, Python3.10 grammar parsing of all new AWS modules, and the API/CLI/infra pytest shard:834passed,1skipped,2456subtests. Commands: `./.venv/bin/python -m unittest discover -s tests/test_cloud -q`, `./.venv/bin/python scripts/verify_cloud_isolation.py`, and `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -q --tb=short`. Full-suite results are recorded in the story Dev Agent Record when complete.


The qualified `config.py` remains byte-for-byte unchanged. Its existing five AWS
credential names cover admitted environment credentials. Unsupported SSO and
container credentials are never resolved. The seven-name secret surface corpus
supplies explicit sensitive values to the existing shared snapshot redactor;
that test does not claim those unsupported environment names are automatically
registered. Manifest environment-canary screening tests cover the existing five
registered AWS names. No parallel credential redactor was introduced.

Final regression: `LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m unittest discover -q` passed2,249tests (3skips). `LLM_API_BASE=http://127.0.0.1:1 bash scripts/ci-local.sh` passed all12shards:3,749tests (3skips), plus109isolation tests, skill scenarios and prompt-injection checks. Environment override only avoids incidental local model inference; no persistent configuration changed. Final logs: `/tmp/story17-2-root-final.log` and `/tmp/story17-2-ci-final.log`. Initial run's in-flight red-phase import and protected-config hash failures were resolved; config.py is byte-for-byte preserved and targeted qualification tests passed3tests.
