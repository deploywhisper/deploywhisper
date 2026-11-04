"""Independent runner administration role, scope and principal matrix."""

from __future__ import annotations

from contextlib import nullcontext
import unittest

from infra_automation.lifecycle import (
    AutomationSettings,
    UpdateSettingsRequest,
    LifecycleError,
)
from services import infra_automation_policy as policy
from services import infra_automation_runners as runners
from services import project_service as auth
from services.identity_service import IdentityError
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class RunnerAuthorizationMatrixTests(unittest.TestCase):
    def fixture(self):
        case = LifecycleCase(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        with case.credentials():
            policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=0,
                    settings=AutomationSettings(enabled=True),
                    reason="Enable matrix fixture.",
                )
            )
        return case

    def request(self, project=100, workspace=100):
        return runners.EnrollmentRequest(
            project_id=project,
            workspace_id=workspace,
            tags=["linux"],
            tool="opentofu",
            profile_digest="sha256:" + "a" * 64,
            runner_version="1.0",
            reason="Matrix fixture enrollment.",
        )

    def test_every_human_role_and_scope_for_administration_and_health(self):
        for role in ("admin", "maintainer", "reviewer", "contributor", "read-only"):
            for project, workspace in ((100, 100), (100, 101), (200, 200)):
                case = self.fixture()
                case.principal("matrix-human")
                case.member(role, principal="matrix-human", workspace=100)
                with case.credentials():
                    issued = runners.create_enrollment(self.request(), now=case.now)
                runners.redeem(
                    issued.enrollment.enrollment_id,
                    issued.token.get_secret_value(),
                    now=case.now,
                )
                scope_matches = (project, workspace) == (100, 100)
                operations = {
                    "enroll": lambda: runners.create_enrollment(
                        self.request(project, workspace), now=case.now
                    ),
                    "health": lambda: runners.health(project, workspace),
                }
                for operation, invoke in operations.items():
                    permitted = scope_matches and (
                        role in ("admin", "maintainer")
                        if operation == "health"
                        else role == "admin"
                    )
                    expected = (
                        nullcontext()
                        if permitted
                        else self.assertRaises(
                            (auth.TrustedAuthorizationError, LifecycleError)
                        )
                    )
                    with self.subTest(
                        role=role, scope=(project, workspace), operation=operation
                    ):
                        with case.credentials("matrix-human"), expected:
                            invoke()
                # Object mutations derive scope from the retained runner, never a
                # caller-supplied project. Change the actor's membership to exercise
                # same project/wrong workspace and cross-project object access.
                with case.factory.begin() as db:
                    from models.tables import ProjectMembership
                    from sqlalchemy import delete

                    db.execute(
                        delete(ProjectMembership).where(
                            ProjectMembership.principal_id == "matrix-human"
                        )
                    )
                case.member(
                    role, principal="matrix-human", project=project, workspace=workspace
                )
                for operation in ("rotate", "revoke"):
                    permitted = scope_matches and role == "admin"
                    expected = (
                        nullcontext()
                        if permitted
                        else self.assertRaises(
                            (auth.TrustedAuthorizationError, LifecycleError)
                        )
                    )
                    with self.subTest(
                        role=role, scope=(project, workspace), operation=operation
                    ):
                        with case.credentials("matrix-human"), expected:
                            getattr(runners, operation)(
                                issued.enrollment.runner_id,
                                reason="Matrix fixture operation.",
                                now=case.now,
                            )
                case.doCleanups()

    def test_nonhuman_sessions_never_grant_runner_administration(self):
        for principal_type in ("service", "agent", "runner", "receiver"):
            for role in ("admin", "maintainer", "reviewer", "contributor", "read-only"):
                for project, workspace in ((100, 100), (100, 101), (200, 200)):
                    case = self.fixture()
                    with case.credentials():
                        issued = runners.create_enrollment(self.request(), now=case.now)
                    runners.redeem(
                        issued.enrollment.enrollment_id,
                        issued.token.get_secret_value(),
                        now=case.now,
                    )
                    case.principal(
                        "machine", principal_type=principal_type, audience="human"
                    )
                    case.member(
                        role, principal="machine", project=project, workspace=workspace
                    )
                    operations = {
                        "enroll": lambda: runners.create_enrollment(
                            self.request(), now=case.now
                        ),
                        "health": lambda: runners.health(100, 100),
                        "rotate": lambda: runners.rotate(
                            issued.enrollment.runner_id,
                            reason="Matrix fixture.",
                            now=case.now,
                        ),
                        "revoke": lambda: runners.revoke(
                            issued.enrollment.runner_id,
                            reason="Matrix fixture.",
                            now=case.now,
                        ),
                    }
                    for operation, invoke in operations.items():
                        with self.subTest(
                            principal_type=principal_type,
                            role=role,
                            scope=(project, workspace),
                            operation=operation,
                        ):
                            with (
                                case.credentials("machine"),
                                self.assertRaises(
                                    (
                                        auth.TrustedAuthorizationError,
                                        LifecycleError,
                                        IdentityError,
                                    )
                                ),
                            ):
                                invoke()
                    case.doCleanups()
