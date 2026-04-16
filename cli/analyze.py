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
import llm.skill_context as skill_context_module
from services.analysis_service import analyze_uploaded_files, build_advisory_summary, build_share_summary
from services.intake_service import build_pending_analysis


def _emit_json(payload: dict, *, stream) -> None:
    stream.write(json.dumps(payload))
    stream.write("\n")


def _load_artifacts(paths: list[str]) -> list[tuple[str, bytes]]:
    artifacts: list[tuple[str, bytes]] = []
    seen_names: dict[str, int] = {}
    for raw_path in paths:
        path = Path(raw_path)
        try:
            display_name = path.name
            seen_names[display_name] = seen_names.get(display_name, 0) + 1
            if seen_names[display_name] > 1:
                display_name = f"{path.stem}#{seen_names[display_name]}{path.suffix}"
            artifacts.append((display_name, path.read_bytes()))
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
    return artifacts


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


def _run_analyze(paths: list[str]) -> int:
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
                details={"items": [item.model_dump() for item in pending_analysis.items]},
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
                audit_context={
                    "source_interface": "cli",
                    "trigger_type": os.getenv("DEPLOYWHISPER_TRIGGER_TYPE", "cli_command"),
                    "trigger_id": os.getenv("DEPLOYWHISPER_TRIGGER_ID"),
                },
            )
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
            share_summary=build_share_summary(
                advisory=build_advisory_summary(result.assessment, result.narrative),
                narrative=result.narrative,
                blast_radius=result.blast_radius,
                rollback_plan=result.rollback_plan,
            ),
        ).model_dump(),
        "meta": build_meta(
            api_version="v1",
            interface="cli",
            advisory_only=True,
            submitted_artifact_count=len(raw_files),
            accepted_artifact_count=pending_analysis.ready_count,
        ),
    }
    _emit_json(payload, stream=sys.stdout)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeployWhisper CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("skills", help="List built-in and custom AI skill statuses.")

    analyze_parser = subparsers.add_parser("analyze", help="Run headless advisory analysis for one or more artifacts.")
    analyze_parser.add_argument("paths", nargs="*", help="Artifact file paths to analyze.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "skills":
        raise SystemExit(_run_skills())
    if args.command == "analyze":
        raise SystemExit(_run_analyze(args.paths))

    print("DeployWhisper CLI ready: foundation-check")


if __name__ == "__main__":
    main()
