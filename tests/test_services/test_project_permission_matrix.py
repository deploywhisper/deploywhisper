"""Independent Story 16.2 acceptance matrix for live scope and typed policy."""

from collections import Counter
from itertools import product
import unittest

from services import project_service as auth
from tests.test_services import test_project_authorization as fixtures


PRINCIPALS = ("human", "service", "agent", "runner", "receiver")
ROLES = ("admin", "maintainer", "reviewer", "contributor", "read-only")
ACTIONS = ("read", "request", "draft", "publish", "cancel", "decision", "admin")
# Acceptance expectations are deliberately independent of production constants.
EXPECTED_ACTIONS = {
    "admin": {"read", "request", "draft", "publish", "cancel", "decision", "admin"},
    "maintainer": {"read", "request", "draft", "cancel", "decision"},
    "reviewer": {"read", "decision"},
    "contributor": {"read", "request", "cancel"},
    "read-only": {"read"},
}


class ProjectPermissionMatrixTests(unittest.TestCase):
    # Reuse fixture helpers without collecting the source class's test methods.
    setUp = fixtures.ProjectAuthorizationTests.setUp
    tearDown = fixtures.ProjectAuthorizationTests.tearDown
    principal = fixtures.ProjectAuthorizationTests.principal
    member = fixtures.ProjectAuthorizationTests.member
    context = fixtures.ProjectAuthorizationTests.context

    def test_complete_live_principal_role_project_workspace_action_matrix(self):
        outcomes = Counter()
        for principal_type in PRINCIPALS:
            name = f"matrix-{principal_type}"
            token, csrf = self.principal(name, principal_type=principal_type)
            for role in ROLES:
                membership = self.member(role, principal=name, workspace=1)
                for project_id, workspace_index, action in product(
                    (1, 2), (0, 1), ACTIONS
                ):
                    workspace_id = 2 * (project_id - 1) + workspace_index + 1
                    expected = (
                        principal_type == "human"
                        and project_id == 1
                        and workspace_id == 1
                        and action in EXPECTED_ACTIONS[role]
                    )
                    with (
                        self.subTest(
                            principal=principal_type,
                            role=role,
                            project=project_id,
                            workspace=workspace_id,
                            action=action,
                        ),
                        self.context(token=token, csrf=csrf, mutation=action != "read"),
                        auth.authorized_session() as db,
                    ):
                        if expected:
                            scope = auth.guard_project(
                                db,
                                project_id,
                                workspace_id,
                                f"automation.{action}",
                                owner_id=name,
                            )
                            self.assertEqual(scope.principal.principal_id, name)
                            self.assertEqual(scope.role, role)
                            self.assertEqual(
                                scope.authorization_version,
                                membership.authorization_version,
                            )
                            outcomes["allowed"] += 1
                        else:
                            with self.assertRaises(
                                auth.TrustedAuthorizationError
                            ) as exc:
                                auth.guard_project(
                                    db,
                                    project_id,
                                    workspace_id,
                                    f"automation.{action}",
                                    owner_id=name,
                                )
                            self.assertEqual(
                                str(exc.exception), "Operation unavailable."
                            )
                            outcomes["denied"] += 1
        self.assertEqual(sum(outcomes.values()), 5 * 5 * 2 * 2 * 7)
        self.assertEqual(outcomes, {"allowed": 18, "denied": 682})

    def test_complete_typed_policy_matrix_does_not_imply_machine_session_support(self):
        human = self.service.resolve_session(self.token)
        outcomes = Counter()
        for principal_type, role, action in product(PRINCIPALS, ROLES, ACTIONS):
            principal = human.model_copy(
                update={
                    "principal_type": principal_type,
                    "credential_audience": "human"
                    if principal_type == "human"
                    else "service-request-v1",
                }
            )
            expected = action in EXPECTED_ACTIONS[role] and (
                principal_type == "human"
                or (
                    principal_type in {"service", "agent"}
                    and action in {"read", "request"}
                )
            )
            with self.subTest(principal=principal_type, role=role, action=action):
                actual = auth.trusted_capability_allowed(
                    principal, role, f"automation.{action}"
                )
                self.assertEqual(actual, expected)
                outcomes["allowed" if actual else "denied"] += 1
        self.assertEqual(sum(outcomes.values()), 5 * 5 * 7)
        self.assertEqual(outcomes, {"allowed": 34, "denied": 141})

    def test_every_policy_cell_rejects_wrong_audience_or_disabled_principal(self):
        human = self.service.resolve_session(self.token)
        denied = Counter()
        for principal_type, role, action in product(PRINCIPALS, ROLES, ACTIONS):
            correct_audience = (
                "human" if principal_type == "human" else "service-request-v1"
            )
            wrong_audience = (
                "service-request-v1" if principal_type == "human" else "human"
            )
            for condition, audience, enabled in (
                ("wrong-audience", wrong_audience, True),
                ("unknown-audience", "unknown", True),
                ("disabled", correct_audience, False),
            ):
                principal = human.model_copy(
                    update={
                        "principal_type": principal_type,
                        "credential_audience": audience,
                        "enabled": enabled,
                    }
                )
                with self.subTest(
                    principal=principal_type,
                    role=role,
                    action=action,
                    condition=condition,
                ):
                    self.assertFalse(
                        auth.trusted_capability_allowed(
                            principal, role, f"automation.{action}"
                        )
                    )
                    denied[condition] += 1
        self.assertEqual(
            denied,
            {"wrong-audience": 175, "unknown-audience": 175, "disabled": 175},
        )


if __name__ == "__main__":
    unittest.main()
