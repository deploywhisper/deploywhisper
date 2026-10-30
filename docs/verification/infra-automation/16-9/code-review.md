# Story16.9 code review — 2026-10-30

Scope: `7ecec1f..7c968cb` and the review corrections on
`feature/16-9-human-approval-inbox-decision-ux`. The accepted backend prerequisite
remains separately delivered in [PR204](https://github.com/deploywhisper/deploywhisper/pull/204).
No production Python service, schema, database contract or dependency changed.

## Review layers and triage

Three fresh native agents ran the BMad Blind Hunter, Edge Case Hunter and
Acceptance Auditor layers. The blind reviewer read only the diff; the edge
reviewer traced referenced paths; the auditor used the story, approved contract
and UX context. No layer failed. Seventeen initial candidate observations normalized into
eight patches (one high, seven medium), four dismissals and five overlapping
observations. No product decision or pre-existing deferred work was required.

| ID | Severity | Finding and correction |
| --- | --- | --- |
| R1 | Medium | Retained collection time, source verification and redaction version were absent. They now appear in the evidence facts before controls. |
| R2 | Medium | Evidence/approval windows and readable remaining validity were not visible, and response latency renewed the local window. Visible facts now use monotonic time from the exact read start, including transit; the server still independently authorizes every POST. |
| R3 | High | An unchanged pending GET cleared an ambiguous POST barrier. Pending reads now retain it until an advancing terminal receipt. A definite server rejection clears only its matching submission serial, using recognized HTTP4xx error metadata. Unknown network/5xx outcomes and invalid success bodies remain blocked. |
| R4 | Medium | Same-version terminal outcome changes and nonhuman approve/reject attribution passed frontend guards. Terminal receipt identity/outcome fields must remain stable at the same version; approved/rejected attribution must be the recorded human reviewer with a valid human role. |
| R5 | Medium | Null decision mode implied independent review, and empty guidance could hide why actions were blocked. Unknown models now stay unavailable and blocked states have a safe recovery explanation. |
| R6 | Medium | Repeated pagination cursors or overlapping records could duplicate inbox rows indefinitely. Consumed-cursor and duplicate-ID guards now stop unsupported pagination. |
| R7 | Medium | Audit export completeness depended only on the last cursor. Exports now account for gaps and the final truncation flag. Earlier continuation pages may legitimately be truncated when all their successors were consumed. |
| R8 | Medium | Error focus could run before React mounted the summary or displace a durable receipt. Focus now follows committed message state; terminal confirmation unmounts before receipt focus. Late non-auth submission errors recover the existing terminal receipt without replacing it with obsolete feedback. |

R3 prevents conflicting human intents while an earlier request may still be in
flight. Backend CAS already protected the single durable transition; this fix
also establishes the promised browser recovery barrier. A pending read cannot
prove that a request stopped. The UI explains waiting for a recorded outcome or
operator recovery, and never automatically replays the POST.

## Dismissed candidates

- Full-page reload also loses CSRF material. Restored sessions are read-only;
  fresh sign-in rotates/revokes the previous session and live server checks remain
  authoritative. The in-memory marker is not an authorization credential.
- Receipt and audit reason/time equality would reject legitimate history.
  Receipt screening permits2048 characters while attribution screening uses512;
  audit creation and decision timestamps use independent clocks. New tests retain
  separately screened reasons, distinct times and legacy values.
- Fixture files intentionally retain synthetic case history inside a documented
  fresh disposable container. This is bounded test state, not production growth.
- Immediate Blob URL revocation had no demonstrated failure in the qualified
  Chromium profile. Actual scoped downloads are exercised; no wider browser
  compatibility claim is made.

## Verification

Regression-first evidence: the added screen/helper tests produced seven failures
before the fixes; the API attribution matrix produced two failures before its
fix. After implementation all256 frontend tests and typecheck/build pass.
Independent source rechecks of acceptance coverage and edge paths are clear.

The first composed iteration exposed receipt-focus interference after introducing
committed error focus. The implementation was corrected rather than relaxing
the focus assertions. A further independent recheck added the late409 race:
hold the original POST, commit another verified review, let polling focus the
receipt, then release the original request to receive an actual conflict. Error
feedback must not steal receipt focus after recovery.

Final composed profiles and the root smoke pass. The exact original
operator container/image/volume are restored healthy, and protected browser
credential exports are removed. Fixture login pacing respects the real five-per-
minute account limit; expiry cases run first so pacing cannot consume their test
window. The limiter was not disabled or bypassed. All browser proof uses the production FastAPI/static image at localhost8080 and
real synthetic API/database setup. Network failures/delays and a forwarded real
422 are fault injection; successful decisions, GETs, attribution and exports use
the actual server. No positive approval response is fabricated.

The original [implementation verification](results.md) retains broad Python CI,
exact shard and prior browser evidence. Review changes affect frontend logic and
its tests only; the accepted Python backend and disposable launcher are unchanged.
Production collector/registry/custody and receiver qualification remains outside
this story, and DB/host administrators remain trusted for audit integrity.

| Review check | Actual result |
| --- | --- |
| Frontend unit/type/build | 256 passed; typecheck/build passed |
| Shared approval profile | 11 passed; single-operator case excluded |
| Fresh one-human profile | 1 passed;11 shared cases excluded |
| Existing composed browser suite with explicit Compose target | 15 passed;28 fixture-inapplicable exclusions |
| New runtime image | Built and verified to contain no Node executable |
| Ruff lint / repo-wide formatting / diff | Passed,447 files |
| Root unittest smoke | 1,278 run; two skips; OK |

Commands: `npm run ui:typecheck`, `npm run ui:test`, `npm run ui:build`;
`docker compose -p deploywhisper-story16-9 -f docker-compose.approval-ui.yml up -d --build`,
health, guarded synthetic seed/export, and
`BASE_URL=http://localhost:8080 APPROVAL_UI_CONTAINER=deploywhisper-story16-9-deploywhisper-1 APPROVAL_UI_FIXTURE=<owned0600-file> npm run test:ui-review -- infra-automation-approvals.spec.ts`.
Repeat from a fresh tmpfs with `APPROVAL_UI_DECISION_MODE=single-operator`.
Existing regression uses the same production image with the documented disposable
legacy-evaluation profile and explicit `COMPOSE_PROJECT_NAME`/`COMPOSE_FILE`.
Root command: `LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m unittest discover -q`.
All profiles are disposed before the original operator is restored.

## Git Flow closure

The branch is a dedicated `feature/*` child of the accepted develop baseline.
All eight findings are resolved and validation is complete. The review correction
and closeout records are committed on this branch; remote push and the PR to
develop are the final workflow closure steps. The PR URL is recorded in the
completion message and closeout metadata.
