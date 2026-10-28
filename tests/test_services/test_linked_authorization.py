"""Protected linked context stays behind the same live membership boundary."""

from unittest.mock import patch
import unittest

from services import project_service as auth
from services import feedback_service, deployment_outcome_service, incident_service
from services import backtesting_service, topology_service, scanner_import_service
from tests.test_services import test_project_authorization as fixture


class LinkedAuthorizationTests(unittest.TestCase):
    def setUp(self):
        fixture.ProjectAuthorizationTests.setUp(self)
        for module in (
            auth,
            feedback_service,
            deployment_outcome_service,
            incident_service,
            backtesting_service,
            topology_service,
            scanner_import_service,
        ):
            patcher = patch.object(module, "SessionLocal", self.factory)
            patcher.start()
            self.addCleanup(patcher.stop)

    tearDown = fixture.ProjectAuthorizationTests.tearDown
    principal = fixture.ProjectAuthorizationTests.principal
    member = fixture.ProjectAuthorizationTests.member
    context = fixture.ProjectAuthorizationTests.context

    def test_missing_credentials_deny_linked_report_operations(self):
        for service, operation in (
            (feedback_service, lambda: feedback_service.fetch_report_feedback_state(1)),
            (
                feedback_service,
                lambda: feedback_service.record_false_negative_feedback(
                    analysis_id=1, note="private"
                ),
            ),
            (
                deployment_outcome_service,
                lambda: deployment_outcome_service.record_deployment_outcome(
                    analysis_id=1, outcome="success"
                ),
            ),
            (
                incident_service,
                lambda: incident_service.ingest_incident_document(
                    "synthetic.md", "incident", analysis_id=1
                ),
            ),
        ):
            with (
                self.subTest(service=service.__name__),
                patch.object(service, "SessionLocal", self.factory),
            ):
                with self.assertRaises(auth.TrustedAuthorizationError):
                    operation()

    def test_missing_credentials_deny_project_context_reads(self):
        for service, operation in (
            (
                feedback_service,
                lambda: feedback_service.fetch_feedback_summary(project_id=1),
            ),
            (
                deployment_outcome_service,
                lambda: deployment_outcome_service.list_deployment_outcomes(
                    project_id=1
                ),
            ),
            (
                incident_service,
                lambda: incident_service.get_incident_records(project_id=1),
            ),
            (
                backtesting_service,
                lambda: backtesting_service.fetch_calibration_dashboard_seed(
                    project_id=1
                ),
            ),
            (
                backtesting_service,
                lambda: backtesting_service.run_incident_backtest(project_id=1),
            ),
            (
                topology_service,
                lambda: topology_service.get_topology_status(project_id=1),
            ),
            (
                scanner_import_service,
                lambda: scanner_import_service.list_external_scanner_evidence(
                    project_id=1
                ),
            ),
        ):
            with (
                self.subTest(service=service.__name__),
                patch.object(service, "SessionLocal", self.factory),
                patch.object(auth, "SessionLocal", self.factory),
            ):
                with self.assertRaises(auth.TrustedAuthorizationError):
                    operation()

    def test_verified_feedback_uses_membership_role_and_audited_principal(self):
        from sqlalchemy import select
        from models.tables import FeedbackEvent, ProjectAuthorizationAudit

        self.member("reviewer", workspace=1)
        with self.context(mutation=True):
            result = feedback_service.record_false_negative_feedback(
                analysis_id=1, note="synthetic missed condition", reviewer_role="admin"
            )
            self.assertEqual(result["reviewer_role"], "reviewer")
            state = feedback_service.fetch_report_feedback_state(1)
            self.assertEqual(len(state["false_negative_notes"]), 1)
        with self.factory() as db:
            event = db.scalar(select(FeedbackEvent))
            self.assertEqual(event.reviewer_role, "reviewer")
            audit = db.scalar(select(ProjectAuthorizationAudit))
            self.assertEqual(audit.actor_principal_id, "human-a")
            self.assertEqual(audit.object_id, str(result["id"]))
            self.assertNotIn("synthetic missed condition", audit.after_json)

    def test_read_only_member_cannot_write_and_read_context_is_not_mutation(self):
        for role, mutation in (("read-only", True), ("reviewer", False)):
            self.member(role, workspace=1)
            with self.subTest(role=role), self.context(mutation=mutation):
                with self.assertRaises(auth.TrustedAuthorizationError):
                    feedback_service.record_false_negative_feedback(
                        analysis_id=1, note="synthetic"
                    )

    def test_report_marker_protects_sibling_project_context(self):
        from models.tables import AnalysisReport

        with self.factory.begin() as db:
            db.get(AnalysisReport, 3).authorization_required = True
        with self.assertRaises(auth.TrustedAuthorizationError):
            feedback_service.fetch_feedback_summary(project_id=3)
        with self.assertRaises(auth.TrustedAuthorizationError):
            scanner_import_service.list_external_scanner_evidence(project_id=3)

    def test_foreign_incident_is_denied_before_private_scope_error(self):
        from models.repositories.incident_records import create_incident_record

        with self.factory() as db:
            incident = create_incident_record(
                db,
                project_id=2,
                workspace_id=3,
                title="private",
                severity="high",
                source_file="synthetic.md",
                incident_date=None,
                content="synthetic",
                analysis_id=2,
            )
            incident_id = incident.id
        self.member("maintainer", workspace=1)
        with (
            self.context(mutation=True),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            deployment_outcome_service.record_deployment_outcome(
                analysis_id=1, outcome="failure", linked_incident_id=incident_id
            )

    def test_cached_backtest_payload_is_guarded_before_return(self):
        import json
        from models.tables import AppSetting

        with self.factory.begin() as db:
            db.add(
                AppSetting(
                    key=backtesting_service._snapshot_key(1),
                    value=json.dumps({"secret": "synthetic"}),
                )
            )
        with self.assertRaises(auth.TrustedAuthorizationError):
            backtesting_service.fetch_calibration_dashboard_seed(project_id=1)

    def test_legacy_feedback_keeps_existing_behavior(self):
        result = feedback_service.record_false_negative_feedback(
            analysis_id=3, note="synthetic", reviewer_role="legacy-reviewer"
        )
        self.assertEqual(result["reviewer_role"], "legacy-reviewer")
        self.assertEqual(
            feedback_service.fetch_feedback_summary(project_id=3)["totals"][
                "events_recorded"
            ],
            1,
        )

    def test_topology_write_and_scanner_ingestion_are_denied_without_membership(self):
        from services.scanner_import_service import ScannerImportFile
        import json

        with self.assertRaises(auth.TrustedAuthorizationError):
            topology_service.save_topology_definition('{"services": []}', project_id=1)
        with self.assertRaises(auth.TrustedAuthorizationError):
            scanner_import_service.import_sarif_file(
                ScannerImportFile(
                    source_file="synthetic.sarif",
                    content=json.dumps(
                        {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {"driver": {"name": "synthetic"}},
                                    "results": [],
                                }
                            ],
                        }
                    ),
                ),
                project_id=1,
            )

    def test_bulk_incident_import_is_guarded(self):
        from services import incident_import_service

        with patch.object(incident_import_service, "SessionLocal", self.factory):
            with self.assertRaises(auth.TrustedAuthorizationError):
                incident_import_service.import_incident_files([], project_id=1)

    def test_public_context_cannot_expose_foreign_protected_report_links(self):
        from models.tables import FeedbackEvent, IncidentRecord, DeploymentOutcome

        with self.factory.begin() as db:
            db.add(
                FeedbackEvent(
                    project_id=3, analysis_id=1, finding_id="foreign", useful=True
                )
            )
            db.add(
                IncidentRecord(
                    project_id=3,
                    analysis_id=1,
                    title="foreign",
                    severity="high",
                    source_file="synthetic.md",
                    content="synthetic",
                )
            )
            db.add(
                DeploymentOutcome(
                    project_id=3,
                    analysis_id=1,
                    outcome_label="failure",
                    deployed_at=self.now,
                )
            )
        self.assertEqual(
            feedback_service.fetch_feedback_summary(project_id=3)["totals"][
                "events_recorded"
            ],
            0,
        )
        self.assertEqual(incident_service.get_incident_records(project_id=3), [])
        self.assertEqual(
            deployment_outcome_service.list_deployment_outcomes(project_id=3), []
        )
        self.assertEqual(
            backtesting_service.run_incident_backtest(project_id=3)["summary"][
                "scenario_count"
            ],
            0,
        )

    def test_incident_management_status_retains_existing_capability(self):
        self.member("read-only", workspace=1)
        with self.context(), self.assertRaises(auth.TrustedAuthorizationError):
            incident_service.get_incident_ingestion_status(project_id=1, workspace_id=1)
        with self.context():
            self.assertEqual(
                incident_service.get_incident_index_snapshot(
                    project_id=1, workspace_id=1
                )["incident_index_size"],
                0,
            )
        self.member("maintainer", workspace=1)
        with self.context():
            self.assertEqual(
                incident_service.get_incident_ingestion_status(
                    project_id=1, workspace_id=1
                ).indexed_count,
                0,
            )

    def test_direct_cache_invalidation_requires_live_mutation_authority(self):
        with self.assertRaises(auth.TrustedAuthorizationError):
            backtesting_service.invalidate_backtesting_snapshot(project_id=1)
        self.member("read-only", workspace=1)
        with (
            self.context(mutation=True),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            backtesting_service.invalidate_backtesting_snapshot(
                project_id=1, workspace_id=1
            )

    def test_authorized_linked_writes_and_workspace_collections(self):
        self.member("maintainer", workspace=1)
        with self.context(mutation=True):
            incident = incident_service.ingest_incident_document(
                "synthetic.md", "Synthetic incident", analysis_id=1
            )
            outcome = deployment_outcome_service.record_deployment_outcome(
                analysis_id=1, outcome="failure", linked_incident_id=incident["id"]
            )
            feedback_service.record_false_negative_feedback(
                analysis_id=1, note="synthetic"
            )
            self.assertEqual(
                feedback_service.fetch_feedback_summary(project_id=1, workspace_id=1)[
                    "totals"
                ]["events_recorded"],
                1,
            )
            self.assertEqual(
                deployment_outcome_service.list_deployment_outcomes(
                    project_id=1, workspace_id=1
                )[0]["id"],
                outcome["id"],
            )
            self.assertEqual(
                incident_service.get_incident_records(project_id=1, workspace_id=1)[0][
                    "id"
                ],
                incident["id"],
            )
            self.assertFalse(
                topology_service.get_topology_status(
                    project_id=1, workspace_id=1
                ).exists
            )
            self.assertEqual(
                scanner_import_service.list_external_scanner_evidence(
                    project_id=1, workspace_id=1
                ),
                [],
            )

    def test_background_jobs_skip_protected_context_even_with_bound_human(self):
        from types import SimpleNamespace

        projects = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        self.member("admin")
        with (
            self.context(mutation=True),
            patch.object(backtesting_service, "list_projects", return_value=projects),
            patch.object(backtesting_service, "run_weekly_backtest") as backtest,
        ):
            self.assertEqual(backtesting_service.run_due_weekly_backtests(), [])
            backtest.assert_not_called()
        with (
            self.context(mutation=True),
            patch.object(topology_service, "list_projects", return_value=projects),
            patch.object(topology_service, "check_topology_drift") as drift,
        ):
            self.assertEqual(topology_service.run_due_topology_drift_checks(), [])
            drift.assert_not_called()

    def test_public_outcomes_do_not_expose_private_incident_references(self):
        from models.tables import IncidentRecord, DeploymentOutcome, Project
        import json

        with self.factory.begin() as db:
            # Public timestamps may contain the private ID's digits incidentally.
            db.get(Project, 3).created_at = self.now.replace(microsecond=444000)
            db.add(
                IncidentRecord(
                    id=444,
                    project_id=2,
                    workspace_id=3,
                    analysis_id=3,
                    title="private-linked-incident",
                    severity="high",
                    source_file="private.md",
                    content="synthetic",
                )
            )
            db.add(
                DeploymentOutcome(
                    project_id=3,
                    analysis_id=3,
                    linked_incident_id=444,
                    outcome_label="failure",
                    deployed_at=self.now,
                )
            )
        listed = deployment_outcome_service.list_deployment_outcomes(project_id=3)
        self.assertIsNone(listed[0]["linked_incident_id"])
        summary = backtesting_service.run_weekly_backtest(project_id=3, now=self.now)
        self.assertIsNone(summary["backtest_rows"][0]["incident_id"])
        self.assertNotIn("private-linked-incident", json.dumps(summary))
        self.assertFalse(
            any(row.get("incident_id") == 444 for row in summary["backtest_rows"])
        )
        # Existing shared caches must re-check incident authority on every read.
        from models.tables import AppSetting

        with self.factory.begin() as db:
            snapshot = db.get(AppSetting, backtesting_service._snapshot_key(3))
            cached = json.loads(snapshot.value)
            cached["backtest_rows"][0]["incident_id"] = 444
            snapshot.value = json.dumps(cached)
        cached_result = backtesting_service.fetch_calibration_dashboard_seed(
            project_id=3, now=self.now
        )
        self.assertIsNone(cached_result["backtest_rows"][0]["incident_id"])
        # The derived report-to-incident association must enforce the incident's
        # own context too, even when its report link points at a public report.
        with self.factory.begin() as db:
            db.query(DeploymentOutcome).update({"linked_incident_id": None})
        summary = backtesting_service.run_weekly_backtest(project_id=3, now=self.now)
        self.assertIsNone(summary["backtest_rows"][0]["incident_id"])

    def test_protected_topology_reads_never_collect_or_persist_drift(self):
        from models.tables import AppSetting, TopologyVersion
        from sqlalchemy import select
        import json

        self.member("read-only", workspace=1)
        with self.factory.begin() as db:
            db.add(
                TopologyVersion(
                    project_id=1,
                    workspace_id=1,
                    source_type="terraform",
                    payload_json=json.dumps(
                        {
                            "services": [
                                {"id": "api", "label": "API", "resource_keys": ["api"]}
                            ],
                            "metadata": {
                                "import": {
                                    "source_type": "terraform",
                                    "source_ref": "/synthetic.tfstate",
                                }
                            },
                        }
                    ),
                )
            )
        with (
            self.context(mutation=False),
            patch.object(topology_service, "_lookup_source_handler") as collector,
        ):
            topology_service.get_topology_status(project_id=1, workspace_id=1)
            topology_service.check_topology_drift(project_id=1, workspace_id=1)
            collector.assert_not_called()
        with self.factory() as db:
            self.assertEqual(list(db.scalars(select(AppSetting))), [])
        cache_key = topology_service._drift_setting_key({"id": 1}, {"id": 1})
        cached = topology_service.TopologyDriftStatus(
            status="up_to_date",
            source_type="terraform",
            source_ref="/synthetic.tfstate",
            checked_at="2020-01-01T00:00:00+00:00",
        )
        with self.factory.begin() as db:
            db.add(AppSetting(key=cache_key, value=cached.model_dump_json()))
        with (
            self.context(),
            patch.object(topology_service, "_lookup_source_handler") as collector,
        ):
            returned = topology_service.check_topology_drift(
                project_id=1, workspace_id=1
            )
            self.assertEqual(returned.checked_at, cached.checked_at)
            collector.assert_not_called()
        with self.factory() as db:
            self.assertEqual(
                db.get(AppSetting, cache_key).value, cached.model_dump_json()
            )

    def test_protected_forced_drift_requires_manage_and_csrf(self):
        for role, mutation in (("read-only", True), ("maintainer", False)):
            self.member(role, workspace=1)
            with (
                self.subTest(role=role),
                self.context(mutation=mutation),
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                topology_service.check_topology_drift(
                    project_id=1, workspace_id=1, force=True
                )
        self.member("maintainer", workspace=1)
        with (
            self.context(mutation=True, csrf="invalid-csrf"),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            topology_service.check_topology_drift(
                project_id=1, workspace_id=1, force=True
            )
        with self.context(mutation=True):
            status = topology_service.check_topology_drift(
                project_id=1, workspace_id=1, force=True
            )
            self.assertEqual(status.status, "unavailable")

    def _topology_collection_race(self, operation, change):
        from concurrent.futures import ThreadPoolExecutor
        import json
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import sessionmaker
        from models.tables import AppSetting, ProjectMembership, TopologyVersion

        self.member("maintainer", workspace=1)
        payload = {
            "services": [{"id": "api", "label": "API", "resource_keys": ["api"]}],
            "metadata": {
                "import": {
                    "source_type": "terraform",
                    "source_ref": "/synthetic.tfstate",
                }
            },
        }
        with self.factory.begin() as db:
            db.add(
                TopologyVersion(
                    project_id=1,
                    workspace_id=1,
                    source_type="terraform",
                    payload_json=json.dumps(payload),
                )
            )
        other_engine = create_engine(self.engine.url, connect_args={"timeout": 0.1})
        other_factory = sessionmaker(other_engine, expire_on_commit=False)
        self.addCleanup(other_engine.dispose)

        def concurrent_operation():
            with auth.authorized_session(other_factory) as db:
                # Independent requests must acquire their own writer while collection waits.
                auth.guard_report(db, 3)
                if change == "revoke":
                    db.scalar(
                        select(ProjectMembership).where(
                            ProjectMembership.project_id == 1
                        )
                    ).enabled = False
                elif change == "source":
                    updated = {
                        **payload,
                        "metadata": {
                            "import": {
                                "source_type": "terraform",
                                "source_ref": "/new.tfstate",
                            }
                        },
                    }
                    db.add(
                        TopologyVersion(
                            project_id=1,
                            workspace_id=1,
                            source_type="terraform",
                            payload_json=json.dumps(updated),
                        )
                    )

        def collect(_reference):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(concurrent_operation).result(timeout=2)
            return topology_service.TopologyChangeSet(
                operation="replace", services=payload["services"]
            )

        with (
            self.context(mutation=True),
            patch.object(
                topology_service, "_lookup_source_handler", return_value=collect
            ),
        ):

            def run():
                if operation == "import":
                    return topology_service.import_topology_source(
                        "terraform", "/synthetic.tfstate", project_id=1, workspace_id=1
                    )
                return topology_service.check_topology_drift(
                    project_id=1, workspace_id=1, force=True
                )

            if change == "revoke":
                with self.assertRaises(auth.TrustedAuthorizationError):
                    run()
            elif change == "source":
                with self.assertRaises(topology_service.TopologyImportError):
                    run()
            else:
                run()
        with self.factory() as db:
            versions = list(db.scalars(select(TopologyVersion)))
            self.assertEqual(
                len(versions),
                2
                if change == "source" or (not change and operation == "import")
                else 1,
            )
            if change:
                self.assertEqual(list(db.scalars(select(AppSetting))), [])

    def test_topology_collectors_release_writer_for_unrelated_operation(self):
        self._topology_collection_race("import", None)

    def test_drift_collectors_release_writer_for_unrelated_operation(self):
        self._topology_collection_race("drift", None)

    def test_topology_import_rechecks_revoked_membership_after_collection(self):
        self._topology_collection_race("import", "revoke")

    def test_topology_drift_rechecks_revoked_membership_after_collection(self):
        self._topology_collection_race("drift", "revoke")

    def test_topology_import_does_not_overwrite_changed_source(self):
        self._topology_collection_race("import", "source")

    def test_topology_drift_does_not_cache_changed_source(self):
        self._topology_collection_race("drift", "source")

    def test_nested_topology_operations_never_collect_or_release_caller_transaction(
        self,
    ):
        import json
        from models.tables import AppSetting, TopologyVersion
        from sqlalchemy import select

        payload = {
            "services": [{"id": "api", "label": "API", "resource_keys": ["api"]}],
            "metadata": {
                "import": {
                    "source_type": "terraform",
                    "source_ref": "/synthetic.tfstate",
                }
            },
        }
        with self.factory.begin() as db:
            db.add(
                TopologyVersion(
                    project_id=3,
                    source_type="terraform",
                    payload_json=json.dumps(payload),
                )
            )
        with (
            auth.authorized_session(self.factory) as db,
            patch.object(topology_service, "_lookup_source_handler") as collector,
        ):
            transaction = db.get_transaction()
            status = topology_service.get_topology_status(project_id=3)
            self.assertEqual(status.drift.status, "unavailable")
            topology_service.load_topology(project_id=3)
            for operation in (
                lambda: topology_service.check_topology_drift(project_id=3, force=True),
                lambda: topology_service.import_topology_source(
                    "terraform", "/synthetic.tfstate", project_id=3
                ),
            ):
                with self.assertRaises(topology_service.TopologyImportError):
                    operation()
            collector.assert_not_called()
            self.assertIs(db.get_transaction(), transaction)
            self.assertEqual(list(db.scalars(select(AppSetting))), [])

    def test_legacy_topology_status_refresh_releases_writer(self):
        from concurrent.futures import ThreadPoolExecutor
        import json
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from models.tables import TopologyVersion

        payload = {
            "services": [{"id": "api", "label": "API", "resource_keys": ["api"]}],
            "metadata": {
                "import": {
                    "source_type": "terraform",
                    "source_ref": "/synthetic.tfstate",
                }
            },
        }
        with self.factory.begin() as db:
            db.add(
                TopologyVersion(
                    project_id=3,
                    source_type="terraform",
                    payload_json=json.dumps(payload),
                )
            )
        other_engine = create_engine(self.engine.url, connect_args={"timeout": 0.1})
        self.addCleanup(other_engine.dispose)
        other_factory = sessionmaker(other_engine)

        def unrelated_read():
            with auth.authorized_session(other_factory) as db:
                auth.guard_report(db, 3)

        def collect(_reference):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(unrelated_read).result(timeout=2)
            return topology_service.TopologyChangeSet(
                operation="replace", services=payload["services"]
            )

        with patch.object(
            topology_service, "_lookup_source_handler", return_value=collect
        ) as collector:
            payload, _ = topology_service.load_topology(project_id=3)
            self.assertEqual(payload["services"][0]["id"], "api")
            collector.assert_called_once()

    def test_incident_lookup_hides_foreign_and_missing_existence(self):
        from models.tables import IncidentRecord

        with self.factory.begin() as db:
            db.add(
                IncidentRecord(
                    id=444,
                    project_id=2,
                    workspace_id=3,
                    title="private",
                    severity="high",
                    source_file="private.md",
                    content="synthetic",
                )
            )
        self.member("maintainer", workspace=1)
        errors = []
        for incident_id in (444, 445):
            with (
                self.context(mutation=True),
                self.assertRaises(auth.TrustedAuthorizationError) as raised,
            ):
                deployment_outcome_service.record_deployment_outcome(
                    analysis_id=1, outcome="failure", linked_incident_id=incident_id
                )
            errors.append(str(raised.exception))
        self.assertEqual(errors[0], errors[1])

    def test_cached_outcome_counts_recompute_after_linked_report_becomes_private(self):
        from models.tables import Project, DeploymentOutcome, AppSetting

        for outcome in ("failure", "success"):
            with self.subTest(outcome=outcome):
                with self.factory.begin() as db:
                    db.get(Project, 1).authorization_required = False
                    db.query(DeploymentOutcome).delete()
                    db.add(
                        DeploymentOutcome(
                            project_id=3,
                            analysis_id=1,
                            outcome_label=outcome,
                            deployed_at=self.now,
                        )
                    )
                initial = backtesting_service.run_weekly_backtest(
                    project_id=3, now=self.now
                )
                self.assertEqual(initial["calibration_metrics"]["sample_size"], 1)
                with self.factory.begin() as db:
                    db.get(Project, 1).authorization_required = True
                    stored_before = db.get(
                        AppSetting, backtesting_service._snapshot_key(3)
                    ).value
                result = backtesting_service.fetch_calibration_dashboard_seed(
                    project_id=3, now=self.now
                )
                self.assertEqual(result["calibration_metrics"]["sample_size"], 0)
                self.assertEqual(result["confidence_trends"]["sample_size"], 0)
                self.assertEqual(result["failed_deploy_count"], 0)
                self.assertEqual(result["backtest_rows"], [])
                self.assertNotIn("_authorization_inputs", result)
                with self.factory() as db:
                    self.assertEqual(
                        db.get(AppSetting, backtesting_service._snapshot_key(3)).value,
                        stored_before,
                    )

    def test_cached_feedback_only_counts_recompute_after_report_protection(self):
        from models.tables import Project, FeedbackEvent

        with self.factory.begin() as db:
            db.get(Project, 1).authorization_required = False
            db.add(
                FeedbackEvent(
                    project_id=3,
                    analysis_id=1,
                    finding_id="synthetic-feedback",
                    useful=True,
                    created_at=self.now,
                )
            )
        initial = backtesting_service.run_weekly_backtest(project_id=3, now=self.now)
        self.assertEqual(
            initial["calibration_metrics"]["feedback_history_event_count"], 1
        )
        with self.factory.begin() as db:
            db.get(Project, 1).authorization_required = True
        result = backtesting_service.fetch_calibration_dashboard_seed(
            project_id=3, now=self.now
        )
        self.assertEqual(
            result["calibration_metrics"]["feedback_history_event_count"], 0
        )
        self.assertEqual(result["calibration_metrics"]["feedback_event_count"], 0)
        self.assertNotIn("_authorization_inputs", result)
