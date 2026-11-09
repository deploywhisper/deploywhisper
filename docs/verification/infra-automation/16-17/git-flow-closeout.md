# Story 16.17 Git Flow closeout — 2026-11-09

Story-owned acceptance and both formal review findings are complete. The story
and sprint entry are `done`. The user's November9 instruction authorizes staging,
committing, pushing and opening PRs; merging, deployment and release publication
are separate actions.

## Publication layout

- `feature/16-17-signed-trigger-intake-backend` targets `develop` with the `backend-for-ui` label. Backend revision `82fb5d30a5d2251981d3e8cfeaefd104a1f25105` contains the signed intake/CLI implementation, migration039, live machine/effect authority, clock rollback repairs, OpenAPI headers and generated contract.
- `feature/16-17-trigger-origin-ui` targets `develop` and depends on that backend. It adds only React origin presentation/decoding, browser fixtures, evidence and story closure beyond the backend branch. Merge the backend PR first, then refresh the UI PR base before merging it. While both target develop and the prerequisite is open, the UI PR's develop comparison includes prerequisite backend changes; compare the two feature branches for the isolated UI delta.

The integrated UI branch retains backend ancestry. Joining that history must
preserve the tested tree byte-for-byte. No protected branch is modified directly.
All closeout commits use intent-first Lore decision records with native trailers.

## Verification

The seven source/test/contract/qualification hashes from the final
[review-fix record](review-fixes-results.json) still match the publication tree.
All fresh browser source and screenshot hashes match as well. The initial closeout preserved runtime bytes. GitHub CodeQL then required an
explicit TLS1.2 minimum in the CLI and synthetic TLS contexts; this narrow change
and its red/green regression were validated separately below.

- Full local CI:3402 cases across ten directories, exit0; root unittest1932/3skips.
- Exact pytest API/CLI/infra:799pass1skip2433subtests; automation1108pass1skip3236subtests.
- Clock coverage:9 regressions; clock/project/report69tests165subtests and independent10tests pass.
- Python3.11.17 selected runtime:27tests pass. Frontend479+2compat/typecheck/build pass.
- Collection49checks and9integritytests/86subtests pass on the recorded qualified profile.
- Fresh standalone backend:51tests/65subtests, standalone frontend typecheck, Ruff and formatting pass.
- Fresh composed publication proof:1test28.7s,12screenshots at1440/760,zeroaxecritical/serious, keyboard pass andvisual94. See [proof](closeout-browser-proof.md) and [structured source/image evidence](closeout-browser-proof.json).
- Fresh repository-wide Ruff lint/format and whitespace checks pass. Existing317mypy diagnostics are unchanged, none in the changed runtime files.

The original app5970d092 is restored Docker-healthy and HTTP200; disposable
Compose resources and private credentials were removed. No operator data was
mounted into the proof lane. Existing16.15 HTTPS/live-runner browser and broader
collector/delivery gates remain open; this closeout does not widen support.

## TLS-floor correction after GitHub analysis

Initial CodeQL reported two high protocol-default alerts. The CLI and its real
TLS fixture now set TLS1.2 minimum explicitly without disabling certificate or
hostname verification. Fresh wholeCLI127/17subtests, automationCLI25/5subtests,
and productionPython3.11 TLS2tests pass. The unchanged-core full-suite results
above remain historical proof for those source bytes; GitHub CI and a fresh
root unittest run validate the final publication head. No CodeQL suppression or
weak TLS fixture was introduced. The fresh browser source/image hashes include
the corrected CLI; its updated result is1test28.7s with12screens/axe0/visual94.

## UI test assertion follow-up

UI CodeQL identified the test-only tag-stripping expression used to inspect a
static summary. It now matches the bounded plain-text span and checks its
expected visible label without rewriting HTML. Production rendering is unchanged.
Fresh frontend479tests/2compatibilitychecks, typecheck and production asset build
pass. No sanitizer suppression or product/flow/style change was introduced.
