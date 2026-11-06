"""Signed admission exercises real API/service gates with isolated synthetic data.

ASGI HTTPS metadata and registered handler stand-ins do not qualify live TLS or
collection. Every database, key reference and credential belongs to this fixture.
"""

from __future__ import annotations

import copy
from datetime import timedelta
import hashlib
import json
import logging
import os
import secrets
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock, patch

import config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.routes import auth as human_identity
from api.routes import infra_automation as human_routes
from api.routes import infra_automation_triggers as routes
from infra_automation.trigger_signing import (
    KEY_ID_HEADER,
    NONCE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    sign_request,
)
from models.repositories import infra_automation_runs as run_repository
from models.tables import (
    IdentityAccount,
    IdentitySession,
    InfraAutomationRun,
    InfraAutomationTriggerNonce,
)
from services.identity_service import password_verifier
from services import infra_automation_trigger_authority as authority
from tests.test_infra_automation import test_engine_service as engine_fixture
from tests.test_infra_automation import test_trigger_intake as intake_fixture

WEBHOOK = "/api/v1/infra-automation/triggers/webhook"


class _Messages(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class TriggerAdmissionApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = intake_fixture.TriggerIntakeTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.factory = self.fixture.factory
        self.counter = 0
        for target, value in (
            ("models.database.SessionLocal", self.factory),
            ("services.identity_service.SessionLocal", self.factory),
            ("services.infra_automation_trigger_authority.SessionLocal", self.factory),
        ):
            context = patch(target, value)
            context.start()
            self.addCleanup(context.stop)
        for target in (
            "api.dependencies.identity_service",
            "api.routes.infra_automation_triggers.identity_service",
        ):
            context = patch(target, return_value=self.fixture.identity)
            context.start()
            self.addCleanup(context.stop)
        for target, result in (
            (
                "infra_automation.local_workers.default_registry",
                engine_fixture.AvailableHandlers(),
            ),
            (
                "services.infra_automation_collection.configured_registry",
                self.fixture.registry,
            ),
        ):
            context = patch(target, return_value=result)
            context.start()
            self.addCleanup(context.stop)
        self.app = FastAPI()
        self.app.include_router(routes.router)
        self.app.include_router(routes.human_router)
        self.app.include_router(human_routes.router)
        self.app.include_router(human_identity.router)
        self.client = self.new_client()

    def new_client(self, *, follow_redirects=False):
        client = TestClient(
            self.app, base_url=self.fixture.origin, follow_redirects=follow_redirects
        )
        self.addCleanup(client.close)
        return client

    def raw(self, payload=None):
        return json.dumps(self.fixture.payload if payload is None else payload).encode()

    def signed_headers(
        self, body, *, path=WEBHOOK, nonce=None, timestamp=None, origin=False
    ):
        self.counter += 1
        fields = {
            "key_id": self.fixture.key["key_id"],
            "method": "POST",
            "path": path,
            "timestamp": timestamp or str(int(self.fixture.now.timestamp())),
            "nonce": nonce or f"http-nonce-{self.counter:024}",
            "body": body,
        }
        headers = {
            "Content-Type": "application/json",
            KEY_ID_HEADER: fields["key_id"],
            TIMESTAMP_HEADER: fields["timestamp"],
            NONCE_HEADER: fields["nonce"],
            SIGNATURE_HEADER: sign_request(self.fixture.secret, **fields),
        }
        if origin:
            headers["Origin"] = self.fixture.origin
        return headers

    def counts(self):
        with self.factory() as session:
            return (
                session.scalar(select(func.count()).select_from(InfraAutomationRun)),
                session.scalar(
                    select(func.count()).select_from(InfraAutomationTriggerNonce)
                ),
            )

    def assert_safe_error(self, response, expected):
        self.assertEqual(response.status_code, expected, response.text)
        value = response.json()
        self.assertEqual(set(value), {"error"})
        self.assertEqual(
            set(value["error"]["details"]), {"retryable", "correlation_id"}
        )
        self.assertRegex(value["error"]["details"]["correlation_id"], r"^[a-f0-9]{32}$")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn(self.fixture.secret.hex(), response.text)
        self.assertNotIn("SYNTHETIC_TRIGGER_KEY", response.text)

    def test_real_admission_without_browser_origin_and_fresh_nonce_replay(self):
        body = self.raw()
        headers = self.signed_headers(body)
        headers.update({"X-Role": "admin", "X-Actor": "human-a", "X-Origin": "manual"})
        first = self.client.post(WEBHOOK, content=body, headers=headers)
        self.assertEqual(first.status_code, 200, first.text)
        original = first.json()["data"]
        self.assertEqual(original["origin"]["principal_type"], "service")
        self.assertEqual(original["origin"]["kind"], "webhook")
        self.assertEqual(original["requested_by"], self.fixture.machine["principal_id"])
        second = self.client.post(
            WEBHOOK, content=body, headers=self.signed_headers(body)
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["data"]["id"], original["id"])
        self.assertEqual(self.counts(), (1, 2))
        with self.factory() as session:
            self.assertIsNotNone(run_repository.get_run(session, original["id"]))
        conflict = self.raw({**self.fixture.payload, "inputs": {"different": "value"}})
        rejected = self.client.post(
            WEBHOOK, content=conflict, headers=self.signed_headers(conflict)
        )
        self.assert_safe_error(rejected, 409)
        self.assertEqual(self.counts(), (1, 3))

    def test_nonce_survives_invalid_parse_and_new_http_client(self):
        body = b'{"secret-looking-unknown-field":'
        headers = self.signed_headers(body, nonce="restart-nonce-00000001")
        original_parser = routes._bounded_body

        async def observe_reservation(*args, **kwargs):
            self.assertEqual(self.counts(), (0, 1))
            await original_parser(*args, **kwargs)

        with patch.object(routes, "_bounded_body", side_effect=observe_reservation):
            first = self.client.post(WEBHOOK, content=body, headers=headers)
        self.assert_safe_error(first, 422)
        self.assertNotIn("secret-looking", first.text)
        restarted = self.new_client()
        with patch.object(
            routes,
            "_bounded_body",
            AsyncMock(side_effect=AssertionError("Replay parsed")),
        ):
            replay = restarted.post(WEBHOOK, content=body, headers=headers)
        self.assert_safe_error(replay, 401)
        self.assertEqual(self.counts(), (0, 1))

    def test_nonce_replay_survives_a_fresh_python_process(self):
        body = b'{"invalid":'
        fields = {
            "key_id": self.fixture.key["key_id"],
            "method": "POST",
            "path": WEBHOOK,
            "timestamp": str(int(self.fixture.now.timestamp())),
            "nonce": "process-restart-nonce-0001",
            "body": body.decode(),
        }
        headers = self.signed_headers(body, nonce=fields["nonce"])
        fields["signature"] = headers[SIGNATURE_HEADER]
        response = self.client.post(WEBHOOK, content=body, headers=headers)
        self.assert_safe_error(response, 422)
        source = """
import json, sys
from infra_automation.lifecycle import LifecycleError
from services.infra_automation_trigger_authority import TriggerAuthority
fields = json.loads(sys.stdin.read())
fields['body'] = fields['body'].encode()
try:
    TriggerAuthority(**fields).reserve_nonce()
except LifecycleError as error:
    if error.status_code == 401:
        print('durable replay rejected')
        raise SystemExit(0)
except Exception:
    pass
print('unexpected replay outcome')
raise SystemExit(1)
"""
        environment = {
            **os.environ,
            "DATABASE_URL": str(self.fixture.engine.url),
            "DEPLOYWHISPER_IDENTITY_PROFILE": "https",
            "DEPLOYWHISPER_IDENTITY_ORIGIN": self.fixture.origin,
            "DEPLOYWHISPER_AUTHORIZATION_PROFILE": "verified",
            "DEPLOYWHISPER_TRIGGER_KEYS_PATH": config.settings.trigger_keys_path,
            "DEPLOYWHISPER_TRIGGER_KEYS_SHA256": config.settings.trigger_keys_sha256,
        }
        result = subprocess.run(
            [sys.executable, "-c", source],
            input=json.dumps(fields),
            text=True,
            capture_output=True,
            env=environment,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.strip(), "durable replay rejected")
        self.assertEqual(self.counts(), (0, 1))

    def test_raw_authentication_failures_never_parse_or_reserve(self):
        body = self.raw()
        valid = self.signed_headers(body)
        cases = [
            (body, {**valid, SIGNATURE_HEADER: "sha256=" + "0" * 64}),
            (body + b" ", valid),
            (
                body,
                self.signed_headers(
                    body, timestamp=str(int(self.fixture.now.timestamp()) - 300)
                ),
            ),
            (
                body,
                self.signed_headers(
                    body, timestamp=str(int(self.fixture.now.timestamp()) + 301)
                ),
            ),
            (body, {**valid, KEY_ID_HEADER: "unknown-key"}),
            (b"x" * 131073, valid),
        ]
        recorder = _Messages()
        logger = logging.getLogger()
        logger.addHandler(recorder)
        self.addCleanup(logger.removeHandler, recorder)
        for raw, headers in cases:
            with self.subTest(length=len(raw), key=headers[KEY_ID_HEADER]):
                with patch.object(
                    routes,
                    "_bounded_body",
                    AsyncMock(side_effect=AssertionError("Unauthenticated parse")),
                ):
                    response = self.client.post(WEBHOOK, content=raw, headers=headers)
                self.assert_safe_error(response, 429 if len(raw) > 131072 else 401)
                self.assertNotIn(headers[SIGNATURE_HEADER], response.text)
        self.assertEqual(self.counts(), (0, 0))
        self.assertNotIn(self.fixture.secret.hex(), "\n".join(recorder.messages))

    def test_path_method_header_and_transport_aliases_schedule_nothing(self):
        body = self.raw()
        valid = self.signed_headers(body)
        variants = [
            (WEBHOOK + "?project_id=200", valid),
            (WEBHOOK.replace("webhook", "%77ebhook"), valid),
            (WEBHOOK, list(valid.items()) + [(KEY_ID_HEADER, valid[KEY_ID_HEADER])]),
            (
                WEBHOOK,
                list(valid.items()) + [(TIMESTAMP_HEADER, valid[TIMESTAMP_HEADER])],
            ),
            (
                WEBHOOK,
                list(valid.items()) + [(SIGNATURE_HEADER, valid[SIGNATURE_HEADER])],
            ),
            (
                WEBHOOK,
                {
                    **valid,
                    "Cookie": "__Host-dw-session=" + self.fixture.tokens["human-a"][0],
                },
            ),
            (WEBHOOK, {**valid, "Authorization": "Bearer synthetic-wrong-audience"}),
            (WEBHOOK, {**valid, "Origin": "https://wrong.invalid"}),
            (WEBHOOK, {**valid, "Host": "wrong.invalid"}),
        ]
        for path, headers in variants:
            with self.subTest(path=path, headers=list(dict(headers))):
                response = self.client.post(path, content=body, headers=headers)
                self.assertIn(response.status_code, (401, 403), response.text)
        self.assertEqual(
            self.client.request(
                "GET", WEBHOOK, content=body, headers=valid
            ).status_code,
            405,
        )
        self.assertEqual(self.counts(), (0, 0))

    def test_aliases_never_consume_nonce_and_all_canonical_operations_still_work(self):
        client = self.new_client(follow_redirects=True)
        cli_payload = copy.deepcopy(self.fixture.payload)
        cli_payload["source"]["origin"] = "cli"
        cli_payload["idempotency_key"] = "cli-operation"
        payloads = [
            (WEBHOOK, self.fixture.payload),
            ("/api/v1/infra-automation/triggers/cli/run", cli_payload),
            (
                "/api/v1/infra-automation/triggers/validate",
                {
                    "project_id": 100,
                    "workspace_id": 100,
                    "definition": json.dumps(self.fixture.definition()),
                },
            ),
            ("/api/v1/infra-automation/triggers/list", {"version": 1, "limit": 1}),
        ]
        original_run = None
        for path, payload in payloads:
            body = self.raw(payload)
            headers = self.signed_headers(body, path=path)
            before = self.counts()
            for suffix in ("/", "//", "/unexpected", "/%2f"):
                with self.subTest(path=path, suffix=suffix):
                    with patch.object(
                        routes, "_bounded_body", wraps=routes._bounded_body
                    ) as parser:
                        response = client.post(
                            path + suffix, content=body, headers=headers
                        )
                    self.assert_safe_error(response, 401)
                    parser.assert_not_awaited()
                    self.assertEqual(self.counts(), before)
            canonical = client.post(path, content=body, headers=headers)
            self.assertEqual(canonical.status_code, 200, canonical.text)
            if path == WEBHOOK:
                original_run = canonical.json()["data"]["id"]
            self.assertEqual(self.counts()[1], before[1] + 1)
        path = "/api/v1/infra-automation/triggers/status"
        body = self.raw({"version": 1, "run_id": original_run})
        headers = self.signed_headers(body, path=path)
        before = self.counts()
        response = client.post(path + "/", content=body, headers=headers)
        self.assert_safe_error(response, 401)
        self.assertEqual(self.counts(), before)
        canonical = client.post(path, content=body, headers=headers)
        self.assertEqual(canonical.status_code, 200, canonical.text)
        self.assertEqual(canonical.json()["data"]["id"], original_run)

    def test_typed_scope_source_unknown_fields_and_duplicate_json_reject_before_run(
        self,
    ):
        candidates = [
            {**self.fixture.payload, "project_id": 200},
            {**self.fixture.payload, "workspace_id": 101},
            {**self.fixture.payload, "actor": "human-a"},
            {**self.fixture.payload, "workflow_revision_id": "unregistered"},
            {**self.fixture.payload, "inputs": {"unknown": "value"}},
        ]
        for source in (
            {"repository_id": "repo", "commit_sha": "main", "origin": "webhook"},
            {"repository_id": "repo", "commit_sha": "b" * 40, "origin": "webhook"},
            {"repository_id": "other", "commit_sha": "a" * 40, "origin": "webhook"},
            {"repository_id": "repo", "commit_sha": "a" * 40, "origin": "cli"},
        ):
            candidates.append({**self.fixture.payload, "source": source})
        bodies = [self.raw(candidate) for candidate in candidates]
        bodies.append(b'{"version":1,"version":1}')
        for body in bodies:
            with self.subTest(body_digest=hashlib.sha256(body).hexdigest()):
                response = self.client.post(
                    WEBHOOK, content=body, headers=self.signed_headers(body)
                )
                self.assertIn(response.status_code, (403, 422), response.text)
                self.assertNotIn("human-a", response.text)
        self.assertEqual(self.counts(), (0, len(bodies)))

    def test_quota_is_closed_and_no_run_or_second_nonce_is_created(self):
        body = b"{}"
        with patch.object(authority, "KEY_NONCES", 1):
            first = self.client.post(
                WEBHOOK, content=body, headers=self.signed_headers(body)
            )
            self.assert_safe_error(first, 422)
            second = self.client.post(
                WEBHOOK, content=self.raw(), headers=self.signed_headers(self.raw())
            )
            self.assert_safe_error(second, 429)
        self.assertEqual(self.counts(), (0, 1))

    def test_agent_uses_same_admission_contract_and_human_routes_stay_human(self):
        with self.factory.begin() as session:
            session.get(
                IdentityAccount, self.fixture.machine["principal_id"]
            ).principal_type = "agent"
        self.fixture.key["principal_type"] = "agent"
        self.fixture.write_key()
        payload = copy.deepcopy(self.fixture.payload)
        payload["source"]["origin"] = "cli"
        path = "/api/v1/infra-automation/triggers/cli/run"
        body = self.raw(payload)
        result = self.client.post(
            path, content=body, headers=self.signed_headers(body, path=path)
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["data"]["origin"]["principal_type"], "agent")
        self.assertEqual(result.json()["data"]["origin"]["kind"], "cli")
        headers = self.signed_headers(body, origin=True)
        for path, value in (
            (
                f"/api/v1/infra-automation/workflows/{self.fixture.workflow}/revisions",
                {
                    "expected_version": 1,
                    "idempotency_key": "forbidden",
                    "reason": "Try publication",
                },
            ),
            (
                "/api/v1/infra-automation/approvals/unknown/decision",
                {
                    "expected_version": 1,
                    "binding_digest": "sha256:" + "a" * 64,
                    "outcome": "approve",
                    "reason": "Try decision",
                },
            ),
        ):
            with self.subTest(path=path):
                rejected = self.client.post(
                    path,
                    json=value,
                    headers={**headers, "X-Role": "admin", "X-Actor": "human-a"},
                )
                self.assertIn(rejected.status_code, (401, 403), rejected.text)
        with self.factory() as session:
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(IdentitySession)
                    .where(
                        IdentitySession.principal_id
                        == self.fixture.machine["principal_id"]
                    )
                ),
                0,
            )

    def test_nonhuman_cannot_login_or_resolve_a_forged_human_session(self):
        password = "synthetic-service-password-only"
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.factory.begin() as session:
            account = session.get(IdentityAccount, self.fixture.machine["principal_id"])
            account.password_verifier = password_verifier(password)
            session.add(
                IdentitySession(
                    id=secrets.token_hex(16),
                    principal_id=account.id,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    csrf_hash=hashlib.sha256(csrf.encode()).hexdigest(),
                    audience="human",
                    security_profile="https",
                    trusted_origin=self.fixture.origin,
                    authentication_version=account.authentication_version,
                    created_at=self.fixture.now,
                    last_seen_at=self.fixture.now,
                    expires_at=self.fixture.now + timedelta(hours=1),
                )
            )
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "synthetic-service", "password": password},
            headers={"Origin": self.fixture.origin},
        )
        self.assertEqual(response.status_code, 401, response.text)
        response = self.client.get(
            "/api/v1/auth/session", headers={"Cookie": "__Host-dw-session=" + token}
        )
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn(password, response.text)
        self.assertNotIn(token, response.text)
