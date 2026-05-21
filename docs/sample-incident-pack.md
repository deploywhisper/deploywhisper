# Safe Sample Incident Pack

DeployWhisper includes an optional safe sample incident pack for demos and local evaluation of incident-memory behavior.

## Provenance

The bundled pack at `samples/incidents/safe-pack-v1/` contains original synthetic incidents authored for DeployWhisper documentation and tests. The records are not copied from customer data, private production incidents, or non-public postmortems.

Each sample incident declares:

- `Sample data: yes`
- provenance and permission text
- no real customer data
- no real organization names
- no non-public postmortem content
- limitations for the specific record

## Loading Behavior

The sample pack is not loaded by default. It must be explicitly loaded into a project scope through the sample incident pack service. This keeps production installs from silently mixing demo records with organization-specific incident memory.

## Limitations

The pack is for product demos, documentation, and regression tests. It is intentionally generic and should not be used as evidence of real incident rates, real outage causes, or real operational behavior.

The safety inspection checks required declarations and rejects obvious unsafe content such as common real organization names, non-example email addresses, and non-documentation public IP addresses. It is a guardrail, not a replacement for human review when adding new public sample records.
