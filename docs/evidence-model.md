# Evidence Model Foundation

DeployWhisper now has first-class domain contracts for the evidence-backed roadmap work in Epic 1.

## Pydantic Models

The new `evidence/models.py` module defines:

- `EvidenceItem`
- `Finding`
- `RiskAssessment`
- `ContextSnapshot`

These models capture the intended report backbone before the scoring and UI stories start consuming them.

## Evidence Extraction

Story 1.2 adds `evidence/extractor.py` as the adapter between parser-normalized changes and the evidence domain.

- parser output now carries a stable `change_id`
- extractor output is deterministic and traceable per normalized change
- artifact-backed evidence uses `analysis_id=0` and `finding_id=pending:<change_id>` until later scoring and persistence stories bind the evidence to a concrete report and finding
- `source_ref` is tool-scoped (`terraform://...`, `kubernetes://...`, etc.) so later UI and report work can render stable trace references without reparsing raw artifacts

## Finding Confidence

Story 1.4 adds `evidence/mappers.py` to turn scored contributors and interaction signals into reviewer-facing `Finding` objects.

- deterministic evidence-backed findings default to `confidence=1.0`
- inferred findings use a model-stated confidence when available, otherwise a heuristic floor
- shared API, CLI, and persisted report payloads now expose findings so UI surfaces can render confidence badges consistently

Story 2.4 extends findings with explicit support context:

- `explanation` carries the reviewer-facing reason for the finding, separate from the stable title/description fields
- `guidance` carries concrete verification or remediation prompts
- `evidence_classification` distinguishes `deterministic`, `derived`, `external`, `model_inferred`, and `user_provided` support
- `evidence_refs` remains the durable link from each finding to the persisted evidence items that support it

## Persistence Shape

The additive persistence layer extends `analysis_reports` with four new tables:

- `findings`
- `evidence_items`
- `risk_assessments`
- `context_snapshots`

Relationship rules introduced in this story:

- one `analysis_reports` row can own many `findings`
- one `finding` can own many `evidence_items`
- one `analysis_reports` row can own one `risk_assessments` row
- one `analysis_reports` row can own one `context_snapshots` row

## Rollout Notes

- The migration is additive and preserves existing report history.
- Existing report readers continue to work because the legacy `analysis_reports` columns are unchanged.
- The shared analysis pipeline now scores extracted `EvidenceItem` objects through `analysis/risk_engine.py` and exposes persisted `evidence_items` in UI, API, and CLI report payloads.
- The report UI now parses `source_ref` into reviewer-facing evidence inspector metadata so uploaded artifacts can link back to their report-local artifact reference, while topology and incident evidence surface a source-system badge without introducing a second evidence contract.
- Context completeness now carries topology freshness, the last imported topology timestamp, and per-tool parser success rates so review surfaces can explain coverage limits with one shared contract instead of scattered warning strings.
- Report surfaces now lift topology freshness into a first-class review cue with `STALE 30+` and `CRITICAL 90+` thresholds, plus a direct link back to topology management so reviewers can quickly discount or refresh blast radius context.
- `RiskAssessment.top_risk_contributors` now carries concrete evidence IDs so downstream findings and report views can trace the verdict back to specific evidence without reparsing raw artifacts.
- When narrative generation degrades, the shared report contract now keeps deterministic analysis artifacts intact and surfaces a visible narrative failure notice instead of fabricating fallback prose.
