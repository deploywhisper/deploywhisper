---
project_name: 'ai-deploy-whisper'
user_name: 'psaho01'
date: '2026-04-20'
sections_completed:
  ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 32
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- Python: code targets Python 3.11 runtime in CI/Docker; `pyproject.toml` currently allows `>=3.10`, so do not introduce syntax that would break 3.10 without intentionally raising the floor.
- Web runtime: NiceGUI `3.10.0` and FastAPI `0.135.2` share one app in `app.py`.
- Persistence: SQLAlchemy `2.0.49`, Alembic `1.18.4`, default SQLite database at `data/deploywhisper.db`.
- Data contracts: Pydantic `2.12.2` models and `Field(...)` metadata.
- LLM layer: LiteLLM `1.83.0`; default local mode is Ollama via `config.Settings`.
- Infra parsing: `python-hcl2`, `ruamel.yaml`, `pyyaml`, `deepdiff`; supported tools are Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation.
- Delivery surfaces: shared UI, REST API, and CLI all sit over the same analysis services.
- Validation path: repository tests are standard-library `unittest`; local CI helper lives in `scripts/ci-local.sh`.

## Critical Implementation Rules

### Language-Specific Rules

- Keep Python modules, functions, and test files in `snake_case`; test classes use the `*Tests` suffix.
- Match the repo’s file prologue pattern: `from __future__ import annotations` plus a short module docstring.
- Use Pydantic models for API/service payload contracts and typed return shapes; avoid ad-hoc dict contracts at public boundaries.
- Keep environment-derived settings centralized in `config.py`; when tests mutate env vars, reload `config`, `models.tables`, and `models.database` before exercising behavior.

### Framework-Specific Rules

- Preserve the shared-core architecture: API routes, UI flows, and CLI commands must reuse service-layer orchestration instead of duplicating analysis logic.
- Register HTTP endpoints under `/api/v1` through `api/routes/*` and keep FastAPI error handling on the existing `ApiRoute` / `ApiError` envelope pattern.
- Treat `app.py` as the canonical runtime entrypoint: NiceGUI pages, FastAPI routes, OpenAPI docs, and DB startup are composed there.
- Keep the pipeline ordering intact: intake/parse -> assess -> blast radius -> rollback -> incident match -> narrative -> persist.
- Narrative generation is downstream of scoring. If the LLM path fails, degrade gracefully and preserve deterministic report output instead of failing the analysis.
- Preserve the advisory-only product contract. Current summaries intentionally set `should_block=False`; do not introduce blocking enforcement behavior unless product requirements explicitly change.
- Preserve the local-first boundary: raw IaC/artifact content stays local; external model calls should only receive structured summaries, never raw uploads.
- Skill resolution is filename-based: built-in skills live in `skills/`, custom overrides/new skills live in `skills/custom/`, and frontmatter is stripped before runtime use.

### Testing Rules

- Add tests in the existing layer-specific layout: `tests/test_api`, `tests/test_services`, `tests/test_analysis`, `tests/test_parsers`, `tests/test_ui`, `tests/test_cli`, `tests/test_infra`.
- Default to `unittest`-style tests that pass under `python -m unittest discover -q`; do not assume `pytest` is the authoritative runner just because older docs mention it.
- Use `fastapi.testclient.TestClient` for API and app-shell coverage instead of bespoke HTTP harnesses.
- For persistence-related tests, use `tempfile.TemporaryDirectory()`, override `DATABASE_URL`, and initialize a fresh database for isolation.
- Patch unstable boundaries such as LLM generation, incident matching, or filesystem-dependent helpers so tests stay deterministic and local.
- When fixing behavior, add or update a regression test in the matching layer before broad refactors.

### Code Quality & Style Rules

- Prefer small, reversible changes that reuse existing services, repositories, schemas, and formatters before adding new abstractions.
- Keep user-facing copy consistent with the product posture: evidence-backed, advisory-first, explicit about uncertainty, never overclaiming certainty.
- Preserve separation by layer: parsers normalize input, analysis modules score/derive risk, services orchestrate, API/UI/CLI adapt outputs.
- Use the shared schema helpers (`build_meta`, response models, formatter helpers) for external surfaces instead of inventing one-off payload shapes.
- Do not hardcode secrets or provider credentials. Read them through environment-backed settings only.

### Development Workflow Rules

- When instructions conflict, prefer the implemented codebase plus `README.md`, `docs/ci.md`, and current scripts over stale contributor prose.
- Validate changes with the repo’s real commands after edits. For Python changes, run `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .` (or the equivalent through `bash scripts/ci-local.sh`) before concluding work. At minimum, keep relevant `unittest` coverage green; use `bash scripts/ci-local.sh` when the touched area is broad enough.
- For AI-agent story execution, follow `CONTRIBUTING.md` Git Flow: start from `develop`, create one short-lived `feature/<identifier>-<short-description>` branch per story (or `bugfix/...` for defect work), commit incrementally on that branch, and target `develop` with a PR. Do not commit directly to `main` or `develop`.
- For AI-agent story closure, the final reviewer must verify the story is on a Git Flow-compliant short-lived branch and must push that branch to the remote before declaring the story lifecycle complete. A story reviewed on `main`, `develop`, or detached HEAD is not considered properly closed.
- For cleanup/refactor work, write a cleanup plan first and lock behavior with regression tests before editing.
- No new dependencies without explicit request. Prefer deletion over addition and keep diffs reviewable.
- If a commit is requested, use the Lore commit protocol from `AGENTS.md` with intent-first subject and native git trailers.

### Critical Don't-Miss Rules

- Do not bypass upload classification and size-limit behavior; API/CLI intake must continue enforcing supported-artifact and aggregate-size checks.
- Do not duplicate analysis decisions across surfaces. New output fields should be derived once in shared services, then rendered in UI/API/CLI.
- Do not hide uncertainty. If parser coverage is partial, topology is missing, or narrative degraded, surface warnings explicitly rather than smoothing them over.
- Do not assume richer deployment infrastructure than the repo currently has: default operation is self-hosted, single-container, SQLite-backed, and local-first.
- Do not let planning artifacts outrun the implementation baseline. Use them for direction, but ground changes in the current code paths and tests.

---

## Usage Guidelines

**For AI Agents:**

- Read this file before implementing code in this repository.
- Follow the current codebase and these rules when they are more specific than high-level planning docs.
- When unsure, choose the more conservative, advisory-first, local-first option.
- Update this file when a new pattern becomes stable across the codebase.

**For Humans:**

- Keep this document lean; add only rules that prevent real implementation mistakes.
- Update it when tooling, validation commands, or architecture boundaries materially change.
- Remove rules that become obsolete or are contradicted by the current codebase.

Last Updated: 2026-04-20
