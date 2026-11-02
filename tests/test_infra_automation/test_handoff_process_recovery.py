"""Physical process exits qualify SQLite commit boundaries with scoped fake ports.

These tests do not qualify host power loss, production delivery, or receiver-owned
action fencing. The child reopens the fixture database and uses real identities.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from infra_automation.handoff import ReceiverCredential
from infra_automation.lifecycle import LifecycleError
from models.tables import (
    InfraAutomationAudit,
    InfraAutomationGrant,
    InfraAutomationHandoff,
    InfraAutomationOutbox,
    InfraAutomationRun,
)
from services.infra_automation_handoffs import HandoffService
from tests.test_infra_automation import test_handoff_service as fixture


_CHILD = r"""
import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import sys

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import config
from infra_automation.approval_eligibility import EvidenceFacts, LiveBinding
from infra_automation.contracts import RegistryContract
from infra_automation.decisions import DecisionBinding
from infra_automation.handoff import (
    DispatchHandoffRequest, PrepareHandoffRequest, ReceiverCredential,
)
from infra_automation.receiver_protocol import receiver_message_bytes
from models.repositories import infra_automation_handoffs as repository
from services import project_service as auth
from services.identity_service import IdentityService
from services.infra_automation_decisions import DecisionMaterial, DecisionService, MaterialWitness
from services.infra_automation_handoffs import HandoffService, _grant_token, _message

try:
    database, private_file, boundary, operation_id = sys.argv[1:]
    data = json.loads(Path(private_file).read_text())
    now = datetime.fromisoformat(data['now'])
    engine = create_engine('sqlite:///' + database, connect_args={'timeout': 10})
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
    factory = sessionmaker(engine, expire_on_commit=False)
    config.settings = replace(
        config.settings, identity_profile='https', identity_origin=data['origin'],
        authorization_profile='legacy-evaluation',
    )
    auth.SessionLocal = factory
    identity = IdentityService(
        factory, now=lambda: now, security_profile='https',
        trusted_origin=data['origin'],
    )
    material = DecisionMaterial(
        binding=DecisionBinding.model_validate_json(data['binding']),
        evidence=EvidenceFacts.model_validate_json(data['evidence']),
        live=LiveBinding.model_validate_json(data['live']),
        registry_contract=RegistryContract.model_validate_json(data['registry']),
    )
    # This child fixture's material is immutable for its entire process lifetime.
    decisions = DecisionService(
        material_port=lambda *args: material,
        material_witness_port=lambda session, scope: MaterialWitness(
            source_id='immutable-child-material', scope_digest=scope.digest,
            generations=tuple(1 for _ in scope.receipts),
        ),
        clock=lambda: now,
    )
    def delivery(envelope, credential):
        assert not auth.has_authorized_session()
        assert credential == config.handoff_credentials('dispatch')['github']
        if boundary == 'dispatch_claimed':
            os._exit(75)
        raise AssertionError('Unexpected delivery')
    service = HandoffService(
        decision_service=decisions, delivery_port=delivery,
        ref_port=lambda snapshot: snapshot.definition.pipeline_workflow_revision,
        clock=lambda: now, session_factory=factory,
    )
    audit = service._audit
    def crash_audit(session, row, **kwargs):
        audit(session, row, **kwargs)
        session.flush()
        if boundary == 'prepare_uncommitted' and kwargs['event'] == 'handoff_prepared':
            os._exit(73)
        if boundary == 'consume_uncommitted' and kwargs['event'] == 'handoff_consumed':
            os._exit(76)
    service._audit = crash_audit
    if boundary.startswith('prepare_'):
        with auth.credential_context(
            identity, data['token'], csrf_token=data['csrf'], mutation=True,
        ):
            service.prepare(PrepareHandoffRequest.model_validate_json(data['request']))
        if boundary == 'prepare_committed':
            os._exit(74)
    elif boundary == 'dispatch_claimed':
        with auth.credential_context(
            identity, data['token'], csrf_token=data['csrf'], mutation=True,
        ):
            service.dispatch(operation_id, DispatchHandoffRequest(
                project_id=100, workspace_id=100, expected_version=1,
                reason='Send approved work',
            ))
    elif boundary.startswith('consume_'):
        with factory() as session:
            row = repository.get_operation(session, operation_id)
            grant = repository.get_grant(session, operation_id)
            message = receiver_message_bytes(_message(row))
            token = _grant_token(row, grant.key_ref)
            receiver = ReceiverCredential(
                row.receiver_id, config.handoff_credentials('receiver')['receiver'],
            )
        service.consume(message, token, receiver)
        if boundary == 'consume_committed':
            os._exit(77)
    os._exit(91)
except BaseException as error:
    # Never render credentials, material, bearer values, or exception payloads.
    sys.stderr.write(type(error).__name__ + '\n')
    sys.stderr.flush()
    os._exit(90)
"""


class HandoffProcessRecoveryTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing fixture without inheriting/rediscovering its tests.
        self.fixture = fixture.HandoffServiceTests(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        credentials = patch(
            "config.handoff_credentials",
            return_value={"receiver": "r" * 32, "github": "d" * 32},
        )
        credentials.start()
        self.addCleanup(credentials.stop)
        self.fixture.receiver = ReceiverCredential(
            self.fixture.material.binding.receiver_id, "r" * 32
        )

        def deliver(envelope, dispatch_credential):
            self.assertEqual(dispatch_credential, "d" * 32)
            self.fixture.sent.append(envelope)

        self.fixture.handoffs.delivery_port = deliver
        self.database = Path(self.fixture.temp.name) / "lifecycle.db"
        self.private_file = Path(self.fixture.temp.name) / "private-child-input.json"
        token, csrf = self.fixture.tokens["human-a"]
        material = self.fixture.material
        data = {
            "token": token,
            "csrf": csrf,
            "origin": self.fixture.origin,
            "now": self.fixture.now.isoformat(),
            "binding": material.binding.model_dump_json(),
            "evidence": material.evidence.model_dump_json(),
            "live": material.live.model_dump_json(),
            "registry": material.registry_contract.model_dump_json(),
            "request": self.fixture.request().model_dump_json(),
        }
        descriptor = os.open(
            self.private_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "w") as private:
            json.dump(data, private)
        self.assertEqual(stat.S_IMODE(self.private_file.stat().st_mode), 0o600)
        self.assertFalse(self.private_file.is_relative_to(Path.cwd()))

    def crash(self, boundary, expected_code, operation_id=""):
        environment = dict(os.environ)
        environment.update(
            DEPLOYWHISPER_INFRA_GRANT_KEY="g" * 32,
            DEPLOYWHISPER_INFRA_RECEIVER_CREDENTIALS=json.dumps({"receiver": "r" * 32}),
            DEPLOYWHISPER_INFRA_DISPATCH_CREDENTIALS=json.dumps({"github": "d" * 32}),
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                _CHILD,
                str(self.database),
                str(self.private_file),
                boundary,
                operation_id,
            ],
            env=environment,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.stdout, b"")
        self.assertEqual(
            completed.returncode,
            expected_code,
            f"Child boundary {boundary}: exit {completed.returncode}; "
            f"error class {completed.stderr.decode(errors='replace')}",
        )
        self.assertEqual(completed.stderr, b"")

    def reopen(self):
        self.fixture.engine.dispose()
        engine = create_engine(
            f"sqlite:///{self.database}", connect_args={"timeout": 10}
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        self.addCleanup(engine.dispose)
        factory = sessionmaker(engine, expire_on_commit=False)
        service = HandoffService(
            decision_service=self.fixture.service,
            delivery_port=self.fixture.handoffs.delivery_port,
            ref_port=self.fixture.handoffs.ref_port,
            clock=lambda: self.fixture.now,
            session_factory=factory,
        )
        return factory, service

    def snapshot(self, factory):
        """Compare all durable handoff, run, and audit facts across abrupt exits."""
        with factory() as session:
            return {
                model.__tablename__: sorted(
                    (
                        tuple(
                            getattr(row, column.key)
                            for column in model.__table__.columns
                        )
                        for row in session.scalars(select(model))
                    ),
                    key=repr,
                )
                for model in (
                    InfraAutomationHandoff,
                    InfraAutomationOutbox,
                    InfraAutomationGrant,
                    InfraAutomationRun,
                    InfraAutomationAudit,
                )
            }

    def test_exit_before_prepare_commit_rolls_back_intent_and_audit(self):
        before = self.snapshot(self.fixture.factory)
        self.crash("prepare_uncommitted", 73)
        factory, _ = self.reopen()
        self.assertEqual(self.snapshot(factory), before)
        with factory() as session:
            for model in (
                InfraAutomationHandoff,
                InfraAutomationOutbox,
                InfraAutomationGrant,
            ):
                self.assertEqual(list(session.scalars(select(model))), [])

    def test_exit_after_prepare_commit_recovers_identical_operation_and_verifier(self):
        self.crash("prepare_committed", 74)
        factory, service = self.reopen()
        before = self.snapshot(factory)
        with factory() as session:
            row = session.scalar(select(InfraAutomationHandoff))
            operation_id = row.id
            self.assertEqual(row.state, "prepared")
            grant = session.scalar(select(InfraAutomationGrant))
            self.assertEqual(grant.status, "available")
            self.assertIsNone(grant.receipt_bytes)
            self.assertEqual(len(grant.verifier_digest), 71)
            self.assertEqual(
                session.scalar(select(InfraAutomationOutbox)).state, "pending"
            )
        with self.fixture.credentials():
            recovered = service.prepare(self.fixture.request())
            self.assertEqual(recovered["id"], operation_id)
            self.assertEqual(recovered["state"], "prepared")
            with self.assertRaises(LifecycleError):
                service.prepare(
                    self.fixture.request().model_copy(
                        update={"idempotency_key": "replacement"}
                    )
                )
        self.assertEqual(self.snapshot(factory), before)
        self.assertEqual(self.fixture.sent, [])

    def test_exit_in_delivery_preserves_claim_and_never_resends(self):
        operation = self.fixture.prepare()
        self.crash("dispatch_claimed", 75, operation["id"])
        factory, service = self.reopen()
        before = self.snapshot(factory)
        with factory() as session:
            row = session.get(InfraAutomationHandoff, operation["id"])
            self.assertEqual(row.state, "sending")
            self.assertEqual(
                session.scalar(select(InfraAutomationOutbox)).state, "sending"
            )
            run = session.scalar(
                select(InfraAutomationRun).where(
                    InfraAutomationRun.id == self.fixture.run.id
                )
            )
            self.assertEqual(run.state, "handing_off")
            self.assertTrue(run.external_possible)
        with self.fixture.credentials():
            recovered = service.get_operation(operation["id"], 100, 100)
            self.assertEqual(recovered["state"], "delivery_unknown")
            self.assertEqual(service.prepare(self.fixture.request()), recovered)
        self.fixture.handoffs = service
        with self.assertRaises(LifecycleError):
            self.fixture.dispatch(recovered)
        self.assertEqual(self.fixture.sent, [])
        self.assertEqual(self.snapshot(factory), before)

    def test_exit_before_consume_commit_rolls_back_grant_receipt_and_operation(self):
        operation = self.fixture.dispatch(self.fixture.prepare())
        before = self.snapshot(self.fixture.factory)
        self.crash("consume_uncommitted", 76, operation["id"])
        factory, service = self.reopen()
        self.assertEqual(self.snapshot(factory), before)
        with factory() as session:
            grant = session.scalar(select(InfraAutomationGrant))
            self.assertEqual(grant.status, "available")
            self.assertIsNone(grant.receipt_bytes)
            self.assertIsNone(grant.receipt_digest)
            self.assertIsNone(grant.consumed_at)
        envelope = self.fixture.sent[0]
        result = service.consume(
            envelope.message_bytes, envelope.grant_token, self.fixture.receiver
        )
        self.assertEqual(result["state"], "consumed")
        self.assertEqual(result["receipt"]["sequence"], 1)

    def test_exit_after_consume_commit_preserves_receipt_and_rejects_reconsume(self):
        operation = self.fixture.dispatch(self.fixture.prepare())
        self.crash("consume_committed", 77, operation["id"])
        factory, service = self.reopen()
        before = self.snapshot(factory)
        recovered = service.receiver_status(operation["id"], self.fixture.receiver)
        self.assertEqual(recovered["state"], "consumed")
        self.assertEqual(recovered["receipt"]["sequence"], 1)
        with factory() as session:
            grant = session.scalar(select(InfraAutomationGrant))
            self.assertEqual(grant.status, "consumed")
            self.assertIsNotNone(grant.receipt_bytes)
            self.assertIsNotNone(grant.receipt_digest)
            self.assertIsNotNone(grant.consumed_at)
            run = session.scalar(
                select(InfraAutomationRun).where(
                    InfraAutomationRun.id == self.fixture.run.id
                )
            )
            self.assertEqual(run.state, "external_running")
            self.assertTrue(run.external_possible)
        envelope = self.fixture.sent[0]
        with self.assertRaises(LifecycleError):
            service.consume(
                envelope.message_bytes, envelope.grant_token, self.fixture.receiver
            )
        self.assertEqual(
            service.receiver_status(operation["id"], self.fixture.receiver), recovered
        )
        self.assertEqual(self.snapshot(factory), before)
        self.assertEqual(len(self.fixture.sent), 1)
