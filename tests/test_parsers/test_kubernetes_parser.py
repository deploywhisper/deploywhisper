"""Tests for Kubernetes parser normalization."""

from __future__ import annotations

import unittest

from parsers.kubernetes_parser import parse_kubernetes


class KubernetesParserTests(unittest.TestCase):
    def test_parse_kubernetes_marks_standalone_manifest_as_apply_unknown_delta(
        self,
    ) -> None:
        raw = b"""apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: etcd-sc-backup
provisioner: efs.csi.aws.com
"""

        changes = parse_kubernetes("etcd-sc-backup.yaml", raw)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].action, "apply")
        self.assertIn("previous cluster state is unknown", changes[0].summary)

    def test_parse_kubernetes_includes_namespace_when_manifest_declares_one(
        self,
    ) -> None:
        raw = b"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: payments
"""

        changes = parse_kubernetes("deployment.yaml", raw)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].resource_id, "Deployment/payments/api")

    def test_parse_kubernetes_leaves_namespace_less_manifest_unscoped(
        self,
    ) -> None:
        raw = b"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
"""

        changes = parse_kubernetes("deployment.yaml", raw)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].resource_id, "Deployment/api")
        self.assertNotIn("resource_aliases", changes[0].metadata)


if __name__ == "__main__":
    unittest.main()
