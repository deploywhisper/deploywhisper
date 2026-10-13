"""Live membership authorization at the operation's SQLite transaction boundary."""

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import secrets
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import config
from models.database import Base
from models.repositories.project_memberships import upsert_membership
from models.tables import (
    AnalysisReport,
    IdentityAccount,
    IdentitySession,
    Project,
    ProjectAuthorizationAudit,
    ProjectWorkspace,
)
from services.identity_service import IdentityService
from services import project_service as auth


class ProjectAuthorizationTests(unittest.TestCase):
    def test_read_only_cannot_start_analysis_with_forged_legacy_role(self):
        from services.analysis_service import analyze_uploaded_files

        self.member("read-only")
        with (
            self.context(mutation=True),
            patch("services.analysis_service.build_analysis_artifacts") as build,
        ):
            with self.assertRaises(auth.TrustedAuthorizationError):
                analyze_uploaded_files([], project_id=1, workspace_id=1)
        build.assert_not_called()

    def test_revocation_at_persistence_remains_authorization_denial(self):
        from services.analysis_service import analyze_uploaded_files

        self.member("contributor")
        with (
            self.context(mutation=True),
            patch("services.analysis_service.build_analysis_artifacts"),
            patch(
                "services.analysis_service.persist_analysis_report",
                side_effect=auth.TrustedAuthorizationError,
            ),
        ):
            with self.assertRaises(auth.TrustedAuthorizationError):
                analyze_uploaded_files([], project_id=1, workspace_id=1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'auth.db'}")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.factory_patch = patch.object(auth, "SessionLocal", self.factory)
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.now = datetime(2026, 10, 13, tzinfo=UTC)
        self.service = IdentityService(
            self.factory,
            now=lambda: self.now,
            security_profile="https",
            trusted_origin="https://identity.invalid",
        )
        self.profile = patch.object(
            config,
            "settings",
            SimpleNamespace(
                **{
                    **vars(config.settings),
                    "authorization_profile": "legacy-evaluation",
                    "identity_decision_mode": "shared",
                }
            ),
        )
        self.profile.start()
        with self.factory.begin() as db:
            for i in (1, 2, 3):
                db.add(
                    Project(
                        id=i,
                        project_key=f"project-{i}",
                        display_name=f"Project {i}",
                        authorization_required=i != 3,
                    )
                )
            db.flush()
            for i in (1, 2, 3, 4):
                db.add(
                    ProjectWorkspace(
                        id=i,
                        project_id=1 if i < 3 else 2,
                        workspace_key=f"ws-{i}",
                        display_name=f"Workspace {i}",
                    )
                )
            db.flush()
            for i in (1, 2, 3):
                db.add(
                    AnalysisReport(
                        id=i,
                        project_id=i,
                        workspace_id=1 if i == 1 else 3 if i == 2 else None,
                        risk_score=0,
                        severity="low",
                        recommendation="go",
                        top_risk="synthetic",
                        parse_summary="synthetic",
                        narrative_opening="synthetic",
                        narrative_explanation="synthetic",
                    )
                )
        self.token, self.csrf = self.principal("human-a", is_admin=True)

    def tearDown(self):
        self.profile.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def test_verified_global_settings_require_memberships_for_unmarked_projects(self):
        with self.factory.begin() as db:
            for project in db.scalars(select(Project)):
                project.authorization_required = False
        config.settings.authorization_profile = "verified"
        with self.context(mutation=True), auth.authorized_session() as db:
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_global_configuration(db, mutation=True)
        self.member("admin", project=1)
        with self.context(mutation=True), auth.authorized_session() as db:
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_global_configuration(db, mutation=True)
        self.member("admin", project=2)
        self.member("admin", project=3)
        with self.context(mutation=True), auth.authorized_session() as db:
            self.assertEqual(
                auth.guard_global_configuration(db, mutation=True).principal_id,
                "human-a",
            )

    def principal(
        self, name, *, is_admin=False, principal_type="human", audience="human"
    ):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.factory.begin() as db:
            account = db.get(IdentityAccount, name)
            if account is None:
                account = IdentityAccount(
                    id=name,
                    username=name,
                    principal_type=principal_type,
                    password_verifier="synthetic-unused",
                    is_admin=is_admin,
                    enabled=True,
                    authentication_version=1,
                    created_at=self.now,
                )
                db.add(account)
                db.flush()
            db.add(
                IdentitySession(
                    id=secrets.token_hex(16),
                    principal_id=name,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    csrf_hash=hashlib.sha256(csrf.encode()).hexdigest(),
                    audience=audience,
                    security_profile="https",
                    trusted_origin="https://identity.invalid",
                    authentication_version=account.authentication_version,
                    created_at=self.now,
                    last_seen_at=self.now,
                    expires_at=self.now + timedelta(hours=1),
                )
            )
        return token, csrf

    def member(self, role="admin", *, principal="human-a", project=1, workspace=None):
        with self.factory.begin() as db:
            return upsert_membership(
                db,
                principal_id=principal,
                project_id=project,
                workspace_id=workspace,
                role=role,
            )

    @contextmanager
    def context(self, *, mutation=False, token=None, csrf=None):
        with auth.credential_context(
            self.service,
            token or self.token,
            csrf_token=csrf or self.csrf,
            mutation=mutation,
        ):
            yield

    def test_missing_context_never_reads_protected_scope(self):
        with auth.authorized_session(self.factory) as db:
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_report(db, 1)
            self.assertEqual(auth.guard_report(db, 3).id, 3)

    def test_role_project_workspace_capability_matrix(self):
        for role, capabilities in auth.PROJECT_ROLE_CAPABILITIES.items():
            self.member(role, workspace=1)
            for capability in (
                "report.read",
                "report.review",
                "settings.manage",
                "automation.read",
                "automation.request",
                "automation.draft",
                "automation.publish",
                "automation.decision",
                "automation.admin",
            ):
                with (
                    self.subTest(role=role, capability=capability),
                    self.context(mutation=True),
                    auth.authorized_session() as db,
                ):
                    if capability in capabilities:
                        auth.guard_project(db, 1, workspace_id=1, capability=capability)
                    else:
                        with self.assertRaises(auth.TrustedAuthorizationError):
                            auth.guard_project(
                                db, 1, workspace_id=1, capability=capability
                            )
                    for project, workspace in ((1, 2), (2, 3), (2, 4), (1, None)):
                        with self.assertRaises(auth.TrustedAuthorizationError):
                            auth.guard_project(
                                db,
                                project,
                                workspace_id=workspace,
                                capability=capability,
                            )

    def test_legacy_roles_cannot_grant_automation(self):
        for role in auth.PROJECT_ROLE_CAPABILITIES:
            self.assertFalse(
                auth.authorize_project_action(
                    role=role,
                    capability="automation.read",
                    project_key="project-1",
                    allowed_project_keys=["project-1"],
                ).allowed
            )

    def test_predicates_hide_other_projects_before_limit_and_count(self):
        self.member("read-only", workspace=1)
        with self.context(), auth.authorized_session() as db:
            predicate = auth.visible_report_predicate(db)
            self.assertEqual(
                [
                    r.id
                    for r in db.scalars(
                        select(AnalysisReport)
                        .where(predicate)
                        .order_by(AnalysisReport.id)
                    )
                ],
                [1, 3],
            )
            self.assertEqual(
                db.scalars(
                    select(AnalysisReport)
                    .where(predicate)
                    .order_by(AnalysisReport.id)
                    .offset(1)
                    .limit(1)
                )
                .one()
                .id,
                3,
            )

    def test_report_marker_protects_entire_project_context(self):
        with self.factory.begin() as db:
            db.get(AnalysisReport, 3).authorization_required = True
        with auth.authorized_session(self.factory) as db:
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_project(db, 3, capability="settings.manage")
            self.assertEqual(
                list(
                    db.scalars(
                        select(AnalysisReport).where(auth.visible_report_predicate(db))
                    )
                ),
                [],
            )

    def test_reentrant_session_and_rollback(self):
        with (
            self.assertRaises(RuntimeError),
            self.context(mutation=True),
            auth.authorized_session() as first,
        ):
            with auth.authorized_session() as second:
                self.assertIs(first, second)
                first.get(Project, 3).display_name = "changed"
            raise RuntimeError("rollback")
        with self.factory() as db:
            self.assertEqual(db.get(Project, 3).display_name, "Project 3")

    def test_bootstrap_only_once_audits_and_invalidates_old_session(self):
        with self.context(mutation=True):
            result = auth.bootstrap_project_membership(1)
        self.assertEqual(result.role, "admin")
        with (
            self.context(),
            auth.authorized_session() as db,
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.guard_report(db, 1)
        self.token, self.csrf = self.principal("human-a")
        with (
            self.context(mutation=True),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.bootstrap_project_membership(1)
        with self.factory() as db:
            self.assertEqual(
                len(list(db.scalars(select(ProjectAuthorizationAudit)))), 1
            )

    def test_membership_changes_invalidate_target_and_preserve_versions(self):
        self.member()
        target, target_csrf = self.principal("human-b")
        with self.context(mutation=True):
            result = auth.assign_project_membership(
                1, "human-b", "reviewer", workspace_id=1
            )
        self.assertEqual(result.authorization_version, 1)
        with (
            self.context(token=target, csrf=target_csrf),
            auth.authorized_session() as db,
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.guard_report(db, 1)
        with self.context(mutation=True):
            result = auth.revoke_project_membership(1, "human-b")
        self.assertEqual(result.authorization_version, 2)
        self.assertFalse(result.enabled)

    def test_nonhuman_or_wrong_audience_cannot_use_human_port(self):
        for principal_type, audience in (
            ("service", "human"),
            ("agent", "human"),
            ("runner", "human"),
            ("human", "service"),
        ):
            name = f"{principal_type}-{audience}"
            token, csrf = self.principal(
                name, principal_type=principal_type, audience=audience
            )
            self.member(principal=name)
            with (
                self.context(token=token, csrf=csrf),
                auth.authorized_session() as db,
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                auth.guard_report(db, 1)

    def test_shared_decision_requires_distinct_principal_and_review(self):
        self.member("reviewer")
        context = auth.DecisionContext(
            project_id=1,
            workspace_id=1,
            report_id=1,
            requester_principal_id="human-a",
            object_id="seeded-context",
        )
        with (
            self.context(mutation=True),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.authorize_automation_decision(context)
        self.principal("human-b")
        context = auth.DecisionContext(
            project_id=1,
            workspace_id=1,
            report_id=1,
            requester_principal_id="human-b",
            object_id="seeded-context",
        )
        with self.context(mutation=True):
            self.assertEqual(
                auth.authorize_automation_decision(context)["decision_kind"],
                "independent-approval",
            )

    def test_single_operator_acknowledgement_not_independent_approval(self):
        self.member("admin")
        context = auth.DecisionContext(
            project_id=1,
            workspace_id=1,
            report_id=1,
            requester_principal_id="human-a",
            object_id="seeded-context",
        )
        with (
            patch.object(
                config.settings,
                "identity_decision_mode",
                "single-operator",
                create=True,
            ),
            self.context(mutation=True),
        ):
            self.assertEqual(
                auth.authorize_automation_decision(context)["decision_kind"],
                "acknowledgement",
            )
            self.principal("second-human")
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.authorize_automation_decision(context)

    def test_mutation_requires_csrf_and_cancel_requires_owner(self):
        self.member("contributor")
        with (
            auth.credential_context(self.service, self.token, mutation=True),
            auth.authorized_session() as db,
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.guard_project(db, 1, capability="automation.request")
        with self.context(mutation=True), auth.authorized_session() as db:
            auth.guard_project(
                db, 1, capability="automation.cancel", owner_id="human-a"
            )
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_project(
                    db, 1, capability="automation.cancel", owner_id="other"
                )

    def test_verified_and_unknown_profiles_cannot_enable_legacy(self):
        for profile in ("verified", "invalid"):
            with (
                patch.object(
                    config.settings, "authorization_profile", profile, create=True
                ),
                auth.authorized_session(self.factory) as db,
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                auth.guard_report(db, 3)

    def test_project_metadata_visible_but_projectwide_action_denied_for_workspace_member(
        self,
    ):
        self.member("admin", workspace=1)
        with self.context(mutation=True), auth.authorized_session() as db:
            ids = list(
                db.scalars(
                    select(Project.id)
                    .where(auth.visible_project_predicate(db))
                    .order_by(Project.id)
                )
            )
            self.assertEqual(ids, [1, 3])
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_project(db, 1, capability="settings.manage")

    def test_live_version_and_revocation_ignore_preexisting_credential_context(self):
        self.member()
        with self.context():
            with self.factory.begin() as db:
                auth.membership_repository.revoke_membership(
                    db, principal_id="human-a", project_id=1
                )
            with (
                auth.authorized_session() as db,
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                auth.guard_report(db, 1)
        self.member()
        with self.context(), auth.authorized_session() as db:
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_project(db, 1, expected_version=1)
            self.assertEqual(auth.guard_project(db, 1).authorization_version, 3)

    def test_operation_reservation_serializes_membership_revocation(self):
        self.member()
        attempting = threading.Event()
        completed = threading.Event()

        def revoke():
            attempting.set()
            with auth.authorized_session(self.factory) as db:
                auth.membership_repository.revoke_membership(
                    db, principal_id="human-a", project_id=1
                )
            completed.set()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with self.context(), auth.authorized_session() as db:
                self.assertEqual(auth.guard_report(db, 1).id, 1)
                future = executor.submit(revoke)
                self.assertTrue(attempting.wait(timeout=2))
                self.assertFalse(completed.wait(timeout=0.1))
                self.assertEqual(auth.guard_report(db, 1).id, 1)
            future.result(timeout=5)
        with (
            self.context(),
            auth.authorized_session() as db,
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.guard_report(db, 1)

    def test_global_administrator_cannot_manage_existing_project_without_membership(
        self,
    ):
        self.principal("human-b")
        self.member(principal="human-b")
        with (
            self.context(mutation=True),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.assign_project_membership(1, "human-a", "admin")
        with (
            self.context(mutation=True),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.bootstrap_project_membership(1)

    def test_revoked_last_membership_cannot_reopen_bootstrap(self):
        self.member()
        with self.context(mutation=True):
            auth.revoke_project_membership(1, "human-a")
        self.token, self.csrf = self.principal("human-a")
        with (
            self.context(mutation=True),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.bootstrap_project_membership(1)

    def test_assignment_rejects_cross_project_workspace_and_unknown_role_atomically(
        self,
    ):
        self.member()
        self.principal("human-b")
        for role, workspace in (("admin", 3), ("forged-admin", 1)):
            with (
                self.context(mutation=True),
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                auth.assign_project_membership(
                    1, "human-b", role, workspace_id=workspace
                )
        with self.factory() as db:
            self.assertIsNone(
                auth.membership_repository.get_membership(
                    db, principal_id="human-b", project_id=1
                )
            )
            self.assertEqual(list(db.scalars(select(ProjectAuthorizationAudit))), [])

    def test_synthetic_verified_machine_policy_intersects_role_and_audience(self):
        principal = self.service.resolve_session(self.token)
        for kind in ("service", "agent", "runner"):
            for role in auth.PROJECT_ROLE_CAPABILITIES:
                machine = principal.model_copy(
                    update={
                        "principal_type": kind,
                        "credential_audience": "service-request-v1",
                    }
                )
                for action in (
                    "read",
                    "request",
                    "draft",
                    "publish",
                    "decision",
                    "cancel",
                    "admin",
                ):
                    capability = f"automation.{action}"
                    expected = (
                        kind in {"service", "agent"}
                        and action in {"read", "request"}
                        and capability in auth.PROJECT_ROLE_CAPABILITIES[role]
                    )
                    with self.subTest(kind=kind, role=role, capability=capability):
                        self.assertEqual(
                            auth.trusted_capability_allowed(machine, role, capability),
                            expected,
                        )
                self.assertFalse(
                    auth.trusted_capability_allowed(
                        machine.model_copy(update={"credential_audience": "human"}),
                        role,
                        "automation.read",
                    )
                )

    def test_internal_commit_cannot_silently_continue_using_authority(self):
        self.member()
        with (
            self.context(),
            self.assertRaises(auth.TrustedAuthorizationError),
            auth.authorized_session() as db,
        ):
            auth.guard_report(db, 1)
            db.commit()
            db.get(Project, 1)
            auth.guard_report(db, 1)

    def test_transport_is_lazy_for_legacy_and_required_for_protected_access(self):
        def deny():
            raise auth.TrustedAuthorizationError()

        self.member()
        with (
            auth.credential_context(self.service, self.token, transport_check=deny),
            auth.authorized_session() as db,
        ):
            self.assertIsNone(auth.guard_project(db, 3))
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_report(db, 1)
            self.assertEqual(
                list(
                    db.scalars(
                        select(AnalysisReport.id).where(
                            auth.visible_report_predicate(db)
                        )
                    )
                ),
                [3],
            )

    def test_read_capability_cannot_mutate_without_explicit_mutation_credentials(self):
        self.member("reviewer")
        with self.context(), auth.authorized_session() as db:
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_report(db, 1, "report.review", mutation=True)
        with self.context(mutation=True), auth.authorized_session() as db:
            self.assertEqual(
                auth.guard_report(db, 1, "report.review", mutation=True).id, 1
            )

    def test_context_reset_prevents_leaking_authority_to_following_call(self):
        self.member()
        with self.context(), auth.authorized_session() as db:
            self.assertTrue(auth.legacy_request_has_identity())
            auth.guard_report(db, 1)
        self.assertFalse(auth.legacy_request_has_identity())
        with (
            auth.authorized_session(self.factory) as db,
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.guard_report(db, 1)

    def test_read_only_and_contributor_cannot_decide_or_create_audit(self):
        self.principal("human-b")
        context = auth.DecisionContext(
            project_id=1,
            workspace_id=1,
            report_id=1,
            requester_principal_id="human-b",
            object_id="seeded-context",
        )
        for role in ("read-only", "contributor"):
            self.member(role)
            with (
                self.context(mutation=True),
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                auth.authorize_automation_decision(context)
        with self.factory() as db:
            self.assertEqual(list(db.scalars(select(ProjectAuthorizationAudit))), [])

    def test_decision_context_must_match_report_and_server_mode(self):
        self.member()
        self.principal("human-b")
        context = auth.DecisionContext(
            project_id=1,
            workspace_id=1,
            report_id=2,
            requester_principal_id="human-b",
            object_id="seeded-context",
        )
        with (
            self.context(mutation=True),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.authorize_automation_decision(context)
        context = auth.DecisionContext(
            project_id=1,
            workspace_id=1,
            report_id=1,
            requester_principal_id="human-b",
            object_id="seeded-context",
        )
        with (
            patch.object(config.settings, "identity_decision_mode", "forged"),
            self.context(mutation=True),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            auth.authorize_automation_decision(context)
