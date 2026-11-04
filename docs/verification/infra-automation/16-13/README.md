# Story 16.13 real isolation qualification

This corpus executes the production `SourceRegistration` loader, immutable source materializer, protected catalog, `DockerSandbox` and `ExecutionRunner`. Docker builds the pinned fixture image; no `docker run` or `docker exec` shortcut executes a task. Read-only Docker inspection observes controls and process trees.

Final run after the review repairs: **passed at 2026-11-04T10:11:21.728473+00:00** — 19 real task cases, three abrupt-controller-death/recovery cases, 17 admission cases and all 172 assertions. Host source hashes remained unchanged; all seven built-image source-pin comparisons match the current bootstrap and fixture bytes. The qualified image is `sha256:49a6523abb3867631692d3ac1ebf09cfe02a21c0725ae2039859703289988875`, catalog `sha256:e76db2a6ff049a3c66d2e29922da0cbb42090a5407af3d80508fc0da785c251b`, synthetic source commit `4235ea38cc4ac4ceef4a3a8299d3144b62a407b1`. See [complete observed results](results.json) and [pinned build definition](../../../../tests/fixtures/infra_automation/qualification/16_13/Dockerfile).

The image runs Python 3.11.17, OpenTofu 1.13.1 and external provider 2.3.5. The exact qualified daemon is Docker 29.1.3 on Linux ARM64 kernel `6.12.54-linuxkit`; the host control process used Python 3.14.3. All three operator-death runs observed exit 124 without a live host supervisor and subsequent production journal recovery; all owned containers were removed.

The delayed-setup case uses a 6-second timeout, a 3-second create delay and a 60-second lease. It resolved the synthetic credential once and observed actual descendants before killing the controller at t+3.806s. Container stop was observed at t+6.092s, inside the original 6-second budget plus the declared 0.75s observation tolerance. Time is anchored at host `execute` entry before setup, never restarted at controller death. The [original failed reproduction](review-deadline-repro.json), which ran until t+9.50s, remains unchanged historical evidence.

Post-run integrity checks: `./.venv/bin/python -m pytest tests/test_infra_automation/test_runner_isolation_qualification.py -q --tb=short` → **6 passed, 26 subtests passed**. Scoped Ruff and repository-wide formatting passed (532 files); `git diff --check` passed. The strengthened integrity guard rejected the obsolete pre-review artifact before passing against this complete real qualification record. Full repository CI belongs to the parent story completion record.

## Reproduce

```sh
./.venv/bin/python scripts/qualify_runner_isolation.py --build
```

The advertised catalog commands are `qualification_probe` and `tool_version`; both have successful real end-to-end evidence. `provider_probe.py` remains the internal helper invoked by the external provider during the fixed plan case, and is no longer an advertised standalone command.

The fixture build downloads the exact pinned OpenTofu image and external-provider package at build time. Both executable SHA-256 values must match before the build completes. The committed provider lockfile supplies exact package checksums. Runtime launches use the resulting immutable local image ID with pulling disabled and a read-only provider mirror; tasks cannot fetch tools, providers or modules. There are no remote modules in this corpus.

Base identities:

- Python image: `python@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89`.
- OpenTofu image: `ghcr.io/opentofu/opentofu@sha256:dfbc3f0a8bed0adfa2cf49ff418f158afe24080eea6d6e748db8799fc4553db6`.
- OpenTofu 1.13.1 executable: `d5c690023baebe8bf2cfb2062e292186f4797a173db22c973bd9de45cb68a62f`.
- `hashicorp/external` 2.3.5 Linux ARM64 executable: `f9994ee228b86d34c289d858af46f758921f34393a27a1bb5677761c08228f50`.

The separate 16.13 fixture preserves all frozen 16.0 artifacts. It installs no cryptography/custody dependency. The build copies the pinned Python interpreter to a regular file at the fixed catalog path, so no-follow verification does not follow the base image's interpreter symlink.

## Declared environment and boundaries

Only the exercised offline Linux ARM64 container profile is eligible for qualification. Docker Desktop's LinuxKit VM is the Linux enforcement host; the macOS control process is not a native macOS sandbox. Docker Engine 29.1.3, LinuxKit kernel, image identity, source commit, file pins, profile limits, observed controls and versions are retained in `results.json`. A successful container launch or connectivity observation is insufficient: every named assertion must pass.

The operator launcher alone accesses its explicit local Docker endpoint. Neither the app nor task mounts a Docker socket. Task credentials are synthetic, allowlisted collector-only values delivered through the two-phase private stdin channel after readiness. The corpus asserts no values in Docker metadata or the durable journal, and checks that host and receiver sentinels do not reach the task/provider process.

This does not qualify production collection/custody integration, real infrastructure credentials, an additional network, alternate OS/architecture/daemon/kernel combinations or universal provider safety. Story 16.14 and release qualification retain those obligations. UI validation is not applicable.

## Corpus and proof obligations

| Boundary | Concrete evidence |
| --- | --- |
| Identity and containment | Actual UID/GID 10001, zero capabilities, seccomp mode 2, no-new-privileges, read-only root/source/catalog, no socket, exact inspected mounts |
| Source/catalog | Real Git object materialization with hostile hooks/config/helpers ignored; untrusted source and option injection denied; snapshot symlink escape and catalog replacement rejected; `.tofu`/`.tofu.json` escaping, remote and oversized configurations rejected before credential resolution; 0755 staging rejected without publishing source |
| Tools/provider | Actual OpenTofu plan invokes pinned external provider and its child Python probe; a contained `.tofu` module with `.tofu.json` child executes successfully; tool-version command returns 1.13.1; only screened facts and digests leave the container |
| Credentials | Collector presence, absent inherited host/receiver values, wrong identity/environment denied, corrupt image pin and unsupported profile denied before credential resolution |
| Network | Actual namespace interfaces, address/route absence, denied metadata and public egress; default LinuxKit tunnel devices require explicit dormant/addressless checks |
| Resources | CPU quota and observed throttling; OOM state; PID creation failure; tmpfs ENOSPC and partial-file removal; finite-writer output overflow |
| Lifetime | Observed child/grandchild with a distinct session before cancellation, timeout and lease loss; durable cancellation before kill, stopped container and bounded removal |
| Publication | Failure/limit/cancel output has no digest and is not finalizable; cancellation during final cleanup wins over successful process exit |
| Cleanup | No owned container remains, protected source snapshots close through their production API, journal contains only scoped hashes/statuses |

`--case NAME` is an exploratory diagnostic selector and cannot qualify the full corpus. The harness exits unsuccessfully unless all complete-corpus assertions, source stability and cleanup checks pass. `results.json` remains the authoritative actual result; this document does not replace a failed gate with prose.

## Independent deadline after operator failure

The fixed in-image PID1 watchdog retains the original wall/lease deadline even if the host supervisor dies. The corpus SIGKILLs a separate host controller only after observing the real task and descendants. It then requires autonomous container exit 124 within the original execution budget before journal recovery removes the owned container. A second case repeats this with six CPU-busy descendants in separate sessions; a third delays creation by three seconds and uses a long lease so the lease cannot mask a restarted execution timeout. Recovery records `interrupted` with cancellation requested and cleanup complete; it does not manufacture a successful collection result.

The child probe attempts SIGSTOP/SIGKILL against namespace PID1, reads `/proc/1/mem`, tries ptrace, and tries changing PID1 priority, scheduling policy and affinity. The qualified profile retains Docker's built-in seccomp filter and installs an additional ARM64 filter before credential resolution. Actual child/provider evidence must show at least two filters and EPERM for the scheduling attacks. The watchdog remains non-dumpable. These are bounded tests of this exact kernel/profile, not a promise against kernel vulnerabilities.

## Evidence drift guard

`tests/test_infra_automation/test_runner_isolation_qualification.py` checks the committed complete passing record, all three operator-death results, the delayed-setup original-deadline bound, new precredential admission cases and usable advertised commands, the six isolation-core module hashes and actual image pins against current bootstrap/fixture bytes. It deliberately does **not** execute Docker or claim live qualification in CI. Isolation-core or pinned fixture changes require a fresh real `--build` qualification run and reviewed evidence. Merely refreshing hashes cannot satisfy the qualification workflow.

## Review evidence boundaries and qualification retries

The ambiguous-create repair (R4) is verified with controlled transport/fault-double tests exercising the production reservation, durable journal and recovery paths. A natural late-commit race inside the Docker daemon was not reproduced; `results.json` explicitly records that limit. The normal real-container scenarios do not silently stand in for this missing daemon-timing proof. See the parent review-fix record for those unit commands and results.

The stricter watchdog can expire before the host issues a kill. For that path, the corpus requires actual exit124, the original-deadline bound, durable timeout/cancellation before host removal and no finalizable output. Explicit cancellation and authority-loss cases still require durable intent before the host kill. A first revised attempt failed the old kill-only observation; the observer was corrected to distinguish these real stop paths, without weakening timeout or cleanup requirements.

Subsequent actual runs exposed two runtime edges that were repaired and reverified: a natural exit racing Docker kill left cleanup incomplete, and a post-exit callback check mislabeled an execution timeout as lease loss. Their failed observations were preserved in separate session artifacts and supplied to the story owner; the final artifact has no failed assertions and no remaining owned containers. The original review deadline failure artifact is preserved separately and has not been rewritten.
