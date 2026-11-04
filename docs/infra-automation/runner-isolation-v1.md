# Isolated runner execution profile v1

Story 16.13 supplies an operator-owned isolation boundary and a real hostile-command qualification corpus. It keeps the web application, outbound runner protocol and future production collector separate. The application never receives a Docker socket, arbitrary command or infrastructure credential. The standard runner handler remains unavailable until Story 16.14 integrates and qualifies collection.

## Supported profile and trust boundary

The initial profile is offline Linux ARM64 containers on Docker Engine 29.1.3 and LinuxKit kernel `6.12.54-linuxkit`, with cgroup v2, Docker's built-in seccomp policy and the pinned qualification image. Exact image, source, catalog and executable hashes, limits and observations are recorded in the [qualification record](../verification/infra-automation/16-13/README.md) and [machine-readable results](../verification/infra-automation/16-13/results.json). Other OS/architecture/daemon/kernel/image or network combinations require separate reviewed qualification; there is no unrestricted local fallback.

The observed enforcement host is Docker Desktop's Linux VM. The macOS process controlling that VM is not a native macOS sandbox. The host Python, Git, Docker client and operator configuration are trusted control-plane components. Containers are not a universal defense against a compromised host, daemon or kernel.

Only the separately configured host launcher may use a canonical local Unix Docker endpoint. It ignores ambient Docker contexts, proxy/configuration variables and credential helpers. The task uses UID/GID 10001, a read-only root, an exact read-only source bind, bounded private work/temp tmpfs, no capabilities, no-new-privileges, private namespaces and no network. Docker logging is disabled. No task/app mount exposes the daemon socket, receiver custody or receiver credentials.

LinuxKit creates a fixed set of dormant tunnel devices even in a `none` network. Admission checks the process network namespace: those devices must be down, addressless and without non-loopback egress routes. Unknown or activated devices deny admission. Actual metadata/public-network connection and interface-activation attempts are part of qualification.

## Protected source and catalog

`load_registration(path, expected_digest)` and `load_catalog(path, expected_digest)` require canonical operator-owned regular files with mode 0400/0600, no links and an independently supplied expected SHA-256. A caller-provided `protected_revision` label is not authority. Source snapshots must come from the protected registration loader and materializer; directly constructed snapshots are rejected.

A source registration binds a local protected repository, exact 40-hex commit, complete file-tree digest and explicit lockfile digests. Materialization copies bounded Git object bytes into a private clean Git directory. It never loads the original hooks, config, aliases, helpers, alternates or promisor configuration. Git only reads exact object identities with replacement/lazy fetching and network protocols disabled. Source paths, links, hardlinks, special files, unsupported dependencies and changed registrations deny before credentials resolve.

Limits are explicit: source at most 256 files / 8 MiB, protected object store at most 64 MiB, bounded traversals and a shared checkout time budget. Terraform/OpenTofu configuration files (`.tf`, `.tf.json`, `.tofu` and `.tofu.json`) are at most 128 KiB each and are parsed in a resource-limited fixed subprocess, not evaluated. Only literal contained vendored module sources are supported; their bytes are pinned by the complete tree digest. Remote or expression-based module sources are unsupported. Linux subprocess address-space limits are additional to input/CPU/wall bounds; no native macOS memory sandbox is claimed.

The catalog pins the immutable image and exact tool/provider/module/lock/probe files. Its command registry is closed: `qualification_probe` and `tool_version`, with enumerated qualification modes. It accepts no executable path, shell, arbitrary flags, installation request or server-defined command. Build-time pinned fixture downloads do not permit runtime fetching. The provider probe script is an internal external-provider helper requiring JSON input; it is not an advertised standalone command. Production collector commands are a later owning-story change.

Staging must be owned by the current operator with exact mode 0700. A private internal envelope protects the container-readable 0555/0444 source tree even if the caller changes its parent permissions. Held directory descriptors and device/inode checks anchor creation, publication, verification and cleanup.

The source materializer returns a sealed `SourceSnapshot`. The caller owns its lifetime and should use its context manager or `close()` after all dependent tasks finish. Cleanup is bounded and descriptor/inode anchored; it does not follow replacement links or delete another root. `ExecutionRunner` does not silently delete a caller-owned reusable snapshot.

## Execution and credential delivery

The host constructs `DockerSandbox` and `ExecutionRunner` from protected local configuration. Each `execute` call requires:

- The authenticated current task's `TaskScope`, a fixed command ID and closed parameters.
- A factory-created admitted `SourceSnapshot`.
- `expected_profile_digest`, matching the canonical digest of the complete local profile and protected catalog digest. A future collector bridge must compare the server-selected runner message's profile digest; computing a local hash is not independent server authorization.
- Trusted bounded authority/cancellation callbacks and an operator-local collector credential resolver.

The same created task container performs a two-phase handshake. Its fixed, pinned bootstrap first verifies actual UID, capabilities, no-new-privileges, seccomp, cgroup limits, mounts, network and source/tool pins. The host resolves credentials only after the exact readiness marker and fresh source/catalog/authority checks. Protected configuration is limited to 128 KiB; the nonsecret handshake is limited to 64 KiB and the credential frame to 16 KiB. Values travel through stdin, never Docker argv, environment metadata, server messages or the journal. The child receives a fixed environment plus the explicit collector-only allow-list; receiver and ambient host variables are excluded.

The current profile uses the synthetic `COLLECTOR_TOKEN` identity to qualify the boundary. Actual infrastructure IAM permissions and provider/custody integration remain Story 16.14/release obligations. No synthetic value or successful connection proves real least-privilege cloud access.

## Lifetime, cancellation and evidence

The host supervisor bounds callbacks, output, time, original task lease and cleanup. The private bootstrap frame carries the original absolute execution deadline and remaining monotonic budget. Setup, validation and frame-delivery time consume that same budget. The fixed in-container PID1 watchdog independently enforces the original execution/lease deadline if the host controller dies; it never starts a fresh full timeout. It is non-dumpable and applies an additional restrictive seccomp filter to prevent task descendants from changing watchdog scheduling/affinity or process memory. The inherited Docker seccomp policy remains active. Exiting PID1 terminates the owned PID namespace, including descendants that created separate sessions.

The private local SQLite journal records task/profile identity and an ownership nonce, never credentials or raw output. Cancellation is durable before termination; finalization performs a reserved transactional cancellation/deadline check. Cancellation or expiry during output processing, inspection, cleanup or journal contention cannot produce finalizable evidence. A late cancellation cannot rewrite terminal success. Task identity excludes the mutable lease deadline, so renewal cannot create a second local execution or make cancellation miss the original attempt. This slice does not extend a running container's captured lease from a cached callback result.

Cleanup uses immutable container IDs and verified ownership nonces, including ambiguous create failures and restart recovery. A name collision never authorizes removing someone else's container. Unacknowledged creation stays pending after empty or foreign-name lookups: a late daemon completion is still possible. The private journal retains the ownership nonce and, once observed, the immutable acknowledged container ID; its additive schema upgrade does not turn legacy uncertainty into successful cleanup. Confirmed absence of that acknowledged ID can be reconciled safely. Unavailable or inconsistent owned-container state remains pending/cleanup-failed; it is not reported as successfully stopped. A failed kill is rechecked against that exact ID so natural exit can be cleaned up without ignoring a still-running or unverifiable container. Startup recovery stops retained owned work rather than resuming execution. It does not reconcile or unlock external handoffs.

Only complete, successful, screened output from a fully cleaned-up execution has an output digest and `finalizable=True`. Output overflow, partial writes, nonzero exit, cancellation, expiry, resource failure or uncertain cleanup yield no finalizable output. Whole bounded output is screened together, including the known credential corpus and bounded URL encodings across chunk boundaries. This is measured screening, not a universal secrecy guarantee against arbitrary obfuscation; trusted source admission and the offline boundary remain necessary.

## Verification

Run the real corpus with:

```sh
./.venv/bin/python scripts/qualify_runner_isolation.py --build
```

This builds a separate pinned qualification image and exercises the production source/catalog/launcher/lifetime paths. It uses synthetic source and credentials only. Partial `--case` diagnostics cannot qualify the full corpus. Fresh results must match the current bootstrap/probe bytes and stable isolation source hashes. The frozen Story 16.0 records remain unchanged.

The unit suites cover admission failures, controlled subprocess timeouts, catalog/path substitution, container ownership and finalization races. They are complementary to actual Linux containment/resource/network/provider/process-death evidence, not substitutes for it. No web UI changed; browser validation is not applicable.

Implementation references: [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/), [Docker seccomp](https://docs.docker.com/engine/security/seccomp/), [Docker network none](https://docs.docker.com/engine/network/drivers/none/), [Linux seccomp filters](https://docs.kernel.org/userspace-api/seccomp_filter.html), and [Git archive configuration](https://git-scm.com/docs/git-archive). The clean-object checkout deliberately avoids configurable archive shell commands.
