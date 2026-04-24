"""Deterministic skill test harness execution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from analysis.risk_scorer import RiskAssessment, RiskContributor
from llm.skill_context import ActiveSkill, build_skill_context_from_active_skills
from services.skill_manifest_service import REPO_ROOT, load_skill_document


SKILLS_DIR = REPO_ROOT / "skills"
SkillHarnessStatus = Literal["passing", "failing", "missing"]


class SkillTestScenarioDefinition(BaseModel):
    """Deterministic scenario definition for a single skill."""

    name: str = Field(..., description="Stable scenario name.")
    description: str | None = Field(
        default=None, description="Human-readable description of the scenario."
    )
    assessment_tool: str = Field(
        ..., description="Contributor tool name used to build assessment context."
    )
    contributor_summary: str = Field(
        default="Exercise skill guidance.",
        description="Summary used for the single contributor in the scenario.",
    )
    raw_files: dict[str, str] = Field(
        default_factory=dict,
        description="Filename to text payload map supplied to skill resolution.",
    )
    expect_selected: bool = Field(
        default=True, description="Whether the target skill should be selected."
    )
    expected_substrings: list[str] = Field(
        default_factory=list,
        description="Substrings that must appear in the emitted skill context.",
    )
    expected_absent_substrings: list[str] = Field(
        default_factory=list,
        description="Substrings that must not appear in the emitted skill context.",
    )

    @field_validator("name", "assessment_tool", "contributor_summary")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @field_validator("expected_substrings", "expected_absent_substrings")
    @classmethod
    def _validate_substrings(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            candidate = str(item).strip()
            if candidate:
                normalized.append(candidate)
        return normalized


class SkillTestScenarioResult(BaseModel):
    """Pass/fail result for one harness scenario."""

    name: str
    description: str | None = None
    passed: bool
    failures: list[str] = Field(default_factory=list)


class SkillTestSummary(BaseModel):
    """Aggregate summary for a harness run."""

    skill_id: str
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    pass_rate: float = Field(..., ge=0.0, le=1.0)
    status: SkillHarnessStatus
    display_text: str
    generated_at: str


class SkillTestSuiteResult(BaseModel):
    """Complete harness result for one skill."""

    skill_id: str
    version: str
    summary: SkillTestSummary
    scenarios: list[SkillTestScenarioResult] = Field(default_factory=list)


class SkillScenarioLoadError(ValueError):
    """Raised when a scenario definition cannot be loaded safely."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(message)


def _timestamp() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _build_summary(
    skill_id: str,
    scenario_results: list[SkillTestScenarioResult],
) -> SkillTestSummary:
    total = len(scenario_results)
    passed = sum(1 for result in scenario_results if result.passed)
    failed = total - passed
    status: SkillHarnessStatus
    if total == 0:
        status = "missing"
    elif failed > 0:
        status = "failing"
    else:
        status = "passing"
    pass_rate = 0.0 if total == 0 else passed / total
    return SkillTestSummary(
        skill_id=skill_id,
        total_scenarios=total,
        passed_scenarios=passed,
        failed_scenarios=failed,
        pass_rate=pass_rate,
        status=status,
        display_text=f"{passed}/{total} scenarios passing",
        generated_at=_timestamp(),
    )


def _scenario_files(suite_dir: Path) -> list[Path]:
    if not suite_dir.exists():
        return []
    return sorted(path for path in suite_dir.glob("*.json") if path.is_file())


def _load_scenarios(suite_dir: Path) -> list[SkillTestScenarioDefinition]:
    scenarios: list[SkillTestScenarioDefinition] = []
    for path in _scenario_files(suite_dir):
        try:
            scenarios.append(
                SkillTestScenarioDefinition.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise SkillScenarioLoadError(path, str(exc)) from exc
    return scenarios


def _load_active_skill(skill_id: str) -> tuple[ActiveSkill, str, Path] | None:
    path = SKILLS_DIR / f"{skill_id}.md"
    if not path.exists():
        return None
    document = load_skill_document(
        path,
        strict_manifest=True,
        allow_legacy_name=False,
        project_root=None,
    )
    if document.manifest is None:
        return None
    return (
        ActiveSkill(
            name=skill_id,
            source="built-in",
            path=str(path),
            content=document.body,
            always_load=document.manifest.always_load,
            triggers=list(document.manifest.triggers),
            trigger_content_patterns=list(document.manifest.trigger_content_patterns),
        ),
        document.manifest.version,
        REPO_ROOT / document.manifest.test_suite_path,
    )


def _build_assessment(
    skill_id: str,
    scenario: SkillTestScenarioDefinition,
) -> RiskAssessment:
    return RiskAssessment(
        score=20,
        severity="low",
        recommendation="go",
        top_risk=f"Skill harness scenario for {skill_id}.",
        partial_context=False,
        warnings=[],
        contributors=[
            RiskContributor(
                source_file=next(
                    iter(scenario.raw_files.keys()), f"{skill_id}.fixture"
                ),
                tool=scenario.assessment_tool,
                resource_id=f"{skill_id}.scenario",
                action="modify",
                contribution=5,
                summary=scenario.contributor_summary,
            )
        ],
    )


def _run_scenario(
    skill_id: str,
    active_skill: ActiveSkill,
    scenario: SkillTestScenarioDefinition,
) -> SkillTestScenarioResult:
    raw_files = {
        filename: content.encode("utf-8")
        for filename, content in scenario.raw_files.items()
    }
    context = build_skill_context_from_active_skills(
        {skill_id: active_skill},
        _build_assessment(skill_id, scenario),
        raw_files=raw_files,
    )
    selected = bool(context.strip())
    failures: list[str] = []
    if scenario.expect_selected and not selected:
        failures.append("Skill was not selected for the scenario context.")
    if not scenario.expect_selected and selected:
        failures.append("Skill was selected unexpectedly for the scenario context.")
    for expected in scenario.expected_substrings:
        if expected not in context:
            failures.append(f"Missing expected substring: {expected}")
    for unexpected in scenario.expected_absent_substrings:
        if unexpected in context:
            failures.append(f"Unexpected substring present: {unexpected}")
    return SkillTestScenarioResult(
        name=scenario.name,
        description=scenario.description,
        passed=not failures,
        failures=failures,
    )


def run_skill_test_suite(skill_id: str) -> SkillTestSuiteResult | None:
    """Run the deterministic harness for a single built-in skill."""

    loaded = _load_active_skill(skill_id)
    if loaded is None:
        return None
    active_skill, version, suite_dir = loaded
    try:
        loaded_scenarios = _load_scenarios(suite_dir)
    except SkillScenarioLoadError as exc:
        scenario_results = [
            SkillTestScenarioResult(
                name="suite-load-error",
                description=f"Failed to load {exc.path.name}.",
                passed=False,
                failures=[f"{exc.path.name}: {exc.message}"],
            )
        ]
        return SkillTestSuiteResult(
            skill_id=skill_id,
            version=version,
            summary=_build_summary(skill_id, scenario_results),
            scenarios=scenario_results,
        )

    scenario_results = [
        _run_scenario(skill_id, active_skill, scenario) for scenario in loaded_scenarios
    ]
    return SkillTestSuiteResult(
        skill_id=skill_id,
        version=version,
        summary=_build_summary(skill_id, scenario_results),
        scenarios=scenario_results,
    )


def summarize_skill_test_suite(skill_id: str) -> SkillTestSummary | None:
    """Return only the harness summary for a built-in skill."""

    suite_result = run_skill_test_suite(skill_id)
    if suite_result is None:
        return None
    return suite_result.summary


def iter_built_in_skill_ids() -> list[str]:
    """Return built-in skill ids that participate in the local harness."""

    return sorted(
        path.stem.lower() for path in SKILLS_DIR.glob("*.md") if path.is_file()
    )


def run_skill_test_suites(
    skill_ids: list[str] | None = None,
) -> list[SkillTestSuiteResult]:
    """Run harness suites for the requested built-in skill ids."""

    requested = skill_ids or iter_built_in_skill_ids()
    results: list[SkillTestSuiteResult] = []
    for skill_id in requested:
        suite = run_skill_test_suite(skill_id)
        if suite is None:
            continue
        results.append(suite)
    return results
