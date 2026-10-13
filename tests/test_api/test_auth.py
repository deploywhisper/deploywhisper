"""Human identity HTTP boundary with an isolated production-shaped database."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import config
from app import create_app
from models.database import Base
from models.tables import IdentitySession
from services.identity_service import IdentityService


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'auth.db'}")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.now = datetime(2026, 10, 12, tzinfo=timezone.utc)
        self.origin = "https://identity.invalid"
        self.service = IdentityService(
            self.factory,
            now=lambda: self.now,
            security_profile="https",
            trusted_origin=self.origin,
        )
        setup = self.service.issue_setup_credential()
        self.password = "synthetic browser password"
        self.account = self.service.bootstrap(
            setup.token.get_secret_value(), "operator", self.password
        )
        self.settings_patch = patch.object(
            config,
            "settings",
            replace(
                config.settings, identity_profile="https", identity_origin=self.origin
            ),
        )
        self.settings_patch.start()
        self.service_patch = patch(
            "api.dependencies.identity_service", return_value=self.service
        )
        self.service_patch.start()
        self.client = TestClient(create_app(), base_url=self.origin)

    def tearDown(self):
        self.client.close()
        self.service_patch.stop()
        self.settings_patch.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def login(self, **kwargs):
        return self.client.post(
            "/api/v1/auth/login",
            json={"username": "operator", "password": self.password, **kwargs},
            headers={"Origin": self.origin},
        )

    def test_login_cookie_principal_and_rotation(self):
        response = self.login()
        self.assertEqual(response.status_code, 200, response.text)
        cookie = response.headers["set-cookie"]
        for value in (
            "__Host-dw-session=",
            "HttpOnly",
            "Secure",
            "SameSite=strict",
            "Path=/",
        ):
            self.assertIn(value, cookie)
        self.assertNotIn("Domain=", cookie)
        token = self.client.cookies.get("__Host-dw-session")
        self.assertNotIn(token, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        principal = response.json()["data"]["principal"]
        self.assertEqual(principal["principal_id"], self.account.principal_id)
        current = self.client.get(
            "/api/v1/auth/session",
            headers={"X-Actor": "attacker", "X-Project-Role": "admin"},
        )
        self.assertEqual(
            current.json()["data"]["principal_id"], self.account.principal_id
        )
        csrf = response.json()["data"]["csrf_token"]
        rotated = self.client.post(
            "/api/v1/auth/session/rotate",
            headers={"Origin": self.origin, "X-CSRF-Token": csrf},
        )
        self.assertEqual(rotated.status_code, 200, rotated.text)
        self.assertNotEqual(rotated.json()["data"]["csrf_token"], csrf)
        self.assertNotEqual(self.client.cookies.get("__Host-dw-session"), token)
        from services.identity_service import IdentityError

        with self.assertRaises(IdentityError):
            self.service.resolve_session(token)

    def test_mutation_denial_has_no_database_change(self):
        response = self.login()
        csrf = response.json()["data"]["csrf_token"]
        with self.factory() as db:
            before = db.scalar(select(IdentitySession)).last_seen_at
        self.now += timedelta(seconds=30)
        for headers in (
            {},
            {"Origin": self.origin},
            {"Origin": "https://foreign.invalid", "X-CSRF-Token": csrf},
            {"Origin": "null", "X-CSRF-Token": csrf},
            {"Origin": self.origin, "X-CSRF-Token": "wrong"},
        ):
            denied = self.client.post("/api/v1/auth/logout", headers=headers)
            self.assertEqual(denied.status_code, 403, denied.text)
        with self.factory() as db:
            row = db.scalar(select(IdentitySession))
            self.assertEqual(row.last_seen_at, before)
            self.assertIsNone(row.revoked_at)
        logout = self.client.post(
            "/api/v1/auth/logout", headers={"Origin": self.origin, "X-CSRF-Token": csrf}
        )
        self.assertEqual(logout.status_code, 200, logout.text)
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 401)

    def test_origin_transport_audience_and_forged_headers(self):
        for origin in (None, "null", "https://foreign.invalid"):
            response = self.client.post(
                "/api/v1/auth/login",
                json={"username": "operator", "password": self.password},
                headers={"Origin": origin} if origin else {},
            )
            self.assertEqual(response.status_code, 403)
        for audience in ("service", "agent", "runner", "receiver"):
            self.assertEqual(self.login(audience=audience).status_code, 400)
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/session",
                headers={"X-Actor": "operator", "X-Project-Role": "admin"},
            ).status_code,
            401,
        )
        self.login()
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/session",
                headers={"Authorization": "Bearer synthetic-agent"},
            ).status_code,
            401,
        )
        insecure = TestClient(create_app(), base_url="http://identity.invalid")
        response = insecure.post(
            "/api/v1/auth/login",
            json={"username": "operator", "password": self.password},
            headers={"Origin": self.origin, "X-Forwarded-Proto": "https"},
        )
        self.assertEqual(response.status_code, 403)
        insecure.close()

    def test_bounded_closed_input_errors_do_not_echo_secrets(self):
        for payload in (
            "[]",
            "{",
            '"secret"',
            '{"username":"operator","password":"' + "x" * 4096 + '"}',
            '{"username":"operator","password":"\\ud800"}',
            '{"synthetic-secret-key":"synthetic-secret-value"}',
        ):
            self.now += timedelta(seconds=60)
            response = self.client.post(
                "/api/v1/auth/login",
                content=payload,
                headers={"Origin": self.origin, "Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, 400, response.text)
            self.assertNotIn("synthetic-secret", response.text)
            self.assertIn("correlation_id", response.json()["error"]["details"])
        for path in ("/api/v1/auth/bootstrap", "/api/v1/auth/recover"):
            self.assertIn(self.client.post(path).status_code, {404, 405})

    def test_account_admin_and_revocation(self):
        csrf = self.login().json()["data"]["csrf_token"]
        headers = {"Origin": self.origin, "X-CSRF-Token": csrf}
        created = self.client.post(
            "/api/v1/auth/accounts",
            headers=headers,
            json={"username": "reviewer", "password": "another synthetic password"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        principal_id = created.json()["data"]["principal_id"]
        user = self.service.login("reviewer", "another synthetic password")
        revoked = self.client.post(
            f"/api/v1/auth/accounts/{principal_id}/revoke", headers=headers
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        from services.identity_service import IdentityError

        with self.assertRaises(IdentityError):
            self.service.resolve_session(user.token.get_secret_value())

    def test_profile_configuration_fails_closed(self):
        for profile, origin in (
            ("disabled", ""),
            ("https", "http://identity.invalid"),
            ("local-development", "http://remote.invalid"),
            ("https", "https://identity.invalid/path"),
        ):
            with patch.object(
                config,
                "settings",
                replace(
                    config.settings, identity_profile=profile, identity_origin=origin
                ),
            ):
                self.assertEqual(self.login().status_code, 403)

    def test_local_profile_cookie_cannot_be_promoted(self):
        origin = "http://localhost:8080"
        service = IdentityService(
            self.factory,
            now=lambda: self.now,
            security_profile="local-development",
            trusted_origin=origin,
        )
        client = TestClient(create_app(), base_url=origin)
        self.addCleanup(client.close)
        with (
            patch.object(
                config,
                "settings",
                replace(
                    config.settings,
                    identity_profile="local-development",
                    identity_origin=origin,
                ),
            ),
            patch("api.dependencies.identity_service", return_value=service),
        ):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "operator", "password": self.password},
                headers={"Origin": origin},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(
                response.json()["data"]["principal"]["production_eligible"]
            )
            self.assertIn("dw-local-session=", response.headers["set-cookie"])
            self.assertNotIn("Secure", response.headers["set-cookie"])
            token = client.cookies.get("dw-local-session")
        response = self.client.get(
            "/api/v1/auth/session", headers={"Cookie": f"__Host-dw-session={token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_duplicate_headers_cookie_and_streamed_overflow_deny(self):
        csrf = self.login().json()["data"]["csrf_token"]
        token = self.client.cookies.get("__Host-dw-session")
        for headers in (
            [("Origin", self.origin), ("Origin", self.origin), ("X-CSRF-Token", csrf)],
            [("Origin", self.origin), ("X-CSRF-Token", csrf), ("X-CSRF-Token", csrf)],
            [
                ("Origin", self.origin),
                ("X-CSRF-Token", csrf),
                ("Cookie", f"__Host-dw-session={token}; __Host-dw-session={token}"),
            ],
        ):
            response = self.client.post("/api/v1/auth/logout", headers=headers)
            self.assertIn(response.status_code, {401, 403})
        response = self.client.post(
            "/api/v1/auth/login",
            content=iter([b'{"username":"operator","password":"', b"x" * 4096, b'"}']),
            headers={
                "Origin": self.origin,
                "Content-Type": "application/json",
                "Content-Length": "1",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 200)

    def test_nonadmin_cannot_create_or_revoke_even_with_role_headers(self):
        admin = self.service.login("operator", self.password)
        self.service.create_account(
            admin.token.get_secret_value(),
            "reader",
            self.password,
            csrf_token=admin.csrf_token.get_secret_value(),
        )
        reader = self.service.login("reader", self.password)
        headers = {
            "Origin": self.origin,
            "Cookie": f"__Host-dw-session={reader.token.get_secret_value()}",
            "X-CSRF-Token": reader.csrf_token.get_secret_value(),
            "X-Project-Role": "admin",
            "X-Actor": "operator",
        }
        created = self.client.post(
            "/api/v1/auth/accounts",
            headers=headers,
            json={"username": "forged", "password": self.password, "is_admin": True},
        )
        self.assertEqual(created.status_code, 403)
        revoked = self.client.post(
            f"/api/v1/auth/accounts/{self.account.principal_id}/revoke", headers=headers
        )
        self.assertEqual(revoked.status_code, 403)

    def test_auth_errors_are_uniform_rate_limited_and_secret_free(self):
        bodies = []
        with self.assertLogs("httpx", level="INFO") as logs:
            for username in ("operator", "missing-account"):
                response = self.client.post(
                    "/api/v1/auth/login",
                    headers={"Origin": self.origin},
                    json={"username": username, "password": "synthetic-wrong-password"},
                )
                self.assertEqual(response.status_code, 401)
                error = response.json()["error"]
                bodies.append((error["code"], error["message"]))
                self.assertNotIn("synthetic-wrong-password", response.text)
            for _ in range(4):
                self.client.post(
                    "/api/v1/auth/login",
                    headers={"Origin": self.origin},
                    json={
                        "username": "operator",
                        "password": "synthetic-wrong-password",
                    },
                )
            response = self.login()
        self.assertEqual(bodies[0], bodies[1])
        self.assertEqual(response.status_code, 429)
        self.assertNotIn(self.password, "\n".join(logs.output))
        self.assertNotIn("synthetic-wrong-password", "\n".join(logs.output))

    def test_openapi_publishes_closed_requests_and_typed_principal(self):
        schema = self.client.get("/api/v1/openapi.json").json()
        login = schema["paths"]["/api/v1/auth/login"]["post"]
        self.assertTrue(
            {"400", "401", "403", "429", "503"}.issubset(login["responses"])
        )
        self.assertFalse(
            login["requestBody"]["content"]["application/json"]["schema"][
                "additionalProperties"
            ]
        )
        self.assertIn(
            "HumanSessionResponse",
            login["responses"]["200"]["content"]["application/json"]["schema"]["$ref"],
        )
        fields = schema["components"]["schemas"]["VerifiedPrincipal"]["properties"]
        self.assertTrue(
            {
                "principal_id",
                "principal_type",
                "credential_audience",
                "session_id",
                "expires_at",
                "authentication_version",
            }.issubset(fields)
        )

    def test_malformed_login_attempts_use_durable_rate_limit(self):
        for _ in range(5):
            response = self.client.post(
                "/api/v1/auth/login",
                content="[]",
                headers={"Origin": self.origin, "Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/api/v1/auth/login",
            content="[]",
            headers={"Origin": self.origin, "Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 429)

    def test_invalid_username_contract_returns_bad_request_for_login_and_accounts(self):
        csrf = self.login().json()["data"]["csrf_token"]
        headers = {"Origin": self.origin, "X-CSRF-Token": csrf}
        for username in ("é" * 65, " operator", "operator ", "oper\x00ator"):
            self.now += timedelta(seconds=60)
            for path in ("/api/v1/auth/login", "/api/v1/auth/accounts"):
                with self.subTest(username=repr(username), path=path):
                    response = self.client.post(
                        path,
                        headers=headers,
                        json={"username": username, "password": self.password},
                    )
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertEqual(
                        response.json()["error"]["code"], "invalid_identity_request"
                    )
                    self.assertNotIn(username, response.text)
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 200)

    def test_runtime_does_not_implicitly_trust_forwarded_transport(self):
        import app
        import uvicorn

        with patch.object(app.uvicorn, "run") as run:
            app.run()
        self.assertIs(run.call_args.kwargs["proxy_headers"], False)
        runtime = uvicorn.Config(
            create_app(), proxy_headers=run.call_args.kwargs["proxy_headers"]
        )
        runtime.load()
        client = TestClient(
            runtime.loaded_app,
            base_url="http://identity.invalid",
            client=("127.0.0.1", 53124),
        )
        self.addCleanup(client.close)
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "operator", "password": self.password},
            headers={"Origin": self.origin, "X-Forwarded-Proto": "https"},
        )
        self.assertEqual(response.status_code, 403)
