"""Trusted engine ceilings, physical reserve and real SQLite-full regressions."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import create_engine, select

import config
from infra_automation import storage, claims
from infra_automation.lifecycle import (
    LifecycleError,
    UpdateSettingsRequest,
    AutomationSettings,
)
from infra_automation.state import EngineBounds
from models.tables import InfraAutomationAudit
from services import project_service as auth
from services import infra_automation_policy as policy
from tests.test_infra_automation import test_engine_recovery_claims as recovery


class EngineConfigurationTests(TestCase):
    def test_dynamic_reduce_only_strict_environment_values(self):
        for field, maximum in EngineBounds().model_dump().items():
            name = "DEPLOYWHISPER_ENGINE_" + field.upper()
            with patch.dict(os.environ, {name: "1"}):
                self.assertEqual(getattr(config.engine_bounds(), field), 1)
            for invalid in (
                "",
                "0",
                "-1",
                "true",
                " 1",
                "+1",
                "1.0",
                "١",
                str(maximum + 1),
            ):
                with (
                    self.subTest(field=field, invalid=invalid),
                    patch.dict(os.environ, {name: invalid}),
                    self.assertRaises(LifecycleError),
                ):
                    config.engine_bounds()

    def test_explicit_wal_full_profile_and_every_new_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine("sqlite:///" + str(Path(directory) / "engine.db"))
            try:
                storage.configure_engine_sqlite(engine)
                storage.configure_engine_sqlite(engine)
                engine.dispose()
                with engine.connect() as db:
                    self.assertEqual(
                        db.exec_driver_sql("PRAGMA journal_mode").scalar(), "wal"
                    )
                    self.assertEqual(
                        db.exec_driver_sql("PRAGMA synchronous").scalar(), 2
                    )
            finally:
                engine.dispose()
        memory = create_engine("sqlite://")
        try:
            with self.assertRaises(LifecycleError):
                storage.configure_engine_sqlite(memory)
        finally:
            memory.dispose()


class EngineLimitPolicyTests(recovery.EngineRecoveryClaimsTests):
    # The inherited recovery corpus intentionally also runs under reserve checks.
    def test_physical_reserve_exact_boundary_and_fail_closed(self):
        reserve = EngineBounds().disk_reserve_bytes
        with auth.authorized_session(self.factory) as db:
            with patch.object(
                storage.shutil,
                "disk_usage",
                return_value=SimpleNamespace(free=reserve + 10),
            ):
                storage.ensure_capacity(db, additional_bytes=10)
                with self.assertRaises(LifecycleError):
                    storage.ensure_capacity(db, additional_bytes=11)
            with (
                patch.object(
                    storage.shutil, "disk_usage", side_effect=OSError("unavailable")
                ),
                self.assertRaises(LifecycleError) as denied,
            ):
                storage.ensure_capacity(db)
            self.assertEqual(denied.exception.status_code, 503)

    def test_disk_shortage_rolls_back_growth_but_allows_safety_stop(self):
        from infra_automation.state import LogChunk

        owner, handle, row = self.owned()
        with patch.object(
            storage.shutil, "disk_usage", return_value=SimpleNamespace(free=0)
        ):
            with self.assertRaises(LifecycleError):
                self.operation(
                    claims.append_log,
                    handle,
                    expected_version=row.version,
                    chunk=LogChunk(sequence=1, text="safe"),
                )
            stopped = self.operation(
                claims.safety_cleanup,
                owner,
                attempt_id=row.id,
                expected_version=row.version,
                state="cancelled",
            )
            self.assertEqual(stopped.state, "cancelled")

    def test_quota_reduction_below_real_queued_runs_is_atomic(self):
        from models.repositories import infra_automation_workflows as workflows

        self.request["key_digest"] = "sha256:" + "a" * 64
        self.admit()
        with self.factory() as db:
            current = workflows.get_policy(db, project_id=100)
            before = (
                current.version,
                current.authorization_epoch,
                current.restore_epoch,
            )
            before_audit = len(db.scalars(select(InfraAutomationAudit)).all())
        request = UpdateSettingsRequest(
            project_id=100,
            expected_version=current.version,
            reason="Synthetic quota reduction.",
            settings=AutomationSettings(enabled=True, max_queued_runs=1),
        )
        with self.credentials(), self.assertRaises(LifecycleError) as denied:
            policy.update_settings(request)
        self.assertEqual(denied.exception.status_code, 409)
        with self.factory() as db:
            current = workflows.get_policy(db, project_id=100)
            self.assertEqual(
                (current.version, current.authorization_epoch, current.restore_epoch),
                before,
            )
            self.assertEqual(
                len(db.scalars(select(InfraAutomationAudit)).all()), before_audit
            )

    def test_active_limit_counts_unknown_runs_and_denies_reduction(self):
        from models.repositories import infra_automation_runs as runs
        from models.repositories import infra_automation_workflows as workflows

        self.request["key_digest"] = "sha256:" + "b" * 64
        other = self.admit()
        with self.factory.begin() as db:
            for row in (self.run, other):
                runs.transition_run(
                    db,
                    run_id=row.id,
                    expected_version=1,
                    state="running",
                    audit_actor=self.actor,
                    reason="synthetic",
                    now=self.now,
                )
            runs.transition_run(
                db,
                run_id=self.run.id,
                expected_version=2,
                state="handing_off",
                audit_actor=self.actor,
                reason="synthetic",
                now=self.now,
            )
            runs.transition_run(
                db,
                run_id=self.run.id,
                expected_version=3,
                state="delivery_unknown",
                audit_actor=self.actor,
                reason="synthetic",
                now=self.now,
            )
        with self.factory() as db:
            current = workflows.get_policy(db, project_id=100)
            before = (
                current.version,
                current.authorization_epoch,
                len(db.scalars(select(InfraAutomationAudit)).all()),
            )
        request = UpdateSettingsRequest(
            project_id=100,
            expected_version=current.version,
            reason="Synthetic active limit.",
            settings=AutomationSettings(enabled=True, max_active_runs=1),
        )
        with self.credentials(), self.assertRaises(LifecycleError):
            policy.update_settings(request)
        with self.factory() as db:
            current = workflows.get_policy(db, project_id=100)
            self.assertEqual(
                (
                    current.version,
                    current.authorization_epoch,
                    len(db.scalars(select(InfraAutomationAudit)).all()),
                ),
                before,
            )

    def test_reduced_log_ceiling_is_enforced_on_current_owned_write(self):
        from infra_automation.state import LogChunk

        _, handle, row = self.owned()
        with patch.dict(os.environ, {"DEPLOYWHISPER_ENGINE_LOG_CHUNK_UTF8_BYTES": "1"}):
            with self.assertRaises(LifecycleError):
                self.operation(
                    claims.append_log,
                    handle,
                    expected_version=row.version,
                    chunk=LogChunk(sequence=1, text="é"),
                )
        with patch.dict(os.environ, {"DEPLOYWHISPER_ENGINE_ATTEMPT_LOG_BYTES": "1"}):
            with self.assertRaises(LifecycleError):
                self.operation(
                    claims.append_log,
                    handle,
                    expected_version=row.version,
                    chunk=LogChunk(sequence=1, text="a"),
                )

    def test_real_engine_sqlite_full_preserves_versions_audit_and_retry(self):
        from infra_automation.state import LogChunk
        from models.repositories import infra_automation_runs as runs
        from sqlalchemy.exc import DBAPIError

        storage.configure_engine_sqlite(self.engine)
        _, handle, row = self.owned()
        path = str(self.engine.url.database)

        def raw_evidence():
            with sqlite3.connect(path) as db:
                run = db.execute(
                    "SELECT state,version,retained_bytes FROM infra_automation_runs WHERE id=?",
                    (handle.run_id,),
                ).fetchone()
                attempt = db.execute(
                    "SELECT state,version,logs_json,uploads_json,output_json,output_digest FROM infra_automation_attempts WHERE id=?",
                    (handle.attempt_id,),
                ).fetchone()
                audit = db.execute(
                    "SELECT COUNT(*) FROM infra_automation_audit"
                ).fetchone()
                return run, attempt, audit

        before = raw_evidence()
        with self.assertRaises(DBAPIError) as failure:
            with auth.authorized_session(self.factory) as db:
                pages = db.connection().exec_driver_sql("PRAGMA page_count").scalar()
                db.connection().exec_driver_sql("PRAGMA max_page_count=" + str(pages))
                claims.append_log(
                    db,
                    handle,
                    expected_version=row.version,
                    chunk=LogChunk(sequence=1, text="x" * 16384),
                    now=self.now,
                )
        self.assertEqual(failure.exception.orig.sqlite_errorcode, sqlite3.SQLITE_FULL)
        self.engine.dispose()
        self.assertEqual(raw_evidence(), before)
        with self.engine.connect() as db:
            db.exec_driver_sql("PRAGMA max_page_count=2147483646")
        recovered = self.operation(
            claims.append_log,
            handle,
            expected_version=row.version,
            chunk=LogChunk(sequence=1, text="safe"),
        )
        self.assertEqual(recovered.last_log_sequence, 1)
        with self.factory() as db:
            self.assertEqual(
                runs.get_attempt(db, handle.attempt_id).version, row.version + 1
            )

    def test_physical_shortage_denies_guarded_new_work_before_effects(self):
        owner = self.acquire()
        with patch.object(
            storage.shutil, "disk_usage", return_value=SimpleNamespace(free=0)
        ):
            with self.assertRaises(LifecycleError):
                self.operation(
                    claims.start_run, owner, run_id=self.run.id, expected_version=1
                )
        self.operation(claims.start_run, owner, run_id=self.run.id, expected_version=1)
        handle = self.operation(
            claims.claim_attempt, owner, attempt_id=self.pending.id, expected_version=1
        )
        with patch.object(
            storage.shutil, "disk_usage", return_value=SimpleNamespace(free=0)
        ):
            with self.assertRaises(LifecycleError):
                self.operation(claims.start_attempt, handle, expected_version=2)
        with self.factory() as db:
            self.assertEqual(
                claims.repo.get_attempt(db, handle.attempt_id).state, "claimed"
            )
