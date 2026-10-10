# WP4 real-tool Linux containment qualification

Status: **passed for the declared bounded profile** on 2026-10-09. Responsible contributor: Codex `real_linux_qualification`; maintainer authorized assembling the disposable profile while accepting RFC 0001. Earlier daemon/tool-availability blockers are superseded by the actual execution below.

The frozen [profile manifest](../../../../tests/fixtures/infra_automation/qualification/16_0/isolation/profile.json) has SHA-256 `1f91ca01dcfce0a06b6ab19cba7f145dae499a551608f0cdc8386c25dd1cbf49`. Its image ID is `sha256:b8fa3e7b352fbc56a53d027c5c2ca25ffa82b5021891e6efcc6580e64f9d1d04`. Only Linux ARM64, OpenTofu **1.13.1** and `hashicorp/external` **2.3.5** were qualified. Other architectures/tools/profiles require separate evidence; runtime resolves and pins the actual image ID, rejects a differing image identity or unsupported profile schema, and verifies frozen catalog/source/control values.

The Python 3.11 base and OpenTofu image are pinned by immutable registry digests in the Dockerfile. The isolated image installs the application's existing cryptography 50.0.2 dependency without changing app requirements. OpenTofu online `init` reported the provider signed with key `0C0AF313E5FD9F80`; `providers mirror` reported authenticated signed package. This records the tool's verification outcome, not independent out-of-band signer authentication. The provider executable SHA-256 is frozen and checked during qualification. Build-time network access prepares the trusted catalog; runtime initialization and planning use only its immutable filesystem mirror.

Actual `tofu plan` used built-in `terraform_data` and the pinned external provider, which executed the owned synthetic Python attack probe. No apply, destroy, real cloud provider or credential was used. The admitted synthetic Git revision is `cbc55062de7730dd19694c418b5f9e9ff03ee223`; its content hash is verified against the executed image source. Untrusted PRs, symbolic source paths, traversal, non-hex/unpinned revisions and catalog/argv substitutions reject. Hostile inherited Git config is ignored by an explicit Git environment, disabled hooks and fixed config; a real symlink fixture and malformed global-config fixture exercise those failures.

The staging and custody stores are each bounded **8 MiB** local-driver tmpfs, retained across receiver-container restart by a non-root lifecycle anchor. Both stores hit full storage in actual probes, removed their partial upload, and preserved the original plan for subsequent verification. Host power-loss persistence is outside this ephemeral qualification.

The collector runs as UID/GID **10001**, receiver as **10002**, with all capabilities dropped, no-new-privileges, kernel Seccomp mode 2, a read-only root, private noexec/nosuid/nodev tmpfs, and no host bind mounts, sockets, application DB/artifacts or credential stores. Actual external-provider checks verified zero effective capabilities, seccomp, no-new-privileges and immutable catalog. A synthetic host secret sentinel was absent from the exact tool environment. Network `none` blocked internet and metadata connections; a separate unique internal-only Docker network allowed the declared local sink while internet and metadata remained denied.

Executable resource results: 0.5 CPU quota visibly throttled; 64 MiB negative-memory task was OOM-killed (137); 16-process limit denied further fork; 16 MiB disk task hit full storage and removed its partial file; observed 64 KiB output cutoff and one-second task deadline stopped tasks (124). Cancel, timeout and lease-loss triggers each killed the whole container with two observed processes, exit 137. The private output monitor polls every 20 ms, so transient private buffered bytes may exceed its cutoff before kill; retained readback is capped at 64 KiB. These are bounded harness triggers, not proof of an integrated production coordinator or workload capacity.

Initial real planning failed because initialization placed an executable provider in the noexec workspace. The repaired profile preinstalls an unpacked immutable provider in the image; the workspace remains noexec. No isolation control was weakened to obtain a pass. Results and exact digests are in [wp4-containment-results.json](wp4-containment-results.json).

Reproduce with the retained local qualified image:

```sh
DW16_REAL_LINUX=1 ./.venv/bin/python -m pytest tests/test_infra/test_infra_automation_real_linux_qualification.py -q
```

Observed result: **3 passed, 6 subtests passed**, exit 0. To assemble the declared image before qualification:

```sh
docker build -f tests/fixtures/infra_automation/qualification/16_0/isolation/Dockerfile -t dw16-qualification:1 tests/fixtures/infra_automation/qualification/16_0
```

A fresh rebuild that changes the resulting image identity must undergo catalog/source/config review and update the qualified manifest before acceptance; the harness fails closed rather than silently admitting it. Each run creates a UUID-scoped disposable pair of volumes, task containers and optional internal network, then removes only those owned resources. Binary plan/state never leave those private resources. The local qualified image is retained for independent review; existing app containers/images/data were untouched.

Host/daemon/DB administrators, the receiver's own OS identity and kernel compromise remain trusted/outside this boundary. This is one synthetic non-root Linux qualification, not production certification, universal redaction proof, or a delivered runner.
