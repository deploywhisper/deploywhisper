# Sprint Change Proposal — Cut Epic 17 Back to v1.6.0

Date: 2026-11-11
Status: Approved under the maintainer's delegated completion authority
Scope: Moderate release-planning correction; no runtime rollback

## Trigger

Story 16.19 reached release qualification while Epic 17 still has zero completed
implementation stories (`17.0` is only `ready-for-dev`; `17.1–17.10` are backlog).
The adopted 2026-10-20 retarget explicitly defines the safe decision rule: if
Epic 17 cannot complete, cut it from v1.5.0 rather than block Epic 16 or merge
partial grounding.

## Decision

Restore Epic 17 to its original v1.6.0 release train. v1.5.0 contains Epic 16
and its release enablers only. Epic 17 remains accepted, independent, opt-in and
disabled by default, but does not gate or appear in v1.5.0 release claims.

## Impact

- No Epic 17 runtime code exists, so no code, migration, data or dependency rollback occurs.
- Epic 16 architecture, APIs, tests and release qualification are unchanged.
- Remove the shared-tag scheduling dependency and Story 16.19 release-note reference.
- Retain Epic 17 story IDs, backlog, RFC acceptance, module/test boundaries and
  all requirements for v1.6.0.
- Reframe Story 17.10 as v1.6.0 standalone release integration; it no longer
  owns cross-epic differential or shared-note obligations.

## Alternatives

- Finish all eleven Epic 17 stories now: rejected; this would expand Story 16.19
  into a separate unimplemented epic and delay the qualified Epic 16 release.
- Ship partial grounding: rejected by the existing fail-safe contract because
  incomplete live context can create confident but wrong conclusions.
- Roll back Epic 16: rejected; no dependency exists and no simplification follows.

## Required Edits

- `prd-live-environment-grounding.md`: v1.6.0 target; remove shared-tag language.
- `architecture.md` §26 and Epic 17 ADR: v1.6.0 standalone release.
- `epics.md`, Epic 17 story files, boundary plan, roadmap and operator overview:
  restore v1.6.0 and remove the v1.5.0 dependency.
- `sprint-status.yaml`: retain Epic 17 implementation statuses, document that it
  no longer gates v1.5.0.
- Story 16.19 release notes: no Epic 17 fragment/reference.

## Success Criteria

- v1.5.0 can be qualified and released without Epic 17 code or claims.
- No artifact states that Epic 17 ships in v1.5.0.
- Epic 17 remains fully planned for v1.6.0 with unchanged safety boundaries.
- Repository tests prove no Epic 16 dependency on unimplemented Epic 17 code.

## Approval

The accountable maintainer instructed the agent to choose the best approach to
complete Story 16.19. This proposal executes the pre-approved cut-back rule from
the 2026-10-20 retarget and is reversible through a future explicit release-scope
course correction.
