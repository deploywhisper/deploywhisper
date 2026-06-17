# DeployWhisper UI Migration Plan — retired UI to React SPA

**Status:** approved · dashboard-first · this document is normative
**Design references (commit both to the repo):**
- `docs/design/deploywhisper-redesign-v3.jsx` — the approved interactive mockup. When this plan and the mockup disagree on an exact value, **the mockup wins**.
- `docs/ui-migration-plan.md` — this file. It is the contract for scope, process, and completeness.

**Target stack:** Vite + React 18 + TypeScript + Tailwind CSS, built to static files and served by the existing FastAPI app. Single-container model preserved. No Node in the runtime image. The retired UI framework is fully removed at the end of this initiative.

---

# PART A — SCOPE GUARDRAILS (read first, applies to every task)

A1. **This is a UI/UX modernization and migration.** Backend logic, APIs, data models, the analysis pipeline, CLI, and the GitHub Action remain unchanged, except for the explicitly sanctioned backend work listed in A3.

A2. **Sanctioned UX/workflow changes.** The demo deliberately changes some flows versus the old UI. These are approved product decisions, not accidents — implement them as shown:
- The two header search boxes ("Search analyses…" + "Search repo or project name" + New project) are replaced by **one global search (⌘K)** plus a **ProjectSwitcher** dropdown containing project search, project list, and the New-project action.
- The marketing hero ("Know the risk before you hit deploy") is removed from the dashboard and replaced by the **Latest Briefing** card.
- The single long scrolling report page becomes a **sticky verdict header + six tabs**.
- Reviewer feedback (Useful / Noisy / False positive) moves **inline into each expanded finding** instead of a separate form block.
- "Copy briefing" in the report header copies the share-summary markdown that the GitHub Action already produces.
- The verdict-health donut, KPI sparklines, and score ring are new presentations of existing data.
- **The embedded full analysis result is removed from the dashboard.** The old dashboard renders the entire latest report inline (5-second verdict block, full narrative, summary context check, confidence ledger, uncertainty drivers, incident similarity, findings table, reviewer-feedback form, context completeness, blast radius, rollback plan, resource severity breakdown) on an expiry timer. In the new design, none of that lives on the dashboard: completing an upload navigates the user to the Report screen, and the dashboard's only trace of the last analysis is the persistent **Latest Briefing** summary card (score, verdict, one-line summary, three stats, CTA).
- Consequently the **"Dashboard Result Display Duration" setting and its countdown mechanism ("Disappears in…") are retired** — the briefing card is persistent and the full report is permanent at its own URL, so an ephemeral display window no longer has a purpose. The Phase 6 settings rebuild drops this option; record it as `sanctioned-change (A2)` in the parity audit.

A3. **Sanctioned backend changes — nothing else without human approval:**
- New **read-only** stats endpoints (Phase 3.0): `GET /api/v1/stats/summary`, `GET /api/v1/stats/verdict-distribution`, `GET /api/v1/projects` (if not already exposed).
- **Additive-only** serializer fields where a list/detail response lacks a field the design displays.
- Phase 6 extraction of logic that existed only inside retired UI callbacks (settings save, topology upload, skills management) into `/api/v1` endpoints — extraction means moving behavior, not changing it.
- Every backend change ships in its own PR labeled `backend-for-ui`, with the design field it serves named in the description.

A4. **Stop-and-ask rule.** If implementing any screen appears to require changing application flow, validation behavior, or an API contract beyond A2/A3, the agent stops and raises the question in the PR/issue instead of deciding. "The old UI did X, the demo does not show X" is a stop-and-ask case (see Part D parity audit), not a license to drop X.

A5. **Air-gap rule.** No CDN imports anywhere in production code — no Google Fonts, no unpkg/cdnjs/jsdelivr. Fonts ship via `@fontsource` packages; icons via the `lucide-react` npm package. The `@import url(fonts.googleapis…)` line in the mockup exists only because it is a sandbox demo; carrying it into the app is a defect.

A6. **Definition of done for the whole initiative** (Part G is the checklist): every old screen has a new-design replacement at parity or with a sanctioned change; zero retired UI code, dependencies, styles, or assets remain; all documentation in Part E updated; all testing standards in Part F in place and green.

---

# PART B — NORMATIVE DESIGN SPECIFICATION

## B0. Design principles & the dashboard information budget

These principles govern every screen and every judgment call the spec below doesn't explicitly settle:

1. **Function- and workflow-driven design.** The interface is shaped by what users do — upload artifacts, get a verdict, drill into evidence, decide go/no-go — not by what data the system can display. Every screen answers one primary question; for the dashboard that question is *"what is the state of my deployments right now, and what needs my attention?"* — nothing more.
2. **Progressive disclosure.** Summary on the dashboard, detail in the report, raw depth inside report tabs. Information appears at the moment of need, never all at once. If a user must scroll past data they didn't ask for to reach data they did, the layout is wrong.
3. **Critical data first.** Verdict, risk score, and open high/critical findings are the loudest elements on any screen that shows them. Supporting context (confidence, freshness, audit trail) is reachable in one interaction but never competes visually with the decision-driving data.
4. **Concise, scannable, refined.** Modern, intuitive, aesthetically disciplined per the B1/B2 system; no walls of repeated text, no raw internal strings or provider errors in the UI, no two elements doing the same job on one screen.
5. Where conciseness and completeness conflict, the dashboard chooses conciseness and links to completeness; the report chooses completeness organized by tabs.

**Dashboard information budget (hard rule for Phase 3 and forever after):**

*The dashboard MAY contain only:* the greeting + Evidence Law chip; the four KPI cards; the recent-analyses table (5 rows, one line each); the Latest Briefing summary card (score ring, verdict chip, one-sentence summary, three stat tiles, one CTA); the new-analysis upload card; the verdict-health donut with its single alert strip.

*The dashboard MUST NOT contain:* full or partial report narrative; the confidence ledger or uncertainty drivers; findings tables or finding bodies; reviewer-feedback controls; context-completeness breakdowns or context TODOs; blast-radius detail; rollback plans; resource severity breakdowns; raw provider/LLM error strings; any expiring/countdown content. All of these exist exclusively as Report-screen tabs (B3). The old UI's pattern of embedding the latest report on the dashboard is retired by rule A2 and must not be reintroduced in any form — including "just one extra section."

A PR that adds dashboard content outside this budget is rejected regardless of how useful the content seems; the correct destination is a report tab or a dedicated screen, raised via A4 if genuinely new.

Everything below this point is extracted from `deploywhisper-redesign-v3.jsx`. The agent must not restyle, approximate, or "improve" these values. Demo content (payments-api, PR #2847, score 78, INC-2024-Q3-17) is **illustrative data** — bind every value to the real API; never hard-code demo content.

## B1. Design tokens

### Color

| Token | Value | Use |
|---|---|---|
| brand | `#F2551F` | primary accent, active icons, links |
| brandDark | `#CE3D0C` | active text on brandSoft |
| brandSoft | `#FEF0E9` | active nav bg, icon tiles, selected option bg |
| brand gradient | `linear-gradient(135deg,#FF8A4C 0%,#F2511F 55%,#E03D0A 100%)` | primary buttons, logo tile, avatar, critical rollback steps, ring stroke |
| bg | `#F5F6F8` | app background |
| card | `#FFFFFF` | all light cards |
| border | `#E7E9EE` | card and control borders |
| borderSoft | `#F0F1F4` | row dividers, inner panel borders |
| ink | `#0E1116` | headings, primary numbers, dark buttons |
| text | `#252B36` | body text |
| muted | `#667085` | secondary text |
| faint | `#98A2B3` | tertiary/micro text, placeholder, inactive icons |
| dark | `#14161C` | dark surfaces (briefing card, diff body, sidebar project card) |
| dark2 | `#1F222B` | dark inner tiles, diff titlebar |
| darkBorder | `#2C303C` | borders on dark surfaces |

Severity scale (fg / bg / dot):
- CRITICAL `#D92D20` / `#FEECEB` / `#F04438`
- HIGH `#E04F16` / `#FEF0E7` / `#F2551F`
- MEDIUM `#B54708` / `#FEF4E4` / `#F5A60A`
- LOW `#079455` / `#E9F8F0` / `#17B26A`

Verdict fills: NO-GO `#D92D20` · CAUTION `#F2551F` · PROCEED `#079455` (white text on all).

Evidence/positive green set: bg `#F2FBF6`, border `#CFEBDA`/`#D5EBDD`, text `#067647`; dark-surface green text `#75DFA6`.

Warning callout set: bg = highBg `#FEF0E7`, text `#93370D`.

### Typography

| Role | Family | Weights | Notes |
|---|---|---|---|
| display | Plus Jakarta Sans | 500–800 | headings, buttons, numbers, chips |
| body | Inter | 400–600 | default UI text |
| mono | JetBrains Mono | 400–600 | everything evidential: file:line refs, scores, env tags, IDs, eyebrows, durations, audit values |

Scale (size / weight / extras): h1 22/800/`-0.03em`; h2 15/700; h3 14.5/700; card-title-large 16.5/800 (report title); body 13.5 line-height 1.65; secondary 12.5; table text 13; micro labels 11–12; eyebrow = mono 9.5 uppercase letter-spacing `0.15em`; table headers 10.5/600 uppercase `0.04em`; KPI value 25/800/`-0.03em`; ring score = 0.3 × ring size at 800.

**Mono-as-evidence rule:** anything deterministic (paths, line numbers, scores, incident IDs, EV-ids, durations, env names) renders in mono. This is the design system's expression of the Evidence Law — do not render these in body font.

### Geometry, depth, motion

- Radii: cards 16 · inner panels/tiles 11–12 · buttons 10–11 · badges/pills/tabs 999.
- Shadows: card `0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.05)`; hover/pop `0 4px 10px rgba(16,24,40,.06), 0 12px 28px rgba(16,24,40,.09)`; primary-button glow `0 4px 14px rgba(242,85,31,.32)`; dark-card `0 8px 28px rgba(16,24,40,.22)`; popover `0 4px 12px rgba(16,24,40,.08), 0 20px 48px rgba(16,24,40,.16)`; verdict-chip glow = `0 2px 8px {fill}55`.
- Motion: card hover `translateY(-2px)` + pop shadow (.18s ease); buttons hover `translateY(-1px)`, active `scale(.97)`; finding chevron rotates 180° (.18s); score-ring stroke-dashoffset animates .6s ease on mount; active-project ping keyframe (scale 2.2 fade, 1.6s loop). **All motion disabled under `prefers-reduced-motion: reduce`.**
- Layout: sidebar 236px fixed, white, 1px right border (hidden < 900px); content `max-width 1120px`, horizontal padding 28px, vertical 22–26px; section gaps 18px; KPI grid 4-col ≥1000px / 2-col below; two-column rows are `2fr 1fr` ≥1000px, stacked below; report two-column is equal halves for ledger cards.
- Sticky surfaces: top bar `rgba(255,255,255,.85)` blur 12; report header `rgba(245,246,248,.88)` blur 14, z-index above content, bottom border `border`.
- Focus: every interactive element shows `outline: 2px solid #F2551F; outline-offset: 2px` on `:focus-visible`.

## B2. Component anatomy (build all in Phase 2; each line is a requirement)

**Sidebar** — logo tile 36px radius-11 gradient with white ShieldCheck 18; wordmark "Deploy" ink + "Whisper" brand, display 800 15; eyebrow "EVIDENCE ENGINE" mono 8.5. Nav item: icon 17 (brand when active, faint otherwise), label 13.5, active = brandSoft bg + brandDark text + weight 600, hover `#F3F4F7`, radius 11, padding 9×13; count pill mono 10 on `#F0F1F4`. Bottom: dark active-project card (radius 16, dark bg, dark shadow) — "ACTIVE PROJECT" mono eyebrow with animated ping dot in brand, project name display 700 14 white, env mono 10.5 `#7E8696`, and an inner dark2 chip "Evidence Law enforced" mono 9.5 in `#75DFA6` with shield icon. Card content is driven by the selected project.

**Top bar** — global search: max-width 380, bg `#FBFBFC`, border, radius 11, Search icon 15 faint, placeholder 13 faint, right-aligned `⌘K` kbd chip (mono 10, white bg, border). Then spacer → ProjectSwitcher → 1px×22 divider → primary "Run analysis" button (gradient, glow, Play icon 13 filled white, display 700 13) → avatar 34 gradient circle, initials display 700 12.

**ProjectSwitcher** — closed: ghost button containing 20px brandSoft tile with FolderGit2 12, project name (12.5/600, ellipsis at 140px), env pill (mono 9.5 on `#F0F1F4`), ChevronsUpDown 13 faint; open state adds brand border + `0 0 0 3px rgba(242,85,31,.12)` ring. Popover: width 296, radius 14, popover shadow, anchored below-right; rows top-to-bottom: (1) search row with autofocus input "Search projects…" 13, bottom border; (2) scrollable list max-height 240 with eyebrow `PROJECTS · {n}`; (3) option rows — 28px icon tile (white tile + brand icon when selected, `#F3F4F7` + muted otherwise), name 13/600 (brandDark when selected) + env mono 9.5 inline, description 11 muted ellipsis, Check 15 brand on the selected row, selected bg brandSoft, hover `#F3F4F7`, radius 9; (4) empty state: `No project matches "{q}". Create it below.` 12.5 muted; (5) pinned footer "New project" — 22px brandSoft Plus tile, 12.5/600 brand text, bg `#FCFCFD`, top border, hover brandSoft. Search filters live; selecting closes, clears the query, and updates sidebar card + dashboard subtitle + upload workspace ref. Transparent full-screen backdrop closes on outside click; Escape must also close (add — not in mockup). Roles: `listbox`/`option`/`aria-selected`, trigger `aria-haspopup` + `aria-expanded`.

**KPI card** — padding 17; header row = 32px brandSoft icon tile (brand icon 15) left, Sparkline 76×26 right; label 12/500 muted; value row = number 25/800 + delta chip (radius 999, 10.5/600, ArrowUpRight/ArrowDownRight 11; good = lowBg/low, attention = highBg/high). Hover lift. Sparkline: stroke 1.7 round-cap, gradient area fill opacity .2→0, unique gradient id per instance.

**Recent analyses table** — card header: title h3 + subtitle 12 + "View history ›" link (brand 12/600, hover brandSoft bg, radius 8). Header row: bg `#FAFBFC`, top+bottom borderSoft, uppercase 10.5 faint: CHANGE / SEVERITY / VERDICT / SCORE / ENV / (chevron col). Row: 28px `#F3F4F7` tile with FileCode2 13 → filename mono 12 ink + `PR {n} · {dur}` 11 faint; SeverityBadge; VerdictChip (sm); ScoreBar = 38×5px track `#EEF0F3` with fill width `{score}%` colored by the severity **dot** color + score in mono 12.5/600 ink; env mono 11 muted; ChevronRight 15 faint on clickable rows only. Hover `#FAFBFC`; borderSoft dividers; first cell left padding 20. Row click navigates to that report.

**Latest briefing card (dark)** — radius 16, dark bg, dark shadow, decorative radial brand glow (190px circle, top-right offset −56, opacity .22, `pointer-events:none`); full height of its grid cell via flex column. Content: eyebrow `LATEST BRIEFING` mono 9 `#7E8696` + CAUTION/whatever-verdict chip (sm) right; row = ScoreRing 72 (dark track) + summary 12.5/1.6 `#C2C7D1` (flex 1); 3-col stat tiles (dark2 bg, darkBorder, radius 11): value display 700 15.5 white + label 10 `#7E8696` — blast radius / incident match / rollback est.; CTA "Open full briefing ›" full-width gradient button **anchored to the card bottom** (`margin-top:auto`). Entire card is driven by the most recent analysis.

**Upload / New analysis card** — header: h3 "New analysis" + subtitle `Workspace {MonoRef project · env}` + "Change project" link (opens ProjectSwitcher). Dropzone: 2px dashed `#DCDFE6`, radius 16, bg `#FBFBFC`, padding 38×24; 44px circle icon tile (`#EFF1F4`/faint, Upload 18) — hover state: border brand, bg brandSoft, tile becomes gradient + white + glow; line 1: `Drop deployment artifacts, or **browse files**` (13.5, "browse files" brand 600); line 2 mono 10.5 faint: `.tf · k8s yaml · ansible · Jenkinsfile · CloudFormation`. Footer: `{n} files staged` 12 faint left; Analyze button right — disabled: `#F0F1F4` bg + faint text + not-allowed cursor; enabled: primary gradient. Real behavior (Phase 3): drag-and-drop + click-to-browse, staged file list with per-file remove, client-side filter to supported extensions, multipart POST, in-flight progress state, success navigates to the new report, failure shows error state on the card.

**Verdict health card** — donut 104px via conic-gradient in series order High focus `#F2551F` → Caution `#F5B40A` → Clear `#17B26A`; inner white circle inset 10; center: dominant share % display 800 19 + label 9.5 faint. Legend rows: 8px dot, label 12.5, count mono 11.5/600 right. Alert strip: radius 11, highBg, text 11.5 `#93370D`, AlertCircle 14, copy pattern `“{n} of {total} reports are high or critical. Review open findings before the next release window.”` — computed, not hard-coded.

**Badge system (used identically everywhere):**
- `SeverityBadge`: pill, 6px dot in severity-dot color, label Title-case 11/600, tinted bg + fg per scale.
- `VerdictChip`: filled pill, white text, AlertTriangle 12 (NO-GO/CAUTION) or CheckCircle2 12 (PROCEED), uppercase display 700, letter-spacing `.07em`, glow `{fill}55`; md = 11/5×13 padding, sm = 10/3×10.
- `EvidenceTag`: radius 7, mono 10.5, green set, CircleDot 9.
- `ConfidenceBadge`: outline pill, Activity 11, Title-case 11/500; HIGH = green border/text, LOW = `#F9DBCB` border + high-orange text.
- `MonoRef`: inline code chip — mono 0.85em, bg `#F2F4F7`, 1px `#E7E9EE` border, radius 6, ink text, nowrap.

**ScoreRing** — SVG, track `#EEF0F3` (light) / `#2C303C` (dark), progress stroke = brand gradient, round linecap, −90° start; centered score (display 800, 0.3×size) over `/100` mono 8. Sizes used: 76 (briefing), 72 (dark), 62 (report header).

## B3. Report screen specification

**Sticky header** (sticky top, blurred `rgba(245,246,248,.88)`, bottom border; everything below scrolls under it):
Row 1: square ghost back button (ArrowLeft 16, radius 11) → ScoreRing 62 → center block: badge row in this order: VerdictChip(md) · SeverityBadge · ConfidenceBadge · EvidenceTag `“{n} deterministic items”`; title 16.5/800 single-line ellipsis; meta row 11.5 muted: `MonoRef PR#` · `project · env` · date · `· {files} files · {duration}` (mono) separated by faint `·` → right: ghost buttons **Compare** (GitCompare 13) and **Share** (Share2 13), then dark button **Copy briefing** (Copy 13).
Row 2: SegmentedTabs — container `#EDEEF2` bg + border, radius 999, padding 4; tab 12.5 display, muted/500 inactive → active = white pill, ink 700, `0 1px 3px rgba(16,24,40,.14)`; Findings tab carries count pill (mono 10/700, highBg/high). Tabs: Overview · Findings · Confidence · Context · Rollback · Audit. Horizontal scroll on overflow; `role=tablist/tab` + `aria-selected`.

**Card primitive** for all report sections: white card, padding 20, header = eyebrow (mono 9.5 uppercase) + title h2 + optional right-slot action; content offset 14.

**Overview tab** — left column (2fr): (1) `OPERATIONAL NARRATIVE / What changed, and why it's risky` — body paragraphs with every file, line, resource, and incident reference wrapped in MonoRef; (2) warning callout: highBg radius 12, 28px white tile with AlertCircle high, bold 12.5 display title "Verify before deploying", body 12.5, all text `#93370D`; (3) `TOP FINDINGS / {n} findings · {x} high, {y} medium` with "All findings ›" right-action switching to the Findings tab — rows: SeverityBadge + title 13/500 ellipsis + first EvidenceTag right, borderSoft dividers. Right column (1fr): (4) `DECISION INPUTS / At a glance` — four rows, each 36px brandSoft tile (Network/History/RotateCcw/ShieldCheck 15) + label 11.5 muted + right-aligned mono 9.5 context + value display 700 13.5: Blast radius, Incident match, Rollback, Evidence Law; (5) `CONTEXT QUALITY / Completeness` — value 23/800 + `/1.00` 11.5 faint, 7px progress track `#EEF0F3` with `linear-gradient(90deg,#34D399,#079455)` fill at score %, 12/1.6 muted summary.

**Findings tab** — vertical stack gap 14 of expandable cards. Collapsed row: 36px severity-tinted tile with AlertTriangle 16, title display 700 14 + SeverityBadge + optional Cross-tool chip (brandSoft pill, brandDark 10/700, Layers 10), body 13/1.6 muted, EvidenceTag row, ChevronDown 16 (rotates open). Expanded: borderSoft top rule, `#FAFBFC` panel containing the DiffBlock (or cross-reference text), then feedback row: `Was this finding useful?` 11.5 faint + pills **Useful / Noisy / False positive** (white, border, 11.5/500, hover lift) wired to the existing reviewer-feedback persistence. Exactly one finding open by default (the first); opening another may collapse the previous (accordion) as in the demo.

**DiffBlock** — radius 12, dark shadow; titlebar dark2 with three 10px macOS dots `#FF5F57 #FEBC2E #28C840` + filename mono 11 `#9CA3B2`; body dark, mono 12; line number col 40px right-aligned `#4A5160` non-selectable; +/− gutter 20px; added line bg `rgba(23,178,106,.13)` text `#75DFA6`; removed `rgba(240,68,56,.13)` / `#FDA29B`; context `#7E8696`.

**Confidence tab** — two equal cards `Why not lower` / `Why not higher` (eyebrow `CONFIDENCE LEDGER`): numbered rows, 20px mono circles — hot side highBg/high, neutral side `#F0F1F4`/muted; body 13.5/1.65 with MonoRefs. Below, full-width `EVIDENCE REGISTER / {n} deterministic items`: bordered radius-12 list, zebra `#FAFBFC`, each row `EV-0n` mono faint → MonoRef reference → description 13 ellipsis → source pill (PARSER/SCANNER/MEMORY — mono 10 uppercase on `#F0F1F4`). Footnote with green shield: `AI explains. Evidence decides — disable the narrative layer and this register still stands.`

**Context tab** — (1) completeness checklist card: rows with 24px circle (lowBg+CheckCircle2 pass / highBg+AlertCircle fail), label 13/500 ink at fixed 185px, value mono 12 (high-orange when failing), right-aligned hint 12 faint; ghost CTA `+ Resolve open context TODO` in brand. (2) `BLAST RADIUS / {n} services affected`: service chips — mono 11.5 pills with 6px dot; direct services = brandSoft bg + `#F9DBCB` border + brandDark + brand dot; transitive = `#FAFBFC` + neutral; summary line 12 muted (`x direct, y transitive · graph depth · topology age`).

**Rollback tab** — single card `ROLLBACK PLAN / {steps} steps · ~{total} · complexity {n}/5` with ghost "Copy full plan" right-action. Vertical timeline: 31px numbered circles (mono 12/700) joined by 1px border line; normal = white + 1.5px border + muted; critical-path = brand gradient + white + glow + trailing `CRITICAL PATH` pill (highBg/high, uppercase 9.5/700); step text 13.5/500; per-step duration mono 11 faint right-aligned.

**Audit tab** — `AUDIT METADATA / How this report was produced`: responsive grid `repeat(auto-fill,minmax(180px,1fr))` of tiles (`#FAFBFC`, borderSoft, radius 11) — dt uppercase 9.5/600 faint, dd mono 12.5 ink — covering interface, trigger, provider, model, risk-scoring mode, narrative source, schema, files analyzed, skills applied, report id. Footnote 12 muted: `Advisory only — DeployWhisper produces intelligence, not authorization. The human reviewer decides.`

## B4. States the demo implies but does not show (required, same visual system)

- **Loading:** skeletons at the exact dimensions of each card/table/header — no layout shift on data arrival.
- **Empty:** dashboard with zero analyses (dropzone becomes the hero, table/briefing show invitation copy); empty history; report 404.
- **Error:** per-card error state with retry, consistent with the alert-strip styling; global API-down banner.
- **Feedback:** "Copy briefing" / "Copy full plan" show a confirmation toast; feedback pills show selected state and persist.
- **Narrative-degraded report:** when the LLM narrative failed (the old UI showed a raw 401 JSON), show a quiet muted notice "AI narrative unavailable — deterministic findings below are unaffected" in the Overview; never render raw provider errors.

## B5. Accessibility baseline (carried from the project's existing a11y investment)

Keyboard: full tab order; switcher and tabs arrow-key navigable; Escape closes popovers; Enter/Space activates rows that act as links. Semantics: tablist/tab/tabpanel, listbox/option, `aria-expanded`, table markup for tables, buttons are `<button>`. Contrast: body/secondary text uses `text`/`muted` (AA on white); `faint` is reserved for decorative micro-text and never for essential information. Focus-visible ring everywhere. `prefers-reduced-motion` respected. Each screen passes an axe-core scan and the keyboard smoke before its PR merges (Part F).

---

# PART C — PHASED EXECUTION

### Phase 0 — Scaffold `frontend/`
Vite react-ts; deps: tailwindcss + @tailwindcss/vite, lucide-react, @tanstack/react-query, react-router-dom, @fontsource-variable/plus-jakarta-sans, @fontsource/inter, @fontsource-variable/jetbrains-mono; dev: vitest, @testing-library/react, @playwright/test, axe-core/@axe-core/playwright, openapi-typescript. Current `vite.config.ts` uses `base:'/'`; the dev proxy `/api`→`http://localhost:8080` exists only for optional local iteration. Typed client: `scripts/gen-api.sh` dumps OpenAPI (from `http://localhost:8080/api/v1/openapi.json` of the running compose stack) → `src/api/schema.d.ts`; `src/api/client.ts` unwraps the `{data, meta}` envelope. Root scripts `ui:build/ui:test/ui:typecheck`; CI frontend job. **Current done state:** `docker compose up -d --build` serves the React SPA from `http://localhost:8080/`, and verification uses the composed app rather than the Vite dev server.

### Phase 1 — SPA serving (includes the Dockerfile change)
FastAPI serves `frontend/dist` at `/` with an SPA fallback route. The retired UI has been removed, and legacy pre-cutover links redirect to root SPA routes.

**Dockerfile (explicit spec).** The existing multi-stage file (python:3.11-slim `builder` → `runtime`, venv copy, strip/prune, non-root `appuser`, healthcheck on `/api/v1/health`) stays exactly as is. Add one stage and one COPY:

```dockerfile
# new stage, before the runtime stage
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build            # outputs /frontend/dist

# in the existing runtime stage, alongside the other COPY lines
COPY --from=frontend --chown=appuser:appuser /frontend/dist ./frontend/dist
```

Rules: package manifests are copied before source so `npm ci` layer-caches; `frontend/node_modules` and `frontend/dist` go in `.dockerignore`; Node never appears in the runtime stage.

`docker-compose.yml` at the repo root needs **no changes** — it already builds this Dockerfile and exposes port 8080; the SPA appears at `http://localhost:8080/`.

**Done when:** `docker compose up -d --build` from the repo root serves the React SPA at `http://localhost:8080/`, with `/api/v1/health` green; image size before/after recorded in the PR.

### Phase 2 — Design system foundation
Implement Part B1 tokens as Tailwind theme + CSS variables and every Part B2 primitive in `src/components/ui/`, each with vitest render + snapshot tests. Build `/dev/components` gallery rendering every primitive in every state (all severities, both chip sizes, switcher open/closed/empty-search, ring at multiple scores, disabled buttons, skeletons). **Done when:** gallery screenshot from `http://localhost:8080/dev/components` matches the mockup component-for-component; this gallery becomes the permanent visual-regression target.

### Phase 3 — Dashboard
3.0 (backend-for-ui PR): `GET /api/v1/stats/summary` (totals, clean-verdict rate, open high/critical, avg time-to-verdict, 7-bucket series for sparklines), `GET /api/v1/stats/verdict-distribution?days=30`, `GET /api/v1/projects`; extend the analyses list serializer additively if it lacks severity/verdict/score/env/duration/filenames.
3.1: compose the dashboard exactly per B2 **and within the B0 information budget — the budget is an acceptance criterion**: greeting + Evidence Law chip, 4 KPIs, recent table, briefing card, upload card with working multipart POST → **navigate to the Report screen on completion** (the old expiring inline-result pattern is retired per A2), verdict donut — all via TanStack Query with B4 loading/empty/error states.
3.2: tests per Part F. **Done when:** side-by-side screenshot old vs new dashboard in the PR; seeded e2e uploads a `samples/` artifact and lands on the report URL.

### Phase 4 — Report detail + shared report
Implement B3 against `GET /api/v1/analyses/{id}`. First commit = a field-mapping table (every B3 element → real schema path) in the PR; gaps become additive serializer fields. Reuse the same screen for public `/reports/{id}` (actions hidden, password-protected shares respected, "Compare with previous" preserved). Copy-briefing uses the existing share-summary markdown.

### Phase 5 — History
TanStack Table: compact rows (timestamp, severity badge, verdict chip, score bar, tools, rescan delta as in the old UI), expandable detail, server-side `severity/recommendation/search/page/page_size` filters, bulk select + delete, pagination. No per-row repetition of full verdict sentences — summary text appears once, in the expanded detail.

### Phase 6 — Settings, Incidents, Skills
Settings rebuilt with the design system: form fields capped ~560px, provider section (active provider select, model, API base, masked key with reveal, local-only toggle), topology upload via the Phase-2 dropzone + drift cadence, reviewer-feedback stat cards, custom-skills manager. Extract any retired UI callback-only logic into `/api/v1` (A3). Incidents + Skills are list/detail ports. **This phase requires the Part D parity audit to be complete first.**

### Phase 7 — Cutover and removal
SPA moves to `/`; delete the retired UI package; remove its Python dependency and prune now-orphaned transitive deps; redirect legacy routes; point all a11y lanes at SPA routes; execute Part D removal checklist and Part E doc updates that land at cutover; record final image-size delta in the PR and CHANGELOG.

---

# PART D — PARITY AUDIT & LEGACY REMOVAL

**D1. Parity audit (do during Phase 2, before any screen ships).** The agent walks every retired UI page/route and produces `docs/design/ui-parity-audit.md`: a table of every element, control, message, and behavior in the old UI, each marked `replaced-by-design (B-ref)` / `sanctioned-change (A2-ref)` / `not-in-demo → stop-and-ask`. Examples that must appear in the audit: the dashboard's embedded full-report section and its expiry countdown → `sanctioned-change (A2: replaced by Latest Briefing card + Report navigation)`; the "Dashboard Result Display Duration" setting → `sanctioned-change (A2: retired)`; the ownership-context / CODEOWNERS follow-up rows, provider-capabilities notice, topology drift cadence, calibration snapshot block, rescan-diff line in history, select-all/delete-selected, dark-mode toggle, the `/reports/{id}` password flow. Nothing from the old UI may silently disappear: it is either in the new design, explicitly superseded, or explicitly raised. This document is the no-omissions guarantee.

**D2. Removal checklist (Phase 7; every box must be checked in the cutover PR):**
- [ ] Retired UI package deleted; no Python imports of it remain.
- [ ] Retired UI dependency removed from Python packaging; orphaned transitive deps pruned; image rebuilt.
- [ ] Old UI Playwright scripts replaced by SPA equivalents; old scripts deleted; `package.json` scripts updated.
- [ ] Old design assets replaced: `docs/assets/demo-dashboard.png`, `demo-history.png`, `demo-settings.png`, `demo-flow.gif` placeholder — re-captured from the new UI.
- [ ] README runtime badge confirms "React SPA + FastAPI".
- [ ] Repo-wide grep gates pass for the retired framework names; no dead CSS, no orphaned static files, no unused npm packages (`depcheck`).
- [ ] All retired UI-era tests removed from CI; no skipped/zombie test lanes.

---

# PART E — DOCUMENTATION UPDATES (each is a deliverable, not an afterthought)

| Document | Update | When |
|---|---|---|
| `AGENTS.md` | Add frontend conventions: Part A ground rules, stack, scripts, test requirements, design-reference paths | Phase 0 |
| `README.md` | Stack description, badges, dev commands (`ui:dev/build/test`), updated quickstart if ports/paths change, new screenshots, testing section | Phase 1 (interim note) + Phase 7 (full) |
| `_bmad-output/planning-artifacts/architecture.md` | UI layer: retired UI → static React SPA served by FastAPI; update component diagram, runtime description, single-container statement, repo-structure listing (`frontend/` replaces the retired UI package) | Phase 1 + Phase 7 |
| `_bmad-output/planning-artifacts/ux-design-specification.md` | Superseded by Part B of this plan + the mockup; rewrite to describe the new design system (tokens, components, screens) and link the design reference | Phase 2 |
| `_bmad-output/planning-artifacts/prd.md` | UI requirements section updated to the new UX, including the sanctioned flow changes in A2 | Phase 3 |
| `_bmad-output/planning-artifacts/epics.md` | Add the "UI modernization & migration" epic with these phases as stories; mark superseded retired UI stories | Phase 0 |
| `docs/ci.md` | Frontend job, e2e lane, screenshot artifacts, a11y gates | Phase 0 + Phase 3 |
| `docs/github-app.md` / action docs | Verify `/reports/{id}` links and screenshots reflect the new shared-report page | Phase 4 |
| `CHANGELOG.md` | Entry per phase; cutover entry includes image-size delta and removal summary | every phase |

Rule: a phase PR that changes behavior or structure without its row's doc update is incomplete.

---

# PART F — LOCAL RUN, VERIFICATION & TESTING STANDARD (applies to every UI task)

**F0. Local run & per-phase verification loop (mandatory).** The application runs locally via the existing `docker-compose.yml` in the repo root — the agent must not invent an alternative serving setup. The Phase 7 cutover is complete, so the React SPA is verified at the root route of the composed app.

`npm run ui:dev` may be used only as an optional coding convenience. It is never accepted for Playwright, E2E, a11y, keyboard, screenshot, or final PR verification because it bypasses the FastAPI static mount, the Dockerfile frontend stage, and the production asset build.

*Verification loop (required before every PR, and at the end of every UI task):*
  1. `docker compose up -d --build` from the repo root (rebuilds the image including the frontend stage — this also proves the Dockerfile change works, not just the dev server).
  2. Wait for health: poll `http://localhost:8080/api/v1/health` until 200 (the compose healthcheck does this; don't proceed on a cold container).
  3. Seed test data (the repo's seeded review-flow fixtures / sample artifacts under `samples/`).
  4. Run the Playwright e2e suite with `BASE_URL=http://localhost:8080`.
  5. Use root SPA routes only: `/`, `/history`, `/settings`, `/skills`, `/incidents`, `/reports/{id}`, and `/dev/components` when the component gallery is intentionally under test.
  6. Capture the Part-F4 screenshots from this composed instance — screenshots from `ui:dev` don't count, because they bypass the FastAPI static mount and the production build.
  7. `docker compose down` when finished.

  The compose default provider is Ollama, which may not be running on the agent's machine — e2e specs must therefore not depend on live LLM narrative generation: seed persisted reports, and assert the B4 "narrative-degraded" notice renders gracefully where narrative is unavailable. A failing e2e because no LLM is reachable is a test-design defect, not an excuse.

**F1. Unit/component:** vitest + React Testing Library for every primitive and screen-level logic (query hooks mocked); snapshots for primitives.
**F2. E2E (the standard):** Playwright specs in `frontend/e2e/`, one spec file per screen, executed against the **composed container at `http://localhost:8080`** per F0 (CI runs the same compose-based flow); flows covered minimum: dashboard load + KPI assertions, artifact upload → report navigation, report tab walk + finding expand + feedback click, history filter + pagination, project switch updates context, shared-report password flow. Do not use Vite dev-server URLs or legacy prefixed SPA paths.
**F3. Accessibility:** per-screen axe-core scan with zero serious/critical violations + keyboard-navigation smoke (port of the existing `test:ui-review`); the macOS screen-reader manual validation remains a separate opt-in check.
**F4. Visual evidence:** every UI PR attaches Playwright screenshots of the affected screens at 1440px and 760px, captured from the composed container per F0; the `/dev/components` gallery screenshot is the standing visual-regression reference when the component gallery is affected.
**F5. CI gates:** typecheck, vitest, build, compose-based e2e (seeded), axe — all required; regenerating the OpenAPI types must produce no type errors (drift gate).
**F6.** The retired UI test lanes keep running until each screen's SPA equivalent is green, then are deleted (D2).

---

# PART G — INITIATIVE COMPLETION CHECKLIST

- [ ] All screens shipped per Part B/C; parity audit (D1) fully resolved — zero unresolved `stop-and-ask` rows.
- [ ] Part D2 removal checklist complete; grep gates pass.
- [ ] Part E documentation table complete.
- [ ] Part F gates green in CI; a11y lanes on SPA.
- [ ] Backend diff for the whole initiative consists only of A3-sanctioned changes.
- [ ] Final container image size recorded; README screenshots are real captures of the new UI.

---

# PART H — OPERATING INSTRUCTIONS FOR THE CODEX AGENT

**Session start (every session):** read this file end-to-end, read `docs/design/deploywhisper-redesign-v3.jsx`, read `docs/design/ui-parity-audit.md` if it exists, then state which Phase/task you are executing before writing code.

**Task loop:** one task → one branch → one PR. Before opening any PR, run the full F0 verification loop: `docker compose up -d --build` from the repo root, health-check `http://localhost:8080/api/v1/health`, seed, run e2e against `BASE_URL=http://localhost:8080` using root SPA routes, and capture screenshots from the composed instance. PR description must contain: the plan reference (e.g., "Phase 3, task 3.1, B2 Recent analyses table"), the doc-table rows from Part E it updates (or "none required"), the F0 e2e output against localhost:8080, and the Part-F4 screenshots. Backend changes only under an A3 label, never mixed with frontend in one PR.

**Prohibitions:** no restyling or "improving" Part B values; no CDN imports; no demo data hard-coded; no deleting old-UI behavior without a parity-audit disposition; no skipping screenshots; no touching analysis pipeline, parsers, scoring, CLI, or Action code.

**When blocked or when the demo is ambiguous:** apply A4 — open a question in the PR with your proposed resolution and wait; do not guess on flow/behavior. Visual micro-ambiguities (e.g., an unspecified gap) are resolved by reading the mockup source, which is normative.
