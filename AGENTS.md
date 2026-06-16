# AGENTS.md

## Purpose
This repository uses the BMad Method as the primary workflow for planning, architecture, implementation, and review.

Treat BMad artifacts as the default source of truth for what to build, why it matters, and what should happen next. Prefer BMad workflows over ad hoc implementation when the work affects product scope, architecture, security, integrations, release flow, or multiple stories.

## Start Here Every Session
1. Run `bmad-help` first.
   - Use it to inspect project state, detect completed artifacts, and recommend the next required step.
   - If you are unsure what workflow to run, ask `bmad-help` instead of guessing.
2. Check for project context at `_bmad-output/project-context.md`.
   - When it exists, treat it as mandatory implementation guidance.
   - When it is missing or stale for an existing codebase, run `bmad-generate-project-context` and review the generated file before implementation.
3. Prefer one BMad workflow per session/task.
   - BMad works best with fresh context boundaries.
   - For Codex CLI, treat each major workflow as a separate task whenever practical.
4. After every major workflow, ask `bmad-help` what should happen next.

## Core Operating Model
Follow the standard BMad phase order unless `bmad-help` explicitly indicates a different next step:
1. **Analysis** — optional research, brainstorming, product brief, PRFAQ
2. **Planning** — PRD / requirements
3. **Solutioning** — architecture and implementation readiness
4. **Implementation** — sprint planning, story creation, development, review, retrospective

For this repository, planning artifacts already exist, so default to **implementation mode** unless the current task is explicitly about changing requirements, architecture, or epic/story structure.

## Source Of Truth In This Repo
When these files exist, use them in this order:

1. `_bmad-output/project-context.md`
   - Repository-specific implementation rules and conventions.
2. `_bmad-output/planning-artifacts/prd.md`
   - Product scope, goals, requirements, and priorities.
3. `_bmad-output/planning-artifacts/architecture.md`
   - Technical decisions, constraints, system shape, integration boundaries.
4. `_bmad-output/planning-artifacts/epics.md`
   - Epic structure and implementation sequencing.
5. `_bmad-output/implementation-artifacts/sprint-status.yaml`
   - Current execution state for epics and stories.
6. `README.md` and codebase structure
   - Current implementation truth and run/test commands.

If planning artifacts become sharded, follow BMad's whole-document-first rule:
- `document-name.md` takes precedence over `document-name/index.md`
- only rely on sharded docs when the whole document is removed or intentionally replaced

## Recommended Workflow For This Project
Because DeployWhisper already has PRD, architecture, and epics, use this default sequence for delivery work:

### When starting or resuming implementation
1. Run `bmad-help`
2. Review:
   - `_bmad-output/project-context.md`
   - PRD
   - architecture
   - epics
   - current sprint status
3. If planning documents changed materially, run `bmad-check-implementation-readiness` before coding.
4. If sprint tracking is missing or stale, run `bmad-sprint-planning`.

### For each story
1. Run `bmad-create-story`
2. Run `bmad-dev-story`
3. Run `bmad-code-review` (recommended, not optional in spirit)
4. Implement any required fixes from review
5. Update sprint/story status and verification notes

### After completing an epic
1. Run retrospective (`bmad-retrospective`) if available in the installed module set.
2. If QA or test automation workflows are installed, use them after story completion and code review.
3. Re-check whether the next epic requires new architecture, context, or document updates.

### When scope or assumptions change
- Use `bmad-correct-course` instead of silently drifting from the PRD/architecture.
- Update the affected planning artifacts before or alongside code changes.

## Project-Specific Engineering Rules For DeployWhisper
- Preserve the product's **local-first** and **advisory-first** posture unless the active epic explicitly changes that behavior.
- Keep one shared analysis core across UI, API, and CLI unless architecture docs explicitly direct a change.
- Favor small, reviewable increments over large speculative rewrites.
- Respect the existing Python-first stack and current repository shape unless the architecture or epic explicitly introduces a migration.
- Prefer deterministic logic and evidence-backed reasoning over “AI magic” in risk-sensitive code paths.
- Avoid introducing features that persist secrets, raw credentials, or unsafe infrastructure artifacts.
- Avoid committing real infrastructure state, secrets, or production-sensitive samples.
- When behavior changes, update code, tests, and docs together.

## Current Repository Shape
Use the existing layout unless an approved architecture change says otherwise:

- `api/` — FastAPI routes and schemas
- `analysis/` — risk scoring, blast radius, rollback, incident matching
- `cli/` — headless analysis commands
- `llm/` — narrative generation and skill context
- `models/` — ORM tables and repositories
- `parsers/` — tool-specific parsers
- `services/` — orchestration, persistence, settings, topology workflows
- `frontend/` — React SPA screens, UI primitives, routes, e2e tests, and static build
- `tests/` — API, CLI, parser, service, UI, and infrastructure tests

## Frontend / UI
DeployWhisper now uses the React SPA in `frontend/` as the only web UI framework. `docs/ui-migration-plan.md` remains the historical migration contract; for current UI work, follow `frontend/src/theme`, `frontend/src/components/ui`, and `docs/design/deploywhisper-redesign-v3.jsx`. When an exact visual value differs, the mockup wins.

Ground rules:
- This is a UI/UX modernization and migration, not a backend, analysis, API, data-model, CLI, or GitHub Action rewrite.
- Backend work for UI must stay additive: read-only stats/project endpoints, additive serializer fields, or API support for existing React screens. Ship backend-for-UI work in its own labeled PR when it changes backend behavior.
- Current sanctioned UX includes the single global search plus ProjectSwitcher, Latest Briefing dashboard card, tabbed report screen, inline finding feedback, permanent report URLs, and retirement of the dashboard result countdown setting.
- If a screen appears to need flow, validation, or API-contract changes beyond the current React contract, stop and raise the question instead of guessing.
- No CDN imports in production code. Fonts must be packaged locally; icons use `lucide-react`.

Operating rules:
- Use one task, one branch, one PR for UI work, and state the active task before writing code.
- The target stack is Vite + React 18 + TypeScript + Tailwind CSS, built to static files and served by the existing FastAPI app. Node must not be present in the runtime image.
- Do not restyle, approximate, or "improve" approved design values; bind UI to real APIs and never hard-code mockup demo data.
- Before every UI PR, run the compose verification loop: `docker compose up -d --build`, wait for `http://localhost:8080/api/v1/health`, seed data, run Playwright against `BASE_URL=http://localhost:8080`, capture required screenshots from the composed app, then `docker compose down`.
- PR descriptions must include the design/plan reference, documentation rows updated when applicable, verification output, and screenshots.

## Validation Requirements
After changing code or config, run the most relevant validation available for the scope of your change.

Minimum expectations:
- Run the unit/integration suite:
  - `./.venv/bin/python -m unittest discover -q`
- For broader local CI coverage, run:
  - `bash scripts/ci-local.sh`
- If the app behavior changed, run the app locally when possible:
  - `python app.py`
- If a story changes any React route, UI primitive, rendered report/history/dashboard/settings/skills surface, browser interaction, keyboard behavior, or accessibility semantics, run browser-side Playwright validation and record the command/result in the story Dev Agent Record before moving the story to review:
  - `npm run test:ui-review` for review/report flows
  - `RUN_UI_A11Y=1 bash scripts/ci-local.sh` when the full local UI lane is needed
  - If no UI surface is touched, record `UI validation not applicable` instead of silently skipping UI validation.
- If dependencies are not installed, bootstrap locally:
  - `python3 -m venv .venv`
  - `source .venv/bin/activate`
  - `python -m pip install --upgrade pip`
  - `pip install -r requirements.txt`

When reporting completion:
- include what changed
- include what commands were run
- include the result of validation
- include any known follow-up or risk

## Documentation Discipline
- Keep planning artifacts aligned with actual implementation.
- Do not let code drift silently from the PRD or architecture.
- If implementation intentionally diverges from the current plan, update the relevant BMad artifacts in the same workstream.
- Update README/setup/docs whenever developer workflow, configuration, or behavior changes.
- Only use document sharding if your tool/model genuinely struggles with large files; otherwise keep whole documents.

## Review Discipline
For meaningful changes, prefer layered review:
1. BMad workflow review (`bmad-code-review`)
2. repo tests / local CI
3. manual sanity check for affected UI/API/CLI behavior
4. document update if user-visible or architecture-relevant

For high-risk areas, also consider:
- `bmad-review-adversarial-general`
- `bmad-review-edge-case-hunter`

## Security And Safety Rules
- Never commit secrets, API keys, `.env` contents, PEM files, private keys, credentials files, or real `*.tfstate` files.
- Use synthetic fixtures for tests.
- Keep provider API keys out of persistent storage.
- Treat uploaded artifacts and incident data as potentially sensitive.
- Preserve the repo's local-first processing assumptions unless architecture docs explicitly approve otherwise.

## When Unsure
- Ask `bmad-help`.
- Re-read `_bmad-output/project-context.md`.
- Re-check PRD, architecture, and epic context before coding.
- Prefer the smallest correct change that moves the active story forward.
- If the requested task is larger than a story, stop and move back to the appropriate BMad planning workflow first.
