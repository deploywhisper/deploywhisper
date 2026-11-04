"""R1/R2 regression proof against real runner attempts and SQLite transactions."""

from __future__ import annotations

from datetime import timedelta
import json
import unittest
from unittest.mock import patch
from urllib.parse import quote

from sqlalchemy import func, select

from infra_automation import claims as engine
from infra_automation.lifecycle import LifecycleError
from infra_automation.runner import claims
from models.repositories import infra_automation_runs as runs
from models.tables import InfraAutomationAudit, InfraAutomationRunnerTask
from services import infra_automation_runner_tasks as tasks
from services.infra_automation_support import canonical, digest
from tests.test_infra_automation import test_runner_attempts as attempts


class RunnerReviewSecurityTests(unittest.TestCase):
    def setUp(self):
        self.case = attempts.RunnerAttemptTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def retained(self):
        case = self.case
        with case.factory() as db:
            row = runs.get_attempt(db, case.pending.id)
            task = db.get(InfraAutomationRunnerTask, case.pending.id)
            run = runs.get_run(db, case.run.id)
            return (
                row.state,
                row.version,
                row.last_observed_at,
                row.lease_until,
                row.logs_json,
                row.uploads_json,
                row.output_json,
                row.output_digest,
                task.sequence,
                task.upload_id,
                task.upload_digest,
                task.upload_bytes,
                run.version,
                run.retained_bytes,
                db.scalar(select(func.count()).select_from(InfraAutomationAudit)),
            )

    def send(self, message, *, raw=None, now=None):
        case = self.case
        return tasks.operate(
            message,
            case.credential,
            case.assignment["task_token"],
            upload_bytes=raw,
            now=now,
        )

    def prepare(self, operation):
        case = self.case
        sequence = 1
        if operation != "claim":
            self.send(case.message("claim", sequence), now=case.now)
            sequence += 1
        raw = canonical(
            [{"name": "main.tf", "content": 'resource "null_resource" "fixture" {}'}]
        )
        if operation == "complete":
            self.send(
                case.message(
                    "upload",
                    sequence,
                    atomic_upload_id="fixture",
                    upload_digest=digest(raw),
                ),
                raw=raw,
                now=case.now,
            )
            sequence += 1
        fields = {
            "claim": {},
            "heartbeat": {},
            "log": {"log": "safe diagnostic"},
            "upload": {"atomic_upload_id": "fixture", "upload_digest": digest(raw)},
            "complete": {"atomic_upload_id": "fixture", "state": "succeeded"},
        }[operation]
        return case.message(
            operation, sequence, **fields
        ), raw if operation == "upload" else None

    def test_percent_encoded_task_credential_is_rejected_before_retention(self):
        case = self.case
        self.send(case.message("claim", 1), now=case.now)
        encoded = "".join(
            "%%%02x" % ord(char) for char in case.assignment["task_token"]
        )
        before = self.retained()
        with self.assertRaises(LifecycleError):
            self.send(case.message("log", 2, log=encoded), now=case.now)
        self.assertEqual(self.retained(), before)

    def test_parse_delay_cannot_renew_expired_attempt(self):
        case = self.case
        message, _ = self.prepare("heartbeat")
        before = self.retained()
        observed = [case.now]
        real_parse = claims.parse_message

        def delayed_parse(value):
            result = real_parse(value)
            observed[0] = case.now + timedelta(seconds=31)
            return result

        with (
            patch.object(
                engine,
                "_now",
                side_effect=lambda value: observed[0] if value is None else value,
            ),
            patch.object(claims, "parse_message", side_effect=delayed_parse),
            self.assertRaises(LifecycleError),
        ):
            self.send(message)
        self.assertEqual(self.retained(), before)

    def fresh_case(self):
        self.case.doCleanups()
        self.case = attempts.RunnerAttemptTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        return self.case

    def test_supported_encoded_credential_corpus_is_rejected_in_every_retained_surface(
        self,
    ):
        from pydantic import ValidationError

        case = self.case
        self.send(case.message("claim", 1), now=case.now)
        secrets = (
            case.assignment["task_token"],
            case.credential.token,
            "enroll-v1-" + "e" * 64,
            "runner-v1-" + "f" * 64,
        )
        for credential_index, secret in enumerate(secrets):
            percent = "".join("%%%02x" % ord(char) for char in secret)
            variants = (
                percent,
                percent.upper(),
                quote(percent, safe=""),
                secret[:5] + "".join("%%%02x" % ord(char) for char in secret[5:]),
            )
            for variant_index, encoded in enumerate(variants):
                for surface in ("log", "upload_name", "upload_content", "upload_id"):
                    with self.subTest(
                        credential=credential_index,
                        variant=variant_index,
                        surface=surface,
                    ):
                        before = self.retained()
                        with self.assertRaises((LifecycleError, ValidationError)):
                            if surface == "log":
                                self.send(
                                    case.message("log", 2, log="diagnostic " + encoded),
                                    now=case.now,
                                )
                            else:
                                name = (
                                    encoded + ".tf"
                                    if surface == "upload_name"
                                    else "main.tf"
                                )
                                content = (
                                    "# "
                                    + encoded
                                    + '\nresource "null_resource" "fixture" {}'
                                    if surface == "upload_content"
                                    else 'resource "null_resource" "fixture" {}'
                                )
                                raw = canonical([{"name": name, "content": content}])
                                self.send(
                                    case.message(
                                        "upload",
                                        2,
                                        atomic_upload_id=encoded
                                        if surface == "upload_id"
                                        else "fixture",
                                        upload_digest=digest(raw),
                                    ),
                                    raw=raw,
                                    now=case.now,
                                )
                        self.assertEqual(self.retained(), before)

    def test_encoded_chunk_join_is_rejected_but_harmless_encoding_is_retained(self):
        for credential_index in range(4):
            case = self.fresh_case()
            secret = (
                case.assignment["task_token"],
                case.credential.token,
                "enroll-v1-" + "e" * 64,
                "runner-v1-" + "f" * 64,
            )[credential_index]
            encoded = "".join("%%%02x" % ord(char) for char in secret)
            # Split the prefix before it is recognizable; tokens are split halfway.
            split = 6 if credential_index else 96
            self.send(case.message("claim", 1), now=case.now)
            self.send(case.message("log", 2, log="progress%20ready "), now=case.now)
            self.send(case.message("log", 3, log=encoded[:split]), now=case.now)
            before = self.retained()
            with (
                self.subTest(credential=credential_index),
                self.assertRaises(LifecycleError),
            ):
                self.send(case.message("log", 4, log=encoded[split:]), now=case.now)
            self.assertEqual(self.retained(), before)
            with case.factory() as db:
                self.assertEqual(
                    json.loads(runs.get_attempt(db, case.pending.id).logs_json)[0][
                        "text"
                    ],
                    "progress%20ready ",
                )

    def assert_delayed_operation_denied(self, operation, boundary, expiry):
        from models.tables import InfraAutomationCoordinatorLease, InfraAutomationRunner

        case = self.fresh_case()
        message, raw = self.prepare(operation)
        expired_at = case.wire_deadline()
        if expiry == "credential":
            expired_at = case.now + timedelta(seconds=1)
            with case.factory.begin() as db:
                db.get(
                    InfraAutomationRunner, case.runner.id
                ).credential_expires_at = expired_at
        elif expiry == "coordinator":
            expired_at = case.now + timedelta(seconds=1)
            with case.factory.begin() as db:
                db.get(InfraAutomationCoordinatorLease, 1).lease_until = expired_at
        before = self.retained()
        observed = [case.now]
        target, name = {
            "parse": (claims, "parse_message"),
            "credential_screen": (claims, "_secret_free"),
            "effect": (
                engine,
                {
                    "claim": "start_attempt",
                    "heartbeat": "heartbeat_attempt",
                    "log": "append_log",
                    "upload": "register_upload",
                    "complete": "complete_attempt",
                }[operation],
            ),
            "audit": (runs, "append_audit"),
            "projection": (claims, "scope_for"),
            "engine_log_screen": (engine.support, "screened_label"),
        }[boundary]
        real = getattr(target, name)
        calls = [0]

        def delay(*args, **kwargs):
            result = real(*args, **kwargs)
            calls[0] += 1
            selected = (
                boundary not in {"audit", "projection", "engine_log_screen"}
                or boundary == "audit"
                and kwargs.get("event_type", "").startswith("runner.")
                or boundary == "projection"
                and calls[0] == 2
                or boundary == "engine_log_screen"
                and args[0] == "safe diagnostic"
            )
            if selected:
                observed[0] = expired_at
            return result

        with (
            patch.object(
                engine,
                "_now",
                side_effect=lambda value: observed[0] if value is None else value,
            ),
            patch.object(target, name, side_effect=delay),
            self.assertRaises(LifecycleError),
        ):
            self.send(message, raw=raw)
        self.assertEqual(observed[0], expired_at, "expiry boundary was not exercised")
        self.assertEqual(self.retained(), before)

    def test_all_operations_recheck_after_parsing_and_screening(self):
        for operation in ("claim", "heartbeat", "log", "upload", "complete"):
            for boundary in ("parse", "credential_screen"):
                for expiry in ("wire_lease", "credential", "coordinator"):
                    with self.subTest(
                        operation=operation, boundary=boundary, expiry=expiry
                    ):
                        self.assert_delayed_operation_denied(
                            operation, boundary, expiry
                        )

    def test_all_effects_audits_and_projections_roll_back_on_expiry(self):
        for operation in ("claim", "heartbeat", "log", "upload", "complete"):
            for boundary in ("effect", "audit", "projection"):
                for expiry in ("wire_lease", "credential", "coordinator"):
                    with self.subTest(
                        operation=operation, boundary=boundary, expiry=expiry
                    ):
                        self.assert_delayed_operation_denied(
                            operation, boundary, expiry
                        )

    def test_expiry_inside_engine_log_screening_rolls_back_every_effect(self):
        for expiry in ("wire_lease", "credential", "coordinator"):
            with self.subTest(expiry=expiry):
                self.assert_delayed_operation_denied("log", "engine_log_screen", expiry)

    def test_explicit_clock_injection_remains_deterministic(self):
        case = self.case
        message, _ = self.prepare("heartbeat")
        real_parse = claims.parse_message
        observed = [case.now]

        def delayed_parse(value):
            result = real_parse(value)
            observed[0] = case.now + timedelta(seconds=31)
            return result

        with (
            patch.object(
                engine,
                "_now",
                side_effect=lambda value: observed[0] if value is None else value,
            ),
            patch.object(claims, "parse_message", side_effect=delayed_parse),
        ):
            result = self.send(message, now=case.now)
        self.assertEqual(result["sequence"], 2)

    def test_final_authority_validation_itself_cannot_hide_elapsed_time(self):
        from models.tables import InfraAutomationCoordinatorLease, InfraAutomationRunner

        for operation in ("claim", "heartbeat", "log", "upload", "complete"):
            for expiry in (
                "wire_lease",
                "credential",
                "credential_fractional",
                "coordinator",
            ):
                with self.subTest(operation=operation, expiry=expiry):
                    case = self.fresh_case()
                    message, raw = self.prepare(operation)
                    expired_at = case.wire_deadline()
                    if expiry != "wire_lease":
                        expired_at = case.now + timedelta(seconds=1)
                        if expiry == "credential_fractional":
                            expired_at = case.now.replace(microsecond=0) + timedelta(
                                seconds=2
                            )
                        with case.factory.begin() as db:
                            if expiry in ("credential", "credential_fractional"):
                                db.get(
                                    InfraAutomationRunner, case.runner.id
                                ).credential_expires_at = expired_at + (
                                    timedelta(microseconds=500000)
                                    if expiry == "credential_fractional"
                                    else timedelta(0)
                                )
                            else:
                                db.get(
                                    InfraAutomationCoordinatorLease, 1
                                ).lease_until = expired_at
                    before = self.retained()
                    observed, audit_finished = [case.now], [False]
                    real_audit, real_attempt = runs.append_audit, engine._attempt

                    def audit(*args, **kwargs):
                        result = real_audit(*args, **kwargs)
                        if kwargs.get("event_type", "").startswith("runner."):
                            audit_finished[0] = True
                        return result

                    def delayed_authority(*args, **kwargs):
                        result = real_attempt(*args, **kwargs)
                        if audit_finished[0]:
                            observed[0] = expired_at
                        return result

                    with (
                        patch.object(
                            engine,
                            "_now",
                            side_effect=lambda value: (
                                observed[0] if value is None else value
                            ),
                        ),
                        patch.object(runs, "append_audit", side_effect=audit),
                        patch.object(engine, "_attempt", side_effect=delayed_authority),
                        self.assertRaises(LifecycleError),
                    ):
                        self.send(message, raw=raw)
                    self.assertEqual(observed[0], expired_at)
                    self.assertEqual(self.retained(), before)
