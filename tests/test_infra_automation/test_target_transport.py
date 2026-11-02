"""Connection-policy qualification with DNS, TCP and TLS doubles only."""

from __future__ import annotations

import socket
import ssl
import threading
import unittest
from unittest.mock import Mock, patch

from infra_automation.target_transport import (
    PinnedGithubTransport,
    TransportError,
    canonical_origin,
    github_dispatch_path,
    validate_addresses,
)


PUBLIC = "93.184.216.34"
PUBLIC6 = "2606:4700:4700::1111"
SECRET = "synthetic-secret-for-transport-tests"


class SocketDouble:
    def __init__(
        self, response=b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n"
    ):
        self.response = response
        self.peer = (PUBLIC, 443)
        self.connected = None
        self.sent = []
        self.timeouts = []
        self.closed = False

    def connect(self, address):
        self.connected = address

    def getpeername(self):
        return self.peer

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def sendall(self, data):
        self.sent.append(bytes(data))

    def recv_into(self, buffer):
        size = min(len(buffer), len(self.response))
        buffer[:size] = self.response[:size]
        self.response = self.response[size:]
        return size

    def close(self):
        self.closed = True


class TargetOriginTests(unittest.TestCase):
    def test_canonical_https_origins(self):
        for raw, expected in (
            ("https://API.GITHUB.COM/", "https://api.github.com"),
            ("https://api.github.com:443", "https://api.github.com"),
            ("https://internal.example:8443/", "https://internal.example:8443"),
            ("https://[2606:4700:4700:0::1111]", f"https://[{PUBLIC6}]"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(canonical_origin(raw), expected)

    def test_unsafe_origins_and_ambiguous_numbers_deny(self):
        for raw in (
            "http://api.github.com",
            "https://user:pass@api.github.com",
            "https://api.github.com/path",
            "https://api.github.com?",
            "https://api.github.com#",
            "https://api.github.com:0",
            "https://api.github.com:65536",
            "https://api.github.com:0443",
            "https://api.github.com:",
            "https://api.github.com\\@evil.example",
            "https://api.github.com%2f.evil",
            "https://api.github.com. ",
            "https://аpi.github.com",
            "https://api.github.com\n",
            "https://api.github.com.",
            "https://[fe80::1%25eth0]",
            "https://2130706433",
            "https://127.1",
            "https://0177.0.0.1",
            "https://0x7f000001",
            "https://0x7f.0.0.1",
            "https://127.000.0.1",
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                canonical_origin(raw)

    def test_dispatch_path_is_fixed_and_components_are_closed(self):
        self.assertEqual(
            github_dispatch_path("example", "repo", "handoff.yml"),
            "/repos/example/repo/actions/workflows/handoff.yml/dispatches",
        )
        for value in (
            "../x",
            "a/b",
            "a%2fb",
            "a?b",
            "a#b",
            "a\\b",
            "a\r\nb",
            "é",
            "..",
            "",
        ):
            for index in range(3):
                values = ["example", "repo", "handoff.yml"]
                values[index] = value
                with (
                    self.subTest(value=value, index=index),
                    self.assertRaises(ValueError),
                ):
                    github_dispatch_path(*values)


class TargetAddressTests(unittest.TestCase):
    def test_public_ipv4_ipv6_and_duplicate_answers(self):
        self.assertEqual(
            validate_addresses("api.github.com", [PUBLIC, PUBLIC6, PUBLIC]),
            (PUBLIC, PUBLIC6),
        )

    def test_every_forbidden_or_mixed_answer_denies(self):
        for address in (
            "127.0.0.1",
            "10.1.2.3",
            "172.16.0.1",
            "192.168.1.1",
            "169.254.169.254",
            "0.0.0.0",
            "224.0.0.1",
            "240.0.0.1",
            "255.255.255.255",
            "192.0.2.1",
            "192.0.0.9",
            "192.0.0.10",
            "192.88.99.1",
            "198.51.100.1",
            "203.0.113.1",
            "100.100.100.200",
            "168.63.129.16",
            "::",
            "::1",
            "fe80::1",
            "ff02::1",
            "fd00:ec2::254",
            "fd20:ce::254",
            "2001:db8::1",
            "::ffff:127.0.0.1",
            "::ffff:93.184.216.34",
            "64:ff9b::7f00:1",
            "2002:7f00:1::",
            "2001::1",
            "2001:20::1",
            "fec0::1",
            "127.1",
            "2130706433",
            "0177.0.0.1",
            "fe80::1%eth0",
        ):
            for answers in ([address], [PUBLIC, address], [address, PUBLIC6]):
                with self.subTest(answers=answers), self.assertRaises(ValueError):
                    validate_addresses("api.github.com", answers)
        with self.assertRaises(ValueError):
            validate_addresses("api.github.com", [])

    def test_only_exact_private_or_loopback_exceptions_are_possible(self):
        for address in ("10.1.2.3", "127.0.0.1", "::1", "fd12::1"):
            self.assertEqual(
                validate_addresses("internal.example", [address], [address]), (address,)
            )
            with self.assertRaises(ValueError):
                validate_addresses("internal.example", [address], ["10.1.2.4"])
        for address in (
            "169.254.169.254",
            "fd00:ec2::254",
            "fd20:ce::254",
            "168.63.129.16",
            "0.0.0.0",
            "::ffff:127.0.0.1",
            "192.0.2.1",
        ):
            with self.subTest(address=address), self.assertRaises(ValueError):
                validate_addresses("internal.example", [address], [address])

    def test_literal_host_cannot_resolve_to_different_address(self):
        with self.assertRaises(ValueError):
            validate_addresses(PUBLIC, [PUBLIC6])


class TargetTransportTests(unittest.TestCase):
    def setUp(self):
        self.socket = SocketDouble()
        self.resolver = Mock(
            return_value=[
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    (PUBLIC, 443),
                )
            ]
        )
        self.socket_factory = Mock(return_value=self.socket)
        self.context = Mock(check_hostname=True, verify_mode=ssl.CERT_REQUIRED)
        self.context.wrap_socket.return_value = self.socket
        self.context_patch = patch(
            "infra_automation.target_transport.ssl.create_default_context",
            return_value=self.context,
        )
        self.context_patch.start()
        self.addCleanup(self.context_patch.stop)

    def transport(self, **kwargs):
        return PinnedGithubTransport(
            _resolver=self.resolver, _socket_factory=self.socket_factory, **kwargs
        )

    def send(self, transport=None, **kwargs):
        fields = dict(
            origin="https://api.github.com",
            owner="example",
            repository="repo",
            workflow="handoff.yml",
            payload_bytes=b'{"ref":"main"}',
            token=SECRET,
        )
        fields.update(kwargs)
        return (transport or self.transport()).post_registered(**fields)

    def assert_failure(self, code, may_have_sent, **kwargs):
        with self.assertRaises(TransportError) as caught:
            self.send(**kwargs)
        error = caught.exception
        self.assertEqual(error.code, code)
        self.assertEqual(error.may_have_sent, may_have_sent)
        self.assertNotIn(SECRET, str(error))
        self.assertNotIn(SECRET, repr(error))
        return error

    def test_numeric_tcp_pin_peer_verification_and_tls_hostname(self):
        with patch.dict("os.environ", {"HTTPS_PROXY": "http://127.0.0.1:8888"}):
            result = self.send()
        self.assertEqual((result.status, result.body), (204, b""))
        self.resolver.assert_called_once_with(
            "api.github.com", 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
        self.socket_factory.assert_called_once_with(
            socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP
        )
        self.assertEqual(self.socket.connected, (PUBLIC, 443))
        self.context.wrap_socket.assert_called_once_with(
            self.socket, server_hostname="api.github.com"
        )
        wire = b"".join(self.socket.sent)
        self.assertIn(
            b"POST /repos/example/repo/actions/workflows/handoff.yml/dispatches HTTP/1.1",
            wire,
        )
        self.assertIn(b"Host: api.github.com\r\n", wire)
        self.assertIn(b"X-GitHub-Api-Version: 2026-03-10\r\n", wire)
        self.assertIn(b"Authorization: Bearer " + SECRET.encode(), wire)
        self.assertTrue(self.socket.closed)
        self.assertTrue(all(0 < timeout <= 10 for timeout in self.socket.timeouts))

    def test_ipv6_numeric_pin_retains_original_hostname(self):
        self.resolver.return_value = [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (PUBLIC6, 443, 0, 0),
            )
        ]
        self.socket.peer = (PUBLIC6, 443, 0, 0)
        self.send()
        self.assertEqual(self.socket.connected, (PUBLIC6, 443, 0, 0))
        self.socket_factory.assert_called_once_with(
            socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP
        )

    def test_dns_rebinding_is_rechecked_on_every_dispatch(self):
        transport = self.transport()
        self.send(transport)
        self.resolver.return_value = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 443),
            )
        ]
        self.assert_failure("destination_denied", False, transport=transport)
        self.assertEqual(self.socket_factory.call_count, 1)

    def test_mixed_dns_answers_deny_before_dial(self):
        self.resolver.return_value.append(
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("::1", 443, 0, 0),
            )
        )
        self.assert_failure("destination_denied", False)
        self.socket_factory.assert_not_called()

    def test_peer_mismatch_denies_before_tls_and_authorization(self):
        self.socket.peer = ("127.0.0.1", 443)
        self.assert_failure("peer_mismatch", False)
        self.context.wrap_socket.assert_not_called()
        self.assertEqual(self.socket.sent, [])
        self.assertTrue(self.socket.closed)

    def test_post_tls_peer_is_rechecked(self):
        self.socket.getpeername = Mock(side_effect=[(PUBLIC, 443), ("127.0.0.1", 443)])
        self.assert_failure("peer_mismatch", False)
        self.assertEqual(self.socket.sent, [])

    def test_protocol_floor_is_explicit_before_tls_wrap(self):
        self.context.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED

        def wrap(raw, *, server_hostname):
            self.assertGreaterEqual(
                self.context.minimum_version, ssl.TLSVersion.TLSv1_2
            )
            return self.socket

        self.context.wrap_socket.side_effect = wrap
        self.send()
        self.assertEqual(self.context.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_unavailable_protocol_floor_denies_before_credentials_are_sent(self):
        class UnavailableContext:
            check_hostname = True
            verify_mode = ssl.CERT_REQUIRED
            wrap_socket = Mock()

            @property
            def minimum_version(self):
                return ssl.TLSVersion.MINIMUM_SUPPORTED

            @minimum_version.setter
            def minimum_version(self, value):
                raise ValueError("Unsupported TLS policy")

        unavailable = UnavailableContext()
        self.context_patch.stop()
        with patch(
            "infra_automation.target_transport.ssl.create_default_context",
            return_value=unavailable,
        ):
            self.assert_failure("connection_failed", False)
        unavailable.wrap_socket.assert_not_called()
        self.assertEqual(self.socket.sent, [])

    def test_tls_verification_is_mandatory(self):
        self.context.verify_mode = ssl.CERT_NONE
        self.assert_failure("tls_unavailable", False)
        self.context.wrap_socket.assert_not_called()
        self.assertEqual(self.socket.sent, [])

    def test_tls_hostname_verification_cannot_be_disabled(self):
        self.context.check_hostname = False
        self.assert_failure("tls_unavailable", False)
        self.context.wrap_socket.assert_not_called()
        self.assertEqual(self.socket.sent, [])

    def test_tcp_failure_cannot_expose_credentials(self):
        self.socket.connect = Mock(side_effect=OSError(SECRET))
        self.assert_failure("connection_failed", False)
        self.context.wrap_socket.assert_not_called()
        self.assertEqual(self.socket.sent, [])
        self.assertTrue(self.socket.closed)

    def test_tls_or_tcp_failure_is_provably_no_send(self):
        self.context.wrap_socket.side_effect = ssl.SSLError(SECRET)
        error = self.assert_failure("connection_failed", False)
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__suppress_context__)
        self.assertEqual(self.socket.sent, [])

    def test_ambiguous_write_failure_has_no_automatic_retry(self):
        self.socket.sendall = Mock(side_effect=TimeoutError(SECRET))
        self.assert_failure("delivery_unknown", True)
        self.socket_factory.assert_called_once()

    def test_every_redirect_is_rejected_without_following(self):
        for status in (300, 301, 302, 303, 307, 308):
            with self.subTest(status=status):
                self.socket.response = f"HTTP/1.1 {status} Redirect\r\nLocation: https://169.254.169.254/\r\nContent-Length: 0\r\n\r\n".encode()
                self.assert_failure("redirect_denied", True)
        self.assertEqual(self.resolver.call_count, 6)

    def test_exact_operator_origin_and_exact_private_ip_exception(self):
        self.resolver.return_value = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("10.1.2.3", 8443),
            )
        ]
        self.socket.peer = ("10.1.2.3", 8443)
        self.assert_failure(
            "destination_denied",
            False,
            origin="https://internal.example:8443",
            allowed_private_addresses=("10.1.2.3",),
        )
        transport = self.transport(allowed_origins=("https://internal.example:8443",))
        self.assert_failure(
            "destination_denied",
            False,
            transport=transport,
            origin="https://internal.example:8443",
        )
        self.send(
            transport,
            origin="https://internal.example:8443",
            allowed_private_addresses=("10.1.2.3",),
        )
        self.assertEqual(self.socket.connected, ("10.1.2.3", 8443))
        self.context.wrap_socket.assert_called_once_with(
            self.socket, server_hostname="internal.example"
        )

    def test_body_token_and_constructor_limits_deny_before_connection(self):
        for kwargs in (
            dict(payload_bytes=b"x" * 65537),
            dict(token=SECRET + "\r\nInjected: x"),
            dict(payload_bytes="text"),
            dict(workflow="../evil"),
        ):
            with self.subTest(kwargs=tuple(kwargs)):
                self.assert_failure("invalid_request", False, **kwargs)
        self.resolver.assert_not_called()
        for kwargs in (
            dict(timeout=0),
            dict(timeout=float("inf")),
            dict(timeout=31),
            dict(max_body_bytes=0),
            dict(max_response_bytes=1048577),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.transport(**kwargs)

    def test_response_size_bound_and_secret_free_repr(self):
        self.socket.response = b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n12345678"
        self.assert_failure(
            "response_too_large", True, transport=self.transport(max_response_bytes=4)
        )
        self.socket.response = (
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(SECRET)).encode()
            + b"\r\n\r\n"
            + SECRET.encode()
        )
        result = self.send()
        self.assertEqual(result.body, SECRET.encode())
        self.assertNotIn(SECRET, repr(result))

    def test_read_timeout_is_ambiguous_and_closes(self):
        self.socket.recv_into = Mock(side_effect=TimeoutError(SECRET))
        self.assert_failure("delivery_unknown", True)
        self.assertTrue(self.socket.closed)

    def test_dns_failure_and_timeout_are_no_send_and_bounded(self):
        self.resolver.side_effect = OSError(SECRET)
        self.assert_failure("connection_failed", False)
        release = threading.Event()
        finished = threading.Event()

        def stalled_resolver(*args, **kwargs):
            try:
                release.wait(1)
                return []
            finally:
                finished.set()

        self.resolver.side_effect = stalled_resolver
        try:
            self.assert_failure(
                "connection_failed", False, transport=self.transport(timeout=0.01)
            )
        finally:
            release.set()
            self.assertTrue(finished.wait(1))
        self.socket_factory.assert_not_called()

    def test_slow_response_cannot_extend_total_deadline(self):
        clock = [0.0]
        receive = self.socket.recv_into

        def trickle(buffer):
            clock[0] += 6
            return receive(memoryview(buffer)[:1])

        self.socket.recv_into = trickle
        with patch(
            "infra_automation.target_transport.time.monotonic",
            side_effect=lambda: clock[0],
        ):
            self.assert_failure("delivery_unknown", True)
        self.assertEqual(clock[0], 12)

    def test_truncated_and_oversized_unknown_length_or_chunked_bodies_deny(self):
        for response, code in (
            (b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nabc", "delivery_unknown"),
            (
                b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n123456",
                "response_too_large",
            ),
            (
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n6\r\n123456\r\n0\r\n\r\n",
                "response_too_large",
            ),
        ):
            self.socket.response = response
            self.assert_failure(
                code, True, transport=self.transport(max_response_bytes=5)
            )

    def test_scoped_or_unbounded_dns_answer_sets_deny(self):
        self.resolver.return_value = [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (PUBLIC6, 443, 0, 2),
            )
        ]
        self.assert_failure("destination_denied", False)
        self.resolver.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (PUBLIC, 443))
        ] * 65
        self.assert_failure("destination_denied", False)
        self.socket_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
