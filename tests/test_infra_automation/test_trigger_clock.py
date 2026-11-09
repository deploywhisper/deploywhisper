"""Durable machine clock observations survive rejected business operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from infra_automation import claims
from infra_automation.lifecycle import LifecycleError
from models.repositories.infra_automation_runs import get_run
from models.tables import InfraAutomationTriggerClock, Project
from services import infra_automation_engine_service as engine
from services import infra_automation_trigger_authority as authority
from services import project_service as auth
from tests.test_infra_automation.test_trigger_privileges import isolated_case, operation


class TriggerClockTests(unittest.TestCase):
    def test_successful_effect_advances_shared_floor_before_another_run(self):
        with isolated_case() as case:
            first = case.admit()
            case.payload["idempotency_key"] = "second-clock-run"
            second = case.admit()
            base = datetime.now(timezone.utc)
            case.now = base + timedelta(seconds=1)
            owner = operation(
                case, claims.acquire_coordinator, project_id=100, workspace_id=100
            )
            original = authority.live_machine_stamp

            def controlled_clock(db, stamp):
                return original(db, stamp, now=case.now)

            with patch.object(authority, "live_machine_stamp", controlled_clock):
                case.now = base + timedelta(seconds=3)
                self.assertIsNotNone(
                    operation(
                        case,
                        claims.start_run,
                        owner,
                        run_id=first["id"],
                        expected_version=first["version"],
                    )
                )
                observed = case.now
                case.now = base + timedelta(seconds=2)
                with self.assertRaises(LifecycleError) as caught:
                    operation(
                        case,
                        claims.start_run,
                        owner,
                        run_id=second["id"],
                        expected_version=second["version"],
                    )
                self.assertEqual(caught.exception.status_code, 503)
            with case.factory() as db:
                self.assertEqual(get_run(db, first["id"]).state, "running")
                self.assertEqual(get_run(db, second["id"]).state, "queued")
                self.assertEqual(
                    db.get(InfraAutomationTriggerClock, 1).last_seen_at,
                    observed.replace(tzinfo=None),
                )

    def test_expiry_denial_retains_only_time_and_blocks_rollback_without_new_ingress(
        self,
    ):
        with isolated_case() as case:
            run = case.admit()
            with case.factory() as db:
                stamp = engine._document(get_run(db, run["id"])).authority
                before = db.get(Project, 100).display_name
            expiry = authority._instant(case.key["expires_at"])
            observed = expiry + timedelta(seconds=1)
            with self.assertRaises(auth.TrustedAuthorizationError):
                with auth.authorized_session(case.factory) as db:
                    # This flushed business write must not survive the denial.
                    db.get(Project, 100).display_name = "must roll back"
                    db.flush()
                    if not authority.live_machine_stamp(db, stamp, now=observed):
                        raise auth.TrustedAuthorizationError()
            with case.factory() as db:
                self.assertEqual(db.get(Project, 100).display_name, before)
                self.assertEqual(
                    db.get(InfraAutomationTriggerClock, 1).last_seen_at,
                    observed.replace(tzinfo=None),
                )
            # New session, unchanged key, no subsequent signed request.
            with self.assertRaises(LifecycleError) as caught:
                with auth.authorized_session(case.factory) as db:
                    authority.live_machine_stamp(
                        db, stamp, now=expiry - timedelta(seconds=1)
                    )
            self.assertEqual(caught.exception.status_code, 503)

    def test_caught_denial_does_not_commit_unscreened_business_writes(self):
        with isolated_case() as case:
            run = case.admit()
            with case.factory() as db:
                stamp = engine._document(get_run(db, run["id"])).authority
                before = db.get(Project, 100).display_name
            observed = authority._instant(case.key["expires_at"]) + timedelta(seconds=1)
            with self.assertRaises(RuntimeError):
                with auth.authorized_session(case.factory) as db:
                    db.get(Project, 100).display_name = "must roll back"
                    db.flush()
                    self.assertFalse(
                        authority.live_machine_stamp(db, stamp, now=observed)
                    )
                    raise RuntimeError("later business failure")
            with case.factory() as db:
                self.assertEqual(db.get(Project, 100).display_name, before)
                self.assertEqual(
                    db.get(InfraAutomationTriggerClock, 1).last_seen_at,
                    observed.replace(tzinfo=None),
                )

    def test_flush_error_rolls_back_raw_and_orm_writes_but_keeps_clock(self):
        import sqlite3
        from sqlalchemy.exc import IntegrityError

        with isolated_case() as case:
            run = case.admit()
            with case.factory() as db:
                stamp = engine._document(get_run(db, run["id"])).authority
                before = db.get(Project, 100).display_name
            observed = datetime.now(timezone.utc)
            original = authority._retain_clock
            retained = []

            def retain_under_same_lock(db, timestamp):
                # Another process/connection must remain fenced while the
                # rollback-only clock is committed.
                with sqlite3.connect(case.engine.url.database, timeout=0) as outsider:
                    with self.assertRaises(sqlite3.OperationalError):
                        outsider.execute("BEGIN IMMEDIATE")
                original(db, timestamp)
                retained.append(timestamp)

            with patch.object(authority, "_retain_clock", retain_under_same_lock):
                with self.assertRaises(IntegrityError):
                    with auth.authorized_session(case.factory) as db:
                        db.connection().exec_driver_sql(
                            "UPDATE projects SET display_name='raw must roll back' WHERE id=100"
                        )
                        self.assertTrue(
                            authority.live_machine_stamp(db, stamp, now=observed)
                        )
                        db.add(
                            Project(id=100, project_key="duplicate", display_name="bad")
                        )
                        db.flush()
            self.assertEqual(retained, [observed, observed])
            with case.factory() as db:
                self.assertEqual(db.get(Project, 100).display_name, before)
                self.assertEqual(
                    db.get(InfraAutomationTriggerClock, 1).last_seen_at,
                    observed.replace(tzinfo=None),
                )

    def test_observation_storage_failure_fails_closed_without_committing_business(self):
        from unittest.mock import Mock

        with isolated_case() as case:
            run = case.admit()
            with case.factory() as db:
                stamp = engine._document(get_run(db, run["id"])).authority
                before = db.get(Project, 100).display_name
                floor = db.get(InfraAutomationTriggerClock, 1).last_seen_at
            original = authority._retain_clock
            calls = 0
            committed_cleanup = Mock()

            def unavailable_after_business_rollback(db, timestamp):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise LifecycleError(503)
                return original(db, timestamp)

            observed = authority._instant(case.key["expires_at"]) + timedelta(seconds=1)
            with patch.object(
                authority, "_retain_clock", unavailable_after_business_rollback
            ):
                with self.assertRaises(LifecycleError) as caught:
                    with auth.authorized_session(case.factory) as db:
                        auth.register_operation_commit(db, committed_cleanup)
                        db.get(Project, 100).display_name = "must roll back"
                        db.flush()
                        self.assertFalse(
                            authority.live_machine_stamp(db, stamp, now=observed)
                        )
                        raise auth.TrustedAuthorizationError()
                self.assertEqual(caught.exception.status_code, 503)
            committed_cleanup.assert_not_called()
            with case.factory() as db:
                self.assertEqual(db.get(Project, 100).display_name, before)
                self.assertEqual(
                    db.get(InfraAutomationTriggerClock, 1).last_seen_at, floor
                )

    def test_outer_commit_failure_cannot_publish_business_writes_or_clock(self):
        from sqlalchemy.exc import OperationalError
        from sqlalchemy.orm import Session

        with isolated_case() as case:
            run = case.admit()
            with case.factory() as db:
                stamp = engine._document(get_run(db, run["id"])).authority
                before = db.get(Project, 100).display_name
                floor = db.get(InfraAutomationTriggerClock, 1).last_seen_at
            original_commit = Session.commit

            def fail_after_releasing_savepoint(db):
                # Exercise the hardest failure point: nested changes reached
                # the outer transaction, but its durable COMMIT did not occur.
                db.get_nested_transaction().commit()
                raise OperationalError("COMMIT", {}, Exception("synthetic failure"))

            with patch.object(Session, "commit", fail_after_releasing_savepoint):
                with self.assertRaises(OperationalError):
                    with auth.authorized_session(case.factory) as db:
                        db.get(Project, 100).display_name = "must roll back"
                        self.assertTrue(
                            authority.live_machine_stamp(
                                db, stamp, now=datetime.now(timezone.utc)
                            )
                        )
            self.assertIs(Session.commit, original_commit)
            with case.factory() as db:
                self.assertEqual(db.get(Project, 100).display_name, before)
                self.assertEqual(
                    db.get(InfraAutomationTriggerClock, 1).last_seen_at, floor
                )

    def test_lost_sqlite_reservation_never_overwrites_replacement_or_retains_time(self):
        with isolated_case() as case:
            run = case.admit()
            with case.factory() as db:
                stamp = engine._document(get_run(db, run["id"])).authority
                floor = db.get(InfraAutomationTriggerClock, 1).last_seen_at
            with self.assertRaises(LifecycleError) as caught:
                with auth.authorized_session(case.factory) as db:
                    db.get(Project, 100).display_name = "uncommitted old writer"
                    self.assertTrue(
                        authority.live_machine_stamp(
                            db, stamp, now=datetime.now(timezone.utc)
                        )
                    )
                    db.connection().connection.driver_connection.rollback()
                    with case.factory.begin() as replacement:
                        replacement.get(
                            Project, 100
                        ).display_name = "replacement writer"
                    raise LifecycleError(503)
            self.assertEqual(caught.exception.status_code, 503)
            with case.factory() as db:
                self.assertEqual(
                    db.get(Project, 100).display_name, "replacement writer"
                )
                self.assertEqual(
                    db.get(InfraAutomationTriggerClock, 1).last_seen_at, floor
                )

    def test_caught_inner_failure_then_outer_success_retains_checked_time(self):
        with isolated_case() as case:
            run = case.admit()
            with case.factory() as db:
                stamp = engine._document(get_run(db, run["id"])).authority
            observed = authority._instant(case.key["expires_at"]) + timedelta(seconds=1)
            with auth.authorized_session(case.factory) as db:
                try:
                    with db.begin_nested():
                        db.get(Project, 100).display_name = "inner must roll back"
                        self.assertFalse(
                            authority.live_machine_stamp(db, stamp, now=observed)
                        )
                        raise LifecycleError(503)
                except LifecycleError:
                    pass
                db.get(Project, 100).display_name = "outer successful diagnostic"
            with case.factory() as db:
                self.assertEqual(
                    db.get(Project, 100).display_name, "outer successful diagnostic"
                )
                self.assertEqual(
                    db.get(InfraAutomationTriggerClock, 1).last_seen_at,
                    observed.replace(tzinfo=None),
                )

    def test_inner_rollback_cannot_replace_the_highest_operation_observation(self):
        with isolated_case() as case:
            run = case.admit()
            with case.factory() as db:
                stamp = engine._document(get_run(db, run["id"])).authority
            expiry = authority._instant(case.key["expires_at"])
            observed = expiry + timedelta(seconds=1)
            with auth.authorized_session(case.factory) as db:
                try:
                    with db.begin_nested():
                        self.assertFalse(
                            authority.live_machine_stamp(db, stamp, now=observed)
                        )
                        raise LifecycleError(503)
                except LifecycleError:
                    pass
                with self.assertRaises(LifecycleError) as caught:
                    authority.live_machine_stamp(
                        db, stamp, now=expiry - timedelta(seconds=1)
                    )
                self.assertEqual(caught.exception.status_code, 503)
            with case.factory() as db:
                self.assertEqual(
                    db.get(InfraAutomationTriggerClock, 1).last_seen_at,
                    observed.replace(tzinfo=None),
                )
