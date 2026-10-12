"""Disposable WP2 qualification; never imports the production application/database."""

from __future__ import annotations

import importlib.util
import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import secrets
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures/infra_automation/qualification/16_0/identity/prototype.py"
)
spec = importlib.util.spec_from_file_location("identity_qualification", FIXTURE)
prototype = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prototype)


class IdentityQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix_metrics = None
        cls.password = secrets.token_urlsafe(24)
        cls.verifier = prototype.password_verifier(cls.password)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = prototype.IdentityStore(Path(self.temp.name) / "identity.sqlite")
        self.store.add_account("human", self.verifier)
        self.store.membership("human", "project", "workspace", "admin")
        self.client = TestClient(
            prototype.make_app(self.store), base_url="https://qualify.invalid"
        )

    def tearDown(self):
        self.client.close()
        self.store.close()
        self.temp.cleanup()

    def test_bootstrap_one_use_expiry_and_no_default_account(self):
        with prototype.IdentityStore(
            Path(self.temp.name) / "bootstrap.sqlite"
        ) as fresh:
            self.assertFalse(fresh.login("admin", self.password, now=0))
            token = fresh.bootstrap_token(now=0)
            self.assertNotIn(token, "\n".join(fresh.db.iterdump()))
            self.assertFalse(
                fresh.bootstrap("invented", "operator", self.password, now=1)
            )
            self.assertTrue(fresh.bootstrap(token, "operator", self.password, now=1))
            self.assertFalse(fresh.bootstrap(token, "second", self.password, now=2))
            self.assertEqual(
                fresh.db.execute("SELECT used FROM bootstrap").fetchone()[0], 1
            )
        with prototype.IdentityStore(
            Path(self.temp.name) / "expired.sqlite"
        ) as expired:
            token = expired.bootstrap_token(now=0)
            self.assertFalse(expired.bootstrap(token, "late", self.password, now=300))
            self.assertFalse(expired.db.execute("SELECT 1 FROM accounts").fetchone())

    def test_global_login_cost_and_concurrency_are_bounded(self):
        self.store.login_lock.acquire()
        try:
            self.assertIsNone(self.store.login("human", self.password, now=0))
        finally:
            self.store.login_lock.release()
        self.store.global_window = 0
        self.store.global_attempts = 20
        self.assertIsNone(self.store.login("human", self.password, now=1))
        self.assertIsNotNone(self.store.login("human", self.password, now=60))
        for index in range(19):
            self.assertIsNone(self.store.login(f"unknown-{index}", "wrong", now=61))
        self.assertEqual(self.store.global_attempts, 20)
        self.assertIsNone(self.store.login("human", self.password, now=62))
        self.assertLessEqual(
            self.store.db.execute("SELECT COUNT(*) FROM login_limits").fetchone()[0], 20
        )
        # Staggered principal windows must not grow the table when global time resets.
        self.assertIsNone(self.store.login("next-window", "wrong", now=120))
        self.assertIsNone(self.store.login("overflow", "wrong", now=120))
        self.assertEqual(
            self.store.db.execute("SELECT COUNT(*) FROM login_limits").fetchone()[0], 20
        )

    def test_salted_fixed_cost_password_verifier(self):
        second = prototype.password_verifier(self.password)
        self.assertNotEqual(self.verifier, second)
        self.assertTrue(prototype.verify_password(self.password, self.verifier))
        self.assertFalse(prototype.verify_password("incorrect", self.verifier))
        for value in (
            "sha256$weak",
            self.verifier.replace("600000", "1"),
            self.verifier.replace("600000", "999999999"),
        ):
            self.assertFalse(prototype.verify_password(self.password, value))
        self.assertFalse(prototype.verify_password("x" * 1025, self.verifier))
        self.assertEqual(prototype.ITERATIONS, 600_000)

    def test_login_bounds_and_hash_only_storage(self):
        for _ in range(5):
            self.assertIsNone(self.store.login("human", "wrong", now=0))
        self.assertIsNone(self.store.login("human", self.password, now=1))
        token, csrf = self.store.login("human", self.password, now=61)
        dump = "\n".join(self.store.db.iterdump())
        self.assertNotIn(token, dump)
        self.assertNotIn(csrf, dump)
        self.assertNotIn(self.password, dump)
        self.assertGreaterEqual(len(token), 43)
        self.assertIsNone(self.store.resolve("invented", "human", now=62))

    def test_login_fixation_and_cookie_policy(self):
        previous, _ = self.store.issue("human", "human")
        self.client.cookies.set("__Host-session", "attacker-fixed")
        response = self.client.post(
            "/login",
            json={"username": "human", "password": self.password},
            headers={"Origin": prototype.ORIGIN},
        )
        self.assertEqual(response.status_code, 200)
        cookie = response.headers["set-cookie"]
        for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
            self.assertIn(flag, cookie)
        self.assertNotIn("Domain=", cookie)
        self.assertNotIn("attacker-fixed", cookie)
        self.assertIsNone(self.store.resolve("attacker-fixed", "human"))
        self.assertIsNone(self.store.resolve(previous, "human"))

    def test_session_rotation_idle_absolute_and_logout(self):
        token, _ = self.store.issue("human", "human", now=0)
        rotated, _ = self.store.rotate(token, now=1)
        self.assertIsNone(self.store.resolve(token, "human", now=2))
        self.assertIsNotNone(self.store.resolve(rotated, "human", now=2))
        self.assertIsNone(self.store.resolve(rotated, "human", now=302))
        token, _ = self.store.issue("human", "human", now=0)
        for time in range(200, 3600, 200):
            self.assertIsNotNone(self.store.resolve(token, "human", now=time))
        self.assertIsNone(self.store.resolve(token, "human", now=3600))
        token, _ = self.store.issue("human", "human", now=0)
        self.store.logout(token)
        self.assertIsNone(self.store.resolve(token, "human", now=1))

    def test_rotation_preserves_original_absolute_authentication_deadline(self):
        token, _ = self.store.issue("human", "human", now=0)
        for now in range(200, 3600, 200):
            token, _ = self.store.rotate(token, now=now)
        self.assertIsNone(self.store.rotate(token, now=3600))
        self.assertIsNone(self.store.resolve(token, "human", now=3600))

    def test_unencodable_password_denied_at_request_and_verifier_boundary(self):
        malformed = "\ud800"
        self.assertFalse(prototype.verify_password(malformed, self.verifier))
        with self.assertRaises(ValueError):
            prototype.password_verifier(malformed)
        response = self.client.post(
            "/login",
            content='{"username":"human","password":"\\ud800"}',
            headers={"Origin": prototype.ORIGIN, "Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.store.global_attempts, 0)
        with self.assertRaises(ValueError):
            self.store.reset("human", malformed)
        with prototype.IdentityStore(
            Path(self.temp.name) / "malformed-bootstrap.sqlite"
        ) as fresh:
            bootstrap = fresh.bootstrap_token(now=0)
            self.assertFalse(fresh.bootstrap(bootstrap, "operator", malformed, now=1))
            self.assertEqual(
                fresh.db.execute("SELECT used FROM bootstrap").fetchone()[0], 0
            )

    def test_failed_measurement_cannot_publish_passing_artifact(self):
        measure_spec = importlib.util.spec_from_file_location(
            "identity_measurement_regression", FIXTURE.with_name("measure.py")
        )
        measurement = importlib.util.module_from_spec(measure_spec)
        measure_spec.loader.exec_module(measurement)
        artifact = Path(self.temp.name) / "result.json"
        artifact.write_text("previous-evidence")
        failed = SimpleNamespace(
            testsRun=1,
            failures=[("test", "failed")],
            errors=[],
            wasSuccessful=lambda: False,
        )
        output = io.StringIO()
        with (
            patch.object(unittest.TextTestRunner, "run", return_value=failed),
            redirect_stdout(output),
        ):
            self.assertEqual(measurement.measure(destination=artifact), 1)
        self.assertEqual(artifact.read_text(), "previous-evidence")
        self.assertEqual(json.loads(output.getvalue())["matrix_metrics"], "unverified")

    def test_failed_measured_crypto_cannot_publish_passing_artifact(self):
        measure_spec = importlib.util.spec_from_file_location(
            "identity_crypto_measurement_regression", FIXTURE.with_name("measure.py")
        )
        measurement = importlib.util.module_from_spec(measure_spec)
        measure_spec.loader.exec_module(measurement)
        artifact = Path(self.temp.name) / "crypto-result.json"
        artifact.write_text("previous-evidence")
        successful = SimpleNamespace(
            testsRun=18, failures=[], errors=[], wasSuccessful=lambda: True
        )
        with (
            patch.object(measurement.prototype, "verify_password", return_value=False),
            patch.object(unittest.TextTestRunner, "run", return_value=successful),
            patch.object(
                type(self), "matrix_metrics", {"total_asserted_outcomes": 2000}
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(measurement.measure(destination=artifact), 1)
        self.assertEqual(artifact.read_text(), "previous-evidence")

    def test_malformed_and_oversized_request_shapes_deny(self):
        token, csrf = self.store.issue("human", "human")
        self.client.cookies.set("__Host-session", token)
        headers = {
            "Origin": prototype.ORIGIN,
            "X-CSRF-Token": csrf,
            "Content-Type": "application/json",
        }
        for path in ("/login", "/capability"):
            for payload in ("{", "[]", "null", '"scalar"', " " * 4097):
                with self.subTest(path=path, payload=payload[:20]):
                    self.assertEqual(
                        self.client.post(
                            path, content=payload, headers=headers
                        ).status_code,
                        400,
                    )
        for project, workspace in (
            ([], "workspace"),
            ("project", {}),
            ("\ud800", "workspace"),
        ):
            response = self.client.post(
                "/capability",
                content=json.dumps(
                    {"project": project, "workspace": workspace, "capability": "report"}
                ),
                headers=headers,
            )
            self.assertEqual(response.status_code, 403)

    def test_reset_revocation_and_privilege_change_invalidate(self):
        for action in ("reset", "revoke", "membership"):
            token, _ = self.store.issue("human", "human", now=0)
            if action == "reset":
                self.store.reset("human", self.verifier)
            elif action == "revoke":
                self.store.revoke("human")
            else:
                self.store.membership("human", "project", "workspace", "reviewer")
            self.assertIsNone(self.store.resolve(token, "human", now=1))

    def test_csrf_origin_and_transport_denials_over_http(self):
        token, csrf = self.store.issue("human", "human")
        self.client.cookies.set("__Host-session", token)
        body = {"project": "project", "workspace": "workspace", "capability": "publish"}
        for headers in (
            {},
            {"Origin": prototype.ORIGIN},
            {"Origin": "null", "X-CSRF-Token": csrf},
            {"Origin": "https://foreign.invalid", "X-CSRF-Token": csrf},
            {"Origin": prototype.ORIGIN, "X-CSRF-Token": "wrong"},
        ):
            self.assertEqual(
                self.client.post("/capability", json=body, headers=headers).status_code,
                403,
            )
        self.assertEqual(
            self.client.post(
                "/capability",
                json=body,
                headers={"Origin": prototype.ORIGIN, "X-CSRF-Token": csrf},
            ).status_code,
            200,
        )
        with TestClient(
            prototype.make_app(self.store), base_url="http://qualify.invalid"
        ) as insecure:
            self.assertEqual(
                insecure.post(
                    "/login",
                    json={"username": "human", "password": self.password},
                    headers={"Origin": prototype.ORIGIN},
                ).status_code,
                403,
            )

    def test_separate_audience_expiry_and_revocation(self):
        for audience in prototype.AUDIENCES:
            token, _ = self.store.issue("human", audience, now=0)
            for expected in prototype.AUDIENCES:
                self.assertEqual(
                    self.store.resolve(token, expected, now=1) is not None,
                    audience == expected,
                )
            self.store.logout(token)
            self.assertIsNone(self.store.resolve(token, audience, now=2))
            token, _ = self.store.issue("human", audience, now=0)
            self.assertIsNone(self.store.resolve(token, audience, now=3600))
        with self.assertRaises(ValueError):
            self.store.issue("human", "unknown")

    def test_full_actor_role_scope_capability_matrix(self):
        expected = {
            "admin": set(prototype.CAPABILITIES),
            "maintainer": {
                "workflow",
                "run",
                "decision",
                "report",
                "artifact",
                "policy",
            },
            "reviewer": {"decision", "report", "artifact", "policy"},
            "contributor": {"run", "report", "artifact", "policy"},
            "read-only": {"report", "artifact", "policy"},
        }
        count = 0
        allowed_count = 0
        matching_count = 0
        for audience in prototype.AUDIENCES:
            for role, allowed in expected.items():
                self.store.membership("human", "project", "workspace", role)
                token, _ = self.store.issue("human", audience, now=0)
                for scope in ("project", "workspace"):
                    for capability in prototype.CAPABILITIES:
                        with self.subTest(
                            audience=audience,
                            role=role,
                            scope=scope,
                            capability=capability,
                        ):
                            self.assertEqual(
                                self.store.authorize(
                                    token,
                                    "project",
                                    "workspace",
                                    scope,
                                    capability,
                                    now=1,
                                ),
                                audience == "human" and capability in allowed,
                            )
                            self.assertFalse(
                                self.store.authorize(
                                    token,
                                    "other",
                                    "workspace",
                                    scope,
                                    capability,
                                    now=1,
                                )
                            )
                            self.assertFalse(
                                self.store.authorize(
                                    token, "project", "other", scope, capability, now=1
                                )
                            )
                            self.assertFalse(
                                self.store.authorize(
                                    token,
                                    "missing",
                                    "missing",
                                    scope,
                                    capability,
                                    now=1,
                                )
                            )
                            count += 4
                            matching_count += 1
                            allowed_count += int(
                                audience == "human" and capability in allowed
                            )
        self.assertEqual(count, 2000)
        self.assertEqual(allowed_count, 54)
        type(self).matrix_metrics = {
            "matching_cells": matching_count,
            "cross_project_cells": matching_count,
            "cross_workspace_cells": matching_count,
            "absent_membership_cells": matching_count,
            "total_asserted_outcomes": count,
            "allowed_matching_cells": allowed_count,
            "denied_matching_cells": matching_count - allowed_count,
            "unauthorized_expected_denials": count - allowed_count,
        }

    def test_shared_requester_denied_single_operator_acknowledged(self):
        token, _ = self.store.issue("human", "human", now=0)
        self.assertIsNone(
            self.store.decision(
                token, "project", "workspace", requester="human", mode="shared", now=1
            )
        )
        self.assertEqual(
            self.store.decision(
                token, "project", "workspace", requester="human", mode="single", now=1
            ),
            "acknowledgement",
        )
        self.assertEqual(
            self.store.decision(
                token, "project", "workspace", requester="other", mode="shared", now=1
            ),
            "approval",
        )
        self.assertIsNone(
            self.store.decision(
                token, "project", "workspace", requester="other", mode="unknown", now=1
            )
        )
        self.store.add_account("second", self.verifier)
        self.assertIsNone(
            self.store.decision(
                token, "project", "workspace", requester="human", mode="single", now=1
            )
        )

    def test_forged_headers_legacy_share_and_machine_cookie_denied(self):
        for capability in prototype.CAPABILITIES:
            response = self.client.post(
                "/capability",
                json={
                    "project": "project",
                    "workspace": "workspace",
                    "capability": capability,
                },
                headers={
                    "X-Role": "admin",
                    "X-Actor": "human",
                    "Authorization": "Bearer legacy-share",
                    "Origin": prototype.ORIGIN,
                    "X-CSRF-Token": "invented",
                },
            )
            self.assertEqual(response.status_code, 401)
        for audience in prototype.AUDIENCES[1:]:
            token, csrf = self.store.issue("human", audience)
            self.client.cookies.set("__Host-session", token)
            response = self.client.post(
                "/capability",
                json={
                    "project": "project",
                    "workspace": "workspace",
                    "capability": "decision",
                },
                headers={"Origin": prototype.ORIGIN, "X-CSRF-Token": csrf},
            )
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/share/legacy").status_code, 404)

    def test_unknown_scope_role_capability_and_revoked_membership_deny(self):
        token, _ = self.store.issue("human", "human", now=0)
        for scope, capability in (("global", "report"), ("project", "unknown")):
            self.assertFalse(
                self.store.authorize(
                    token, "project", "workspace", scope, capability, now=1
                )
            )
        self.store.membership("human", "project", "workspace", "unknown")
        token, _ = self.store.issue("human", "human", now=0)
        self.assertFalse(
            self.store.authorize(
                token, "project", "workspace", "project", "report", now=1
            )
        )
        self.store.db.execute("DELETE FROM memberships")
        self.store.db.commit()
        self.assertFalse(
            self.store.authorize(
                token, "project", "workspace", "project", "report", now=1
            )
        )
