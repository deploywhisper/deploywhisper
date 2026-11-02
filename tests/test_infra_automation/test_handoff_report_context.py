"""Private receiver report reads cannot become general human authority."""

from __future__ import annotations

from unittest.mock import Mock

from infra_automation.handoff_context import _bind_receiver_report
from models.tables import AnalysisReport
from services import project_service as auth
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class ReceiverReportContextTests(LifecycleCase):
    def setUp(self):
        super().setUp()
        with self.factory.begin() as session:
            session.add(
                AnalysisReport(
                    id=1,
                    project_id=100,
                    workspace_id=100,
                    risk_score=0,
                    severity="low",
                    recommendation="go",
                    top_risk="synthetic",
                    parse_summary="synthetic",
                    narrative_opening="synthetic",
                    narrative_explanation="synthetic",
                )
            )

    def test_reader_is_transaction_bound_read_only_and_never_a_principal(self):
        with auth.authorized_session(session_factory=self.factory) as session:
            reader = Mock(
                side_effect=lambda db, report_id: db.get(AnalysisReport, report_id)
            )
            with _bind_receiver_report(session, reader):
                self.assertEqual(auth.guard_report(session, 1).id, 1)
                with self.assertRaises(auth.TrustedAuthorizationError):
                    auth.guard_report(session, 1, mutation=True)
                with self.assertRaises(auth.TrustedAuthorizationError):
                    auth.guard_report(session, 1, "report.review")
                with self.assertRaises(auth.TrustedAuthorizationError):
                    auth.guard_project(
                        session, 100, 100, "automation.decision", mutation=True
                    )
                with (
                    self.factory() as other,
                    self.assertRaises(auth.TrustedAuthorizationError),
                ):
                    auth.guard_report(other, 1)
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_report(session, 1)

    def test_each_read_rechecks_the_callback_and_cannot_return_another_report(self):
        with auth.authorized_session(session_factory=self.factory) as session:

            def denied(db, report_id):
                raise auth.TrustedAuthorizationError()

            with (
                _bind_receiver_report(session, denied),
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                auth.guard_report(session, 1)
            wrong = AnalysisReport(id=2, project_id=100, workspace_id=100)
            with (
                _bind_receiver_report(session, lambda db, report_id: wrong),
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                auth.guard_report(session, 1)
