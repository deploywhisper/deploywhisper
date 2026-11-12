"""Trusted startup composition for the co-located material authority profile."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import config
from infra_automation.lifecycle import LifecycleError


class MaterialAuthorityCompositionTests(unittest.TestCase):
    def test_disabled_profile_preserves_default_deny(self):
        from app import _configure_infra_automation_authority

        with patch.object(
            config,
            "settings",
            replace(config.settings, material_authority_profile="disabled"),
        ):
            self.assertIsNone(_configure_infra_automation_authority())

    def test_colocated_profile_installs_one_shared_decision_service(self):
        from app import _configure_infra_automation_authority
        from services import infra_automation_decisions as decisions
        from services import infra_automation_handoffs as handoffs
        from services import infra_automation_material_authority as material

        original = (
            material._configured_signature,
            decisions._default_service,
            handoffs._default_service,
        )
        self.addCleanup(setattr, material, "_configured_signature", original[0])
        self.addCleanup(setattr, decisions, "_default_service", original[1])
        self.addCleanup(setattr, handoffs, "_default_service", original[2])
        material._configured_signature = None
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private_key = Ed25519PrivateKey.generate()
            public_path = root / "public.pem"
            public_path.write_bytes(
                private_key.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
            public_path.chmod(0o600)
            settings = replace(
                config.settings,
                material_authority_profile="colocated-v1",
                material_ledger_path=str(root / "material.json"),
                material_verification_key_path=str(public_path),
                material_probe_socket_path=str(root / "custody.sock"),
                recovery_control_path=str(root / "recovery"),
                collection_profiles_path=str(root / "profiles.json"),
                collection_profiles_sha256="sha256:" + "a" * 64,
            )
            with patch.object(config, "settings", settings):
                decision, handoff = _configure_infra_automation_authority()
                self.assertIs(decision, decisions._default_service)
                self.assertIs(handoff, handoffs._default_service)
                self.assertIs(handoff.decision_service, decision)
                self.assertEqual(
                    _configure_infra_automation_authority(), (decision, handoff)
                )
                with patch.object(
                    config,
                    "settings",
                    replace(settings, material_ledger_path=str(root / "other.json")),
                ):
                    with self.assertRaises(LifecycleError):
                        _configure_infra_automation_authority()

    def test_partial_profile_fails_closed(self):
        from app import _configure_infra_automation_authority

        with patch.object(
            config,
            "settings",
            replace(
                config.settings,
                material_authority_profile="colocated-v1",
                material_ledger_path="",
                material_verification_key_path="",
                material_probe_socket_path="",
                collection_profiles_sha256="",
            ),
        ):
            with self.assertRaises(LifecycleError):
                _configure_infra_automation_authority()

    def test_app_rejects_private_authority_material(self):
        from app import _configure_infra_automation_authority

        with patch.object(
            config,
            "settings",
            replace(
                config.settings,
                material_authority_profile="colocated-v1",
                material_ledger_path="ledger.json",
                material_verification_key_path="public.pem",
                material_probe_socket_path="custody.sock",
                material_signing_key_path="private.pem",
                recovery_control_path="recovery",
                collection_profiles_path="profiles.json",
                collection_profiles_sha256="sha256:" + "a" * 64,
            ),
        ):
            with self.assertRaises(LifecycleError):
                _configure_infra_automation_authority()

    def test_app_refuses_authority_private_key_or_raw_custody_configuration(self):
        from app import _configure_infra_automation_authority

        for field, value in (
            ("material_signing_key_path", "/private/signing.pem"),
            ("material_custody_root", "/private/raw-custody"),
        ):
            with (
                self.subTest(field=field),
                patch.object(
                    config,
                    "settings",
                    replace(config.settings, **{field: value}),
                ),
            ):
                with self.assertRaises(LifecycleError):
                    _configure_infra_automation_authority()

    def test_operator_cli_fails_closed_without_profile(self):
        from cli.material_authority import main

        with patch.object(
            config,
            "settings",
            replace(config.settings, material_authority_profile="disabled"),
        ):
            self.assertEqual(main(["--run-id", "run-one", "--step-id", "decision"]), 1)

    def test_operator_cli_rebinds_ledger_after_recovery_generation(self):
        from cli.material_authority import _current_document
        from infra_automation.material_authority import (
            MaterialAuthorityDocument,
            MaterialAuthorityLedger,
            MaterialAuthorityRecord,
        )

        with tempfile.TemporaryDirectory() as temporary:
            private_key = Ed25519PrivateKey.generate()
            ledger = MaterialAuthorityLedger(
                Path(temporary) / "authority.json",
                signing_key=private_key,
                verification_key=private_key.public_key(),
            )
            ledger.write(
                MaterialAuthorityDocument(
                    source_id="installation-one",
                    recovery_generation=1,
                    records=(
                        MaterialAuthorityRecord(
                            run_id="run-one",
                            step_id="decision",
                            binding_digest="sha256:" + "a" * 64,
                            source_digest="sha256:" + "b" * 64,
                            custody_handle="custody-one",
                            raw_local_digest="sha256:" + "c" * 64,
                            expires_at="2030-01-01T00:00:00Z",
                            generation=1,
                        ),
                    ),
                )
            )
            rebound = _current_document(
                ledger, {"installation_id": "installation-two", "generation": 2}
            )
            self.assertEqual(rebound.source_id, "installation-two")
            self.assertEqual(rebound.recovery_generation, 2)
            self.assertEqual(rebound.records[0].state, "revoked")
            self.assertEqual(rebound.records[0].generation, 2)


if __name__ == "__main__":
    unittest.main()
