# DeployWhisper Maintainers

DeployWhisper maintainership is public so contributors can see who reviews major
project areas, which responsibilities maintainers carry, and where ownership
coverage is still thin.

## Current Maintainers

| Maintainer | GitHub handle | Current role |
| --- | --- | --- |
| Pramoda Sahoo | `@pramodksahoo` | Project owner and current maintainer for all major repository areas |

## Maintainer Responsibilities

Maintainers are expected to:

- Review pull requests for correctness, security posture, test coverage, and fit
  with the advisory-first and local-first product boundaries.
- Keep governance, contribution, security, support, roadmap, and ownership
  documents aligned with current project behavior.
- Protect sensitive artifacts by rejecting real credentials, raw production state,
  private incident data, and unsafe infrastructure samples.
- Route changes to area owners through CODEOWNERS and request additional review
  when a change crosses multiple ownership areas.
- Record meaningful decisions in planning artifacts, pull request descriptions,
  or future RFCs when changes affect architecture, security, governance, roadmap,
  or compatibility.

## Maintainer Areas

| Area | CODEOWNERS path | Primary maintainer | Review focus |
| --- | --- | --- | --- |
| `.agents` | `/.agents/` | `@pramodksahoo` | Local agent skills, workflow helpers, and project-specific automation surfaces |
| `_bmad` | `/_bmad/` | `@pramodksahoo` | BMad module configuration, workflow registration, and method metadata |
| `_bmad-output` | `/_bmad-output/` | `@pramodksahoo` | Planning, implementation, test architecture, and story lifecycle artifacts |
| `.github` | `/.github/` | `@pramodksahoo` | CI, pull request templates, release automation, repository workflows |
| `api` | `/api/` | `@pramodksahoo` | FastAPI route contracts, response envelopes, OpenAPI behavior |
| `analysis` | `/analysis/` | `@pramodksahoo` | Risk scoring, evidence rules, blast radius, rollback, incident matching |
| `cli` | `/cli/` | `@pramodksahoo` | Command-line workflows and shared-service integration |
| `data` | `/data/` | `@pramodksahoo` | Seeded local data, analytics snapshots, and topology examples |
| `docs` | `/docs/` | `@pramodksahoo` | User, operator, contributor, governance, and integration documentation |
| `evidence` | `/evidence/` | `@pramodksahoo` | Evidence models, extractors, and mapper contracts |
| `integrations` | `/integrations/` | `@pramodksahoo` | External integration boundaries and GitHub app services |
| `llm` | `/llm/` | `@pramodksahoo` | Provider adapters, prompt boundaries, narrative fallback behavior |
| `migrations` | `/migrations/` | `@pramodksahoo` | Alembic migrations and schema evolution history |
| `models` | `/models/` | `@pramodksahoo` | Database models, repositories, persistence contracts |
| `parsers` | `/parsers/` | `@pramodksahoo` | IaC parsing behavior and supported artifact boundaries |
| `samples` | `/samples/` | `@pramodksahoo` | Synthetic examples and non-sensitive demonstration artifacts |
| `schemas` | `/schemas/` | `@pramodksahoo` | JSON schemas and machine-readable contract definitions |
| `scripts` | `/scripts/` | `@pramodksahoo` | Local CI, registry publishing, analytics, and helper automation |
| `services` | `/services/` | `@pramodksahoo` | Shared orchestration and business logic used by UI, API, and CLI |
| `skills` | `/skills/` | `@pramodksahoo` | Skill manifests, registry content, harness scenarios, contribution flow |
| `tests` | `/tests/` | `@pramodksahoo` | Regression coverage, fixtures, infrastructure guardrails |
| `ui` | `/ui/` | `@pramodksahoo` | NiceGUI routes, review surfaces, accessibility-sensitive flows |

## Known Coverage Gaps

- DeployWhisper currently has one public maintainer for all major areas.
- There is no separate security-response maintainer group yet.
- There is no independent release manager or docs maintainer yet.
- Maintainer promotion, inactivity handling, and contributor ladder rules are
  planned for later governance stories.

Until those gaps are closed, contributors should expect `@pramodksahoo` to be
requested on major-area changes through CODEOWNERS.

## Ownership Updates

Ownership changes should be made in the same pull request when CODEOWNERS and
this file diverge. A valid ownership update should explain:

- The repository area being added, removed, or transferred.
- The maintainer handle responsible for review.
- Any remaining coverage gap or temporary fallback.
- Whether the change affects governance, security, release, or RFC expectations.
