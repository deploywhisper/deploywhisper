"""Report surfaces enforce live scope before reads, aggregation and filesystem I/O."""

from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from tests.test_services import test_project_authorization as auth_tests
from services import (
    report_service as reports,
    stats_service as stats,
    artifact_snapshot_service as artifacts,
)
from services import project_service as auth
from models.tables import AnalysisReport


class ReportAuthorizationTests(unittest.TestCase):
    principal = auth_tests.ProjectAuthorizationTests.principal
    member = auth_tests.ProjectAuthorizationTests.member
    context = auth_tests.ProjectAuthorizationTests.context
    tearDown = auth_tests.ProjectAuthorizationTests.tearDown

    def setUp(self):
        auth_tests.ProjectAuthorizationTests.setUp(self)
        self.patches = ExitStack()
        for module in (reports, stats, artifacts, auth):
            self.patches.enter_context(
                patch.object(module, "SessionLocal", self.factory, create=True)
            )
        self.patches.enter_context(
            patch.object(
                artifacts,
                "settings",
                SimpleNamespace(
                    artifact_snapshot_dir=str(Path(self.temp.name) / "artifacts")
                ),
            )
        )
        self.addCleanup(self.patches.close)

    def _persist_report(self, *, snapshots=True, project_id=1, **kwargs):
        from tests.test_services.test_report_service import ReportServiceTests

        return reports.persist_analysis_report(
            *ReportServiceTests()._content_boundary_models(),
            project_id=project_id,
            workspace_id=1 if project_id == 1 else None,
            artifact_snapshots={
                "playbook.yaml": b"- hosts: all\n  tasks:\n    - debug:\n        msg: private original\n"
            }
            if snapshots
            else None,
            **kwargs,
        )

    def test_commit_failure_removes_snapshots_before_releasing_reservation(self):
        self.member("contributor", workspace=1)
        original_cleanup = reports._cleanup_partial_report
        cleanup_states = []

        def cleanup(report_id):
            session = auth._operation_session.get()
            cleanup_states.append(session.connection().connection.in_transaction)
            original_cleanup(report_id)

        with self.context(mutation=True):
            # The explicit outer operation makes the failure happen after the
            # nested persistence service has returned its materialized report.
            with (
                patch.object(reports, "_cleanup_partial_report", side_effect=cleanup),
                self.assertRaises(OperationalError),
                patch.object(
                    Session,
                    "commit",
                    side_effect=OperationalError("COMMIT", {}, Exception("disk full")),
                ),
                auth.authorized_session(self.factory),
            ):
                self.assertEqual(self._persist_report()["id"], 4)
        self.assertEqual(cleanup_states, [True])
        self.assertFalse(
            (Path(artifacts.settings.artifact_snapshot_dir) / "4").exists()
        )
        with self.factory() as db:
            self.assertIsNone(db.get(AnalysisReport, 4))
        with self.context(mutation=True):
            replacement = self._persist_report(snapshots=False)
            self.assertEqual(replacement["id"], 4)
            self.assertIsNone(artifacts.load_report_artifact(4, "playbook.yaml"))

    def test_enclosing_operation_rollback_removes_snapshots(self):
        self.member("contributor", workspace=1)
        with self.context(mutation=True):
            with self.assertRaisesRegex(ValueError, "later operation failed"):
                with auth.authorized_session(self.factory):
                    self.assertEqual(self._persist_report()["id"], 4)
                    raise ValueError("later operation failed")
        self.assertFalse(
            (Path(artifacts.settings.artifact_snapshot_dir) / "4").exists()
        )
        with self.factory() as db:
            self.assertIsNone(db.get(AnalysisReport, 4))

    def test_successful_persistence_retains_snapshots_and_verified_actor(self):
        self.member("contributor", workspace=1)
        with self.context(mutation=True):
            report = self._persist_report(audit_context={"actor": "forged actor"})
            self.assertEqual(report["audit"]["actor"], "human-a")
            self.assertEqual(
                report["submission_manifest"]["provenance"]["actor"], "human-a"
            )
            self.assertEqual(
                reports.fetch_analysis_report(4)["audit"]["actor"], "human-a"
            )
            self.assertIn(
                "private original",
                artifacts.load_report_artifact(4, "playbook.yaml").content,
            )

    def test_unprotected_legacy_persistence_retains_caller_actor(self):
        report = self._persist_report(
            project_id=3, audit_context={"actor": "legacy actor"}
        )
        self.assertEqual(report["audit"]["actor"], "legacy actor")

    def test_reused_report_id_cannot_attach_orphaned_snapshots(self):
        root = Path(artifacts.settings.artifact_snapshot_dir) / "4"
        root.mkdir(parents=True)
        (root / "manifest.json").write_text('{"old.txt": "old.txt"}')
        (root / "old.txt").write_text("private orphan from rolled back report")
        self.member("contributor", workspace=1)
        with self.context(mutation=True):
            self.assertEqual(self._persist_report(snapshots=False)["id"], 4)
            self.assertIsNone(artifacts.load_report_artifact(4, "old.txt"))
        self.assertFalse(root.exists())

    def test_cleanup_never_deletes_replacement_after_sqlite_loses_reservation(self):
        self.member("contributor", workspace=1)
        root = Path(artifacts.settings.artifact_snapshot_dir) / "4"
        with self.context(mutation=True):
            with self.assertRaisesRegex(ValueError, "transaction already rolled back"):
                with auth.authorized_session(self.factory) as session:
                    self._persist_report()
                    # SQLite can itself roll back on storage failures. A later
                    # writer may already have reused the ID before unwinding.
                    session.connection().connection.driver_connection.rollback()
                    with self.factory.begin() as replacement:
                        replacement.add(
                            AnalysisReport(
                                id=4,
                                project_id=1,
                                workspace_id=1,
                                risk_score=0,
                                severity="low",
                                recommendation="go",
                                top_risk="replacement",
                                parse_summary="replacement",
                                narrative_opening="replacement",
                                narrative_explanation="replacement",
                            )
                        )
                    (root / "replacement.txt").write_text("new writer's artifact")
                    raise ValueError("transaction already rolled back")
        self.assertEqual(
            (root / "replacement.txt").read_text(), "new writer's artifact"
        )

    def test_single_and_share_reads_deny_without_membership(self):
        for read in (
            lambda: reports.fetch_analysis_report(1),
            lambda: reports.fetch_analysis_report_for_project_keys(
                1, project_keys=["project-1"]
            ),
            lambda: reports.fetch_shared_analysis_report(1, bypass_password=True),
            lambda: reports.fetch_report_comparison(3, previous_report_id=1),
        ):
            with (
                self.subTest(read=read),
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                read()

    def test_lists_counts_stats_and_toolchains_filter_before_paging(self):
        with self.factory.begin() as db:
            db.get(AnalysisReport, 1).contributors_json = '[{"tool":"private-tool"}]'
        page = reports.fetch_filtered_analysis_history_page(page_size=1)
        self.assertEqual([r["id"] for r in page["items"]], [3])
        self.assertEqual(page["total_count"], 1)
        self.assertEqual(stats.fetch_stats_summary()["total_analyses"], 1)
        self.assertEqual(stats.fetch_verdict_distribution()["total"], 1)
        self.assertNotIn("private-tool", reports.fetch_history_toolchains())
        self.assertEqual(reports.fetch_dashboard_briefing()["saved_briefings"], 1)
        self.assertEqual(reports.fetch_risk_trends(project_id=3)["total_reports"], 1)

    def test_member_scope_and_revocation_are_live(self):
        self.member("read-only", workspace=1)
        with self.context():
            self.assertEqual(reports.fetch_analysis_report(1)["id"], 1)
            self.assertEqual(
                reports.fetch_filtered_analysis_history_page()["total_count"], 2
            )
            with self.factory.begin() as db:
                auth.membership_repository.revoke_membership(
                    db, principal_id="human-a", project_id=1
                )
            with self.assertRaises(auth.TrustedAuthorizationError):
                reports.fetch_analysis_report(1)

    def test_batch_delete_authorizes_every_report_before_deleting_any(self):
        with self.assertRaises(auth.TrustedAuthorizationError):
            reports.remove_analysis_reports([3, 1])
        with self.factory() as db:
            self.assertIsNotNone(db.get(AnalysisReport, 3))

    def test_mutations_require_role_and_csrf(self):
        for role, mutation in (("read-only", True), ("reviewer", False)):
            self.member(role)
            with self.context(mutation=mutation):
                for action in (
                    lambda: reports.remove_analysis_report(1),
                    lambda: reports.configure_report_share(
                        1, password=None, redact_filenames=False
                    ),
                    lambda: artifacts.save_report_artifacts(1, {"a.txt": b"safe"}),
                    lambda: artifacts.delete_report_artifacts(1),
                ):
                    with (
                        self.subTest(role=role, mutation=mutation),
                        self.assertRaises(auth.TrustedAuthorizationError),
                    ):
                        action()

    def test_artifacts_require_live_metadata_even_when_files_exist(self):
        root = Path(artifacts.settings.artifact_snapshot_dir) / "99"
        root.mkdir(parents=True)
        (root / "manifest.json").write_text('{"a.txt":"a.txt"}')
        (root / "a.txt").write_text("sensitive test content")
        for action in (
            lambda: artifacts.load_report_artifact(99, "a.txt"),
            lambda: artifacts.delete_report_artifacts(99),
            lambda: artifacts.save_report_artifacts(99, {"a.txt": b"replacement"}),
        ):
            with self.assertRaises(auth.TrustedAuthorizationError):
                action()
        self.assertTrue((root / "a.txt").exists())

    def test_report_marker_protects_project_siblings_and_artifacts(self):
        with self.factory.begin() as db:
            db.get(AnalysisReport, 3).authorization_required = True
        with self.assertRaises(auth.TrustedAuthorizationError):
            artifacts.load_report_artifact(3, "anything.txt")
        self.assertEqual(
            reports.fetch_filtered_analysis_history_page()["total_count"], 0
        )

    def test_report_materialization_holds_authority_until_response_ready(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading

        self.member("read-only", workspace=1)
        materializing = threading.Event()
        release = threading.Event()
        revoking = threading.Event()
        revoked = threading.Event()
        original = reports._serialize_report

        def serialize(report, **kwargs):
            materializing.set()
            self.assertTrue(release.wait(5))
            return original(report, **kwargs)

        def read():
            with self.context():
                return reports.fetch_analysis_report(1)

        def revoke():
            revoking.set()
            with auth.authorized_session(self.factory) as db:
                auth.membership_repository.revoke_membership(
                    db, principal_id="human-a", project_id=1
                )
            revoked.set()

        with (
            ThreadPoolExecutor(max_workers=2) as executor,
            patch.object(reports, "_serialize_report", side_effect=serialize),
        ):
            result = executor.submit(read)
            self.assertTrue(materializing.wait(5))
            revocation = executor.submit(revoke)
            self.assertTrue(revoking.wait(5))
            try:
                self.assertFalse(revoked.wait(0.1))
            finally:
                release.set()
            self.assertEqual(result.result(timeout=5)["id"], 1)
            revocation.result(timeout=5)
        with self.context(), self.assertRaises(auth.TrustedAuthorizationError):
            reports.fetch_analysis_report(1)

    def test_snapshot_read_save_delete_follow_live_membership(self):
        self.member("admin", workspace=1)
        with self.context(mutation=True):
            artifacts.save_report_artifacts(1, {"safe.txt": b"safe synthetic artifact"})
        with self.context():
            self.assertEqual(
                artifacts.load_report_artifact(1, "safe.txt").content,
                "safe synthetic artifact",
            )
        with self.assertRaises(auth.TrustedAuthorizationError):
            artifacts.load_report_artifact(1, "safe.txt")
        with self.context(mutation=True):
            artifacts.delete_report_artifacts(1)
            self.assertIsNone(artifacts.load_report_artifact(1, "safe.txt"))

    def test_comparison_cannot_cross_restricted_workspace(self):
        self.member("read-only", workspace=1)
        with self.factory.begin() as db:
            db.add(
                AnalysisReport(
                    id=4,
                    project_id=1,
                    workspace_id=2,
                    risk_score=0,
                    severity="low",
                    recommendation="go",
                    top_risk="synthetic",
                    parse_summary="synthetic",
                    narrative_opening="synthetic",
                    narrative_explanation="synthetic",
                )
            )
        with self.context(), self.assertRaises(auth.TrustedAuthorizationError):
            reports.fetch_report_comparison(1, previous_report_id=4)
        with self.context():
            ids = [
                r["id"] for r in reports.fetch_filtered_analysis_history_page()["items"]
            ]
            self.assertEqual(ids, [3, 1])

    def test_reviewer_can_delete_scoped_report_with_csrf(self):
        self.member("admin", workspace=1)
        with self.context(mutation=True):
            artifacts.save_report_artifacts(1, {"safe.txt": b"safe synthetic artifact"})
        self.member("reviewer", workspace=1)
        with self.context(mutation=True):
            self.assertTrue(reports.remove_analysis_report(1))
        with self.factory() as db:
            self.assertIsNone(db.get(AnalysisReport, 1))
        self.assertFalse(
            (Path(artifacts.settings.artifact_snapshot_dir) / "1").exists()
        )

    def _seed_deletion_snapshot(self):
        self.member("admin", workspace=1)
        with self.context(mutation=True):
            artifacts.save_report_artifacts(1, {"safe.txt": b"retained original"})
        self.member("reviewer", workspace=1)

    def _assert_deletion_rolled_back(self):
        with self.factory() as db:
            self.assertIsNotNone(db.get(AnalysisReport, 1))
        with self.context():
            snapshot = artifacts.load_report_artifact(1, "safe.txt")
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot.content, "retained original")

    def test_deletion_commit_failure_retains_row_and_snapshot(self):
        self._seed_deletion_snapshot()
        with self.context(mutation=True):
            with (
                self.assertRaises(OperationalError),
                patch.object(
                    Session,
                    "commit",
                    side_effect=OperationalError("COMMIT", {}, Exception("disk full")),
                ),
            ):
                reports.remove_analysis_report(1)
        self._assert_deletion_rolled_back()

    def test_deletion_enclosing_rollback_retains_row_and_snapshot(self):
        self._seed_deletion_snapshot()
        with self.context(mutation=True):
            with self.assertRaisesRegex(ValueError, "later failure"):
                with auth.authorized_session(self.factory):
                    self.assertTrue(reports.remove_analysis_report(1))
                    raise ValueError("later failure")
        self._assert_deletion_rolled_back()

    def test_deletion_later_batch_failure_retains_row_and_snapshot(self):
        self._seed_deletion_snapshot()
        original_delete = reports.delete_analysis_report

        def delete(session, report_id, **kwargs):
            if report_id == 3:
                raise ValueError("later failure")
            return original_delete(session, report_id, **kwargs)

        with (
            self.context(mutation=True),
            patch.object(reports, "delete_analysis_report", side_effect=delete),
            self.assertRaisesRegex(ValueError, "later failure"),
        ):
            reports.remove_analysis_reports([1, 3])
        self._assert_deletion_rolled_back()

    def test_deletion_duplicate_ids_delete_once(self):
        self._seed_deletion_snapshot()
        with (
            self.context(mutation=True),
            patch.object(
                reports,
                "_delete_report_artifacts_after_authorization",
                wraps=reports._delete_report_artifacts_after_authorization,
            ) as cleanup,
        ):
            self.assertEqual(reports.remove_analysis_reports([1, 1]), 1)
        cleanup.assert_called_once_with(1)
        with self.factory() as db:
            self.assertIsNone(db.get(AnalysisReport, 1))
        self.assertFalse(
            (Path(artifacts.settings.artifact_snapshot_dir) / "1").exists()
        )

    def test_deletion_does_not_erase_replacement_before_deferred_cleanup(self):
        self._seed_deletion_snapshot()
        original_commit = Session.commit
        replaced = False
        root = Path(artifacts.settings.artifact_snapshot_dir) / "1"

        def commit(session):
            nonlocal replaced
            original_commit(session)
            if not replaced:
                replaced = True
                with self.factory.begin() as db:
                    db.add(
                        AnalysisReport(
                            id=1,
                            project_id=1,
                            workspace_id=1,
                            risk_score=0,
                            severity="low",
                            recommendation="go",
                            top_risk="replacement",
                            parse_summary="replacement",
                            narrative_opening="replacement",
                            narrative_explanation="replacement",
                        )
                    )
                root.mkdir(parents=True, exist_ok=True)
                (root / "replacement.txt").write_text("replacement artifact")

        with self.context(mutation=True), patch.object(Session, "commit", commit):
            self.assertTrue(reports.remove_analysis_report(1))
        self.assertEqual((root / "replacement.txt").read_text(), "replacement artifact")

    def test_deletion_cleanup_failure_leaves_committed_row_absent(self):
        self._seed_deletion_snapshot()
        with (
            self.context(mutation=True),
            patch.object(
                reports,
                "_delete_report_artifacts_after_authorization",
                side_effect=OSError("filesystem unavailable"),
            ),
        ):
            self.assertTrue(reports.remove_analysis_report(1))
        with self.factory() as db:
            self.assertIsNone(db.get(AnalysisReport, 1))
        with self.context(), self.assertRaises(auth.TrustedAuthorizationError):
            artifacts.load_report_artifact(1, "safe.txt")

    def test_deletion_then_id_reuse_in_same_operation_preserves_original_on_rollback(
        self,
    ):
        artifacts.save_report_artifacts(3, {"safe.txt": b"retained original"})
        with self.assertRaisesRegex(RuntimeError, "committed deletion"):
            with auth.authorized_session(self.factory):
                self.assertTrue(reports.remove_analysis_report(3))
                self._persist_report(project_id=3)
        with self.factory() as db:
            self.assertIsNotNone(db.get(AnalysisReport, 3))
        self.assertEqual(
            artifacts.load_report_artifact(3, "safe.txt").content, "retained original"
        )

    def test_deletion_cleanup_uses_outer_factory_after_context_reset(self):
        self._seed_deletion_snapshot()
        original_cleanup = reports._delete_report_artifacts_after_authorization
        outer = None
        cleanup_state = []

        def cleanup(report_id):
            current = auth._operation_session.get()
            cleanup_state.append(
                (
                    current is outer,
                    current.connection().connection.in_transaction,
                    current.get_bind() is self.engine,
                )
            )
            original_cleanup(report_id)

        with self.context(mutation=True):
            with (
                patch.object(
                    reports,
                    "SessionLocal",
                    side_effect=AssertionError("wrong database"),
                ),
                patch.object(
                    reports,
                    "_delete_report_artifacts_after_authorization",
                    side_effect=cleanup,
                ) as cleaned,
                auth.authorized_session(self.factory) as outer,
            ):
                self.assertTrue(reports.remove_analysis_report(1))
                cleaned.assert_not_called()
            cleaned.assert_called_once_with(1)
        self.assertEqual(cleanup_state, [(False, True, True)])

    def test_caught_persistence_reuse_error_cannot_commit_replacement_row(self):
        artifacts.save_report_artifacts(3, {"safe.txt": b"retained original"})
        with auth.authorized_session(self.factory):
            reports.remove_analysis_report(3)
            with self.assertRaisesRegex(RuntimeError, "committed deletion"):
                self._persist_report(project_id=3)
        with self.factory() as db:
            self.assertIsNone(db.get(AnalysisReport, 3))
        self.assertFalse(
            (Path(artifacts.settings.artifact_snapshot_dir) / "3").exists()
        )

    def test_deleting_last_marked_report_keeps_project_context_protected(self):
        self.member("reviewer", project=3)
        with self.factory.begin() as db:
            db.get(AnalysisReport, 3).authorization_required = True
            db.add(
                AnalysisReport(
                    id=4,
                    project_id=3,
                    risk_score=0,
                    severity="low",
                    recommendation="go",
                    top_risk="synthetic sibling",
                    parse_summary="synthetic",
                    narrative_opening="synthetic",
                    narrative_explanation="synthetic",
                )
            )
            self.assertFalse(db.get(auth.Project, 3).authorization_required)
        with self.context(mutation=True):
            self.assertEqual(reports.remove_analysis_reports([3]), 1)
        with self.factory() as db:
            self.assertTrue(db.get(auth.Project, 3).authorization_required)
            self.assertIsNone(db.get(AnalysisReport, 3))
            self.assertIsNotNone(db.get(AnalysisReport, 4))
        with auth.authorized_session(self.factory) as db:
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_project(db, 3, capability="settings.manage", mutation=True)
        with self.assertRaises(auth.TrustedAuthorizationError):
            reports.fetch_analysis_report(4)
        self.assertEqual(
            reports.fetch_filtered_analysis_history_page()["total_count"], 0
        )

    def test_verified_profile_deletion_does_not_mark_unmarked_legacy_project(self):
        self.member("reviewer", project=3)
        with (
            patch.object(auth.config.settings, "authorization_profile", "verified"),
            self.context(mutation=True),
        ):
            self.assertTrue(reports.remove_analysis_report(3))
        with self.factory() as db:
            self.assertFalse(db.get(auth.Project, 3).authorization_required)

    def test_denied_batch_does_not_promote_or_delete_marker(self):
        self.member("reviewer", project=3)
        with self.factory.begin() as db:
            db.get(AnalysisReport, 3).authorization_required = True
        with (
            self.context(mutation=True),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            reports.remove_analysis_reports([3, 1])
        with self.factory() as db:
            self.assertFalse(db.get(auth.Project, 3).authorization_required)
            self.assertIsNotNone(db.get(AnalysisReport, 3))

    def test_outcome_derived_history_and_trends_require_outcome_read(self):
        from datetime import timedelta
        from models.tables import DeploymentOutcome

        with self.factory.begin() as db:
            db.get(AnalysisReport, 1).created_at = self.now - timedelta(days=4)
            db.add(
                AnalysisReport(
                    id=4,
                    project_id=1,
                    workspace_id=1,
                    risk_score=0,
                    severity="low",
                    recommendation="go",
                    top_risk="synthetic",
                    parse_summary="synthetic",
                    narrative_opening="synthetic",
                    narrative_explanation="synthetic",
                    created_at=self.now - timedelta(hours=2),
                )
            )
            db.add(
                DeploymentOutcome(
                    project_id=1,
                    workspace_id=1,
                    analysis_id=1,
                    outcome_label="failure",
                    deployed_at=self.now - timedelta(hours=1),
                )
            )
        for role in ("read-only", "contributor", "reviewer"):
            self.member(role, workspace=1)
            can_read_outcomes = role == "reviewer"
            with self.subTest(role=role), self.context():
                scope = {"project_id": 1, "workspace_id": 1}
                trends = reports.fetch_risk_trends(**scope)
                self.assertEqual(trends["total_reports"], 2)
                self.assertEqual(
                    trends["outcome_counts"].get("failure", 0), int(can_read_outcomes)
                )
                self.assertEqual(
                    trends["outcome_links"]["analysis_ids"],
                    [1] if can_read_outcomes else [],
                )
                self.assertEqual(
                    trends["false_reassurance_signals"]["deployment_count"],
                    int(can_read_outcomes),
                )
                filtered = reports.fetch_filtered_analysis_history_page(
                    **scope, outcome="failure"
                )
                self.assertEqual(filtered["total_count"], int(can_read_outcomes))
                window = reports.fetch_filtered_analysis_history_page(
                    **scope,
                    created_from=self.now - timedelta(hours=3),
                    created_to=self.now,
                    page_size=1,
                )
                self.assertEqual(window["total_count"], 2 if can_read_outcomes else 1)
                self.assertEqual(
                    [item["id"] for item in window["items"]],
                    [1] if can_read_outcomes else [4],
                )

                broad_window = reports.fetch_filtered_analysis_history_page(
                    **scope,
                    created_from=self.now - timedelta(days=5),
                    created_to=self.now,
                    page_size=1,
                )
                self.assertEqual(broad_window["total_count"], 2)
                self.assertEqual(
                    [item["id"] for item in broad_window["items"]],
                    [1] if can_read_outcomes else [4],
                )

    def test_outcome_filter_preserves_visible_legacy_rows_in_mixed_scope(self):
        from models.tables import DeploymentOutcome

        self.member("read-only", workspace=1)
        with self.factory.begin() as db:
            for report_id, workspace_id in ((1, 1), (3, None)):
                db.add(
                    DeploymentOutcome(
                        project_id=report_id,
                        workspace_id=workspace_id,
                        analysis_id=report_id,
                        outcome_label="failure",
                        deployed_at=self.now,
                    )
                )
        with self.context():
            history = reports.fetch_filtered_analysis_history_page(
                outcome="failure", page_size=1
            )
            self.assertEqual(history["total_count"], 1)
            self.assertEqual([item["id"] for item in history["items"]], [3])
            self.assertEqual(
                reports.fetch_risk_trends(project_id=3)["outcome_counts"],
                {"failure": 1},
            )
