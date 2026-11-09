"""Thin authenticated automation HTTP commands; credentials never become roles."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import http.client
import json
import math
import os
import re
import secrets
import queue
import socket
import ssl
import stat
import sys
import time
import threading
from urllib.parse import urlencode, urlsplit

from api.errors import build_error
from api.schemas import (
    AutomationApprovalResponse,
    AutomationRunListResponse,
    AutomationRunResponse,
    AutomationValidationResponse,
)
from cli.identity import _check_private_descriptor
from infra_automation.contracts import SAFE_INTEGER
from infra_automation.lifecycle import LifecycleError
from infra_automation.trigger_signing import (
    KEY_ID_HEADER,
    TIMESTAMP_HEADER,
    NONCE_HEADER,
    SIGNATURE_HEADER,
    sign_request,
)

MAX_BODY = 131072
MAX_PREFLIGHT_BODY = 12582912
BASE = "/api/v1/infra-automation"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_ENV = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
# Timed-out DNS calls cannot be forcibly interrupted by Python. Keep their
# daemon workers counted until they exit; repeated calls cannot accumulate them.
_TRANSPORT_SLOTS = threading.BoundedSemaphore(4)


class CliError(Exception):
    def __init__(self, status=422):
        self.status = status
        super().__init__("Automation command failed.")


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse otherwise reflects invalid arguments, which may be secrets.
        raise CliError()


@dataclass(frozen=True, repr=False)
class Credentials:
    kind: str
    origin: str
    session_token: str = ""
    csrf_token: str = ""
    key_id: str = ""
    secret_env_ref: str = ""


def build_parser():
    parser = _Parser(description="Use the authenticated versioned automation API.")
    parser.add_argument("--credential-file", required=True)
    parser.add_argument("--url", help="Exact origin pinned in the credential file.")
    parser.add_argument("--timeout", type=int, default=15)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "run"):
        command = commands.add_parser(name)
        command.add_argument("--request", required=True, help="Exact JSON body file.")
        if name == "run":
            command.add_argument("--preflight", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("run_id")
    listing = commands.add_parser("list")
    listing.add_argument("--project-id", type=int)
    listing.add_argument("--workspace-id", type=int)
    listing.add_argument("--workflow-id")
    listing.add_argument("--limit", type=int, default=25)
    listing.add_argument("--cursor")
    decision = commands.add_parser("decision")
    decision.add_argument("approval_id")
    decision.add_argument("--request", required=True)
    return parser


def _origin(value):
    if type(value) is not str or not 1 <= len(value) <= 512:
        raise CliError()
    try:
        value.encode("ascii")
        parsed = urlsplit(value)
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or value != f"{parsed.scheme}://{parsed.netloc}"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "?" in value
            or "#" in value
            or "\\" in value
            or "%" in parsed.netloc
            or any(ord(char) <= 32 or ord(char) >= 127 for char in value)
            or (port is not None and not 1 <= port <= 65535)
            or (
                parsed.scheme == "http"
                and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            )
        ):
            raise CliError()
    except (ValueError, UnicodeError):
        raise CliError() from None
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _integer(value):
    if len(value.lstrip("-")) > 16 or abs(int(value)) > SAFE_INTEGER:
        raise ValueError
    return int(value)


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError
    return result


def _constant(value):
    raise ValueError


def _json(raw, maximum=MAX_BODY):
    if type(raw) is not bytes or len(raw) > maximum:
        raise ValueError
    text = raw.decode("utf-8")
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 16:
                raise ValueError
        elif char in "]}":
            depth -= 1
    return json.loads(
        text,
        object_pairs_hook=_pairs,
        parse_int=_integer,
        parse_float=_float,
        parse_constant=_constant,
    )


def _read_file(path, maximum, *, private=False):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise CliError()
        if private:
            _check_private_descriptor(descriptor)
            if info.st_nlink != 1:
                raise CliError()
        if not 0 < info.st_size <= maximum:
            raise CliError()
        result = bytearray()
        while len(result) <= maximum:
            chunk = os.read(descriptor, min(65536, maximum + 1 - len(result)))
            if not chunk:
                break
            result.extend(chunk)
        if len(result) > maximum:
            raise CliError()
        return bytes(result)
    finally:
        os.close(descriptor)


def _credentials(path):
    value = _json(_read_file(path, 8192, private=True), maximum=8192)
    if type(value) is not dict:
        raise CliError()
    if value.get("kind") == "human":
        if set(value) != {"kind", "origin", "session_token", "csrf_token"} or any(
            type(value.get(field)) is not str or _TOKEN.fullmatch(value[field]) is None
            for field in ("session_token", "csrf_token")
        ):
            raise CliError()
    elif value.get("kind") == "signed":
        if (
            set(value) != {"kind", "origin", "key_id", "secret_env_ref"}
            or type(value.get("key_id")) is not str
            or _IDENTIFIER.fullmatch(value["key_id"]) is None
            or type(value.get("secret_env_ref")) is not str
            or _ENV.fullmatch(value["secret_env_ref"]) is None
        ):
            raise CliError()
    else:
        raise CliError()
    _origin(value.get("origin"))
    return Credentials(**value)


def _id(value):
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise CliError()
    return value


def _positive(value):
    if type(value) is not int or not 1 <= value <= SAFE_INTEGER:
        raise CliError()
    return value


class _TransportDeadline:
    def __init__(self, timeout):
        self.end = time.monotonic() + timeout
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.socket = None

    def remaining(self):
        value = self.end - time.monotonic()
        if self.closed.is_set() or value <= 0:
            raise CliError(503)
        return value

    def watch(self, sock):
        with self.lock:
            try:
                self.remaining()
            except CliError:
                sock.close()
                raise
            self.socket = sock

    def close(self):
        self.closed.set()
        with self.lock:
            sock = self.socket
            self.socket = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def connect(self, address, timeout=None, source_address=None):
        # Separate DNS from connect: a resolver that finishes after cancellation
        # must not initiate even a TCP connection, let alone a late POST.
        answers = socket.getaddrinfo(address[0], address[1], 0, socket.SOCK_STREAM)
        for family, kind, protocol, _, destination in answers:
            self.remaining()
            sock = socket.socket(family, kind, protocol)
            try:
                self.watch(sock)
                sock.settimeout(self.remaining())
                sock.connect(destination)
                self.remaining()
                return sock
            except OSError:
                sock.close()
        raise CliError(503)


class _DeadlineConnection(http.client.HTTPConnection):
    def __init__(self, host, port, deadline):
        super().__init__(host, port, timeout=deadline.remaining())
        self.deadline = deadline
        self._create_connection = deadline.connect
        self.auto_open = 0

    def send(self, data):
        remaining = self.deadline.remaining()
        if self.sock is not None:
            self.sock.settimeout(remaining)
        return super().send(data)


def _exchange(origin, method, path, headers, body, timeout):
    """Bound the complete exchange, including DNS, TLS and trickled headers.

    A deadline seals the result channel and closes the owned socket. Workers
    cannot send after a late DNS/connect return or keep the CLI process alive.
    """
    deadline = _TransportDeadline(timeout)
    slots = _TRANSPORT_SLOTS
    if not slots.acquire(blocking=False):
        raise CliError(503)
    result = queue.Queue(maxsize=1)

    def worker():
        connection = None
        try:
            parsed = urlsplit(origin)
            secure = parsed.scheme == "https"
            connection = _DeadlineConnection(
                parsed.hostname, parsed.port or (443 if secure else 80), deadline
            )
            connection.connect()
            deadline.remaining()
            if secure:
                context = ssl.create_default_context()
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.set_alpn_protocols(["http/1.1"])
                deadline.remaining()
                connection.sock = context.wrap_socket(
                    connection.sock,
                    server_hostname=parsed.hostname,
                    do_handshake_on_connect=False,
                )
                deadline.watch(connection.sock)
                connection.sock.settimeout(deadline.remaining())
                connection.sock.do_handshake()
            deadline.remaining()
            connection.request(
                method, path, body=body, headers={**headers, "Host": parsed.netloc}
            )
            with connection.getresponse() as response:
                raw = bytearray()
                while len(raw) <= MAX_BODY:
                    deadline.remaining()
                    chunk = response.read1(min(8192, MAX_BODY + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                if len(raw) > MAX_BODY:
                    raise CliError(503)
                deadline.remaining()
                result.put_nowait((response.status, bytes(raw)))
        except Exception:
            if not deadline.closed.is_set():
                result.put_nowait(None)
        finally:
            try:
                if connection is not None:
                    connection.close()
            finally:
                slots.release()

    try:
        thread = threading.Thread(target=worker, daemon=True, name="automation-http")
        try:
            thread.start()
        except Exception:
            slots.release()
            raise
        # KeyboardInterrupt during Thread.start may happen after native startup.
        # Keep that ambiguous slot owned by the worker rather than allowing a
        # replacement to escape the concurrency bound. The CLI exits uncertain.
        value = result.get(timeout=deadline.remaining())
        deadline.remaining()
        if value is None:
            raise CliError(503)
        return value
    except queue.Empty:
        raise CliError(503) from None
    finally:
        deadline.close()


def _error(status, body=None):
    value = LifecycleError(status if status in LifecycleError._ERRORS else 503)
    details = {"retryable": value.retryable}
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        candidate = body["error"].get("details")
        if isinstance(candidate, dict):
            correlation = candidate.get("correlation_id")
            if type(correlation) is str and re.fullmatch(r"[a-f0-9]{32}", correlation):
                details["correlation_id"] = correlation
    return build_error(value.code, value.message, details)


def _execute(args, credentials):
    signed = credentials.kind == "signed"
    if not 1 <= args.timeout <= 60:
        raise CliError()
    if args.url is not None and _origin(args.url) != credentials.origin:
        raise CliError()
    if signed and (args.command == "decision" or getattr(args, "preflight", False)):
        raise CliError(403)
    method, raw = "POST", b""
    if args.command in {"run", "validate", "decision"}:
        maximum = (
            MAX_PREFLIGHT_BODY if args.command == "run" and args.preflight else MAX_BODY
        )
        raw = _read_file(args.request, maximum)
        if signed:
            path = BASE + (
                "/triggers/cli/run" if args.command == "run" else "/triggers/validate"
            )
        elif args.command == "run":
            path = BASE + ("/cli/preflights" if args.preflight else "/cli/runs")
        elif args.command == "validate":
            path = BASE + "/workflows/validate"
        else:
            path = BASE + f"/approvals/{_id(args.approval_id)}/decision"
    elif args.command == "status":
        run_id = _id(args.run_id)
        if signed:
            path = BASE + "/triggers/status"
            raw = json.dumps({"version": 1, "run_id": run_id}).encode()
        else:
            method, path = "GET", BASE + f"/runs/{run_id}"
    else:
        if not 1 <= args.limit <= 100:
            raise CliError()
        cursor = _id(args.cursor) if args.cursor is not None else None
        if signed:
            if args.project_id is not None or args.workspace_id is not None:
                raise CliError()
            workflow = _id(args.workflow_id) if args.workflow_id is not None else None
            path = BASE + "/triggers/list"
            raw = json.dumps(
                {
                    "version": 1,
                    "workflow_id": workflow,
                    "limit": args.limit,
                    "cursor": cursor,
                }
            ).encode()
        else:
            if args.workflow_id is not None:
                raise CliError()
            query = {"project_id": _positive(args.project_id), "limit": args.limit}
            if args.workspace_id is not None:
                query["workspace_id"] = _positive(args.workspace_id)
            if cursor is not None:
                query["cursor"] = cursor
            method, path = "GET", BASE + "/runs?" + urlencode(query)
    headers = {"Accept": "application/json", "Origin": credentials.origin}
    if method == "POST":
        headers["Content-Type"] = "application/json"
    sensitive = [credentials.session_token, credentials.csrf_token]
    if signed:
        secret = os.environ.get(credentials.secret_env_ref, "")
        if re.fullmatch(r"[0-9a-fA-F]{64}", secret) is None:
            raise CliError()
        sensitive.extend((secret, secret.lower(), secret.upper()))
        timestamp, nonce = str(int(time.time())), secrets.token_urlsafe(24)
        headers.update(
            {
                KEY_ID_HEADER: credentials.key_id,
                TIMESTAMP_HEADER: timestamp,
                NONCE_HEADER: nonce,
            }
        )
        headers[SIGNATURE_HEADER] = sign_request(
            bytes.fromhex(secret),
            key_id=credentials.key_id,
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=raw,
        )
    else:
        cookie = (
            "__Host-dw-session"
            if credentials.origin.startswith("https:")
            else "dw-local-session"
        )
        headers["Cookie"] = f"{cookie}={credentials.session_token}"
        if method == "POST":
            headers["X-CSRF-Token"] = credentials.csrf_token
    try:
        status, response = _exchange(
            credentials.origin, method, path, headers, raw or None, args.timeout
        )
        try:
            result = _json(response)
        except (ValueError, UnicodeError, RecursionError):
            result = None
        if status < 200 or status >= 300:
            return (2 if status in {400, 413, 422} else 1), _error(status, result)
        if (
            not isinstance(result, dict)
            or set(result) != {"data", "meta"}
            or not isinstance(result["data"], dict)
            or not isinstance(result["meta"], dict)
        ):
            raise CliError(503)
        response_model = {
            "validate": AutomationValidationResponse,
            "run": AutomationRunResponse,
            "status": AutomationRunResponse,
            "list": AutomationRunListResponse,
            "decision": AutomationApprovalResponse,
        }[args.command]
        response_model.model_validate(result)
        encoded = json.dumps(result, ensure_ascii=False)
        if any(value and value in encoded for value in sensitive):
            raise CliError(503)
        return (
            2
            if args.command == "validate" and result["data"].get("valid") is False
            else 0
        ), result
    except CliError:
        raise
    except Exception:
        raise CliError(503) from None


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        credentials = _credentials(args.credential_file)
        code, result = _execute(args, credentials)
    except CliError as error:
        code, result = (2 if error.status == 422 else 1), _error(error.status)
    except KeyboardInterrupt:
        # A request may already have committed before interruption is observed.
        code, result = 1, _error(503)
    except Exception:
        code, result = 2, _error(422)
    print(
        json.dumps(result),
        file=sys.stdout if code == 0 else sys.stderr,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
