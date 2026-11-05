"""Real scoped immutable inventory admission and run binding regressions."""

from __future__ import annotations

import copy
import unittest
from tests.test_infra_automation import test_target_admission as target_fixture
from sqlalchemy import select, func
from infra_automation.lifecycle import LifecycleError
from infra_automation.unit_contracts import SaveUnitsRequest, UnitRunRequest
from services import infra_automation_units as units
from services import project_service as auth
from tests.test_infra_automation.test_preflight_service import PreflightServiceTests
from models.tables import InfraAutomationRun, InfraAutomationUnitRevision


def inventory():
    return {
        "version": 1,
        "affected": ["app"],
        "units": [
            {
                "id": "app",
                "source": {"kind": "uploaded", "path": "."},
                "environment": "dev",
                "target": "local",
                "prerequisites": [],
            }
        ],
    }


class UnitServiceTests(PreflightServiceTests):
    def save(self, data=None, **kwargs):
        with self.credentials():
            return units.save_units(
                SaveUnitsRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_version=0,
                    reason="Declared fixture scope",
                    map=data or inventory(),
                    **kwargs,
                )
            )

    def start(self, revision, **updates):
        payload = dict(
            run=self.request.run.model_dump(mode="json"),
            revision_id=revision["revision_id"],
            confirmed_map_digest=revision["map_digest"],
            bindings=[
                dict(
                    unit_id="app",
                    intake_step_id="upload",
                    analysis_step_id="analysis",
                    artifacts=[item.model_dump() for item in self.request.artifacts],
                )
            ],
        )
        payload.update(updates)
        with self.credentials():
            return units.request_unit_run(UnitRunRequest.model_validate(payload))

    def test_revision_is_immutable_and_scope_is_rechecked(self):
        item = self.save()
        with self.credentials():
            read = units.get_revision(
                item["inventory_id"],
                item["revision_id"],
                project_id=100,
                workspace_id=100,
            )
            self.assertEqual(read, item)
            with self.assertRaises(auth.TrustedAuthorizationError):
                units.get_revision(
                    item["inventory_id"],
                    item["revision_id"],
                    project_id=200,
                    workspace_id=200,
                )
        with self.factory.begin() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(InfraAutomationUnitRevision)
                ),
                1,
            )

    def test_run_snapshot_and_artifact_intake_commit_together(self):
        revision = self.save()
        run = self.start(revision)
        with self.credentials():
            view = units.get_run_units(run["id"], project_id=100, workspace_id=100)
        self.assertTrue(view["available"])
        self.assertEqual(
            view["snapshot"]["revision"]["map_digest"], revision["map_digest"]
        )
        self.assertEqual(view["evidence"]["status"], "pending")
        self.assertEqual(self.start(revision)["id"], run["id"])

    def test_accepted_replay_survives_inventory_supersession_without_new_authority(
        self,
    ):
        revision = self.save()
        original = self.start(revision)
        with self.credentials():
            units.save_units(
                SaveUnitsRequest(
                    project_id=100,
                    workspace_id=100,
                    inventory_id=revision["inventory_id"],
                    expected_version=1,
                    reason="Supersede reviewed inventory",
                    map=inventory(),
                )
            )
        self.assertEqual(self.start(revision)["id"], original["id"])
        new_request = self.request.run.model_dump(mode="json")
        new_request["idempotency_key"] = "new-start-after-supersession"
        with self.assertRaises(LifecycleError):
            self.start(revision, run=new_request)
        changed = self.request.run.model_dump(mode="json")
        changed["reason"] = "Different request with original key"
        with self.assertRaises(LifecycleError):
            self.start(revision, run=changed)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationRun)), 1
            )
        self.member("read-only")
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.start(revision)

    def test_wrong_confirmation_and_mapping_roll_back_admission(self):
        revision = self.save()
        for change in (
            {"confirmed_map_digest": "sha256:" + "a" * 64},
            {
                "bindings": [
                    dict(
                        unit_id="missing",
                        intake_step_id="upload",
                        analysis_step_id="analysis",
                    )
                ]
            },
        ):
            with self.subTest(change=change), self.assertRaises(LifecycleError):
                self.start(revision, **change)
        with self.factory.begin() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationRun)), 0
            )

    def test_analysis_persists_combined_evidence_and_changes_are_denied(self):
        revision = self.save()
        run = self.start(revision)
        self.execute(run)
        with self.credentials():
            view = units.get_run_units(run["id"], project_id=100, workspace_id=100)
        self.assertEqual(view["evidence"]["status"], "available")
        self.assertTrue(view["evidence"]["combined_digest"].startswith("sha256:"))
        changed = copy.deepcopy(inventory())
        changed["units"][0]["source"]["path"] = "new"
        with self.credentials():
            units.save_units(
                SaveUnitsRequest(
                    project_id=100,
                    workspace_id=100,
                    inventory_id=revision["inventory_id"],
                    expected_version=1,
                    reason="Changed declared scope",
                    map=changed,
                )
            )
            view = units.get_run_units(run["id"], project_id=100, workspace_id=100)
        self.assertEqual(view["evidence"]["status"], "changed")

    def two_unit_request(self, *, dependency="analysis-network"):
        from infra_automation.state import RunRequest
        from infra_automation.preflight_contracts import PreflightRequest
        from models.repositories import infra_automation_workflows
        import json

        with self.factory() as db:
            raw = infra_automation_workflows.get_revision(
                db, self.request.run.revision_id
            ).canonical_definition
        workflow = json.loads(raw)
        first = copy.deepcopy(workflow["steps"])
        for step in first:
            step["id"] += "-network"
            step["depends_on"] = [item + "-network" for item in step["depends_on"]]
            if "artifact" in step:
                step["artifact"]["step_id"] += "-network"
        if dependency:
            workflow["steps"][0]["depends_on"] = [dependency]
        workflow["steps"] = first + workflow["steps"]
        workflow_id, revision_id = self.publish_fixture(workflow)
        self.request = PreflightRequest(
            run=RunRequest(
                workflow_id=workflow_id,
                revision_id=revision_id,
                workspace_id=100,
                idempotency_key="two-units",
                reason="Declared two unit request",
            ),
            artifacts=self.request.artifacts,
        )
        data = inventory()
        network = copy.deepcopy(data["units"][0])
        network["id"] = "network"
        data["units"][0]["prerequisites"] = ["network"]
        data["units"].append(network)
        revision = self.save(data)
        bindings = [
            dict(
                unit_id=unit,
                intake_step_id="upload" + suffix,
                analysis_step_id="analysis" + suffix,
                artifacts=[item.model_dump() for item in self.request.artifacts],
            )
            for unit, suffix in (("app", ""), ("network", "-network"))
        ]
        return revision, bindings

    def execute_two_units(self, run):
        from infra_automation import claims
        from infra_automation.analysis_context import _bind_worker
        from infra_automation.local_workers import WorkerInput
        from models.repositories import infra_automation_runs as runs
        from services import infra_automation_preflight as preflight

        with auth.authorized_session(self.factory) as db:
            owner = claims.acquire_coordinator(db, project_id=100, workspace_id=100)
            row = runs.get_run(db, run["id"])
            claims.start_run(db, owner, run_id=row.id, expected_version=row.version)
        for step_id in ("upload-network", "analysis-network", "upload", "analysis"):
            with auth.authorized_session(self.factory) as db:
                registration = preflight.PREFLIGHT_REGISTRY.get(
                    "uploaded_intake"
                    if step_id.startswith("upload")
                    else "shared_analysis"
                )
                attempt = claims.prepare_attempt(
                    db,
                    owner,
                    run_id=run["id"],
                    step_id=step_id,
                    handler_id=registration.handler_id,
                    handler_version=registration.handler_version,
                    retry_safe=True,
                )
                handle = claims.claim_attempt(
                    db, owner, attempt_id=attempt.id, expected_version=attempt.version
                )
                claims.start_attempt(db, handle, expected_version=attempt.version)
                row = runs.get_run(db, run["id"])
                previous = [
                    a
                    for a in runs.list_attempts(db, run_id=row.id)
                    if a.state == "succeeded"
                ]
                value = WorkerInput(
                    row.snapshot_bytes,
                    step_id,
                    tuple((a.step_id, a.output_json.encode()) for a in previous),
                )
            with _bind_worker(handle, self.factory):
                result = preflight.execute_preflight_step(value)
            with auth.authorized_session(self.factory) as db:
                attempt = runs.get_attempt(db, handle.attempt_id)
                attempt = claims.register_upload(
                    db,
                    handle,
                    expected_version=attempt.version,
                    reference=result.output,
                )
                attempt = claims.commit_output(
                    db, handle, expected_version=attempt.version, output=result.output
                )
                claims.complete_attempt(
                    db, handle, expected_version=attempt.version, state="succeeded"
                )

    def test_two_units_complete_real_shared_analysis_and_order_is_canonical(self):
        revision, bindings = self.two_unit_request()
        run = self.start(revision, bindings=bindings)
        self.assertEqual(
            self.start(revision, bindings=list(reversed(bindings)))["id"], run["id"]
        )
        self.execute_two_units(run)
        with self.credentials():
            value = units.get_run_units(run["id"], project_id=100, workspace_id=100)
        self.assertEqual(
            value["snapshot"]["revision"]["plan"]["waves"], [["network"], ["app"]]
        )
        self.assertEqual(value["evidence"]["status"], "available")
        self.assertEqual(len(value["evidence"]["items"]), 2)
        self.assertEqual({item["status"] for item in value["locks"]}, {"not_requested"})

    def test_missing_dependency_analysis_and_extra_step_coverage_are_denied(self):
        revision, bindings = self.two_unit_request(dependency="upload-network")
        with self.assertRaises(LifecycleError):
            self.start(revision, bindings=bindings)
        with self.assertRaises(LifecycleError):
            self.start(revision, bindings=bindings[:1])
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationRun)), 0
            )

    def test_undeclared_review_order_cannot_be_hidden_on_analysis_step(self):
        from models.repositories import infra_automation_workflows as workflows
        from infra_automation.state import RunRequest
        import json

        _, bindings = self.two_unit_request(dependency=None)
        with self.factory() as db:
            definition = json.loads(
                workflows.get_revision(
                    db, self.request.run.revision_id
                ).canonical_definition
            )
        definition["steps"][-1]["depends_on"].append("analysis-network")
        workflow_id, revision_id = self.publish_fixture(definition)
        data = inventory()
        network = copy.deepcopy(data["units"][0])
        network["id"] = "network"
        data["units"].append(network)
        data["affected"].append("network")
        revision = self.save(data)
        request = RunRequest(
            workflow_id=workflow_id,
            revision_id=revision_id,
            workspace_id=100,
            idempotency_key="hidden-analysis-order",
            reason="Reject hidden review ordering",
        )
        with self.assertRaises(LifecycleError):
            self.start(revision, run=request.model_dump(), bindings=bindings)

    def test_revision_conflict_and_insufficient_role_never_write(self):
        revision = self.save()
        with self.credentials(), self.assertRaises(LifecycleError):
            units.save_units(
                SaveUnitsRequest(
                    project_id=100,
                    workspace_id=100,
                    inventory_id=revision["inventory_id"],
                    expected_version=0,
                    reason="Stale edit",
                    map=inventory(),
                )
            )
        self.principal("reader")
        self.member("read-only", principal="reader")
        with (
            self.credentials("reader"),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            units.save_units(
                SaveUnitsRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_version=0,
                    reason="No write permission",
                    map=inventory(),
                )
            )
        with self.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(InfraAutomationUnitRevision)
                ),
                1,
            )

    def test_existing_unassociated_run_and_changed_artifacts_cannot_replay(self):
        revision = self.save()
        self.admit()
        with self.assertRaises(LifecycleError):
            self.start(revision)

    def test_corrupt_revision_and_run_snapshot_fail_closed(self):
        from models.tables import InfraAutomationRunUnits

        revision = self.save()
        run = self.start(revision)
        with self.factory.begin() as db:
            row = db.get(InfraAutomationRunUnits, run["id"])
            row.snapshot_bytes = b"{}"
        with self.credentials(), self.assertRaises(LifecycleError):
            units.get_run_units(run["id"], project_id=100, workspace_id=100)
        with self.factory.begin() as db:
            row = db.get(InfraAutomationUnitRevision, revision["revision_id"])
            row.plan_bytes = b"{}"
        with self.credentials(), self.assertRaises(LifecycleError):
            units.get_revision(
                revision["inventory_id"],
                revision["revision_id"],
                project_id=100,
                workspace_id=100,
            )

    def test_uploaded_complete_bundle_remains_advisory_only(self):
        from types import SimpleNamespace
        from datetime import timedelta
        from services import infra_automation_support as support
        from models.repositories import infra_automation_runs as runs

        revision = self.save()
        run = self.start(revision)
        self.execute(run)
        with self.credentials(), auth.authorized_session() as db:
            row = runs.get_run(db, run["id"])
            view = units.get_run_units(run["id"], project_id=100, workspace_id=100)
            deadline = support.utc(runs.utc(row.created_at) + timedelta(minutes=1))
            binding = SimpleNamespace(
                unit_waves_digest=view["evidence"]["combined_digest"],
                evidence_deadline=deadline,
            )
            with self.assertRaises(LifecycleError):
                units.assert_unit_binding(db, row, binding)

    def test_inventory_counts_against_global_engine_byte_quota(self):
        from unittest.mock import patch
        import config

        with patch("services.infra_automation_units.MAX_PROJECT_BYTES", 1):
            with self.assertRaises(LifecycleError):
                self.save()
        self.save()
        bounds = config.engine_bounds()
        with patch(
            "config.engine_bounds",
            return_value=bounds.model_copy(update={"global_bytes": 1}),
        ):
            with self.assertRaises(LifecycleError):
                self.save()

    def test_retained_failed_report_link_does_not_hide_latest_success(self):
        from models.tables import (
            AnalysisReport,
            InfraAutomationAttempt,
            InfraAutomationReportLink,
            InfraAutomationRunUnits,
        )
        from models.repositories import infra_automation_runs as runs
        from services import infra_automation_support as support
        import json

        revision = self.save()
        run = self.start(revision)
        self.execute(run)
        with self.factory.begin() as db:
            prior = db.scalar(
                select(InfraAutomationAttempt).where(
                    InfraAutomationAttempt.run_id == run["id"],
                    InfraAutomationAttempt.step_id == "analysis",
                )
            )
            values = {
                column.key: getattr(prior, column.key)
                for column in InfraAutomationAttempt.__table__.columns
                if column.key not in {"sequence", "id"}
            }
            prior.state = "failed"
            successful = InfraAutomationAttempt(
                id="latest-successful-attempt",
                **{**values, "attempt_number": 2, "fence": 2},
            )
            db.add(successful)
            link = db.scalar(
                select(InfraAutomationReportLink).where(
                    InfraAutomationReportLink.attempt_id == prior.id
                )
            )
            report = db.get(AnalysisReport, link.report_id)
            new_report = AnalysisReport(
                **{
                    column.key: getattr(report, column.key)
                    for column in AnalysisReport.__table__.columns
                    if column.key != "id"
                }
            )
            db.add(new_report)
            db.flush()
            content = json.loads(link.provenance_bytes)
            content.update(
                attempt_id=successful.id,
                report_id=new_report.id,
                report_url=f"/reports/{new_report.id}",
            )
            raw = support.canonical(content)
            new_link = InfraAutomationReportLink(
                id="latest-successful-link",
                run_id=run["id"],
                attempt_id=successful.id,
                manifest_id=link.manifest_id,
                report_id=new_report.id,
                project_id=100,
                workspace_id=100,
                requested_by="human-a",
                provenance_bytes=raw,
                digest=support.digest(raw),
                created_at=link.created_at,
            )
            db.add(new_link)
            successful.output_json = support.canonical(
                dict(kind="report", reference=new_link.id, digest=new_link.digest)
            ).decode()
            successful.output_digest = new_link.digest
            expected_report = new_report.id
        with self.credentials(), auth.authorized_session() as db:
            row = runs.get_run(db, run["id"])
            retained = db.get(InfraAutomationRunUnits, run["id"])
            current = units._evidence(db, row, retained, units._snapshot(db, retained))
            self.assertEqual(current[1][0]["report_id"], expected_report)
        # A persisted earlier complete bundle remains stale after an actual replan.
        with self.credentials():
            view = units.get_run_units(run["id"], project_id=100, workspace_id=100)
        self.assertEqual(view["evidence"]["status"], "changed")
        self.assertEqual(view["evidence"]["items"][0]["report_id"], expected_report)

    def test_migration_guards_reject_snapshot_replacement_and_history_deletion(self):
        from importlib import import_module
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy import text

        migration = import_module("migrations.versions.038_add_declared_unit_maps")
        revision = self.save()
        run = self.start(revision)
        self.execute(run)
        with self.engine.begin() as connection:
            for name, body in migration.GUARDS.items():
                connection.exec_driver_sql(f"CREATE TRIGGER {name} {body}")
        statements = (
            "UPDATE infra_automation_unit_revisions SET plan_bytes=plan_bytes",
            "DELETE FROM infra_automation_unit_revisions",
            "INSERT OR REPLACE INTO infra_automation_unit_revisions SELECT * FROM infra_automation_unit_revisions",
            "UPDATE infra_automation_run_units SET snapshot_bytes=snapshot_bytes",
            "UPDATE infra_automation_run_units SET evidence_bytes=evidence_bytes",
            "DELETE FROM infra_automation_run_units",
            "INSERT OR REPLACE INTO infra_automation_run_units SELECT * FROM infra_automation_run_units",
        )
        for sql in statements:
            with (
                self.subTest(sql=sql),
                self.assertRaises(IntegrityError),
                self.engine.begin() as connection,
            ):
                connection.execute(text(sql))


class UnitTargetTests(unittest.TestCase):
    def setUp(self):
        self.case = target_fixture.TargetAdmissionTests(
            "test_identical_request_reuses_capture_and_lock_without_recapturing"
        )
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.register()

    def request(self, *, alias="target-one", path=".", key="units-target", two=False):
        run = self.case.request(alias, *(["target-two"] if two else []), key=key)
        data = {
            "affected": ["unit" + str(i) for i in range(2 if two else 1)],
            "units": [
                dict(
                    id="unit" + str(i),
                    source=dict(
                        kind="declared_repository",
                        repository_id="repo",
                        commit_sha="a" * 40,
                        path=path,
                    ),
                    environment="test",
                    target=alias if i == 0 else "target-two",
                    prerequisites=[],
                )
                for i in range(2 if two else 1)
            ],
        }
        with self.case.credentials():
            revision = units.save_units(
                SaveUnitsRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_version=0,
                    reason="Declared target fixture",
                    map=data,
                )
            )
        return UnitRunRequest(
            run=run,
            revision_id=revision["revision_id"],
            confirmed_map_digest=revision["map_digest"],
            bindings=[
                dict(
                    unit_id="unit" + str(i),
                    intake_step_id="collect" + ("_1" if i else ""),
                    analysis_step_id="analyze" + ("_1" if i else ""),
                )
                for i in range(2 if two else 1)
            ],
        )

    def admit(self, request):
        with self.case.credentials():
            return units.request_unit_run(
                request,
                registry=self.case.handlers,
                registry_contract=self.case.registry,
            )

    def test_unit_aliases_share_one_canonical_lock_and_unknown_work_retains_it(self):
        from models.tables import InfraAutomationTargetLock
        from infra_automation.state import CancelRunRequest
        from services import infra_automation_engine_service as engine

        request = self.request(two=True)
        run = self.admit(request)
        with self.case.credentials():
            view = units.get_run_units(run["id"], project_id=100, workspace_id=100)
        self.assertEqual(len(view["locks"]), 2)
        self.assertEqual(
            {item["canonical_target"] for item in view["locks"]}, {"target"}
        )
        with self.case.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationTargetLock)),
                1,
            )
        competing = self.request(alias="target-two", key="competing")
        with self.assertRaises(LifecycleError):
            self.admit(competing)
        with self.case.factory.begin() as db:
            row = db.scalar(
                select(InfraAutomationRun).where(InfraAutomationRun.id == run["id"])
            )
            row.external_possible = True
            row.state = "delivery_unknown"
        with self.case.credentials():
            current = engine.get_run(run["id"])
            engine.cancel_run(
                run["id"],
                CancelRunRequest(
                    expected_version=current["version"],
                    reason="Unknown work stays locked",
                ),
            )
            view = units.get_run_units(run["id"], project_id=100, workspace_id=100)
        self.assertEqual({item["status"] for item in view["locks"]}, {"held"})
        with self.assertRaises(LifecycleError):
            self.admit(competing)

    def test_nonroot_declared_source_cannot_claim_root_collected_evidence(self):
        request = self.request(path="subdirectory")
        before = self.case.counts()
        with self.assertRaises(LifecycleError):
            self.admit(request)
        self.assertEqual(self.case.counts(), before)

    def _assert_decision_order_rejected(self, stage):
        import json
        from infra_automation.state import RunRequest
        from models.repositories import infra_automation_workflows as workflows
        from tests.test_infra_automation import test_workflow_snapshots as snapshots

        request = self.request(two=True)
        with self.case.factory() as db:
            workflow = json.loads(
                workflows.get_revision(db, request.run.revision_id).canonical_definition
            )
        steps = {step["id"]: step for step in workflow["steps"]}
        steps["collect_1"]["depends_on"] = [
            "decision" if stage == "intake" else "analyze"
        ]
        if stage == "analysis":
            steps["analyze_1"]["depends_on"] = ["collect_1", "decision"]
        workflow_ids = snapshots.WorkflowSnapshotTests.publish_fixture(
            self.case, workflow
        )
        with self.case.credentials():
            from models.repositories import infra_automation_units as repository

            with auth.authorized_session() as session:
                old = units._revision_view(
                    repository.revision(session, request.revision_id)
                )
            declared = old["plan"]["inventory"]
            declared["affected"] = ["unit1"]
            declared["units"][1]["prerequisites"] = ["unit0"]
            revision = units.save_units(
                SaveUnitsRequest(
                    project_id=100,
                    workspace_id=100,
                    inventory_id=old["inventory_id"],
                    expected_version=1,
                    reason="Declared collection dependency",
                    map=declared,
                )
            )
        changed = request.model_copy(
            update={
                "run": RunRequest(
                    workflow_id=workflow_ids[0],
                    revision_id=workflow_ids[1],
                    workspace_id=100,
                    idempotency_key="decision-before-" + stage,
                    reason="Reject circular evidence wait",
                ),
                "revision_id": revision["revision_id"],
                "confirmed_map_digest": revision["map_digest"],
            }
        )
        before = self.case.counts()
        with self.assertRaises(LifecycleError) as caught:
            self.admit(changed)
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(self.case.counts(), before)

    def test_upstream_decision_before_intake_cannot_deadlock_combined_evidence(self):
        self._assert_decision_order_rejected("intake")

    def test_upstream_decision_before_analysis_cannot_deadlock_combined_evidence(self):
        self._assert_decision_order_rejected("analysis")

    def test_upstream_external_handoff_is_not_collection_order(self):
        from infra_automation.state import RunRequest
        from models.repositories import infra_automation_workflows as workflows
        from tests.test_infra_automation import test_workflow_snapshots as snapshots
        import json

        request = self.request(two=True)
        with self.case.factory() as db:
            workflow = json.loads(
                workflows.get_revision(db, request.run.revision_id).canonical_definition
            )
        workflow["steps"][5]["depends_on"] = ["handoff"]
        ids = snapshots.WorkflowSnapshotTests.publish_fixture(self.case, workflow)
        changed = request.model_copy(
            update={
                "run": RunRequest(
                    workflow_id=ids[0],
                    revision_id=ids[1],
                    workspace_id=100,
                    idempotency_key="external-order",
                    reason="Reject deployment ordering",
                )
            }
        )
        before = self.case.counts()
        with self.assertRaises(LifecycleError):
            self.admit(changed)
        self.assertEqual(self.case.counts(), before)


class UnitCollectedEvidenceTests(unittest.TestCase):
    def setUp(self):
        from tests.test_infra_automation.test_collection_intake import (
            CollectionIntakeTests,
        )

        self.case = CollectionIntakeTests(
            "test_collected_artifact_reuses_shared_analysis_and_relational_provenance"
        )
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def associate_fixture(self):
        """Seed association before analysis; production late association has no API."""
        from models.tables import InfraAutomationRunUnits
        from models.repositories import infra_automation_runs as runs
        from services import infra_automation_support as support
        from infra_automation.unit_map import plan_unit_map

        data = inventory()
        data["units"][0]["source"] = dict(
            kind="declared_repository",
            repository_id=self.case.repository_id,
            commit_sha=self.case.source_commit,
            path=".",
        )
        with self.case.credentials():
            revision = units.save_units(
                SaveUnitsRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_version=0,
                    reason="Synthetic collected map evidence fixture",
                    map=data,
                )
            )
        binding = dict(
            unit_id="app", intake_step_id="upload", analysis_step_id="analysis"
        )
        from infra_automation.unit_contracts import UnitInputBinding

        with self.case.credentials(), auth.authorized_session() as db:
            run = runs.get_run(db, self.case.run.id)
            document = units.engine._document(run)
            targets = units._bind_steps(
                db, run, document, plan_unit_map(data), [UnitInputBinding(**binding)]
            )
            payload = support.canonical(
                dict(revision=revision, bindings=[binding], targets=targets)
            )
            db.add(
                InfraAutomationRunUnits(
                    run_id=run.id,
                    revision_id=revision["revision_id"],
                    project_id=100,
                    workspace_id=100,
                    snapshot_bytes=payload,
                    snapshot_digest=support.digest(payload),
                    request_digest=support.digest(b"fixture"),
                )
            )

    def test_authenticated_collection_custody_deadline_bounds_complete_bundle(self):
        from datetime import timedelta
        from types import SimpleNamespace
        from infra_automation.decisions import instant
        from models.repositories import infra_automation_runs as runs

        self.associate_fixture()
        payload = self.case.payload()
        custody_deadline = self.case.now + timedelta(seconds=60)
        payload["provenance"]["custody"]["expires_at"] = units.support.utc(
            custody_deadline
        )
        payload["provenance"]["source_deadline"] = payload["provenance"]["custody"][
            "expires_at"
        ]
        self.case.collect(payload)
        self.case.analyze_collection()
        with self.case.credentials():
            value = units.get_run_units(
                self.case.run.id, project_id=100, workspace_id=100
            )
        self.assertEqual(value["evidence"]["status"], "available")
        binding = SimpleNamespace(
            unit_waves_digest=value["evidence"]["combined_digest"],
            evidence_deadline=units.support.utc(custody_deadline),
        )
        with self.case.credentials(), auth.authorized_session() as db:
            run = runs.get_run(db, self.case.run.id)
            units.assert_unit_binding(db, run, binding)
            binding.unit_waves_digest = "sha256:" + "f" * 64
            with self.assertRaises(LifecycleError):
                units.assert_unit_binding(db, run, binding)
            binding.unit_waves_digest = value["evidence"]["combined_digest"]
            from unittest.mock import patch
            from models.repositories import infra_automation_units as repository

            retained = repository.run_units(db, run.id)
            mixed = copy.deepcopy(units._snapshot(db, retained))
            mixed["revision"]["plan"]["inventory"]["units"].append(
                dict(
                    id="uploaded-prerequisite",
                    source=dict(kind="uploaded", path="."),
                    environment="dev",
                    target="local",
                    prerequisites=[],
                )
            )
            with (
                patch.object(units, "_snapshot", return_value=mixed),
                self.assertRaises(LifecycleError),
            ):
                units.assert_unit_binding(db, run, binding)
            with self.assertRaises(LifecycleError):
                units.assert_unit_binding(
                    db,
                    run,
                    binding,
                    now=instant(payload["provenance"]["custody"]["expires_at"]),
                )
            binding.evidence_deadline = units.support.utc(
                custody_deadline + timedelta(seconds=1)
            )
            with self.assertRaises(LifecycleError):
                units.assert_unit_binding(db, run, binding)
