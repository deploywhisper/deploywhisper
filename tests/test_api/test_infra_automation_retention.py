"""Human-only retention HTTP adapter uses the real service and closed errors."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest

from sqlalchemy import select, update

from models.tables import InfraAutomationArtifactManifest, InfraAutomationRun
from services import infra_automation_retention as retention
from tests.test_api import test_infra_automation_preflight as fixtures


class RetentionApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.InfraAutomationPreflightApiTests()
        self.addCleanup(self.fixture.tearDown)
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.fixture.payload["artifacts"][0]["content"] += "\n# synthetic padding" * 300
        response = self.fixture.post()
        self.assertEqual(response.status_code, 200, response.text)
        run = response.json()["data"]
        with self.fixture.factory.begin() as db:
            row = db.scalar(
                select(InfraAutomationArtifactManifest).where(
                    InfraAutomationArtifactManifest.run_id == run["id"]
                )
            )
            self.path = f"/api/v1/infra-automation/manifests/{row.id}/purge"
            current = db.scalar(
                select(InfraAutomationRun).where(InfraAutomationRun.id == run["id"])
            )
            db.execute(
                update(InfraAutomationRun)
                .where(InfraAutomationRun.id == run["id"])
                .values(state="failed", version=current.version + 1)
            )
            self.body = dict(
                expected_run_version=current.version,
                reason="Expired synthetic evidence",
            )
        self.future = datetime.now(timezone.utc) + timedelta(days=8)

    def test_admin_purge_and_conflicting_replay(self):
        with patch.object(retention, "_now", return_value=self.future):
            response = self.fixture.client.post(
                self.path, json=self.body, headers=self.fixture.headers()
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["data"]["content_status"], "removed")
            self.assertEqual(response.headers["cache-control"], "no-store")
            replay = self.fixture.client.post(
                self.path, json=self.body, headers=self.fixture.headers()
            )
            self.assertEqual(replay.json()["data"], response.json()["data"])
            conflict = self.fixture.client.post(
                self.path,
                json={**self.body, "reason": "Changed request"},
                headers=self.fixture.headers(),
            )
            self.fixture.assert_error(conflict, 409)

    def test_missing_session_csrf_nonadmin_and_cas_deny(self):
        for headers, body, status in (
            (
                {
                    "Cookie": "",
                    "Origin": "https://identity.invalid",
                    "X-CSRF-Token": "missing",
                },
                self.body,
                401,
            ),
            (self.fixture.headers(**{"X-CSRF-Token": "wrong"}), self.body, 403),
            (self.fixture.headers(), {**self.body, "expected_run_version": 999}, 409),
        ):
            with (
                self.subTest(status=status),
                patch.object(retention, "_now", return_value=self.future),
            ):
                response = self.fixture.client.post(
                    self.path, json=body, headers=headers
                )
                self.fixture.assert_error(response, status)
        self.fixture.member("read-only")
        response = self.fixture.client.post(
            self.path, json=self.body, headers=self.fixture.headers()
        )
        self.fixture.assert_error(response, 403)

    def test_original_preflight_retry_after_removal_returns_retained_run_without_recreation(
        self,
    ):
        from models.tables import (
            InfraAutomationAudit,
            InfraAutomationRetentionTombstone,
        )
        from sqlalchemy import func
        from services import infra_automation_engine_service as engine
        from services import infra_automation_preflight as preflight
        from copy import deepcopy

        with patch.object(retention, "_now", return_value=self.future):
            removed = self.fixture.client.post(
                self.path, json=self.body, headers=self.fixture.headers()
            )
        self.assertEqual(removed.status_code, 200, removed.text)
        manifest_id = removed.json()["data"]["manifest_id"]
        run_id = removed.json()["data"]["run_id"]
        with self.fixture.factory() as db:
            before = db.scalar(
                select(InfraAutomationRun).where(InfraAutomationRun.id == run_id)
            )
            retained = (before.version, before.retained_bytes)
            audit_count = db.scalar(
                select(func.count()).select_from(InfraAutomationAudit)
            )
        # Keep replay time at the removal floor. These synthetic session and
        # server clocks are injected independently; no expired session is revived.
        original_request_run = engine.request_run
        with (
            patch.object(
                engine,
                "request_run",
                side_effect=lambda request, **kwargs: original_request_run(
                    request, now=self.future, **kwargs
                ),
            ),
            patch.object(preflight.reports, "_now", return_value=self.future),
        ):
            replay = self.fixture.post()
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json()["data"]["id"], run_id)
            self.assertEqual(replay.json()["data"]["state"], "failed")
            changed = deepcopy(self.fixture.payload)
            changed["artifacts"][0]["content"] += "\n# changed content"
            self.fixture.assert_error(self.fixture.post(changed), 409)
        with self.fixture.factory() as db:
            row = db.get(InfraAutomationArtifactManifest, manifest_id)
            run = db.scalar(
                select(InfraAutomationRun).where(InfraAutomationRun.id == run_id)
            )
            self.assertEqual(row.artifacts_bytes, b"[]")
            self.assertIsNotNone(db.get(InfraAutomationRetentionTombstone, manifest_id))
            self.assertEqual((run.version, run.retained_bytes), retained)
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationAudit)),
                audit_count,
            )
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(InfraAutomationArtifactManifest)
                ),
                1,
            )


class RetentionMigratedApiTests(RetentionApiTests):
    """Repeat the API contract against Alembic head, including every SQL guard."""

    def setUp(self):
        from alembic import command
        from alembic.config import Config
        from models.database import Base
        import os

        def migrate(engine):
            cfg = Config("alembic.ini")
            url = str(engine.url)
            cfg.set_main_option("sqlalchemy.url", url)
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(cfg, "head")
            # The historical migration seeds a default project; the shared
            # synthetic fixture supplies its own three projects with those IDs.
            with engine.begin() as connection:
                connection.exec_driver_sql("DELETE FROM projects")

        with patch.object(Base.metadata, "create_all", side_effect=migrate):
            super().setUp()

    def test_full_head_guard_allows_only_the_exact_one_use_retention_debit(self):
        import sqlite3
        from sqlalchemy import event
        from sqlalchemy.exc import IntegrityError
        from models.tables import InfraAutomationRetentionTombstone

        checked = []

        def probe(connection, cursor, statement, parameters, context, executemany):
            driver = connection.connection.driver_connection
            if statement.startswith(
                "INSERT INTO infra_automation_retention_tombstones"
            ):
                columns = statement.split("(", 1)[1].split(")", 1)[0].split(", ")
                fractional = list(parameters)
                fractional[columns.index("reclaimed_bytes")] = 1.5
                with self.assertRaises(sqlite3.IntegrityError):
                    driver.execute(statement, tuple(fractional))
                checked.append("fractional reclaimed bytes")
                return
            if not statement.startswith("UPDATE infra_automation_runs SET"):
                return
            tombstone = driver.execute(
                "SELECT run_id FROM infra_automation_retention_tombstones"
            ).fetchone()
            if tombstone is None:
                return
            # These probes execute in the real reserved transaction after marker
            # publication and before the service's legitimate exact debit.
            common = "UPDATE infra_automation_runs SET retained_bytes=retained_bytes-(SELECT reclaimed_bytes FROM infra_automation_retention_tombstones WHERE run_id=?),version=version+1,last_observed_at=(SELECT deleted_at FROM infra_automation_retention_tombstones WHERE run_id=?),updated_at=(SELECT deleted_at FROM infra_automation_retention_tombstones WHERE run_id=?) WHERE id=?"
            for changed in (
                common.replace(
                    "retained_bytes=retained_bytes-", "retained_bytes=retained_bytes-1-"
                ),
                common.replace("version=version+1", "version=version+2"),
                common.replace(
                    "version=version+1", "version=version+1,state='succeeded'"
                ),
                common.replace(
                    "version=version+1", "version=version+1,external_possible=1"
                ),
                common.replace(
                    "updated_at=(SELECT deleted_at FROM infra_automation_retention_tombstones WHERE run_id=?)",
                    "updated_at=(SELECT '2099-01-01 00:00:00' FROM infra_automation_retention_tombstones WHERE run_id=?)",
                ),
            ):
                with self.assertRaises(sqlite3.IntegrityError):
                    driver.execute(changed, (tombstone[0],) * 4)
                checked.append(changed)

        event.listen(self.fixture.engine, "before_cursor_execute", probe)
        try:
            with patch.object(retention, "_now", return_value=self.future):
                response = self.fixture.client.post(
                    self.path, json=self.body, headers=self.fixture.headers()
                )
        finally:
            event.remove(self.fixture.engine, "before_cursor_execute", probe)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(checked), 6)
        with self.fixture.factory() as db:
            tombstone = db.get(
                InfraAutomationRetentionTombstone,
                response.json()["data"]["manifest_id"],
            )
            self.assertGreater(tombstone.reclaimed_bytes, 0)
            run_id = tombstone.run_id
        with self.fixture.engine.begin() as db:
            with self.assertRaises(IntegrityError) as caught:
                db.exec_driver_sql(
                    "UPDATE infra_automation_runs SET retained_bytes=retained_bytes-1,version=version+1 WHERE id=?",
                    (run_id,),
                )
            self.assertIn("Immutable engine", str(caught.exception))

    def test_full_head_guard_denies_unreceipted_debit_and_preserves_binding(self):
        from sqlalchemy.exc import IntegrityError

        for assignment in (
            "retained_bytes=retained_bytes-1",
            "snapshot_digest='changed'",
            "external_possible=-1",
        ):
            with self.subTest(assignment=assignment), self.fixture.engine.begin() as db:
                with self.assertRaises(IntegrityError):
                    db.exec_driver_sql(
                        f"UPDATE infra_automation_runs SET {assignment},version=version+1"
                    )
