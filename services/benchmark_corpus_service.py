"""Benchmark corpus loading and validation."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from services.skill_manifest_service import REPO_ROOT


DEFAULT_BENCHMARK_CORPUS_DIR = REPO_ROOT / "benchmarks" / "corpus" / "v1"
PUBLIC_LICENSES = {
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "CC-BY-4.0",
    "CC0-1.0",
    "MIT",
}
PRIVATE_PATH_PARTS = {"..", ""}
UNSAFE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
        "private key material",
    ),
    (
        re.compile(
            r"\b(password|passwd|secret|token|api[_-]?key|access[_-]?key)"
            r"\s*[:=]\s*[\"']?[^\s\"']{6,}",
            re.IGNORECASE,
        ),
        "secret-like assignment",
    ),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key pattern"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "GitHub token pattern"),
)
NON_PUBLIC_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bconfidential\b", re.IGNORECASE), "confidential marker"),
    (re.compile(r"\binternal only\b", re.IGNORECASE), "internal-only marker"),
    (re.compile(r"\bnot for public\b", re.IGNORECASE), "non-public marker"),
    (re.compile(r"\bproprietary\b", re.IGNORECASE), "proprietary marker"),
)


Severity = Literal["info", "low", "medium", "high", "critical"]
ExpectedVerdict = Literal["go", "warn", "stop", "unsupported", "insufficient_context"]


def _strip_required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be empty")
    return normalized


def _normalize_required_text_list(
    value: list[str], *, field_label: str = "items"
) -> list[str]:
    normalized = [_strip_required_text(item) for item in value]
    if not normalized:
        raise ValueError(f"must include at least one {field_label}")
    return normalized


class BenchmarkCorpusManifest(BaseModel):
    """Top-level corpus manifest."""

    corpus_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    scenarios: list[str] = Field(..., min_length=1)

    @field_validator("corpus_id", "version", "description")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        return _strip_required_text(value)

    @field_validator("scenarios")
    @classmethod
    def _normalize_scenarios(cls, value: list[str]) -> list[str]:
        return _normalize_required_text_list(value, field_label="scenario path")


class BenchmarkArtifact(BaseModel):
    """Scenario artifact reference."""

    path: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)

    @field_validator("path", "type", "description")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        return _strip_required_text(value)


class BenchmarkExpectedEvidence(BaseModel):
    """Evidence item expected from a scenario."""

    id: str = Field(..., min_length=1)
    artifact_path: str = Field(..., min_length=1)
    selector: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)

    @field_validator("id", "artifact_path", "selector", "description")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        return _strip_required_text(value)


class BenchmarkExpectedFinding(BaseModel):
    """Finding expected from a scenario."""

    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    severity: Severity
    evidence_ids: list[str] = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)

    @field_validator("id", "title", "rationale")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        return _strip_required_text(value)

    @field_validator("evidence_ids")
    @classmethod
    def _normalize_evidence_ids(cls, value: list[str]) -> list[str]:
        return _normalize_required_text_list(value, field_label="evidence id")


class BenchmarkLicenseMetadata(BaseModel):
    """Public licensing metadata for a scenario."""

    spdx_id: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    public_sample: bool

    @field_validator("spdx_id", "source")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        return _strip_required_text(value)


class BenchmarkSafetyMetadata(BaseModel):
    """Safety declarations for public benchmark samples."""

    synthetic: bool
    contains_secrets: bool
    contains_customer_data: bool
    contains_non_public_information: bool


class BenchmarkScenarioDefinition(BaseModel):
    """Replayable benchmark scenario contract."""

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    labels: list[str] = Field(..., min_length=1)
    artifacts: list[BenchmarkArtifact] = Field(..., min_length=1)
    expected_findings: list[BenchmarkExpectedFinding] = Field(..., min_length=1)
    expected_evidence: list[BenchmarkExpectedEvidence] = Field(..., min_length=1)
    expected_verdict: ExpectedVerdict
    expected_verdict_rationale: str = Field(..., min_length=1)
    license: BenchmarkLicenseMetadata
    safety: BenchmarkSafetyMetadata

    @field_validator("id", "name", "description", "expected_verdict_rationale")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        return _strip_required_text(value)

    @field_validator("labels")
    @classmethod
    def _normalize_labels(cls, value: list[str]) -> list[str]:
        labels = sorted({item.strip() for item in value if item.strip()})
        if not labels:
            raise ValueError("must include at least one label")
        return labels


class BenchmarkScenarioValidationResult(BaseModel):
    """Validation summary for one scenario."""

    id: str
    name: str
    path: str
    artifact_count: int
    expected_finding_count: int
    expected_evidence_count: int
    labels: list[str]


class BenchmarkCorpusSummary(BaseModel):
    """Aggregate corpus validation summary."""

    corpus_id: str
    version: str
    scenario_count: int
    valid_scenario_count: int
    generated_at: str


class BenchmarkCorpusValidationResult(BaseModel):
    """Complete corpus validation result."""

    valid: bool
    summary: BenchmarkCorpusSummary
    scenarios: list[BenchmarkScenarioValidationResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BenchmarkCorpusValidationError(ValueError):
    """Raised when benchmark corpus validation fails."""

    def __init__(self, errors: list[str], result: BenchmarkCorpusValidationResult):
        self.errors = errors
        self.result = result
        super().__init__("; ".join(errors))


class BenchmarkCorpusScenario(BaseModel):
    """Loaded benchmark scenario with its manifest-relative path."""

    path: str
    scenario: BenchmarkScenarioDefinition


class BenchmarkCorpusDefinition(BaseModel):
    """Loaded benchmark corpus ready for execution."""

    root: str
    manifest: BenchmarkCorpusManifest
    scenarios: list[BenchmarkCorpusScenario]


def _timestamp() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative_path_error(value: str, *, field_name: str) -> str | None:
    candidate = Path(value)
    if candidate.is_absolute():
        return f"{field_name} must be relative: {value}"
    if any(part in PRIVATE_PATH_PARTS for part in candidate.parts):
        return f"{field_name} must not escape the corpus: {value}"
    return None


def _resolve_child(base_dir: Path, relative_path: str) -> Path:
    return (base_dir / relative_path).resolve()


def _read_artifact(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        return None, "artifact must be UTF-8 text"
    except OSError as exc:
        return None, str(exc)


def _iter_string_values(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _iter_string_values(nested)
    elif isinstance(value, list | tuple):
        for nested in value:
            yield from _iter_string_values(nested)


def _scan_public_safety(
    *,
    corpus_root: Path,
    scenario: BenchmarkScenarioDefinition,
    scenario_dir: Path,
) -> list[str]:
    errors: list[str] = []
    if scenario.license.spdx_id not in PUBLIC_LICENSES:
        errors.append(f"{scenario.id}: non-public license {scenario.license.spdx_id!r}")
    if not scenario.license.public_sample:
        errors.append(f"{scenario.id}: license metadata marks sample as non-public")
    if not scenario.safety.synthetic:
        errors.append(f"{scenario.id}: safety metadata must mark sample as synthetic")
    if scenario.safety.contains_secrets:
        errors.append(f"{scenario.id}: unsafe metadata declares secrets")
    if scenario.safety.contains_customer_data:
        errors.append(f"{scenario.id}: non-public customer data is not allowed")
    if scenario.safety.contains_non_public_information:
        errors.append(f"{scenario.id}: non-public information is not allowed")

    metadata_text = "\n".join(_iter_string_values(scenario.model_dump(mode="json")))
    for pattern, reason in UNSAFE_PATTERNS:
        if pattern.search(metadata_text):
            errors.append(f"{scenario.id}: unsafe scenario metadata ({reason})")
    for pattern, reason in NON_PUBLIC_PATTERNS:
        if pattern.search(metadata_text):
            errors.append(f"{scenario.id}: non-public scenario metadata ({reason})")

    for artifact in scenario.artifacts:
        path_error = _relative_path_error(artifact.path, field_name="artifact path")
        if path_error:
            continue
        artifact_path = _resolve_child(scenario_dir, artifact.path)
        if corpus_root not in artifact_path.parents:
            continue
        if artifact_path.is_symlink() or not artifact_path.is_file():
            continue
        content, read_error = _read_artifact(artifact_path)
        if read_error is not None:
            errors.append(f"{scenario.id}: {artifact.path}: {read_error}")
            continue
        for pattern, reason in UNSAFE_PATTERNS:
            if pattern.search(content or ""):
                errors.append(f"{scenario.id}: unsafe artifact content ({reason})")
        for pattern, reason in NON_PUBLIC_PATTERNS:
            if pattern.search(content or ""):
                errors.append(f"{scenario.id}: non-public artifact content ({reason})")
    return errors


def _validate_paths(
    *,
    corpus_root: Path,
    scenario_path: Path,
    scenario: BenchmarkScenarioDefinition,
) -> list[str]:
    errors: list[str] = []
    scenario_dir = scenario_path.parent
    artifact_paths: dict[str, Path] = {}
    for artifact in scenario.artifacts:
        path_error = _relative_path_error(artifact.path, field_name="artifact path")
        if path_error:
            errors.append(f"{scenario.id}: {path_error}")
            continue
        artifact_path = _resolve_child(scenario_dir, artifact.path)
        if corpus_root not in artifact_path.parents:
            errors.append(f"{scenario.id}: artifact escapes corpus: {artifact.path}")
            continue
        if not artifact_path.exists():
            errors.append(f"{scenario.id}: artifact missing: {artifact.path}")
            continue
        if artifact_path.is_symlink():
            errors.append(f"{scenario.id}: artifact symlinks are not allowed")
        if not artifact_path.is_file():
            errors.append(f"{scenario.id}: artifact must be a file: {artifact.path}")
            continue
        artifact_paths[artifact.path] = artifact_path

    for evidence in scenario.expected_evidence:
        artifact_path = artifact_paths.get(evidence.artifact_path)
        if artifact_path is None:
            errors.append(
                f"{scenario.id}: evidence {evidence.id} references unknown artifact "
                f"{evidence.artifact_path}"
            )
            continue
        content, read_error = _read_artifact(artifact_path)
        if read_error is not None:
            continue
        if evidence.selector not in (content or ""):
            errors.append(
                f"{scenario.id}: evidence {evidence.id} selector not found in "
                f"{evidence.artifact_path}"
            )
    return errors


def _validate_expected_outputs(scenario: BenchmarkScenarioDefinition) -> list[str]:
    errors: list[str] = []
    evidence_ids = {evidence.id for evidence in scenario.expected_evidence}
    if len(evidence_ids) != len(scenario.expected_evidence):
        errors.append(f"{scenario.id}: expected evidence ids must be unique")

    finding_ids = {finding.id for finding in scenario.expected_findings}
    if len(finding_ids) != len(scenario.expected_findings):
        errors.append(f"{scenario.id}: expected finding ids must be unique")

    for finding in scenario.expected_findings:
        missing = sorted(set(finding.evidence_ids) - evidence_ids)
        if missing:
            errors.append(
                f"{scenario.id}: finding {finding.id} references unknown evidence "
                f"{', '.join(missing)}"
            )
        if finding.severity in {"high", "critical"} and not finding.evidence_ids:
            errors.append(
                f"{scenario.id}: {finding.severity} finding {finding.id} has no "
                "expected evidence"
            )
    return errors


def _scenario_result(
    scenario: BenchmarkScenarioDefinition,
    scenario_path: Path,
    corpus_root: Path,
) -> BenchmarkScenarioValidationResult:
    return BenchmarkScenarioValidationResult(
        id=scenario.id,
        name=scenario.name,
        path=str(scenario_path.relative_to(corpus_root)),
        artifact_count=len(scenario.artifacts),
        expected_finding_count=len(scenario.expected_findings),
        expected_evidence_count=len(scenario.expected_evidence),
        labels=scenario.labels,
    )


def validate_benchmark_corpus(
    corpus_root: Path | str | None = None,
    *,
    raise_on_error: bool = True,
) -> BenchmarkCorpusValidationResult:
    """Validate the public benchmark corpus contract."""

    root = (
        Path(corpus_root) if corpus_root is not None else DEFAULT_BENCHMARK_CORPUS_DIR
    )
    root = root.resolve()
    manifest_path = root / "manifest.json"
    errors: list[str] = []
    scenario_results: list[BenchmarkScenarioValidationResult] = []
    manifest = BenchmarkCorpusManifest.model_construct(
        corpus_id="unknown",
        version="unknown",
        description="invalid corpus",
        scenarios=[],
    )

    try:
        manifest = BenchmarkCorpusManifest.model_validate(_load_json(manifest_path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        errors.append(f"manifest.json: {exc}")

    seen_scenarios: set[str] = set()
    for scenario_ref in manifest.scenarios:
        path_error = _relative_path_error(
            scenario_ref, field_name="scenario manifest path"
        )
        if path_error:
            errors.append(path_error)
            continue
        scenario_path = _resolve_child(root, scenario_ref)
        if root not in scenario_path.parents:
            errors.append(f"scenario manifest escapes corpus: {scenario_ref}")
            continue
        try:
            scenario = BenchmarkScenarioDefinition.model_validate(
                _load_json(scenario_path)
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            errors.append(f"{scenario_ref}: {exc}")
            continue
        if scenario.id in seen_scenarios:
            errors.append(f"{scenario.id}: scenario id must be unique")
        seen_scenarios.add(scenario.id)
        errors.extend(
            _validate_paths(
                corpus_root=root,
                scenario_path=scenario_path,
                scenario=scenario,
            )
        )
        errors.extend(_validate_expected_outputs(scenario))
        errors.extend(
            _scan_public_safety(
                corpus_root=root,
                scenario=scenario,
                scenario_dir=scenario_path.parent,
            )
        )
        scenario_results.append(_scenario_result(scenario, scenario_path, root))

    result = BenchmarkCorpusValidationResult(
        valid=not errors,
        summary=BenchmarkCorpusSummary(
            corpus_id=manifest.corpus_id,
            version=manifest.version,
            scenario_count=len(manifest.scenarios),
            valid_scenario_count=0 if errors else len(scenario_results),
            generated_at=_timestamp(),
        ),
        scenarios=scenario_results,
        errors=errors,
    )
    if errors and raise_on_error:
        raise BenchmarkCorpusValidationError(errors, result)
    return result


def load_benchmark_corpus(
    corpus_root: Path | str | None = None,
    *,
    validate: bool = True,
) -> BenchmarkCorpusDefinition:
    """Load a validated benchmark corpus for deterministic execution."""

    root = (
        Path(corpus_root) if corpus_root is not None else DEFAULT_BENCHMARK_CORPUS_DIR
    )
    root = root.resolve()
    if validate:
        validate_benchmark_corpus(root)
    manifest = BenchmarkCorpusManifest.model_validate(
        _load_json(root / "manifest.json")
    )
    scenarios: list[BenchmarkCorpusScenario] = []
    for scenario_ref in manifest.scenarios:
        path_error = _relative_path_error(
            scenario_ref, field_name="scenario manifest path"
        )
        if path_error:
            raise ValueError(path_error)
        scenario_path = _resolve_child(root, scenario_ref)
        try:
            scenario_path.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"scenario manifest escapes corpus: {scenario_ref}"
            ) from exc
        scenario = BenchmarkScenarioDefinition.model_validate(_load_json(scenario_path))
        scenarios.append(BenchmarkCorpusScenario(path=scenario_ref, scenario=scenario))
    return BenchmarkCorpusDefinition(
        root=str(root),
        manifest=manifest,
        scenarios=scenarios,
    )
