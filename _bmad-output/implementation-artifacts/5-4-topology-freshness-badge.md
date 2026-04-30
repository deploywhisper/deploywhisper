# Story 5.4: Topology freshness badge

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a reviewer,
I want to see how fresh the topology is in every report,
so that I know when to discount blast radius.

## Acceptance Criteria

1. Every report shows topology age prominently
2. Warning at 30+ days stale
3. Critical warning at 90+ days stale
4. Link to topology management page
5. Topology-aware evidence scoring keeps the final verdict coherent when contributors are reweighted, so high-severity topology-linked changes still drive the surfaced recommendation and top risk

### Requirement Traceability

- Primary PRD requirements: `CTX-02`, `REV-02`
- Supporting PRD / NFR / differentiation requirements: `ADM-03`, `NFR-XAI-03`
- Coverage intent: `Baseline + Delta`
- Story alignment note: Promote existing topology freshness signals into a report-native review cue and keep topology-aware verdict ordering trustworthy when those signals influence contributor weighting.

## Tasks / Subtasks

- [x] Implement AC1: Every report shows topology age prominently (AC: 1)
- [x] Implement AC2: Warning at 30+ days stale (AC: 2)
- [x] Implement AC3: Critical warning at 90+ days stale (AC: 3)
- [x] Implement AC4: Link to topology management page (AC: 4)
- [x] Implement AC5: Topology-aware evidence scoring preserves verdict coherence after contributor reweighting (AC: 5)
- [x] Add or update automated verification, fixtures, docs, and rollout notes required for this story (AC: 1, 2, 3, 4, 5)

## Dev Notes

- Epic context: Context Moat (2, 15-22 (overlaps Epics 3-4), P1).
- Epic goal: Automate topology discovery across supported infrastructure sources. Capture deployment outcomes. Build the feedback loop. This epic turns DeployWhisper from "smart on day 1" to "measurably smarter every month".
- This story contributes directly to context moat and should read freshness from shared topology/source metadata rather than assuming a single Terraform import timestamp.
- Freshness cues must make multi-source uncertainty visible, including missing, stale, partial, or mixed-freshness topology context.
- Epic 5 is the feedback/context moat. Topology freshness, deployment outcomes, and reviewer feedback are first-class context signals that must remain auditable.
- Capture history and feedback in a way that can support later calibration and backtesting without rewriting the persistence model again.
- Outcome and feedback ingestion should be explicit and operator-visible; hidden heuristics will undermine trust.
- Preserve the project-context guardrails: shared analysis core, local-first handling of raw IaC, advisory-first outputs, and deterministic tests over flaky integration assumptions.

### Project Structure Notes

- Likely implementation surfaces: services/topology_service.py, services/report_service.py, api/routes/, models/, ui/routes/, cli/, tests/, ui/routes/settings.py.
- Keep new capabilities in the correct layer instead of duplicating logic across UI, API, CLI, integrations, or docs.
- If this story introduces a new top-level folder or runtime surface, align it with the architecture document before implementation starts.

### References

- [Epics](../planning-artifacts/epics.md)
- [PRD](../planning-artifacts/prd.md)
- [Architecture](../planning-artifacts/architecture.md)
- [Project Context](../project-context.md)

## Dev Agent Record

### Agent Model Used

GPT-5

### Implementation Plan

- Add failing regression tests for report-level topology freshness badge display, 30-day warning state, 90-day critical state, and the settings-page link.
- Reuse the shared topology freshness/context completeness data to build one report-native freshness badge contract instead of duplicating age logic across surfaces.
- Harden topology-aware evidence scoring so contributor reweighting still preserves coherent verdict ordering in apply-style flows with shared topology context.
- Update the affected UI/report formatting surfaces, risk scoring logic, docs, and story tracking, then run the required validation stack before moving the story to review.

### Debug Log References

- 2026-04-29T00:00:00+05:30: Loaded Story 5.4, sprint status, and project context on a clean `develop` worktree.
- 2026-04-29T00:00:00+05:30: Created branch `feature/5-4-topology-freshness-badge`.
- 2026-04-29T18:12:36+05:30: Added shared topology freshness formatter/banner wiring across dashboard verdicts, upload result cards, dedicated report pages, shared report HTML, and a direct settings anchor for topology management.
- 2026-04-29T18:12:36+05:30: Verified Story 5.4 with focused UI regression suites, repo-wide Ruff checks, full unittest discovery, and `bash scripts/ci-local.sh` (Bandit unavailable locally, so the script reported that skip and continued green).
- 2026-04-29T18:12:36+05:30: Fixed code-review findings by adding freshness cues to history list/comparison surfaces, carrying context completeness into comparison payloads, and removing the internal settings jump from the public shared-report view while keeping a share-safe freshness explanation.
- 2026-04-30T16:00:00+05:30: Fixed the remaining Story 5.4 review findings by validating topology uploads on file selection before save, keeping the upload/save controls inside the topology settings panel, and staging the shared freshness helper modules so the branch is self-contained.
- 2026-04-30T16:00:00+05:30: Captured the direct branch-side evidence scoring hardening in `analysis/risk_engine.py` and `tests/test_analysis/test_risk_engine.py` so the story artifact matches the working branch history.
- 2026-04-30T17:00:00+05:30: Corrected the malformed-upload preview path so it no longer reuses active topology metrics, and synchronized the story file list plus sprint metadata with the full reviewed branch diff.

### Completion Notes List

- Added a shared report-native topology freshness banner with explicit `CURRENT`, `STALE 30+`, `CRITICAL 90+`, and `UNKNOWN` states so reviewers see topology age before digging into lower sections.
- Reused the existing `context_completeness.topology_freshness_days` signal instead of duplicating age logic in each surface, and pointed the new CTA at `/settings#topology-context`.
- Hardened `analysis/risk_engine.py` so topology-aware contributor reweighting keeps high-severity evidence ahead of low-severity entries when determining the surfaced verdict and top-risk summary.
- Extended UI regression coverage for dashboard, history detail, and shared report routes, and documented the rollout note in `docs/evidence-model.md`.
- Follow-up after review: the history index and history comparison views now surface topology freshness directly, and the public shared report keeps the freshness cue without linking into mutable internal settings.
- Review remediation: topology JSON selection now performs immediate validation feedback before persistence, while the explicit save action still controls when the active project topology changes.
- Scope merge note: the direct `analysis/risk_engine.py` scoring adjustment and its focused regression coverage are now explicitly part of Story 5.4 rather than branch-only parity notes.
- Bookkeeping remediation: malformed topology previews now stay isolated from the active topology state, and the story metadata now reflects the broader branch-level file set that reviewers are seeing.

### File List

- _bmad-output/implementation-artifacts/5-4-topology-freshness-badge.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- analysis/risk_engine.py
- app.py
- docs/evidence-model.md
- services/report_service.py
- services/topology_service.py
- tests/test_analysis/test_risk_engine.py
- tests/test_ui/test_history_page.py
- tests/test_ui/test_app_shell.py
- tests/test_ui/test_settings_page.py
- ui/components/analysis_history_row.py
- ui/components/report_detail_page.py
- ui/components/topology_freshness_banner.py
- ui/components/upload_panel.py
- ui/components/verdict_card.py
- ui/formatters/topology_freshness.py
- ui/routes/history.py
- ui/routes/settings.py
- ui/theme.py
