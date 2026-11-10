"""Current-schema capacity adapter uses persisted authenticated runner ports."""

from __future__ import annotations

from dataclasses import replace
import os
import unittest
from unittest.mock import patch

from sqlalchemy import func, select

from infra_automation.lifecycle import LifecycleError
from infra_automation.operator_recovery import RecoveryError, assert_startup_allowed
import config
from models.tables import InfraAutomationRunner, InfraAutomationRunnerEnrollment
from scripts import qualify_operator_capacity as capacity
from services import infra_automation_runner_tasks as tasks
from services import project_service as auth


class OperatorCapacityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = capacity.make_current_fixture()
        self.addCleanup(self.fixture.doCleanups)

    def test_bound_recovery_configuration_and_removed_control_deny(self):
        state = self.fixture.recovery_store.status()
        self.assertEqual(state["phase"], "ready")
        self.assertEqual(
            config.settings.recovery_control_path, str(self.fixture.recovery_control)
        )
        self.assertEqual(
            os.environ["DEPLOYWHISPER_RECOVERY_CONTROL_PATH"],
            str(self.fixture.recovery_control),
        )
        port = capacity.AuthenticatedRunnerPort(self.fixture)
        with (
            patch.object(
                config,
                "settings",
                replace(config.settings, recovery_control_path=""),
            ),
            patch.dict(os.environ, {"DEPLOYWHISPER_RECOVERY_CONTROL_PATH": ""}),
        ):
            with self.assertRaises(LifecycleError) as denied:
                tasks.poll(next(iter(port.credentials.values())))
            self.assertEqual(denied.exception.status_code, 503)
            with (
                patch.object(
                    config,
                    "settings",
                    replace(config.settings, database_url=str(self.fixture.engine.url)),
                ),
                self.assertRaises(RecoveryError),
            ):
                assert_startup_allowed()

    def test_current_head_and_twenty_persisted_credential_authentications(self):
        with self.fixture.engine.connect() as connection:
            self.assertEqual(
                connection.exec_driver_sql(
                    "SELECT version_num FROM alembic_version"
                ).scalar(),
                capacity.REVISION,
            )
        port = capacity.AuthenticatedRunnerPort(self.fixture)
        self.assertEqual(port.exercise(1, 0), 20)
        self.assertEqual(port.heartbeat_calls, 20)
        self.assertEqual(port.read_calls, 1)
        with self.fixture.factory() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(InfraAutomationRunner)),
                20,
            )
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(InfraAutomationRunnerEnrollment)
                    .where(InfraAutomationRunnerEnrollment.consumed_at.is_not(None))
                ),
                20,
            )
            for row in session.scalars(select(InfraAutomationRunner)):
                self.assertEqual(row.status, "active")
                self.assertIsNotNone(row.last_seen_at)
                self.assertNotEqual(row.credential_hash, port.credentials[row.id].token)

    def test_rotation_rejects_old_bearer_and_refreshes_all_twenty(self):
        port = capacity.AuthenticatedRunnerPort(self.fixture, rotate_before_seconds=900)
        old = dict(port.credentials)
        self.assertEqual(port.exercise(1, 0), 20)
        self.assertEqual(port.rotation_count, 20)
        for credential in old.values():
            with self.assertRaises(LifecycleError):
                tasks.poll(credential)
        self.assertEqual(port.exercise(2, 0), 20)
        with auth.authorized_session(self.fixture.factory) as session:
            self.assertTrue(
                all(
                    row.generation >= 2
                    for row in session.scalars(select(InfraAutomationRunner))
                )
            )

    def test_source_hashes_cover_adapter_and_participating_runtime(self):
        hashes = capacity.source_hashes()
        for path in (
            "scripts/qualify_operator_capacity.py",
            "tests/test_infra_automation/test_operator_capacity.py",
            "tests/fixtures/infra_automation/engine_v1/qualification.py",
            "services/infra_automation_runners.py",
            "services/infra_automation_runner_tasks.py",
            "infra_automation/operator_recovery.py",
            "migrations/versions/041_add_operator_recovery.py",
            "app.py",
            "api/routes/infra_automation.py",
        ):
            self.assertIn(path, hashes)
            self.assertEqual(len(hashes[path]), 64)
