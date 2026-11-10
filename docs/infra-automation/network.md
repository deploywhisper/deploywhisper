# Infra automation restricted-network procedures — v1.5.0

The current qualified collection profile is offline Linux ARM64. It has no task
network fallback. Follow the exact [isolation qualification](../verification/infra-automation/16-13/README.md)
and [collection qualification](../verification/infra-automation/16-14/README.md)
records; another host, image, tool, provider or network needs its own qualification.
Terraform/cloud IAM/remote state and an arbitrary egress-enabled collector are not
qualified by the offline OpenTofu 1.13.1 record. These instructions are operator
preparation, not evidence that Story 16.18's installation/recovery exercise passed.

## Qualified offline task defaults

The exact immutable image/catalog/source digests come from the operator's
qualified profile, never a mutable image tag. Defaults below are limits rather
than a host-wide storage or throughput promise:

| Field | Default |
| --- | --- |
| `architecture` | arm64 |
| `docker_version` | 29.1.3 |
| `kernel_version` | 6.12.54-linuxkit |
| `network` | none |
| `work_bytes` | 67108864 |
| `tmp_bytes` | 8388608 |
| `output_bytes` | 65536 |
| `timeout_seconds` | 60 |

Task egress and DNS allowlists are empty. No provider, Git, module, registry,
metadata-service or Internet DNS request is allowed from the task. LinuxKit's
known dormant tunnel devices must remain down, addressless and without routes;
an unknown or activated device denies admission. The existing qualification
corpus checks public/metadata connection and interface-activation attempts.
Changing `network` to a bridge/host mode is not recovery. Do not add an ad hoc
proxy, DNS resolver, Docker socket or writable host cache mount to a task.

## Identify each network boundary

| Identity/process | Permitted destination policy | Credentials and limits |
| --- | --- | --- |
| Offline collection task | Empty host and DNS allowlists; network `none`. | Only the locally allowlisted collector identity after sandbox/pin verification; no receiver or ambient host credential. |
| Runner control client | The exact operator-configured HTTPS application origin. | Expiring runner/task credentials; fixed audience, scope, sequence and original lease deadline. No replacement task after ambiguous delivery. |
| Application handoff transport | The registered canonical HTTPS target API origin and exact workflow destination. Default GitHub origin is `https://api.github.com`; private origins require the explicit target transport policy. | Separate receiver/delivery identity; bounded response/timeout and current target/approval checks. Never a wildcard GitHub/cloud allowlist. |
| Trusted host image/source preparation | The operator's approved image/source/provider acquisition hosts, or removable offline media. Record exact hosts, DNS resolver and digest verification before acquisition. | Separate provisioning identity; no task runtime fetch. The repository supplies no universal download-host allowlist. |
| Receiver | Its configured authenticated application channel plus its explicitly approved external boundary. | Receiver credential audience is separate from runner and human sessions. Raw plan custody remains local. |

Enforce host egress/DNS using the deployment's firewall/proxy/resolver controls;
the application does not manage a host firewall. Record the actual allowlist,
ports, TLS trust and DNS failure behavior for the supported deployment. Do not
infer that a configured HTTPS origin proves successful TLS or network isolation.
Browser loopback HTTP evidence is not production HTTPS evidence.

## Stage pinned tools and caches offline

1. On a separately approved preparation host, acquire the exact qualified image,
   tools, providers, modules and lockfiles through the approved channel. Verify
   their independent licenses, publisher evidence and exact SHA-256 digests.
   Operators supply tools; do not bundle proprietary binaries or claim MIT
   relicensing. Save an inventory containing digest, byte size, version, source
   and license, without credential-bearing URLs.
2. Transfer the image and source inventory through protected offline media.
   Docker image export/import is a transport step, not digest verification:
   inspect the imported image ID and match the qualified immutable image ID
   before registration. A matching human-readable tag is insufficient.
3. Install an owner-controlled pinned catalog and admitted source registration.
   The catalog accepts at most 256 file pins and at most 2 tool-version entries.
   Source must be the exact immutable commit with complete tree/lockfile digests;
   clean Git-object processing does not import source hooks or network config.
   Follow [runner isolation](runner-isolation-v1.md) and
   [collection composition](collection.md) for their actual Python interfaces.
4. Put the required providers/modules and CLI configuration into the immutable
   image at their pinned catalog paths. The offline task cannot repair an
   incomplete mirror by downloading. Reject missing/mismatched pins and prepare
   a newly qualified image instead of silently widening the profile.
5. Set an operator-enforced host storage quota and per-inventory byte ceiling
   before importing tools/images. Verify the private inventory with the bounded
   verifier below. Keep a bounded number of qualified immutable versions and
   refuse imports that would exceed that ceiling. No host-wide cache quota is
   enforced by the current runner. The bounded task tmpfs/output and catalog
   entry counts are not an image-store byte quota. Remove only confirmed
   unused images under the operator's normal Docker retention procedure; never
   remove an active task's image, journal, source snapshot or custody bundle to
   regain space.
6. With acquisition-host access blocked, execute the supported disposable
   collection fixture and verify pinned tool/version, denied egress/DNS, bounded
   disk/output, screened JSON and exact local custody receipt. Record failed
   missing-cache and changed-pin cases as denials. A preinstalled image alone
   does not establish offline installation/recovery acceptance.

## Verify a private cache inventory

The read-only verifier inspects an existing owner-private, canonical directory.
It does not download, execute, install or admit tools to a runner. Keep the cache
quiesced throughout verification and subsequent image preparation: the summary
does not give a continuing lease on mutable files. Put the private pin manifest
outside the cache, since every file inside the cache must be listed.

The manifest has version 1 and a nonempty `files` array. Each item has only a
canonical relative `path`, byte `size` and algorithm-qualified `sha256`. This
synthetic one-byte example describes an ordinary file containing the byte `x`;
replace it with actual pinned inventory, not a demo tool:

```json
{
  "version": 1,
  "files": [
    {
      "path": "synthetic-fixture",
      "size": 1,
      "sha256": "sha256:2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
    }
  ]
}
```

Directories must be owned by the current user and mode 0700. Files must be
regular, single-link, current-user-owned and mode 0400, 0500, 0600 or 0700.
Symlinks, special files, changed bytes/identity/metadata, duplicate or unlisted
files and mismatched digests deny verification. The manifest itself uses the
existing protected configuration reader: a canonical protected parent and
root/current-user-owned, single-link regular mode 0400/0600 file, at most
131072 bytes. Pin the SHA-256 of its exact bytes, including whitespace.

| Verifier bound | Maximum |
| --- | ---: |
| Manifest files | 256 |
| Traversed entries, including directories | 512 |
| Bytes per file | 134217728 |
| Total listed bytes | 1073741824 |

`--max-bytes` lowers the aggregate byte ceiling and cannot raise the 1 GiB maximum.
For example, after preparing actual private paths and their exact manifest pin:

```text
./.venv/bin/python -m infra_automation.runner.cache --root /private/operator/cache --manifest /private/operator/cache-pins.json --sha256 sha256:<exact-manifest-sha256> --max-bytes 67108864
```

Success exits 0 and prints only version, verified file count, total bytes and
manifest digest. Failure exits 1 with a generic diagnostic. A successful summary
does not qualify publisher provenance, runtime image/catalog/source admission,
offline installation, host-wide storage quotas or network isolation. Preserve
those separate checks and the exact qualified profile.

## Rotate identities without widening access

Human setup/recovery/session credentials, signed trigger keys, runner enrollment,
runner credentials, task grants, collector credentials and receiver credentials
are distinct authorities. Keep real values out of this repository, browser
settings, reports, support exports and cache manifests.

Use the existing [runner API and protected-file CLI](runner-protocol-v1.md) for
enrollment/rotation/revocation. Human admin issuance requires HTTPS and CSRF.
Save issuance values once in protected owner-only files; a lost issuance reply
requires revocation and new authority, not a replay to retrieve plaintext.
Rotation invalidates the prior generation. Check current issuer membership,
profile and slot capacity; expired-credential rotation reserves capacity again.
Polling tasks consumes one-time delivery authority, so never use it as a health
probe.

For [signed triggers](triggers.md), rotate the environment-backed key and
SHA-pinned protected key-reference manifest through the operator's configuration
mechanism. Recheck the exact account/membership/restore versions and finite key
expiry. An edited shell environment does not change a running process. Pending
effects bound to old key material must fail; do not erase replay nonces or reset
clock floors. Rotate receiver and collector credentials through their separate
operator-owned integrations; neither belongs in the server's persistent settings.

During network failure, retain the original operation/request identity, stop
new effects and use authorized history/same-operation reconciliation. A timeout,
credential expiry or broken DNS cannot prove remote work stopped. Never disable
TLS checks, allow redirects, add arbitrary DNS/egress or replace a grant to make
recovery appear successful. See [operator incident recovery](operations.md).

## Acceptance and air-gap limits

The [prepared-cache exercise](../verification/infra-automation/16-18/cache-results.json)
records successful verification of a pinned OpenTofu artifact copied from the
already-local qualified image, rejection under a lowered byte limit and rejection
after tampering. It runs no tool and downloads nothing. It qualifies prepared
local artifact verification only; it does not qualify a fresh air-gapped
installation or admit the binary to a runtime profile.

Story 16.18 still needs denied egress/DNS, offline-cache installation, credential
rotation and restricted-network recovery exercises on the exact supported
deployment. The prepared-cache exercise does not close these gates. Record
source/image/tool/catalog digests, actual allowed hosts, media inventory sizes,
host-cache ceiling, firewall/DNS configuration, precise commands, timestamps,
resource samples and nonsecret results. Real credentials and saved plans remain
in protected local custody; verification records contain only summaries/digests.

These automation instructions contribute to
[Story 12.8](../../_bmad-output/implementation-artifacts/12-8-air-gapped-and-restricted-network-guide.md).
They do not close its full offline core installation/analysis acceptance.
Optional external LLMs, registries, connectors and updates have separate network
requirements; deterministic local analysis must be exercised independently with
those services unavailable. Do not claim universal air-gap support or a complete
production runner/receiver qualification from fixture tests.
