# Agent JSON CLI Output

DeployWhisper provides a stable, machine-readable advisory contract for AI
coding agents:

```bash
deploywhisper analyze \
  --agent-json \
  --project payments \
  path/to/plan.json > deploywhisper-agent.json
```

The command runs the same local-first analysis and persistence path used by the
standard CLI and API. `--agent-json` changes only the successful output shape;
it does not run a second analysis or give the calling agent additional
authority.

## Safety contract

Every successful agent payload includes these immutable guardrails:

```json
{
  "schema_version": "v1",
  "advisory_only": true,
  "deployment_approval": false,
  "human_decision_required": true,
  "approval_statement": "This output is advisory and is not deployment approval. A human must review the evidence before any deployment decision."
}
```

An agent must not translate a DeployWhisper recommendation or risk score into
autonomous approval, deployment, or remediation. A human reviewer remains
responsible for the deployment decision. Non-zero CLI exit codes indicate
operational failure, not an advisory risk outcome.

## Stable v1 fields

The top-level v1 contract contains:

- `schema_version`: agent-output contract version
- `report_schema_version`: canonical persisted report version
- `report_id`: persisted analysis identifier
- `scope`: explicit project and optional workspace identity
- `verdict`: risk score, severity, recommendation, and top risk
- `advisory_only`, `deployment_approval`, `human_decision_required`, and
  `approval_statement`: non-approval guardrails
- `evidence_law`: severe-claim verification status and detail
- `evidence`: canonical evidence items with stable references and confidence
- `findings`: canonical findings, evidence references, confidence, uncertainty,
  and finding-level guidance
- `confidence`: overall verdict confidence and the confidence ledger
- `uncertainty`: flags, context summary, completeness state, and warnings
- `context_todos`: missing context that would improve future analysis
- `verification_guidance`: deduplicated human verification steps from findings,
  incident matches, scanner conflicts, and narrative guidance

Consumers should branch on `schema_version` before parsing. New optional report
details can evolve under `report_schema_version`; incompatible changes to the
agent contract require a new agent `schema_version`.

## Operational errors

Operational failures continue to use the existing structured error envelope on
standard error:

```json
{
  "error": {
    "code": "missing_artifacts",
    "message": "At least one artifact file is required.",
    "details": {}
  }
}
```

Do not treat an operational error as a low-risk or approved result.
