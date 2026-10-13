"""Identity lifecycle regression contracts with isolated independent sessions."""

from __future__ import annotations

from contextlib import closing

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import multiprocessing
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models.database import Base
from models.tables import IdentityAccount, IdentitySession, IdentityCredential
from services.identity_service import (
    IdentityError,
    IdentityService,
    password_verifier,
    verify_password,
)


def _bootstrap_process(path, token, password, barrier, outcomes):
    engine = create_engine(f"sqlite:///{path}")
    service = IdentityService(
        sessionmaker(engine), now=lambda: datetime(2026, 10, 12, tzinfo=timezone.utc)
    )
    barrier.wait(timeout=15)
    try:
        service.bootstrap(token, "operator", password)
        outcomes.put("created")
    except IdentityError:
        outcomes.put("denied")
    finally:
        engine.dispose()


def _login_process(path, password, outcomes):
    engine = create_engine(f"sqlite:///{path}")
    service = IdentityService(
        sessionmaker(engine),
        now=lambda: datetime(2026, 10, 12, tzinfo=timezone.utc),
        security_profile="https",
        trusted_origin="https://identity.invalid",
    )
    try:
        service.login("operator", password)
        outcomes.put(200)
    except IdentityError as error:
        outcomes.put(error.status_code)
    finally:
        engine.dispose()


class IdentityServiceTests(unittest.TestCase):
    def test_successful_administration_refreshes_idle_expiry(self):
        self.bootstrap()
        issued = self.login()
        token = issued.token.get_secret_value()
        csrf = issued.csrf_token.get_secret_value()
        self.time += timedelta(seconds=290)
        account = self.service.create_account(
            token, "new-account", self.password, csrf_token=csrf
        )
        self.time += timedelta(seconds=290)
        self.service.revoke_account(token, account.principal_id, csrf_token=csrf)
        self.time += timedelta(seconds=290)
        self.assertEqual(
            self.service.resolve_session(token).principal_id,
            issued.principal.principal_id,
        )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "identity.db"
        self.engine = create_engine(f"sqlite:///{self.path}")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.time = datetime(2026, 10, 12, tzinfo=timezone.utc)
        self.service = self.new_service()
        self.password = "synthetic password for test"

    def new_service(self, **kwargs):
        return IdentityService(
            self.factory,
            now=lambda: self.time,
            security_profile=kwargs.get("security_profile", "https"),
            trusted_origin=kwargs.get("trusted_origin", "https://identity.invalid"),
        )

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def bootstrap(self):
        token = self.service.issue_setup_credential().token.get_secret_value()
        return self.service.bootstrap(token, "operator", self.password)

    def login(self):
        return self.service.login("operator", self.password)

    def test_bootstrap_is_one_use_and_independently_concurrent(self):
        token = self.service.issue_setup_credential().token.get_secret_value()

        def attempt(i):
            try:
                return self.new_service().bootstrap(
                    token, f"operator{i}", self.password
                )
            except IdentityError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(item is not None for item in results), 1)
        with self.factory() as db:
            self.assertEqual(len(db.scalars(select(IdentityAccount)).all()), 1)
        with self.assertRaises(IdentityError):
            self.service.bootstrap(token, "replay", self.password)

    def test_bootstrap_is_atomic_across_independent_processes(self):
        token = self.service.issue_setup_credential().token.get_secret_value()
        context = multiprocessing.get_context("spawn")
        barrier, outcomes = context.Barrier(3), context.Queue()
        processes = [
            context.Process(
                target=_bootstrap_process,
                args=(str(self.path), token, self.password, barrier, outcomes),
            )
            for _ in range(2)
        ]
        try:
            for process in processes:
                process.start()
            barrier.wait(timeout=15)
            results = [outcomes.get(timeout=15) for _ in processes]
            for process in processes:
                process.join(timeout=15)
                self.assertEqual(process.exitcode, 0)
            self.assertCountEqual(results, ["created", "denied"])
            with self.factory() as db:
                self.assertEqual(len(db.scalars(select(IdentityAccount)).all()), 1)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            outcomes.close()

    def test_csrf_denial_does_not_refresh_idle_and_version_change_denies(self):
        account = self.bootstrap()
        issued = self.login()
        self.time += timedelta(seconds=200)
        with self.assertRaises(IdentityError):
            self.service.resolve_session(
                issued.token.get_secret_value(), csrf_token="bad"
            )
        with self.factory() as db:
            stored = db.get(IdentitySession, issued.principal.session_id)
            self.assertEqual(
                stored.last_seen_at.replace(tzinfo=timezone.utc),
                self.time - timedelta(seconds=200),
            )
        with self.factory.begin() as db:
            db.get(IdentityAccount, account.principal_id).authentication_version += 1
        with self.assertRaises(IdentityError):
            self.service.resolve_session(issued.token.get_secret_value())

    def test_local_session_cannot_be_promoted_to_production(self):
        self.bootstrap()
        local = self.new_service(
            security_profile="local-development", trusted_origin="http://localhost:8080"
        )
        issued = local.login("operator", self.password)
        self.assertFalse(issued.principal.production_eligible)
        with self.assertRaises(IdentityError):
            self.service.resolve_session(issued.token.get_secret_value())
        with self.assertRaises(IdentityError):
            self.new_service(security_profile="disabled").login(
                "operator", self.password
            )

    def test_nonblocking_derivation_limit_applies_to_all_expensive_operations(self):
        from services.identity_service import _DERIVATION_SLOT

        self.bootstrap()
        issued = self.login()
        recovery = self.service.issue_recovery_credential("operator")
        self.assertTrue(_DERIVATION_SLOT.acquire(blocking=False))
        try:
            operations = [
                lambda: self.login(),
                lambda: self.service.bootstrap("wrong", "new", self.password),
                lambda: self.service.recover(
                    recovery.token.get_secret_value(), self.password
                ),
                lambda: self.service.create_account(
                    issued.token.get_secret_value(),
                    "second",
                    self.password,
                    csrf_token=issued.csrf_token.get_secret_value(),
                ),
            ]
            with patch("services.identity_service.hashlib.pbkdf2_hmac") as derive:
                for operation in operations:
                    with self.assertRaises(IdentityError) as caught:
                        operation()
                    self.assertEqual(caught.exception.status_code, 429)
                derive.assert_not_called()
        finally:
            _DERIVATION_SLOT.release()

    def test_expired_setup_and_malformed_password_do_not_consume(self):
        token = self.service.issue_setup_credential().token.get_secret_value()
        with self.assertRaises(IdentityError):
            self.service.bootstrap(token, "operator", "\ud800")
        self.time += timedelta(seconds=300)
        with self.assertRaises(IdentityError):
            self.service.bootstrap(token, "operator", self.password)

    def test_rotation_logout_and_hash_only_persistence(self):
        self.bootstrap()
        first = self.login()
        second = self.login()
        with self.assertRaises(IdentityError):
            self.service.resolve_session(first.token.get_secret_value())
        token, csrf = (
            second.token.get_secret_value(),
            second.csrf_token.get_secret_value(),
        )
        principal = self.service.resolve_session(token, csrf_token=csrf)
        self.assertTrue(principal.is_admin)
        self.assertNotIn(token, repr(second))
        with self.factory() as db:
            row = db.scalar(
                select(IdentitySession).where(
                    IdentitySession.id == principal.session_id
                )
            )
            self.assertNotEqual(row.token_hash, token)
            self.assertNotEqual(row.csrf_hash, csrf)
        self.service.logout(token, csrf_token=csrf)
        with self.assertRaises(IdentityError):
            self.service.resolve_session(token)

    def test_exact_idle_and_absolute_deadlines_and_rotation(self):
        self.bootstrap()
        issued = self.login()
        self.time += timedelta(seconds=300)
        with self.assertRaises(IdentityError):
            self.service.resolve_session(issued.token.get_secret_value())
        issued = self.login()
        absolute = issued.principal.expires_at
        for _ in range(17):
            self.time += timedelta(seconds=200)
            issued = self.service.rotate_session(
                issued.token.get_secret_value(),
                csrf_token=issued.csrf_token.get_secret_value(),
            )
            self.assertEqual(issued.principal.expires_at, absolute)
        self.time += timedelta(seconds=200)
        with self.assertRaises(IdentityError):
            self.service.resolve_session(issued.token.get_secret_value())

    def test_csrf_and_security_profile_are_bound(self):
        self.bootstrap()
        issued = self.login()
        token = issued.token.get_secret_value()
        with self.assertRaises(IdentityError):
            self.service.logout(token, csrf_token="wrong")
        for service in (
            self.new_service(trusted_origin="https://other.invalid"),
            self.new_service(
                security_profile="local-development",
                trusted_origin="http://localhost:8080",
            ),
        ):
            with self.assertRaises(IdentityError):
                service.resolve_session(token)
        self.assertEqual(self.service.resolve_session(token).principal_type, "human")

    def test_recovery_requires_one_use_evidence_and_invalidates_old_sessions(self):
        self.bootstrap()
        issued = self.login()
        recovery = self.service.issue_recovery_credential("operator")
        token = recovery.token.get_secret_value()
        with self.assertRaises(IdentityError):
            self.service.recover("wrong", "new synthetic password")
        self.service.recover(token, "new synthetic password")
        with self.assertRaises(IdentityError):
            self.service.resolve_session(issued.token.get_secret_value())
        with self.assertRaises(IdentityError):
            self.service.recover(token, self.password)
        self.service.login("operator", "new synthetic password")

    def test_recovery_expiry_and_supersession(self):
        self.bootstrap()
        first = self.service.issue_recovery_credential("operator")
        second = self.service.issue_recovery_credential("operator")
        with self.assertRaises(IdentityError):
            self.service.recover(first.token.get_secret_value(), self.password)
        self.time += timedelta(seconds=300)
        with self.assertRaises(IdentityError):
            self.service.recover(second.token.get_secret_value(), self.password)

    def test_account_administration_rechecks_live_authority(self):
        self.bootstrap()
        admin = self.login()
        token, csrf = (
            admin.token.get_secret_value(),
            admin.csrf_token.get_secret_value(),
        )
        account = self.service.create_account(
            token, "reviewer", self.password, csrf_token=csrf
        )
        user = self.service.login("reviewer", self.password)
        with self.assertRaises(IdentityError):
            self.service.revoke_account(
                user.token.get_secret_value(),
                admin.principal.principal_id,
                csrf_token=user.csrf_token.get_secret_value(),
            )
        self.service.revoke_account(token, account.principal_id, csrf_token=csrf)
        with self.assertRaises(IdentityError):
            self.service.resolve_session(user.token.get_secret_value())
        self.service.revoke_account(
            token, admin.principal.principal_id, csrf_token=csrf
        )
        with self.assertRaises(IdentityError):
            self.service.create_account(token, "forged", self.password, csrf_token=csrf)

    def test_machine_accounts_and_sessions_deny(self):
        account = self.bootstrap()
        for audience in ("service", "agent", "runner", "receiver"):
            with self.factory.begin() as db:
                db.get(IdentityAccount, account.principal_id).principal_type = audience
            with self.assertRaises(IdentityError):
                self.login()
        with self.factory.begin() as db:
            db.get(IdentityAccount, account.principal_id).principal_type = "human"
        issued = self.login()
        for audience in ("service", "agent", "runner", "receiver"):
            with self.factory.begin() as db:
                db.get(IdentitySession, issued.principal.session_id).audience = audience
            with self.assertRaises(IdentityError):
                self.service.resolve_session(issued.token.get_secret_value())

    def test_limits_survive_new_service_and_unknown_accounts_are_bounded(self):
        self.bootstrap()
        for _ in range(5):
            with self.assertRaises(IdentityError):
                self.service.login("operator", "wrong")
        with self.assertRaises(IdentityError) as caught:
            self.new_service().login("operator", self.password)
        self.assertEqual(caught.exception.status_code, 429)
        context = multiprocessing.get_context("spawn")
        outcomes = context.Queue()
        restarted = context.Process(
            target=_login_process, args=(str(self.path), self.password, outcomes)
        )
        try:
            restarted.start()
            self.assertEqual(outcomes.get(timeout=15), 429)
            restarted.join(timeout=15)
            self.assertEqual(restarted.exitcode, 0)
        finally:
            if restarted.is_alive():
                restarted.terminate()
                restarted.join(timeout=5)
            outcomes.close()
        self.time += timedelta(seconds=60)
        self.login()
        for i in range(19):
            with self.assertRaises(IdentityError):
                self.new_service().login(f"unknown{i}", "wrong")
        with self.assertRaises(IdentityError) as caught:
            self.new_service().login("other", "wrong")
        self.assertEqual(caught.exception.status_code, 429)

    def test_crypto_bounds_and_exact_parser(self):
        verifier = password_verifier(self.password)
        self.assertNotEqual(verifier, password_verifier(self.password))
        self.assertTrue(verify_password(self.password, verifier))
        self.assertFalse(verify_password("wrong", verifier))
        with patch("services.identity_service.hashlib.pbkdf2_hmac") as derive:
            for bad in (
                "sha256$bad",
                verifier.replace("600000", "999999999"),
                verifier.upper(),
            ):
                self.assertFalse(verify_password(self.password, bad))
            for bad in ("x" * 1025, "\ud800"):
                self.assertFalse(verify_password(bad, verifier))
                with self.assertRaises(IdentityError):
                    password_verifier(bad)
            derive.assert_not_called()

    def test_secrets_never_appear_in_database(self):
        setup = self.service.issue_setup_credential()
        self.service.bootstrap(
            setup.token.get_secret_value(), "operator", self.password
        )
        issued = self.login()
        recovery = self.service.issue_recovery_credential("operator")
        import sqlite3

        with closing(sqlite3.connect(self.path)) as db, db:
            dump = "\n".join(db.iterdump())
        for secret in (
            self.password,
            setup.token.get_secret_value(),
            issued.token.get_secret_value(),
            issued.csrf_token.get_secret_value(),
            recovery.token.get_secret_value(),
        ):
            self.assertNotIn(secret, dump)
        with self.factory() as db:
            self.assertGreater(len(db.scalars(select(IdentityCredential)).all()), 0)
