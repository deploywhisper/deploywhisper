"""Tests for evidence extraction from parser-derived normalized changes."""

from __future__ import annotations

import unittest

from evidence.extractor import EvidenceExtractor, extract_batch_evidence
from parsers.ansible_parser import parse_ansible
from parsers.base import ParseBatchResult, ParsedFileResult
from parsers.cloudformation_parser import parse_cloudformation
from parsers.jenkins_parser import parse_jenkins
from parsers.kubernetes_parser import parse_kubernetes
from parsers.terraform_parser import parse_terraform


SCENARIOS = [
    {
        "label": "terraform security group modify",
        "parser": parse_terraform,
        "file_name": "plan.json",
        "raw": b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
        "expected_source_ref": "terraform://plan.json#aws_security_group.main?action=modify",
        "expected_severity": "high",
    },
    {
        "label": "terraform iam create",
        "parser": parse_terraform,
        "file_name": "identity.json",
        "raw": b'{"resource_changes": [{"address": "aws_iam_role.deployer", "change": {"actions": ["create"]}}]}',
        "expected_source_ref": "terraform://identity.json#aws_iam_role.deployer?action=create",
        "expected_severity": "high",
    },
    {
        "label": "terraform module modify",
        "parser": parse_terraform,
        "file_name": "network.tf",
        "raw": b'module "network" {\n  source = "./modules/network"\n}\n',
        "expected_source_ref": "terraform://network.tf#module.network?action=modify",
        "expected_severity": "medium",
    },
    {
        "label": "terraform destroy compute",
        "parser": parse_terraform,
        "file_name": "compute.json",
        "raw": b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["delete"]}}]}',
        "expected_source_ref": "terraform://compute.json#aws_instance.web?action=destroy",
        "expected_severity": "high",
    },
    {
        "label": "terraform replace compute",
        "parser": parse_terraform,
        "file_name": "replace.json",
        "raw": b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["delete", "create"], "replace_paths": [["ami"]]}}]}',
        "expected_source_ref": "terraform://replace.json#aws_instance.web?action=replace",
        "expected_severity": "high",
    },
    {
        "label": "kubernetes service apply",
        "parser": parse_kubernetes,
        "file_name": "service.yaml",
        "raw": b"apiVersion: v1\nkind: Service\nmetadata:\n  name: api\n",
        "expected_source_ref": "kubernetes://service.yaml#Service/api?action=apply",
        "expected_severity": "high",
    },
    {
        "label": "kubernetes deployment apply",
        "parser": parse_kubernetes,
        "file_name": "deployment.yaml",
        "raw": b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n",
        "expected_source_ref": "kubernetes://deployment.yaml#Deployment/api?action=apply",
        "expected_severity": "medium",
    },
    {
        "label": "kubernetes namespace apply",
        "parser": parse_kubernetes,
        "file_name": "namespace.yaml",
        "raw": b"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: payments\n",
        "expected_source_ref": "kubernetes://namespace.yaml#Namespace/payments?action=apply",
        "expected_severity": "high",
    },
    {
        "label": "kubernetes configmap apply",
        "parser": parse_kubernetes,
        "file_name": "configmap.yaml",
        "raw": b"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: app-settings\n",
        "expected_source_ref": "kubernetes://configmap.yaml#ConfigMap/app-settings?action=apply",
        "expected_severity": "low",
    },
    {
        "label": "ansible firewall task",
        "parser": parse_ansible,
        "file_name": "firewall.yml",
        "raw": b"hosts: app\ntasks:\n  - name: Update firewall rules\n    ansible.builtin.command: ufw allow 443/tcp\n",
        "expected_source_ref": "ansible://firewall.yml#Update%20firewall%20rules?action=modify",
        "expected_severity": "high",
    },
    {
        "label": "ansible deploy task",
        "parser": parse_ansible,
        "file_name": "deploy.yml",
        "raw": b"hosts: app\ntasks:\n  - name: Deploy api\n    ansible.builtin.command: ./deploy-api.sh\n",
        "expected_source_ref": "ansible://deploy.yml#Deploy%20api?action=modify",
        "expected_severity": "medium",
    },
    {
        "label": "ansible restart task",
        "parser": parse_ansible,
        "file_name": "restart.yml",
        "raw": b"hosts: app\ntasks:\n  - name: Restart nginx\n    ansible.builtin.service:\n      name: nginx\n      state: restarted\n",
        "expected_source_ref": "ansible://restart.yml#Restart%20nginx?action=modify",
        "expected_severity": "medium",
    },
    {
        "label": "ansible template task",
        "parser": parse_ansible,
        "file_name": "template.yml",
        "raw": b"hosts: app\ntasks:\n  - name: Render config template\n    ansible.builtin.template:\n      src: app.conf.j2\n      dest: /etc/app.conf\n",
        "expected_source_ref": "ansible://template.yml#Render%20config%20template?action=modify",
        "expected_severity": "medium",
    },
    {
        "label": "jenkins deploy stage",
        "parser": parse_jenkins,
        "file_name": "Jenkinsfile",
        "raw": b"pipeline { stages { stage('Deploy Prod') { steps { echo 'deploy' } } } }",
        "expected_source_ref": "jenkins://Jenkinsfile#stage/Deploy%20Prod?action=modify",
        "expected_severity": "medium",
    },
    {
        "label": "jenkins security scan stage",
        "parser": parse_jenkins,
        "file_name": "Jenkinsfile",
        "raw": b"pipeline { stages { stage('Security Scan') { steps { echo 'scan' } } } }",
        "expected_source_ref": "jenkins://Jenkinsfile#stage/Security%20Scan?action=modify",
        "expected_severity": "medium",
    },
    {
        "label": "jenkins build stage",
        "parser": parse_jenkins,
        "file_name": "Jenkinsfile",
        "raw": b"pipeline { stages { stage('Build') { steps { echo 'build' } } } }",
        "expected_source_ref": "jenkins://Jenkinsfile#stage/Build?action=modify",
        "expected_severity": "medium",
    },
    {
        "label": "jenkins pipeline fallback",
        "parser": parse_jenkins,
        "file_name": "Jenkinsfile",
        "raw": b"pipeline { agent any }",
        "expected_source_ref": "jenkins://Jenkinsfile#pipeline?action=modify",
        "expected_severity": "medium",
    },
    {
        "label": "cloudformation security group resource",
        "parser": parse_cloudformation,
        "file_name": "stack.yaml",
        "raw": b"Resources:\n  AppSecurityGroup:\n    Type: AWS::EC2::SecurityGroup\n",
        "expected_source_ref": "cloudformation://stack.yaml#resource/AppSecurityGroup?action=apply",
        "expected_severity": "high",
    },
    {
        "label": "cloudformation vpc resource",
        "parser": parse_cloudformation,
        "file_name": "stack.yaml",
        "raw": b"Resources:\n  SharedVpc:\n    Type: AWS::EC2::VPC\n",
        "expected_source_ref": "cloudformation://stack.yaml#resource/SharedVpc?action=apply",
        "expected_severity": "high",
    },
    {
        "label": "cloudformation bucket resource",
        "parser": parse_cloudformation,
        "file_name": "stack.yaml",
        "raw": b"Resources:\n  AppBucket:\n    Type: AWS::S3::Bucket\n",
        "expected_source_ref": "cloudformation://stack.yaml#resource/AppBucket?action=apply",
        "expected_severity": "medium",
    },
    {
        "label": "cloudformation lambda resource",
        "parser": parse_cloudformation,
        "file_name": "stack.yaml",
        "raw": b"Resources:\n  ApiFunction:\n    Type: AWS::Lambda::Function\n",
        "expected_source_ref": "cloudformation://stack.yaml#resource/ApiFunction?action=apply",
        "expected_severity": "medium",
    },
]


class EvidenceExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = EvidenceExtractor()

    def test_extract_covers_mutating_parser_fixture_scenarios(self) -> None:
        self.assertEqual(len(SCENARIOS), 21)

        observed_tools: set[str] = set()

        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario["label"]):
                changes = scenario["parser"](scenario["file_name"], scenario["raw"])

                self.assertEqual(len(changes), 1)
                change = changes[0]
                observed_tools.add(change.tool)

                evidence_items = self.extractor.extract(change)
                self.assertEqual(len(evidence_items), 1)

                evidence_item = evidence_items[0]
                self.assertEqual(evidence_item.source_type, "artifact")
                self.assertEqual(
                    evidence_item.source_ref, scenario["expected_source_ref"]
                )
                self.assertEqual(evidence_item.summary, change.summary)
                self.assertEqual(
                    evidence_item.severity_hint, scenario["expected_severity"]
                )
                self.assertTrue(evidence_item.deterministic)
                self.assertEqual(evidence_item.analysis_id, 0)
                self.assertEqual(
                    evidence_item.finding_id, f"pending:{change.change_id}"
                )
                self.assertEqual(evidence_item.related_change_ids, [change.change_id])

        self.assertEqual(
            observed_tools,
            {"terraform", "kubernetes", "ansible", "jenkins", "cloudformation"},
        )

    def test_extract_skips_non_mutating_terraform_plan_changes(self) -> None:
        for file_name, raw in (
            ("empty-plan.json", b'{"resource_changes": []}'),
            (
                "data.json",
                b'{"resource_changes": [{"address": "data.aws_ami.latest", "mode": "data", "change": {"actions": ["read"]}}]}',
            ),
        ):
            with self.subTest(file_name=file_name):
                changes = parse_terraform(file_name, raw)

                self.assertEqual(len(changes), 1)
                self.assertEqual(self.extractor.extract(changes[0]), [])

    def test_extract_batch_evidence_filters_non_mutating_terraform_changes(
        self,
    ) -> None:
        changes = parse_terraform(
            "mixed-plan.json",
            (
                b'{"resource_changes": ['
                b'{"address": "aws_security_group.unchanged", "change": {"actions": ["no-op"]}},'
                b'{"address": "data.aws_ami.latest", "mode": "data", "change": {"actions": ["read"]}},'
                b'{"address": "aws_security_group.updated", "change": {"actions": ["update"]}}'
                b"]}"
            ),
        )
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="mixed-plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=changes,
                )
            ]
        )

        evidence_items = extract_batch_evidence(batch)

        self.assertEqual(
            [item.source_ref for item in evidence_items],
            [
                "terraform://mixed-plan.json#aws_security_group.updated?action=modify",
            ],
        )

    def test_extract_batch_evidence_preserves_duplicate_parser_changes(self) -> None:
        duplicate_changes = parse_ansible(
            "duplicate.yml",
            (
                b"hosts: app\n"
                b"tasks:\n"
                b"  - name: Restart nginx\n"
                b"    ansible.builtin.service:\n"
                b"      name: nginx\n"
                b"      state: restarted\n"
                b"  - name: Restart nginx\n"
                b"    ansible.builtin.service:\n"
                b"      name: nginx\n"
                b"      state: restarted\n"
            ),
        )
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="duplicate.yml",
                    tool="ansible",
                    status="parsed",
                    changes=duplicate_changes,
                ),
                ParsedFileResult(
                    file_name="broken.tf",
                    tool="terraform",
                    status="failed",
                    changes=[],
                ),
            ]
        )

        evidence_items = extract_batch_evidence(batch)

        self.assertEqual(len(evidence_items), 2)
        self.assertEqual(
            [item.source_ref for item in evidence_items],
            [
                "ansible://duplicate.yml#Restart%20nginx?action=modify",
                "ansible://duplicate.yml#Restart%20nginx?action=modify",
            ],
        )
        self.assertEqual(len({item.evidence_id for item in evidence_items}), 2)
        self.assertEqual(
            len({item.related_change_ids[0] for item in evidence_items}),
            2,
        )

    def test_extract_batch_evidence_identifies_review_context_fields(self) -> None:
        changes = parse_terraform(
            "prod/network/plan.json",
            b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
        )
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="prod/network/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=changes,
                )
            ]
        )

        evidence_items = extract_batch_evidence(
            batch,
            project_id=12,
            project_key="platform",
            workspace_id=34,
            workspace_key="prod",
        )

        self.assertEqual(len(evidence_items), 1)
        evidence_item = evidence_items[0]
        self.assertEqual(evidence_item.artifact, "prod/network/plan.json")
        self.assertEqual(
            evidence_item.location,
            "prod/network/plan.json#aws_security_group.main",
        )
        self.assertEqual(evidence_item.resource, "aws_security_group.main")
        self.assertEqual(evidence_item.operation, "modify")
        self.assertEqual(evidence_item.project_id, 12)
        self.assertEqual(evidence_item.project_key, "platform")
        self.assertEqual(evidence_item.workspace_id, 34)
        self.assertEqual(evidence_item.workspace_key, "prod")
        self.assertEqual(evidence_item.source_kind, "artifact")
        self.assertEqual(evidence_item.determinism_level, "deterministic")
        self.assertEqual(evidence_item.redaction_status, "none")


if __name__ == "__main__":
    unittest.main()
