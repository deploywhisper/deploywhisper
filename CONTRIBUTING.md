# Contributing to DeployWhisper

Thank you for your interest in contributing to **DeployWhisper** — the AI-Powered Pre-Deployment Risk Intelligence Platform. This document covers everything you need to know before submitting your first pull request.

---

## Table of contents

1. [Code of conduct](#code-of-conduct)
2. [Getting started](#getting-started)
3. [Branching strategy — Git Flow](#branching-strategy--git-flow)
4. [Branch naming conventions](#branch-naming-conventions)
5. [Workflow walkthroughs](#workflow-walkthroughs)
6. [Commit message conventions](#commit-message-conventions)
7. [Pull request process](#pull-request-process)
8. [Code standards](#code-standards)
9. [Testing](#testing)
10. [Release process](#release-process)
11. [Reporting issues](#reporting-issues)

---

## Code of conduct

All contributors are expected to be respectful, constructive, and collaborative. We are building a tool that helps engineers make safer deployment decisions — bring that same thoughtfulness to how you interact with fellow contributors.

---

## Getting started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git 2.30+

### Local setup

```bash
# Clone the repository
git clone https://github.com/pramodksahoo/ai-deploy-whisper.git
cd ai-deploy-whisper

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy the example environment file
cp .env.example .env

# Run the application
python app.py

# Run the test suite
pytest tests/ -v
```

### Verify your setup

```bash
# Lint check
ruff check .

# Tests with coverage
pytest tests/ --cov=. -v

# Docker build
docker build -t ai-deploy-whisper:local .
```

---

## Branching strategy — Git Flow

This project follows the **Git Flow** branching model, designed for versioned and scheduled releases. Every change reaches production through a structured path of branches, reviews, and CI checks.

### Long-lived branches

| Branch    | Purpose                            | Deployable? |
|-----------|------------------------------------|-------------|
| `main`    | Production-ready code. Every commit is a release. | Yes — always |
| `develop` | Integration branch. Latest accepted work lives here. | No — may be unstable |

These two branches are **permanent** and **protected**. You never commit directly to either one.

### Short-lived branches

| Branch type  | Created from | Merges into          | Lifetime       |
|--------------|--------------|----------------------|----------------|
| `feature/*`  | `develop`    | `develop`            | Days to weeks  |
| `bugfix/*`   | `develop`    | `develop`            | Days           |
| `release/*`  | `develop`    | `main` and `develop` | Days (stabilisation) |
| `hotfix/*`   | `main`       | `main` and `develop` | Hours to days  |

### How branches interact

```
main         ●────────────────────────●───────────●
              \                      / (tag v1.0) / (tag v1.0.1)
               \        release/v1.0              /
                \       ●──●──●────/   hotfix/   /
                 \     /          /    v1.0.1    /
develop    ●──●───●───●─────●───●──────●───●───●
                \        /         \      /
          feature/     /      feature/   /
          parser  ●──●        api   ●──●
```

**Key rules:**

- `main` only receives merges from `release/*` and `hotfix/*` branches.
- `develop` receives merges from `feature/*`, `bugfix/*`, and back-merges from `release/*` and `hotfix/*`.
- Every merge into `main` gets a version tag.
- Every merge into a protected branch goes through a pull request with CI checks.

---

## Branch naming conventions

All branch names must follow this pattern:

```
<type>/<identifier>-<short-description>
```

### Format rules

- Use **lowercase** letters only.
- Separate words with **hyphens** (`-`), never underscores or spaces.
- Keep the description under **5 words**.
- Include a ticket/issue number when one exists.

### Examples

| Type | Example |
|------|---------|
| Feature | `feature/DW-12-terraform-parser` |
| Feature (no ticket) | `feature/add-blast-radius-graph` |
| Bugfix | `bugfix/DW-45-fix-risk-scorer-null` |
| Release | `release/v1.0.0` |
| Hotfix | `hotfix/v1.0.1-health-endpoint-timeout` |

### What NOT to do

```
# Too vague
feature/update
bugfix/fix

# Wrong format
Feature/DW-12-Parser
feature/DW_12_terraform_parser
feature/add new terraform parser support

# Wrong base branch
feature/* branching from main (must branch from develop)
```

---

## Workflow walkthroughs

### Working on a feature

```bash
# 1. Start from the latest develop
git checkout develop
git pull origin develop

# 2. Create your feature branch
git checkout -b feature/DW-15-kubernetes-parser

# 3. Work and commit incrementally
git add parsers/kubernetes_parser.py
git commit -m "feat(parser): add base Kubernetes manifest parser"

git add tests/test_parsers/test_kubernetes.py
git commit -m "test(parser): add unit tests for K8s parser"

# 4. Push and open a pull request targeting develop
git push origin feature/DW-15-kubernetes-parser
```

Then open a PR on GitHub targeting `develop`, fill in the PR template, and request a review.

After the PR is approved and CI passes, **squash merge** via the GitHub UI. The feature branch is automatically deleted.

### Fixing a bug on develop

The workflow is identical to a feature, but use the `bugfix/` prefix:

```bash
git checkout develop && git pull origin develop
git checkout -b bugfix/DW-30-risk-score-overflow
# ... fix and commit ...
git push origin bugfix/DW-30-risk-score-overflow
# Open PR → develop
```

### Cutting a release

```bash
# 1. Branch from develop
git checkout develop && git pull origin develop
git checkout -b release/v1.0.0

# 2. Stabilise: bump version, update changelog, fix last-minute issues
# Edit pyproject.toml version field
git commit -m "chore(release): bump version to 1.0.0"
# Only bugfixes allowed on this branch — no new features

# 3. Push and open a PR targeting main
git push origin release/v1.0.0
# Open PR → main (use merge commit, not squash)

# 4. After merge, tag the release
git checkout main && git pull origin main
git tag -a v1.0.0 -m "Release v1.0.0 — Initial platform launch"
git push origin v1.0.0

# 5. Back-merge into develop so it stays in sync
git checkout develop && git pull origin develop
git merge main --no-edit
git push origin develop

# 6. Delete the release branch
git branch -d release/v1.0.0
git push origin --delete release/v1.0.0
```

### Emergency hotfix

```bash
# 1. Branch from main (production)
git checkout main && git pull origin main
git checkout -b hotfix/v1.0.1-fix-api-crash

# 2. Fix the critical issue
git commit -m "fix(api): prevent null pointer on health check"

# 3. Push and open a PR targeting main
git push origin hotfix/v1.0.1-fix-api-crash
# Open PR → main (fast-track review)

# 4. After merge, tag it
git checkout main && git pull origin main
git tag -a v1.0.1 -m "Hotfix v1.0.1 — Fix API crash on health check"
git push origin v1.0.1

# 5. Back-merge into develop
git checkout develop && git pull origin develop
git merge main --no-edit
git push origin develop
```

---

## Commit message conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/). Every commit message must match this structure:

```
<type>(<scope>): <short summary>

[optional body]

[optional footer]
```

### Types

| Type       | When to use                                      |
|------------|--------------------------------------------------|
| `feat`     | A new feature or capability                      |
| `fix`      | A bug fix                                        |
| `docs`     | Documentation changes only                       |
| `test`     | Adding or updating tests                         |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `chore`    | Build, CI, tooling, or dependency changes        |
| `perf`     | Performance improvement                          |
| `style`    | Code style (formatting, semicolons) — not CSS    |
| `ci`       | CI/CD pipeline changes                           |
| `revert`   | Reverting a previous commit                      |

### Scopes (specific to this project)

| Scope       | Covers                                  |
|-------------|-----------------------------------------|
| `parser`    | parsers/ — Terraform, K8s, Ansible, etc |
| `analysis`  | analysis/ — risk scoring, blast radius  |
| `llm`       | llm/ — narrator, providers, prompts     |
| `api`       | api/ — FastAPI routes and schemas       |
| `ui`        | ui/ — NiceGUI dashboard and components  |
| `cli`       | cli/ — command-line interface            |
| `db`        | models/ and migrations/                 |
| `skills`    | skills/ — AI skill documents            |
| `docker`    | Dockerfile, docker-compose              |
| `ci`        | .github/workflows/                      |
| `release`   | Version bumps and changelog             |

### Examples

```bash
# Good
feat(parser): add CloudFormation drift detection
fix(api): handle missing auth header gracefully
docs: add deployment guide to README
test(analysis): cover edge case in blast radius calc
chore(ci): add Docker layer caching to CI pipeline
refactor(llm): extract prompt templates into separate module
perf(parser): cache parsed Terraform state between runs

# Bad — missing type or scope
"updated parser"
"fix stuff"
"WIP"
"misc changes"
```

### Breaking changes

If your commit introduces a breaking change, add a `!` after the type/scope and explain in the footer:

```
feat(api)!: change analysis endpoint response schema

BREAKING CHANGE: The /api/v1/analyses response now returns
risk_score as a float (0.0–1.0) instead of an integer (0–100).
Clients consuming this endpoint must update their parsing logic.
```

---

## Pull request process

### Before opening a PR

1. Your branch is up to date with its base (`develop` or `main`).
2. All tests pass locally: `pytest tests/ -v`
3. Linting passes: `ruff check .`
4. Docker build succeeds: `docker build -t ai-deploy-whisper:local .`
5. You have not committed any secrets or `.env` files.

### PR requirements

- Fill out the **PR template** completely (it auto-populates when you open a PR).
- Target the correct branch (`develop` for features/bugfixes, `main` for releases/hotfixes).
- Keep PRs focused — one logical change per PR.
- PRs should ideally be under **400 lines changed**. If larger, consider splitting.

### Merge strategies

| Merge target | Strategy     | Why                                               |
|--------------|-------------|---------------------------------------------------|
| `develop`    | Squash merge | Keeps develop history clean, one commit per feature |
| `main`       | Merge commit | Preserves the full release/hotfix history          |

### Review expectations

- At least **1 approval** required before merging.
- Reviewers should check for correctness, test coverage, and adherence to this guide.
- Use GitHub's **suggestion** feature for small fixes — the author can commit them directly.
- Resolve all review conversations before merging.

---

## Code standards

### Python style

- **Formatter**: We use [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting.
- **Line length**: 100 characters max.
- **Type hints**: Required on all public function signatures.
- **Docstrings**: Required on all public modules, classes, and functions (Google style).

```python
def calculate_risk_score(changes: list[ParsedChange], context: AnalysisContext) -> RiskScore:
    """Calculate the aggregate risk score for a set of parsed changes.

    Args:
        changes: List of parsed infrastructure changes.
        context: Environmental and historical context for scoring.

    Returns:
        A RiskScore containing the numeric score and contributing factors.
    """
```

### Project structure rules

- Parsers go in `parsers/`, one file per IaC tool.
- AI Skills go in `skills/`, one markdown file per tool.
- API routes go in `api/routes/`, grouped by domain.
- All database models live in `models/`.
- Tests mirror the source structure under `tests/`.

---

## Testing

### Running tests

```bash
# Full suite
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=term-missing -v

# Specific module
pytest tests/test_parsers/ -v

# Single test
pytest tests/test_parsers/test_terraform.py::test_drift_detection -v
```

### Testing expectations

- Every new feature or bugfix must include tests.
- Maintain **80%+ code coverage** on new code.
- Use fixtures from `tests/fixtures/` for sample IaC files.
- Tests must not depend on external services (use mocks for LLM calls).

---

## Release process

We follow [Semantic Versioning](https://semver.org/):

```
MAJOR.MINOR.PATCH

v1.0.0  → First stable release
v1.1.0  → New feature (backward compatible)
v1.1.1  → Bugfix / patch
v2.0.0  → Breaking change
```

### Release checklist

1. All planned features for the release are merged into `develop`.
2. Create `release/vX.Y.Z` branch from `develop`.
3. Update version in `pyproject.toml`.
4. Update `CHANGELOG.md` with all changes since the last release.
5. Only bugfixes are allowed on the release branch — no new features.
6. Open PR from `release/vX.Y.Z` → `main`.
7. After merge, tag `main` with `vX.Y.Z`.
8. GitHub Actions automatically builds and publishes the Docker image.
9. Back-merge `main` into `develop`.
10. Delete the release branch.

---

## Reporting issues

### Bug reports

Open an issue using the **Bug Report** template and include:

- Steps to reproduce.
- Expected vs actual behaviour.
- IaC tool and file type involved (if applicable).
- Relevant logs or error messages.
- Your environment (OS, Python version, Docker version).

### Feature requests

Open an issue using the **Feature Request** template and describe:

- The problem you are trying to solve.
- Your proposed solution or approach.
- Which IaC tools or workflows are affected.

---

## Quick reference card

```
Branch from develop → feature/DW-xx-description → PR to develop (squash merge)
Branch from develop → bugfix/DW-xx-description  → PR to develop (squash merge)
Branch from develop → release/vX.Y.Z            → PR to main (merge commit) → tag → back-merge
Branch from main    → hotfix/vX.Y.Z-description → PR to main (merge commit) → tag → back-merge

Commit format:  <type>(<scope>): <summary>
PR target:      develop (features, bugs) | main (releases, hotfixes)
Versioning:     semver — MAJOR.MINOR.PATCH
```

---

*This document is maintained alongside the codebase. If a process described here changes, update this file in the same PR.*