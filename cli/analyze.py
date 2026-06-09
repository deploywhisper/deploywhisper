"""Headless CLI workflows for DeployWhisper."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from api.errors import build_error
from api.schemas import AdvisorySummaryData, build_analysis_run_data, build_meta
from integrations.github.init_service import (
    GitHubInitError,
    collect_github_init_options,
    run_github_init,
)
import llm.skill_context as skill_context_module
from services.skill_manifest_service import (
    SkillManifestValidationError,
    load_skill_document,
)
from services.skill_installer_service import (
    SkillInstallerError,
    install_skill,
    list_installed_skills,
    remove_skill,
    update_skill,
)
from services.skill_registry_service import fetch_skill_registry_page
from services.skill_test_harness_service import run_skill_test_suites
from services.skill_test_harness_service import iter_built_in_skill_ids
from services.analysis_service import (
    AnalysisPersistenceError,
    analyze_uploaded_files,
    build_share_summary,
    resolve_analysis_project_scope,
)
from services.benchmark_corpus_service import (
    BenchmarkCorpusValidationError,
    validate_benchmark_corpus,
)
from services.backtesting_service import run_incident_backtest
from services.benchmark_runner_service import run_benchmark_corpus
from services.deployment_outcome_service import record_deployment_outcome
from services.project_service import create_project, create_workspace
from services.project_service import filter_projects_by_authorization
from services.project_service import has_restricted_project_scope
from services.project_service import list_project_role_definitions
from services.project_service import list_projects, list_workspaces
from services.project_service import require_project_permission
from services.project_service import resolve_project_reference
from services.intake_service import (
    MAX_TOTAL_UPLOAD_BYTES,
    build_pending_analysis,
    uniquify_artifact_names,
)
from services.report_service import (
    REPORT_SCHEMA_VERSION,
    ReportTrendError,
    build_report_advisory_payload,
    fetch_analysis_report,
    fetch_risk_trends,
)
from services.topology_service import get_topology_status, import_topology_source
from pydantic import ValidationError


def _emit_json(payload: dict, *, stream) -> None:
    stream.write(json.dumps(payload))
    stream.write("\n")


def _analysis_run_advisory(result) -> AdvisorySummaryData:
    persisted_report = result.persisted_report
    fallback_payload = (
        build_report_advisory_payload(persisted_report)
        if isinstance(persisted_report, dict)
        else {}
    )
    advisory = AdvisorySummaryData.model_validate(fallback_payload)
    if isinstance(persisted_report, dict):
        persisted_report["advisory"] = advisory.model_dump(mode="json")
    return advisory


def _split_env_project_keys(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _project_authorization_from_env() -> dict[str, object]:
    return {
        "role": os.environ.get("DEPLOYWHISPER_PROJECT_ROLE"),
        "allowed_project_keys": _split_env_project_keys(
            os.environ.get("DEPLOYWHISPER_PROJECT_KEYS")
        ),
    }


def _cli_authorization_has_restricted_project_scope() -> bool:
    authorization = _project_authorization_from_env()
    return has_restricted_project_scope(
        role=authorization["role"],
        allowed_project_keys=authorization["allowed_project_keys"],
    )


def _emit_project_authorization_error(exc: PermissionError) -> int:
    _emit_json(
        build_error(
            code=getattr(exc, "code", "project_permission_denied"),
            message=getattr(exc, "message", str(exc)),
        ),
        stream=sys.stderr,
    )
    return 2


def _emit_project_scope_forbidden_error() -> int:
    _emit_json(
        build_error(
            code="project_scope_forbidden",
            message="Caller is not authorized for the requested project.",
        ),
        stream=sys.stderr,
    )
    return 2


def _emit_missing_workspace_project_scope_error() -> int:
    _emit_json(
        build_error(
            code="missing_project_scope",
            message="Project scope is required when resolving workspace_id.",
        ),
        stream=sys.stderr,
    )
    return 2


def _should_mask_cli_project_reference_error(
    *,
    project_id: int | None,
    exc: ValueError,
) -> bool:
    return (
        project_id is not None
        and getattr(exc, "code", None)
        in {"project_not_found", "conflicting_project_reference"}
        and _cli_authorization_has_restricted_project_scope()
    )


def _should_mask_cli_scope_reference_error(exc: ValueError) -> bool:
    return _cli_authorization_has_restricted_project_scope() and getattr(
        exc, "code", None
    ) in {
        "analysis_not_found",
        "conflicting_project_reference",
        "project_not_found",
        "workspace_not_found",
        "conflicting_workspace_reference",
    }


def _require_cli_project_permission(
    *,
    capability: str,
    project_key: str | None = None,
) -> None:
    authorization = _project_authorization_from_env()
    require_project_permission(
        role=authorization["role"],
        capability=capability,
        project_key=project_key,
        allowed_project_keys=authorization["allowed_project_keys"],
    )


def _require_cli_analysis_project_permission(
    *,
    capability: str,
    analysis_id: int,
) -> bool:
    _require_cli_project_permission(capability=capability)
    report = fetch_analysis_report(analysis_id)
    if report is None:
        return False
    project = report.get("project") or {}
    _require_cli_project_permission(
        capability=capability,
        project_key=project.get("project_key"),
    )
    return True


def _load_artifacts(paths: list[str]) -> list[tuple[str, bytes]]:
    artifacts: list[tuple[str, bytes]] = []
    running_total = 0
    for raw_path in paths:
        path = Path(raw_path)
        try:
            file_size = path.stat().st_size
            running_total += file_size
            if running_total > MAX_TOTAL_UPLOAD_BYTES:
                raise ValueError(
                    json.dumps(
                        build_error(
                            code="upload_limit_exceeded",
                            message="Total artifact payload exceeds the 50 MB analysis-session limit.",
                        )
                    )
                )
            artifacts.append((path.name, path.read_bytes()))
        except OSError as exc:
            raise ValueError(
                json.dumps(
                    build_error(
                        code="artifact_read_failed",
                        message="One or more artifact files could not be read.",
                        details={"path": str(path), "reason": str(exc)},
                    )
                )
            ) from exc
    return [
        (str(name), bytes(raw_content or b""))
        for name, raw_content in uniquify_artifact_names(artifacts)
    ]


def _run_skills() -> int:
    statuses = skill_context_module.get_custom_skill_statuses()
    if not statuses:
        print("No custom skills detected.")
        return 0
    for status in statuses:
        mode_text = "override" if status.mode == "override" else "new"
        state_text = "detected" if status.active else "ignored"
        print(f"{status.name}: {mode_text} ({state_text})")
    return 0


def _run_skill_lint(path_arg: str) -> int:
    path = Path(path_arg)
    project_root = Path.cwd().resolve()
    try:
        document = load_skill_document(
            path,
            strict_manifest=True,
            allow_legacy_name=False,
            project_root=project_root,
        )
    except FileNotFoundError:
        sys.stderr.write(f"Skill file not found: {path}\n")
        return 2
    except SkillManifestValidationError as exc:
        sys.stderr.write(f"{path}: invalid skill manifest v1\n")
        for issue in exc.issues:
            sys.stderr.write(f"- {issue}\n")
        return 2

    if document.manifest is None:
        sys.stderr.write(f"{path}: missing skill manifest v1\n")
        return 2
    print(
        f"{path}: valid skill manifest v1 "
        f"({document.manifest.name}@{document.manifest.version})"
    )
    return 0


def _run_skill_test(skill_ids: list[str], *, emit_json: bool = False) -> int:
    normalized_ids = [
        skill_id.strip().lower() for skill_id in skill_ids if skill_id.strip()
    ]
    known_ids = set(iter_built_in_skill_ids())
    missing_ids = [skill_id for skill_id in normalized_ids if skill_id not in known_ids]
    if missing_ids:
        if emit_json:
            _emit_json(
                build_error(
                    code="skill_not_found",
                    message="One or more skills were not found.",
                    details={"skill_ids": missing_ids},
                ),
                stream=sys.stderr,
            )
        else:
            sys.stderr.write("Unknown skill ids: " + ", ".join(missing_ids) + "\n")
        return 2

    results = run_skill_test_suites(normalized_ids)
    if emit_json:
        _emit_json(
            {"data": [result.model_dump() for result in results]},
            stream=sys.stdout,
        )
    else:
        if not results:
            print("No skill test suites found.")
            return 1
        for result in results:
            summary = result.summary
            print(f"{result.skill_id}: {summary.display_text} [{summary.status}]")
            for scenario in result.scenarios:
                if scenario.passed:
                    continue
                print(f"  - {scenario.name}: {'; '.join(scenario.failures)}")
    return (
        0
        if results and all(result.summary.status == "passing" for result in results)
        else 1
    )


def _run_skill_install(skill_id: str) -> int:
    try:
        result = install_skill(skill_id)
    except SkillInstallerError as exc:
        sys.stderr.write(f"{exc.message}\n")
        return 2
    print(
        f"Installed {result.skill_id}@{result.version} "
        f"to {result.destination} [{result.mode}]"
    )
    return 0


def _run_skill_list() -> int:
    installed = list_installed_skills()
    if not installed:
        print("No installed custom skills found.")
        return 0
    for item in installed:
        version_text = item.version or "unknown"
        state_text = "active" if item.active else "ignored"
        line = f"{item.id}@{version_text} [{item.mode}, {state_text}]"
        if item.warning:
            line += f" - {item.warning}"
        print(line)
    return 0


def _run_skill_catalog_list() -> int:
    items = []
    page_number = 1
    page_size = 100
    total_count = 0

    while True:
        page = fetch_skill_registry_page(page=page_number, page_size=page_size)
        if page_number == 1:
            total_count = page.total_count
        items.extend(page.items)
        if len(items) >= total_count or not page.items:
            break
        page_number += 1

    if not items:
        print("No registry skills found.")
        return 0
    for item in items:
        pass_rate = (
            f"{round(item.test_results.pass_rate * 100):.0f}%"
            if item.test_results is not None and item.test_results.status != "missing"
            else "n/a"
        )
        print(
            f"{item.id} installs={item.install_count} "
            f"pass-rate={pass_rate} "
            f"active-issues={item.active_issue_count} "
            f"updated={item.updated_at[:10]} "
            f"analytics={item.analytics_updated_at[:10]}"
        )
    return 0


def _run_skill_update(skill_id: str) -> int:
    try:
        result = update_skill(skill_id)
    except SkillInstallerError as exc:
        sys.stderr.write(f"{exc.message}\n")
        return 2
    if result.action == "unchanged":
        print(
            f"{result.skill_id} is already up to date "
            f"at {result.version} ({result.destination})"
        )
        return 0
    print(
        f"Updated {result.skill_id} "
        f"{result.previous_version or 'unknown'} -> {result.version} "
        f"at {result.destination}"
    )
    return 0


def _run_skill_remove(skill_id: str) -> int:
    try:
        result = remove_skill(skill_id)
    except SkillInstallerError as exc:
        sys.stderr.write(f"{exc.message}\n")
        return 2
    print(f"Removed {result.skill_id} from {result.destination}")
    return 0


def _run_analyze(
    paths: list[str],
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> int:
    if not paths:
        _emit_json(
            build_error(
                code="missing_artifacts",
                message="At least one artifact file is required.",
            ),
            stream=sys.stderr,
        )
        return 2

    try:
        project_key_for_auth = project_key.strip() if project_key is not None else None
        if project_key_for_auth:
            _require_cli_project_permission(
                capability="analysis.submit",
                project_key=project_key_for_auth,
            )
        else:
            _require_cli_project_permission(capability="analysis.submit")
        resolved_project = resolve_analysis_project_scope(
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
        _require_cli_project_permission(
            capability="analysis.submit",
            project_key=resolved_project.project_key,
        )
    except PermissionError as exc:
        return _emit_project_authorization_error(exc)
    except ValueError as exc:
        if _should_mask_cli_scope_reference_error(exc):
            return _emit_project_scope_forbidden_error()
        if _should_mask_cli_project_reference_error(project_id=project_id, exc=exc):
            return _emit_project_scope_forbidden_error()
        _emit_json(
            build_error(
                code=getattr(exc, "code", "invalid_project_request"),
                message=str(exc),
            ),
            stream=sys.stderr,
        )
        return 2

    try:
        raw_files = _load_artifacts(paths)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    pending_analysis = build_pending_analysis(raw_files)
    if pending_analysis.ready_count == 0:
        _emit_json(
            build_error(
                code="no_supported_artifacts",
                message="At least one supported artifact is required for analysis.",
                details={
                    "items": [item.model_dump() for item in pending_analysis.items]
                },
            ),
            stream=sys.stderr,
        )
        return 2

    try:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            result = analyze_uploaded_files(
                raw_files,
                project_id=project_id,
                project_key=project_key,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
                audit_context={
                    "source_interface": "cli",
                    "trigger_type": os.getenv(
                        "DEPLOYWHISPER_TRIGGER_TYPE", "cli_command"
                    ),
                    "trigger_id": os.getenv("DEPLOYWHISPER_TRIGGER_ID"),
                    "actor": os.getenv("DEPLOYWHISPER_ACTOR", "cli_local_user"),
                },
            )
    except ValueError as exc:
        if _should_mask_cli_scope_reference_error(exc):
            return _emit_project_scope_forbidden_error()
        _emit_json(
            build_error(
                code=getattr(exc, "code", "invalid_project_request"),
                message=str(exc),
            ),
            stream=sys.stderr,
        )
        return 2
    except AnalysisPersistenceError as exc:
        _emit_json(
            build_error(
                code=exc.code,
                message=str(exc),
                details={"reason": exc.public_reason},
            ),
            stream=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        _emit_json(
            build_error(
                code="analysis_failed",
                message="Analysis failed.",
                details={"reason": str(exc)},
            ),
            stream=sys.stderr,
        )
        return 1
    payload = {
        "data": build_analysis_run_data(
            intake=pending_analysis,
            result=result,
            advisory=_analysis_run_advisory(result),
            share_summary=build_share_summary(result.persisted_report),
        ).model_dump(),
        "meta": build_meta(
            api_version="v1",
            report_schema_version=REPORT_SCHEMA_VERSION,
            interface="cli",
            advisory_only=True,
            submitted_artifact_count=len(raw_files),
            accepted_artifact_count=pending_analysis.ready_count,
        ),
    }
    _emit_json(payload, stream=sys.stdout)
    return 0


def _run_project_create(args: argparse.Namespace) -> int:
    try:
        _require_cli_project_permission(
            capability="project.manage",
            project_key=args.project_key,
        )
        created = create_project(
            project_key=args.project_key,
            display_name=args.display_name,
            description=args.description,
            repository_url=args.repository_url,
            default_branch=args.default_branch,
        )
    except PermissionError as exc:
        return _emit_project_authorization_error(exc)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    print(
        f"Created project {created.project_key} "
        f"({created.display_name}) [id={created.id}]"
    )
    return 0


def _run_project_list() -> int:
    authorization = _project_authorization_from_env()
    try:
        projects = filter_projects_by_authorization(
            list_projects(),
            role=authorization["role"],
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    except PermissionError as exc:
        return _emit_project_authorization_error(exc)
    for project in projects:
        suffix = " [default]" if project.is_default else ""
        print(f"{project.project_key}: {project.display_name}{suffix}")
    return 0


def _run_project_roles() -> int:
    for definition in list_project_role_definitions():
        print(f"{definition.role}: {', '.join(definition.capabilities)}")
    return 0


def _run_project_workspace_create(args: argparse.Namespace) -> int:
    try:
        _require_cli_project_permission(
            capability="workspace.manage",
            project_key=args.project_key,
        )
        created = create_workspace(
            project_key=args.project_key,
            workspace_key=args.workspace_key,
            display_name=args.display_name,
            description=args.description,
            environment=args.environment,
        )
    except PermissionError as exc:
        return _emit_project_authorization_error(exc)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    print(
        f"Created workspace {created.workspace_key} "
        f"({created.display_name}) for project {created.project_key} "
        f"[id={created.id}]"
    )
    return 0


def _run_project_workspace_list(args: argparse.Namespace) -> int:
    try:
        _require_cli_project_permission(
            capability="workspace.read",
            project_key=args.project_key,
        )
        workspaces = list_workspaces(project_key=args.project_key)
    except PermissionError as exc:
        return _emit_project_authorization_error(exc)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    for workspace in workspaces:
        environment = (
            f" ({workspace.environment})" if workspace.environment is not None else ""
        )
        print(
            f"{workspace.project_key}/{workspace.workspace_key}: "
            f"{workspace.display_name}{environment}"
        )
    return 0


def _run_outcome_record(args: argparse.Namespace) -> int:
    try:
        authorized_analysis = _require_cli_analysis_project_permission(
            capability="outcome.manage",
            analysis_id=args.analysis_id,
        )
        if not authorized_analysis:
            if _cli_authorization_has_restricted_project_scope():
                return _emit_project_scope_forbidden_error()
            _emit_json(
                build_error(
                    code="analysis_not_found",
                    message="Analysis report not found.",
                ),
                stream=sys.stderr,
            )
            return 2
        recorded = record_deployment_outcome(
            analysis_id=args.analysis_id,
            outcome=args.outcome,
            deployed_at=args.deployed_at,
            linked_incident_id=args.linked_incident_id,
            environment=args.environment,
            summary=args.summary,
            notes=args.notes,
            project_id=args.project_id,
            project_key=args.project_key,
            workspace_id=args.workspace_id,
            workspace_key=args.workspace_key,
            source_interface="cli",
        )
    except PermissionError as exc:
        return _emit_project_authorization_error(exc)
    except ValueError as exc:
        if _should_mask_cli_scope_reference_error(exc):
            return _emit_project_scope_forbidden_error()
        _emit_json(
            build_error(
                code=getattr(exc, "code", "invalid_deployment_request"),
                message=str(exc),
            ),
            stream=sys.stderr,
        )
        return 2

    _emit_json(
        {
            "data": recorded,
            "meta": build_meta(interface="cli", id=recorded["id"]),
        },
        stream=sys.stdout,
    )
    return 0


def _run_topology_import(args: argparse.Namespace) -> int:
    if (
        args.workspace_id is not None
        and args.project_id is None
        and args.project_key is None
    ):
        return _emit_missing_workspace_project_scope_error()
    try:
        project_key_for_auth = (
            args.project_key.strip() if args.project_key is not None else None
        )
        if project_key_for_auth:
            _require_cli_project_permission(
                capability="topology.manage",
                project_key=project_key_for_auth,
            )
        else:
            _require_cli_project_permission(capability="topology.manage")
        project = resolve_project_reference(
            project_id=args.project_id,
            project_key=args.project_key,
        )
        _require_cli_project_permission(
            capability="topology.manage",
            project_key=project.project_key,
        )
        import_result = import_topology_source(
            args.source_type,
            args.source,
            project_id=project.id,
            workspace_id=args.workspace_id,
            workspace_key=args.workspace_key,
        )
        status = get_topology_status(
            project_id=project.id,
            workspace_id=args.workspace_id,
            workspace_key=args.workspace_key,
        )
    except PermissionError as exc:
        return _emit_project_authorization_error(exc)
    except ValueError as exc:
        if _should_mask_cli_scope_reference_error(exc):
            return _emit_project_scope_forbidden_error()
        if _should_mask_cli_project_reference_error(
            project_id=args.project_id,
            exc=exc,
        ):
            return _emit_project_scope_forbidden_error()
        _emit_json(
            build_error(
                code=getattr(exc, "code", "invalid_topology_definition"),
                message=str(exc),
                details=getattr(exc, "details", None),
            ),
            stream=sys.stderr,
        )
        return 2

    _emit_json(
        {
            "data": {
                "project": project.model_dump(),
                "import": import_result.model_dump(),
                "topology": {
                    "path": status.path,
                    "exists": status.exists,
                    "updated_at": status.updated_at,
                    "service_count": status.service_count,
                    "dependency_count": status.dependency_count,
                    "resource_key_count": status.resource_key_count,
                    "preview_services": status.preview_services,
                    "warnings": status.warnings,
                    "blocking_errors": status.blocking_errors,
                },
            },
            "meta": build_meta(interface="cli"),
        },
        stream=sys.stdout,
    )
    return 0


def _run_github_init(args: argparse.Namespace) -> int:
    try:
        options = collect_github_init_options(
            repo_path=args.repo,
            workflow_path=args.workflow_path,
            api_endpoint=args.api_endpoint,
            enable_github_app=args.github_app,
            base_branch=args.base_branch,
            github_owner=args.github_owner,
            github_app_name=args.github_app_name,
            github_app_slug=args.github_app_slug,
            public_base_url=args.public_base_url,
            project_key=args.project_key,
            project_id=args.project_id,
            workspace_key=args.workspace_key,
            workspace_id=args.workspace_id,
            allow_derived_project_scope=args.allow_derived_project_scope,
            branch_name=args.branch_name,
        )
        result = run_github_init(options)
    except GitHubInitError as exc:
        _emit_json(
            build_error(
                code="github_init_failed",
                message="GitHub initialization wizard failed.",
                details={"reason": str(exc)},
            ),
            stream=sys.stderr,
        )
        return 1

    print(f"Updated workflow: {result.workflow_path}")
    print(f"Updated README: {result.readme_path}")
    if result.github_app_notes_path:
        print(f"Added self-hosted GitHub App notes: {result.github_app_notes_path}")
    print(f"Created branch: {result.branch_name}")
    print(f"Base branch: {result.base_branch}")
    print(f"Commit: {result.commit_sha}")
    print(f"Pull request: {result.pr_url}")
    return 0


def _run_benchmark_validate_corpus(path: str | None) -> int:
    result = validate_benchmark_corpus(
        Path(path) if path is not None else None,
        raise_on_error=False,
    )
    _emit_json(result.model_dump(mode="json"), stream=sys.stdout)
    return 0 if result.valid else 1


def _benchmark_error_summary(
    *,
    corpus_id: str = "unknown",
    version: str = "unknown",
    scenario_count: int = 0,
) -> dict:
    return {
        "corpus_id": corpus_id,
        "version": version,
        "scenario_count": scenario_count,
        "passed_count": 0,
        "failed_count": scenario_count,
        "unsupported_count": 0,
        "total_latency_ms": 0.0,
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
    }


def _run_benchmark_run(path: str | None) -> int:
    try:
        result = run_benchmark_corpus(Path(path) if path is not None else None)
    except BenchmarkCorpusValidationError as exc:
        validation_summary = exc.result.summary
        _emit_json(
            {
                "passed": False,
                "valid": False,
                "summary": _benchmark_error_summary(
                    corpus_id=validation_summary.corpus_id,
                    version=validation_summary.version,
                    scenario_count=validation_summary.scenario_count,
                ),
                "scenarios": [],
                "errors": exc.errors,
            },
            stream=sys.stdout,
        )
        return 1
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as exc:
        _emit_json(
            {
                "passed": False,
                "valid": False,
                "summary": _benchmark_error_summary(),
                "scenarios": [],
                "errors": [str(exc)],
            },
            stream=sys.stdout,
        )
        return 1
    _emit_json(result.model_dump(mode="json"), stream=sys.stdout)
    return 0 if result.passed else 1


def _run_benchmark_backtest_incidents(args: argparse.Namespace) -> int:
    try:
        result = run_incident_backtest(
            project_id=args.project_id,
            project_key=args.project_key,
            workspace_id=args.workspace_id,
            workspace_key=args.workspace_key,
        )
    except (ValueError, OSError, ValidationError) as exc:
        _emit_json(
            {
                "passed": False,
                "summary": {
                    "project_id": args.project_id,
                    "project_key": args.project_key,
                    "workspace_id": args.workspace_id,
                    "workspace_key": args.workspace_key,
                    "scenario_count": 0,
                    "detected_count": 0,
                    "missed_count": 0,
                    "unsupported_count": 0,
                    "insufficient_context_count": 0,
                    "error_count": 1,
                    "generated_at": datetime.now(tz=UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                },
                "scenarios": [],
                "errors": [str(exc)],
            },
            stream=sys.stdout,
        )
        return 1
    _emit_json(result, stream=sys.stdout)
    return 0 if result.get("passed") else 1


def _parse_trend_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _run_benchmark_risk_trends(args: argparse.Namespace) -> int:
    try:
        if args.project_id is None and not args.project_key:
            raise ReportTrendError(
                "missing_project_scope",
                "Project scope is required for risk trend review.",
            )
        created_from = _parse_trend_timestamp(args.created_from)
        created_to = _parse_trend_timestamp(args.created_to)
        if (
            created_from is not None
            and created_to is not None
            and created_from > created_to
        ):
            raise ReportTrendError(
                "invalid_time_window",
                "created_from must be earlier than or equal to created_to.",
            )
        result = fetch_risk_trends(
            project_id=args.project_id,
            project_key=args.project_key,
            workspace_id=args.workspace_id,
            workspace_key=args.workspace_key,
            severity=args.severity,
            toolchain=args.toolchain,
            outcome=args.outcome,
            created_from=created_from,
            created_to=created_to,
        )
    except (ValueError, OSError, ValidationError) as exc:
        _emit_json(
            build_error(
                code=getattr(exc, "code", "risk_trend_export_failed"),
                message=str(exc),
            ),
            stream=sys.stderr,
        )
        return 1
    _emit_json(result, stream=sys.stdout)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeployWhisper CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("skills", help="List built-in and custom AI skill statuses.")
    skill_parser = subparsers.add_parser(
        "skill", help="Authoring and package actions for individual skills."
    )
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command")
    skill_install_parser = skill_subparsers.add_parser(
        "install", help="Fetch and install a registry skill into skills/custom."
    )
    skill_install_parser.add_argument("skill_id", help="Skill id to install.")
    skill_list_parser = skill_subparsers.add_parser(
        "list", help="List installed custom skills from skills/custom."
    )
    skill_list_parser.add_argument(
        "--catalog",
        action="store_true",
        help="Show registry catalog analytics instead of installed custom skills.",
    )
    skill_lint_parser = skill_subparsers.add_parser(
        "lint", help="Validate a skill markdown file against manifest v1."
    )
    skill_lint_parser.add_argument("path", help="Skill markdown path to validate.")
    skill_test_parser = skill_subparsers.add_parser(
        "test", help="Run deterministic harness scenarios for one or more skills."
    )
    skill_test_parser.add_argument(
        "skill_ids",
        nargs="*",
        help="Optional skill ids to test. Defaults to all built-in skills.",
    )
    skill_test_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable output.",
    )
    skill_update_parser = skill_subparsers.add_parser(
        "update", help="Refresh an installed skill to the latest registry version."
    )
    skill_update_parser.add_argument("skill_id", help="Installed skill id to update.")
    skill_remove_parser = skill_subparsers.add_parser(
        "remove", help="Uninstall a custom skill from skills/custom."
    )
    skill_remove_parser.add_argument("skill_id", help="Installed skill id to remove.")

    analyze_parser = subparsers.add_parser(
        "analyze", help="Run headless advisory analysis for one or more artifacts."
    )
    analyze_parser.add_argument(
        "--project",
        dest="project_key",
        help="Project key for the analysis. Required unless --project-id is provided.",
    )
    analyze_parser.add_argument(
        "--project-id",
        dest="project_id",
        type=int,
        help="Numeric project id for the analysis. Required unless --project is provided.",
    )
    analyze_parser.add_argument(
        "--workspace",
        dest="workspace_key",
        help="Optional project-local workspace/environment key for the analysis.",
    )
    analyze_parser.add_argument(
        "--workspace-id",
        dest="workspace_id",
        type=int,
        help="Optional numeric workspace/environment id for the analysis.",
    )
    analyze_parser.add_argument(
        "paths", nargs="*", help="Artifact file paths to analyze."
    )

    project_parser = subparsers.add_parser(
        "project", help="Manage lightweight project/workspace records."
    )
    project_subparsers = project_parser.add_subparsers(dest="project_command")
    project_subparsers.required = True
    project_create_parser = project_subparsers.add_parser(
        "create", help="Create a project/workspace record."
    )
    project_create_parser.add_argument("project_key", help="Stable project key.")
    project_create_parser.add_argument(
        "display_name", help="Human-readable project name."
    )
    project_create_parser.add_argument(
        "--description",
        help="Optional project description.",
    )
    project_create_parser.add_argument(
        "--repository-url",
        help="Optional repository URL.",
    )
    project_create_parser.add_argument(
        "--default-branch",
        help="Optional default branch name.",
    )
    project_subparsers.add_parser("list", help="List known project/workspace records.")
    project_subparsers.add_parser(
        "roles", help="List lightweight project role capabilities."
    )
    project_workspace_parser = project_subparsers.add_parser(
        "workspace", help="Manage workspace/environment records for a project."
    )
    workspace_subparsers = project_workspace_parser.add_subparsers(
        dest="workspace_command"
    )
    workspace_subparsers.required = True
    workspace_create_parser = workspace_subparsers.add_parser(
        "create", help="Create a workspace/environment record."
    )
    workspace_create_parser.add_argument("project_key", help="Owning project key.")
    workspace_create_parser.add_argument("workspace_key", help="Stable workspace key.")
    workspace_create_parser.add_argument(
        "display_name", help="Human-readable workspace name."
    )
    workspace_create_parser.add_argument(
        "--description",
        help="Optional workspace description.",
    )
    workspace_create_parser.add_argument(
        "--environment",
        help="Optional environment label such as prod or staging.",
    )
    workspace_list_parser = workspace_subparsers.add_parser(
        "list", help="List workspace/environment records for a project."
    )
    workspace_list_parser.add_argument("project_key", help="Owning project key.")

    outcome_parser = subparsers.add_parser(
        "outcome", help="Record post-deployment outcomes for persisted analyses."
    )
    outcome_subparsers = outcome_parser.add_subparsers(dest="outcome_command")
    outcome_subparsers.required = True
    outcome_record_parser = outcome_subparsers.add_parser(
        "record",
        help="Capture a deployment outcome for a persisted analysis report.",
    )
    outcome_record_parser.add_argument(
        "--analysis-id",
        required=True,
        type=int,
        help="Persisted analysis report identifier.",
    )
    outcome_record_parser.add_argument(
        "--outcome",
        required=True,
        help="Deployment result: success, failure, rolled_back, or rollback.",
    )
    outcome_record_parser.add_argument(
        "--deployed-at",
        help="Optional ISO 8601 deployment timestamp. Defaults to now.",
    )
    outcome_record_parser.add_argument(
        "--linked-incident-id",
        type=int,
        help="Optional linked incident identifier.",
    )
    outcome_record_parser.add_argument(
        "--environment",
        help="Optional environment label such as prod or staging.",
    )
    outcome_record_parser.add_argument(
        "--summary",
        help="Optional operator summary for the deployment outcome.",
    )
    outcome_record_parser.add_argument(
        "--notes",
        help="Optional operator notes for the deployment outcome.",
    )
    outcome_record_parser.add_argument(
        "--project",
        dest="project_key",
        help="Optional project/workspace key for validation.",
    )
    outcome_record_parser.add_argument(
        "--project-id",
        dest="project_id",
        type=int,
        help="Optional numeric project id for validation.",
    )
    outcome_record_parser.add_argument(
        "--workspace",
        dest="workspace_key",
        help="Optional workspace/environment key for validation.",
    )
    outcome_record_parser.add_argument(
        "--workspace-id",
        dest="workspace_id",
        type=int,
        help="Optional numeric workspace/environment id for validation.",
    )

    topology_parser = subparsers.add_parser(
        "topology", help="Manage project-scoped topology context."
    )
    topology_subparsers = topology_parser.add_subparsers(dest="topology_command")
    topology_subparsers.required = True
    topology_import_parser = topology_subparsers.add_parser(
        "import",
        help="Import topology context from a registered source for a project/workspace.",
    )
    topology_import_parser.add_argument(
        "--from",
        dest="source_type",
        required=True,
        help="Registered topology source identifier.",
    )
    topology_import_parser.add_argument(
        "--source",
        required=True,
        help="Topology source path or URI reference.",
    )
    topology_import_parser.add_argument(
        "--project",
        dest="project_key",
        help="Project key for the topology import.",
    )
    topology_import_parser.add_argument(
        "--project-id",
        dest="project_id",
        type=int,
        help="Numeric project id for the topology import.",
    )
    topology_import_parser.add_argument(
        "--workspace",
        dest="workspace_key",
        help="Optional workspace/environment key for the topology import.",
    )
    topology_import_parser.add_argument(
        "--workspace-id",
        dest="workspace_id",
        type=int,
        help="Optional numeric workspace/environment id for the topology import.",
    )
    github_parser = subparsers.add_parser(
        "github", help="GitHub workflow setup helpers."
    )
    github_subparsers = github_parser.add_subparsers(dest="github_command")
    github_init_parser = github_subparsers.add_parser(
        "init",
        help="Scaffold the DeployWhisper GitHub workflow, commit it, and open a PR.",
    )
    github_init_parser.add_argument(
        "--repo",
        help="Target repository checkout path. Defaults to the current directory.",
    )
    github_init_parser.add_argument(
        "--workflow-path",
        help="Workflow file path relative to the target repository.",
    )
    github_init_parser.add_argument(
        "--api-endpoint",
        help="DeployWhisper analyses API endpoint for the generated workflow.",
    )
    github_init_parser.add_argument(
        "--base-branch",
        help="Base branch that should receive the generated PR.",
    )
    github_init_parser.add_argument(
        "--github-app",
        action="store_true",
        default=None,
        help="Include advanced self-hosted GitHub App setup notes.",
    )
    github_init_parser.add_argument(
        "--github-owner",
        help="GitHub owner or account for the self-hosted GitHub App path.",
    )
    github_init_parser.add_argument(
        "--github-app-name",
        help="GitHub App display name for the self-hosted GitHub App path.",
    )
    github_init_parser.add_argument(
        "--github-app-slug",
        help="GitHub App slug for the self-hosted GitHub App path.",
    )
    github_init_parser.add_argument(
        "--public-base-url",
        help="Public DeployWhisper base URL for the self-hosted GitHub App path.",
    )
    github_init_parser.add_argument(
        "--project-key",
        help="DeployWhisper project key for the generated action workflow.",
    )
    github_init_parser.add_argument(
        "--project-id",
        help="DeployWhisper numeric project id for the generated action workflow.",
    )
    github_init_parser.add_argument(
        "--workspace-key",
        help="Optional DeployWhisper workspace key for the generated action workflow.",
    )
    github_init_parser.add_argument(
        "--workspace-id",
        help="Optional DeployWhisper numeric workspace id for the generated action workflow.",
    )
    github_init_parser.add_argument(
        "--allow-derived-project-scope",
        action="store_true",
        default=None,
        help="Generate an action workflow that relies on the API endpoint to derive project scope.",
    )
    github_init_parser.add_argument(
        "--branch-name",
        help="Optional branch name to use in the target repository.",
    )

    benchmark_parser = subparsers.add_parser(
        "benchmark", help="Benchmark corpus and result helpers."
    )
    benchmark_subparsers = benchmark_parser.add_subparsers(dest="benchmark_command")
    benchmark_subparsers.required = True
    benchmark_validate_parser = benchmark_subparsers.add_parser(
        "validate-corpus", help="Validate the public benchmark corpus contract."
    )
    benchmark_validate_parser.add_argument(
        "--path",
        help="Optional benchmark corpus root. Defaults to benchmarks/corpus/v1.",
    )
    benchmark_run_parser = benchmark_subparsers.add_parser(
        "run", help="Run the public benchmark corpus against the analysis core."
    )
    benchmark_run_parser.add_argument(
        "--path",
        help="Optional benchmark corpus root. Defaults to benchmarks/corpus/v1.",
    )
    benchmark_backtest_parser = benchmark_subparsers.add_parser(
        "backtest-incidents",
        help="Replay incident-linked artifacts against the current analysis core.",
    )
    benchmark_backtest_parser.add_argument(
        "--project-id",
        type=int,
        help="DeployWhisper numeric project id.",
    )
    benchmark_backtest_parser.add_argument(
        "--project-key",
        help="DeployWhisper project key.",
    )
    benchmark_backtest_parser.add_argument(
        "--workspace-id",
        type=int,
        help="Optional DeployWhisper numeric workspace id.",
    )
    benchmark_backtest_parser.add_argument(
        "--workspace-key",
        help="Optional DeployWhisper workspace key.",
    )
    benchmark_risk_trends_parser = benchmark_subparsers.add_parser(
        "risk-trends",
        help="Export scoped risk trend review data as JSON.",
    )
    benchmark_risk_trends_parser.add_argument(
        "--project-id",
        type=int,
        help="DeployWhisper numeric project id.",
    )
    benchmark_risk_trends_parser.add_argument(
        "--project-key",
        help="DeployWhisper project key.",
    )
    benchmark_risk_trends_parser.add_argument(
        "--workspace-id",
        type=int,
        help="Optional DeployWhisper numeric workspace id.",
    )
    benchmark_risk_trends_parser.add_argument(
        "--workspace-key",
        help="Optional DeployWhisper workspace key.",
    )
    benchmark_risk_trends_parser.add_argument(
        "--severity",
        choices=("critical", "high", "medium", "low"),
        help="Optional risk severity filter.",
    )
    benchmark_risk_trends_parser.add_argument(
        "--toolchain",
        help="Optional normalized toolchain filter, such as terraform or kubernetes.",
    )
    benchmark_risk_trends_parser.add_argument(
        "--outcome",
        choices=("success", "failure", "rolled_back", "rollback"),
        help="Optional deployment outcome filter.",
    )
    benchmark_risk_trends_parser.add_argument(
        "--created-from",
        help=(
            "Optional inclusive activity-window start timestamp "
            "(report created, outcome deployed, or feedback created), ISO-8601 or Zulu."
        ),
    )
    benchmark_risk_trends_parser.add_argument(
        "--created-to",
        help=(
            "Optional inclusive activity-window end timestamp "
            "(report created, outcome deployed, or feedback created), ISO-8601 or Zulu."
        ),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "skills":
        raise SystemExit(_run_skills())
    if args.command == "skill" and args.skill_command == "install":
        raise SystemExit(_run_skill_install(args.skill_id))
    if args.command == "skill" and args.skill_command == "list":
        raise SystemExit(
            _run_skill_catalog_list()
            if getattr(args, "catalog", False)
            else _run_skill_list()
        )
    if args.command == "skill" and args.skill_command == "lint":
        raise SystemExit(_run_skill_lint(args.path))
    if args.command == "skill" and args.skill_command == "test":
        raise SystemExit(_run_skill_test(args.skill_ids, emit_json=args.json))
    if args.command == "skill" and args.skill_command == "update":
        raise SystemExit(_run_skill_update(args.skill_id))
    if args.command == "skill" and args.skill_command == "remove":
        raise SystemExit(_run_skill_remove(args.skill_id))
    if args.command == "analyze":
        raise SystemExit(
            _run_analyze(
                args.paths,
                project_id=getattr(args, "project_id", None),
                project_key=getattr(args, "project_key", None),
                workspace_id=getattr(args, "workspace_id", None),
                workspace_key=getattr(args, "workspace_key", None),
            )
        )
    if args.command == "project" and args.project_command == "create":
        raise SystemExit(_run_project_create(args))
    if args.command == "project" and args.project_command == "list":
        raise SystemExit(_run_project_list())
    if args.command == "project" and args.project_command == "roles":
        raise SystemExit(_run_project_roles())
    if args.command == "project" and args.project_command == "workspace":
        if args.workspace_command == "create":
            raise SystemExit(_run_project_workspace_create(args))
        if args.workspace_command == "list":
            raise SystemExit(_run_project_workspace_list(args))
    if args.command == "outcome" and args.outcome_command == "record":
        raise SystemExit(_run_outcome_record(args))
    if args.command == "topology" and args.topology_command == "import":
        raise SystemExit(_run_topology_import(args))
    if args.command == "github" and args.github_command == "init":
        raise SystemExit(_run_github_init(args))
    if args.command == "benchmark" and args.benchmark_command == "validate-corpus":
        raise SystemExit(_run_benchmark_validate_corpus(args.path))
    if args.command == "benchmark" and args.benchmark_command == "run":
        raise SystemExit(_run_benchmark_run(args.path))
    if args.command == "benchmark" and args.benchmark_command == "backtest-incidents":
        raise SystemExit(_run_benchmark_backtest_incidents(args))
    if args.command == "benchmark" and args.benchmark_command == "risk-trends":
        raise SystemExit(_run_benchmark_risk_trends(args))

    print("DeployWhisper CLI ready: foundation-check")


if __name__ == "__main__":
    main()
