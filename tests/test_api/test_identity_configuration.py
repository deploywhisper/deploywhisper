"""Public identity configuration is a closed, read-only, nonsecret contract."""

from dataclasses import replace
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import config
from api.routes.auth import router
from api.schemas import IdentityConfigurationData, IdentityConfigurationResponse
from services.identity_service import IdentityService


class IdentityConfigurationTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.app = app

    def request(self, *, profile="disabled", origin="", base_url=None, **settings):
        options = {
            "identity_profile": profile,
            "identity_origin": origin,
            "authorization_profile": "legacy-evaluation",
            "identity_decision_mode": "shared",
            **settings,
        }
        with (
            patch.object(
                config,
                "settings",
                replace(config.settings, **options),
            ),
            TestClient(self.app, base_url=base_url or "http://testserver") as client,
        ):
            return client.get("/api/v1/auth/configuration")

    def test_disabled_configuration_is_readable_and_uncached(self):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"],
            {
                "version": 1,
                "profile": "disabled",
                "configured_origin": None,
                "configuration_valid": False,
                "login_available": False,
                "authorization_profile": "legacy-evaluation",
                "decision_mode": "shared",
            },
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["pragma"], "no-cache")
        self.assertEqual(
            response.headers["x-correlation-id"],
            response.json()["meta"]["correlation_id"],
        )
        self.assertNotIn("set-cookie", response.headers)
        IdentityConfigurationResponse.model_validate(response.json())

    def test_valid_profiles_and_actual_origin(self):
        for profile, origin in (
            ("local-development", "http://localhost:8080"),
            ("local-development", "http://127.0.0.1:8080"),
            ("local-development", "http://[::1]:8080"),
            ("https", "https://identity.invalid"),
        ):
            with self.subTest(profile=profile, origin=origin):
                data = self.request(
                    profile=profile, origin=origin, base_url=origin
                ).json()["data"]
                self.assertTrue(data["configuration_valid"])
                self.assertTrue(data["login_available"])
                self.assertEqual(data["configured_origin"], origin)
                wrong = self.request(profile=profile, origin=origin).json()["data"]
                self.assertTrue(wrong["configuration_valid"])
                self.assertFalse(wrong["login_available"])

    def test_invalid_origins_are_redacted(self):
        for origin in (
            "https://synthetic-secret@identity.invalid",
            "https://:synthetic-secret@identity.invalid",
            "https://identity.invalid/synthetic-secret",
            "https://identity.invalid?synthetic-secret",
            "https://identity.invalid#synthetic-secret",
            "https://identity.invalid:synthetic-secret",
            "https://[synthetic-secret",
            "https://identity.invalid synthetic-secret",
            "http://identity.invalid",
            "https://identity.invalid/",
            "https://@identity.invalid",
            "https://identity.invalid?",
            "https://identity.invalid#",
            "https://identity.invalid\\synthetic-secret",
        ):
            with self.subTest(origin=origin):
                response = self.request(profile="https", origin=origin)
                self.assertEqual(response.status_code, 200)
                data = response.json()["data"]
                self.assertFalse(data["configuration_valid"])
                self.assertFalse(data["login_available"])
                self.assertIsNone(data["configured_origin"])
                self.assertNotIn("synthetic-secret", response.text)
        data = self.request(
            profile="local-development", origin="http://remote.invalid"
        ).json()["data"]
        self.assertFalse(data["configuration_valid"])
        self.assertIsNone(data["configured_origin"])

    def test_verified_single_operator_configuration_is_reported(self):
        data = self.request(
            profile="https",
            origin="https://identity.invalid",
            base_url="https://identity.invalid",
            authorization_profile="verified",
            identity_decision_mode="single-operator",
        ).json()["data"]
        self.assertEqual(data["authorization_profile"], "verified")
        self.assertEqual(data["decision_mode"], "single-operator")
        self.assertTrue(data["login_available"])

    def test_unknown_configuration_values_are_sanitized(self):
        settings = replace(
            config.settings,
            identity_profile="synthetic-secret",
            identity_origin="https://identity.invalid",
            authorization_profile="synthetic-secret",
            identity_decision_mode="synthetic-secret",
        )
        with patch.object(config, "settings", settings):
            with TestClient(self.app) as client:
                response = client.get("/api/v1/auth/configuration")
        data = response.json()["data"]
        for field in ("profile", "authorization_profile", "decision_mode"):
            self.assertEqual(data[field], "unavailable")
        self.assertFalse(data["configuration_valid"])
        self.assertFalse(data["login_available"])
        self.assertIsNone(data["configured_origin"])
        self.assertNotIn("synthetic-secret", response.text)

    def test_does_not_read_database_mutate_or_issue_principals(self):
        with (
            patch.object(IdentityService, "_transaction", side_effect=AssertionError),
            patch.object(
                IdentityService, "_issue_credential", side_effect=AssertionError
            ),
            patch.object(IdentityService, "login", side_effect=AssertionError),
            patch.object(
                IdentityService, "resolve_session", side_effect=AssertionError
            ),
        ):
            response = self.request(
                profile="https",
                origin="https://identity.invalid",
                base_url="https://identity.invalid",
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("principal", response.text)
        self.assertNotIn("token", response.text)
        self.assertNotIn("set-cookie", response.headers)
        with TestClient(self.app) as client:
            self.assertEqual(client.post("/api/v1/auth/configuration").status_code, 405)
            for route in ("setup", "bootstrap", "recover", "recovery"):
                self.assertEqual(client.post(f"/api/v1/auth/{route}").status_code, 404)

    def test_forwarded_headers_and_roles_do_not_enable_login(self):
        settings = replace(
            config.settings,
            identity_profile="https",
            identity_origin="https://identity.invalid",
        )
        with patch.object(config, "settings", settings):
            with TestClient(self.app, base_url="http://wrong.invalid") as client:
                response = client.get(
                    "/api/v1/auth/configuration",
                    headers={
                        "Forwarded": "proto=https;host=identity.invalid",
                        "X-Forwarded-Proto": "https",
                        "X-Forwarded-Host": "identity.invalid",
                        "X-Actor": "operator",
                        "X-Project-Role": "admin",
                    },
                )
        self.assertFalse(response.json()["data"]["login_available"])

    def test_contract_rejects_coercion_and_extra_fields(self):
        payload = self.request().json()
        for version in (True, False, 1.0, "1", 0, 2):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                IdentityConfigurationData.model_validate(
                    {**payload["data"], "version": version}
                )
        for key in ("configuration_valid", "login_available"):
            for value in (0, 1, "false", "true"):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ValidationError):
                        IdentityConfigurationData.model_validate(
                            {**payload["data"], key: value}
                        )
        for invalid in (
            {**payload, "secret": "no"},
            {**payload, "data": {**payload["data"], "secret": "no"}},
            {**payload, "meta": {**payload["meta"], "secret": "no"}},
        ):
            with self.assertRaises(ValidationError):
                IdentityConfigurationResponse.model_validate(invalid)


if __name__ == "__main__":
    unittest.main()
