# Story16.9 approval inbox and decision UI

Design references: [v3 mockup](../../../design/deploywhisper-redesign-v3.jsx),
[automation UX/WP6](../../../design/infra-automation-ux.md) and accepted
[Story16.7 screenshots](../16-7/screenshots/).

UI baseline: `7ecec1f` on `feature/16-9-human-approval-inbox-decision-ux`.
The approved backend prerequisite shipped separately in
[PR204](https://github.com/deploywhisper/deploywhisper/pull/204). Its
[verification record](../16-9-backend-for-ui/results.md) covers immutable packet
projection, strict confirmation, session/CSRF, malicious role headers, nonhuman
credentials, separation of duties, CAS, scoped export and retained attribution.
This UI branch changes no production backend service, schema or database.

## Delivered behavior

The scoped inbox links each exact run/approval tuple to immutable report/action
context before controls. Server-selected shared approval or single-operator
acknowledgement, absolute UTC deadline components, current policy/context,
confirmation challenges and durable audit attribution remain distinct.

The adapter rejects malformed, cross-scope and inconsistent packets. Submission
rechecks session and exact packet and posts once. Ambiguous response recovery
reads the exact approval before retry is available. Terminal refresh closes stale
confirmation and focuses the receipt; failed reads disable stale controls, and
denied reads remove protected content. Identity/project changes remount the form.
Audit download uses the existing administrator-only endpoint, bounded pagination
and an explicit completeness flag. No new dependency or backend authority was
introduced.

## Composed approval browser proof

`docker-compose.approval-ui.yml` builds the real multi-stage runtime image and
serves the static SPA through FastAPI at `http://localhost:8080`. It uses a
dedicated Compose project, nonroot image user and disposable `/app/data` tmpfs;
it never mounts the operator volume. The read-only test launcher refuses host,
root, wrong configuration or non-tmpfs execution before loading database code.

The launcher creates actual accounts, memberships, workflows, collected manifests,
reports, policy attempts, bindings and decision requests. A scoped synthetic
material port is installed in that server process solely for contract/UI proof.
All successful browser/API responses and mutations use the real app. Only
lost-response and failed-read network faults are injected. Production collection,
target/custody integration and remote dispatch remain unqualified/unavailable.

Use an isolated machine with port8080 available. The harness creates random
synthetic credentials; the exported browser file must remain private and outside
the repository. Do not include authentication pages in traces or screenshots.

```bash
docker compose -p deploywhisper-story16-9 -f docker-compose.approval-ui.yml up -d --build
curl --fail http://localhost:8080/api/v1/health
proof_dir=$(mktemp -d)
docker exec deploywhisper-story16-9-deploywhisper-1 python /tmp/approval_fixture.py --export-fixture
docker cp deploywhisper-story16-9-deploywhisper-1:/tmp/approval-ui-browser-fixture.json "$proof_dir/browser.json"
chmod 600 "$proof_dir/browser.json"
BASE_URL=http://localhost:8080 \
  APPROVAL_UI_CONTAINER=deploywhisper-story16-9-deploywhisper-1 \
  APPROVAL_UI_FIXTURE="$proof_dir/browser.json" \
  npm run test:ui-review -- infra-automation-approvals.spec.ts
docker compose -p deploywhisper-story16-9 -f docker-compose.approval-ui.yml down
```

Wait for health before exporting. Repeat from a fresh container/tmpfs with
`APPROVAL_UI_DECISION_MODE=single-operator` on the `up` command and export a new
private browser file. The latter profile contains exactly one enabled human.
Remove the temporary credential directory after verification. The Playwright
loader also verifies the exact running Compose target, tmpfs, origin, identity
mode, read-only launcher and owned mode0600 fixture before any helper operation.

| Active profile | Actual result |
| --- | --- |
| Shared | 7 passed; single-operator journey intentionally excluded |
| Single operator | 1 passed; seven shared journeys intentionally excluded |

Shared journeys cover keyboard inbox/high approval, critical rejection, advisory
no-go, exact typed phrase, missing-CSRF denial, Tab/Shift+Tab/Escape, protected
permanent report navigation, one-POST lost-response recovery, concurrent reviewer
receipt, expiry preserving reason, payload change, unavailable authority,
mandatory-evidence hard block, project switch, live membership revocation,
read-only/unassigned denial, requester self-denial and administrator audit export
after reviewer demotion. Retained actor/type/role and differing state digests are
asserted; export excludes all fixture passwords. Serious/critical axe violations
fail every named screen/state check.

| Acceptance criterion | Evidence |
| --- | --- |
| AC1 | Shared inbox/review journey, evidence/control screenshots, adapter shape/scope guards and immutable packet API tests |
| AC2 | Shared self-denial/read-only/unassigned browser states, one-human acknowledgement journey, prerequisite nonhuman/header-spoof/session authorization tests |
| AC3 | High approve/critical reject phrase checks, advisory no-go decision, required reason tests and mandatory-evidence browser/API denial |
| AC4 | Real expiry, payload mutation, project switch, role revocation, lost response and concurrent reviewer journeys; uncertain/read-regression unit guards |
| AC5 | Scoped administrator download after reviewer demotion, retained role/type/state digests and password exclusion; prerequisite append-only/export/screening tests |
| AC6 | Production Compose build, keyboard confirmation/focus/recovery, serious/critical axe assertions and both-width screenshots |

## Verification corrections and independent review

An independent reviewer found five initial issues: failed reads retaining usable
controls, late pending reads replacing receipts, terminal refresh leaving a stale
modal, missing initial heading focus and a public-default report link. All were
fixed and rechecked; no production source blockers remained. The concurrent test
was corrected to assert the closed modal and focused durable receipt instead of
expecting stale confirmation to survive.

Real composed checks also found a native-dialog margin reset, focus escaping
confirmation, sign-in return-route rejection, long project text overlapping the
account link, and inaccessible low/proceed badge/link colors. Corrections reuse
the existing return-path allowlist, focus handling and approved theme/primitives.
Low/proceed labels use the existing evidence primitive; warning links use the
existing warning-text token. No global primitive colors were changed. The final manual
visual-verdict assessment is 94/100 against Story16.7 captures and the v3/WP6 authority.

## Regression and static validation

The existing unauthenticated report/settings suite uses a separate fresh tmpfs
profile of the same image with `command: [python, app.py]`, identity `disabled`,
authorization `legacy-evaluation`, an unavailable local model endpoint and its
existing synthetic share token. It has no seeded protected projects. The approval
fixture variables are omitted from that invocation, so its eight opt-in tests
are excluded there; their active verification is the two-profile matrix above.
The earlier workflow-authoring opt-in suite also retains its separate fixture
requirements. This separation does not weaken authorization in the approval
profile or replace the new approval browser proof.

| Command/check | Actual result |
| --- | --- |
| `npm run ui:typecheck`, `npm run ui:build` | Passed |
| `npm run ui:test` | 241 passed, 16 files |
| `./.venv/bin/python -m unittest discover -q` | 1,278 run, two skips, OK |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | 697 passed, one opt-in skip, 2,279 subtests |
| `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh` | All Python/static gates passed; initial browser Docker-helper targeting failure, corrected below |
| Every-directory CI discovery | All10 directories OK: 2,724 run, two skips |
| Prompt-injection CI gate | 8 passed, 96 subtests |
| Full browser regression rerun with explicit Compose target | 15 passed, 24 fixture-inapplicable skips, exit0 |
| Ruff lint / repository-wide formatting | Passed, 447 files |
| Fixture guards / compile / Compose config | Four guards passed; compile/config passed |
| Runtime image | Actual container has no Node executable |

Directory counts in CI order: analysis69, API317, CLI102, docs51, infra279,
automation533, LLM76, models22, parsers43 and services1232. Optional narrative
fallback used `LLM_API_BASE=http://127.0.0.1:1` for host checks.

The combined local-CI invocation initially reached an existing report test whose
`docker compose exec` helper selected the default project. The operator container
was stopped, so the helper failed before any write. All Python/static gates had
passed. After explicitly binding Compose to the disposable regression app, the
entire browser lane passed. No production/test code bypass was introduced and
unaffected Python gates were not repeated. Actual recovered invocation:

```bash
BASE_URL=http://localhost:8080 \
  COMPOSE_PROJECT_NAME=deploywhisper-story16-9 \
  COMPOSE_FILE=/tmp/story16-9-ui-fixture/regression-compose.yaml \
  npm run test:ui-review
```

Keep both Compose variables explicit when running the existing suite against a
custom project: its report seeding helper uses the Compose CLI. The24 exclusions
are eight approval-profile tests (actively passed above) and16 workflow/identity
fixture tests with their separately documented setup. They are not counted as
passing browser journeys here.

The dedicated fixture has no high-severity/high-confidence Bandit findings.
Its five medium `B108` diagnostics are fixed `/tmp` paths in this guarded
disposable container: reads reject symlinks, wrong owners/permissions and large
files; atomic writes use `mkstemp`, mode0600 and replacement, with a verified
owned/no-follow lock. These were reviewed without broad suppressions. Production
Bandit runs through the normal local CI gate. Repository-wide mypy retains the
312 pre-existing findings documented in the prerequisite; this branch introduces
no typed production Python module.

## Screenshots

Credential-free composed captures at both 1440 and760 pixels are in
[`screenshots/`](screenshots/). They include inbox, exact review, confidence and
rollback, decision controls, high confirmation, approve/reject receipts,
permanent report, response uncertainty/recovery, expiry, changed binding,
hard block, revoked reviewer, self-denial and audit attribution. Authentication-page development captures are excluded.

## Trust and remaining scope

Human account classification does not prove a physical person clicked. Server
session/membership/CSRF and immutable evidence checks establish the authorization
boundary. Audit is application append-only; DB/host administrators remain trusted.
This UI does not qualify production collectors, receiver execution or remote
handoff, and cannot enable those capabilities. Formal BMad code-review closure
remains the next story workflow.


## Cleanup and completion

The dedicated test Compose project was removed after both approval profiles and
the recovered existing browser lane completed. The exact original operator
container was restarted using its original image and persistent volume and
verified Docker-healthy with HTTP200. The operator volume was never mounted into
the fixture app. Private exported browser credentials were removed. Story and
sprint are `review`; implementation is committed on the dedicated feature branch,
with formal BMad review and Git Flow push/optional PR closure next.
