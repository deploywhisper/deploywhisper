"""Keep operator procedures aligned with existing contracts and local references."""

from __future__ import annotations

from pathlib import Path
import json
import re
import unittest
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from cli.identity import build_parser
from infra_automation.lifecycle import AutomationSettings
from infra_automation.retention import PurgeManifestBody
from infra_automation.runner.cache import (
    MAX_BYTES,
    MAX_ENTRIES,
    MAX_FILE_BYTES,
    CacheManifest,
)
from infra_automation.runner.execution_profile import ExecutionProfile
from infra_automation.state import EngineBounds


ROOT = Path(__file__).resolve().parents[2]
GUIDES = tuple(
    ROOT / "docs" / "infra-automation" / name
    for name in ("operations.md", "network.md")
)


def table_values(content: str, heading: str) -> dict[str, str]:
    section = content.split(heading + "\n", 1)[1].split("\n## ", 1)[0]
    return {
        match[1]: match[2].strip()
        for match in re.finditer(r"^\| `([a-z0-9_]+)` \| ([^|]+) \|$", section, re.M)
    }


class AutomationOperationsDocumentationTests(unittest.TestCase):
    def test_documented_upgrade_result_matches_linked_evidence(self):
        content = GUIDES[0].read_text(encoding="utf-8")
        evidence = json.loads(
            (
                ROOT / "docs/verification/infra-automation/16-18/upgrade-results.json"
            ).read_text()
        )
        match = re.search(r"destination schema (\d{3})", content)
        self.assertIsNotNone(match)
        self.assertEqual(match[1], evidence["destination_schema"].split("_", 1)[0])

    def test_local_links_resolve_inside_repository(self):
        parser = MarkdownIt()
        for guide in GUIDES:
            tokens = parser.parse(guide.read_text(encoding="utf-8"))
            for token in tokens:
                for child in token.children or ():
                    target = child.attrGet("href") or child.attrGet("src")
                    if not target or urlsplit(target).scheme:
                        continue
                    with self.subTest(guide=guide.name, target=target):
                        path = (guide.parent / unquote(urlsplit(target).path)).resolve()
                        self.assertTrue(path.is_relative_to(ROOT))
                        self.assertTrue(path.is_file(), str(path))

    def test_project_setting_defaults_match_typed_contract(self):
        content = GUIDES[0].read_text(encoding="utf-8")
        expected = {
            key: str(value).lower()
            for key, value in AutomationSettings().model_dump().items()
        }
        self.assertEqual(table_values(content, "## Project policy defaults"), expected)

    def test_engine_ceiling_defaults_match_typed_contract(self):
        content = GUIDES[0].read_text(encoding="utf-8")
        self.assertEqual(
            table_values(content, "## Engine ceiling defaults"),
            {key: str(value) for key, value in EngineBounds().model_dump().items()},
        )

    def test_network_profile_cannot_silently_expand(self):
        content = GUIDES[1].read_text(encoding="utf-8")
        profile = ExecutionProfile(image_id="sha256:" + "a" * 64)
        names = (
            "architecture",
            "docker_version",
            "kernel_version",
            "network",
            "work_bytes",
            "tmp_bytes",
            "output_bytes",
            "timeout_seconds",
        )
        self.assertEqual(
            table_values(content, "## Qualified offline task defaults"),
            {name: str(getattr(profile, name)) for name in names},
        )
        self.assertIn("Task egress and DNS allowlists are empty", content)
        self.assertIn("No host-wide cache quota is enforced", " ".join(content.split()))

    def test_identity_examples_are_real_parser_commands(self):
        content = GUIDES[0].read_text(encoding="utf-8")
        examples = (
            ["setup", "--output", "/private/operator/setup"],
            [
                "bootstrap",
                "--username",
                "operator",
                "--credential-file",
                "/private/operator/setup",
            ],
            [
                "recovery-issue",
                "--username",
                "operator",
                "--output",
                "/private/operator/recovery",
            ],
            ["recover", "--credential-file", "/private/operator/recovery"],
        )
        for args in examples:
            with self.subTest(command=args[0]):
                self.assertIn("python -m cli.identity " + " ".join(args), content)
                self.assertEqual(build_parser().parse_args(args).command, args[0])

    def test_cache_manifest_example_and_bounds_match_verifier(self):
        content = GUIDES[1].read_text(encoding="utf-8")
        manifest = re.search(r"```json\n(.*?)\n```", content, re.S)
        self.assertIsNotNone(manifest)
        value = CacheManifest.model_validate_json(manifest[1])
        self.assertEqual(len(value.files), 1)
        self.assertEqual(value.files[0].size, 1)
        self.assertEqual(value.files[0].path, "synthetic-fixture")
        self.assertIn(f"| Bytes per file | {MAX_FILE_BYTES} |", content)
        self.assertIn(f"| Total listed bytes | {MAX_BYTES} |", content)
        self.assertIn(
            f"| Traversed entries, including directories | {MAX_ENTRIES} |", content
        )
        maximum = next(
            item.max_length
            for item in CacheManifest.model_fields["files"].metadata
            if hasattr(item, "max_length")
        )
        self.assertIn(f"| Manifest files | {maximum} |", content)
        self.assertIn("python -m infra_automation.runner.cache --root", content)

    def test_retention_request_example_uses_the_real_closed_body(self):
        content = GUIDES[0].read_text(encoding="utf-8")
        example = re.search(r"```json\n(.*?)\n```", content, re.S)
        self.assertIsNotNone(example)
        request = PurgeManifestBody.model_validate_json(example[1])
        self.assertEqual(request.expected_run_version, 1)
        for statement in (
            "every pending/approved decision",
            "any external handoff",
            "held/broken locks",
            "does not erase linked report exports",
        ):
            self.assertIn(statement, " ".join(content.split()))

    def test_documented_existing_policy_and_lock_routes_are_installed(self):
        source = (ROOT / "api/routes/infra_automation.py").read_text()
        content = GUIDES[0].read_text(encoding="utf-8")
        routes = (
            ("get", "/settings"),
            ("patch", "/settings"),
            ("post", "/settings/revoke"),
            ("post", "/settings/restore-epoch"),
            ("get", "/audit"),
            ("post", "/targets/{target_id}/break-lock"),
            ("post", "/manifests/{manifest_id}/purge"),
        )
        for method, route in routes:
            with self.subTest(method=method, route=route):
                self.assertRegex(source, rf'@router\.{method}\(\s*"{re.escape(route)}"')
                self.assertIn(f"`{method.upper()} {route}`", content)
