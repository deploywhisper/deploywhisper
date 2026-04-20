# Evidence Model Foundation

DeployWhisper now has first-class domain contracts for the evidence-backed roadmap work in Epic 1.

## Pydantic Models

The new `evidence/models.py` module defines:

- `EvidenceItem`
- `Finding`
- `RiskAssessment`
- `ContextSnapshot`

These models capture the intended report backbone before the scoring and UI stories start consuming them.

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
- Later Epic 1 stories will wire the shared analysis pipeline to populate these tables and models.
