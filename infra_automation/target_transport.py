"""Fixed GitHub dispatch transport with operator policy and pinned HTTPS peers.

This boundary accepts trusted registry fields, not workflow-selected URLs. Its
socket/DNS injection points qualify policy locally; they are not runtime TLS
configuration. Delivery/receiver protocol qualification belongs to Story16.11.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import http.client
import io
import ipaddress
import math
import queue
import re
import socket
import ssl
import threading
import time
from urllib.parse import quote, urlsplit


_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\Z")
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "::1/128",
        "fc00::/7",
    )
)
_METADATA = frozenset(
    (
        "169.254.169.254",
        "100.100.100.200",
        "168.63.129.16",
        "fd00:ec2::254",
        "fd20:ce::254",
    )
)
_DNS_SLOTS = threading.BoundedSemaphore(8)
_SPECIAL_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("192.0.0.0/24", "192.88.99.0/24", "2001::/23", "2002::/16")
)


def _host(value: str) -> str:
    if not value or not value.isascii() or "%" in value:
        raise ValueError("invalid destination host")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        value = value.lower()
        labels = value.split(".")
        if (
            len(value) > 253
            or any(not _DNS_LABEL.fullmatch(label) for label in labels)
            or not any(char.isalpha() for char in labels[-1])
            or re.fullmatch(r"0x[0-9a-f]+", labels[-1])
        ):
            raise ValueError("invalid destination host") from None
        return value
    return str(address)


def canonical_origin(value: str) -> str:
    """Validate an ASCII HTTPS origin, preserving only canonical host and port."""
    if (
        not isinstance(value, str)
        or not value.isascii()
        or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        or any(char in value for char in ("\\", "%", "?", "#", "@"))
    ):
        raise ValueError("invalid HTTPS origin")
    try:
        parts = urlsplit(value)
        if parts.scheme != "https" or parts.path not in ("", "/") or not parts.hostname:
            raise ValueError
        host = _host(parts.hostname)
        port = parts.port
        authority = parts.netloc
        if ":" in host:
            if not authority.startswith("[") or "]" not in authority:
                raise ValueError
            suffix = authority[authority.index("]") + 1 :]
        else:
            suffix = authority[len(parts.hostname) :]
        if suffix and (port is None or suffix != f":{port}"):
            raise ValueError
        if port is not None and not 1 <= port <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("invalid HTTPS origin") from None
    authority = f"[{host}]" if ":" in host else host
    return f"https://{authority}" + (f":{port}" if port not in (None, 443) else "")


def github_dispatch_path(owner: str, repository: str, workflow: str) -> str:
    """Build only the fixed GitHub workflow-dispatch route."""
    for value, pattern in (
        (owner, _OWNER),
        (repository, _COMPONENT),
        (workflow, _COMPONENT),
    ):
        if not isinstance(value, str) or not pattern.fullmatch(value) or ".." in value:
            raise ValueError("invalid registered dispatch component")
    return f"/repos/{owner}/{repository}/actions/workflows/{workflow}/dispatches"


def github_registered_get_path(
    owner: str, repository: str, resource: str, selector: str | None = None
) -> str:
    """Build metadata routes from a closed resource set, never a supplied path."""
    github_dispatch_path(owner, repository, "validate.yml")
    root = f"/repos/{owner}/{repository}"
    if resource in ("repository", "rulesets"):
        if selector is not None:
            raise ValueError("unexpected registered selector")
        return (
            root
            if resource == "repository"
            else root + "/rulesets?includes_parents=true&per_page=100&page=1"
        )
    if not isinstance(selector, str):
        raise ValueError("missing registered selector")
    if resource in ("run", "ruleset"):
        if not re.fullmatch(r"[1-9][0-9]{0,15}", selector) or int(selector) > 2**53 - 1:
            raise ValueError("invalid registered numeric selector")
        suffix = "actions/runs" if resource == "run" else "rulesets"
    elif resource == "workflow":
        github_dispatch_path(owner, repository, selector)
        suffix = "actions/workflows"
    elif resource in ("branch", "tag_ref"):
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", selector)
            or any(part in selector for part in ("..", "//", "@{"))
            or selector.endswith(("/", ".", ".lock"))
        ):
            raise ValueError("invalid registered ref selector")
        suffix = "branches" if resource == "branch" else "git/ref/tags"
    elif resource == "tag_object":
        if not re.fullmatch(r"[0-9a-f]{40}", selector):
            raise ValueError("invalid registered tag selector")
        suffix = "git/tags"
    else:
        raise ValueError("unregistered resource")
    return f"{root}/{suffix}/{quote(selector, safe='')}"


def _address(value: str):
    if not isinstance(value, str) or "%" in value or not value.isascii():
        raise ValueError("invalid destination address")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise ValueError("invalid destination address") from None
    if isinstance(address, ipaddress.IPv6Address) and (
        address.ipv4_mapped or address.sixtofour or address.teredo
    ):
        raise ValueError("destination address denied")
    if (
        str(address) in _METADATA
        or address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or (address.is_reserved and not address.is_loopback)
        or (isinstance(address, ipaddress.IPv6Address) and address.is_site_local)
        or any(address in network for network in _SPECIAL_NETWORKS)
    ):
        raise ValueError("destination address denied")
    return address


def validate_addresses(
    host: str, addresses, allowed_private_addresses=()
) -> tuple[str, ...]:
    """Reject the entire DNS answer set unless every address meets policy.

    Only RFC1918/ULA/loopback can be excepted. This helper's exceptions must come
    from an audited registry; the transport independently checks exact origin
    membership. Metadata, mapped/transition, reserved and special ranges deny.
    """
    host = _host(host)
    allowed = frozenset(str(_address(value)) for value in allowed_private_addresses)
    result = []
    for value in addresses:
        address = _address(value)
        canonical = str(address)
        private = any(address in network for network in _PRIVATE_NETWORKS)
        if private:
            if canonical not in allowed:
                raise ValueError("private destination denied")
        elif not address.is_global or (
            address.version == 6 and address not in ipaddress.ip_network("2000::/3")
        ):
            raise ValueError("destination address denied")
        if canonical not in result:
            result.append(canonical)
    if not result:
        raise ValueError("empty destination addresses")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and result != [str(literal)]:
        raise ValueError("literal destination mismatch")
    return tuple(result)


class TransportError(RuntimeError):
    """Secret-free failure classification; never implies safe automatic retry."""

    def __init__(self, code: str, *, may_have_sent: bool):
        self.code = code
        self.may_have_sent = may_have_sent
        super().__init__(code)


@dataclass(frozen=True)
class DispatchResponse:
    status: int
    body: bytes = field(repr=False)


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("transport deadline exceeded")
    return remaining


def _resolve(resolver, host, port, deadline):
    """Bound platform DNS waits without leaving unbounded background workers.

    A stuck OS resolver cannot be interrupted safely. At most eight daemon DNS
    calls may remain; they receive neither credentials nor connection authority.
    """
    if not _DNS_SLOTS.acquire(timeout=_remaining(deadline)):
        raise TimeoutError("resolver capacity unavailable")
    result = queue.Queue(maxsize=1)

    def resolve():
        try:
            records = resolver(
                host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
            result.put((True, records))
        except Exception:
            result.put((False, None))
        finally:
            _DNS_SLOTS.release()

    thread = threading.Thread(target=resolve, daemon=True)
    try:
        thread.start()
    except Exception:
        _DNS_SLOTS.release()
        raise
    success, records = result.get(timeout=_remaining(deadline))
    if not success:
        raise OSError("destination resolution failed")
    return records


class _DeadlineReader(io.RawIOBase):
    def __init__(self, sock, deadline):
        self.sock = sock
        self.deadline = deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        self.sock.settimeout(_remaining(self.deadline))
        return self.sock.recv_into(buffer)


class _DeadlineSocket:
    """Apply one deadline to every read, including response headers/chunks."""

    def __init__(self, sock, deadline):
        self.sock = sock
        self.deadline = deadline

    def sendall(self, data):
        self.sock.settimeout(_remaining(self.deadline))
        self.sock.sendall(data)

    def makefile(self, mode):
        if mode != "rb":
            raise ValueError("invalid socket file mode")
        return io.BufferedReader(_DeadlineReader(self.sock, self.deadline))

    def close(self):
        self.sock.close()


class PinnedGithubTransport:
    """Bounded HTTPS metadata/dispatch using exact operator-allowlisted origins.

    No proxies, redirects, retries, arbitrary paths or TLS-disable switches.
    Resolver/socket hooks are constructor-owned trusted qualification seams.
    """

    def __init__(
        self,
        allowed_origins: tuple[str, ...] = ("https://api.github.com",),
        *,
        timeout: float = 10.0,
        max_body_bytes: int = 65536,
        max_response_bytes: int = 65536,
        _resolver=None,
        _socket_factory=None,
    ):
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or not 0 < timeout <= 30
        ):
            raise ValueError("invalid transport timeout")
        if any(
            type(value) is not int or not 1 <= value <= 1048576
            for value in (max_body_bytes, max_response_bytes)
        ):
            raise ValueError("invalid transport size limit")
        self.allowed_origins = tuple(
            canonical_origin(value) for value in allowed_origins
        )
        self.timeout = timeout
        self.max_body_bytes = max_body_bytes
        self.max_response_bytes = max_response_bytes
        self._resolver = _resolver or socket.getaddrinfo
        self._socket_factory = _socket_factory or socket.socket

    def post_registered(
        self,
        origin: str,
        owner: str,
        repository: str,
        workflow: str,
        payload_bytes: bytes,
        token: str,
        allowed_private_addresses=(),
    ) -> DispatchResponse:
        """POST registered bytes; classify pre-send failures versus uncertainty."""
        try:
            path = github_dispatch_path(owner, repository, workflow)
        except (ValueError, TypeError):
            raise TransportError("invalid_request", may_have_sent=False) from None
        return self._request_registered(
            "POST", origin, path, payload_bytes, token, allowed_private_addresses
        )

    def get_registered(
        self,
        origin: str,
        owner: str,
        repository: str,
        resource: str,
        selector: str | None,
        token: str,
        allowed_private_addresses=(),
    ) -> DispatchResponse:
        """GET fixed registered metadata with the identical pinned TLS boundary."""
        try:
            path = github_registered_get_path(owner, repository, resource, selector)
        except (ValueError, TypeError):
            raise TransportError("invalid_request", may_have_sent=False) from None
        return self._request_registered(
            "GET", origin, path, None, token, allowed_private_addresses
        )

    def _request_registered(
        self, method, origin, path, payload_bytes, token, allowed_private_addresses
    ):
        try:
            origin = canonical_origin(origin)
            if (
                (
                    payload_bytes is not None
                    and (
                        not isinstance(payload_bytes, bytes)
                        or len(payload_bytes) > self.max_body_bytes
                    )
                )
                or (method == "POST" and payload_bytes is None)
                or not isinstance(token, str)
                or not 1 <= len(token) <= 8192
                or not token.isascii()
                or any(ord(char) <= 32 or ord(char) == 127 for char in token)
            ):
                raise ValueError
        except (ValueError, TypeError):
            raise TransportError("invalid_request", may_have_sent=False) from None
        if origin not in self.allowed_origins:
            raise TransportError("destination_denied", may_have_sent=False)
        parsed = urlsplit(origin)
        host, port = parsed.hostname, parsed.port or 443
        if host is None:
            raise TransportError("invalid_request", may_have_sent=False)
        deadline = time.monotonic() + self.timeout
        raw = tls = connection = None
        may_have_sent = False
        try:
            records = _resolve(self._resolver, host, port, deadline)
            try:
                if (
                    not isinstance(records, (list, tuple))
                    or not 1 <= len(records) <= 64
                ):
                    raise ValueError
                addresses = validate_addresses(
                    host,
                    [record[4][0] for record in records],
                    allowed_private_addresses,
                )
                # A malicious/scoped IPv6 answer must not smuggle a zone ID.
                if any(
                    record[0] not in (socket.AF_INET, socket.AF_INET6)
                    or (
                        record[0] == socket.AF_INET6
                        and len(record[4]) > 3
                        and record[4][3] != 0
                    )
                    for record in records
                ):
                    raise ValueError
            except (ValueError, TypeError, IndexError):
                raise TransportError(
                    "destination_denied", may_have_sent=False
                ) from None
            selected = ipaddress.ip_address(addresses[0])
            family = socket.AF_INET if selected.version == 4 else socket.AF_INET6
            raw = self._socket_factory(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            raw.settimeout(_remaining(deadline))
            endpoint = (
                (str(selected), port)
                if selected.version == 4
                else (str(selected), port, 0, 0)
            )
            raw.connect(endpoint)
            self._check_peer(raw, selected, port)
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            if (
                context.check_hostname is not True
                or context.verify_mode != ssl.CERT_REQUIRED
            ):
                raise TransportError("tls_unavailable", may_have_sent=False)
            raw.settimeout(_remaining(deadline))
            tls = context.wrap_socket(raw, server_hostname=host)
            self._check_peer(tls, selected, port)
            connection = http.client.HTTPConnection(
                host, port, timeout=_remaining(deadline)
            )
            connection.sock = _DeadlineSocket(tls, deadline)
            may_have_sent = True
            connection.request(
                method,
                path,
                body=payload_bytes,
                headers={
                    "Host": parsed.netloc,
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2026-03-10",
                    "Content-Type": "application/json",
                    "User-Agent": "DeployWhisper-registered-handoff",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise TransportError("redirect_denied", may_have_sent=True)
            if (
                response.length is not None
                and response.length > self.max_response_bytes
            ):
                raise TransportError("response_too_large", may_have_sent=True)
            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise TransportError("response_too_large", may_have_sent=True)
            if response.length not in (None, 0):
                raise TransportError("delivery_unknown", may_have_sent=True)
            return DispatchResponse(status=response.status, body=body)
        except TransportError:
            raise
        except Exception:
            raise TransportError(
                "delivery_unknown" if may_have_sent else "connection_failed",
                may_have_sent=may_have_sent,
            ) from None
        finally:
            # Close failures must not replace the screened delivery classification.
            for resource in (connection, tls, raw):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        pass

    @staticmethod
    def _check_peer(sock, selected, port):
        try:
            peer = sock.getpeername()
            if (
                "%" in peer[0]
                or ipaddress.ip_address(peer[0]) != selected
                or peer[1] != port
                or (len(peer) > 3 and peer[3] != 0)
            ):
                raise ValueError
        except (ValueError, TypeError, IndexError):
            raise TransportError("peer_mismatch", may_have_sent=False) from None
