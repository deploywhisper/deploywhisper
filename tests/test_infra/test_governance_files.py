"""Guardrails for public governance and community documentation."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]

TYPOGRAPHIC_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2212"

REQUIRED_COMMUNITY_FILES = (
    "GOVERNANCE.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
    "ROADMAP.md",
)

FORBIDDEN_POSTURE_PATTERNS = (
    ("SaaS-only posture", re.compile(r"\bsaas[-\s]?only\b")),
    ("SaaS mandate", re.compile(r"\bsaas\s+(?:deployment\s+)?(?:is\s+)?mandatory\b")),
    ("hosted-only posture", re.compile(r"\bhosted[-\s]?only\b")),
    (
        "hosted exclusivity",
        re.compile(r"\bavailable\s+exclusively\s+via\s+the\s+hosted\s+service\b"),
    ),
    ("open-core posture", re.compile(r"\bopen[-\s]?core\b")),
    ("enterprise-only posture", re.compile(r"\benterprise[-\s]?only\b")),
    ("paid feature gating", re.compile(r"\bpaid\s+(?:feature|tier|plan|edition)\b")),
    (
        "hosted control-plane requirement",
        re.compile(
            r"\b(?:core\s+analysis|main\s+workflow|deployment-risk\s+briefing)"
            r"\s+requires\s+(?:a\s+)?(?:cloud|hosted)\s+control\s+plane\b"
        ),
    ),
    (
        "vendor-controlled roadmap priority",
        re.compile(
            r"\b(?:vendor|sponsor|commercial|customer)[-\s]+controlled\s+roadmap\b"
            r"|\broadmap\s+(?:is\s+)?(?:vendor|sponsor|commercial|customer)[-\s]+controlled\b"
            r"|\broadmap\s+priority\s+(?:is|will\s+be)\s+controlled\b"
            r"|\b(?:sponsors?|vendors?|commercial\s+customers?|customers?)"
            r"\s+(?:set|determine|control)\s+roadmap\s+(?:priorities|priority|order)\b"
            r"|\bcustomer[-\s]+driven\s+roadmap\s+priorities\b"
        ),
    ),
    (
        "proprietary plugin requirement",
        re.compile(
            r"\bproprietary\s+plugins?\s+(?:(?:is|are)\s+)?required\b"
            r"|\brequired\s+proprietary\s+plugins?\b"
            r"|\bmajor\s+(?:supported\s+)?platforms?\s+require\s+proprietary\s+plugins?\b"
        ),
    ),
    (
        "commercial edition requirement",
        re.compile(r"\bcommercial\s+edition\s+(?:is\s+)?required\b"),
    ),
)

REQUIRED_POSTURE_PATTERNS = (
    (
        "GOVERNANCE.md",
        "roadmap priority must remain public",
        re.compile(
            r"\b(?:external\s+funding|sponsorship|cloud\s+credits|foundation\s+support)"
            r".{0,120}\bmust\s+not\s+grant\s+private\s+control\b"
            r".{0,80}\broadmap\s+priority\b"
        ),
    ),
    (
        "GOVERNANCE.md",
        "optional hosted/vendor services must not become prerequisites",
        re.compile(
            r"\b(?:optional\s+services|hosted\s+deployments|vendor-specific\s+adapters)"
            r".{0,160}\bmust\s+not\s+become\s+prerequisites\b"
            r".{0,100}\bdeployment-risk\s+briefing\s+workflow\b"
        ),
    ),
    (
        "ROADMAP.md",
        "core analysis must not require a hosted control plane",
        re.compile(
            r"\bshould\s+not\s+require\s+a\s+hosted\s+control\s+plane\b.{0,80}\bcore\s+analysis\b"
        ),
    ),
)

PLACEHOLDER_TERMS = ("todo", "tbd", "coming soon", "placeholder", "lorem ipsum")


def _normalize_markdown(content: str) -> str:
    """Return lowercase text normalized for policy-pattern matching."""

    dash_translation = str.maketrans({dash: "-" for dash in TYPOGRAPHIC_DASHES})
    content = content.translate(dash_translation).lower()
    return re.sub(r"\s+", " ", content)


def _is_negated(content: str, match: re.Match[str]) -> bool:
    prefix = content[max(0, match.start() - 40) : match.start()]
    return bool(
        re.search(
            r"\b(?:not|never|no|without|does\s+not|do\s+not|must\s+not|should\s+not)"
            r"(?:\s+\w+){0,4}\s*$",
            prefix,
        )
    )


def _has_forbidden_posture(content: str, pattern: re.Pattern[str]) -> bool:
    return any(not _is_negated(content, match) for match in pattern.finditer(content))


def _is_placeholder_document(content: str) -> bool:
    normalized = _normalize_markdown(content)
    body = re.sub(r"(?m)^#+\s*", "", content).strip().lower()
    word_count = len(re.findall(r"[a-z0-9]+", body))
    return word_count < 20 or any(term in normalized for term in PLACEHOLDER_TERMS)


class GovernanceFilesTests(unittest.TestCase):
    """Verify repository-level community files stay present and open."""

    def test_required_community_files_exist(self) -> None:
        missing = [
            name for name in REQUIRED_COMMUNITY_FILES if not (ROOT / name).is_file()
        ]

        self.assertEqual([], missing)

    def test_required_community_files_are_not_placeholders(self) -> None:
        placeholders: list[str] = []

        for name in REQUIRED_COMMUNITY_FILES:
            path = ROOT / name
            if path.is_file() and _is_placeholder_document(
                path.read_text(encoding="utf-8")
            ):
                placeholders.append(name)

        self.assertEqual([], placeholders)

    def test_community_files_do_not_imply_feature_gating(self) -> None:
        violations: list[tuple[str, str]] = []

        for name in REQUIRED_COMMUNITY_FILES:
            path = ROOT / name
            if not path.exists():
                continue
            content = _normalize_markdown(path.read_text(encoding="utf-8"))
            for label, pattern in FORBIDDEN_POSTURE_PATTERNS:
                if _has_forbidden_posture(content, pattern):
                    violations.append((name, label))

        self.assertEqual([], violations)

    def test_community_files_explicitly_reject_closed_posture(self) -> None:
        missing: list[tuple[str, str]] = []

        for name, label, pattern in REQUIRED_POSTURE_PATTERNS:
            path = ROOT / name
            if not path.is_file():
                missing.append((name, label))
                continue
            content = _normalize_markdown(path.read_text(encoding="utf-8"))
            if not pattern.search(content):
                missing.append((name, label))

        self.assertEqual([], missing)

    def test_forbidden_posture_patterns_cover_reviewed_phrasings(self) -> None:
        forbidden_examples = (
            "Proprietary plugin is required for Kubernetes.",
            "The core analysis requires a cloud control plane.",
            "Available exclusively via the hosted service.",
            "Sponsors set roadmap priorities.",
            "This is an open-core distribution.",
            "The product is hosted-only.",
            "The roadmap is vendor-controlled.",
        )

        for example in forbidden_examples:
            normalized = _normalize_markdown(example)
            self.assertTrue(
                any(
                    _has_forbidden_posture(normalized, pattern)
                    for _, pattern in FORBIDDEN_POSTURE_PATTERNS
                ),
                example,
            )

    def test_forbidden_posture_patterns_allow_explicit_negations(self) -> None:
        allowed_examples = (
            "DeployWhisper is not open-core.",
            "This project is not SaaS-only.",
            "Core analysis should not require a hosted control plane.",
            "The roadmap must not grant private control to sponsors.",
        )

        for example in allowed_examples:
            normalized = _normalize_markdown(example)
            self.assertFalse(
                any(
                    _has_forbidden_posture(normalized, pattern)
                    for _, pattern in FORBIDDEN_POSTURE_PATTERNS
                ),
                example,
            )


if __name__ == "__main__":
    unittest.main()
