# Additional DNS denial observation

The [machine-readable record](network-results.json) records an actual DNS lookup
on 2026-11-10 from a host-controlled observation process in an already-admitted
qualified offline task container. It adds DNS evidence to the existing
[16.13 IP-egress/namespace qualification](../16-13/README.md); it does not replace
that corpus or qualify another image, profile, collector command or network.

## Actual execution and result

The temporary host orchestrator ran:

```text
./.venv/bin/python /tmp/dw16-18-dns-observation.py
```

It reused `scripts.qualify_runner_isolation` image/source helpers without
building/downloading anything. `ExecutionRunner` admitted and started the
existing pinned `qualification_probe` command in its `descendants` mode, using
the protected source registration, catalog, real `DockerSandbox` and two-phase
bootstrap. The credential resolver supplied an empty environment: no provider,
server, receiver or collector secret was supplied. The pinned task stayed alive
while the operator observed it; no source/image/catalog/profile was edited.

The operator used the sandbox's bounded Docker control channel to run one fixed
Python observation with UID/GID 10001. Its only network request was:

```python
socket.getaddrinfo("example.com", 443, type=socket.SOCK_STREAM)
```

The real hostname avoids a deliberately nonexistent test domain. An eight-second
signal deadline and the bounded control-command timeout limited the observation;
neither deadline had to fire. The actual resolver raised `socket.gaierror` with
errno **-3 (`EAI_AGAIN`)** in **0.009907166 seconds**. It returned no addresses.
The inspected container used network `none`; the observed IPv4 routing table had
no route entries. The resolver configuration is retained only as its digest.
No DNS mock, replacement resolver, host firewall change, new mount or network
profile was used.

The controller then requested cancellation through `ExecutionRunner.cancel`.
The production journal and cleanup path completed with state `cancelled`, no
output digest/collection, `cleanup_complete: true`, and the exact owned container
was absent from Docker afterward. Other containers and port 8080 were untouched.

## Exact identity and source integrity

| Identity | Observed value |
| --- | --- |
| Image | `sha256:49a6523abb3867631692d3ac1ebf09cfe02a21c0725ae2039859703289988875` |
| Catalog | `sha256:bfe87ec0126558fc0e1473cccb7d4543d939f9b34631c4a1251032ec133628c6` |
| Execution profile | `sha256:c7bc6344d718256431ac9c79df03d582e9e0b29b44a905e0bdc3a1ee1970a7eb` |
| Synthetic source commit | `4235ea38cc4ac4ceef4a3a8299d3144b62a407b1` |
| Source digest | `sha256:15c2dc831ffe59640c71bf6b3c78818679f9ca393829b33ab6e984246d4083b4` |
| Platform | Docker 29.1.3, Linux ARM64, qualified LinuxKit 6.12.54 profile |

The source, catalog and profile IDs exactly match the retained `cancel-descendants`
case in the current passing 16.13 record. All 23 retained source hashes match the
measured start hashes, and start/end hashes are unchanged. The record includes
the complete profile/inspected controls, exact observation code, orchestrator
digest, command, timestamps and cleanup facts. The initial temporary adapter
attempt failed before container creation because a strict tuple field was loaded
as a Python list; using the actual JSON model loader corrected that host adapter
without changing profile bytes or admission.

## Security and proof limits

The observation process joins the container's network/mount/cgroup boundary and
retains OCI controls: actual UID/GID 10001, zero effective capabilities,
no-new-privileges and seccomp mode 2. Docker exec does **not** inherit the pinned
PID1 bootstrap's additional per-process scheduling seccomp filter; the observed
process reported one filter. Therefore this is an additional read-only namespace
observation, not an admitted collector command or evidence that arbitrary exec
has the full bootstrap-child security context. The pinned qualification task
continued under its unchanged production bootstrap/profile.

The observation's network namespace inode was 4026533696. Access to PID1's
namespace identity was denied by the existing protections; no permission was
relaxed to obtain it. The result does not claim a successful inode comparison.
Container network mode and the operator's explicit exec target identify the
observed boundary.

This proves the named lookup failed within its bound in this exact offline
container. It does not qualify universal DNS filtering, a remote network,
air-gapped installation from new media, cloud IAM, provider credentials, a live
receiver recovery, or host-power-loss durability. IP/metadata egress, dormant
device checks and actual pinned collector execution retain their separate
current 16.13/16.14 qualification records. Story 16.18's remaining operational
pilot and network-recovery gates must be evaluated independently.
