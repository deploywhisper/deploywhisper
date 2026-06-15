"""Tests for blast radius analysis."""

from __future__ import annotations

from datetime import UTC, datetime
import unittest

from analysis.blast_radius import BlastRadiusResult, compute_blast_radius
from parsers.base import UnifiedChange


class BlastRadiusTests(unittest.TestCase):
    def test_compute_blast_radius_returns_direct_and_transitive_impact(self) -> None:
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "database",
                    "label": "Database",
                    "resource_keys": ["aws_security_group.main"],
                    "downstream": ["api"],
                    "owners": ["sre"],
                },
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                    "owner": "payments",
                },
            ],
        }
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a security group.",
            )
        ]
        result = compute_blast_radius(changes, topology)
        self.assertEqual(result.direct_count, 1)
        self.assertEqual(result.transitive_count, 1)
        self.assertIsNone(result.warning)
        self.assertEqual(result.context_source["type"], "custom")
        self.assertEqual(result.context_source["ref"], "topology.json")
        self.assertEqual(result.freshness["updated_at"], "2026-06-08T12:00:00Z")
        self.assertEqual(result.context_state, "current")
        database_node = next(
            node for node in result.affected if node.service_id == "database"
        )
        api_node = next(node for node in result.affected if node.service_id == "api")
        self.assertEqual(database_node.dependencies, [])
        self.assertEqual(database_node.owners, ["sre"])
        self.assertEqual(api_node.dependencies, ["database"])
        self.assertEqual(api_node.owners, ["payments"])

    def test_compute_blast_radius_calculates_freshness_age_with_injected_clock(
        self,
    ) -> None:
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ],
        }
        changes = [
            UnifiedChange(
                source_file="manifest.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            )
        ]

        result = compute_blast_radius(
            changes, topology, now=datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
        )

        self.assertEqual(result.freshness["age_days"], 1)

    def test_compute_blast_radius_prefers_exact_match_over_legacy_alias(
        self,
    ) -> None:
        topology = {
            "services": [
                {
                    "id": "api-payments",
                    "label": "Payments API",
                    "resource_keys": ["Deployment/payments/api"],
                    "downstream": [],
                },
                {
                    "id": "api-legacy",
                    "label": "Legacy API",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                },
            ]
        }
        changes = [
            UnifiedChange(
                source_file="deployment.yaml",
                tool="kubernetes",
                resource_id="Deployment/payments/api",
                action="modify",
                summary="Deployment changed.",
                metadata={"resource_aliases": ["Deployment/api"]},
            )
        ]

        result = compute_blast_radius(changes, topology)

        self.assertEqual(result.direct_count, 1)
        self.assertEqual(
            [node.service_id for node in result.affected], ["api-payments"]
        )

    def test_compute_blast_radius_ignores_ambiguous_legacy_alias(
        self,
    ) -> None:
        topology = {
            "services": [
                {
                    "id": "api-a",
                    "label": "API A",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                },
                {
                    "id": "api-b",
                    "label": "API B",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                },
            ]
        }
        changes = [
            UnifiedChange(
                source_file="deployment.yaml",
                tool="kubernetes",
                resource_id="Deployment/payments/api",
                action="modify",
                summary="Deployment changed.",
                metadata={"resource_aliases": ["Deployment/api"]},
            )
        ]

        result = compute_blast_radius(changes, topology)

        self.assertEqual(result.direct_count, 0)
        self.assertEqual(result.affected, [])
        self.assertEqual(result.unmatched_resources, ["Deployment/payments/api"])

    def test_compute_blast_radius_drops_malformed_owner_values(self) -> None:
        topology = {
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                    "owner": {"team": "payments"},
                    "owners": ["sre", {"team": "security"}],
                }
            ]
        }
        changes = [
            UnifiedChange(
                source_file="manifest.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            )
        ]

        result = compute_blast_radius(changes, topology)

        self.assertEqual(result.affected[0].owners, ["sre"])

    def test_compute_blast_radius_marks_missing_topology_metadata_incomplete(
        self,
    ) -> None:
        topology = {
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ]
        }
        changes = [
            UnifiedChange(
                source_file="manifest.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            )
        ]

        result = compute_blast_radius(changes, topology)

        self.assertEqual(result.context_state, "incomplete")
        self.assertIn("missing_topology_source", result.context_limitations)
        self.assertIn("missing_topology_freshness", result.context_limitations)

    def test_compute_blast_radius_marks_invalid_topology_freshness_incomplete(
        self,
    ) -> None:
        topology = {
            "updated_at": "not-a-date",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ],
        }
        changes = [
            UnifiedChange(
                source_file="manifest.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            )
        ]

        result = compute_blast_radius(changes, topology)

        self.assertEqual(result.context_state, "incomplete")
        self.assertIn("invalid_topology_freshness", result.context_limitations)

    def test_compute_blast_radius_marks_future_topology_freshness_incomplete(
        self,
    ) -> None:
        topology = {
            "updated_at": "2099-01-01T00:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ],
        }
        changes = [
            UnifiedChange(
                source_file="manifest.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            )
        ]

        result = compute_blast_radius(
            changes, topology, now=datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
        )

        self.assertEqual(result.context_state, "incomplete")
        self.assertEqual(result.freshness["age_days"], None)
        self.assertIn("invalid_topology_freshness", result.context_limitations)

    def test_compute_blast_radius_marks_partial_source_metadata_incomplete(
        self,
    ) -> None:
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {"import": {"source_type": "custom"}},
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ],
        }
        changes = [
            UnifiedChange(
                source_file="manifest.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            )
        ]

        result = compute_blast_radius(changes, topology)

        self.assertEqual(result.context_state, "incomplete")
        self.assertEqual(result.context_source, {"type": "custom", "ref": None})
        self.assertIn("missing_topology_source", result.context_limitations)

    def test_compute_blast_radius_marks_non_scalar_source_metadata_incomplete(
        self,
    ) -> None:
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": {"kind": "custom"},
                    "source_ref": "topology.json",
                }
            },
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ],
        }
        changes = [
            UnifiedChange(
                source_file="manifest.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            )
        ]

        result = compute_blast_radius(changes, topology)

        self.assertEqual(result.context_state, "incomplete")
        self.assertEqual(result.context_source, {"type": None, "ref": "topology.json"})
        self.assertIn("invalid_topology_source", result.context_limitations)
        self.assertIn("missing_topology_source", result.context_limitations)

    def test_compute_blast_radius_normalizes_downstream_service_ids(self) -> None:
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "database",
                    "label": "Database",
                    "resource_keys": ["aws_security_group.main"],
                    "downstream": [" api "],
                },
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": [],
                    "downstream": [],
                },
            ],
        }
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a security group.",
            )
        ]

        result = compute_blast_radius(changes, topology)

        self.assertEqual(
            [node.service_id for node in result.affected], ["database", "api"]
        )
        api_node = next(node for node in result.affected if node.service_id == "api")
        self.assertEqual(api_node.dependencies, ["database"])

    def test_compute_blast_radius_deduplicates_downstream_dependencies(self) -> None:
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "database",
                    "label": "Database",
                    "resource_keys": ["aws_security_group.main"],
                    "downstream": ["api", " api ", "api"],
                },
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": [],
                    "downstream": [],
                },
            ],
        }
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a security group.",
            )
        ]

        result = compute_blast_radius(changes, topology)

        api_node = next(node for node in result.affected if node.service_id == "api")
        self.assertEqual(api_node.dependencies, ["database"])

    def test_legacy_blast_radius_payload_drops_malformed_additive_fields(self) -> None:
        legacy_result = BlastRadiusResult.model_validate(
            {
                "affected": [
                    {
                        "service_id": "api",
                        "label": "API Service",
                        "depth": 0,
                        "dependencies": None,
                        "owners": None,
                    }
                ],
                "direct_count": 1,
                "transitive_count": 0,
                "warning": None,
                "unmatched_resources": [],
                "context_source": "legacy",
                "freshness": "unknown",
                "context_limitations": "legacy",
            }
        )

        self.assertEqual(legacy_result.affected[0].dependencies, [])
        self.assertEqual(legacy_result.affected[0].owners, [])
        self.assertEqual(legacy_result.context_source, {"type": None, "ref": None})
        self.assertEqual(
            legacy_result.freshness, {"updated_at": None, "age_days": None}
        )
        self.assertEqual(legacy_result.context_limitations, [])

    def test_legacy_blast_radius_payload_drops_malformed_nested_additive_fields(
        self,
    ) -> None:
        legacy_result = BlastRadiusResult.model_validate(
            {
                "affected": [
                    {
                        "service_id": "api",
                        "label": "API Service",
                        "depth": 0,
                    }
                ],
                "direct_count": 1,
                "transitive_count": 0,
                "warning": None,
                "unmatched_resources": [],
                "context_source": {"type": {"kind": "custom"}, "ref": "topology.json"},
                "freshness": {"updated_at": {"bad": "value"}, "age_days": []},
                "context_state": {"state": "missing"},
            }
        )

        self.assertEqual(
            legacy_result.context_source, {"type": None, "ref": "topology.json"}
        )
        self.assertEqual(
            legacy_result.freshness, {"updated_at": None, "age_days": None}
        )
        self.assertEqual(legacy_result.context_state, "unknown")

    def test_legacy_blast_radius_payload_has_unknown_context_state(self) -> None:
        legacy_result = BlastRadiusResult.model_validate(
            {
                "affected": [
                    {
                        "service_id": "api",
                        "label": "API Service",
                        "depth": 0,
                    }
                ],
                "direct_count": 1,
                "transitive_count": 0,
                "warning": None,
                "unmatched_resources": [],
            }
        )

        self.assertEqual(legacy_result.context_state, "unknown")
        self.assertEqual(legacy_result.context_limitations, [])

    def test_legacy_blast_radius_payload_normalizes_null_context_state(
        self,
    ) -> None:
        legacy_result = BlastRadiusResult.model_validate(
            {
                "affected": [],
                "direct_count": 0,
                "transitive_count": 0,
                "warning": None,
                "unmatched_resources": [],
                "context_state": None,
            }
        )

        self.assertEqual(legacy_result.context_state, "unknown")

    def test_compute_blast_radius_warns_when_no_matches_found(self) -> None:
        topology = {
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ]
        }
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a security group.",
            )
        ]
        result = compute_blast_radius(changes, topology)
        self.assertTrue(result.warning)
        self.assertIn("no topology mapping found", result.warning)
        self.assertEqual(result.unmatched_resources, ["aws_security_group.main"])
        self.assertEqual(result.context_state, "incomplete")
        self.assertIn("missing_resource_mapping", result.context_limitations)

    def test_compute_blast_radius_marks_missing_topology_context(self) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a security group.",
            )
        ]

        result = compute_blast_radius(
            changes,
            None,
            "Blast radius may be incomplete — service topology is not configured.",
        )

        self.assertEqual(result.context_state, "missing")
        self.assertEqual(result.context_source["type"], None)
        self.assertIn("missing_topology", result.context_limitations)

    def test_compute_blast_radius_marks_stale_topology_context(self) -> None:
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ],
        }
        changes = [
            UnifiedChange(
                source_file="manifest.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            )
        ]

        result = compute_blast_radius(
            changes, topology, "Topology is stale: last updated more than 30 days ago."
        )

        self.assertEqual(result.context_state, "stale")
        self.assertIn("stale_topology", result.context_limitations)

    def test_compute_blast_radius_marks_conflicting_topology_context(self) -> None:
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ],
        }
        changes = [
            UnifiedChange(
                source_file="manifest.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            )
        ]

        result = compute_blast_radius(
            changes, topology, "Topology validation failed because duplicate ids exist."
        )

        self.assertEqual(result.context_state, "conflicting")
        self.assertIn("conflicting_topology", result.context_limitations)

    def test_compute_blast_radius_ignores_noop_and_read_changes(self) -> None:
        topology = {
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": [
                        "aws_security_group.main",
                        "data.aws_ami.latest",
                    ],
                    "downstream": ["worker"],
                },
                {
                    "id": "worker",
                    "label": "Worker",
                    "resource_keys": [],
                    "downstream": [],
                },
            ]
        }
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="no-op",
                summary="Terraform resource aws_security_group.main has no planned changes.",
            ),
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="data.aws_ami.latest",
                action="read",
                summary="Terraform resource data.aws_ami.latest marked for read.",
            ),
        ]

        result = compute_blast_radius(changes, topology)

        self.assertEqual(result.affected, [])
        self.assertEqual(result.direct_count, 0)
        self.assertEqual(result.transitive_count, 0)
        self.assertEqual(result.unmatched_resources, [])
        self.assertIsNone(result.warning)
