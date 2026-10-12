---
workflow: bmad-check-implementation-readiness
date: 2026-10-07
assessor: Independent Codex readiness reviewer
stepsCompleted: [1, 2, 3, 4, 5, 6]
status: completed
readiness: NOT READY
planning_reconciliation: applied
direction: accepted-for-planning
architecture_rfc: Proposed-not-approved
feature_implementation: unstarted
story_preparation: complete-20-contexts
first_story_status: ready-for-dev-governance-and-synthetic-qualification-only
execution_sizing: pending-after-16.0-spikes
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/prd-infra-automation.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/epics.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
  - docs/design/infra-automation-ux.md
  - docs/rfcs/0001-infra-automation-preflight-and-handoff.md
  - _bmad-output/planning-artifacts/infra-automation-v1.5.0-release-plan.md
  - _bmad-output/planning-artifacts/infra-automation-requirement-dispositions.json
  - _bmad-output/implementation-artifacts/sprint-status.yaml
---

# Infrastructure Automation v1.5.0 implementation readiness

> Historical assessment: its original open-gate snapshot is superseded for Story16.0 foundation readiness by the [2026-10-10 assessment](implementation-readiness-report-2026-10-10-infra-automation-v1.5.0.md). Production/release obligations remain with their owning stories.


**Story-preparation follow-up:** All 20 dedicated contexts now exist. Story 16.0 is ready to begin governance/disposable qualification only; 16.1–16.19 remain backlog. The initial assessment below preserves its original evidence snapshot. IR-04 document refinement is resolved by prepared bounded packets, while execution sizing/named assignment awaits real 16.0 results. Public governance, feasibility and interface gates remain open. [Preparation report](../implementation-artifacts/epic-16-story-preparation-report.md).

**Overall: NOT READY for downstream feature implementation or production release.** The planning change is adopted, the bounded scope is appropriate, and Epic 16 has a traceable implementation path. Public RFC acceptance and Story 16.0 executable trust-boundary qualification are outstanding. Preparing 16.0 and its review/spike evidence is the appropriate next work; these blockers do not mean the requested documentation reconciliation is unfinished.

## 1. Document discovery and authority

The user's batch instruction selects the canonical whole-document inputs below and authorizes the six-step review. No unresolved whole/sharded conflict exists. The parent PRD plus feature addendum are complementary contracts, not duplicate PRDs. `docs/deploywhisper-infra-automation-prd.md` remains historical vision and is not the implementation contract. Current whole documents prevail over archived/sharded plans. Readiness does not silently supersede the public RFC process.

| Input | Role | Bytes | State |
| --- | --- | --- | --- |
| `_bmad-output/planning-artifacts/prd.md` | Parent 187 FR / 38 NFR | 117999 | Canonical planning/input; not runtime proof |
| `_bmad-output/planning-artifacts/prd-infra-automation.md` | Canonical 60 FR / 12 NFR addendum | 34263 | Canonical planning/input; not runtime proof |
| `_bmad-output/planning-artifacts/architecture.md` | Existing architecture + §25 amendment | 79888 | Canonical planning/input; not runtime proof |
| `_bmad-output/planning-artifacts/epics.md` | Existing 101 + new 20 story definitions | 165619 | Canonical planning/input; not runtime proof |
| `_bmad-output/planning-artifacts/ux-design-specification.md` | Existing UX + authority override | 63275 | Canonical planning/input; not runtime proof |
| `docs/design/infra-automation-ux.md` | Feature UX journeys/contracts | 20954 | Canonical planning/input; not runtime proof |
| `docs/rfcs/0001-infra-automation-preflight-and-handoff.md` | Public architecture decision | 22680 | Proposed; public review pending |
| `_bmad-output/planning-artifacts/infra-automation-v1.5.0-release-plan.md` | Reviewed release scope/sequence | 42604 | Canonical planning/input; not runtime proof |
| `_bmad-output/planning-artifacts/infra-automation-requirement-dispositions.json` | Original dispositions + active traceability | 107109 | Canonical planning/input; not runtime proof |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | Current execution status | 9055 | Canonical planning/input; not runtime proof |

Execution baseline: 121 stories across 17 epics: **84 done, 15 ready-for-dev, 2 review, 20 backlog**. All 20 Epic 16 stories are backlog. Story 12.5 remains the SBOM enabler; delivered 12.6 and 13.8 retain their identities and statuses. The two Epic 15 review items remain review; planning adoption does not close parity acceptance. Existing IDs are preserved instead of moving security history to make room for the new feature.

## 2. PRD analysis

The full-text requirement inventories below retain all **187 parent FR and 38 parent NFR** and extract all **60 new FR and 12 new NFR**. The parent text is preserved verbatim from the canonical requirement extraction; the addendum text/proofs are cross-checked against its JSON and canonical story rows. Scope dispositions are not delivery statuses.

Additional binding requirements include: default-disabled rollout; singleton SQLite/Python application; separately deployed qualified Linux collector and operator self-hosted receiver; no binary plan/state transport to the app; no bundled IaC licensing assumption; no new dependency implicitly approved; real server identity and memberships; exact evidence/action binding; restore epochs and uncertain-outcome locks; additive migration and report compatibility; production composed-browser qualification; public RFC review and feasibility spikes before dependent implementation.

The parent exclusion of provisioning is now precise: preflight collection and approved external handoff do not give DeployWhisper apply/destroy/remediation ownership. Deferred AI, broad plugins/collectors, scheduling, promotion and PostgreSQL automation are not P0. Existing supported uploads and optional report narrative remain available. The parent insufficient-context concept is represented by the canonical verdict vocabulary plus typed flags, not a new invented enum.

## 3. Epic coverage validation

| Scope | Requirements | Planning coverage | Implementation claim |
| --- | --- | --- | --- |
| Parent FR | 187 | 187/187 explicit family/story ownership (100% planning coverage) | Preserved baseline, not re-certified by this review |
| Parent NFR | 38 | 38/38 explicit family or epic Primary coverage | Preserved baseline, not measured anew |
| New FR | 60 | 60/60 mapped to Epic 16, matching requirement-specific acceptance text and proof | 0 implemented in this planning task |
| New NFR | 12 | 12/12 mapped to owners including 12.5 where applicable | Targets remain unmeasured |
| Original draft rows | 179 | 89 adopted-revised, 45 partial-revised, 45 deferred | Neither 179 implemented nor 179 fully promised for v1.5.0 |

Every active new requirement has a named proof and one or more story owners. The check compares full text and proof rows, not just requirement IDs. Shared ownership means each slice proves its owned contract and later integration proves the full cross-boundary requirement; it must not force an implicit forward dependency. Counts are planning traceability, not test coverage or delivered capability.

Semantic checks: human sessions cannot be minted by service/agent/runner/receiver credentials; legacy linked-report/settings/policy paths are part of the authority boundary; failed/partial mandatory evidence cannot authorize; canonical advisory `should_block=False` remains separate from workflow eligibility; decisions bind authorization kind and the full immutable tuple; upload-only advisory requests explicitly mark unavailable source and cannot authorize apply, while collected/exact-plan paths require the admitted commit and custody; receiver admission rechecks live authority; lost acceptance is `delivery_unknown`; grants/restore/revocation and target locks fail closed; saved-plan bytes remain in qualified local custody; report linkage is relational first with additive provenance only after compatibility proof. Performance targets identify a reference workload and future measurements rather than asserting capacity.

## 4. UX alignment

Both canonical UX documents exist. The feature contract explicitly overrides stale historical identity/style guidance using the approved React v3 mockup, current theme and existing primitives. Dedicated root routes preserve the Dashboard budget, global search and ProjectSwitcher; UI reads real scoped API data. Approval, upload-only advisory handoff, exact-plan authorization and external outcome have distinct meanings. The decision packet includes source, policy, payload, report and artifact identities plus effective deadline; single-operator acknowledgement is labeled honestly.

Feature-off, unauthorized, stale-project caches, unknown delivery, cancellation, transient enrollment credentials, partial evidence, network loss and revocation receive explicit behavior. Keyboard focus, tables, dialogs, live updates and reduced motion are described. Backend supports those resources through additive API work. Compose production build, seeded APIs, Playwright/axe/keyboard and screenshots remain required future evidence. No feature UI runtime evidence is present. Story 16.0 must freeze actual enums/error/routes and screen composition before dependent UI story preparation.

## 5. Epic and story quality

Epic 16 delivers one coherent user outcome: scoped evidence-backed preflight, durable human decision and qualified handoff. It builds on earlier completed shared-core/project/report work and does not depend on a later epic. Brownfield placement, migrations from v1.4.0, shared scoring, Python runtime/React static build and external Marketplace action repository boundaries are explicit. Each slice creates only needed entities; no foundation story is authorized to precreate all future tables. No greenfield starter or framework migration is justified.

All 20 definitions contain user/maintainer value, Given/When/Then framing, negative cases and requirement-specific proof tables. Their explicit dependencies form an earlier-story DAG. Numbering preserves history and allows the highest-priority feature to run before unrelated unfinished documentation/CNCF items.

Sizing remains a refinement concern: 16.0 bundles governance and several spikes; 16.5 bundles state/claims/quotas/cancellation; 16.11 spans network adapter, receiver and recovery; 16.18 spans retention, migration, restore and restricted networks. Keep stable IDs but split the story specifications into bounded reviewed subtasks/PRs with named owners and executable acceptance per subtask. The first usable vertical slice arrives at 16.6–16.9 after security/state foundations. Foundation stories are justified by concrete operator safety, but their generic first GWT clauses are not sufficient implementation instructions without the specific test matrix and create-story refinement.

The release estimate (28–49 person-weeks plus contingency) is preliminary. It does not imply a date or staffing commitment. Freeze support versions and re-estimate after 16.0. No reduction of identity, containment, custody or unknown-delivery controls is an acceptable schedule shortcut.


## 6. Final assessment and blocker registry

**Verdict: NOT READY.** Planning scope and priority are adopted; feature implementation acceptance and production qualification remain blocked. Readiness is complete as an assessment and does not mark Story 16.0 done or later stories ready-for-dev.

| ID | Severity / state | Finding and evidence | Owner | Required next action |
| --- | --- | --- | --- | --- |
| IR-01 | Critical / open governance gate | RFC 0001 remains Proposed. PR #154 opened 2026-10-08T08:06:23Z and merged at 08:37:29Z that day; the 2026-10-09 observation found no reviews, comments or outstanding review requests. The original minimum decision time is 2026-10-15T08:06:23Z. Actual maintainer/independent outcome and qualification remain absent; early merge is publication only. [WP1 packet](../../docs/verification/infra-automation/16-0/README.md) records the gaps. | Maintainer / 16.0 | Establish and link an actual public review continuation for the merged planning PR; record applicable opening/window, area requests, discussion and approving maintainer outcome. No exception, merge or elapsed window is inferred as acceptance. |
| IR-02 | Critical / open feasibility gate | 2026-10-09 disposable identity and SQLite prototypes pass their declared cases; the synthetic receiver fault slice passes after review fixes. [Evidence packet](../../docs/verification/infra-automation/16-0/README.md) records 41 tests. Real hostile-source Linux isolation, actual saved-plan custody/separate identities/storage policy and integrated receiver admission remain unqualified; these unresolved proofs keep the overall gate open. Architecture §25.10 and RFC Review Plan explicitly require them. | Backend/security/runner owners / 16.0 | Execute disposable synthetic spikes; retain commands, versions, fault points, results and known gaps; resolve IA-ADR choices and any dependency approval. Security-sensitive implementation waits for the accepted contract. |
| IR-03 | Major / open story-preparation gate | Proposed profile is selected, but exact workflow/runner/receiver schema, wire states/routes/error fixtures, crypto parameters, report consumer/hash compatibility and final screen composition are not frozen. Feature UX explicitly retains these 16.0 gates. | Architecture/API/UI owners / 16.0, 16.3 | Publish versioned fixtures and threat model, route/permission matrix and compatible report decision; rerun readiness before promoting downstream stories. |
| IR-04 | Document refinement resolved; execution sizing pending | All 20dedicated contexts contain bounded packets, owned paths, explicit acceptance cases and per-slice proof. Broad16.0/16.5/16.11/16.18/16.19 have ordered review units; reviewer assignments and estimates still require real 16.0 evidence. | Maintainer /16.0 and story owners | Honor prepared scope; assign named implementers and re-estimate from spikes before dependent story promotion. No test double or prepared context proves production support. |
| IR-05 | Major / resolved in this review | Architecture §25.6 now lists stopped_by_gate and timed_out and distinguishes gate stop from human rejected; feature UX External delivery and cancellation lists the corresponding cause vocabulary. | Architecture/UX owner | Final wire enum fixtures remain IR-03; planning enum mismatch is corrected. |
| IR-06 | Major / resolved in this review | Epic 16 story-specific Slice acceptance boundary paragraphs and architecture §25.12 now name contract/test-double qualification separately from integrated proof. 16.11 uses protected immutable synthetic custody; 16.14 explicitly depends on 16.11 in both epic and release plan, and real collector/custody integration remains mandatory in 16.14/16.19. | Epic/architecture owner | Preserve this separation during create-story; no double proves a production collector profile. |
| IR-07 | Minor / resolved in this review | Parent map now explicitly assigns ADM-06 to Epic 11/11.2, ADM-08 to Epic 1/1.1, and performance targets to existing workload/measurement owners. Parent requirement text and statuses are preserved. | Planning owner | No historical story is reopened or latency achievement implied by this map correction. |

IR-01/02 are required governance and experiment evidence, not contradictions the documentation can declare solved. IR-03/04 are story-preparation work. IR-05/06 were concrete artifact alignment defects and are now resolved after rechecking the updated canonical files. IR-07 was inherited baseline granularity and is also resolved. Four open gates remain across governance, feasibility, contract preparation and sizing; three alignment findings were corrected in this documentation workstream.

Recommended next sequence:

1. Prepare the context-filled Story 16.0 with public RFC review, named spike subtasks, threat model, explicit evidence custody and protocol/schema contracts. Keep later feature stories backlog.
2. Preserve the corrected document alignment, qualify the selected boundaries and record the real public decision. Rerun implementation readiness; promote only dependency-satisfied prepared stories.
3. Run Story 12.5 SBOM work as the parallel release enabler; preserve 12.7/12.8 full acceptance while adding automation-specific operations evidence. Existing Epic 15 reviews remain independently tracked.
4. Build the uploaded-evidence vertical slice after identity/state foundations, then receiver and isolated collector integrations, declared units/triggers, operational qualification and signed release. Include tests/docs/review in every slice.
5. Have `bmad-help` confirm this handoff. Stable v1.5.0 requires 16.19 evidence: full application CI, current constructor/consumer shards, real tools/receiver, fault/recovery/load qualification, composed browser/a11y, independent review, support matrix, SBOM/signing/provenance and pilot.

Assessment verification run: a read-only `python3` inventory/assertion check passed for all 225 parent full-text rows, 72 active full-text/story-proof mappings, 20 earlier-only dependency definitions and the 121-story status distribution; `git diff --check -- _bmad-output/planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md` passed.

Assessment evidence: canonical requirement text/proof comparison found no mismatch in the 72 active rows and their mapped Epic 16 tables; explicit dependencies use earlier stories; statuses retain the accepted baseline plus 20 backlog items. The previous 51 documentation-test passes validate documentation checks only. This review has run no new application/runner/receiver/Compose/load/recovery qualification and makes no production-readiness claim. The leader owns final aggregate documentation validation and BMad help handoff.

## Appendix A. Complete parent requirement extraction and current epic coverage

Full requirement text is preserved; family-map coverage is distinct from verified per-story delivery. The final family/epic ownership map now explicitly covers every parent ID; rows preserve full parent text and do not infer runtime achievement from ownership.

### Parent FR (187)

| ID | Complete parent requirement | Current epic coverage |
| --- | --- | --- |
| ING-01 | Accept one or more artifacts from supported toolchains in a single analysis. | Epic 2 |
| ING-02 | Auto-detect artifact type without requiring manual labeling for normal cases. | Epic 2 |
| ING-03 | Support partial analysis when not all related artifacts are available. | Epic 2 |
| ING-04 | Detect unsupported artifacts and explain why they were excluded. | Epic 2 |
| ING-05 | Detect sensitive files and block unsafe downstream handling. | Epic 2 |
| ING-06 | Preserve a submission manifest showing accepted, excluded, partially parsed, and failed artifacts. | Epic 2 |
| ING-07 | Accept Terraform plan JSON as a first-class input. | Epic 2 |
| ING-08 | Accept project/workspace key in CLI, API, and integration flows. | Epic 2 |
| ING-09 | Preserve artifact provenance and redaction status. | Epic 2 |
| PRJ-01 | Define instance, project, workspace/environment, service, resource, analysis run, report, and connector objects. | Epic 1 |
| PRJ-02 | Scope reports to a project. | Epic 1 |
| PRJ-03 | Scope incidents to a project. | Epic 1 |
| PRJ-04 | Scope deployment outcomes to a project and optional workspace. | Epic 1 |
| PRJ-05 | Scope external scanner imports to a project. | Epic 1 |
| PRJ-06 | Scope connector credentials to instance, project, or workspace. | Epic 1 |
| PRJ-07 | Support project-aware RBAC roles. | Epic 1 |
| PRJ-08 | Accept or derive project keys in CLI, API, UI, and workflow integrations. | Epic 1 |
| PRJ-09 | Include project/workspace scope in context graph nodes and evidence items. | Epic 1 |
| PRJ-10 | Document project modeling patterns for monorepos, multi-repos, Terraform workspaces, Kubernetes clusters, and platform teams. | Epic 1 |
| EVD-01 | Normalize supported artifacts into a shared internal change model. | Epic 2 |
| EVD-02 | Each finding shall reference one or more concrete evidence items. | Epic 2 |
| EVD-03 | Evidence items shall identify artifact, location, resource, operation, project, and contextual source where applicable. | Epic 2 |
| EVD-04 | Reports shall distinguish deterministic findings, derived findings, external evidence, model-inferred explanations, and user-provided context. | Epic 2 |
| EVD-05 | Reports shall surface confidence and uncertainty for key findings and overall verdict. | Epic 2 |
| EVD-06 | Reports shall explain main contributors to the overall risk score. | Epic 2 |
| EVD-07 | Incomplete context shall produce explicit uncertainty instead of implied certainty. | Epic 2 |
| EVD-08 | Evidence items shall persist with reports for audit, comparison, and benchmark replay. | Epic 2 |
| EVD-09 | High and critical findings shall require at least one deterministic evidence item. | Epic 2 |
| EVD-10 | Narrative generation failure shall not remove deterministic evidence or verdict. | Epic 2 |
| EVD-11 | Evidence Law status shall be visible in reports. | Epic 2 |
| EVD-12 | CI shall fail when fixtures generate high/critical findings without deterministic evidence. | Epic 2 |
| RSK-01 | Produce a unified advisory deployment risk verdict. | Epic 2 |
| RSK-02 | Classify findings and verdicts by severity. | Epic 2 |
| RSK-03 | Detect cross-tool interactions that increase risk. | Epic 2 |
| RSK-04 | Generate reviewer-oriented explanations of operational risk. | Epic 2 |
| RSK-05 | Generate actionable remediation or verification guidance. | Epic 2 |
| RSK-06 | Produce rollback guidance and rollback complexity score. | Epic 2 |
| RSK-07 | Distinguish product recommendation from human decision. | Epic 2 |
| RSK-08 | Continue deterministic analysis if narrative generation fails. | Epic 2 |
| RSK-09 | Provide "why not lower" and "why not higher" explanation for verdicts. | Epic 2 |
| RSK-10 | Support an insufficient-context verdict. | Epic 2 |
| RSK-11 | Detect AI-generated IaC risk patterns where provenance or content signals are available. | Epic 2; Epic 10 |
| RSK-12 | Label public risk pattern matches separately from organization incident matches. | Epic 2 |
| CTX-01 | Compute blast radius using project-scoped topology context. | Epic 7 |
| CTX-02 | Indicate when topology is stale, missing, incomplete, or conflicting. | Epic 7 |
| CTX-03 | Ingest incident records for similarity matching. | Epic 4; Epic 7 |
| CTX-04 | Surface relevant incident similarity results with match confidence and match reasons. | Epic 4; Epic 7 |
| CTX-05 | Support service criticality and environment-aware risk context. | Epic 7 |
| CTX-06 | Store deployment history sufficient for comparison and trend analysis. | Epic 7 |
| CTX-07 | Support topology auto-discovery and source connectors without replacing the core report format. | Epic 7 |
| CTX-08 | Support read-only Terraform state connector. | Epic 7 |
| CTX-09 | Support optional read-only Kubernetes live-state connector. | Epic 7 |
| CTX-10 | Support CODEOWNERS and ownership mapping. | Epic 7 |
| CTX-11 | Support context freshness and confidence per source. | Epic 7 |
| CTX-12 | Generate context TODOs to improve future report quality. | Epic 7 |
| CTX-13 | Attach context source metadata to evidence items. | Epic 7 |
| INC-01 | Support built-in public risk pattern memory on fresh installs. | Epic 4 |
| INC-02 | Clearly distinguish public risk pattern matches from organization-specific incidents. | Epic 4 |
| INC-03 | Support optional sample incident pack for demos. | Epic 4 |
| INC-04 | Support markdown, YAML, and JSON incident import. | Epic 4 |
| INC-05 | Support future imports from PagerDuty, Opsgenie, Jira, GitHub Issues, and Slack exports. | Epic 4 |
| INC-06 | Store incident metadata, root cause, trigger change, affected services, rollback path, and prevention notes. | Epic 4 |
| INC-07 | Compute similarity using deterministic and semantic signals. | Epic 4 |
| INC-08 | Explain why an incident matched the current change. | Epic 4 |
| INC-09 | Support backtesting against historical incident-causing changes. | Epic 4; Epic 6 |
| INC-10 | Capture deployment outcomes for calibration. | Epic 4 |
| INC-11 | Track false positives and false reassurance from outcome feedback. | Epic 4 |
| INC-12 | Ensure sample incident packs contain no real customer data, no real organization names, and no non-public postmortem content without explicit attribution and permission. | Epic 4 |
| REV-01 | Web report shall present verdict first, then Evidence Law status, confidence, evidence, and details. | Epic 3 |
| REV-02 | Report shall show top findings, blast radius, rollback, risk patterns, incident memory, external scanner context, and uncertainty above the fold. | Epic 3 |
| REV-03 | Users shall be able to inspect full findings and evidence details on demand. | Epic 3 |
| REV-04 | Users shall be able to retrieve prior reports and compare analyses over time. | Epic 3 |
| REV-05 | System shall generate concise summaries for PRs and approval threads. | Epic 3 |
| REV-06 | Shared summaries shall remain explicitly advisory. | Epic 3 |
| REV-07 | Report shall support expert quick scan and detailed investigation. | Epic 3 |
| REV-08 | Report diff shall show resolved, new, and persistent risks after reruns. | Epic 3 |
| REV-09 | Report shall show context TODOs. | Epic 3 |
| REV-10 | Report schema version shall be visible and machine-readable. | Epic 3 |
| WRK-01 | Expose a stable versioned REST API. | Epic 5, Epic 11 |
| WRK-02 | Expose CLI access using the same analysis core. | Epic 5, Epic 11 |
| WRK-03 | Support GitHub-first workflow delivery for PR review. | Epic 5, Epic 11 |
| WRK-04 | Post formatted PR summaries including verdict, Evidence Law status, top risks, evidence, blast radius, rollback, incident memory, public risk patterns, external scanner context, and uncertainty. | Epic 5, Epic 11 |
| WRK-05 | Support rerun after new commits or changed artifacts. | Epic 5, Epic 11 |
| WRK-06 | Support report links and machine-friendly summary payloads. | Epic 5, Epic 11 |
| WRK-07 | Support future GitLab, Atlantis, HCP Terraform, Jenkins, Argo CD, Flux, and chat adapters without redesigning the core report object. | Epic 5, Epic 11 |
| WRK-08 | CLI and integration flows shall accept project key or project ID. | Epic 5, Epic 11 |
| WRK-09 | GitHub repository flows may derive default project key from repository name. | Epic 5, Epic 11 |
| WRK-10 | Support pre-commit or local developer feedback mode. | Epic 5, Epic 11 |
| AIA-01 | Provide machine-readable analysis output for AI agents. | Epic 10 |
| AIA-02 | Provide `--agent-json` CLI mode. | Epic 10 |
| AIA-03 | Provide MCP-compatible interface or equivalent agent-callable interface. | Epic 10 |
| AIA-04 | Treat AI-generated IaC as untrusted input. | Epic 10 |
| AIA-05 | Detect common AI-generated infrastructure risk patterns. | Epic 10 |
| AIA-06 | Preserve provenance metadata where available, including human-authored, AI-assisted, or unknown. | Epic 10 |
| AIA-07 | Ensure AI models cannot directly create high or critical findings without deterministic evidence. | Epic 10 |
| AIA-08 | Include prompt-injection tests for IaC comments, PR comments, incident text, scanner output, and documentation-like artifacts. | Epic 10 |
| AIA-09 | Ensure agents cannot use DeployWhisper to autonomously approve, deploy, or remediate production changes. | Epic 10 |
| AIA-10 | Document AI-generated IaC review workflows. | Epic 10 |
| EXT-01 | Maintain documentation explaining DeployWhisper alongside existing security tools. | Epic 8 |
| EXT-02 | Support SARIF ingestion. | Epic 8 |
| EXT-03 | Support at least one scanner JSON format in Phase 1.5 or Phase 2. | Epic 8 |
| EXT-04 | Label external scanner findings as external evidence. | Epic 8 |
| EXT-05 | Prevent external scanner findings from automatically becoming high/critical DeployWhisper findings without DeployWhisper evidence and scoring. | Epic 8 |
| EXT-06 | Include external scanner context in reports, PR comments, and API output. | Epic 8 |
| EXT-07 | Document how AppSec, SRE, and platform teams should use scanner output with DeployWhisper. | Epic 8 |
| EXT-08 | Surface conflicts between external scanner findings and deterministic evidence instead of silently choosing one source. | Epic 8 |
| HIS-01 | Persist completed reports before showing final success. | Epic 2 |
| HIS-02 | Retain audit metadata with each report. | Epic 2 |
| HIS-03 | Users shall be able to search and filter historical reports. | Epic 3 |
| HIS-04 | Managers shall be able to review risk trends over time. | Epic 6 |
| HIS-05 | Capture reviewer feedback on report quality and correctness. | Epic 4 |
| HIS-06 | Support outcome capture after deployment for calibration. | Epic 4; Epic 6 |
| HIS-07 | Support benchmark and backtest workflows against historical incidents. | Epic 4; Epic 6 |
| HIS-08 | Scope reports, topology, outcomes, and feedback to a project/workspace. | Epic 1 |
| HIS-09 | Support false-positive and false-reassurance tracking. | Epic 4 |
| ADM-01 | Admins shall configure narrative-provider settings through a DeployWhisper-owned provider adapter boundary. | Epic 12 |
| ADM-02 | Admins shall enable fully local-only operation. | Epic 12 |
| ADM-03 | Admins shall manage topology data and freshness status. | Epic 7 |
| ADM-04 | Admins shall manage incident ingestion and indexing. | Epic 4 |
| ADM-05 | Admins shall add or override custom Skills and organization-specific heuristics. | Epic 9 |
| ADM-06 | Admins shall manage thresholds and reporting defaults without changing core code. | Epic 11, Story 11.2 (threshold/reporting configuration) |
| ADM-07 | Policy adapters shall consume report outputs without changing advisory-first core behavior. | Epic 5, Epic 11 |
| ADM-08 | Admins shall create and manage lightweight project/workspace records. | Epic 1, Story 1.1 (project/workspace records) |
| ADM-09 | Admins shall configure optional enforcement adapter behavior per integration. | Epic 5, Epic 11 |
| ADM-10 | Admins shall configure external scanner ingestion per project. | Epic 8 |
| SKL-01 | Expose a Skills registry API for listing, fetching, and installing community-contributed Skills. | Epic 9 |
| SKL-02 | Support versioned Skills with a formal manifest schema. | Epic 9 |
| SKL-03 | Run automated test harness on every Skill submission. | Epic 9 |
| SKL-04 | Provide Skills installer CLI. | Epic 9 |
| SKL-05 | Provide public Skills browser UI with search and filters. | Epic 9 |
| SKL-06 | Track skill analytics such as install counts, test pass rates, last update, and issue activity. | Epic 9 |
| SKL-07 | Provide contribution workflow with PR template, automated linting, and reviewer assignment. | Epic 9 |
| SKL-08 | Support trust levels: experimental, verified, core, deprecated. | Epic 9 |
| SKL-09 | Require deterministic scenarios for verified/core Skills. | Epic 9 |
| BEN-01 | Maintain public benchmark corpus. | Epic 6 |
| BEN-02 | Provide benchmark runner. | Epic 6 |
| BEN-03 | Compare against baseline approaches where reproducible. | Epic 6 |
| BEN-04 | Publish quarterly benchmark results. | Epic 6 |
| BEN-05 | Track precision, recall, false reassurance, evidence coverage, latency, and regression stability. | Epic 6 |
| BEN-06 | Require expected evidence and expected verdict rationale for benchmark scenarios. | Epic 6 |
| BEN-07 | Support backtesting against incident records. | Epic 6 |
| BEN-08 | Benchmark reports shall include a public "scenarios we missed" section. | Epic 6 |
| BEN-09 | Material misses shall create linked GitHub issues unless the scenario is explicitly out of scope. | Epic 6 |
| BEN-10 | Benchmark reports shall distinguish product limitations from benchmark limitations. | Epic 6 |
| BEN-11 | Benchmark reports shall include Evidence Law violation count. | Epic 6 |
| GOV-01 | Maintain public governance documentation. | Epic 0, Epic 12, Epic 14 |
| GOV-02 | Maintain maintainer ladder. | Epic 0, Epic 12, Epic 14 |
| GOV-03 | Maintain public roadmap. | Epic 0, Epic 12, Epic 14 |
| GOV-04 | Maintain contributor guide. | Epic 0, Epic 12, Epic 14 |
| GOV-05 | Maintain code of conduct. | Epic 0, Epic 12, Epic 14 |
| GOV-06 | Maintain security policy. | Epic 0, Epic 12, Epic 14 |
| GOV-07 | Maintain release process. | Epic 0, Epic 12, Epic 14 |
| GOV-08 | Maintain adopters list. | Epic 0, Epic 12, Epic 14 |
| GOV-09 | Use public RFCs for major design decisions. | Epic 0, Epic 12, Epic 14 |
| GOV-10 | Maintain CNCF readiness checklist. | Epic 0, Epic 12, Epic 14 |
| GOV-11 | Maintain `MAINTAINERS.md` mapping maintainers to major project areas. | Epic 0, Epic 12, Epic 14 |
| GOV-12 | Maintain `CODEOWNERS` for major directories. | Epic 0, Epic 12, Epic 14 |
| GOV-13 | Track maintainer coverage gaps. | Epic 0, Epic 12, Epic 14 |
| GOV-14 | Publicly document maintainer promotion and inactivity process. | Epic 0, Epic 12, Epic 14 |
| GOV-15 | Track contribution and community health metrics. | Epic 0, Epic 12, Epic 14 |
| DOC-01 | Maintain a public, versioned documentation tree or docs site in the repository. | Epic 13 |
| DOC-02 | Document every primary user journey: install, configure, analyze, review, integrate, troubleshoot, extend, and contribute. | Epic 13 |
| DOC-03 | Provide self-hosted installation guides for local CLI, Docker Compose, Kubernetes/Helm, and air-gapped environments. | Epic 13 |
| DOC-04 | Documentation shall not assume a DeployWhisper-hosted SaaS service, hosted API, hosted dashboard, hosted model, or hosted control plane. | Epic 13 |
| DOC-05 | Each epic shall include documentation tasks and documentation acceptance criteria. | Epic 13 |
| DOC-06 | User-facing stories shall not be considered done until required docs are updated. | Epic 13 |
| DOC-07 | Provide first-analysis and report-interpretation guides using safe sample artifacts. | Epic 13 |
| DOC-08 | Maintain integration guides for every supported workflow integration. | Epic 13 |
| DOC-09 | Maintain connector guides for every supported context connector. | Epic 13 |
| DOC-10 | Maintain API, report schema, evidence schema, webhook, CLI, and MCP references. | Epic 13 |
| DOC-11 | Maintain security, privacy, prompt-injection, secrets-handling, and local-first provider-boundary documentation. | Epic 13 |
| DOC-12 | Maintain operations docs for backup, restore, upgrade, scaling, observability, logs, database, workers, and troubleshooting. | Epic 13 |
| DOC-13 | Maintain Skills authoring, testing, publishing, private Skill, and Skill trust-level documentation. | Epic 13 |
| DOC-14 | Maintain benchmark documentation, including methodology, running benchmarks, adding scenarios, and reading results. | Epic 13 |
| DOC-15 | Maintain contributor documentation for development setup, architecture, tests, parser authoring, connector authoring, docs authoring, governance, and releases. | Epic 13 |
| DOC-16 | Provide docs CI for broken links, markdown formatting, generated references, and command/schema drift where practical. | Epic 13 |
| DOC-17 | Provide release notes and upgrade notes for every user-visible release. | Epic 13 |
| DOC-18 | Link from UI, CLI errors, API docs, and integration outputs to relevant documentation where practical. | Epic 13 |
| DOC-19 | Maintain CNCF readiness documentation covering governance, security, releases, adoption, community, and project scope. | Epic 13 |
| DOC-20 | Track documentation health metrics as part of project health. | Epic 13 |
| DOC-21 | Maintain `docs/concepts/evidence-law.md`. | Epic 13 |
| DOC-22 | Maintain `docs/concepts/project-model.md`. | Epic 13 |
| DOC-23 | Maintain `docs/incidents/day-zero-incident-memory.md` or equivalent. | Epic 13 |
| DOC-24 | Maintain `docs/ai-safety/reviewing-ai-generated-iac.md`. | Epic 10; Epic 13 |
| DOC-25 | Maintain `docs/comparisons/deploywhisper-alongside-security-tools.md`. | Epic 13 |
| DOC-26 | Maintain `docs/community/maintainer-areas.md`. | Epic 13 |
| DOC-27 | Maintain `docs/benchmarks/honest-failure-reporting.md`. | Epic 13 |

### Parent NFR (38)

| ID | Complete parent requirement | Current epic coverage |
| --- | --- | --- |
| NFR-SEC-01 | Fully local operation must be possible. | Epic 2; Epic 12 |
| NFR-SEC-02 | Raw IaC must not be sent externally by default. | Epic 2; Epic 12 |
| NFR-SEC-03 | Provider credentials must not be persisted unsafely. | Epic 2; Epic 12 |
| NFR-SEC-04 | Secrets must be redacted from logs, prompts, reports, and telemetry by default. | Epic 2; Epic 12 |
| NFR-SEC-05 | Prompt-injection controls must be tested. | Epic 2; Epic 12 |
| NFR-SEC-06 | High/critical findings must satisfy the Evidence Law. | Epic 2; Epic 12 |
| NFR-SEC-07 | Project/RBAC boundaries must prevent cross-project data leakage. | Epic 1; Epic 2; Epic 12 |
| NFR-PERF-01 | Standard PR analysis should complete in under 15 seconds at p95 for common small-to-medium changes when using local deterministic analysis and already-available project context, excluding optional remote LLM latency and unavailable external connector timeouts. The benchmark corpus must define the reference dataset, runner profile, timeout policy, and measurement method. | Epic 6, Stories 6.1/6.2 (reference workload and measurement ownership; not a claim the target is measured) |
| NFR-PERF-02 | Large artifact submissions should degrade gracefully by returning partial deterministic results, explicit skipped-scope details, and actionable timeout/context messages rather than failing silently. | Epic 2, Stories 2.1/2.6 (partial intake/context and skipped-scope behavior) |
| NFR-PERF-03 | Narrative generation failure or timeout must not block deterministic analysis results. | Epic 2, Story 2.7 (narrative timeout/failure fallback) |
| NFR-PERF-04 | Benchmark latency should be tracked per release, including p50, p95, p99, timed-out analyses, and deterministic-vs-narrative latency split. | Epic 6 |
| NFR-PERF-05 | Connectors that cannot respond within their configured timeout must be marked stale/unavailable and must not block the core deterministic report. | Epic 7, Stories 7.2/7.3 and Epic 2 Story 2.6 (connector deadline/unavailable context) |
| NFR-REL-01 | Analysis failures must be explicit and actionable. | Epic 2 |
| NFR-REL-02 | Partial analysis must show what was included and excluded. | Epic 2 |
| NFR-REL-03 | Reports must persist before success is returned. | Epic 2 |
| NFR-REL-04 | Re-running the same deterministic inputs should produce stable deterministic findings. | Epic 2 |
| NFR-XAI-01 | Reports must be understandable to reviewers without requiring source-code reading. | Epic 3 |
| NFR-XAI-02 | Evidence must be inspectable. | Epic 3 |
| NFR-XAI-03 | Uncertainty must be visible. | Epic 3 |
| NFR-XAI-04 | Severity reasoning must be explainable. | Epic 3 |
| NFR-XAI-05 | UI and docs should follow accessibility best practices. | Epic 3 |
| NFR-OPS-01 | Support local, Docker Compose, Kubernetes/Helm, and air-gapped deployment paths. | Epic 12 |
| NFR-OPS-02 | Configuration must be file/env driven where practical. | Epic 12 |
| NFR-OPS-03 | PostgreSQL path should be available for shared/team installs. | Epic 12 |
| NFR-OPS-04 | SQLite may be supported for local/single-node installs. | Epic 12 |
| NFR-OPS-05 | Backup, restore, upgrade, and retention must be documented. | Epic 12 |
| NFR-OPS-06 | Observability metrics and logs must avoid secrets. | Epic 12 |
| NFR-DOC-01 | Docs must be sufficient for self-service installation. | Epic 13 |
| NFR-DOC-02 | Docs must not assume SaaS onboarding. | Epic 13 |
| NFR-DOC-03 | Examples should be copy-pasteable where practical. | Epic 13 |
| NFR-DOC-04 | Docs should be versioned with releases. | Epic 13 |
| NFR-DOC-05 | Docs CI should catch broken links and obvious drift where practical. | Epic 13 |
| NFR-DOC-06 | Docs must include troubleshooting for common self-hosted failures. | Epic 13 |
| NFR-OSS-01 | Governance, contribution, release, and security processes must be public. | Epic 0, Epic 12, Epic 14 |
| NFR-OSS-02 | Maintainer ownership must be public. | Epic 0, Epic 12, Epic 14 |
| NFR-OSS-03 | CODEOWNERS must route reviews for major areas. | Epic 0, Epic 12, Epic 14 |
| NFR-OSS-04 | RFC process must be used for major changes. | Epic 0, Epic 12, Epic 14 |
| NFR-OSS-05 | Benchmark and Skills contributions must have clear contribution paths. | Epic 0, Epic 12, Epic 14 |

## Appendix B. Complete active addendum extraction and story coverage

All rows are planned and unimplemented; proof names describe future acceptance evidence.

| ID | Complete requirement | Story coverage | Required proof |
| --- | --- | --- | --- |
| IAU15-FR-001 | Support only Tier 0 preflight and Tier 1 human-approved external handoff in v1.5.0; reject apply/destroy, remediation, unattended approvals and unsupported execution profiles. | 16.0, 16.3 | Scope/RFC review and unsupported-mode rejection corpus |
| IAU15-FR-002 | Resolve each human decision from a verified human principal; caller actor/role headers cannot establish identity. | 16.1, 16.2 | Authenticated-session and malicious-header tests |
| IAU15-FR-003 | Bootstrap the first local operator through an operator-held one-use setup credential with no default account/password; provide a documented secured account-recovery procedure. | 16.1, 16.18 | Bootstrap replay/default-credential tests and recovery exercise |
| IAU15-FR-004 | Enforce human session expiry, logout and revocation with protected cookies and CSRF defenses for browser mutations. | 16.1 | Session lifecycle, cookie and CSRF test matrix |
| IAU15-FR-005 | Distinguish human, service, agent and runner credentials; nonhuman credentials cannot obtain human sessions, publish workflows or decide approvals. | 16.1, 16.2, 16.17 | Principal-type privilege matrix |
| IAU15-FR-006 | Derive project/workspace capabilities from server-owned memberships, denying absent membership and cross-scope access by default. | 16.2 | Role × project × workspace authorization matrix |
| IAU15-FR-007 | Protect automation-linked report, policy, settings and artifact paths against bypass through legacy caller-controlled scope or role inputs. | 16.2, 16.6 | Legacy-route and linked-object bypass regression tests |
| IAU15-FR-008 | Enforce distinct requester/approver identities in shared mode; label authenticated single-operator decisions as acknowledgement with no separation-of-duties claim. | 16.2, 16.9 | Self-approval denial and acknowledgement-mode E2E |
| IAU15-FR-009 | Publish a versioned workflow schema with typed, bounded inputs and explicit supported step input/output contracts. | 16.3 | Schema valid/invalid fixture corpus |
| IAU15-FR-010 | Validate definitions without side effects using bounded YAML bytes/depth/aliases, duplicate-key rejection and an acyclic graph capped at 50 steps. | 16.3 | Parser resource-abuse and cycle/step-limit corpus |
| IAU15-FR-011 | Accept only the closed P0 registry: supported artifact intake, OpenTofu/Terraform collection, analyze, policy gate, approval and GitHub handoff; reject arbitrary scripts/plugins, loops and generic failure/finally execution. | 16.3 | Registry and unsupported-handler denial corpus |
| IAU15-FR-012 | Resolve only typed substitution references to inputs, declared step outputs and run/project metadata; reject unknown references, functions and code evaluation. | 16.3 | Typed-reference and injection fixture corpus |
| IAU15-FR-013 | Require every executable path to a handoff to pass its mandatory successful evidence analysis, policy gate and matching approval; skipped/failed or unrelated ancestors do not qualify. | 16.3, 16.8 | Wrong-branch, skipped-ancestor and alternate-path tests |
| IAU15-FR-014 | Scope workflow drafts and revisions to one project and optional workspace. | 16.4 | Workflow cross-scope CRUD tests |
| IAU15-FR-015 | Keep published revisions immutable; restore creates a new draft, and drafts cannot execute. | 16.4 | Publish/edit/restore/draft-run lifecycle tests |
| IAU15-FR-016 | Snapshot the published definition, validated inputs, scope and source identity immutably when a run starts; require a repository commit for collected/exact-plan paths and explicitly mark unavailable source for upload-only advisory review. | 16.4, 16.5 | Post-start mutation and rerun snapshot tests |
| IAU15-FR-017 | Disable, revoke or restore epoch changes must invalidate unconsumed grants and prevent new run starts, collection claims, dispatch or grant consumption while preserving read and reconciliation for accepted external work. | 16.4, 16.10, 16.11, 16.18 | Disable/revoke/restore-before-dispatch-or-consume race matrix |
| IAU15-FR-018 | Persist run/step transitions and explicit `stopped_by_gate`, `expired`, `timed_out`, `cancelled`, `failed`, `succeeded` and `delivery_unknown` outcomes across restart. | 16.5, 16.11 | Crash at each transition with state recovery assertions |
| IAU15-FR-019 | Fence leader/task attempts so only the current owner may heartbeat, log, upload or complete a task. | 16.5, 16.12 | Overlapping leader and stale-attempt rejection tests |
| IAU15-FR-020 | Retry only declared safe/idempotent local work within finite deadlines; persist idempotent outputs and reconcile uncertain external work instead of blind resend. | 16.5, 16.11 | Retry/deadline/duplicate-completion and dropped-response tests |
| IAU15-FR-021 | Record cancellation durably and terminate the owned runner process tree; explain that cancellation cannot undo accepted external work. | 16.5, 16.13, 16.15 | Cancellation/dispatch races and process-tree termination tests |
| IAU15-FR-022 | Bound per-workflow/project concurrency, backlog, analysis workers and storage usage with explicit quota/backpressure errors. | 16.5, 16.18 | Saturation, queue-cap and storage-exhaustion tests |
| IAU15-FR-023 | Allow runner-less upload of currently supported artifact formats through existing scoped intake protections. | 16.6 | Uploaded-artifact vertical slice and size/type/traversal tests |
| IAU15-FR-024 | Screen inputs, metadata, streamed logs, errors and artifacts before persistence or analysis; reject state/credential/key/binary-plan uploads and inline secret-looking values. | 16.6, 16.14 | Secret corpus including chunk boundaries and blocked-file tests |
| IAU15-FR-025 | Record authenticated collection provenance with runner/task attempt, command/argv digest, source SHA, exit code, time, raw-local digest, sanitized digest and redaction version; recompute received digests. | 16.6, 16.14 | Tampered digest, stale attempt and redaction-provenance tests |
| IAU15-FR-026 | Invoke the existing shared analysis core without duplicating risk logic; provenance alone cannot turn inferred output into deterministic evidence. | 16.6, 16.14 | Cross-surface report parity and Evidence Law fixtures |
| IAU15-FR-027 | Link runs to immutable reports through a compatible versioned optional provenance contract; retain permanent report URLs and existing report consumers. | 16.6, 16.7 | Serializer/constructor/legacy-consumer contract tests |
| IAU15-FR-028 | Expose missing/partial/stale collection as confidence limitations and context TODOs; failed or incomplete mandatory collection cannot make approval eligible. | 16.6, 16.8, 16.14 | Partial/error/stale collection eligibility tests |
| IAU15-FR-029 | Keep deterministic automation usable with AI disabled or narrative failure, and preserve existing structured-summary/local-only provider boundaries without new AI composition. | 16.6 | AI-off and narrative-failure vertical slice |
| IAU15-FR-030 | Pause for a human decision durably with a finite deadline and never auto-approve on restart, expiry or missing reviewer. | 16.8 | Restart/expiry/missing-reviewer decision tests |
| IAU15-FR-031 | Bind approval to authorization kind, revision, source identity and required exact-plan commit, project/workspace/environment, reports, artifact and unit-plan digests, policy version, exact target and payload digest. | 16.8, 16.10 | Independent mutation of every decision-tuple field |
| IAU15-FR-032 | Enforce evidence freshness at decision, dispatch and receiver consumption; default collection TTL is 60 minutes unless an audited stricter policy applies. | 16.8, 16.11 | Clock/TTL boundary and delayed-consume tests |
| IAU15-FR-033 | Evaluate explicit workflow policy separately from advisory report semantics, preserving canonical should_block=False and using existing policy-adapter field meanings where compatible. | 16.8 | Gate decision versus advisory report contract tests |
| IAU15-FR-034 | Require an explicit authenticated approve/reject decision and reason when the canonical recommendation is `no-go`, severity is high/critical or the separate typed `insufficient_context` flag is true, with typed confirmation for high/critical. | 16.9 | Reason/confirmation API denial and keyboard decision E2E |
| IAU15-FR-035 | Invalidate eligibility when evidence, revision, source, scope, target, policy, membership or custody changes, expires or is superseded; no emergency bypass or delegated approval in P0. | 16.8, 16.10, 16.11 | Revocation/supersession/custody-loss and bypass-denial matrix |
| IAU15-FR-036 | Register outbound GitHub destinations with administrator-controlled host policy; revalidate DNS/connection addresses and redirects, blocking metadata/loopback/private targets except explicit audited internal-host exceptions. | 16.10 | IPv4/IPv6/DNS/redirect SSRF corpus |
| IAU15-FR-037 | Atomically persist the approved outbound intent and exact payload before network effects, with a stable receiver operation identity. | 16.10 | Transaction/crash-before-send and payload-tamper tests |
| IAU15-FR-038 | Issue one-use scoped receiver grants bound to the decision tuple, operation, expiry and live epoch; reject duplicate/replayed or altered consumption. | 16.10, 16.11 | Grant replay/expiry/epoch/source/digest tests |
| IAU15-FR-039 | Consume grants into a durable receiver operation record before external action so a consume-before-action crash resumes the same operation without a second action. | 16.11 | Receiver crash at consume/start/completion boundaries |
| IAU15-FR-040 | Distinguish dispatch acceptance, externally observed completion and delivery_unknown; reconcile unknown outcomes through receiver receipts and never report dispatch acceptance as successful deployment. | 16.11 | Lost-response/poll/receipt fault matrix and UI semantic tests |
| IAU15-FR-041 | Authorize exact-plan handoff only when the qualified self-hosted receiver can verify the original immutable saved-plan bytes in protected local custody by opaque handle, raw digest and expiry; no server/public-artifact plan storage, and replanning requires fresh evidence/approval. Upload-only advisory receipts never authorize apply or require invented repository provenance. | 16.0, 16.11, 16.14 | Real custody access/restart/overwrite/symlink/expiry/replan spike and receiver tests |
| IAU15-FR-042 | Canonicalize target lock identities across aliases and retain locks during unknown external work until verified resolution or an audited operator break that does not mint a new authorization. | 16.10, 16.16 | Alias collision/lock expiry/unknown-work/break tests |
| IAU15-FR-043 | Verify receiver callback signatures, operation/run/source identity and replay protection using the pinned GitHub adapter version and protected branch/tag dispatch ref. | 16.11 | API-version, callback replay and mutable-ref substitution contract tests |
| IAU15-FR-044 | Enroll runners using one-use tokens and project-scoped expiring credentials with rotation/revocation and outbound HTTPS protocol-version negotiation. | 16.12 | Enrollment replay/rotation/revocation/TLS/version tests |
| IAU15-FR-045 | Bind every task claim, heartbeat, log, upload and completion to the authorized runner, project, current attempt and live lease. | 16.12 | Wrong-runner/project/expired-lease matrix |
| IAU15-FR-046 | Route collection to eligible runner tags with no silent fallback; fail clearly when none qualify or enforce an explicit finite wait, and expose last-seen/version/task health. | 16.12, 16.15 | No-runner/tag-mismatch/wait-timeout and health tests |
| IAU15-FR-047 | Collect only from admitted trusted immutable sources in disposable isolated workspaces with canonical-root/symlink containment and controlled tool/provider installation; reject untrusted PR sources and inherited Git/hooks/config. | 16.13 | Hostile checkout/provider/config and isolation spike |
| IAU15-FR-048 | Execute only operator-protected fixed catalog commands with validated parameters; reject arbitrary shell, server-defined commands and app Docker-socket access. | 16.13 | Catalog tampering/option injection/arbitrary-command denial tests |
| IAU15-FR-049 | Qualify OpenTofu/Terraform plan and JSON extraction for declared pinned versions, distinguishing exit 0/no-change, 2/change and error; retain the sensitive binary plan locally and transport screened JSON only. | 16.14 | Real-tool compatibility smoke and hostile/sensitive plan fixtures |
| IAU15-FR-050 | Resolve infrastructure credentials only in the operator-owned runner/receiver execution identities under an environment allow-list and least privilege; never send or persist their values in DeployWhisper. | 16.13, 16.14 | Credential inheritance/transport/persistence corpus and separated-identity spike |
| IAU15-FR-051 | Enforce task CPU/time/disk/output/egress caps and atomic bounded uploads with cleanup after failure; cancellation must terminate the entire owned process tree. | 16.13, 16.14 | Limit, partial-upload, disk-full, egress and descendant-process tests |
| IAU15-FR-052 | Provide sanctioned React navigation, validated templates/YAML draft/publish controls and scoped workflow/run lists using actual APIs and existing design primitives without changing Dashboard information budget. | 16.7 | Compose-built workflow creation and scoped-list keyboard/a11y E2E |
| IAU15-FR-053 | Show immutable run timeline, screened logs, artifact digests, linked briefing, uncertainty and permanent report provenance links with loading/empty/error/disabled/degraded states. | 16.7 | Compose-built run/history/report states and real-data E2E |
| IAU15-FR-054 | Provide a scoped approval inbox and keyboard-operable decision screen showing exact evidence, target/payload, freshness, policy, confidence, blast radius and rollback context with acknowledgement labeling. | 16.9 | Compose-built approve/reject/self-approval/freshness E2E |
| IAU15-FR-055 | Expose runner health, collection/cancel progress and unknown/reconciliation state with advisory copy that never claims Tier 0/1 deploys infrastructure. | 16.15 | Real-runner composed E2E and unknown-state copy checks |
| IAU15-FR-056 | Accept only human-declared unit inventory and dependencies; validate exact unit coverage/cycles/unknown identities, persist deterministic preflight waves and combined evidence digest, and show accessible scope/lock tables without claiming deployment ordering. | 16.16 | Multi-unit exact-cover/cycle/digest tests and accessible table E2E |
| IAU15-FR-057 | Start scoped runs manually or through signed timestamped replay-resistant webhook intake with typed inputs, idempotency, source pinning and bounded errors/quotas; record trigger origin and principal. | 16.17 | Raw-byte HMAC/replay/idempotency/invalid-input/source tests |
| IAU15-FR-058 | Expose versioned automation API and CLI validation/run/status/list/decision commands over the same authority, envelopes and generated SPA types; agent read/request mode cannot decide or publish. | 16.17 | API/CLI/OpenAPI parity and nonhuman-mutation denial tests |
| IAU15-FR-059 | Record append-only application audit events with verified principal/type, role, scope, target, reason, time and before/after digests; expose scoped UI/JSON export without raw artifacts/secrets and document DB-admin trust limits. | 16.4, 16.9, 16.12, 16.18 | Audit event coverage/export authorization and secret corpus |
| IAU15-FR-060 | Let authorized operators configure feature enablement, targets, quotas, retention, TTL and credential lifetimes; reject unsafe reductions, protect pending evidence or invalidate its decision before deletion, and audit each change. | 16.4, 16.18 | Configuration permissions, pending-retention and floor-change tests |
| IAU15-NFR-001 | The declared crash/race corpus must lose no committed run/decision state and produce no unauthorized or duplicate receiver action, including stale attempts, unknown delivery and restore epochs. | 16.5, 16.10, 16.11, 16.19 | Published fault-injection results at every persisted boundary |
| IAU15-NFR-002 | The declared principal × role × project/workspace × object/action matrix must produce zero cross-scope reads or unauthorized mutations. | 16.1, 16.2, 16.12, 16.19 | Published complete authorization matrix results |
| IAU15-NFR-003 | The versioned sensitive-data corpus must yield zero known secret patterns in stored artifacts/logs/metadata/errors/audit or transmitted narrative summaries; no universal-redaction claim follows. | 16.6, 16.14, 16.19 | Stored/output corpus scans including chunk boundaries |
| IAU15-NFR-004 | Automation-originated fixture reports must produce zero Evidence Law violations and preserve deterministic/inferred labels and advisory report semantics. | 16.6, 16.14, 16.19 | Evidence Law and cross-surface contract CI results |
| IAU15-NFR-005 | Ready-step server orchestration overhead must have p95 <1 second, excluding collection/network/analysis duration, under the reproducible reference workload. | 16.5, 16.19 | Timestamped 1,000-transition overhead benchmark |
| IAU15-NFR-006 | Enqueue-to-claim latency must have p95 <2 seconds with 20 online compatible runners under the reference workload. | 16.12, 16.19 | Timestamped 1,000-claim runner benchmark |
| IAU15-NFR-007 | The singleton SQLite profile must sustain 10 active runs with at most 2 concurrent analysis jobs and 20 online runners, with bounded queue/storage and no corrupted transitions. | 16.5, 16.18, 16.19 | 30-minute capacity/saturation run with resource and error report |
| IAU15-NFR-008 | Workflow validation must have p95 <500 milliseconds for the declared 50-step workflow corpus under the reference workload. | 16.3, 16.19 | 1,000-validation timing/correctness benchmark |
| IAU15-NFR-009 | All new React routes must pass the composed-app axe critical/serious violation gate and keyboard-only create/run/review/decision/recovery journeys, using real API-backed seeded data and required screenshots. | 16.7, 16.9, 16.15, 16.16, 16.19 | Compose production build, Playwright/axe/keyboard results and screenshots |
| IAU15-NFR-010 | Upgrade from a v1.4.0 database copy, interrupted upgrade, coordinated DB/artifact backup/restore, token rotation and restricted-network recovery must preserve auditable state while invalidating outstanding authorization/leases until reconciled. | 16.18, 16.19 | Recorded upgrade/restore/rotation/offline exercises |
| IAU15-NFR-011 | Publish version-matched schema/API/CLI/operator/security/support-limit docs with CI link/drift checks and secret-free run/queue/step/runner/approval/delivery metrics plus troubleshooting runbooks. | 16.18, 16.19 | Docs CI and operator self-service installation/recovery pilot |
| IAU15-NFR-012 | Stable v1.5.0 requires signed app/runner artifacts, SBOM/checksums/provenance, named tool/receiver support matrix, full application CI, independent review and supported-profile pilot with no unresolved introduced critical/high defect. | 16.19, 12.5 | Signed release manifest, CI/security/review/pilot evidence |

## Leader completion verification

Final aggregate documentation verification passed: 51 documentation tests; 247 total functional/50 nonfunctional requirement inventories; all 179 original dispositions/source digest; all 72 active exact text/proof mappings; 121 unique story definitions; 20 new backlog entries; all 133 prior status entries preserved; earlier-only dependencies including 16.14→16.11; canonical links/frontmatter/whitespace. `git diff --check` passed. Final bounded independent recheck retained four open gates and three corrected alignment findings. Runtime feature, browser, collector, receiver, load and production qualification remain unexecuted. BMad Help selects preparation of Story 16.0/RFC/feasibility evidence next, with 12.5 as the parallel release-enabler story.

## Dedicated context follow-up — 2026-10-07

The owner requested `bmad-create-epics-and-stories` for the readiness work and preparation of 16.0. All 20context files are now prepared. Story 16.0 alone has ready-for-dev status for governance and disposable synthetic qualification; Epic 16 is in-progress for that preparation, with 19feature contexts held backlog. Current distribution is 121 stories: 84 done, 16 ready-for-dev, 2 review, 19 backlog. Other prior statuses/IDs are unchanged. IR-04 is split into completed documentation refinement and pending spike-based execution sizing; IR-01/02/03 retain their actual unrun or unaccepted gates. No production feature readiness or completed spike/publicRFC is claimed. Final context findings are in [the independent validation](../implementation-artifacts/epic-16-story-validation-report.md).

## Public planning/RFC closeout — 2026-10-08

The owner explicitly requested Git Flow add/commit/push/PR after validation. [PR #154](https://github.com/deploywhisper/deploywhisper/pull/154) now targets `develop` from `feature/16-0-infra-automation-planning`; opening time 2026-10-08T08:06:23Z anchors the RFC review window (not before 2026-10-15T08:06:23Z). RFC remains Proposed, Story 16.0 remains ready only for qualification, later feature contexts stay backlog and no experiment or production qualification is claimed. Root smoke passed 555 tests with one optional skip; documentation 51 tests, lint, repo-wide formatting 306 files and staged/traceability checks passed. The listed CODEOWNER is also the author; no self-review request or independent human approval is claimed.
