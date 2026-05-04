# DeployWhisper RFC Process

DeployWhisper uses public RFCs for major decisions that change project direction, trust boundaries, or long-lived contributor expectations. The process keeps architecture, roadmap, governance, and security decisions auditable and traceable to the PRD and architecture.

## When An RFC Is Required

Open an RFC before implementation when a proposed change affects any of these areas:

- Architecture, runtime boundaries, persistence contracts, report schemas, API contracts, CLI contracts, or supported integration surfaces.
- Governance, maintainer ownership, contribution policy, release policy, community process, or CNCF readiness posture.
- Security posture, local-first boundaries, raw artifact handling, credential handling, signing, provenance, or vulnerability disclosure expectations.
- Roadmap scope, supported platforms, compatibility guarantees, deprecations, or public project priorities.

Routine bug fixes, small documentation updates, test-only changes, and implementation details that do not change public behavior usually do not need an RFC. Maintainers can request an RFC during issue or pull request review if the change is larger than it first appears.

## RFC Lifecycle

1. Copy `docs/rfcs/0000-template.md` to `docs/rfcs/NNNN-short-title.md`.
2. Fill every required section before requesting review.
3. Open a pull request that adds the RFC file and links any related issue, PRD section, architecture section, or prior decision.
4. Keep the RFC in `Proposed` while discussion is active.
5. Move the RFC to `Accepted`, `Rejected`, or `Withdrawn` when maintainers record the outcome.

Accepted RFCs must link back to relevant PRD sections and architecture sections in the `PRD and Architecture Links` section. If the decision intentionally diverges from the current PRD or architecture, the RFC must identify the follow-up planning artifact update that brings them back into alignment.

## Required Sections

Every RFC must include:

- Summary.
- Motivation.
- PRD and architecture links.
- Detailed design.
- Security and privacy considerations.
- Compatibility and migration notes.
- Alternatives considered.
- Review plan.
- Decision record.

Use the template as the source of truth for the exact headings.

## Review Expectations

RFC review happens in public pull request discussion unless the topic requires private security handling under `SECURITY.md`.

- The minimum review window is 7 calendar days for architecture, governance, security, roadmap, compatibility, or deprecation RFCs.
- The pull request must request review from the relevant CODEOWNERS area.
- Security-affecting RFCs must include a maintainer familiar with the local-first and raw-artifact boundaries.
- Governance or roadmap RFCs must include maintainer review from the project governance owners.
- Architecture RFCs must explain how the proposal preserves the shared analysis core and advisory-first posture.
- Reviewers should check whether linked PRD and architecture sections are current and whether follow-up planning updates are required.

Maintainers may extend the review window for high-impact or contested changes. Emergency security work may proceed faster, but the RFC must still be recorded after the private remediation path is complete.

## Decision Recording

The decision record must use one of these states:

- `Proposed`: under active review.
- `Accepted`: approved for implementation or already implemented.
- `Rejected`: reviewed and declined.
- `Withdrawn`: closed by the author before a final maintainer decision.

Accepted decisions must record:

- The approving maintainers.
- The decision date.
- The linked PRD and architecture sections.
- Required follow-up issues, stories, documentation updates, or migration notes.
- Any compatibility, security, or governance constraints future maintainers must preserve.

Rejected and withdrawn RFCs should still keep their rationale so future contributors do not repeat the same proposal without new evidence.

## File Naming

Use `docs/rfcs/NNNN-short-title.md`.

- `NNNN` is the next available four-digit number.
- Use lowercase words separated by hyphens.
- Keep the title short and descriptive.

Example: `docs/rfcs/0001-report-schema-versioning.md`
