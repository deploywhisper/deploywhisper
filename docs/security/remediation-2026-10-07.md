# Supply-chain and SAST remediation — 2026-10-07

Evidence captured 2026-10-07; baseline develop commit `7a5fbd8d3ed25fcf634188c4109758eca52efb89`. Initial read-only triage preceded the remediation recorded below. No live exploit or alert dismissal was performed.

## Result

All 21 Scorecard advisory IDs match vulnerable versions in the baseline frontend lockfile. They are all npm advisories; none maps to Python requirements. This does not establish that Python dependencies are vulnerability-free. Seven package-family updates cover the listed fixes.

The root package.json has scripts and no dependencies, and its lockfile has only the root entry. Five live open Dependabot alerts refer to obsolete root entries (four decompress, one brace-expansion). Frontend brace-expansion remains vulnerable independently of the stale root alert.

## Advisory mapping

All matches below are in `frontend/package-lock.json`; affected package version does not itself prove application exploitability.

| Advisory | Severity | Current package/version | Fix on installed line | Baseline status |
| --- | --- | --- | --- | --- |
| [GHSA-82fw-gwwq-j7x9](https://api.osv.dev/v1/vulns/GHSA-82fw-gwwq-j7x9) | Moderate | `@vitest/mocker 4.1.9`; `vitest 4.1.9` | `4.1.11`; `4.1.11` | Affected |
| [GHSA-3jxr-9vmj-r5cp](https://api.osv.dev/v1/vulns/GHSA-3jxr-9vmj-r5cp) | High | `brace-expansion 2.1.1` | `2.1.2` | Affected |
| [GHSA-6j4f-fj2g-mc7p](https://api.osv.dev/v1/vulns/GHSA-6j4f-fj2g-mc7p) | High | `brace-expansion 2.1.1` | `2.1.5` | Affected |
| [GHSA-mh99-v99m-4gvg](https://api.osv.dev/v1/vulns/GHSA-mh99-v99m-4gvg) | High | `brace-expansion 2.1.1` | `2.1.3` | Affected |
| [GHSA-q2hr-2g5m-vwhr](https://api.osv.dev/v1/vulns/GHSA-q2hr-2g5m-vwhr) | Moderate | `brace-expansion 2.1.1` | `2.1.7` | Affected |
| [GHSA-qhr7-859c-m2p7](https://api.osv.dev/v1/vulns/GHSA-qhr7-859c-m2p7) | High | `brace-expansion 2.1.1` | `2.1.6` | Affected |
| [GHSA-rgw5-rvv9-x895](https://api.osv.dev/v1/vulns/GHSA-rgw5-rvv9-x895) | High | `brace-expansion 2.1.1` | `2.1.4` | Affected |
| [GHSA-2883-xcg3-v3hh](https://api.osv.dev/v1/vulns/GHSA-2883-xcg3-v3hh) | High | `js-yaml 4.1.1` | `4.3.2` | Affected |
| [GHSA-52cp-r559-cp3m](https://api.osv.dev/v1/vulns/GHSA-52cp-r559-cp3m) | High | `js-yaml 4.1.1` | `4.3.0` | Affected |
| [GHSA-5p4m-2wfm-xmqj](https://api.osv.dev/v1/vulns/GHSA-5p4m-2wfm-xmqj) | High | `js-yaml 4.1.1` | `4.3.1` | Affected |
| [GHSA-h67p-54hq-rp68](https://api.osv.dev/v1/vulns/GHSA-h67p-54hq-rp68) | Moderate | `js-yaml 4.1.1` | `4.2.0` | Affected |
| [GHSA-28wg-ghj8-5hjv](https://api.osv.dev/v1/vulns/GHSA-28wg-ghj8-5hjv) | High | `nanoid 3.3.12` | `3.3.16` | Affected |
| [GHSA-2v37-7h3g-55p8](https://api.osv.dev/v1/vulns/GHSA-2v37-7h3g-55p8) | High | `nanoid 3.3.12` | `3.3.18` | Affected |
| [GHSA-fxqj-rqcc-2cmp](https://api.osv.dev/v1/vulns/GHSA-fxqj-rqcc-2cmp) | Moderate | `postcss 8.5.15` | `8.5.23` | Affected |
| [GHSA-r28c-9q8g-f849](https://api.osv.dev/v1/vulns/GHSA-r28c-9q8g-f849) | High | `postcss 8.5.15` | `8.5.18` | Affected |
| [GHSA-337j-9hxr-rhxg](https://api.osv.dev/v1/vulns/GHSA-337j-9hxr-rhxg) | Moderate | `react-router 7.17.0` | `7.18.0` | Affected |
| [GHSA-chx6-hx7r-mcp5](https://api.osv.dev/v1/vulns/GHSA-chx6-hx7r-mcp5) | High | `react-router 7.17.0` | `7.18.0` | Affected |
| [GHSA-h8fp-f39c-q6mh](https://api.osv.dev/v1/vulns/GHSA-h8fp-f39c-q6mh) | Moderate | `react-router 7.17.0` | `7.18.0` | Affected |
| [GHSA-qwww-vcr4-c8h2](https://api.osv.dev/v1/vulns/GHSA-qwww-vcr4-c8h2) | High | `react-router 7.17.0` | `7.18.2` | Affected |
| [GHSA-wrjc-x8rr-h8h6](https://api.osv.dev/v1/vulns/GHSA-wrjc-x8rr-h8h6) | Moderate | `react-router 7.17.0` | `7.18.0` | Affected |
| [GHSA-68fv-2mgg-jv7q](https://api.osv.dev/v1/vulns/GHSA-68fv-2mgg-jv7q) | High | `source-map-js 1.2.1` | `1.2.2` | Affected |

## Remediation candidates

| Family | Target | Parent chain |
| --- | --- | --- |
| `@vitest/mocker` | `4.1.11` | direct vitest → @vitest/mocker (both 4.1.11) |
| `brace-expansion` | `2.1.7` | openapi-typescript → @redocly/openapi-core → minimatch → brace-expansion |
| `js-yaml` | `4.3.2` | openapi-typescript → @redocly/openapi-core → js-yaml (exact 4.1.1 pin) |
| `nanoid` | `3.3.18` | vite → postcss → nanoid |
| `postcss` | `8.5.23` | vite → postcss |
| `react-router` | `7.18.2` | direct react-router-dom → react-router (both 7.18.2) |
| `source-map-js` | `1.2.2` | vite → postcss → source-map-js; @tailwindcss/vite → @tailwindcss/node → source-map-js |

Current direct ranges permit newer vitest/react-router-dom on the same major. minimatch allows brace-expansion ^2.0.1; vite allows postcss ^8.5.15; postcss allows nanoid ^3.3.12 and source-map-js ^1.2.1; Tailwind node also allows source-map-js ^1.2.1. js-yaml is pinned exactly to 4.1.1 by @redocly/openapi-core, so a generic transitive update will not suffice: upgrade a compatible parent that fixes the pin or use a narrowly scoped override. These candidates need a fresh registry/audit/install check and tests by the implementation owner.

## Exposure assessment

- `frontend/src/main.tsx` uses BrowserRouter/Routes/Route (Declarative Mode). Official advisory details explicitly exempt Declarative Mode from GHSA-337j-9hxr-rhxg (SSR hydration constructor injection) and GHSA-chx6-hx7r-mcp5 (Framework manifest DoS). GHSA-h8fp-f39c-q6mh and GHSA-qwww-vcr4-c8h2 require unstable RSC APIs, absent from this SPA. The GHSA-wrjc-x8rr-h8h6 navigation open redirect can affect Link/useNavigate when they receive attacker-supplied paths; consumers exist in this code. Upgrade to remove all affected-version matches.
- Vitest/mocker is dev tooling. Official details require access to its redirect mock-registration handler. `frontend/vite.config.ts` configures only React/Tailwind plugins, with no standalone mocker/interceptor or browser-mode config. No exposed vulnerable mocker handler was demonstrated.
- js-yaml and brace-expansion are dev tools reached through OpenAPI code generation; malicious YAML/schema/glob input is the relevant boundary. js-yaml is unrelated to Python PyYAML.
- PostCSS/nanoid/source-map-js are frontend build tooling. Some lock entries omit dev:true because Tailwind is a dependency. Dockerfile only copies frontend/dist into the Python runtime and leaves Node/node_modules in the build stage. CSS/source-map parsing during build is the demonstrated surface.

## Live Dependabot comparison

Source: [official repository alerts endpoint](https://api.github.com/repos/deploywhisper/deploywhisper/dependabot/alerts).

| Alert | Advisory | Severity | Location | Range and patch | Assessment |
| --- | --- | --- | --- | --- | --- |
| #7 | [GHSA-hrh2-vp3x-79xf](https://github.com/advisories/GHSA-hrh2-vp3x-79xf) | critical | `package-lock.json` | `decompress <= 4.2.1`; no patch listed | Absent from root lock. Removal already represented by baseline. |
| #5 | [GHSA-jwp9-9v96-94mx](https://github.com/advisories/GHSA-jwp9-9v96-94mx) | medium | `package-lock.json` | `decompress <= 4.2.1`; no patch listed | Absent from root lock. Removal already represented by baseline. |
| #3 | [GHSA-h39j-r5qq-r9mm](https://github.com/advisories/GHSA-h39j-r5qq-r9mm) | medium | `package-lock.json` | `decompress <= 4.2.1`; no patch listed | Absent from root lock. Removal already represented by baseline. |
| #2 | [GHSA-3jxr-9vmj-r5cp](https://github.com/advisories/GHSA-3jxr-9vmj-r5cp) | high | `package-lock.json` | `brace-expansion < 1.1.16`; 1.1.16 | Absent from root lock. Frontend still affected at 2.1.1; fix frontend separately. |
| #1 | [GHSA-mp2f-45pm-3cg9](https://github.com/advisories/GHSA-mp2f-45pm-3cg9) | critical | `package-lock.json` | `decompress <= 4.2.1`; no patch listed | Absent from root lock. Removal already represented by baseline. |

Recheck GitHub alerts after dependency-graph ingestion of the repaired default-branch manifests. A stale root alert does not prove frontend is fixed. Do not dismiss real frontend findings based on the root mismatch.

## Evidence / limits

- `/private/tmp/deploywhisper-hardening-scorecard.json`: Scorecard commit and 21 IDs.
- `/private/tmp/deploywhisper-osv-advisories.json`: successful official OSV API responses for all 21 IDs; each table link identifies its source.
- `/private/tmp/deploywhisper-open-alerts.json`: live open Dependabot metadata.
- Inspected requirements.txt, both manifests/lockfiles, Dockerfile, Vite configuration, and router imports/usage. Parent chains come from lockfile dependency edges.
- No tests were run for this read-only triage. Verify remediation with fresh npm/pip audits, frontend typecheck/tests/build, and composed Playwright checks required by AGENTS.md. No dependency update has been validated by this report.

## Implemented remediation

The user explicitly requested work directly on `develop`, overriding the normal feature-branch convention for this task. Compatible npm resolution repaired all 21 affected-version matches, without `--force`, overrides or additional application dependencies. Fresh root/frontend npm audits and Python requirements audit report zero known vulnerabilities. Installed families are now: Vitest/mocker 4.1.11, brace-expansion 2.1.7, js-yaml 4.3.2, nanoid 3.3.20, PostCSS 8.5.29, React Router/DOM 7.18.4, source-map-js 1.2.2. Updating the compatible Redocly parent to 1.34.20 resolved its previous js-yaml pin. Direct manifest minimums for React Router and Vitest also exclude their previous vulnerable versions.

GitHub advisory/Dependabot ingestion is an external follow-up. Five open root alerts concern absent dependencies; their current UI state is not silently accepted or dismissed. Recheck after default-branch graph refresh. Audits establish current advisory coverage, not absence of every possible vulnerability.

## Source finding dispositions

| Alert(s) | Finding | Disposition and evidence |
| --- | --- | --- |
| 100 | Weak share-password hashing | Fixed: versioned PBKDF2-HMAC-SHA256, 600,000 iterations, random 128-bit salt. Successful legacy authentication upgrades only matching password fields, preserving concurrent configuration. Existing schema/API maintained. Legacy hashes remain until authentication/reconfiguration. |
| 92–93 | Redaction regex denial of service | Fixed overlapping URL-userinfo and block-scalar alternatives. Bounded malicious-input subprocess regression failed before repair, now passes; colon-bearing passwords and CRLF/blank content remain redacted. |
| 90–91 | Assignment/heredoc regex alerts | Existing identifier boundaries/disjoint quoting and anchored delimiters protect the reviewed paths; bounded 16KB failing inputs completed in ~0.006/~0.0006 seconds. Performance regressions remain enabled. |
| 89 | Webhook exception disclosure | Fixed public config/upstream/scope error messages; unknown scope codes map to an allowlist. Opaque exception-marker regression verifies full response does not expose details. |
| 85–88 | Artifact path traversal | Hardened manifest values, report IDs and report/manifest/artifact symlinks. Malicious local manifests cannot select external paths; ordinary historical basenames remain readable. Configured storage root is trusted. This does not promise race-proof protection against a hostile local process rewriting files concurrently. |
| 94 | Artifact cleartext storage | Supported false positive: only clean local snapshots are retained. Sensitive names are skipped and detected/known secrets block the entire snapshot; existing/new boundary tests verify this. |
| 95–97 | Credential fixture storage/logging | Synthetic test markers in isolated test fixtures; no real credentials. Tests verify the production credential boundary, not a production storage/log sink. |
| 98–99 | YAML deserialization | Supported false positive: CloudFormation loader inherits `yaml.SafeLoader`; custom tag construction handles primitive/mapping/sequence values only. Python object-tag nonexecution regression passes. |
| 84 | Artifact HTML reflected XSS | Supported false positive: artifact names/title and raw lines use `html.escape`; report/line identifiers are integers and class values static. Existing content-security browser/API coverage retained. |
| 101 | Cookie injection | Supported false positive: cookie name uses typed integer report ID and value uses SHA-256 hexadecimal output. No raw user-supplied header value. |
| 102 | GitHub download partial SSRF | Supported false positive: configured trusted HTTPS API origin and constructed paths, ignored upstream download URL, same-origin redirects; existing credential-security regressions cover cross-origin/redirect attempts. |
| 83 | Predictable temporary browser fixture | Fixed by uploading an in-memory file payload; no filesystem pathname or shared temporary file remains. |
| 75–82 | Mutable action tags | Fixed: official upstream tags resolved (peeled annotated tags), referenced third-party actions pinned to 40-character commits. Same major versions retained. |

No CodeQL alert was remotely dismissed by this work. A fresh scan must establish which alerts close automatically; supported false-positive dispositions retain their evidence for maintainer review.

## Updates, permissions and SAST

Dependabot checks Python, root/frontend npm and GitHub Actions weekly, targeting `develop`; updates require normal review and CI. CI now audits both npm graphs at every vulnerability severity. The updater and audit serve different purposes.

Workflow defaults use `contents: read`. Only container publication has `packages: write`, release creation has `contents: write`, and the analytics snapshot job has `contents: write`/`issues: read`. Removed unused release OIDC and CI PR-write privileges. Analytics popularity feeds never receive the GitHub token; GitHub issue search retains its Authorization header. Snapshot commits are scoped to `data/skill-analytics.json`. Release image build explicitly depends on the validation job whose output it consumes.

CodeQL retains Python, JavaScript/TypeScript and Actions extended-query coverage, safe triggers and fresh-output provenance. Scorecard's SAST 7/10 is historical coverage of recent merged PR heads; additional source fixes do not fabricate old successful checks. Direct develop work cannot manufacture independent PR approvals. Branch protection/review policy, signed releases (Story 12.6), and other baseline controls remain owned under issue #131. No new badge score is claimed until changes are published and rescanned.

## Verification

Focused source/security regressions, clean audits, frontend typecheck, 56 frontend unit tests, production build and actionlint passed. Final local CI ran 1,794 tests across nine directories successfully (one optional live-provider skip); smoke ran 510 tests successfully (one optional skip). All 17 rebuilt, isolated Compose browser tests passed with no skips, including connector/provider disposable fixtures. Original app restored healthy; disposable test volume removed. Strict mypy retains 312 baseline errors with zero introduced errors. Final shard results and review evidence are recorded in the implementation spec. Publication/alert refresh remain pending a push; no new badge score claimed.

## Published verification — 2026-10-07

The earlier manual run `37585265566` scanned remote commit `7a5fbd8`, because remediation commit `9190270` had only been committed locally. Publishing the tested commit to `develop` and running [publisher workflow 37585646199](https://github.com/deploywhisper/deploywhisper/actions/runs/37585646199) produced a successful public report at `2026-10-07T07:09:53Z` for `9190270e271de71fcbe650aae58138afda5d3830`. The official API and badge both verify **6.7/10**, increased from **4.2/10**.

Verified check improvements: Vulnerabilities **0→10** (zero existing findings reported), Dependency-Update-Tool **0→10**, Token-Permissions **0→10**, Pinned-Dependencies **1→4**. CodeQL on the pushed commit completed successfully. [Full pushed-commit CI](https://github.com/deploywhisper/deploywhisper/actions/runs/37585645478) completed successfully, including all four test shards, quality/security, frontend, Docker and migration checks. The push-trigger publisher was superseded normally by the explicitly dispatched run under concurrency cancellation.

The [verification summary](../verification/supply-chain-remediation-2026-10-07.json) records the published commit, timestamp, workflow and every check. Remaining low controls include branch protection, independent review history, signing, dependency pinning, best-practices badge, fuzzing, contributor diversity and policy completeness. Those need actual controls or documented applicability, not fabricated review activity or a rewritten badge. SAST remains 7 due historical coverage. Issue #131 remains the owner-tracked follow-up; this result does not close all security-policy work or remotely dismiss source alerts.
