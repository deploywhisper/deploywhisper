# UI Parity Audit

Source: `docs/ui-migration-plan.md` Part D1. This is a historical parity record retained after cutover; the retired UI source package has been removed, and current replacements live in the React SPA under `frontend/`.

Status: Phase 2 parity audit. Every row is classified; unresolved product decisions are explicitly marked `not-in-demo -> stop-and-ask`.

## Scope

| Surface | Current React route/source | Covered |
| --- | --- | --- |
| Shared shell | `frontend/src/screens/Phase6Shell.tsx`, `frontend/src/screens/dashboard.css` | Yes |
| Dashboard | `/`, `frontend/src/screens/Dashboard.tsx` | Yes |
| Report detail | `/reports/{report_id}?private=1`, `frontend/src/screens/Report.tsx` | Yes |
| Report comparison | `/reports/{report_id}?private=1&compare=previous`, `frontend/src/screens/Report.tsx` | Yes |
| History | `/history`, `frontend/src/screens/History.tsx` | Yes |
| Settings | `/settings`, `frontend/src/screens/Settings.tsx` | Yes |
| Incidents | `/incidents`, `frontend/src/screens/Incidents.tsx` | Yes |
| Skills | `/skills`, `/skills/{skill_id}`, `frontend/src/screens/Skills.tsx` | Yes |
| Shared reports | `/reports/{id}`, `/reports/{id}/unlock`, `/reports/{id}/artifacts`, `frontend/src/screens/Report.tsx` plus `app.py` redirects/static serving | Yes |
| Artifact viewer | `/history/{id}/artifacts`, `app.py` | Yes |

## Summary

| Classification | Count |
| --- | ---: |
| `replaced-by-design` | 68 |
| `sanctioned-change` | 7 |
| `not-in-demo -> stop-and-ask` | 12 |
| Unclassified | 0 |

## Audit Table

| Surface | Old UI element, control, message, or behavior | Classification | Migration target or proposed disposition |
| --- | --- | --- | --- |
| Shared shell | DeployWhisper brand mark, wordmark, and "Evidence engine" sidebar label | replaced-by-design (B1 typography, B2 Card/Button primitives, Phase 3 dashboard shell) | Keep brand in the React app shell using Part B tokens; visual treatment follows the mockup rather than retired UI CSS. |
| Shared shell | Primary nav links: Dashboard, Skills, Incidents with badge, History, Settings | replaced-by-design (Part C Phase 3/5/6 navigation destinations) | Recreate navigation in React shell; current retired UI links map to SPA routes as each phase lands. |
| Shared shell | Active project card in sidebar with display name, key, repository context, hidden "Active Project" accessibility text | replaced-by-design (B2 ProjectSwitcher, Phase 3 dashboard scope) | Project context moves into the ProjectSwitcher/global header area; preserve project name, key, and repository context. |
| Shared shell | Header "Search analyses, services..." input | sanctioned-change (A2: two header searches become global search) | Replace with the single global search command surface. |
| Shared shell | Header project combobox search plus "New project" action | sanctioned-change (A2: ProjectSwitcher contains project search/list/New-project) | Replace with B2 ProjectSwitcher including search filtering, empty state, Escape close, listbox/option semantics, and New-project footer. |
| Shared shell | Create Project Workspace dialog: project key, display name, repository URL, default branch, description, required-field note, Cancel/Create actions, validation errors | replaced-by-design (B2 ProjectSwitcher New-project footer, Phase 6 API extraction under A3) | Preserve create-project workflow behind the React ProjectSwitcher action; extract callback-only logic when Phase 6 reaches settings/project management. |
| Shared shell | "Run Analysis" header button that scrolls to the dashboard deploy-review/upload area | replaced-by-design (Phase 3 dashboard upload card) | Replace with the dashboard New Analysis/upload entry; no separate scroll-only command needed once upload is a first-screen card. |
| Shared shell | Dark-mode toggle button and localStorage theme persistence | not-in-demo -> stop-and-ask | Proposed disposition: keep a theme toggle only if product wants user-controlled dark mode; the mockup shows dark component states but not a persistent shell control. |
| Shared shell | User initials/avatar chip ("JD") without account menu behavior | not-in-demo -> stop-and-ask | Proposed disposition: remove until a real user/account surface exists, or replace with an authenticated-user menu if product scope adds one. |
| Shared shell | Authorization failure hidden context/notifications for project access | replaced-by-design (B4 error states, Part A4 stop-and-ask rule for behavior changes) | Preserve user-visible authorization errors in React error/empty states; do not change authorization semantics. |
| Dashboard | Marketing/overview page title "Analysis snapshot" and subtitle "Real-time verdicts across every environment" | sanctioned-change (A2: marketing hero removed/replaced by Latest Briefing card) | Replace dashboard emphasis with the mockup's operational dashboard and Latest Briefing. |
| Dashboard | Evidence Law enforced chip | replaced-by-design (Part B3 sticky verdict header and Phase 3 dashboard briefing/status chips) | Preserve Evidence Law as a chip/status signal in React. |
| Dashboard | KPI cards: Total Analyses, Clean Verdict Rate, High/Critical Findings, Avg Time to Verdict with icons, live trend text, sparklines | replaced-by-design (B2 Sparkline, B2 Card, Phase 3 dashboard KPIs) | Rebuild as the four dashboard KPIs from the approved mockup using Part B tokens. |
| Dashboard | Verdict Health donut and distribution last 30 days | replaced-by-design (A2: new presentation of existing data; B2 ScoreRing/verdict visuals; Phase 3 verdict donut) | Preserve data, use the mockup donut/ring visual language. |
| Dashboard | Recent Analyses table/cards: timestamp, environment badge, risk/verdict badge, summary, source metadata | replaced-by-design (Phase 3 recent table; B2 SeverityBadge/VerdictChip/MonoRef) | Rebuild recent table with compact rows and design-system badges. |
| Dashboard | Deployment briefing card: latest summary, weighted focus score, saved briefing/high-focus stats, last-scan note | replaced-by-design (A2 Latest Briefing card; B2 Card/ScoreRing) | This is the persistent replacement for the old inline latest report. |
| Dashboard | Deploy review/upload section title and active project authorization warning | replaced-by-design (Phase 3 upload card; B4 empty/error states) | Preserve project-required behavior and authorization messaging in the React upload card. |
| Dashboard upload | Project workspace select in upload panel and Create project action | replaced-by-design (B2 ProjectSwitcher; Phase 3 upload card) | Use ProjectSwitcher as the project scope control; preserve project switching clearing staged uploads. |
| Dashboard upload | File uploader: select deployment artifacts, select artifact directory, accepted extensions, 50 MB session/file limit, relative-path metadata, directory metadata validation | replaced-by-design (Phase 3 upload multipart POST, B4 error states) | Preserve upload constraints and validation behavior; React control can be visually redesigned but must submit the same metadata. |
| Dashboard upload | Staged artifact summary: total files, accepted count, per-file tool/status/message rows | replaced-by-design (Phase 3 upload card, B4 loading/empty/error states) | Preserve feedback before analysis; use badges and list primitives. |
| Dashboard upload | Analyze button disabled until a project and accepted artifacts exist; uploads disabled while analysis runs | replaced-by-design (B2 Button disabled state, Phase 3 upload card) | Preserve enable/disable rules and in-progress lockout. |
| Dashboard upload | Progress spinner, percentage, message, progress bar, "Uploads are disabled while analysis is running." | replaced-by-design (B4 skeleton/loading states, Phase 3 upload card) | Preserve progress feedback with React loading states. |
| Dashboard upload | Provider-readiness modal: "LLM provider not ready", provider/model, readiness message, heuristic-only warning, Cancel, Continue Anyway | not-in-demo -> stop-and-ask | Proposed disposition: preserve the confirmation workflow unless product decides heuristic-only analysis should run silently. |
| Dashboard upload | Notifications: no supported artifacts, select/create project, partial context, completion, persistence/analysis failure cards | replaced-by-design (B4 error states, Phase 3 upload flow) | Preserve messages and failure semantics; visual presentation follows the React design. |
| Dashboard latest result | Embedded full report after analysis: verdict badges, top risk, narrative, parse summary, saved report link, manifest notices, provenance, provider/model/skills, LLM notices, topology banner, context summary, confidence ledger, incidents, change table, findings, reviewer feedback, context completeness, blast radius, rollback, resource breakdown | sanctioned-change (A2: embedded full analysis result removed; upload navigates to Report screen) | Do not rebuild inline on dashboard. On completion navigate to the permanent Report screen; dashboard keeps only Latest Briefing. |
| Dashboard latest result | Expiry countdown label "Disappears in ..." and clearing the active dashboard result after the configured duration | sanctioned-change (A2: countdown mechanism retired) | Drop countdown and expiry from React dashboard; full report persists at its own URL. |
| Dashboard latest result | Dashboard Result Display Duration setting dependency | sanctioned-change (A2: setting retired) | Remove from Phase 6 settings. |
| Dashboard latest result | Ownership context / CODEOWNERS follow-up rows derived from artifact paths | not-in-demo -> stop-and-ask | Proposed disposition: preserve as report-tab evidence/context guidance if still required; decide whether it belongs in Findings, Audit, or Context. |
| Report detail | Header: "Analysis report", severity, recommendation, confidence, timestamp, top risk, explanatory copy, topology freshness banner, numeric risk score | replaced-by-design (B3 sticky verdict header; B2 SeverityBadge/VerdictChip/ConfidenceBadge/ScoreRing) | Rebuild as sticky verdict header with design-system chips and score ring. |
| Report detail | Header signals: Verdict, Advisory posture, Evidence Law, Confidence, Top risk, Next action | replaced-by-design (B3 Overview tab and sticky header) | Preserve signal content, reorganized into B3 header/Overview. |
| Report detail | Description and Advisory cards, deterministic fallback text, LLM note, report warning | replaced-by-design (B3 Overview tab; B4 error/warning states) | Preserve narrative and deterministic fallback messaging inside Report screen. |
| Report detail | Context summary and topology freshness panels | replaced-by-design (B3 Context tab; B2 Card/SeverityBadge) | Preserve context quality and freshness indicators in Report tabs. |
| Report detail | Operational narrative: What changed, why risky, exact resource/file, verify before deploying, rollback concern | replaced-by-design (B3 Overview and Findings expanded detail) | Preserve copy blocks, but distribute by the tab anatomy rather than one long page. |
| Report detail | Confidence ledger: contributors, factors, why-not-lower, why-not-higher, uncertainty drivers | replaced-by-design (B3 Confidence tab) | Preserve ledger sections in the dedicated tab. |
| Report detail | Incident/risk pattern similarity cards and empty state | replaced-by-design (B3 Incident similarity section; Phase 6 Incidents list/detail port) | Preserve matching evidence and guidance in the report. |
| Report detail | Findings table with evidence refs, redaction states, artifact links, legacy schema handling | replaced-by-design (B3 Findings tab; B2 EvidenceTag/MonoRef) | Preserve evidence/redaction semantics; use expanded finding rows. |
| Report detail | Reviewer feedback separate block: Thumbs up, Mark noisy, false-positive reason textarea, Mark false positive, missed-finding notes, legacy missed-finding notes | replaced-by-design (A2: feedback moves inline into each expanded finding; B3 Findings tab) | Preserve feedback actions but move them inline per design. |
| Report detail | Context completeness detailed panel and TODOs | replaced-by-design (B3 Context tab) | Preserve full breakdown off the dashboard. |
| Report detail | Blast radius detail or "No blast radius data..." empty state | replaced-by-design (B3 Blast radius/report tab content) | Preserve populated and empty states. |
| Report detail | Rollback plan detail or "No rollback plan..." empty state | replaced-by-design (B3 Rollback tab content) | Preserve populated and empty states. |
| Report detail | Resource severity breakdown including contributor metadata and security flags | replaced-by-design (B3 Findings/Audit tabs) | Preserve contributor detail outside dashboard. |
| Report detail | Audit metadata: interface, provider, trigger, files analyzed, scoring/narrative source, model, schema, skills, submission manifest, fallback artifacts | replaced-by-design (B3 Audit tab) | Preserve audit metadata and manifest/fallback warnings. |
| Artifact viewer | `/history/{id}/artifacts` raw artifact snapshot table with line numbers, highlighted line, Back to history link | not-in-demo -> stop-and-ask | Proposed disposition: keep as evidence drill-down from Report Findings unless product chooses a safer inline source excerpt component. |
| History | Page header "History / Analysis history", project-scoped subtitle, Back to dashboard | replaced-by-design (Phase 5 History screen; B2 Card/Button) | Rebuild as React History page header. |
| History | Risk trends summary block: total reports, critical/high counts, top tools, outcomes, calibration signals, context completeness, trend deltas, limitation labels | not-in-demo -> stop-and-ask | Proposed disposition: preserve as a collapsible analytics/summary panel only if product wants history analytics in Phase 5. |
| History | Calibration snapshot block: failed deploys, warned failed, precision, recall, window, confidence label, limitation labels | not-in-demo -> stop-and-ask | Proposed disposition: move to a future analytics/calibration surface or include as optional History panel; do not drop silently. |
| History filters | Search top risk or summary | replaced-by-design (Phase 5 server-side search filter; B2 controls) | Preserve as History search. |
| History filters | Project filter display and workspace select | not-in-demo -> stop-and-ask | Proposed disposition: keep project scoping via global ProjectSwitcher; decide whether workspace needs a History-local filter. |
| History filters | Time range, risk verdict/severity filters | replaced-by-design (Phase 5 server-side filters; B2 SegmentedTabs/select controls) | Preserve filtering; map severity to design-system controls. |
| History filters | Toolchain, analysis status, outcome filters | not-in-demo -> stop-and-ask | Proposed disposition: keep if operations teams rely on them; otherwise defer behind an advanced filter menu. |
| History rows | Compact report rows: checkbox, timestamp, severity, interface, top risk, recommendation, narrative/parse summary, project/workspace, tools, schema, status | replaced-by-design (Phase 5 compact rows; B2 SeverityBadge/VerdictChip/MonoRef) | Preserve row data in compact React rows; avoid repeating full verdict sentences. |
| History rows | Topology freshness age/badge plus Manage topology link | replaced-by-design (B3/Phase 5 row detail; Phase 6 topology settings) | Preserve freshness indicator and route Manage topology to settings. |
| History rows | Rescan diff line: score delta, previous report id, severity transition, recommendation transition | replaced-by-design (Phase 5: compact rows include rescan delta) | Preserve rescan delta in History rows. |
| History rows | Confidence badge and provenance line: risk/narrative/provider | replaced-by-design (Phase 5 expandable detail; B2 ConfidenceBadge) | Preserve in expanded row detail. |
| History actions | Select all on page, selection count, Previous/Next pagination, Delete selected bulk action | replaced-by-design (Phase 5: bulk select + delete, pagination) | Preserve bulk selection, deletion, and pagination. |
| History actions | Per-row Delete action and delete confirmation dialog text "This action cannot be undone." | not-in-demo -> stop-and-ask | Proposed disposition: decide whether bulk delete alone is sufficient or single-row delete remains required. |
| History empty/error | "No reports match the current filters." and authorization/no-project trend limitations | replaced-by-design (B4 empty/error states) | Preserve empty and authorization states. |
| Report comparison | `/history/{id}/compare`: side-by-side previous/current report, risk score delta, warnings, topology freshness, resolved/new/persistent/context-changed/severity-changed findings | not-in-demo -> stop-and-ask | Proposed disposition: preserve comparison either as a Report tab/action or align with Phase 4 "Compare with previous" behavior. |
| Report detail missing | Missing report and schema/read errors shown as warning cards with Back to history action | replaced-by-design (B4 error states; Phase 5/Report routing) | Preserve not-found/unreadable states. |
| Settings | Header "Operational settings" and Back to dashboard | replaced-by-design (Phase 6 Settings screen) | Rebuild settings shell with Part B cards and form controls. |
| Settings AI provider | Active Provider select, Model input, API base input, masked API key with reveal, Local-only mode toggle, Save AI settings, validation feedback | replaced-by-design (Phase 6 provider section; B2 Button/Card; A3 callback extraction) | Preserve provider settings behavior via extracted `/api/v1` endpoints. |
| Settings AI provider | Secrets notice that API keys are not stored in the app database | replaced-by-design (Phase 6 Settings provider section) | Preserve as explanatory settings copy. |
| Settings AI provider | Provider capabilities notice and dynamic summary: Structured output, Local-only, Remote MCP, Local MCP, Tool approval | not-in-demo -> stop-and-ask | Proposed disposition: keep if needed for operator trust; decide whether it belongs in provider settings or a collapsed advanced details row. |
| Settings dashboard duration | Dashboard Result Display Duration select and "currently remain visible" / "will remain visible" feedback | sanctioned-change (A2: retired with countdown mechanism) | Remove from React settings. |
| Settings topology | Topology context section, active project label, topology JSON upload, validation preview, save topology button, success/error/warning/blocking-error messages | replaced-by-design (Phase 6 topology upload via Phase-2 dropzone; B4 error states; A3 callback extraction) | Preserve validation-before-save and project scoping. |
| Settings topology | Topology status: service/dependency/resource mapping counts, active file, last updated, preview services, no-active-topology state | replaced-by-design (Phase 6 topology settings) | Preserve status block in settings. |
| Settings topology | Topology drift block: no check yet, status, drift check cadence, last/next check, changed resources, added/removed/modified resources, warnings | replaced-by-design (Phase 6 topology drift cadence) | Preserve drift cadence and status details. |
| Settings feedback | Reviewer feedback summary: Useful, Noisy, False positives, Missed findings, recorded events, Recent notes/empty state | replaced-by-design (Phase 6 reviewer-feedback stat cards) | Preserve metrics and recent notes. |
| Settings custom skills | Custom AI Skills copy, markdown upload, detected/ignored status rows, path, warning, success/error messages, no custom skills empty state | replaced-by-design (Phase 6 custom-skills manager; A3 callback extraction) | Preserve upload and status behavior through React/API extraction. |
| Incidents | Header "Incident ingestion management", project authorization unavailable warning | replaced-by-design (Phase 6 Incidents list/detail port; B4 error states) | Rebuild as React incidents surface. |
| Incidents | Project summary stats: indexed incidents, rejected records, redaction status, index freshness, last indexed | replaced-by-design (Phase 6 Incidents list/detail port; B2 Card) | Preserve project incident status cards. |
| Incidents | Incident sources list: import source, title, freshness, scope/indexed/rejected/redaction, last indexed, failure summaries with correction path | replaced-by-design (Phase 6 Incidents list/detail port) | Preserve source rows and actionable failure/correction messages. |
| Incidents | "No incident sources indexed..." empty state | replaced-by-design (B4 empty states; Phase 6 Incidents) | Preserve empty state. |
| Skills browser | Marketplace hero, skills atlas title, visible skills/catalog installs/open issues/passing harnesses stats | replaced-by-design (Phase 6 Skills list/detail port; B2 Card) | Rebuild as React skills list with registry metrics. |
| Skills browser | Search skills/tags/triggers, Tool select, Author select, Sort select, URL query filters | replaced-by-design (Phase 6 Skills list; B2 controls) | Preserve filter behavior. |
| Skills browser | Catalog header, Open public registry link, no-match empty state | replaced-by-design (Phase 6 Skills list/detail port; B4 empty states) | Preserve external registry link unless product removes it explicitly. |
| Skills browser | Skill rows: name, description, Official/Featured badges, tool/author/maintainer/updated/version metadata, tags, installs/pass rate/issues metrics, install-ready chip, install command | replaced-by-design (Phase 6 Skills list/detail port; B2 badges/cards/MonoRef) | Preserve list fields and install command visibility. |
| Skills detail | Skill detail header/back, install command, author/maintainer/installs/issues/updated/pass-rate stats, tracked versions, analytics refreshed | replaced-by-design (Phase 6 Skills detail) | Preserve detail fields. |
| Skills detail | Contributors, version history current/archived rows, Ready to install, full tags, registry snapshot copy | replaced-by-design (Phase 6 Skills detail) | Preserve sections in React detail layout. |
| Skills detail | 404 "Skill not found" behavior | replaced-by-design (B4 error states) | Preserve not-found route behavior. |
| Shared reports | Password prompt: "Shared DeployWhisper report", "This shared report requires a password.", invalid password error, password input, Open shared report button | replaced-by-design (Phase 4: reuse same screen for public `/reports/{id}`, password-protected shares respected; B4 error states) | Preserve password flow before rendering shared report. |
| Shared reports | Unlock POST issues HttpOnly cookie, safe redirect back to report/compare target, invalid password returns 401 prompt | replaced-by-design (Phase 4 shared report behavior) | Preserve auth-cookie and safe redirect semantics. |
| Shared reports | Shared report overview: severity/recommendation badges, score, narrative, topology freshness, shared-view marker, created, share URL, blast radius, rollback, findings, files analyzed | replaced-by-design (Phase 4 public Report screen; B3 report tabs/actions hidden) | Reuse Report screen with actions hidden and public-share constraints. |
| Shared reports | Compare with previous link and comparison mode including previous password gate | replaced-by-design (Phase 4: "Compare with previous" preserved) | Preserve compare flow and previous-report password gate. |
| Shared reports | Shared confidence ledger and incident/risk-pattern similarity sections | replaced-by-design (B3 Confidence/Incidents report sections) | Preserve on public report with safe redactions. |
| Shared reports | Redacted filename note when share redacts filenames | replaced-by-design (B3 Audit/Evidence redaction states) | Preserve redaction notice. |
| Shared reports | `/reports/{id}/artifacts` always returns 404 so public shares never expose raw artifact snapshots | replaced-by-design (Phase 4 public Report security behavior) | Preserve non-exposure of raw artifacts on public links. |
