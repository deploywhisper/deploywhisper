"""Truthful non-login engine audit identity without human bootstrap bypasses."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from infra_automation.lifecycle import LifecycleError
from models.database import Base
from models.tables import IdentityAccount, IdentityCredential, IdentitySession
from services import infra_automation_engine_support as engine_support
from services import infra_automation_support as support
from services import project_service as authorization
from services.identity_service import IdentityError, IdentityService, validate_username
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class EngineIdentityTests(LifecycleCase):
    def ensure_actor(self):
        with self.credentials(), authorization.authorized_session() as session:
            grant = support.scope(
                session, 100, 100, "automation.request", mutation=True
            )
            return engine_support.ensure_engine_actor(session, grant)

    def test_actor_is_lazy_non_login_and_has_no_human_credentials(self):
        with self.factory() as session:
            self.assertIsNone(
                session.get(IdentityAccount, engine_support.ENGINE_ACTOR_ID)
            )
        self.ensure_actor()
        self.ensure_actor()
        with self.factory() as session:
            row = session.get(IdentityAccount, engine_support.ENGINE_ACTOR_ID)
            self.assertEqual(row.principal_type, "service")
            self.assertFalse(row.enabled)
            self.assertFalse(row.is_admin)
            self.assertEqual(row.username, engine_support.ENGINE_ACTOR_USERNAME)
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(IdentitySession)
                    .where(IdentitySession.principal_id == row.id)
                ),
                0,
            )
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(IdentityCredential)
                    .where(IdentityCredential.principal_id == row.id)
                ),
                0,
            )
        with self.assertRaises(IdentityError):
            validate_username(engine_support.ENGINE_ACTOR_USERNAME)
        with self.assertRaises(IdentityError):
            self.identity.login(
                engine_support.ENGINE_ACTOR_USERNAME, "synthetic-unused"
            )
        with self.assertRaises(IdentityError):
            self.identity.issue_recovery_credential(
                engine_support.ENGINE_ACTOR_USERNAME
            )

    def test_uncredentialed_creation_cannot_seed_account(self):
        with authorization.authorized_session() as session:
            with self.assertRaises(authorization.TrustedAuthorizationError):
                engine_support.ensure_engine_actor(session, None)
        with self.factory() as session:
            self.assertIsNone(
                session.get(IdentityAccount, engine_support.ENGINE_ACTOR_ID)
            )

    def test_conflicting_identity_fails_closed_without_repurposing_human(self):
        with self.factory.begin() as session:
            session.add(
                IdentityAccount(
                    id=engine_support.ENGINE_ACTOR_ID,
                    username="existing-synthetic-human",
                    principal_type="human",
                    password_verifier="synthetic-unused",
                    enabled=True,
                    is_admin=False,
                    authentication_version=1,
                    created_at=self.now,
                )
            )
        with self.assertRaises(LifecycleError):
            self.ensure_actor()
        with self.factory() as session:
            self.assertEqual(
                session.get(
                    IdentityAccount, engine_support.ENGINE_ACTOR_ID
                ).principal_type,
                "human",
            )

    def test_empty_metadata_schema_preserves_first_human_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'fresh.db'}")
            try:
                Base.metadata.create_all(engine)
                factory = sessionmaker(engine, expire_on_commit=False)
                identity = IdentityService(
                    factory, now=lambda: datetime(2026, 10, 19, tzinfo=timezone.utc)
                )
                with factory() as session:
                    self.assertEqual(
                        session.scalar(
                            select(func.count()).select_from(IdentityAccount)
                        ),
                        0,
                    )
                setup = identity.issue_setup_credential()
                account = identity.bootstrap(
                    setup.token.get_secret_value(),
                    "operator",
                    "synthetic-long-password",
                )
                self.assertEqual(account.principal_type, "human")
                with factory() as session:
                    self.assertIsNone(
                        session.get(IdentityAccount, engine_support.ENGINE_ACTOR_ID)
                    )
            finally:
                engine.dispose()
