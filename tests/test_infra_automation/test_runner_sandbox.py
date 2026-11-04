"""Host control assertions for the isolated runner launcher."""

from __future__ import annotations
import unittest
from pydantic import ValidationError
from infra_automation.runner.execution_profile import ExecutionProfile, IsolationError
from infra_automation.runner.sandbox import DockerSandbox


class RunnerSandboxTests(unittest.TestCase):
    def test_closed_profile_rejects_privileged_and_unbounded_settings(self):
        for extra in (
            {"uid": 0},
            {"network": "host"},
            {"memory_bytes": 0},
            {"nano_cpus": True},
            {"privileged": True},
            {"architecture": "amd64"},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                ExecutionProfile(image_id="sha256:" + "a" * 64, **extra)

    def test_ambient_context_and_remote_socket_are_rejected(self):
        with self.assertRaises(IsolationError):
            DockerSandbox(
                "/usr/bin/docker",
                "tcp://example.invalid:2375",
                ExecutionProfile(image_id="sha256:" + "a" * 64),
            )


class OfflineNetworkTests(unittest.TestCase):
    def check(
        self,
        interfaces,
        *,
        flags=0,
        address=False,
        routes="header\n",
        ipv6="",
        ipv6_routes="",
    ):
        import errno
        import struct
        from unittest.mock import patch
        from infra_automation.runner import bootstrap

        def ioctl(fd, operation, value):
            if operation == 0x8913:
                return b"\0" * 16 + struct.pack("H", flags) + b"\0" * 238
            if address:
                return b"\0" * 256
            raise OSError(errno.EADDRNOTAVAIL, "Unavailable")

        files = {
            "/proc/net/route": routes,
            "/proc/net/if_inet6": ipv6,
            "/proc/net/ipv6_route": ipv6_routes,
        }
        with (
            patch.object(
                bootstrap.socket,
                "if_nameindex",
                return_value=list(enumerate(interfaces, 1)),
            ),
            patch.object(bootstrap.fcntl, "ioctl", side_effect=ioctl),
            patch.object(bootstrap.Path, "read_text", lambda path: files[str(path)]),
        ):
            bootstrap.verify_offline_network()

    def test_only_exact_dormant_tunnels_are_qualified(self):
        from infra_automation.runner.bootstrap import DORMANT_TUNNELS

        self.check(["lo", *DORMANT_TUNNELS])
        self.check(["lo"])
        for interfaces in (["lo", "eth0"], ["lo", "new_tunnel"], []):
            with self.subTest(interfaces=interfaces), self.assertRaises(ValueError):
                self.check(interfaces)

    def test_activation_address_and_egress_routes_deny(self):
        for options in (
            {"flags": 1},
            {"flags": 64},
            {"address": True},
            {"routes": "header\ntunl0 route\n"},
            {"ipv6": "00000000000000000000000000000001 1 80 10 80 tunl0\n"},
            {"ipv6_routes": "0 0 0 0 0 0 0 0 0 tunl0\n"},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.check(["lo", "tunl0"], **options)

    def test_host_kernel_and_docker_version_are_closed(self):
        for values in ({"kernel_version": "other"}, {"docker_version": "99.0"}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ExecutionProfile(image_id="sha256:" + "a" * 64, **values)


class WatchdogFilterTests(unittest.TestCase):
    def test_aarch64_watchdog_mutations_deny_while_normal_syscalls_remain(self):
        from infra_automation.runner.bootstrap import (
            watchdog_filter_program,
            WATCHDOG_DENIED_SYSCALLS,
        )

        def verdict(number, architecture=0xC00000B7):
            code = watchdog_filter_program()
            pc = 0
            value = 0
            while pc < len(code):
                instruction, jt, jf, constant = code[pc]
                if instruction == 0x20:
                    value = {0: number, 4: architecture}[constant]
                elif instruction == 0x15:
                    pc += jt if value == constant else jf
                elif instruction == 0x06:
                    return constant
                else:
                    self.fail("Unsupported filter instruction")
                pc += 1
            self.fail("Filter did not decide")

        for number in WATCHDOG_DENIED_SYSCALLS:
            with self.subTest(number=number):
                self.assertEqual(verdict(number), 0x00050001)
        for number in (57, 63, 64, 113, 172, 220, 221):
            with self.subTest(number=number):
                self.assertEqual(verdict(number), 0x7FFF0000)
        self.assertEqual(verdict(64, 0xC000003E), 0x80000000)


class AmbiguousCreationTests(unittest.TestCase):
    def test_empty_lookup_after_create_error_keeps_unknown_operation_pending(self):
        from pathlib import Path
        import tempfile

        sandbox = object.__new__(DockerSandbox)
        sandbox.profile = ExecutionProfile(image_id="sha256:" + "a" * 64)
        sandbox._owned = {}
        sandbox._reservations = {}
        sandbox._attempted = set()
        sandbox.preflight = lambda: None
        name = sandbox.reserve()

        def control(*args, **kwargs):
            if args[0] in ("create", "inspect"):
                raise IsolationError()
            if args[0] == "ps":
                return b""
            self.fail("Unowned mutation attempted")

        sandbox.control = control
        with tempfile.TemporaryDirectory() as root, self.assertRaises(IsolationError):
            sandbox.create(Path(root).resolve(), name=name, task_digest="b" * 64)
        self.assertTrue(sandbox.pending_creation(name))
        self.assertFalse(sandbox.owns(name))

    def test_late_create_is_retained_across_restart_then_recovered_by_nonce(self):
        import json
        from pathlib import Path
        import tempfile
        from infra_automation.runner.execution import ExecutionRunner

        record = {"visible": False}
        removed = []
        key = "b" * 64
        identifier = "e" * 64

        def port():
            value = object.__new__(DockerSandbox)
            value.profile = ExecutionProfile(image_id="sha256:" + "a" * 64)
            value._owned = {}
            value._reservations = {}
            value._attempted = set()
            value.preflight = lambda: None

            def control(*args, **kwargs):
                if args[0] == "create":
                    record["labels"] = dict(
                        args[i + 1].split("=", 1)
                        for i, arg in enumerate(args)
                        if arg == "--label"
                    )
                    raise IsolationError()
                if args[0] == "inspect":
                    if not record["visible"]:
                        raise IsolationError()
                    return json.dumps(
                        [
                            {
                                "Id": identifier,
                                "Image": value.profile.image_id,
                                "Name": "/" + record["name"],
                                "Config": {"Labels": record["labels"]},
                                "State": {"Running": False},
                            }
                        ]
                    ).encode()
                if args[0] == "ps":
                    return identifier.encode() if record["visible"] else b""
                if args[0] == "rm":
                    removed.append(args[-1])
                    record["visible"] = False
                    return b""
                self.fail("Unexpected control operation")

            value.control = control
            return value

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sandbox = port()
            name = sandbox.reserve()
            record["name"] = name
            runner = ExecutionRunner(
                sandbox, root / "catalog", "sha256:" + "a" * 64, root / "journal"
            )
            runner.journal.begin(key, name, "profile", sandbox.reservation_nonce(name))
            with self.assertRaises(IsolationError):
                sandbox.create(root, name=name, task_digest=key)
            self.assertFalse(runner.recover_pending()[0]["cleanup_complete"])
            self.assertTrue(runner.journal.pending())
            self.assertEqual(removed, [])
            record["visible"] = True
            restarted = ExecutionRunner(
                port(), root / "catalog", "sha256:" + "a" * 64, root / "journal"
            )
            self.assertTrue(restarted.recover_pending()[0]["cleanup_complete"])
            self.assertEqual(removed, [identifier])
            self.assertEqual(restarted.journal.pending(), [])


class TerminationRaceTests(unittest.TestCase):
    def port(self, scenario):
        import json

        sandbox = object.__new__(DockerSandbox)
        sandbox.profile = ExecutionProfile(image_id="sha256:" + "a" * 64)
        name = "dw-isolated-" + "b" * 32
        identifier = "c" * 64
        sandbox._owned = {name: identifier}
        sandbox._attempted = {name}
        sandbox._reservations = {name: "d" * 32}
        removed = []

        def control(*args, **kwargs):
            if args[0] == "kill":
                raise IsolationError()
            if args[0] == "ps":
                if scenario == "unavailable":
                    raise IsolationError()
                if scenario == "foreign":
                    return ("f" * 64).encode()
                return b"" if scenario == "absent" or removed else identifier.encode()
            if args[0] == "inspect":
                return json.dumps(
                    [{"Id": identifier, "State": {"Running": scenario == "running"}}]
                ).encode()
            if args[0] == "rm":
                removed.append(args[-1])
                return b""
            self.fail("Unexpected control operation")

        sandbox.control = control
        return sandbox, name, identifier, removed

    def test_natural_exit_racing_kill_still_removes_owned_container(self):
        for scenario in ("stopped", "absent"):
            with self.subTest(scenario=scenario):
                sandbox, name, identifier, removed = self.port(scenario)
                sandbox.terminate(name)
                sandbox.remove(name)
                self.assertEqual(removed, [identifier] if scenario == "stopped" else [])
                self.assertFalse(sandbox.owns(name))

    def test_failed_kill_does_not_hide_running_unavailable_or_foreign_state(self):
        for scenario in ("running", "unavailable", "foreign"):
            with self.subTest(scenario=scenario):
                sandbox, name, _, removed = self.port(scenario)
                with self.assertRaises(IsolationError):
                    sandbox.terminate(name)
                self.assertTrue(sandbox.owns(name))
                self.assertEqual(removed, [])
