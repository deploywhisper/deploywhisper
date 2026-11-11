# Bounded offline application installation and recovery exercise

Executed 2026-11-10 against immutable image
`sha256:363f797bb98e1ca90f549892b28802d6589000e776505a6f21cefdc7e61c41df`.
Outcome: **passed**. Full commands, package/layer hashes, versions, network
observations, 28 CLI/API checks and cleanup receipts are in
[offline-install-results.json](offline-install-results.json).

This establishes a complete transport archive and a fresh application/state
installation on an **already installed Docker host**. The daemon already held
the image layers. It does not establish a cold Docker cache, bare-machine
installation, offline operating-system/Docker installation or independent human
adoption.

## Complete archive, independent content verification and local load

The existing Docker 29.1.3 daemon saved the pinned image into an owner-only
temporary directory. Before writing, the exercise checked image size and free
disk, reserved a 512 MiB margin beyond the explicit **2 GiB package ceiling**,
and enforced that ceiling while streaming. The published archive was mode 0400.

| Observation | Actual result |
| --- | --- |
| Image size reported before save | 219,647,946 bytes |
| Archive size | 229,869,568 bytes |
| Archive SHA-256 | `09a59258d77facf0c4a645d1093c960b9719945e776907f22169aa66aa9277e2` |
| Config identity | Exact pinned image ID |
| Configured layers | All 21 present, exact sizes and digests verified |
| Uncompressed layer identity | Every layer matched the corresponding ordered `config.rootfs.diff_ids` entry and the inspected image layer list |
| Local load | Exit 0; loaded image ID remained identical |
| Registry pulls/new tools/dependencies | None |

The verifier streamed the archive hash and independently re-read it. It enforced
canonical unique outer member paths, regular-file/directory types, metadata size
bounds and complete member lengths. Every actual member passed these checks;
no malicious-archive corpus is claimed. It read tar members without extracting
them, checked content-addressed blob names against their bytes, verified the
config digest against the pinned image ID, and verified every configured layer.
Layer decompression also had an aggregate 2 GiB ceiling. Detailed per-layer
archive/uncompressed sizes, encodings and SHA-256 values are retained in JSON.

The relevant commands were:

```text
docker image save sha256:363f797bb98e1ca90f549892b28802d6589000e776505a6f21cefdc7e61c41df
docker image load --input PRIVATE_PINNED_IMAGE_ARCHIVE
docker image inspect sha256:363f797bb98e1ca90f549892b28802d6589000e776505a6f21cefdc7e61c41df
```

The already cached daemon layers mean this is not proof that `docker load`
populated an empty daemon. Archive completeness was independently established
from the transported bytes rather than inferred from the successful load.

## Fresh installation with no external network

Fresh named volumes separated the database/artifacts/custody domain, outside
control ledger, backup location and private operator credential files. Container
execution used `--pull=never --network none`, with no host port publication or
host application directory mounts. The runtime identity was UID **999**.
Private roots were mode 0700; files were mode 0400/0600. APIs were called only by
`docker exec` into the new app container at `http://localhost:8080`, matching its
explicit `local-development` identity origin.

Real migrations initialized schema **042**. Before explicit bootstrap, accounts,
sessions, memberships and enabled policies were all **zero**. The pinned image
therefore introduced no default account or implicit execution authority.

Actual namespace observations were:

- Docker network mode `none`, no UP non-loopback interface and no non-loopback
  IPv4 or IPv6 route.
- `example.com` DNS resolution was denied within the bounded probe.
- IPv4 TCP egress to `1.1.1.1:443` and IPv6 TCP egress to
  `[2606:4700:4700::1111]:443` both failed with errno 101, network unreachable.
- Only the container's own loopback HTTP origin was allowed. No host port 8080
  or 18080 was bound or used by the exercise.
- Configured provider/connector credential count was zero.

LinuxKit exposes dormant built-in GRE/tunnel interfaces in this namespace. They
were DOWN and had no routes. The first fixture attempt incorrectly required the
interface list to contain only `lo`; the final checks verify actual UP flags,
routes and denied traffic while retaining the dormant-device inventory. No
product code or network profile was changed to pass the exercise.

## Actual CLI/API bootstrap and recovery results

All 28 normal operator checks passed inside the restricted namespace:

1. The actual CLI issued a one-use setup credential and bootstrapped the first
   synthetic administrator through private files. Explicit API project
   membership was still required; policy was saved with execution disabled.
2. CLI account recovery rotated the synthetic password, advanced authentication
   version 2 → 3 and revoked old sessions. The old HTTP session returned 401;
   fresh login succeeded and live WAL/SHM descriptors remained valid.
3. Backup refused while the app held its shared lifecycle lock. After shutdown,
   the coordinated database/artifact/custody backup succeeded.
4. Restore reserved generation **4** and entered `reconciliation_required`.
   The previous session returned 401; fresh login and authorized historical
   reads returned 200. One actual settings audit event retained its exact digest.
   Run history was empty; no external operation was fabricated.
5. Attempted re-enable returned 503. Fresh global/project administrative
   authority completed recovery through the private CLI after app shutdown;
   policy remained disabled on restart.
6. Restoring the identical snapshot again reserved generation **5**. The prior
   ready session returned 401 and fresh login succeeded. Final schema was 042,
   integrity was `ok`, foreign-key violations were zero, and synthetic custody
   bytes retained their exact digest.

Every one of the **209 packaged runtime/source files** independently matched the
frozen root. The 210-file source inventory includes the generated TypeScript
contract, a static frontend build input intentionally absent from the runtime
filesystem. Its source hash is retained separately.

All created containers, four named volumes, private credential files and the
private image archive were removed. The original application and all unrelated
containers/volumes were preserved. No product source, dependency, tool version or
permission setting changed during this exercise.

## Acceptance boundary

This closes the prepared-cache-only evidence gap for the bounded application
image archive/load and fresh local state on this preinstalled Docker profile.
It supplements the [operator procedure proof](operator-exercise.md)
and [restricted-network contract](../../../infra-automation/network.md).

The custody/artifact files and all human credentials were disposable synthetic
inputs. No real saved plan/state, infrastructure operation, receiver/runner/provider
credential, remote collector, provider-cache acquisition, production HTTPS
deployment or host-power-loss event was exercised. The daemon's cold-cache
behavior, operating-system/Docker/dependency installation, other tool/provider
profiles and independent human pilot remain unqualified. Original Story 12.8's
broader offline installation/core-analysis and optional-integration acceptance
is not closed by this bounded result.
