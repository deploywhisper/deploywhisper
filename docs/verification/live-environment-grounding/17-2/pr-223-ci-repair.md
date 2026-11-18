# PR223 frontend security gate repair

Date:2026-11-18. Baseline:`afee422`. The only original failure was Frontend SPA's npm audit; CI Summary failed as a consequence. Original quality, Python/security, Docker, migrations, changed-test, CodeQL and redaction checks passed.

## Cause and correction

The existing Picomatch4.0.7 dependency is affected by [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf). The registry's latest release remains4.0.7 and the advisory lists no patched release. A toolchain downgrade or audit suppression would not establish remediation.

The existing transitive library is replaced by an explicitly named private local fork, `@deploywhisper/picomatch@4.0.7`, packaged as `frontend/vendor/deploywhisper-picomatch-4.0.7-security.3.tgz`. This is not an upstream fixed release. Original MIT license, registry archive integrity, readable source patch and every installed-file hash are retained. A direct development anchor and `$picomatch` override resolve the local archive portably for all existing consumers; no independent library or application runtime dependency was introduced.

The parser retains its existing safety fallback and linear character-star flattening. Unsafe repeated bodies with wildcard/nested/bracket syntax, quotes, escapes or non-ASCII normalization are literalized. Remaining literal alternatives must be prefix-free after ASCII case folding. Ordinary glob matching, braces and test discovery remain functional. This scoped mitigation does not claim arbitrary raw regular expressions are safe.

Both npm audit commands and audit-level=low are unchanged. Because audit matches package identity rather than source hashes, it cannot certify a private fork. Mandatory source/archive/lock/behavior checks provide patch proof. A separate fixed-HTTPS upstream-advisory query tracks Picomatch4.0.7; only the exact known mitigated advisory is recognized, and only alongside successful patch tests. New/changed advisory metadata, malformed responses, redirects, oversized bodies, timeouts and failed patch proof fail closed.

## Review

Initial review found quoted-branch and escaped-class bypasses; implementation review also found case-folding ambiguity. These were fixed with positive literal grammar and dedicated deadline-bound regressions before final packaging. Final static blind review and archive/provenance acceptance review found no remaining blocker in this CVE scope. The edge reviewer independently identified the quoted case, then its tool became unavailable; the parent and acceptance reviewer verified its fix using bounded tests. No claim is made that every possible parser path was exhaustively proven.

## Validation

- Upstream baseline exploit timed out in a bounded child process; final22security/provenance/compatibility/advisory-fixture tests pass.
- Clean Node22.23.5/npm10.9.4 temporary install, audit,22security tests and live upstream tracking pass: `/tmp/pr223-node22-npm10-final.log`.
- Host clean `npm ci --prefix frontend`; both root and frontend `npm audit --audit-level=low`:zero vulnerabilities. Live `npm --prefix frontend run audit:picomatch-upstream` passes; no advisory gate was weakened.
- `npm run ui:typecheck`, `npm run ui:test` (30files,513Vitest tests plus Node guards), and `npm run ui:build`:passed. Logs:`/tmp/pr223-{typecheck,ui-test,ui-build}-final.log`.
- `docker build -t deploywhisper:pr223-security-repair .`:passed after copying local vendor material before npm ci. Final runtime image is byte-identical to the previous build: `sha256:fff48a770f7aa232f1b14f4875d525bc7d5efed8f4ca18b8d806c1ddeffe713c`. All compiled frontend asset hashes also match. Logs:`/tmp/pr223-docker-build-final.log`, `/tmp/pr223-frontend-assets-{before,final}.json`.
- Targeted release/SBOM, hash-lock and qualified-source tests:23passed,78subtests. Repo-wide Ruff lint/format and diff checks passed. No Python source or dependency lock changed. Supplemental root unittest run is in progress at push time; its outcome will be recorded in the PR validation summary.
- UI browser validation not applicable: this is build/test tooling only, rendered application sources and compiled assets are unchanged. No live AWS/production-profile qualification is added.

## Delivery and maintenance

Push this repair to the existing PR223 branch and verify the latest GitHub checks. Remove the fork only when a maintained upstream patched release passes the same security and compatibility corpus. Preserve upstream-advisory tracking and artifact/provenance verification until removal. See [vendor maintenance instructions](../../../../frontend/vendor/README.md).
