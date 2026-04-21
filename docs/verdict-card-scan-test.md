# Verdict Card Scan Test

Story `2.1` uses a five-second scan check centered on three reviewer personas and the live dashboard shell at `1440x900`.

## Goal

Confirm that a reviewer can identify the verdict, top risk, confidence, and context completeness without scrolling or opening secondary panels.

## Test Personas

1. Release approver
   Task: decide whether to ship or investigate further.
   Expected first-scan answers:
   - recommendation badge
   - risk score
   - top risk one-liner

2. On-call SRE
   Task: determine whether uncertainty or degraded narration blocks fast approval.
   Expected first-scan answers:
   - confidence badge
   - context completeness badge
   - narrative/context warning when present

3. Junior reviewer
   Task: decide whether to dig deeper into findings after the first glance.
   Expected first-scan answers:
   - severity/risk signal
   - top risk summary
   - whether the report looks trustworthy enough to continue

## Result

Three role-based scan runs were executed on `2026-04-21` against the dashboard shell at `1440x900`.

| Run | Persona | Prompt | First-scan outcome | Result |
| --- | --- | --- | --- | --- |
| 1 | Release approver | "Should I ship or pause?" | Recommendation badge, risk score, and top risk were visible in the hero verdict block without scrolling. | Pass |
| 2 | On-call SRE | "Do I trust this result?" | Confidence badge, context completeness badge, and any narrative/context warning were visible in the same verdict block. | Pass |
| 3 | Junior reviewer | "Do I need to dig deeper?" | Severity/risk signal and top risk were visible before findings, giving a clear go-deeper cue in under five seconds. | Pass |

Pass criteria for Story `2.1`:

- verdict card renders in the dashboard hero surface
- the key verdict signals remain visible above the detailed review sections
- the first scan reveals recommendation, risk score, top risk, confidence, and context completeness

## Supporting Evidence

- UI regression coverage in `tests/test_ui/test_app_shell.py`
- hero-level verdict rendering through `ui/routes/dashboard.py`
- persisted detail rendering through `ui/components/upload_panel.py`
- shared verdict rendering in `ui/components/verdict_card.py`
