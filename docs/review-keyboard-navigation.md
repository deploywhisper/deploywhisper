# Review Keyboard Navigation

DeployWhisper report review surfaces now expose a consistent keyboard path across the dashboard result view and the history report dialog.

## Keyboard map

- `Tab`: follows the natural DOM order through the review landmarks and their controls. In the standard report flow this means verdict card, findings table, expanded evidence inspector content, context completeness, blast radius, then rollback plan.
- `ArrowUp` / `ArrowDown`: moves focus between finding rows inside the findings table.
- `Home` / `End`: jumps to the first or last finding row.
- `Enter` or `Space`: expands or collapses the focused finding row's evidence inspector.
- `Escape`: closes the active modal dialog, including the history report dialog and confirmation dialogs.

## Manual screen-reader checklist

Run these checks on a workstation with the target screen reader enabled:

1. Open a report with findings, context completeness, blast radius, and rollback data.
2. Confirm the report landmarks are announced in the expected order while tabbing.
3. Move through findings with arrow keys and confirm the focused row title is announced.
4. Expand a finding with `Enter` and `Space`, then confirm the evidence inspector label and evidence source text are announced.
5. Open the history report dialog and confirm `Escape` closes it without trapping focus.

## Notes

- VoiceOver: validate on macOS Safari or Chrome with Quick Nav disabled during the tab-order pass.
- NVDA: validate on Windows with browse mode toggled off for the arrow-key row-navigation pass.
- The automated test suite covers the rendered landmarks, row semantics, section order, and modal escape hooks; screen-reader speech output still requires manual verification on the target platform.
