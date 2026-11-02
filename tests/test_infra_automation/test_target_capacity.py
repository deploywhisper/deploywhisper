"""New registry and captured target copies honor existing storage admission."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import func, select

from infra_automation import claims
from infra_automation.lifecycle import LifecycleError
from infra_automation.state import EngineBounds
from infra_automation.targets import BreakLockRequest, canonical
from models.tables import (
    InfraAutomationRun,
    InfraAutomationRunTarget,
    InfraAutomationTarget,
    InfraAutomationTargetLock,
)
from models.repositories import infra_automation_runs as runs
from services.infra_automation_snapshots import export_run_snapshot
from services import infra_automation_support as support
from services import infra_automation_targets as targets
from services import project_service as authorization
from tests.test_infra_automation import test_target_admission as fixture


class TargetCapacityTests(fixture.TargetAdmissionTests):
    @staticmethod
    def bookkeeping_size(values):
        return len(
            canonical(
                {
                    key: support.utc(value) if isinstance(value, datetime) else value
                    for key, value in values.items()
                }
            )
        )

    def captured_allocation(self, session, run_id, charged):
        """Separate charged lock bytes from immutable copies and the run base."""
        captures = list(
            session.scalars(
                select(InfraAutomationRunTarget).where(
                    InfraAutomationRunTarget.run_id == run_id
                )
            )
        )
        copy_bytes = 0
        for capture in captures:
            values = {
                column.key: getattr(capture, column.key)
                for column in capture.__table__.columns
            }
            copy_bytes += len(values.pop("snapshot_bytes"))
            copy_bytes += self.bookkeeping_size(values)
        locks = list(
            session.scalars(
                select(InfraAutomationTargetLock).where(
                    InfraAutomationTargetLock.run_id == run_id
                )
            )
        )
        return charged - copy_bytes, locks, copy_bytes

    def test_lock_reservation_covers_longest_utf8_break_reason(self):
        self.register()
        request = self.request("target-one", "target-two")
        with patch.object(claims, "_charge", wraps=claims._charge) as charge:
            created = self.admit(request)
        positive = [call.args[2] for call in charge.call_args_list if call.args[2]]
        self.assertEqual(len(positive), 1)
        with self.factory() as session:
            allocated, locks, _ = self.captured_allocation(
                session, created["id"], positive[0]
            )
            self.assertEqual(len(locks), 1)
            lock = locks[0]
            original = {
                column.key: getattr(lock, column.key)
                for column in lock.__table__.columns
            }
            before = runs.get_run(session, created["id"]).retained_bytes
        reason = "\U0001f600" * 256
        for status in ("broken", "resolved"):
            with self.subTest(status=status):
                terminal = {
                    **original,
                    "version": 2,
                    "status": status,
                    "reason": reason,
                    "updated_at": self.now + timedelta(seconds=1),
                }
                self.assertGreaterEqual(allocated, self.bookkeeping_size(terminal))
        with self.credentials():
            targets.break_lock(
                "target-one",
                BreakLockRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_lock_id=lock.id,
                    expected_version=lock.version,
                    acknowledge_uncertainty=True,
                    reason=reason,
                ),
                now=self.now + timedelta(seconds=1),
            )
        with self.factory() as session:
            broken = session.get(InfraAutomationTargetLock, lock.id)
            actual = {
                column.key: getattr(broken, column.key)
                for column in broken.__table__.columns
            }
            self.assertGreaterEqual(allocated, self.bookkeeping_size(actual))
            self.assertEqual(
                runs.get_run(session, created["id"]).retained_bytes, before
            )

    def test_terminal_lock_reservation_quota_denies_entire_admission(self):
        class RollbackProbe(Exception):
            pass

        self.register()
        request = self.request("target-one")
        before = self.counts()
        with self.assertRaises(RollbackProbe):
            with self.credentials(), authorization.authorized_session() as session:
                with patch.object(claims, "_charge", wraps=claims._charge) as charge:
                    created = self.admit(request)
                positive = [
                    call.args[2] for call in charge.call_args_list if call.args[2]
                ]
                self.assertEqual(len(positive), 1)
                _, locks, copies = self.captured_allocation(
                    session, created["id"], positive[0]
                )
                self.assertEqual(len(locks), 1)
                maximum = {
                    column.key: getattr(locks[0], column.key)
                    for column in locks[0].__table__.columns
                }
                maximum.update(version=2, status="resolved", reason="\U0001f600" * 256)
                run_base = (
                    runs.get_run(session, created["id"]).retained_bytes - positive[0]
                )
                required = run_base + copies + self.bookkeeping_size(maximum)
                raise RollbackProbe
        self.assertEqual(self.counts(), before)
        for limit in ("project_bytes", "global_bytes"):
            with self.subTest(limit=limit):
                with patch(
                    "config.engine_bounds",
                    return_value=EngineBounds(**{limit: required - 1}),
                ):
                    with self.assertRaises(LifecycleError) as error:
                        self.admit(request)
                    self.assertEqual(error.exception.status_code, 429)
                self.assertEqual(self.counts(), before)

    def test_run_target_copies_are_charged_once_and_replay_does_not_charge(self):
        self.register()
        request = self.request("target-one")
        created = self.admit(request)
        with self.factory() as db:
            row = runs.get_run(db, created["id"])
            before = row.retained_bytes
            captures = list(db.scalars(select(InfraAutomationRunTarget)))
            self.assertGreaterEqual(
                before,
                len(row.snapshot_bytes)
                + sum(len(item.snapshot_bytes) for item in captures),
            )
        self.admit(request)
        with self.factory() as db:
            self.assertEqual(runs.get_run(db, created["id"]).retained_bytes, before)

    def test_target_copy_quota_failure_rolls_back_the_entire_admission(self):
        self.register()
        request = self.request("target-one")
        with self.credentials():
            snapshot = export_run_snapshot(
                request.workflow_id,
                request.revision_id,
                request.inputs,
                100,
                registry_contract=self.registry,
            )
        with patch(
            "config.engine_bounds",
            return_value=EngineBounds(project_bytes=len(snapshot.canonical_bytes) + 1),
        ):
            with self.assertRaises(LifecycleError) as error:
                self.admit(request)
            self.assertEqual(error.exception.status_code, 429)
        with self.factory() as db:
            for model in (
                InfraAutomationRun,
                InfraAutomationRunTarget,
                InfraAutomationTargetLock,
            ):
                self.assertEqual(db.scalar(select(func.count()).select_from(model)), 0)

    def test_registry_write_fails_before_persistence_when_disk_reserve_is_unavailable(
        self,
    ):
        with patch(
            "infra_automation.storage.shutil.disk_usage",
            return_value=SimpleNamespace(free=0),
        ):
            with self.assertRaises(LifecycleError) as error:
                self.register()
            self.assertEqual(error.exception.status_code, 429)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationTarget)), 0
            )
