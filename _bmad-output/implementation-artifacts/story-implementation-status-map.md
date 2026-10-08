# Story Implementation Status Map

Reconciled: 2026-10-07. Canonical machine-readable tracker: `sprint-status.yaml`.

## Accepted baseline and evidence policy

v1.4.0 was published on 2026-10-07 from `935f3bbc88907948de8ae25bd2a361d04044ebc6`. Integration evidence was merged in PR #153. The release accepts implementation through Story 12.4, with out-of-order signing/provenance (12.6) and release/upgrade documentation (13.8). The 101-story delivery baseline was reconciled. The adopted v1.5.0 roadmap adds 20 unimplemented Epic 16 backlog stories: **121 total; 84 done, 16 ready-for-dev, 2 review, 19 backlog; 12 done epics, 5 in-progress (including Epic 16 preparation)**. Retrospectives remain optional because no completed retrospective is evidenced.

Closeout uses completed story tasks/review-fix records, merged delivery, and the accepted release evidence. It does not claim every historical review attempt passed, a new code review was performed, or tests were rerun for this administrative update. `done` records accepted delivery; separately tracked legacy/deferred risks remain visible.

- [Published release](https://github.com/deploywhisper/deploywhisper/releases/tag/v1.4.0)
- [Release verification](../../docs/verification/v1.4.0-release.json)
- [Correct Course decision](../planning-artifacts/sprint-change-proposal-2026-10-07-v1.4.0-status-reconciliation.md)
- Current story IDs supersede archived numbered sets; historical provider-hardening stories are outside this 101-story inventory.

## Epic inventory

| Epic | Status | Stories done | Stories remaining |
| --- | --- | --- | --- |
| 0 | done | 4/4 | 0 |
| 1 | done | 6/6 | 0 |
| 2 | done | 9/9 | 0 |
| 3 | done | 8/8 | 0 |
| 4 | done | 7/7 | 0 |
| 5 | done | 6/6 | 0 |
| 6 | done | 6/6 | 0 |
| 7 | done | 5/5 | 0 |
| 8 | done | 5/5 | 0 |
| 9 | done | 7/7 | 0 |
| 10 | done | 5/5 | 0 |
| 11 | done | 4/4 | 0 |
| 12 | in-progress | 5/8 | 3 |
| 13 | in-progress | 1/8 | 7 |
| 14 | in-progress | 0/5 | 5 |
| 15 | in-progress | 6/8 | 2 (review) |
| 16 | in-progress | 0/20 | 20; 16.0 qualification ready |

## Story inventory

| Story | Status | Delivery evidence / remaining work |
| --- | --- | --- |
| [0.1](./0-1-publish-core-governance-files.md) | `done` | [PR #37](https://github.com/deploywhisper/deploywhisper/pull/37), `a8c9be9` |
| [0.2](./0-2-define-maintainer-ownership-and-codeowners.md) | `done` | [PR #38](https://github.com/deploywhisper/deploywhisper/pull/38), `0c46a92` |
| [0.3](./0-3-create-requirements-traceability-matrix.md) | `done` | [PR #39](https://github.com/deploywhisper/deploywhisper/pull/39), `841290e` |
| [0.4](./0-4-establish-rfc-and-decision-process.md) | `done` | [PR #40](https://github.com/deploywhisper/deploywhisper/pull/40), `dfa8eac` |
| [1.1](./1-1-project-and-workspace-records.md) | `done` | [PR #41](https://github.com/deploywhisper/deploywhisper/pull/41), `1758d49` |
| [1.2](./1-2-project-aware-analysis-submission.md) | `done` | [PR #42](https://github.com/deploywhisper/deploywhisper/pull/42), `dfd9d27` |
| [1.3](./1-3-project-scoped-report-persistence.md) | `done` | [PR #43](https://github.com/deploywhisper/deploywhisper/pull/43), `fd3cc5e` |
| [1.4](./1-4-project-scoped-learning-and-context-records.md) | `done` | [PR #44](https://github.com/deploywhisper/deploywhisper/pull/44), `57df508` |
| [1.5](./1-5-lightweight-rbac-role-model.md) | `done` | [PR #45](https://github.com/deploywhisper/deploywhisper/pull/45), `8c68792` |
| [1.6](./1-6-project-model-documentation.md) | `done` | [PR #47](https://github.com/deploywhisper/deploywhisper/pull/47), `b59c251` |
| [2.1](./2-1-submission-manifest-and-provenance.md) | `done` | [PR #48](https://github.com/deploywhisper/deploywhisper/pull/48), `3a1221a` |
| [2.2](./2-2-terraform-plan-json-intake.md) | `done` | [PR #49](https://github.com/deploywhisper/deploywhisper/pull/49), `b22269b` |
| [2.3](./2-3-evidence-item-model-and-extraction.md) | `done` | [PR #50](https://github.com/deploywhisper/deploywhisper/pull/50), `960dfe2` |
| [2.4](./2-4-finding-model-and-evidence-links.md) | `done` | [PR #51](https://github.com/deploywhisper/deploywhisper/pull/51), `6f0efd4` |
| [2.5](./2-5-evidence-law-runtime-gate.md) | `done` | [PR #52](https://github.com/deploywhisper/deploywhisper/pull/52), `f25a0a3` |
| [2.6](./2-6-confidence-uncertainty-and-insufficient-context.md) | `done` | [PR #53](https://github.com/deploywhisper/deploywhisper/pull/53), `dc2bd52` |
| [2.7](./2-7-narrative-after-scoring-and-degraded-fallback.md) | `done` | [PR #54](https://github.com/deploywhisper/deploywhisper/pull/54), `4c3ff06` |
| [2.8](./2-8-report-schema-versioning.md) | `done` | [PR #55](https://github.com/deploywhisper/deploywhisper/pull/55), `2f2a941` |
| [2.9](./2-9-durable-report-persistence-and-audit-metadata.md) | `done` | [PR #56](https://github.com/deploywhisper/deploywhisper/pull/56), `3be7669` |
| [3.1](./3-1-verdict-first-report-header.md) | `done` | [PR #57](https://github.com/deploywhisper/deploywhisper/pull/57), `5259c1c` |
| [3.2](./3-2-findings-table-with-evidence-badges.md) | `done` | [PR #58](https://github.com/deploywhisper/deploywhisper/pull/58), `c5352e5` |
| [3.3](./3-3-evidence-inspector-panel.md) | `done` | [PR #59](https://github.com/deploywhisper/deploywhisper/pull/59), `e008975` |
| [3.4](./3-4-confidence-ledger-and-why-not-lower-higher.md) | `done` | [PR #60](https://github.com/deploywhisper/deploywhisper/pull/60), `c108a53` |
| [3.5](./3-5-context-completeness-and-todo-panel.md) | `done` | [PR #61](https://github.com/deploywhisper/deploywhisper/pull/61), `a6cdd67` |
| [3.6](./3-6-report-diff-after-rerun.md) | `done` | [PR #62](https://github.com/deploywhisper/deploywhisper/pull/62), `516153f` |
| [3.7](./3-7-keyboard-and-accessibility-review-pass.md) | `done` | [PR #63](https://github.com/deploywhisper/deploywhisper/pull/63), `6ebd442` |
| [3.8](./3-8-historical-report-search-and-filtering.md) | `done` | [PR #64](https://github.com/deploywhisper/deploywhisper/pull/64), `273f3cd` |
| [4.1](./4-1-public-risk-pattern-library-v1.md) | `done` | [PR #65](https://github.com/deploywhisper/deploywhisper/pull/65), `36bede7` |
| [4.2](./4-2-safe-sample-incident-pack.md) | `done` | [PR #66](https://github.com/deploywhisper/deploywhisper/pull/66), `bf1b450` |
| [4.3](./4-3-incident-import-for-markdown-yaml-and-json.md) | `done` | [PR #67](https://github.com/deploywhisper/deploywhisper/pull/67), `1e6a1f5` |
| [4.4](./4-4-incident-similarity-with-match-explanation.md) | `done` | [PR #68](https://github.com/deploywhisper/deploywhisper/pull/68), `4ad63da` |
| [4.5](./4-5-reviewer-feedback-capture.md) | `done` | [PR #69](https://github.com/deploywhisper/deploywhisper/pull/69), `5d1d777` |
| [4.6](./4-6-deployment-outcome-capture.md) | `done` | [PR #70](https://github.com/deploywhisper/deploywhisper/pull/70), `0ea398c` |
| [4.7](./4-7-incident-ingestion-management-and-indexing.md) | `done` | [PR #71](https://github.com/deploywhisper/deploywhisper/pull/71), `8f2820f` |
| [5.1](./5-1-versioned-api-report-contract.md) | `done` | [PR #72](https://github.com/deploywhisper/deploywhisper/pull/72), `f0525d2` |
| [5.2](./5-2-cli-project-aware-advisory-output.md) | `done` | [PR #73](https://github.com/deploywhisper/deploywhisper/pull/73), `6ae6ccd` |
| [5.3](./5-3-github-action-integration-contract.md) | `done` | [PR #75](https://github.com/deploywhisper/deploywhisper/pull/75), `13a033b` |
| [5.4](./5-4-pr-comment-formatter.md) | `done` | [PR #76](https://github.com/deploywhisper/deploywhisper/pull/76), `1c196cc` |
| [5.5](./5-5-rerun-on-commit-and-report-comparison.md) | `done` | [PR #77](https://github.com/deploywhisper/deploywhisper/pull/77), `af8e0ca` |
| [5.6](./5-6-future-adapter-output-contract.md) | `done` | [PR #78](https://github.com/deploywhisper/deploywhisper/pull/78), `2a85c58` |
| [6.1](./6-1-benchmark-corpus-v1.md) | `done` | [PR #79](https://github.com/deploywhisper/deploywhisper/pull/79), `4da68da` |
| [6.2](./6-2-benchmark-runner.md) | `done` | [PR #80](https://github.com/deploywhisper/deploywhisper/pull/80), `3da8515` |
| [6.3](./6-3-honest-failure-report-generator.md) | `done` | [PR #81](https://github.com/deploywhisper/deploywhisper/pull/81), `201fe6c` |
| [6.4](./6-4-outcome-calibration-metrics.md) | `done` | [PR #82](https://github.com/deploywhisper/deploywhisper/pull/82), `e27a2e2` |
| [6.5](./6-5-incident-backtesting.md) | `done` | [PR #85](https://github.com/deploywhisper/deploywhisper/pull/85), `18de17e` |
| [6.6](./6-6-risk-trend-review.md) | `done` | [PR #86](https://github.com/deploywhisper/deploywhisper/pull/86), `703fc72` |
| [7.1](./7-1-project-scoped-topology-context.md) | `done` | [PR #87](https://github.com/deploywhisper/deploywhisper/pull/87), `0c514e7` |
| [7.2](./7-2-terraform-state-connector.md) | `done` | [PR #88](https://github.com/deploywhisper/deploywhisper/pull/88), `000a042` |
| [7.3](./7-3-kubernetes-live-state-connector.md) | `done` | [PR #89](https://github.com/deploywhisper/deploywhisper/pull/89), `da0cdcb` |
| [7.4](./7-4-codeowners-and-ownership-mapping.md) | `done` | [PR #90](https://github.com/deploywhisper/deploywhisper/pull/90), `a518e7f` |
| [7.5](./7-5-context-graph-and-freshness-ledger.md) | `done` | [PR #105](https://github.com/deploywhisper/deploywhisper/pull/105), `125f475` |
| [8.1](./8-1-sarif-ingestion.md) | `done` | [PR #106](https://github.com/deploywhisper/deploywhisper/pull/106), `2a1f063` |
| [8.2](./8-2-scanner-json-adapter-v1.md) | `done` | [PR #107](https://github.com/deploywhisper/deploywhisper/pull/107), `2b3b619` |
| [8.3](./8-3-external-evidence-report-context.md) | `done` | [PR #108](https://github.com/deploywhisper/deploywhisper/pull/108), `0192e23` |
| [8.4](./8-4-scanner-conflict-handling.md) | `done` | [PR #109](https://github.com/deploywhisper/deploywhisper/pull/109), `edbab89` |
| [8.5](./8-5-existing-security-tools-comparison-guide.md) | `done` | [PR #111](https://github.com/deploywhisper/deploywhisper/pull/111), `91b12f5` |
| [9.1](./9-1-skill-manifest-spec-v1.md) | `done` | [PR #112](https://github.com/deploywhisper/deploywhisper/pull/112), `8dcd500` |
| [9.2](./9-2-skills-registry-api.md) | `done` | [PR #113](https://github.com/deploywhisper/deploywhisper/pull/113), `70efc0d` |
| [9.3](./9-3-skill-test-harness.md) | `done` | [PR #114](https://github.com/deploywhisper/deploywhisper/pull/114), `07c6a3c` |
| [9.4](./9-4-skills-installer-cli.md) | `done` | [PR #115](https://github.com/deploywhisper/deploywhisper/pull/115), `629677e` |
| [9.5](./9-5-skills-browser-ui.md) | `done` | [PR #116](https://github.com/deploywhisper/deploywhisper/pull/116), `5b44ff3` |
| [9.6](./9-6-skill-contribution-workflow.md) | `done` | [PR #117](https://github.com/deploywhisper/deploywhisper/pull/117), `3b14f12` |
| [9.7](./9-7-skill-analytics-and-deprecation-signals.md) | `done` | [PR #118](https://github.com/deploywhisper/deploywhisper/pull/118), `2b1143a` |
| [10.1](./10-1-agent-json-cli-mode.md) | `done` | [PR #119](https://github.com/deploywhisper/deploywhisper/pull/119), `d4d827c` |
| [10.2](./10-2-mcp-compatible-or-equivalent-agent-interface.md) | `done` | [PR #120](https://github.com/deploywhisper/deploywhisper/pull/120), `74e83c3` |
| [10.3](./10-3-ai-generated-iac-provenance-and-risk-patterns.md) | `done` | [PR #121](https://github.com/deploywhisper/deploywhisper/pull/121), `df12872` |
| [10.4](./10-4-prompt-injection-test-suite.md) | `done` | [PR #122](https://github.com/deploywhisper/deploywhisper/pull/122), `5d8b0b1` |
| [10.5](./10-5-ai-safety-documentation.md) | `done` | [PR #123](https://github.com/deploywhisper/deploywhisper/pull/123), `50542f0` |
| [11.1](./11-1-policy-adapter-output-contract.md) | `done` | [PR #124](https://github.com/deploywhisper/deploywhisper/pull/124), `6b3dc76` |
| [11.2](./11-2-threshold-and-reporting-defaults-management.md) | `done` | [PR #125](https://github.com/deploywhisper/deploywhisper/pull/125), `8ed9741` |
| [11.3](./11-3-integration-level-enforcement-settings.md) | `done` | [PR #126](https://github.com/deploywhisper/deploywhisper/pull/126), `f4d352a` |
| [11.4](./11-4-enforcement-guardrail-documentation.md) | `done` | [PR #127](https://github.com/deploywhisper/deploywhisper/pull/127), `af4eb15` |
| [12.1](./12-1-secrets-and-raw-artifact-boundary-audit.md) | `done` | [PR #128](https://github.com/deploywhisper/deploywhisper/pull/128), `493ead8` |
| [12.2](./12-2-provider-settings-administration.md) | `done` | [PR #129](https://github.com/deploywhisper/deploywhisper/pull/129), `6bf57d8` |
| [12.3](./12-3-connector-credential-handling-and-redaction-audit.md) | `done` | [PR #130](https://github.com/deploywhisper/deploywhisper/pull/130), `495f845` |
| [12.4](./12-4-openssf-scorecard-and-codeql.md) | `done` | [PR #132](https://github.com/deploywhisper/deploywhisper/pull/132), `7a5fbd8` |
| [12.5](./12-5-sbom-and-release-checksums.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [12.6](./12-6-signing-and-provenance.md) | `done` | [Published release acceptance](../../docs/verification/v1.4.0-release.json) |
| [12.7](./12-7-backup-restore-upgrade-and-retention-docs.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [12.8](./12-8-air-gapped-and-restricted-network-guide.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [13.1](./13-1-documentation-information-architecture.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [13.2](./13-2-first-analysis-and-report-interpretation-guides.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [13.3](./13-3-api-and-report-schema-references.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [13.4](./13-4-cli-evidence-and-agent-output-references.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [13.5](./13-5-connector-guides.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [13.6](./13-6-workflow-integration-guides.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [13.7](./13-7-docs-ci-and-drift-checks.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [13.8](./13-8-release-notes-and-upgrade-notes.md) | `done` | [PR #153](https://github.com/deploywhisper/deploywhisper/pull/153); [release notes](../../docs/releases/v1.4.0.md) |
| [14.1](./14-1-cncf-readiness-checklist.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [14.2](./14-2-public-adopters-and-usage-signals.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [14.3](./14-3-maintainer-coverage-and-promotion-process.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [14.4](./14-4-community-health-metrics.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [14.5](./14-5-cncf-application-package.md) | `ready-for-dev` | Prepared story; acceptance gaps remain |
| [15.0](./15-0-scaffold-frontend-and-migration-documentation.md) | `done` | [PR #92](https://github.com/deploywhisper/deploywhisper/pull/92); accepted migration phase |
| [15.1](./15-1-spa-serving.md) | `done` | [PR #92](https://github.com/deploywhisper/deploywhisper/pull/92); accepted migration phase |
| [15.2](./15-2-design-system-foundation-and-parity-audit.md) | `done` | [PR #96](https://github.com/deploywhisper/deploywhisper/pull/96); accepted migration phase |
| [15.3](./15-3-dashboard.md) | `done` | [PR #101](https://github.com/deploywhisper/deploywhisper/pull/101); accepted migration phase |
| [15.4](./15-4-report-detail-and-shared-report.md) | `done` | [PR #98](https://github.com/deploywhisper/deploywhisper/pull/98); accepted migration phase |
| [15.5](./15-5-history.md) | `done` | [PR #99](https://github.com/deploywhisper/deploywhisper/pull/99); accepted migration phase |
| [15.6](./15-6-settings-incidents-and-skills.md) | `review` | [PR #100](https://github.com/deploywhisper/deploywhisper/pull/100); implemented; unresolved parity/disposition acceptance |
| [15.7](./15-7-cutover-and-retired-ui-removal.md) | `review` | [PR #102](https://github.com/deploywhisper/deploywhisper/pull/102); implemented; unresolved parity/disposition acceptance |

## Prepared Epic 16 Contexts

Story 16.0 is ready only for governance/synthetic qualification. Other context files are prepared but held backlog by their execution gates.

| Story | Status | Dedicated context |
| --- | --- | --- |
| 16.0 | `ready-for-dev` | [16-0-adopt-and-qualify-infra-automation-contract.md](16-0-adopt-and-qualify-infra-automation-contract.md) |
| 16.1 | `backlog` | [16-1-verified-human-principal-and-session-lifecycle.md](16-1-verified-human-principal-and-session-lifecycle.md) |
| 16.2 | `backlog` | [16-2-trusted-project-memberships-and-automation-permissions.md](16-2-trusted-project-memberships-and-automation-permissions.md) |
| 16.3 | `backlog` | [16-3-closed-workflow-schema-and-validator.md](16-3-closed-workflow-schema-and-validator.md) |
| 16.4 | `backlog` | [16-4-scoped-workflows-and-immutable-revisions.md](16-4-scoped-workflows-and-immutable-revisions.md) |
| 16.5 | `backlog` | [16-5-durable-engine-and-fenced-recovery.md](16-5-durable-engine-and-fenced-recovery.md) |
| 16.6 | `backlog` | [16-6-uploaded-artifact-preflight-and-report-linkage.md](16-6-uploaded-artifact-preflight-and-report-linkage.md) |
| 16.7 | `backlog` | [16-7-workflow-editor-and-run-history-ui.md](16-7-workflow-editor-and-run-history-ui.md) |
| 16.8 | `backlog` | [16-8-evidence-bound-decisions-and-freshness.md](16-8-evidence-bound-decisions-and-freshness.md) |
| 16.9 | `backlog` | [16-9-human-approval-inbox-and-decision-ux.md](16-9-human-approval-inbox-and-decision-ux.md) |
| 16.10 | `backlog` | [16-10-registered-targets-outbox-grants-and-locks.md](16-10-registered-targets-outbox-grants-and-locks.md) |
| 16.11 | `backlog` | [16-11-github-receiver-and-outcome-reconciliation.md](16-11-github-receiver-and-outcome-reconciliation.md) |
| 16.12 | `backlog` | [16-12-runner-enrollment-and-attempt-protocol.md](16-12-runner-enrollment-and-attempt-protocol.md) |
| 16.13 | `backlog` | [16-13-isolated-runner-execution-profile.md](16-13-isolated-runner-execution-profile.md) |
| 16.14 | `backlog` | [16-14-opentofu-terraform-collection-and-provenance.md](16-14-opentofu-terraform-collection-and-provenance.md) |
| 16.15 | `backlog` | [16-15-runner-health-and-collection-ux.md](16-15-runner-health-and-collection-ux.md) |
| 16.16 | `backlog` | [16-16-declared-multi-unit-preflight-planning.md](16-16-declared-multi-unit-preflight-planning.md) |
| 16.17 | `backlog` | [16-17-signed-trigger-intake-and-cli.md](16-17-signed-trigger-intake-and-cli.md) |
| 16.18 | `backlog` | [16-18-operator-recovery-retention-and-network-readiness.md](16-18-operator-recovery-retention-and-network-readiness.md) |
| 16.19 | `backlog` | [16-19-production-qualification-and-v1-5-0-release.md](16-19-production-qualification-and-v1-5-0-release.md) |

## Next delivery and remaining risks

Epic 15 was omitted from tracking: its eight existing planned phases now have reconstructed delivery records. Six are accepted done; 15.6/15.7 remain review because 12 historical parity labels awaiting a current disposition crosswalk and initiative checklist closure lack accepted dispositions. Resolve that acceptance work in a separate task; no UI changes were made here.

Next planning/qualification is Story 16.0 and public RFC review. Epic 16 has highest v1.5.0 feature priority; it is not ready for runtime implementation until the readiness gates close. Story 12.5 remains the parallel release-enabler lane. Checksums and provenance already shipped; deliver and verify the missing SBOM against actual published artifacts without replacing immutable v1.4.0 assets. Then complete 12.7/12.8, Epic 13's remaining documentation acceptance, and Epic 14's governance/adoption readiness. Do not rebuild completed 12.6 or 13.8.

The optional public Skills Registry publisher credential failure, legitimate independent-human review-policy prerequisites, legacy share-password remediation, and the existing deferred-work register remain separate follow-ups. v1.4.0 publication does not prove full GA/CNCF readiness or all documentation requirements.

Current planning authority: [feature PRD](../planning-artifacts/prd-infra-automation.md), [course correction](../planning-artifacts/sprint-change-proposal-2026-10-07-infra-automation-v1.5.0.md), [readiness report](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md). Historical 101-story release evidence and archived sets remain intact.

Story preparation: [complete report](epic-16-story-preparation-report.md). Current feature readiness remains NOT READY until RFC/16.0 experiment/contract gates close; ready-for-dev on 16.0 is a bounded qualification scope, not a production implementation approval.
