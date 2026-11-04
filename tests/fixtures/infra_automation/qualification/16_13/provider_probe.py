"""Synthetic external provider child: reports containment booleans, never secrets."""

from __future__ import annotations

import json
import errno
import fcntl
import struct
import os
from pathlib import Path
import socket
import sys


def evidence():
    fields = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    result = {
        "uid": os.getuid(),
        "gid": os.getgid(),
        "seccomp_enforced": fields["Seccomp"].strip() == "2",
        "seccomp_filter_count": int(fields["Seccomp_filters"].strip()),
        "no_new_privileges": fields["NoNewPrivs"].strip() == "1",
        "capabilities_dropped": int(fields["CapEff"].strip(), 16) == 0,
        "host_secret_absent": "QUALIFICATION_HOST_SECRET" not in os.environ,
        "receiver_secret_absent": "RECEIVER_API_TOKEN" not in os.environ,
        "git_config_absent": not any(key.startswith("GIT_") for key in os.environ),
        "collector_present": "COLLECTOR_TOKEN" in os.environ,
        "socket_absent": not any(
            Path(path).exists() for path in ("/var/run/docker.sock", "/run/docker.sock")
        ),
    }
    interfaces = sorted(name for _, name in socket.if_nameindex())
    flags = {}
    addressed = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        for name in interfaces:
            request = struct.pack("256s", name.encode()[:15])
            flags[name] = struct.unpack(
                "H", fcntl.ioctl(control.fileno(), 0x8913, request)[16:18]
            )[0]
            try:
                fcntl.ioctl(control.fileno(), 0x8915, request)
                addressed.append(name)
            except OSError:
                pass
        target = next((name for name in interfaces if name != "lo"), "lo")
        activation = struct.pack(
            "16sH", target.encode()[:15], flags[target] | 1
        ) + bytes(238)
        try:
            fcntl.ioctl(control.fileno(), 0x8914, activation)
            activation_denied = False
        except OSError as exc:
            activation_denied = exc.errno == errno.EPERM
    result["activation_denied"] = activation_denied
    result["namespace_interfaces"] = interfaces
    result["interface_flags"] = flags
    result["dormant_interfaces_down"] = all(
        not (flags[name] & 1) for name in interfaces if name != "lo"
    )
    result["no_nonloopback_ipv4_address"] = not any(name != "lo" for name in addressed)
    result["no_nonloopback_ipv6_address"] = not any(
        line.split()[-1] != "lo"
        for line in Path("/proc/net/if_inet6").read_text().splitlines()
    )
    result["no_nonloopback_ipv4_route"] = not any(
        line.split()[0] != "lo"
        for line in Path("/proc/net/route").read_text().splitlines()[1:]
    )
    result["no_nonloopback_ipv6_route"] = not any(
        line.split()[-1] != "lo"
        for line in Path("/proc/net/ipv6_route").read_text().splitlines()
    )
    for label, address in (("metadata", "169.254.169.254"), ("egress", "1.1.1.1")):
        try:
            with socket.create_connection((address, 80), timeout=0.2):
                result[label + "_denied"] = False
        except OSError:
            result[label + "_denied"] = True
    for label, path in (
        ("root", "/forbidden"),
        ("source", "/source/forbidden"),
        ("catalog", "/opt/deploywhisper/forbidden"),
    ):
        try:
            Path(path).write_bytes(b"synthetic")
            result[label + "_readonly"] = False
        except OSError:
            result[label + "_readonly"] = True
    return result


if __name__ == "__main__":
    json.load(sys.stdin)
    print(json.dumps({key: str(value) for key, value in evidence().items()}))
