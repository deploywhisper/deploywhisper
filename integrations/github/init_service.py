"""Interactive GitHub setup wizard for installing DeployWhisper into a repo."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
from textwrap import dedent
from urllib.parse import urlparse

DEFAULT_WORKFLOW_PATH = ".github/workflows/deploywhisper.yml"
DEFAULT_APP_NOTES_PATH = ".github/deploywhisper-self-hosted-github-app.md"
DEFAULT_BRANCH_NAME = "feature/deploywhisper-github-init"
README_SECTION_START = "<!-- deploywhisper:start -->"
README_SECTION_END = "<!-- deploywhisper:end -->"
OPERATOR_DOCS_URL = (
    "https://github.com/deploywhisper/deploywhisper/blob/develop/"
    "docs/github-app-self-hosted-setup.md"
)


class GitHubInitError(RuntimeError):
    """Raised when the GitHub init wizard cannot complete."""


@dataclass(frozen=True)
class GitHubInitOptions:
    repo_path: str
    workflow_path: str
    api_endpoint: str
    enable_github_app: bool
    base_branch: str
    project_key: str | None = None
    project_id: str | None = None
    workspace_key: str | None = None
    workspace_id: str | None = None
    allow_derived_project_scope: bool = False
    github_owner: str | None = None
    github_app_name: str | None = None
    github_app_slug: str | None = None
    public_base_url: str | None = None
    branch_name: str | None = None


@dataclass(frozen=True)
class GitHubInitResult:
    repo_path: str
    workflow_path: str
    readme_path: str
    github_app_notes_path: str | None
    branch_name: str
    base_branch: str
    commit_sha: str
    pr_url: str


def collect_github_init_options(
    *,
    repo_path: str | None,
    workflow_path: str | None,
    api_endpoint: str | None,
    enable_github_app: bool | None,
    github_owner: str | None,
    github_app_name: str | None,
    github_app_slug: str | None,
    public_base_url: str | None,
    base_branch: str | None,
    project_key: str | None = None,
    project_id: str | None = None,
    workspace_key: str | None = None,
    workspace_id: str | None = None,
    allow_derived_project_scope: bool | None = None,
    branch_name: str | None,
    input_fn=input,
) -> GitHubInitOptions:
    """Collect or confirm wizard answers for repo installation."""

    repo_value = _prompt_required(
        "Repo checkout path",
        default=(repo_path or "."),
        input_fn=input_fn,
    )
    workflow_value = _prompt_required(
        "Workflow path",
        default=(workflow_path or DEFAULT_WORKFLOW_PATH),
        input_fn=input_fn,
    )
    api_value = _prompt_required(
        "DeployWhisper API endpoint",
        default=(api_endpoint or _default_api_endpoint()),
        input_fn=input_fn,
    )
    base_branch_value = _prompt_required(
        "Base branch for the pull request",
        default=(base_branch or _infer_base_branch(repo_value)),
        input_fn=input_fn,
    )
    project_key_value = (project_key or "").strip()
    project_id_value = (project_id or "").strip()
    derived_scope_value = bool(allow_derived_project_scope)
    if not project_key_value and not project_id_value and not derived_scope_value:
        project_key_value = _prompt_required(
            "DeployWhisper project key (leave blank only if the API endpoint derives project scope)",
            default="",
            input_fn=input_fn,
        )
        if not project_key_value:
            derived_scope_value = _prompt_yes_no(
                "Does the API endpoint derive project scope without action inputs?",
                default=False,
                input_fn=input_fn,
            )

    workspace_key_value = (workspace_key or "").strip()
    workspace_id_value = (workspace_id or "").strip()
    if (
        not workspace_key_value
        and not workspace_id_value
        and (project_key_value or project_id_value)
    ):
        workspace_key_value = _prompt_required(
            "DeployWhisper workspace key (optional)",
            default="",
            input_fn=input_fn,
        )

    advanced_requested = bool(enable_github_app) or any(
        [github_owner, github_app_name, github_app_slug, public_base_url]
    )
    if enable_github_app is None and not advanced_requested:
        advanced_requested = _prompt_yes_no(
            "Add advanced self-hosted GitHub App setup notes?",
            default=False,
            input_fn=input_fn,
        )

    owner_value = github_owner
    app_name_value = github_app_name
    app_slug_value = github_app_slug
    public_base_value = public_base_url
    if advanced_requested:
        owner_value = _prompt_required(
            "GitHub owner or account",
            default=(github_owner or ""),
            input_fn=input_fn,
        )
        app_name_value = _prompt_required(
            "GitHub App name",
            default=(github_app_name or "DeployWhisper"),
            input_fn=input_fn,
        )
        app_slug_value = _prompt_required(
            "GitHub App slug",
            default=(github_app_slug or "deploywhisper"),
            input_fn=input_fn,
        )
        public_base_value = _prompt_required(
            "Public DeployWhisper base URL",
            default=(public_base_url or _default_public_base_url()),
            input_fn=input_fn,
        )

    options = GitHubInitOptions(
        repo_path=repo_value,
        workflow_path=workflow_value,
        api_endpoint=api_value,
        enable_github_app=advanced_requested,
        base_branch=base_branch_value,
        project_key=project_key_value,
        project_id=project_id_value,
        workspace_key=workspace_key_value,
        workspace_id=workspace_id_value,
        allow_derived_project_scope=derived_scope_value,
        github_owner=owner_value,
        github_app_name=app_name_value,
        github_app_slug=app_slug_value,
        public_base_url=public_base_value,
        branch_name=branch_name,
    )
    _validate_options(options)
    return options


def run_github_init(options: GitHubInitOptions) -> GitHubInitResult:
    """Apply the GitHub init wizard to a target repository and open a PR."""

    _validate_options(options)
    repo_root = Path(options.repo_path).expanduser().resolve()
    if not repo_root.exists():
        raise GitHubInitError(f"Repository path does not exist: {repo_root}")
    if not repo_root.is_dir():
        raise GitHubInitError(f"Repository path is not a directory: {repo_root}")
    _require_binary("git")
    _require_binary("gh")

    _ensure_git_repo(repo_root)
    _ensure_clean_worktree(repo_root)
    _ensure_origin_remote(repo_root)

    base_branch = _checkout_base_branch(repo_root, options.base_branch)

    branch_name = _resolve_branch_name(repo_root, options.branch_name)
    _run_command(repo_root, "git", "checkout", "-b", branch_name)

    workflow_rel_path = options.workflow_path.strip().replace("\\", "/")
    workflow_path = repo_root / workflow_rel_path
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(_render_workflow(options), encoding="utf-8")

    readme_path = repo_root / "README.md"
    existing_readme = (
        readme_path.read_text(encoding="utf-8")
        if readme_path.exists()
        else f"# {repo_root.name}\n\n"
    )
    github_app_notes_path: str | None = None
    notes_rel_path = None
    if options.enable_github_app:
        notes_rel_path = DEFAULT_APP_NOTES_PATH
        notes_path = repo_root / notes_rel_path
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(
            _render_github_app_notes(options),
            encoding="utf-8",
        )
        github_app_notes_path = notes_rel_path
    readme_path.write_text(
        _upsert_readme_section(
            existing_readme,
            _render_readme_section(
                options,
                workflow_path=workflow_rel_path,
                notes_path=notes_rel_path,
            ),
        ),
        encoding="utf-8",
    )

    files_to_add = [workflow_rel_path, "README.md"]
    if github_app_notes_path:
        files_to_add.append(github_app_notes_path)

    _run_command(repo_root, "git", "add", *files_to_add)
    _run_command(
        repo_root,
        "git",
        "commit",
        "-m",
        "Add DeployWhisper GitHub review workflow",
    )
    commit_sha = _git_stdout(repo_root, "rev-parse", "HEAD")
    _run_command(repo_root, "git", "push", "-u", "origin", branch_name)
    pr_url = _gh_create_pr(
        repo_root,
        base_branch=base_branch,
        head_branch=branch_name,
        title="Add DeployWhisper GitHub review workflow",
        body=_render_pr_body(options, workflow_path=workflow_rel_path),
    )

    return GitHubInitResult(
        repo_path=str(repo_root),
        workflow_path=workflow_rel_path,
        readme_path="README.md",
        github_app_notes_path=github_app_notes_path,
        branch_name=branch_name,
        base_branch=base_branch,
        commit_sha=commit_sha,
        pr_url=pr_url,
    )


def _render_workflow(options: GitHubInitOptions) -> str:
    api_endpoint = options.api_endpoint.strip()
    scope_lines = _render_action_scope_inputs(options)
    workflow = dedent(
        f"""\
        name: DeployWhisper

        on:
          pull_request:
            types: [opened, synchronize, reopened]

        permissions:
          contents: read
          pull-requests: write

        jobs:
          deploywhisper:
            runs-on: ubuntu-latest
            env:
              DEPLOYWHISPER_API_URL: {api_endpoint}
            steps:
              - uses: actions/checkout@v4
                with:
                  fetch-depth: 0
              - uses: deploywhisper/analyze-action@v1
                with:
                  api-url: ${{{{ env.DEPLOYWHISPER_API_URL }}}}
                  api-token: ${{{{ secrets.DEPLOYWHISPER_API_TOKEN }}}}
        """
    )
    return f"{workflow.rstrip()}\n{scope_lines}\n"


def _render_readme_section(
    options: GitHubInitOptions,
    *,
    workflow_path: str,
    notes_path: str | None,
) -> str:
    lines = [
        "## DeployWhisper",
        "",
        "This repository uses DeployWhisper for advisory-only deployment risk review in pull requests.",
        "",
        "### GitHub workflow",
        "",
        f"- Workflow file: `{workflow_path}`",
        f"- Configured API endpoint: `{options.api_endpoint}`",
        "- Optional secret: `DEPLOYWHISPER_API_TOKEN` for protected DeployWhisper APIs",
        *_scope_readme_lines(options),
        "- The `DeployWhisper / Risk Analysis` check is advisory-only and should not be configured as a required status check",
        "",
        "### Configuration example",
        "",
        "Set these in your repository before merging the PR:",
        "",
        f"- `DEPLOYWHISPER_API_URL={options.api_endpoint}`",
        "- `DEPLOYWHISPER_API_TOKEN=<optional bearer token>`",
        *_scope_configuration_lines(options),
    ]
    if options.enable_github_app:
        lines.extend(
            [
                "",
                "### Advanced self-hosted GitHub App",
                "",
                "- This setup keeps the Action-first workflow and adds self-hosted GitHub App guidance as an advanced path.",
                f"- GitHub owner/account: `{options.github_owner}`",
                f"- GitHub App name: `{options.github_app_name}`",
                f"- GitHub App slug: `{options.github_app_slug}`",
                f"- Public DeployWhisper base URL: `{options.public_base_url}`",
                f"- Operator guide: {OPERATOR_DOCS_URL}",
            ]
        )
        if notes_path:
            lines.append(f"- Repo-local setup notes: `{notes_path}`")
    return "\n".join(lines).strip()


def _render_github_app_notes(options: GitHubInitOptions) -> str:
    return dedent(
        f"""\
        # Advanced Self-Hosted DeployWhisper GitHub App

        This repository selected the advanced self-hosted GitHub App path in addition
        to the default Action-first workflow.

        ## Selected values

        - GitHub owner/account: `{options.github_owner}`
        - GitHub App name: `{options.github_app_name}`
        - GitHub App slug: `{options.github_app_slug}`
        - Public DeployWhisper base URL: `{options.public_base_url}`

        ## Next steps

        1. Keep the Action-first workflow in `{options.workflow_path}` for PR-triggered analysis.
        2. Create the self-hosted GitHub App in your own GitHub account or organization.
        3. Point the webhook and callback URLs at `{options.public_base_url}`.
        4. Follow the operator guide: {OPERATOR_DOCS_URL}
        5. Keep `DeployWhisper / Risk Analysis` advisory-only in branch protection.
        """
    )


def _render_pr_body(options: GitHubInitOptions, *, workflow_path: str) -> str:
    lines = [
        "## Summary",
        "",
        "- add the DeployWhisper GitHub workflow",
        "- document the API endpoint and advisory-only check behavior",
    ]
    if options.enable_github_app:
        lines.append("- add advanced self-hosted GitHub App setup notes")
    lines.extend(
        [
            "",
            "## Files",
            "",
            f"- `{workflow_path}`",
            "- `README.md`",
        ]
    )
    if options.enable_github_app:
        lines.append(f"- `{DEFAULT_APP_NOTES_PATH}`")
    return "\n".join(lines)


def _render_action_scope_inputs(options: GitHubInitOptions) -> str:
    lines: list[str] = []
    if options.project_key:
        lines.append(f"          project-key: {_yaml_string(options.project_key)}")
    if options.project_id:
        lines.append(f"          project-id: {_yaml_string(options.project_id)}")
    if options.workspace_key:
        lines.append(f"          workspace-key: {_yaml_string(options.workspace_key)}")
    if options.workspace_id:
        lines.append(f"          workspace-id: {_yaml_string(options.workspace_id)}")
    if (
        options.allow_derived_project_scope
        and not options.project_key
        and not options.project_id
    ):
        lines.append('          allow-derived-project-scope: "true"')
    else:
        lines.append('          allow-derived-project-scope: "false"')
    return "\n".join(lines)


def _yaml_string(value: str) -> str:
    return json.dumps(value.strip())


def _scope_readme_lines(options: GitHubInitOptions) -> list[str]:
    if options.project_key:
        scope = f"Project scope: `project-key={options.project_key.strip()}`"
    elif options.project_id:
        scope = f"Project scope: `project-id={options.project_id.strip()}`"
    else:
        scope = "Project scope: derived by the configured DeployWhisper endpoint"
    lines = [f"- {scope}"]
    if options.workspace_key:
        lines.append(
            f"- Workspace scope: `workspace-key={options.workspace_key.strip()}`"
        )
    if options.workspace_id:
        lines.append(
            f"- Workspace scope: `workspace-id={options.workspace_id.strip()}`"
        )
    return lines


def _scope_configuration_lines(options: GitHubInitOptions) -> list[str]:
    lines: list[str] = []
    if options.project_key:
        lines.append(f"- `DEPLOYWHISPER_PROJECT_KEY={options.project_key.strip()}`")
    if options.project_id:
        lines.append(f"- `DEPLOYWHISPER_PROJECT_ID={options.project_id.strip()}`")
    if options.workspace_key:
        lines.append(f"- `DEPLOYWHISPER_WORKSPACE_KEY={options.workspace_key.strip()}`")
    if options.workspace_id:
        lines.append(f"- `DEPLOYWHISPER_WORKSPACE_ID={options.workspace_id.strip()}`")
    if (
        options.allow_derived_project_scope
        and not options.project_key
        and not options.project_id
    ):
        lines.append(
            "- Project scope is derived by the configured DeployWhisper endpoint."
        )
    return lines


def _upsert_readme_section(existing: str, section: str) -> str:
    rendered_section = f"{README_SECTION_START}\n{section}\n{README_SECTION_END}\n"
    if README_SECTION_START in existing and README_SECTION_END in existing:
        before, _, remainder = existing.partition(README_SECTION_START)
        _, _, after = remainder.partition(README_SECTION_END)
        prefix = before.rstrip()
        suffix = after.lstrip("\n")
        blocks = [prefix, rendered_section.rstrip()]
        if suffix:
            blocks.append(suffix.rstrip())
        return "\n\n".join(block for block in blocks if block) + "\n"
    stripped = existing.rstrip()
    if stripped:
        return f"{stripped}\n\n{rendered_section}"
    return rendered_section


def _default_api_endpoint() -> str:
    base_url = _default_public_base_url()
    if not base_url:
        return "http://127.0.0.1:8080/api/v1/analyses"
    return f"{base_url.rstrip('/')}/api/v1/analyses"


def _default_public_base_url() -> str:
    return (
        os.getenv("APP_BASE_URL")
        or os.getenv("PUBLIC_APP_URL")
        or "https://deploywhisper.example.com"
    )


def _prompt_required(prompt: str, *, default: str, input_fn) -> str:
    raw = input_fn(f"{prompt} [{default}]: ").strip()
    return raw or default


def _prompt_yes_no(prompt: str, *, default: bool, input_fn) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = input_fn(f"{prompt} [{suffix}]: ").strip().lower()
    if not raw:
        return default
    if raw in {"y", "yes"}:
        return True
    if raw in {"n", "no"}:
        return False
    raise GitHubInitError(f"Expected yes or no answer for: {prompt}")


def _validate_options(options: GitHubInitOptions) -> None:
    if not options.workflow_path.strip():
        raise GitHubInitError("Workflow path is required.")
    if not options.base_branch.strip():
        raise GitHubInitError("Base branch is required.")
    _validate_url(options.api_endpoint, field_name="API endpoint")
    _validate_scope_options(options)
    if options.enable_github_app:
        if not options.github_owner:
            raise GitHubInitError(
                "GitHub owner/account is required for GitHub App setup."
            )
        if not options.github_app_name:
            raise GitHubInitError("GitHub App name is required for GitHub App setup.")
        if not options.github_app_slug:
            raise GitHubInitError("GitHub App slug is required for GitHub App setup.")
        _validate_url(
            options.public_base_url or "",
            field_name="public DeployWhisper base URL",
        )


def _validate_scope_options(options: GitHubInitOptions) -> None:
    project_key = (options.project_key or "").strip()
    project_id = (options.project_id or "").strip()
    workspace_key = (options.workspace_key or "").strip()
    workspace_id = (options.workspace_id or "").strip()
    if project_key and project_id:
        raise GitHubInitError(
            "Provide only one project scope: project key or project id."
        )
    if workspace_key and workspace_id:
        raise GitHubInitError(
            "Provide only one workspace scope: workspace key or workspace id."
        )
    for label, value in {
        "project id": project_id,
        "workspace id": workspace_id,
    }.items():
        if value and (not value.isdecimal() or int(value) <= 0):
            raise GitHubInitError(f"DeployWhisper {label} must be a positive number.")
    if (workspace_key or workspace_id) and not project_key and not project_id:
        raise GitHubInitError("Workspace scope requires project key or project id.")
    if not project_key and not project_id and not options.allow_derived_project_scope:
        raise GitHubInitError(
            "DeployWhisper project scope is required. Provide project key/project id "
            "or explicitly enable derived project scope."
        )


def _validate_url(value: str, *, field_name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise GitHubInitError(f"{field_name} must be an absolute http(s) URL.")


def _require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise GitHubInitError(f"Required command not found on PATH: {name}")


def _ensure_git_repo(repo_root: Path) -> None:
    marker = _git_stdout(repo_root, "rev-parse", "--is-inside-work-tree")
    if marker != "true":
        raise GitHubInitError(f"Target path is not a git repository: {repo_root}")


def _ensure_clean_worktree(repo_root: Path) -> None:
    status = _git_stdout(repo_root, "status", "--porcelain")
    if status:
        raise GitHubInitError(
            "Target repository has uncommitted changes. Commit or stash them before running deploywhisper github init."
        )


def _ensure_origin_remote(repo_root: Path) -> None:
    remote = _git_stdout(repo_root, "remote", "get-url", "origin")
    if not remote:
        raise GitHubInitError(
            "Target repository does not have an origin remote configured."
        )


def _infer_base_branch(repo_path: str) -> str:
    repo_root = Path(repo_path).expanduser().resolve()
    if not repo_root.exists() or shutil.which("git") is None:
        return "main"
    if _git_ref_exists(repo_root, "refs/heads/develop") or _git_ref_exists(
        repo_root,
        "refs/remotes/origin/develop",
    ):
        return "develop"
    completed = _run_command(
        repo_root,
        "git",
        "symbolic-ref",
        "refs/remotes/origin/HEAD",
        check=False,
    )
    if completed.returncode == 0:
        ref = completed.stdout.strip()
        prefix = "refs/remotes/origin/"
        if ref.startswith(prefix):
            branch_name = ref.removeprefix(prefix).strip()
            if branch_name:
                return branch_name
    return "main"


def _checkout_base_branch(repo_root: Path, branch_name: str) -> str:
    cleaned = branch_name.strip()
    if _git_ref_exists(repo_root, f"refs/heads/{cleaned}"):
        _run_command(repo_root, "git", "checkout", cleaned)
        return cleaned
    if _git_ref_exists(repo_root, f"refs/remotes/origin/{cleaned}"):
        _run_command(
            repo_root,
            "git",
            "checkout",
            "-b",
            cleaned,
            f"origin/{cleaned}",
        )
        return cleaned
    raise GitHubInitError(f"Base branch does not exist locally or on origin: {cleaned}")


def _resolve_branch_name(repo_root: Path, requested: str | None) -> str:
    candidate = (requested or DEFAULT_BRANCH_NAME).strip() or DEFAULT_BRANCH_NAME
    if not _branch_exists(repo_root, candidate):
        return candidate
    suffix = 2
    while _branch_exists(repo_root, f"{candidate}-{suffix}"):
        suffix += 1
    return f"{candidate}-{suffix}"


def _branch_exists(repo_root: Path, branch_name: str) -> bool:
    return _git_ref_exists(repo_root, f"refs/heads/{branch_name}")


def _git_ref_exists(repo_root: Path, ref_name: str) -> bool:
    completed = _run_command(
        repo_root,
        "git",
        "show-ref",
        "--verify",
        "--quiet",
        ref_name,
        check=False,
    )
    return completed.returncode == 0


def _gh_create_pr(
    repo_root: Path,
    *,
    base_branch: str,
    head_branch: str,
    title: str,
    body: str,
) -> str:
    completed = _run_command(
        repo_root,
        "gh",
        "pr",
        "create",
        "--base",
        base_branch,
        "--head",
        head_branch,
        "--title",
        title,
        "--body",
        body,
    )
    return completed.stdout.strip()


def _git_stdout(repo_root: Path, *args: str) -> str:
    completed = _run_command(repo_root, "git", *args)
    return completed.stdout.strip()


def _run_command(
    repo_root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        stderr = (
            completed.stderr.strip() or completed.stdout.strip() or "unknown failure"
        )
        raise GitHubInitError(f"Command failed ({' '.join(args)}): {stderr}")
    return completed
