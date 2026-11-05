# Story 16.15 scoped implementation readiness

2026-11-05. Independent review confirms earlier dependencies: Story16.7 has composed workflow/run/report proof; PR211 merged Story16.14 as `80958779e1447fe154d3646217644f1b80fdf73d`, with successful remote CI/security/CodeQL and current collection/isolation records. Its stale review tracker is not an upstream implementation blocker.

## Reviewed implementation contracts

- Backend health/admin contracts stay on `feature/16-15-runner-health-backend-for-ui`; frontend changes stay on `feature/16-15-runner-health-and-collection-ux`. Backend-for-UI publication remains separate from UI publication. Current work is local implementation, not public publication.
- Extend existing health with authoritative evaluation time and connectivity: online through60 seconds, stale through180 seconds, otherwise offline. Missing/future heartbeats are not fresh. These are descriptive thresholds; matching the60-second freshness predicate does not establish full task eligibility or isolation qualification.
- Preserve registration and credential state separately. Trusted configured profile metadata can be displayed, but `isolation_qualified=False` remains truthful: health cannot independently attest execution controls. Separate runner capabilities preserve the existing closed editor capability array.
- Typed enrollment/rotation/revoke envelopes retain existing HTTPS, production-eligible human and scoped administrator gates. Browser secret values are uncached transient component state with expiry/context/authorization clearing.
- A separate authorized run observation projection uses immutable source snapshots, attempts, validated staged uploads, finalized manifests and shared-analysis links. Unknown internal substages remain `not_observed`; `observed_at` is read time and `event_at` requires retained evidence. Final manifest/report facts take precedence over cleared staging. Server screening/upload is one observed durable milestone; collector assertions remain attributed provenance.
- Reuse existing collected run start, cancel and reconciliation operations. Zero finite wait remains the dispatcher policy. No new runner protocol, inferred progress percentage, arbitrary command, automatic resend or approval authority is introduced.

Independent review accepted this durable-state design as satisfying AC4 accuracy without new runner-v1 telemetry. Estimates: health/admin2–3 review units; observations/diagnostics2–3; runner screen2; run/timeline/cancel2–3; composed qualification2–3.

## Pending browser transport decision

Existing runner administration requires HTTPS and production-eligible sessions. The mandatory browser origin in AGENTS.md/story is `http://localhost:8080`, whose local-development sessions intentionally cannot supply that authority. Cross-origin HTTPS APIs or spoofed forwarding headers do not resolve the identity/origin contract.

A user clarification is pending for a supplemental same-origin HTTPS Compose browser lane while retaining the required HTTP lane for existing flows and denied states. No security gate will be weakened. Independent implementation, unit/API tests and HTTP-denial evidence proceed; positive enrollment/real-run browser acceptance stays unclaimed until this verification amendment is authorized and exercised.
