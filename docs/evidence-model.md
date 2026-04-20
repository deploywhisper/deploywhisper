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
- The shared analysis pipeline now extracts evidence items alongside the current parser output; later Epic 1 stories will bind those items into findings and persisted report records.
