"""Tests for ownership context helpers."""

from __future__ import annotations

import unittest

from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange
from services.ownership_service import (
    CodeownersSource,
    OWNERSHIP_CONTEXT_TODO,
    _pattern_matches,
    build_ownership_context,
    uploaded_codeowners_sources,
)
from services.intake_service import uniquify_artifact_names


class OwnershipServiceTests(unittest.TestCase):
    def _codeowners(self, source_ref: str, content: str) -> CodeownersSource:
        return CodeownersSource(source_ref=source_ref, content=content)

    def test_codeowners_path_patterns_follow_documented_boundaries(self) -> None:
        self.assertTrue(_pattern_matches("/*.md", "README.md"))
        self.assertFalse(_pattern_matches("/*.md", "docs/readme.md"))
        self.assertTrue(_pattern_matches("/docs/*.md", "docs/readme.md"))
        self.assertFalse(_pattern_matches("/docs/*.md", "docs/sub/readme.md"))
        self.assertTrue(_pattern_matches("docs/readme.md", "docs/readme.md"))
        self.assertFalse(
            _pattern_matches("docs/readme.md", "docs/readme.md/config.yaml")
        )
        self.assertFalse(_pattern_matches("docs/readme.md", "services/docs/readme.md"))
        self.assertTrue(_pattern_matches("docs", "docs/readme.md"))
        self.assertTrue(_pattern_matches("apps/", "services/apps/config.yaml"))
        self.assertFalse(_pattern_matches("/apps/", "services/apps/config.yaml"))
        self.assertTrue(_pattern_matches("docs/**/README.md", "docs/README.md"))
        self.assertTrue(
            _pattern_matches("docs/**/README.md", "docs/services/README.md")
        )
        self.assertTrue(_pattern_matches("[Dd]ockerfile", "Dockerfile"))
        self.assertFalse(_pattern_matches("[Dd]ockerfile", "docs/Dockerfile/app.yaml"))

    def test_codeowners_escaped_space_patterns_match_file_paths(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="docs/My File.md",
                    tool="terraform",
                    status="failed",
                    changes=[],
                )
            ]
        )

        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(
                self._codeowners("CODEOWNERS", "docs/My\\ File.md @docs-team"),
            ),
        )

        self.assertEqual(context.owner_signals[0].subject, "docs/My File.md")
        self.assertEqual(context.owner_signals[0].owners, ["@docs-team"])
        self.assertEqual(context.owner_signals[0].matched_pattern, "docs/My File.md")
        self.assertEqual(context.context_todos, ())

    def test_codeowners_escaped_hash_patterns_match_file_paths(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="docs/#runbook.md",
                    tool="terraform",
                    status="failed",
                    changes=[],
                )
            ]
        )

        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(
                self._codeowners("CODEOWNERS", "docs/\\#runbook.md @docs-team"),
            ),
        )

        self.assertEqual(context.owner_signals[0].subject, "docs/#runbook.md")
        self.assertEqual(context.owner_signals[0].owners, ["@docs-team"])
        self.assertEqual(context.context_todos, ())

    def test_codeowners_utf8_bom_does_not_break_first_rule(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="services/payments/plan.json",
                    tool="terraform",
                    status="failed",
                    changes=[],
                )
            ]
        )
        sources = uploaded_codeowners_sources(
            [
                (
                    "CODEOWNERS",
                    "\ufeff/services/payments/ @payments-sre".encode("utf-8"),
                )
            ]
        )

        context = build_ownership_context(parse_batch, codeowners_sources=sources)

        self.assertEqual(context.owner_signals[0].owners, ["@payments-sre"])
        self.assertEqual(context.context_todos, ())

    def test_long_team_slug_owner_token_is_accepted(self) -> None:
        long_team = "@platform/" + ("release-approval-team-" * 3).rstrip("-")
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="services/payments/plan.json",
                    tool="terraform",
                    status="failed",
                    changes=[],
                )
            ]
        )

        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(
                self._codeowners("CODEOWNERS", f"/services/payments/ {long_team}"),
            ),
        )

        self.assertEqual(context.owner_signals[0].owners, [long_team])
        self.assertEqual(context.context_todos, ())

    def test_first_uploaded_codeowners_source_wins_and_inline_comments_are_ignored(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="services/payments/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="services/payments/plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.payments",
                            action="modify",
                            summary="Terraform changed a payments security group.",
                        )
                    ],
                )
            ]
        )
        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(
                self._codeowners(
                    ".github/CODEOWNERS",
                    "\n".join(
                        [
                            "/services/payments/ @payments-sre # primary owner",
                            "*.tf @terraform-owner",
                        ]
                    ),
                ),
                self._codeowners("CODEOWNERS", "/services/payments/ @wrong-owner"),
            ),
        )

        self.assertEqual(context.owner_signals[0].owners, ["@payments-sre"])
        self.assertEqual(context.owner_signals[0].source_ref, ".github/CODEOWNERS")

    def test_uploaded_codeowners_sources_follow_lookup_order(self) -> None:
        sources = uploaded_codeowners_sources(
            [
                ("CODEOWNERS", "* @root"),
                ("docs/CODEOWNERS", "* @docs"),
                (".github/CODEOWNERS", "* @github"),
            ]
        )

        self.assertEqual(
            sources,
            (CodeownersSource(source_ref=".github/CODEOWNERS", content="* @github"),),
        )

    def test_traversal_normalized_codeowners_is_not_trusted(self) -> None:
        files = uniquify_artifact_names(
            [
                ("repo/../CODEOWNERS", b"* @spoofed-owner"),
                ("repo/services/payments/plan.json", b"{}"),
            ]
        )

        sources = uploaded_codeowners_sources(files)

        self.assertEqual(sources, ())

    def test_reserved_unsafe_prefix_codeowners_is_not_trusted(self) -> None:
        files = uniquify_artifact_names(
            [
                ("__unsafe_path__/CODEOWNERS", b"* @spoofed-owner"),
                ("repo/services/payments/plan.json", b"{}"),
            ]
        )

        sources = uploaded_codeowners_sources(files)

        self.assertEqual(sources, ())

    def test_reserved_external_prefix_codeowners_is_not_trusted(self) -> None:
        sources = uploaded_codeowners_sources(
            [
                ("__external_path__/CODEOWNERS", b"* @spoofed-owner"),
                ("repo/services/payments/plan.json", b"{}"),
            ]
        )

        self.assertEqual(sources, ())

    def test_prefixed_docs_codeowners_keeps_docs_lookup_semantics(self) -> None:
        sources = uploaded_codeowners_sources(
            [
                ("repo/docs/CODEOWNERS", b"* @docs-owner"),
            ]
        )

        self.assertEqual(
            sources,
            (
                CodeownersSource(
                    source_ref="repo/docs/CODEOWNERS",
                    content="* @docs-owner",
                    root_prefix="repo",
                ),
            ),
        )

    def test_uploaded_codeowners_sources_detect_prefixed_repository_root(self) -> None:
        sources = uploaded_codeowners_sources(
            [
                ("repo/CODEOWNERS", "* @root"),
                ("repo/.github/CODEOWNERS", "* @github"),
            ]
        )

        self.assertEqual(
            sources,
            (
                CodeownersSource(
                    source_ref="repo/.github/CODEOWNERS",
                    content="* @github",
                    root_prefix="repo",
                ),
            ),
        )

    def test_prefixed_codeowners_source_matches_files_under_same_root(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="repo/services/payments/plan.json",
                    tool="terraform",
                    status="failed",
                    changes=[],
                ),
                ParsedFileResult(
                    file_name="other/services/payments/plan.json",
                    tool="terraform",
                    status="failed",
                    changes=[],
                ),
            ]
        )

        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(
                CodeownersSource(
                    source_ref="repo/.github/CODEOWNERS",
                    content="/services/payments/ @payments-sre",
                    root_prefix="repo",
                ),
            ),
        )

        self.assertEqual(len(context.owner_signals), 1)
        self.assertEqual(
            context.owner_signals[0].subject, "repo/services/payments/plan.json"
        )
        self.assertEqual(context.owner_signals[0].owners, ["@payments-sre"])
        self.assertIn("other/services/payments/plan.json", context.unmapped_subjects)

    def test_rootless_codeowners_does_not_fallback_for_known_prefixed_root(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="repo/services/payments/plan.json",
                    tool="terraform",
                    status="failed",
                    changes=[],
                ),
                ParsedFileResult(
                    file_name="services/root/plan.json",
                    tool="terraform",
                    status="failed",
                    changes=[],
                ),
            ]
        )
        sources = uploaded_codeowners_sources(
            [
                ("CODEOWNERS", "* @root-owner"),
                ("repo/.github/CODEOWNERS", "/services/other/ @repo-owner"),
            ]
        )

        context = build_ownership_context(parse_batch, codeowners_sources=sources)

        self.assertEqual(
            [signal.subject for signal in context.owner_signals],
            ["services/root/plan.json"],
        )
        self.assertEqual(context.owner_signals[0].owners, ["@root-owner"])
        self.assertIn("repo/services/payments/plan.json", context.unmapped_subjects)

    def test_multi_root_codeowners_sources_match_each_uploaded_root(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="repo-a/services/payments/plan.json",
                    tool="terraform",
                    status="failed",
                    changes=[],
                ),
                ParsedFileResult(
                    file_name="repo-b/services/billing/plan.json",
                    tool="terraform",
                    status="failed",
                    changes=[],
                ),
            ]
        )
        sources = uploaded_codeowners_sources(
            [
                ("repo-a/.github/CODEOWNERS", "/services/payments/ @payments-sre"),
                ("repo-b/.github/CODEOWNERS", "/services/billing/ @billing-sre"),
            ]
        )

        context = build_ownership_context(parse_batch, codeowners_sources=sources)

        self.assertEqual(
            [signal.owners for signal in context.owner_signals],
            [["@payments-sre"], ["@billing-sre"]],
        )
        self.assertEqual(context.unmapped_subjects, ())

    def test_oversized_uploaded_codeowners_degrades_to_unmapped_context(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="app.js",
                    tool="terraform",
                    status="failed",
                    changes=[],
                )
            ]
        )
        sources = uploaded_codeowners_sources([("CODEOWNERS", b"* @root\n" * 500_000)])

        context = build_ownership_context(parse_batch, codeowners_sources=sources)

        self.assertEqual(
            sources,
            (CodeownersSource(source_ref="CODEOWNERS", content="", readable=False),),
        )
        self.assertEqual(context.owner_signals, ())
        self.assertIn("app.js", context.unmapped_subjects)

    def test_invalid_higher_priority_codeowners_does_not_fall_through(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="app.js",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="app.js",
                            tool="terraform",
                            resource_id="aws_security_group.app",
                            action="modify",
                            summary="Terraform changed an app security group.",
                        )
                    ],
                )
            ]
        )
        sources = uploaded_codeowners_sources(
            [
                (".github/CODEOWNERS", b"\xff"),
                ("CODEOWNERS", "* @fallback-owner"),
            ]
        )

        context = build_ownership_context(parse_batch, codeowners_sources=sources)

        self.assertEqual(
            sources,
            (
                CodeownersSource(
                    source_ref=".github/CODEOWNERS", content="", readable=False
                ),
            ),
        )
        self.assertEqual(context.owner_signals, ())
        self.assertIn("app.js", context.unmapped_subjects)
        self.assertEqual(context.context_todos, (OWNERSHIP_CONTEXT_TODO,))

    def test_ownership_context_does_not_read_deploywhisper_codeowners_by_default(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="services/payments/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="services/payments/plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.payments",
                            action="modify",
                            summary="Terraform changed a payments security group.",
                        )
                    ],
                )
            ]
        )

        context = build_ownership_context(parse_batch)

        self.assertEqual(context.owner_signals, ())
        self.assertIn("services/payments/plan.json", context.unmapped_subjects)

    def test_codeowners_bracket_patterns_match_file_paths(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="app.js",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="app.js",
                            tool="terraform",
                            resource_id="aws_security_group.app",
                            action="modify",
                            summary="Terraform changed an app security group.",
                        )
                    ],
                )
            ]
        )
        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(
                self._codeowners(
                    "CODEOWNERS",
                    "\n".join(
                        [
                            "*.j[st] @js-owner",
                            "!app.js @negated-owner",
                        ]
                    ),
                ),
            ),
        )

        self.assertEqual(context.owner_signals[0].owners, ["@js-owner"])
        self.assertEqual(context.context_todos, ())

        docker_context = build_ownership_context(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="Dockerfile",
                        tool="terraform",
                        status="failed",
                        changes=[],
                    )
                ]
            ),
            codeowners_sources=(
                self._codeowners("CODEOWNERS", "[Dd]ockerfile @container-owner"),
            ),
        )

        self.assertEqual(docker_context.owner_signals[0].owners, ["@container-owner"])
        self.assertEqual(docker_context.context_todos, ())

    def test_missing_service_owner_adds_todo_even_when_file_owner_exists(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="services/payments/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="services/payments/plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.payments",
                            action="modify",
                            summary="Terraform changed a payments security group.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["aws_security_group.payments"],
                    "downstream": [],
                }
            ]
        }
        context = build_ownership_context(
            parse_batch,
            topology=topology,
            codeowners_sources=(
                self._codeowners("CODEOWNERS", "/services/payments/ @payments-sre"),
            ),
        )

        self.assertEqual([signal.scope for signal in context.owner_signals], ["file"])
        self.assertEqual(context.unmapped_subjects, ("Payments API",))
        self.assertEqual(context.context_todos, (OWNERSHIP_CONTEXT_TODO,))

    def test_ambiguous_alias_match_adds_todo_instead_of_owner_signals(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployments/payments.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="deployments/payments.yaml",
                            tool="kubernetes",
                            resource_id="Deployment/payments/api",
                            action="modify",
                            summary="Kubernetes deployment changed.",
                            metadata={"resource_aliases": ["Deployment/api"]},
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@payments-runtime"],
                },
                {
                    "id": "billing-api",
                    "label": "Billing API",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@billing-runtime"],
                },
            ]
        }
        context = build_ownership_context(parse_batch, topology=topology)

        self.assertEqual(context.owner_signals, ())
        self.assertIn("Deployment/payments/api", context.unmapped_subjects)
        self.assertEqual(context.context_todos, (OWNERSHIP_CONTEXT_TODO,))

    def test_ambiguous_exact_resource_match_adds_todo_instead_of_owner_signals(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployments/payments.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="deployments/payments.yaml",
                            tool="kubernetes",
                            resource_id="Deployment/api",
                            action="modify",
                            summary="Kubernetes deployment changed.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@payments-runtime"],
                },
                {
                    "id": "billing-api",
                    "label": "Billing API",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@billing-runtime"],
                },
            ]
        }

        context = build_ownership_context(parse_batch, topology=topology)

        self.assertEqual(context.owner_signals, ())
        self.assertIn("Deployment/api", context.unmapped_subjects)
        self.assertEqual(context.context_todos, (OWNERSHIP_CONTEXT_TODO,))

    def test_ambiguous_resource_stays_unmapped_with_file_owner(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="services/payments/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="services/payments/plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.payments",
                            action="modify",
                            summary="Terraform changed a payments security group.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["aws_security_group.payments"],
                    "owners": ["@payments-runtime"],
                },
                {
                    "id": "billing-api",
                    "label": "Billing API",
                    "resource_keys": ["aws_security_group.payments"],
                    "owners": ["@billing-runtime"],
                },
            ]
        }

        context = build_ownership_context(
            parse_batch,
            topology=topology,
            codeowners_sources=(
                self._codeowners("CODEOWNERS", "/services/payments/ @payments-sre"),
            ),
        )

        self.assertEqual([signal.scope for signal in context.owner_signals], ["file"])
        self.assertEqual(context.owner_signals[0].owners, ["@payments-sre"])
        self.assertIn("aws_security_group.payments", context.unmapped_subjects)
        self.assertEqual(context.context_todos, (OWNERSHIP_CONTEXT_TODO,))

    def test_multiple_services_with_same_owner_emit_service_signals(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployments/payments.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="deployments/payments.yaml",
                            tool="kubernetes",
                            resource_id="Deployment/api",
                            action="modify",
                            summary="Kubernetes deployment changed.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@shared-runtime"],
                },
                {
                    "id": "payments-worker",
                    "label": "Payments Worker",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@shared-runtime"],
                },
            ]
        }

        context = build_ownership_context(parse_batch, topology=topology)

        self.assertEqual(
            [signal.subject for signal in context.owner_signals],
            ["Payments API", "Payments Worker"],
        )
        self.assertNotIn("Deployment/api", context.unmapped_subjects)

    def test_multiple_services_with_same_owner_set_ignore_owner_order(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployments/payments.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="deployments/payments.yaml",
                            tool="kubernetes",
                            resource_id="Deployment/api",
                            action="modify",
                            summary="Kubernetes deployment changed.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@payments-runtime", "@platform-runtime"],
                },
                {
                    "id": "payments-worker",
                    "label": "Payments Worker",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@platform-runtime", "@payments-runtime"],
                },
            ]
        }

        context = build_ownership_context(parse_batch, topology=topology)

        self.assertEqual(
            [signal.subject for signal in context.owner_signals],
            ["Payments API", "Payments Worker"],
        )
        self.assertNotIn("Deployment/api", context.unmapped_subjects)

    def test_topology_only_owner_satisfies_file_ownership_context(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployments/payments.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="deployments/payments.yaml",
                            tool="kubernetes",
                            resource_id="Deployment/api",
                            action="modify",
                            summary="Kubernetes deployment image changed.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "metadata": {"import": {"source_ref": "topology.yaml"}},
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@payments-runtime"],
                }
            ],
        }

        context = build_ownership_context(parse_batch, topology=topology)

        self.assertEqual(
            [signal.scope for signal in context.owner_signals], ["service"]
        )
        self.assertEqual(context.owner_signals[0].owners, ["@payments-runtime"])
        self.assertEqual(context.unmapped_subjects, ())
        self.assertEqual(context.context_todos, ())

    def test_plain_topology_owner_label_satisfies_ownership_context(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployments/payments.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="deployments/payments.yaml",
                            tool="kubernetes",
                            resource_id="Deployment/api",
                            action="modify",
                            summary="Kubernetes deployment image changed.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "metadata": {"import": {"source_ref": "topology.yaml"}},
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["payments-team"],
                }
            ],
        }

        context = build_ownership_context(parse_batch, topology=topology)

        self.assertEqual(
            [signal.scope for signal in context.owner_signals], ["service"]
        )
        self.assertEqual(context.owner_signals[0].owners, ["payments-team"])
        self.assertEqual(context.unmapped_subjects, ())
        self.assertEqual(context.context_todos, ())

    def test_topology_owner_satisfies_external_artifact_ownership_context(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="__external_path__/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="__external_path__/plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.payments",
                            action="modify",
                            summary="Terraform changed a payments security group.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "metadata": {"import": {"source_ref": "topology.yaml"}},
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["aws_security_group.payments"],
                    "owners": ["@payments-runtime"],
                }
            ],
        }

        context = build_ownership_context(parse_batch, topology=topology)

        self.assertEqual(
            [signal.scope for signal in context.owner_signals], ["service"]
        )
        self.assertEqual(context.owner_signals[0].owners, ["@payments-runtime"])
        self.assertEqual(context.unmapped_subjects, ())
        self.assertEqual(context.context_todos, ())

    def test_non_mutating_changes_do_not_create_missing_ownership_context(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployments/payments.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="deployments/payments.yaml",
                            tool="kubernetes",
                            resource_id="Deployment/api",
                            action="read",
                            summary="Kubernetes deployment was read without changes.",
                        )
                    ],
                )
            ]
        )

        context = build_ownership_context(parse_batch)

        self.assertEqual(context.unmapped_subjects, ())
        self.assertEqual(context.context_todos, ())

    def test_invalid_topology_owner_tokens_do_not_emit_owner_signals(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployments/payments.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="deployments/payments.yaml",
                            tool="kubernetes",
                            resource_id="Deployment/api",
                            action="modify",
                            summary="Kubernetes deployment changed.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@payments-runtime."],
                }
            ]
        }

        context = build_ownership_context(parse_batch, topology=topology)

        self.assertEqual(context.owner_signals, ())
        self.assertIn("Payments API", context.unmapped_subjects)
        self.assertEqual(context.context_todos, (OWNERSHIP_CONTEXT_TODO,))

    def test_duplicate_service_id_with_conflicting_owners_is_unmapped(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployments/payments.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="deployments/payments.yaml",
                            tool="kubernetes",
                            resource_id="Deployment/api",
                            action="modify",
                            summary="Kubernetes deployment changed.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["Deployment/api"],
                    "owners": [],
                },
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["Deployment/api"],
                    "owners": ["@payments-runtime"],
                },
            ]
        }

        context = build_ownership_context(parse_batch, topology=topology)

        self.assertEqual(context.owner_signals, ())
        self.assertIn("Deployment/api", context.unmapped_subjects)
        self.assertEqual(context.context_todos, (OWNERSHIP_CONTEXT_TODO,))

    def test_failed_file_still_gets_file_owner_signal(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="services/payments/broken-plan.json",
                    tool="terraform",
                    status="failed",
                    changes=[],
                )
            ]
        )
        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(
                self._codeowners("CODEOWNERS", "/services/payments/ @payments-sre"),
            ),
        )

        self.assertEqual([signal.scope for signal in context.owner_signals], ["file"])
        self.assertEqual(context.owner_signals[0].owners, ["@payments-sre"])
        self.assertEqual(context.context_todos, ())

    def test_empty_file_name_degrades_to_unmapped_subject(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="",
                    tool="terraform",
                    status="failed",
                    changes=[],
                )
            ]
        )

        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(self._codeowners("CODEOWNERS", "* @root-owner"),),
        )

        self.assertEqual(context.owner_signals, ())
        self.assertIn("unknown-file", context.unmapped_subjects)

    def test_empty_file_name_with_service_owner_does_not_add_unknown_file(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="",
                            tool="terraform",
                            resource_id="aws_security_group.payments",
                            action="modify",
                            summary="Terraform changed a payments security group.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["aws_security_group.payments"],
                    "owners": ["@payments-runtime"],
                }
            ],
        }

        context = build_ownership_context(parse_batch, topology=topology)

        self.assertEqual(
            [signal.scope for signal in context.owner_signals], ["service"]
        )
        self.assertEqual(context.unmapped_subjects, ())
        self.assertNotIn("unknown-file", context.unmapped_subjects)

    def test_codeowners_file_owner_satisfies_unmatched_resource_escalation(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="services/payments/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="services/payments/plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.unmapped",
                            action="modify",
                            summary="Terraform changed an unmapped security group.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["aws_security_group.payments"],
                    "owners": ["@payments-runtime"],
                    "downstream": [],
                }
            ]
        }
        context = build_ownership_context(
            parse_batch,
            topology=topology,
            codeowners_sources=(
                self._codeowners("CODEOWNERS", "/services/payments/ @payments-sre"),
            ),
        )

        self.assertEqual([signal.scope for signal in context.owner_signals], ["file"])
        self.assertEqual(context.unmapped_subjects, ())
        self.assertEqual(context.context_todos, ())

    def test_blank_resource_id_uses_codeowners_file_owner_fallback(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="services/payments/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="services/payments/plan.json",
                            tool="terraform",
                            resource_id=" ",
                            action="modify",
                            summary="Terraform changed an unnamed resource.",
                        )
                    ],
                )
            ]
        )

        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(
                self._codeowners("CODEOWNERS", "/services/payments/ @payments-sre"),
            ),
        )

        self.assertEqual([signal.scope for signal in context.owner_signals], ["file"])
        self.assertEqual(context.unmapped_subjects, ())
        self.assertEqual(context.context_todos, ())

    def test_invalid_uploaded_codeowners_degrades_to_unmapped_context(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="app.js",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="app.js",
                            tool="terraform",
                            resource_id="aws_security_group.app",
                            action="modify",
                            summary="Terraform changed an app security group.",
                        )
                    ],
                )
            ]
        )
        sources = uploaded_codeowners_sources([("CODEOWNERS", b"\xff")])

        context = build_ownership_context(parse_batch, codeowners_sources=sources)

        self.assertEqual(
            sources,
            (CodeownersSource(source_ref="CODEOWNERS", content="", readable=False),),
        )
        self.assertEqual(context.owner_signals, ())
        self.assertIn("app.js", context.unmapped_subjects)
        self.assertEqual(context.context_todos, (OWNERSHIP_CONTEXT_TODO,))

    def test_ownerless_codeowners_lines_clear_earlier_valid_matches(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="app.js",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="app.js",
                            tool="terraform",
                            resource_id="aws_security_group.app",
                            action="modify",
                            summary="Terraform changed an app security group.",
                        )
                    ],
                )
            ]
        )

        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(self._codeowners("CODEOWNERS", "* @platform\napp.js"),),
        )

        self.assertEqual(context.owner_signals, ())
        self.assertIn("app.js", context.unmapped_subjects)

    def test_invalid_codeowners_owner_tokens_are_skipped(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="app.py",
                    tool="terraform",
                    status="failed",
                    changes=[],
                ),
                ParsedFileResult(
                    file_name="service.yaml",
                    tool="terraform",
                    status="failed",
                    changes=[],
                ),
                ParsedFileResult(
                    file_name="infra.tf",
                    tool="terraform",
                    status="failed",
                    changes=[],
                ),
            ]
        )

        context = build_ownership_context(
            parse_batch,
            codeowners_sources=(
                self._codeowners(
                    "CODEOWNERS",
                    "\n".join(
                        [
                            "*.py platform-team",
                            "*.yaml @platform bad-token",
                            "*.tf @bad-owner.",
                        ]
                    ),
                ),
            ),
        )

        self.assertEqual(context.owner_signals, ())
        self.assertIn("app.py", context.unmapped_subjects)
        self.assertIn("service.yaml", context.unmapped_subjects)
        self.assertIn("infra.tf", context.unmapped_subjects)


if __name__ == "__main__":
    unittest.main()
