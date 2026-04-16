"""Tests for Kubernetes parser normalization."""

from __future__ import annotations

import unittest

from parsers.kubernetes_parser import parse_kubernetes


class KubernetesParserTests(unittest.TestCase):
    def test_parse_kubernetes_marks_standalone_manifest_as_apply_unknown_delta(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
