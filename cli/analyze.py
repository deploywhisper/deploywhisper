"""Headless CLI workflows for DeployWhisper."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from api.errors import build_error
from api.schemas import build_analysis_run_data, build_meta
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
    analyze_uploaded_files,
    build_advisory_summary,
    build_share_summary,
    resolve_analysis_project_scope,
)
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
from services.report_service import REPORT_SCHEMA_VERSION, fetch_analysis_report
from services.topology_service import get_topology_status, import_topology_source


def _emit_json(payload: dict, *, stream) -> None:
    stream.write(json.dumps(payload))
    stream.write("\n")


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

    assert document.manifest is not None
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
        if (
            project_id is not None
            and not project_key_for_auth
            and _cli_authorization_has_restricted_project_scope()
        ):
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
                },
            )
    except ValueError as exc:
        _emit_json(
            build_error(
                code=getattr(exc, "code", "invalid_project_request"),
                message=str(exc),
            ),
            stream=sys.stderr,
        )
        return 2
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
            advisory=build_advisory_summary(result.assessment, result.narrative),
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
            project_id=args.project_id,
            project_key=args.project_key,
            workspace_id=args.workspace_id,
            workspace_key=args.workspace_key,
            source_interface="cli",
        )
    except PermissionError as exc:
        return _emit_project_authorization_error(exc)
    except ValueError as exc:
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
        if (
            args.project_id is not None
            and not project_key_for_auth
            and _cli_authorization_has_restricted_project_scope()
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
        help="Deployment result: success, failure, or rolled_back.",
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
        "--branch-name",
        help="Optional branch name to use in the target repository.",
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

    print("DeployWhisper CLI ready: foundation-check")


if __name__ == "__main__":
    main()
