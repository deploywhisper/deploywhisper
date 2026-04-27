"""Refresh the committed skill analytics snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
import os
from pathlib import Path
from urllib import error, parse, request
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "skill-analytics.json"
DEFAULT_REPOSITORY = "deploywhisper/deploywhisper"
DEFAULT_METRICS_URL = (
    "https://deploywhisper.github.io/skills-registry/skill-popularity.json"
)
GITHUB_API_BASE = "https://api.github.com"

_SEEDED_ANALYTICS: dict[str, dict[str, int]] = {
    "terraform": {"install_count": 1842, "star_count": 418, "active_issue_count": 2},
    "kubernetes": {"install_count": 1765, "star_count": 403, "active_issue_count": 3},
    "docker": {"install_count": 1448, "star_count": 332, "active_issue_count": 1},
    "ansible": {"install_count": 1320, "star_count": 286, "active_issue_count": 2},
    "git": {"install_count": 1186, "star_count": 267, "active_issue_count": 1},
    "jenkins": {"install_count": 1094, "star_count": 241, "active_issue_count": 4},
    "cloudformation": {
        "install_count": 962,
        "star_count": 228,
        "active_issue_count": 2,
    },
    "helm": {"install_count": 938, "star_count": 214, "active_issue_count": 2},
    "argocd": {"install_count": 921, "star_count": 207, "active_issue_count": 3},
    "pulumi": {"install_count": 904, "star_count": 203, "active_issue_count": 4},
    "crossplane": {"install_count": 876, "star_count": 198, "active_issue_count": 2},
    "istio": {"install_count": 861, "star_count": 192, "active_issue_count": 5},
    "nginx-ingress": {
        "install_count": 846,
        "star_count": 188,
        "active_issue_count": 2,
    },
    "cert-manager": {
        "install_count": 832,
        "star_count": 181,
        "active_issue_count": 1,
    },
    "flux": {"install_count": 819, "star_count": 176, "active_issue_count": 2},
    "tekton": {"install_count": 804, "star_count": 172, "active_issue_count": 3},
    "opa-gatekeeper": {
        "install_count": 789,
        "star_count": 168,
        "active_issue_count": 2,
    },
    "datadog-monitors": {
        "install_count": 775,
        "star_count": 164,
        "active_issue_count": 3,
    },
    "prometheus-rules": {
        "install_count": 761,
        "star_count": 159,
        "active_issue_count": 2,
    },
    "aws-cdk": {"install_count": 748, "star_count": 156, "active_issue_count": 4},
    "bicep": {"install_count": 734, "star_count": 151, "active_issue_count": 2},
    "pulumi-gcp": {"install_count": 719, "star_count": 147, "active_issue_count": 3},
    "pulumi-azure": {
        "install_count": 703,
        "star_count": 144,
        "active_issue_count": 3,
    },
    "kustomize": {"install_count": 688, "star_count": 139, "active_issue_count": 1},
    "helmfile": {"install_count": 672, "star_count": 135, "active_issue_count": 2},
    "tanka": {"install_count": 655, "star_count": 131, "active_issue_count": 2},
    "jsonnet": {"install_count": 641, "star_count": 128, "active_issue_count": 1},
    "terragrunt": {"install_count": 0, "star_count": 0, "active_issue_count": 0},
}


def iter_built_in_skill_ids() -> list[str]:
    return sorted(
        path.stem.strip().lower()
        for path in SKILLS_DIR.glob("*.md")
        if path.is_file() and path.name.lower() != "readme.md"
    )


def _load_existing(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"generated_at": "", "skills": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "DeployWhisper/skill-analytics-refresh",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _load_json_source(location: str, *, token: str | None = None) -> dict[str, object]:
    parsed = urlparse(location)
    if parsed.scheme in {"http", "https"}:
        req = request.Request(
            location,
            headers=_github_headers(token),
        )
        with request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(location).read_text(encoding="utf-8"))


def _build_issue_query(skill_id: str, repo: str) -> str:
    exact_skill = skill_id.replace('"', "")
    return (
        f"repo:{repo} is:issue is:open "
        f'(label:"skill:{exact_skill}" OR "{exact_skill}" in:title OR "{exact_skill}" in:body)'
    )


def fetch_active_issue_counts(
    skill_ids: list[str],
    *,
    repo: str,
    token: str | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for skill_id in skill_ids:
        query = parse.urlencode(
            {"q": _build_issue_query(skill_id, repo), "per_page": 1}
        )
        req = request.Request(
            f"{GITHUB_API_BASE}/search/issues?{query}",
            headers=_github_headers(token),
        )
        try:
            with request.urlopen(req, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, error.HTTPError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Failed to refresh active issue counts for {skill_id}: {exc}"
            ) from exc
        counts[skill_id] = int(payload.get("total_count", 0))
    return counts


def fetch_popularity_metrics(
    source: str,
    *,
    token: str | None = None,
) -> dict[str, dict[str, int]]:
    try:
        payload = _load_json_source(source, token=token)
    except (OSError, error.URLError, error.HTTPError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to refresh popularity metrics: {exc}") from exc

    skills_payload = payload.get("skills") if isinstance(payload, dict) else None
    if not isinstance(skills_payload, dict):
        raise RuntimeError(
            "Popularity metrics payload must contain a top-level 'skills' object."
        )

    metrics: dict[str, dict[str, int]] = {}
    for skill_id, raw_metrics in skills_payload.items():
        if not isinstance(raw_metrics, dict):
            continue
        metrics[str(skill_id).strip().lower()] = {
            "install_count": int(raw_metrics.get("install_count", 0)),
            "star_count": int(raw_metrics.get("star_count", 0)),
        }
    return metrics


def resolve_metrics_url(cli_value: str = "") -> str:
    """Resolve the popularity metrics source used by the refresh job."""

    return (
        cli_value.strip()
        or os.environ.get("DEPLOYWHISPER_SKILL_ANALYTICS_URL", "").strip()
        or DEFAULT_METRICS_URL
    )


def build_snapshot(
    path: Path,
    *,
    issue_counts: dict[str, int] | None = None,
    popularity_metrics: dict[str, dict[str, int]] | None = None,
    repo: str | None = None,
    token: str | None = None,
) -> dict[str, object]:
    built_in_skill_ids = iter_built_in_skill_ids()
    current_issue_counts = issue_counts or fetch_active_issue_counts(
        built_in_skill_ids,
        repo=repo or DEFAULT_REPOSITORY,
        token=token,
    )
    if popularity_metrics is None:
        raise RuntimeError(
            "Daily analytics refresh requires current popularity metrics for every built-in skill."
        )
    missing_metrics = sorted(
        skill_id
        for skill_id in built_in_skill_ids
        if skill_id not in popularity_metrics
    )
    if missing_metrics:
        raise RuntimeError(
            "Missing popularity metrics for built-in skills: "
            + ", ".join(missing_metrics)
        )
    skills: dict[str, dict[str, int]] = {}
    for skill_id in built_in_skill_ids:
        current_metrics = dict(popularity_metrics[skill_id])
        skills[skill_id] = {
            "install_count": int(current_metrics.get("install_count", 0)),
            "star_count": int(current_metrics.get("star_count", 0)),
            "active_issue_count": int(current_issue_counts.get(skill_id, 0)),
        }
    return {
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "skills": skills,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh skill analytics snapshot.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Snapshot file path to write.",
    )
    parser.add_argument(
        "--repo",
        default="",
        help="GitHub repository slug used for open-issue lookups.",
    )
    parser.add_argument(
        "--metrics-url",
        default="",
        help=(
            "JSON source containing per-skill install_count and star_count values. "
            f"Defaults to {DEFAULT_METRICS_URL}."
        ),
    )
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_url = resolve_metrics_url(args.metrics_url)
    auth_token = os.environ.get("DEPLOYWHISPER_ANALYTICS_TOKEN") or os.environ.get(
        "GITHUB_TOKEN"
    )
    payload = build_snapshot(
        output_path,
        popularity_metrics=fetch_popularity_metrics(metrics_url, token=auth_token),
        repo=args.repo.strip() or None,
        token=auth_token,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
