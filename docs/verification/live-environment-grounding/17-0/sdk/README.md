# Disposable AWS SDK trust-boundary qualification

This is an offline prototype, not a product connector. It imports the real botocore1.44.1 model and credential resolver, validates SDK-shaped requests with Stubber and forbids live socket creation in the network-sensitive tests. Synthetic ambient credentials are only test canaries. No real credentials, cloud calls, product dependency changes or new product capability are introduced.

## Frozen credential disposition

Default credential mechanism: ambient environment only. A trusted operator may opt into an explicitly selected shared-credentials file/profile; project request configuration accepts only the bounded canonical region. Missing allowed credentials fails closed without trying host roles. IMDS, container endpoints, credential_process, role chains, SSO, login and web identity are removed before credential resolution in this qualified prototype. SSO/IRSA/dedicated instance roles need separately scoped qualification before admission; no unqualified mechanism is silently enabled. The ambient-only requirement means no credentials are accepted in project requests or persisted by DeployWhisper. It does not require enabling every SDK mechanism.

The real SDK test exposed an unsafe assumption: `set_config_variable("profile", None)` still allowed `AWS_PROFILE` to select an environment profile. The final implementation replaces the version-specific ConfigStore profile provider with a constant trusted value before constructing the resolver. This is an internal botocore surface: exact SDK pinning and rerunning these tests is required on upgrade. Both empty credentials and hostile profile/endpoint/proxy/CA environment cases are covered.

A further regression demonstrated that the default SDK Loader searches `AWS_DATA_PATH` and `~/.aws/models` before package metadata. The final probe registers a Loader restricted to the resolved installed botocore package data directory with `include_default_search_paths=False`. A real-format malicious EC2 service model and endpoint metadata in both untrusted directories are ignored; the canonical EC2 endpoint remains unchanged. Loader/component registration and package layout are also pinned SDK implementation surfaces requiring upgrade requalification.

## Exact request and transport disposition

Validate action membership before constructing clients. Permit only explicit nonempty physical instance IDs; reject arbitrary filters, missing scope, pagination tokens and unlisted read/mutating actions. A bounded manifest lists exactly the requests that are intended; do not build followup calls from response discovery. A continuation token produces incomplete evidence rather than hidden pagination. Full feature coverage and one-hop responses are defined by the main Story17.0 coverage contract, not this one-action probe.

Use provider-canonical HTTPS endpoints with `ignore_configured_endpoint_urls=True`, TLS verification explicitly enabled, no environment proxy inheritance, one total attempt, and one-second connect/read timeouts. These tests prove SDK configuration and modeled request behavior; they do not qualify real DNS, network latency, IAM or AWS account behavior. A live timeout may include connection and response phases; total-deadline authority belongs to the bounded collector rather than to this isolated single-call test.

Provider error messages, request IDs and raw responses are not serialized: the probe emits a fixed status, known cause category and required permission. Successful results project only instance count; raw attributes are discarded. Existing product redaction remains the product-owned boundary, with separate synthetic redaction proof in the earlier spike.

The final SDK suite contains eleven passing checks.

## Reproduce

```sh
/tmp/dw17-qualification-venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/sdk -v
./.venv/bin/ruff check docs/verification/live-environment-grounding/17-0/sdk
./.venv/bin/ruff format --check docs/verification/live-environment-grounding/17-0/sdk
./.venv/bin/bandit -r docs/verification/live-environment-grounding/17-0/sdk --severity-level medium --confidence-level medium
```

The disposable environment requires the approved boto3 qualification version set recorded by the main packet. Its absolute temporary path is a local reproduction example, not a runtime dependency path.
