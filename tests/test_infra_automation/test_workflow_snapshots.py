"""Immutable, authorized published-revision snapshot consumer proofs."""

from __future__ import annotations

import copy
import json
from unittest.mock import patch

from sqlalchemy import select

from infra_automation.contracts import ProfileContract, RegistryContract
from infra_automation.lifecycle import AutomationSettings, LifecycleError
from models.repositories import infra_automation_workflows as repository
from models.tables import InfraAutomationAudit
from services.infra_automation_snapshots import export_run_snapshot
from services.infra_automation_support import canonical, digest
from services import project_service as authorization
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class WorkflowSnapshotTests(LifecycleCase):
    def publish_fixture(self, definition=None, *, workspace_id=100):
        definition = definition or {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": str(workspace_id) if workspace_id is not None else None,
            "environment": "dev",
            "inputs": {"note": {"type": "string", "max_length": 100}},
            "steps": [
                {
                    "id": "upload",
                    "kind": "uploaded_intake",
                    "depends_on": [],
                    "source": {"kind": "uploaded"},
                }
            ],
        }
        from infra_automation.workflow_schema import Workflow

        raw = canonical(Workflow.model_validate(definition).model_dump(mode="json"))
        with self.factory() as session:
            row = repository.create_workflow(
                session,
                project_id=100,
                workspace_id=workspace_id,
                name="Snapshot fixture",
                canonical_definition=raw,
                digest=digest(raw),
                created_by="human-a",
            )
            revision = repository.append_revision(
                session,
                workflow_id=row.id,
                project_id=100,
                workspace_id=workspace_id,
                revision_number=1,
                canonical_definition=raw,
                digest=digest(raw),
                published_by="human-a",
                idempotency_key_digest=digest(row.id.encode()),
                request_digest=digest(raw),
            )
            ids = row.id, revision.id
            session.commit()
        return ids

    def enable(self):
        with self.factory() as session:
            policy = repository.get_policy(session, project_id=100)
            repository.save_policy(
                session,
                project_id=100,
                expected_version=policy.version if policy else 0,
                settings_json=AutomationSettings(enabled=True).model_dump_json(),
            )
            session.commit()

    def export(self, ids, inputs=None, workspace_id=100, **kwargs):
        with self.credentials():
            return export_run_snapshot(
                *ids,
                {"note": "original"} if inputs is None else inputs,
                workspace_id,
                **kwargs,
            )

    def test_uploaded_snapshot_is_immutable_after_caller_draft_and_policy_edits(self):
        self.enable()
        ids = self.publish_fixture()
        inputs = {"note": "original"}
        exported = self.export(ids, inputs)
        before = exported.canonical_bytes
        inputs["note"] = "edited"
        view = exported.data
        view["inputs"]["note"] = "changed"
        exported.snapshot.definition.steps.clear()
        with self.factory() as session:
            row = repository.get_workflow(session, ids[0])
            altered = json.loads(row.draft_definition)
            altered["environment"] = "changed"
            raw = canonical(altered)
            repository.update_workflow(
                session,
                workflow_id=row.id,
                expected_version=row.draft_version,
                canonical_definition=raw,
                digest=digest(raw),
            )
            policy = repository.get_policy(session, project_id=100)
            repository.save_policy(
                session,
                project_id=100,
                expected_version=policy.version,
                settings_json=AutomationSettings(enabled=False).model_dump_json(),
            )
            session.commit()
        self.assertEqual(exported.canonical_bytes, before)
        self.assertEqual(exported.digest, digest(before))
        self.assertEqual(exported.snapshot.inputs, {"note": "original"})
        source = exported.snapshot.sources[0]
        self.assertIsNone(source.repository_id)
        self.assertIsNone(source.commit_sha)
        self.assertIn("does not establish", source.limitation)
        self.assertTrue(exported.snapshot.policy.enabled)
        self.assertEqual(exported.authority.authentication_version, 1)
        self.assertEqual(exported.authority.workspace_id, 100)

    def test_old_revision_replay_ignores_changed_draft_and_keeps_input_identity(self):
        self.enable()
        ids = self.publish_fixture()
        first = self.export(ids)
        with self.factory() as session:
            row = repository.get_workflow(session, ids[0])
            repository.update_workflow(
                session,
                workflow_id=row.id,
                expected_version=row.draft_version,
                canonical_definition=b"{}",
                digest=digest(b"{}"),
            )
            session.commit()
        second = self.export(ids, {"note": "rerun"})
        self.assertEqual(first.definition_digest, second.definition_digest)
        self.assertNotEqual(first.input_digest, second.input_digest)
        self.assertEqual(first.snapshot.revision_id, second.snapshot.revision_id)
        self.assertEqual(first.snapshot.inputs, {"note": "original"})

    def test_draft_unknown_revision_other_workflow_and_workspace_are_denied(self):
        self.enable()
        ids = self.publish_fixture()
        other = self.publish_fixture()
        for candidate, workspace in [
            ((ids[0], ids[0]), 100),
            ((ids[0], "unknown"), 100),
            ((ids[0], other[1]), 100),
            (ids, 200),
            (ids, None),
            (ids, True),
        ]:
            with self.subTest(candidate=candidate, workspace=workspace):
                with self.assertRaises(
                    (authorization.TrustedAuthorizationError, LifecycleError)
                ):
                    self.export(candidate, workspace_id=workspace)

    def test_project_scoped_definition_resolves_concrete_existing_workspace(self):
        self.enable()
        ids = self.publish_fixture(workspace_id=None)
        exported = self.export(ids)
        self.assertIsNone(exported.snapshot.definition.workspace_id)
        self.assertEqual(exported.snapshot.workspace_id, 100)
        with self.assertRaises(authorization.TrustedAuthorizationError):
            self.export(ids, workspace_id=9999)

    def test_disabled_archived_unknown_inputs_and_secret_values_fail_closed(self):
        ids = self.publish_fixture()
        with self.assertRaises(LifecycleError):
            self.export(ids)
        self.enable()
        for value in (
            {},
            {"note": "ok", "extra": "no"},
            {"note": 1},
            {"note": "ghp_" + "A" * 36},
        ):
            with self.subTest(value=value):
                with self.assertRaises(LifecycleError):
                    self.export(ids, value)
        with self.factory() as session:
            repository.update_workflow(
                session, workflow_id=ids[0], expected_version=1, archived=True
            )
            session.commit()
        with self.assertRaises(LifecycleError):
            self.export(ids)
        with self.factory() as session:
            self.assertEqual(list(session.scalars(select(InfraAutomationAudit))), [])

    def test_collected_sources_resolve_immutable_commit_and_require_trusted_profile(
        self,
    ):
        self.enable()
        profile = "sha256:" + "a" * 64
        definition = {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": "100",
            "environment": {"ref": "input", "name": "environment"},
            "inputs": {
                "repository": {"type": "identifier"},
                "commit": {"type": "commit_sha"},
                "environment": {
                    "type": "identifier",
                    "required": False,
                    "default": "dev",
                },
            },
            "steps": [
                {
                    "id": "collect",
                    "kind": "admitted_collection",
                    "depends_on": [],
                    "source": {
                        "kind": "collected",
                        "repository_id": {"ref": "input", "name": "repository"},
                        "commit_sha": {"ref": "input", "name": "commit"},
                        "profile_digest": profile,
                    },
                }
            ],
        }
        ids = self.publish_fixture(definition)
        registry = RegistryContract(
            profiles=(
                ProfileContract(
                    digest=profile,
                    tool="opentofu",
                    authorization_kinds=("exact_plan",),
                ),
            )
        )
        supplied = {"repository": "synthetic-repo", "commit": "b" * 40}
        with self.assertRaises(LifecycleError):
            self.export(ids, supplied)
        exported = self.export(ids, supplied, registry_contract=registry)
        supplied["commit"] = "c" * 40
        self.assertEqual(exported.snapshot.sources[0].commit_sha, "b" * 40)
        self.assertEqual(exported.snapshot.inputs["environment"], "dev")
        self.assertEqual(exported.snapshot.environment, "dev")
        for invalid in ("main", "b" * 39, "B" * 40, None):
            with self.subTest(commit=invalid):
                supplied["commit"] = invalid
                with self.assertRaises(LifecycleError):
                    self.export(ids, supplied, registry_contract=registry)
        uploaded = {
            "id": "upload",
            "kind": "uploaded_intake",
            "depends_on": [],
            "source": {"kind": "uploaded"},
        }
        mixed = copy.deepcopy(definition)
        mixed["steps"].append(uploaded)
        exported_mixed = self.export(
            self.publish_fixture(mixed),
            {"repository": "synthetic-repo", "commit": "b" * 40},
            registry_contract=registry,
        )
        self.assertEqual(
            [item.kind for item in exported_mixed.snapshot.sources],
            ["collected", "uploaded"],
        )

    def test_audit_contains_digests_and_actual_scope_without_inputs(self):
        self.enable()
        ids = self.publish_fixture(workspace_id=None)
        exported = self.export(ids)
        with self.factory() as session:
            events = list(session.scalars(select(InfraAutomationAudit)))
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event.event_type, "snapshot_exported")
            self.assertEqual(event.workspace_id, 100)
            self.assertEqual(event.actor_principal_id, "human-a")
            self.assertEqual(event.before_digest, exported.definition_digest)
            self.assertEqual(event.after_digest, exported.digest)
            self.assertNotIn("original", event.reason)

    def test_synthetic_nonhuman_principal_cannot_export(self):
        self.enable()
        ids = self.publish_fixture()
        from services import infra_automation_support as support

        original_scope = support.scope

        def synthetic(*args, **kwargs):
            from dataclasses import replace

            grant = original_scope(*args, **kwargs)
            principal = grant.principal.model_copy(
                update={
                    "principal_type": "service",
                    "credential_audience": "service-request-v1",
                }
            )
            return replace(grant, principal=principal)

        with patch.object(support, "scope", side_effect=synthetic):
            with self.assertRaises(authorization.TrustedAuthorizationError):
                self.export(ids)

    def test_revision_digest_and_semantics_are_rechecked_without_modifying_history(
        self,
    ):
        self.enable()
        ids = self.publish_fixture()
        from types import SimpleNamespace

        with self.factory() as session:
            revision = repository.get_revision(session, ids[1])
            record = {
                key: getattr(revision, key)
                for key in (
                    "id",
                    "workflow_id",
                    "project_id",
                    "workspace_id",
                    "revision_number",
                    "canonical_definition",
                    "digest",
                )
            }
        altered = json.loads(record["canonical_definition"])
        altered["steps"][0]["depends_on"] = ["missing"]
        bad_graph = canonical(altered)
        variants = [
            {"digest": "sha256:" + "f" * 64},
            {"canonical_definition": bad_graph, "digest": digest(bad_graph)},
            {"canonical_definition": b"{}", "digest": digest(b"{}")},
        ]
        for changes in variants:
            with self.subTest(changes=changes):
                forged = SimpleNamespace(**(record | changes))
                with patch.object(repository, "get_revision", return_value=forged):
                    with self.assertRaises(LifecycleError) as caught:
                        self.export(ids)
                self.assertEqual(caught.exception.status_code, 503)
        valid = self.export(ids)
        self.assertEqual(valid.definition_digest, record["digest"])

    def test_membership_is_live_and_snapshot_oversize_rolls_back_audit(self):
        self.enable()
        ids = self.publish_fixture()
        self.member("read-only")
        with self.assertRaises(authorization.TrustedAuthorizationError):
            self.export(ids)
        self.member("admin")
        from services import infra_automation_support as support

        original_canonical = support.canonical

        def oversized_snapshot(value):
            if isinstance(value, dict) and "authority" in value:
                return b"x" * (512 * 1024 + 1)
            return original_canonical(value)

        with patch.object(support, "canonical", side_effect=oversized_snapshot):
            with self.assertRaises(LifecycleError) as caught:
                self.export(ids)
        self.assertEqual(caught.exception.status_code, 429)
        with self.factory() as session:
            self.assertEqual(list(session.scalars(select(InfraAutomationAudit))), [])
