## Deferred from: code review of 2-1-submission-manifest-and-provenance.md (2026-05-07)

- Resolved 2026-05-07: Share filename redaction can over-replace ordinary basename text in prose [services/report_service.py:119]. The fix keeps exact full-path replacement while limiting basename prose replacement to file-like names with extensions.

## Deferred from: code review of 2-5-evidence-law-runtime-gate.md (2026-05-09)

- Evidence Law status is not yet explicitly visible in UI/API/CLI report surfaces [frontend/src/components/report_detail_page.py:82]. Deferred because Story 2.5 only gates persistence; visible report header/table status is covered by later report-surface stories 3.1 and 3.2, but should remain tracked so those stories render the persisted Evidence Law warning/status instead of hiding it.

## Deferred from: code review of 2-7-narrative-after-scoring-and-degraded-fallback.md (2026-05-12)

- Resolved 2026-05-12: Blank APP_HOST still builds a malformed share URL [services/report_service.py:181]. The share-link host helper now normalizes blank APP_HOST to localhost.
- Resolved 2026-05-12: Bracketed non-IP APP_HOST values still build malformed share URLs [services/report_service.py:181]. The share-link host helper now unwraps bracketed non-IP hostnames before URL construction.

## Deferred from: code review of 2-7-narrative-after-scoring-and-degraded-fallback.md (2026-05-12)

- APP_HOST URL-like values can still produce malformed share links [services/report_service.py:197]. Deferred as pre-existing configuration hardening because APP_BASE_URL/PUBLIC_APP_URL are the intended full-URL settings and Story 2.7 only touched host fallback normalization.
- Non-numeric APP_PORT can still crash share-link fallback generation [services/report_service.py:179]. Deferred as pre-existing configuration validation outside the narrative-fallback acceptance criterion.
- Share-link environment parsing remains outside centralized settings [services/report_service.py:172]. Deferred as pre-existing architecture cleanup; the story changed defensive normalization but did not introduce the direct environment reads.

## Deferred from: code review of 2-7-narrative-after-scoring-and-degraded-fallback.md (2026-05-12)

- Resolved 2026-05-12: Unbracketed IPv6 APP_HOST values with common 4-digit embedded-port-looking suffixes remain ambiguous with valid numeric IPv6 hextets [services/report_service.py:188]. The share-link host helper now strips a bounded set of common copied web/dev ports while still preserving ordinary numeric IPv6 hextets such as `:1234`.

## Deferred from: code review of 3-3-evidence-inspector-panel.md (2026-05-15)

- Extend the UI review browser gate beyond WebKit for focus-sensitive keyboard behavior [playwright.config.cjs:29]. Deferred as pre-existing browser-matrix hardening; Story 3.3 currently uses the approved `APP_PORT=18080 npm run test:ui-review` WebKit UI E2E substitute for the local manual screen-reader blocker.

## Deferred from: code review of 3-3-evidence-inspector-panel.md (2026-05-15)

- Add a direct narrative sanitization regression that covers redacted, sensitive-blocked, and unknown redaction states together for raw `source_ref` and `summary` leakage [frontend/e2e/test_history_page.py:49]. Deferred as supplemental coverage hardening because current focused tests already cover sensitive-blocked and unknown-redaction narrative leakage and mixed-redaction reference selection.

## Deferred from: code review of 5-1-versioned-api-report-contract.md (2026-05-25)

- List endpoint masks forbidden/conflicting scoped reads as empty success instead of an error envelope [api/routes/analyses.py:425]. Deferred as pre-existing behavior locked by existing scoped-read tests; it should be revisited as a project/workspace authorization contract cleanup separate from Story 5.1 report contract payload work.

## Deferred from: code review of 6-2-benchmark-runner.md (2026-06-02)

- Resolved 2026-06-02: Benchmark runs are not explicitly isolated from ambient topology/narrative service behavior [services/benchmark_runner_service.py:346]. The runner now calls the shared artifact builder with an explicit deterministic benchmark profile that disables ambient topology, incident lookup, narrative generation, and LLM scoring assists while preserving the shared parser/evidence/scoring/finding path.

## Deferred from: code review of 7-3-kubernetes-live-state-connector.md (2026-06-10)

- Malformed non-object Kubernetes manifest documents still abort parsing [parsers/kubernetes_parser.py:17]. Deferred as pre-existing parser hardening because the unguarded `document.get(...)` behavior existed before Story 7.3; this story only added namespace-aware resource IDs and aliases inside the existing parser loop.

## Deferred from: code review of 8-1-sarif-ingestion.md (2026-06-19)

- Resolved 2026-06-19: Incremental scanner rescan/update semantics need product decision [services/scanner_import_service.py:198]. Story 8.1 now upserts same-scope SARIF rescans, refreshes existing evidence severity/message/source metadata, and imports new findings from mixed duplicate/new runs.
- Resolved 2026-06-19: Workspace deletion should decide between preserving scanner history and preventing workspace-scope promotion [models/tables.py:162]. Scanner workspace FKs now preserve history with `SET NULL`, while project-scope listing and uniqueness exclude orphaned workspace evidence via retained `workspace_key`.

## Deferred from: code review of 9-1-skill-manifest-spec-v1.md (2026-07-20)

- Expose parsed trust level and related manifest metadata through registry/API/install listing surfaces [services/skill_registry_service.py:28]. Deferred to Stories 9.2/9.5 where registry API and browser trust-level visibility are in scope; Story 9.1 only formalizes and validates the manifest schema.

## Deferred from: code review of 9-4-skills-installer-cli.md (2026-07-23)

- Resolved 2026-07-24: The no-source remediation text now includes `PUBLIC_APP_URL`, matching the documented registry URL resolution order [services/skill_installer_service.py:153].

## Deferred from: code review of 9-4-skills-installer-cli.md (2026-07-24)

- Resolved 2026-07-24: Skill install and update now write a same-directory temporary file and atomically replace the destination, preserving the prior installed file when writes or replacement fail [services/skill_installer_service.py:625].

## Deferred from: code review of 9-5-skills-browser-ui.md (2026-07-27)

- Resolved 2026-07-27: The Skill detail page now renders the full deterministic harness summary together with harness-run and analytics-refresh timestamps [frontend/src/screens/Skills.tsx:224].
- Resolved 2026-07-27: `SkillRegistryData` now requires visible contributors, the generated frontend contract includes them, and the Skill detail page renders them [api/schemas.py:2080].

## Deferred from: code review of 10-4-prompt-injection-test-suite.md (2026-07-31)

- Resolved 2026-07-31: Release-blocking claims such as `Stop the release` and `Release should be blocked` now contradict a GO recommendation [llm/prompt_security.py:97].

## Deferred from: code review of 11-3-integration-level-enforcement-settings.md (2026-08-14)

- Resolved 2026-08-14: GitHub check-run creation failures on neutral-skip and successful-analysis paths now return bounded partial results while preserving handled webhook state and persisted report references [integrations/github/app_service.py:421].
- Resolved 2026-08-14: GitHub skipped-analysis guidance now distinguishes sensitive-only, unsupported-only, mixed rejected, and empty artifact sets without exposing filenames or contents [integrations/github/app_service.py:414].
