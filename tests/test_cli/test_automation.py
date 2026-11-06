"""Authenticated automation CLI preserves wire bytes and separate audiences."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cli import automation
from infra_automation.trigger_signing import verify_request
from datetime import datetime, timezone


def run_envelope():
    from api.schemas import build_meta

    return {
        "data": {
            "id": "run-one",
            "workflow_id": "workflow-one",
            "revision_id": "revision-one",
            "project_id": 7,
            "workspace_id": 9,
            "requested_by": "human-one",
            "state": "queued",
            "version": 1,
            "snapshot_digest": "sha256:" + "a" * 64,
            "definition_digest": "sha256:" + "b" * 64,
            "input_digest": "sha256:" + "c" * 64,
            "created_at": "2026-11-05T00:00:00Z",
            "deadline_at": "2026-11-05T01:00:00Z",
            "cancel_requested": False,
            "cancellation_requested_at": None,
            "origin": None,
        },
        "meta": build_meta(correlation_id="a" * 32),
    }


class AutomationCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.origin = "http://localhost:8080"
        self.token = "TOKEN" + "t" * 38
        self.csrf = "CSRF" + "c" * 39
        self.human = self.file(
            "human.json",
            json.dumps(
                {
                    "kind": "human",
                    "origin": self.origin,
                    "session_token": self.token,
                    "csrf_token": self.csrf,
                }
            ),
            private=True,
        )
        self.signed = self.file(
            "signed.json",
            json.dumps(
                {
                    "kind": "signed",
                    "origin": self.origin,
                    "key_id": "key-one",
                    "secret_env_ref": "DW_TEST_TRIGGER_KEY",
                }
            ),
            private=True,
        )
        self.key = "ab" * 32
        self.env = patch.dict(os.environ, {"DW_TEST_TRIGGER_KEY": self.key})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.body = b'{ "version":1, "value":"synthetic" }\n'
        self.request = self.file("request.json", self.body)
        self.calls = []

    def file(self, name, content, *, private=False):
        path = self.root / name
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        path.chmod(0o600 if private else 0o644)
        return path

    def exchange(self, origin, method, path, headers, body, timeout):
        self.calls.append((origin, method, path, headers, body, timeout))
        result = run_envelope()
        if path.endswith("/triggers/list"):
            result["data"] = {
                "items": [result["data"]],
                "cursor": {
                    "version": 1,
                    "snapshot_id": "snapshot-one",
                    "next_cursor": None,
                    "limit": 3,
                    "last_sequence": 1,
                    "truncated": False,
                    "gap": False,
                },
            }
        return 200, json.dumps(result).encode()

    def run_cli(self, *arguments, credentials=None, exchange=None):
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(
                automation, "_exchange", side_effect=exchange or self.exchange
            ),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            code = automation.main(
                [
                    "--credential-file",
                    str(credentials or self.human),
                    *map(str, arguments),
                ]
            )
        text = out.getvalue() + err.getvalue()
        for secret in (self.token, self.csrf, self.key):
            self.assertNotIn(secret, text)
        return code, json.loads(out.getvalue() or err.getvalue())

    def test_human_run_uses_cli_channel_and_exact_body(self):
        code, result = self.run_cli("run", "--request", self.request)
        self.assertEqual(code, 0)
        self.assertEqual(result["data"]["id"], "run-one")
        origin, method, path, headers, raw, _ = self.calls[0]
        self.assertEqual(
            (origin, method, path),
            (self.origin, "POST", "/api/v1/infra-automation/cli/runs"),
        )
        self.assertEqual(raw, self.body)
        self.assertEqual(headers["Cookie"], f"dw-local-session={self.token}")
        self.assertEqual(headers["X-CSRF-Token"], self.csrf)
        self.assertEqual(headers["Origin"], self.origin)

    def test_signed_raw_body_signature_and_fresh_nonce_on_explicit_repetition(self):
        for _ in range(2):
            code, _ = self.run_cli(
                "run", "--request", self.request, credentials=self.signed
            )
            self.assertEqual(code, 0)
        nonces = []
        for _, method, path, headers, body, _ in self.calls:
            self.assertEqual(path, "/api/v1/infra-automation/triggers/cli/run")
            self.assertEqual(body, self.body)
            self.assertNotIn("Cookie", headers)
            self.assertNotIn("Authorization", headers)
            nonce = headers["X-DeployWhisper-Nonce"]
            nonces.append(nonce)
            verify_request(
                bytes.fromhex(self.key),
                key_id="key-one",
                method=method,
                path=path,
                timestamp=headers["X-DeployWhisper-Timestamp"],
                nonce=nonce,
                body=body,
                signature=headers["X-DeployWhisper-Signature"],
                now=datetime.now(timezone.utc),
            )
        self.assertNotEqual(*nonces)

    def test_machine_decision_and_preflight_deny_without_network(self):
        for arguments in (
            ("decision", "approval-one", "--request", self.request),
            ("run", "--preflight", "--request", self.request),
        ):
            code, result = self.run_cli(*arguments, credentials=self.signed)
            self.assertEqual(code, 1)
            self.assertEqual(result["error"]["code"], "permission_denied")
        self.assertEqual(self.calls, [])

    def test_origin_pinning_and_private_custody_deny_before_network(self):
        code, _ = self.run_cli("--url", "https://other.invalid", "status", "run-one")
        self.assertNotEqual(code, 0)
        self.human.chmod(0o644)
        code, _ = self.run_cli("status", "run-one")
        self.assertNotEqual(code, 0)
        self.human.chmod(0o600)
        link = self.root / "linked.json"
        link.symlink_to(self.human)
        code, _ = self.run_cli("status", "run-one", credentials=link)
        self.assertNotEqual(code, 0)
        self.assertEqual(self.calls, [])

    def test_credential_hardlinks_duplicate_fields_and_invalid_origin_deny(self):
        alias = self.root / "hardlinked.json"
        os.link(self.human, alias)
        code, _ = self.run_cli("status", "run-one")
        self.assertEqual(code, 2)
        alias.unlink()
        self.human.write_text('{"kind":"human","kind":"signed"}')
        code, _ = self.run_cli("status", "run-one")
        self.assertEqual(code, 2)
        for origin in (
            "http://remote.invalid",
            "https://user@remote.invalid",
            "https://remote.invalid/path",
            "https://remote.invalid?",
            "https://remote.invalid#",
        ):
            with self.subTest(origin=origin), self.assertRaises(automation.CliError):
                automation._origin(origin)
        self.assertEqual(self.calls, [])

    def test_preflight_uses_larger_existing_limit_but_normal_request_does_not(self):
        self.request.write_bytes(b" " * 131073)
        code, _ = self.run_cli("run", "--request", self.request)
        self.assertEqual(code, 2)
        self.assertEqual(self.calls, [])
        code, _ = self.run_cli("run", "--preflight", "--request", self.request)
        self.assertEqual(code, 0)
        self.assertEqual(self.calls[0][2], "/api/v1/infra-automation/cli/preflights")
        self.assertEqual(len(self.calls[0][4]), 131073)

    def test_machine_list_is_one_bounded_signed_page(self):
        code, _ = self.run_cli(
            "list",
            "--limit",
            "3",
            "--cursor",
            "cursor-one",
            "--workflow-id",
            "workflow-one",
            credentials=self.signed,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(
            json.loads(self.calls[0][4]),
            {
                "version": 1,
                "workflow_id": "workflow-one",
                "limit": 3,
                "cursor": "cursor-one",
            },
        )

    def test_errors_and_invalid_arguments_never_echo_credentials(self):
        def rejected(*args):
            self.calls.append(args)
            return 403, json.dumps(
                {
                    "error": {
                        "code": "permission_denied",
                        "message": self.key,
                        "details": {"leak": self.token},
                    }
                }
            ).encode()

        code, result = self.run_cli("status", "run-one", exchange=rejected)
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["code"], "permission_denied")
        code, _ = self.run_cli("--unknown", self.key)
        self.assertEqual(code, 2)

    def test_noncanonical_https_scheme_is_rejected_before_credentials_are_sent(self):
        value = json.loads(self.human.read_text())
        value["origin"] = "HTTPS://example.invalid"
        self.human.write_text(json.dumps(value))
        code, result = self.run_cli("status", "run-one")
        self.assertEqual(code, 2)
        self.assertEqual(result["error"]["code"], "request_validation_failed")
        self.assertEqual(self.calls, [])

    def test_canonical_https_uses_secure_human_cookie(self):
        value = json.loads(self.human.read_text())
        value["origin"] = "https://example.invalid"
        self.human.write_text(json.dumps(value))
        code, _ = self.run_cli("status", "run-one")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls[0][3]["Cookie"], f"__Host-dw-session={self.token}")

    def test_interrupted_request_reports_unavailable_not_rejected(self):
        def interrupted(*args):
            raise KeyboardInterrupt()

        code, result = self.run_cli(
            "run", "--request", self.request, exchange=interrupted
        )
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["code"], "authority_unavailable")

    def test_malformed_oversize_and_secret_success_responses_fail_closed(self):
        leaked = run_envelope()
        leaked["data"]["requested_by"] = self.key
        for body in (
            b"not-json",
            b"x" * 131073,
            json.dumps(leaked).encode(),
            b'{"data":{},"meta":{}}',
        ):
            code, _ = self.run_cli(
                "status",
                "run-one",
                credentials=self.signed,
                exchange=lambda *args: (200, body),
            )
            self.assertEqual(code, 1)


class AutomationApiParityTests(unittest.TestCase):
    """Real API/SQL authority; TestClient transport does not claim real TLS proof."""

    def use_fixture(self, fixture):
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def credential(self, fixture, *, signed=False, principal="human-a"):
        path = Path(fixture.temp.name) / f"cli-{principal}-{signed}.json"
        if signed:
            value = {
                "kind": "signed",
                "origin": fixture.origin,
                "key_id": "key-one",
                "secret_env_ref": "SYNTHETIC_TRIGGER_KEY",
            }
        else:
            token, csrf = fixture.tokens[principal]
            value = {
                "kind": "human",
                "origin": fixture.origin,
                "session_token": token,
                "csrf_token": csrf,
            }
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        return path

    def call(self, fixture, client, credentials, *args):
        def exchange(origin, method, path, headers, body, timeout):
            self.assertEqual(origin, fixture.origin)
            response = client.request(
                method, path, headers=headers, content=body, follow_redirects=False
            )
            return response.status_code, response.content

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(automation, "_exchange", side_effect=exchange),
            patch.object(automation.time, "time", return_value=fixture.now.timestamp()),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = automation.main(
                ["--credential-file", str(credentials), *map(str, args)]
            )
        if hasattr(fixture, "secret"):
            self.assertNotIn(
                fixture.secret.hex(), stdout.getvalue() + stderr.getvalue()
            )
        for token, csrf in fixture.tokens.values():
            self.assertNotIn(token, stdout.getvalue() + stderr.getvalue())
            self.assertNotIn(csrf, stdout.getvalue() + stderr.getvalue())
        return code, json.loads(stdout.getvalue() or stderr.getvalue())

    def test_signed_validation_matches_actual_api_and_denies_cross_scope(self):
        from tests.test_api.test_infra_automation_triggers import SignedTriggerApiTests

        fixture = self.use_fixture(SignedTriggerApiTests("runTest"))
        path = Path(fixture.temp.name) / "validate.json"
        payload = {
            "project_id": 100,
            "workspace_id": 100,
            "definition": json.dumps(fixture.definition()),
        }
        raw = json.dumps(payload, indent=2).encode()
        path.write_bytes(raw)
        direct = fixture.client.post(
            "/api/v1/infra-automation/triggers/validate",
            content=raw,
            headers=fixture.headers("/api/v1/infra-automation/triggers/validate", raw),
        )
        code, response = self.call(
            fixture,
            fixture.client,
            self.credential(fixture, signed=True),
            "validate",
            "--request",
            path,
        )
        self.assertEqual((direct.status_code, code), (200, 0))
        self.assertEqual(response["data"], direct.json()["data"])
        payload["project_id"], payload["workspace_id"] = 200, 200
        path.write_text(json.dumps(payload))
        code, response = self.call(
            fixture,
            fixture.client,
            self.credential(fixture, signed=True),
            "validate",
            "--request",
            path,
        )
        self.assertEqual(code, 1)
        self.assertEqual(response["error"]["code"], "permission_denied")

    def test_signed_invalid_json_and_replay_match_closed_api_errors(self):
        from tests.test_api.test_infra_automation_triggers import SignedTriggerApiTests

        fixture = self.use_fixture(SignedTriggerApiTests("runTest"))
        path = Path(fixture.temp.name) / "invalid.json"
        path.write_text('{"broken":')
        credential = self.credential(fixture, signed=True)
        with patch.object(
            automation.secrets, "token_urlsafe", return_value="same-nonce-for-cli-test"
        ):
            code, invalid = self.call(
                fixture, fixture.client, credential, "validate", "--request", path
            )
            self.assertEqual(code, 2)
            self.assertEqual(invalid["error"]["code"], "request_validation_failed")
            code, replay = self.call(
                fixture, fixture.client, credential, "validate", "--request", path
            )
            self.assertEqual(code, 1)
            self.assertEqual(replay["error"]["code"], "authentication_required")

    def test_human_preflight_status_and_list_use_actual_server_cli_origin(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.infra_automation import router
        from api.routes.infra_automation_triggers import human_router
        from tests.test_infra_automation.test_preflight_service import (
            PreflightServiceTests,
        )

        fixture = self.use_fixture(PreflightServiceTests("runTest"))
        app = FastAPI()
        app.include_router(router)
        app.include_router(human_router)
        client = TestClient(app, base_url=fixture.origin)
        self.addCleanup(client.close)
        credential = self.credential(fixture)
        path = Path(fixture.temp.name) / "preflight.json"
        path.write_text(fixture.request.model_dump_json())
        with patch("api.dependencies.identity_service", return_value=fixture.identity):
            code, response = self.call(
                fixture, client, credential, "run", "--preflight", "--request", path
            )
            self.assertEqual(code, 0, response)
            run = response["data"]
            self.assertEqual(run["origin"]["kind"], "cli")
            self.assertEqual(run["origin"]["principal_type"], "human")
            fixture.execute(run)
            code, response = self.call(fixture, client, credential, "status", run["id"])
            self.assertEqual(code, 0, response)
            self.assertEqual(response["data"]["id"], run["id"])
            code, response = self.call(
                fixture,
                client,
                credential,
                "list",
                "--project-id",
                "100",
                "--workspace-id",
                "100",
                "--limit",
                "1",
            )
            self.assertEqual(code, 0, response)
            self.assertEqual(
                [item["id"] for item in response["data"]["items"]], [run["id"]]
            )
            self.assertEqual(response["data"]["cursor"]["limit"], 1)

    def test_human_cli_decision_keeps_exact_binding_and_separation(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.infra_automation import router
        from tests.test_infra_automation.test_decision_service import (
            DecisionServiceTests,
        )
        from services import infra_automation_decisions as decisions

        fixture = self.use_fixture(DecisionServiceTests("runTest"))
        pending = fixture.pending()
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, base_url=fixture.origin)
        self.addCleanup(client.close)
        path = Path(fixture.temp.name) / "decision.json"
        payload = fixture.request(pending).model_dump(mode="json")
        path.write_text(json.dumps(payload))
        with (
            patch("api.dependencies.identity_service", return_value=fixture.identity),
            patch.object(decisions, "_default_service", fixture.service),
        ):
            code, response = self.call(
                fixture,
                client,
                self.credential(fixture),
                "decision",
                pending["id"],
                "--request",
                path,
            )
            self.assertEqual(code, 1)
            self.assertEqual(response["error"]["code"], "permission_denied")
            payload["binding_digest"] = "sha256:" + "f" * 64
            path.write_text(json.dumps(payload))
            code, response = self.call(
                fixture,
                client,
                self.credential(fixture, principal="reviewer"),
                "decision",
                pending["id"],
                "--request",
                path,
            )
            self.assertEqual(code, 1)
            self.assertEqual(response["error"]["code"], "binding_conflict")
            payload["binding_digest"] = pending["binding_digest"]
            path.write_text(json.dumps(payload))
            code, response = self.call(
                fixture,
                client,
                self.credential(fixture, principal="reviewer"),
                "decision",
                pending["id"],
                "--request",
                path,
            )
            self.assertEqual(code, 0, response)
            self.assertEqual(response["data"]["status"], "approved")
            self.assertEqual(response["data"]["decision_kind"], "independent-approval")
            self.assertEqual(
                response["data"]["binding_digest"], pending["binding_digest"]
            )

    def test_signed_cli_run_replay_status_and_list_preserve_machine_origin(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from sqlalchemy import select, func
        from api.routes.infra_automation_triggers import router
        from tests.test_infra_automation.test_trigger_intake import TriggerIntakeTests
        from tests.test_infra_automation.test_engine_service import AvailableHandlers
        from services import infra_automation_triggers as triggers
        from models.tables import InfraAutomationRun, IdentitySession

        fixture = self.use_fixture(TriggerIntakeTests("runTest"))
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, base_url=fixture.origin)
        self.addCleanup(client.close)
        credential = self.credential(fixture, signed=True)
        payload = dict(fixture.payload)
        payload["source"] = {**payload["source"], "origin": "cli"}
        path = Path(fixture.temp.name) / "machine-run.json"
        path.write_text(json.dumps(payload, indent=2))
        original = triggers.request_trigger

        def request(value):
            return original(
                value, registry=AvailableHandlers(), registry_contract=fixture.registry
            )

        with (
            patch(
                "api.routes.infra_automation_triggers.identity_service",
                return_value=fixture.identity,
            ),
            patch.object(triggers, "request_trigger", side_effect=request),
        ):
            first, response = self.call(
                fixture, client, credential, "run", "--request", path
            )
            self.assertEqual(first, 0, response)
            run = response["data"]
            self.assertEqual(run["origin"]["kind"], "cli")
            self.assertEqual(run["origin"]["principal_type"], "service")
            code, replay = self.call(
                fixture, client, credential, "run", "--request", path
            )
            self.assertEqual(code, 0, replay)
            self.assertEqual(replay["data"]["id"], run["id"])
            code, status = self.call(fixture, client, credential, "status", run["id"])
            self.assertEqual(code, 0, status)
            self.assertEqual(status["data"]["id"], run["id"])
            code, listing = self.call(
                fixture,
                client,
                credential,
                "list",
                "--limit",
                "1",
                "--workflow-id",
                fixture.workflow,
            )
            self.assertEqual(code, 0, listing)
            self.assertEqual(
                [item["id"] for item in listing["data"]["items"]], [run["id"]]
            )
        with fixture.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationRun)), 1
            )
            self.assertEqual(
                db.scalar(
                    select(func.count())
                    .select_from(IdentitySession)
                    .where(
                        IdentitySession.principal_id == fixture.machine["principal_id"]
                    )
                ),
                0,
            )


class AutomationTransportTests(unittest.TestCase):
    def setUp(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        self.seen = []
        self.stop = threading.Event()
        seen = self.seen
        stop = self.stop

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append((self.path, dict(self.headers)))
                if self.path == "/trickle":
                    try:
                        self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                        self.wfile.flush()
                        for _ in range(40):
                            if stop.wait(0.04):
                                return
                            self.wfile.write(b"x")
                            self.wfile.flush()
                        self.wfile.write(b"\r\nContent-Length: 2\r\n\r\n{}")
                    except OSError:
                        pass
                    return
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/secret-sink")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(
                        b"x" * (automation.MAX_BODY + 1)
                        if self.path == "/oversized"
                        else b'{"data":{},"meta":{}}'
                    )

            do_POST = do_GET

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()

        def close():
            self.stop.set()
            self.server.shutdown()
            self.server.server_close()
            thread.join(timeout=2)

        self.addCleanup(close)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def test_real_http_does_not_follow_redirect_or_honor_ambient_proxy(self):
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1",
                "ALL_PROXY": "http://127.0.0.1:1",
            },
        ):
            status, body = automation._exchange(
                self.origin, "GET", "/redirect", {"Cookie": "synthetic-cookie"}, None, 2
            )
            self.assertEqual(status, 302)
            self.assertEqual([path for path, _ in self.seen], ["/redirect"])
            status, body = automation._exchange(self.origin, "GET", "/ok", {}, None, 2)
            self.assertEqual(
                (status, json.loads(body)), (200, {"data": {}, "meta": {}})
            )

    def test_real_http_oversize_is_bounded(self):
        with self.assertRaises(automation.CliError):
            automation._exchange(self.origin, "GET", "/oversized", {}, None, 2)

    def test_trickled_headers_cannot_extend_total_deadline(self):
        import time

        started = time.monotonic()
        with self.assertRaises(automation.CliError) as caught:
            automation._exchange(self.origin, "GET", "/trickle", {}, None, 0.2)
        self.assertEqual(caught.exception.status, 503)
        self.assertLess(time.monotonic() - started, 0.65)

    def test_late_dns_never_sends_request_and_transport_capacity_is_bounded(self):
        import socket
        import threading
        import time

        resolve = socket.getaddrinfo
        release = threading.Event()
        resolved = threading.Event()

        def delayed(*args, **kwargs):
            release.wait(0.8)
            try:
                return resolve(*args, **kwargs)
            finally:
                resolved.set()

        timer = threading.Timer(0.7, release.set)
        timer.start()
        slots = threading.BoundedSemaphore(1)
        try:
            with (
                patch.object(socket, "getaddrinfo", side_effect=delayed) as lookup,
                patch.object(automation, "_TRANSPORT_SLOTS", slots),
            ):
                started = time.monotonic()
                with self.assertRaises(automation.CliError):
                    automation._exchange(self.origin, "POST", "/late", {}, b"{}", 0.1)
                self.assertLess(time.monotonic() - started, 0.4)
                # A timed-out resolver still owns its slot until it really exits.
                with self.assertRaises(automation.CliError):
                    automation._exchange(self.origin, "POST", "/extra", {}, b"{}", 0.1)
                self.assertEqual(lookup.call_count, 1)
                release.set()
                self.assertTrue(resolved.wait(1))
                self.assertTrue(slots.acquire(timeout=1))
                slots.release()
                self.assertEqual(lookup.call_count, 1)
            self.assertEqual(self.seen, [])
            with patch.object(automation, "_TRANSPORT_SLOTS", slots):
                self.assertEqual(
                    automation._exchange(self.origin, "GET", "/ok", {}, None, 1)[0],
                    200,
                )
        finally:
            release.set()
            timer.cancel()
            timer.join(timeout=1)

    def test_interrupted_thread_start_keeps_slot_until_worker_exits(self):
        import socket
        import threading

        resolve = socket.getaddrinfo
        start = threading.Thread.start
        entered, release = threading.Event(), threading.Event()
        slots = threading.BoundedSemaphore(1)

        def delayed(*args, **kwargs):
            entered.set()
            release.wait(1)
            return resolve(*args, **kwargs)

        def interrupted(thread):
            start(thread)
            self.assertTrue(entered.wait(1))
            raise KeyboardInterrupt()

        try:
            with (
                patch.object(socket, "getaddrinfo", side_effect=delayed),
                patch.object(
                    threading.Thread, "start", side_effect=interrupted, autospec=True
                ),
                patch.object(automation, "_TRANSPORT_SLOTS", slots),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    automation._exchange(self.origin, "POST", "/late", {}, b"{}", 2)
                self.assertFalse(slots.acquire(blocking=False))
                release.set()
                self.assertTrue(slots.acquire(timeout=1))
                slots.release()
            self.assertEqual(self.seen, [])
        finally:
            release.set()


class AutomationTlsTests(unittest.TestCase):
    def test_real_tls_requires_trust_and_checks_hostname(self):
        from datetime import timedelta
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import ssl
        import threading
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        with tempfile.TemporaryDirectory() as directory:
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
            now = datetime.now(timezone.utc)
            certificate = (
                x509.CertificateBuilder()
                .subject_name(name)
                .issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=1))
                .not_valid_after(now + timedelta(days=1))
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName("localhost")]),
                    critical=False,
                )
                .sign(key, hashes.SHA256())
            )
            cert_path, key_path = (
                Path(directory) / "cert.pem",
                Path(directory) / "key.pem",
            )
            cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            key_path.chmod(0o600)
            seen = []

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    seen.append(self.path)
                    self.send_response(200)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"{}")

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert_path, key_path)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                origin = f"https://localhost:{server.server_port}"
                with self.assertRaises(automation.CliError):
                    automation._exchange(origin, "GET", "/untrusted", {}, None, 2)
                trusted = ssl.create_default_context(cafile=str(cert_path))
                self.assertTrue(trusted.check_hostname)
                self.assertEqual(trusted.verify_mode, ssl.CERT_REQUIRED)
                with patch.object(
                    automation.ssl, "create_default_context", return_value=trusted
                ):
                    with self.assertRaises(automation.CliError):
                        automation._exchange(
                            f"https://127.0.0.1:{server.server_port}",
                            "GET",
                            "/wrong-host",
                            {},
                            None,
                            2,
                        )
                    self.assertEqual(
                        automation._exchange(origin, "GET", "/trusted", {}, None, 2),
                        (200, b"{}"),
                    )
                self.assertEqual(seen, ["/trusted"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


class AutomationDispatchTests(unittest.TestCase):
    def test_existing_console_and_script_entry_use_dedicated_adapter(self):
        from cli import analyze

        with (
            patch.object(
                sys,
                "argv",
                [
                    "deploywhisper",
                    "automation",
                    "--credential-file",
                    "private.json",
                    "status",
                    "run-one",
                ],
            ),
            patch.object(automation, "main", return_value=0) as invoke,
            patch.object(
                analyze,
                "_project_authorization_from_env",
                side_effect=AssertionError("Legacy identity used"),
            ),
        ):
            with self.assertRaises(SystemExit) as caught:
                analyze.main()
        self.assertEqual(caught.exception.code, 0)
        invoke.assert_called_once_with(
            ["--credential-file", "private.json", "status", "run-one"]
        )
        self.assertIn("automation", analyze.build_parser().format_help())
