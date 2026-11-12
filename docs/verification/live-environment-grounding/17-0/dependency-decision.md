# AWS SDK dependency decision

Date: 2026-11-12. Status: **APPROVED**. Authority: maintainer's explicit same-thread approval to select the best fit and complete Story17.0.

Selected: optional boto3 extra for AWS-enabled deployments. Default installations remain cloud-SDK-free. Reject mandatory runtime installation because grounding is opt-in; reject a thin signed-request client because it would duplicate signing, endpoint metadata, pagination and credential refresh security responsibilities.

Story17.0 may install boto3 in a disposable qualification environment. Product dependency/lock/image changes belong to17.2 and must include a separately hash-locked optional dependency group, Python>=3.10 compatibility, exact transitive versions and advisory checks. Existing default locks must remain unchanged in this governance/spike story. The qualified version set and security scan are recorded alongside the spike evidence. This approval authorizes the dependency choice, not cloud mutations or production credential use.

Sources: [AWS credential chain](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html), [botocore configuration](https://docs.aws.amazon.com/botocore/latest/reference/config.html).

## Qualified dependency set

`boto3==1.44.1`, `botocore==1.44.1`, `s3transfer==0.19.3`, `jmespath==1.1.0`, `python-dateutil==2.9.0.post0`, `six==1.17.0`, `urllib3==2.8.0`. Metadata and dependency edges: [sdk-versions.json](sdk-versions.json). Hash-locked, resolved for the existing Python3.10 floor: [sdk-requirements.lock](sdk-requirements.lock). Advisory scan: [sdk-audit.json](sdk-audit.json), no known vulnerabilities reported. Audit tooling is disposable and is not an application dependency. Exact qualification installation was isolated at `/tmp/dw17-qualification-venv`; default application locks and packaging remain unchanged.

Commands: `uv venv /tmp/dw17-qualification-venv`; `uv pip install --python /tmp/dw17-qualification-venv/bin/python boto3 pip-audit`; `uv pip compile /tmp/dw17-sdk-requirements.txt --python-version 3.10 --generate-hashes -o docs/verification/live-environment-grounding/17-0/sdk-requirements.lock`; `/tmp/dw17-qualification-venv/bin/python -m pip_audit --disable-pip --no-deps -r /tmp/dw17-sdk-requirements.txt -f json`. The pinned input file's seven entries are the exact versions above.
