# Story 16.15 development review

All three BMad review layers completed against the integrated backend/UI diff. Backend scope and interface readiness were separately reviewed. Current disposition: **reported implementation findings repaired and independently rechecked; positive HTTPS/browser acceptance remains open**.

| Finding | Repair and evidence |
| --- | --- |
| Local collection validation could create a permanent unknown-request marker without POST | Shared reason/body validation precedes the adapter's onSubmit callback; invalid local input remains editable and browser verifies zero POSTs |
| Late collection success/definite rejection stranded pending markers after unmount | Shared observable ticket state settles before mounted-only UI/navigation updates; known run link retained, no automatic replay |
| Late definite cancellation rejection stranded same-version guard | Ticket-specific rejection settles outside React lifetime; older responses cannot clear newer tickets; committed cancellation plus refresh failure retains protection |
| Membership refresh bypassed uncertain runner issuance | Stable principal/session/project/workspace continuity key separate from secret-display epoch/membership key; browser verifies secret clearing without duplicate issuance |
| Non-auth read errors discarded focus/drafts | Same-scope authorized cached panels remain explicitly stale and inert for mutations, including versioned read failures;403 clears content |
| Stale lease state lacked a correction | Explicit lease/deadline and evidence expiry/supersession guidance, with no process-stop or target-unlock claim |

Additional browser/implementation checks repaired initial secret-clock skew, the missing runner account-return path, and the first-request/terminal-version collection response race. The attempt-state exhaustion hypothesis was dismissed after checking the actual persisted seven-state contract. A separate HTTPS-only browser acceptance gate is a documented dependency, not a concealed runtime fix or claimed success.

Focused independent repair checks:71 tests plus six direct transpiled-handler scenarios. Final composed tests:19 new HTTP/component cases and14 uploaded compatibility cases pass. Component fault models use intercepted synthetic responses and do not substitute for real HTTPS enrollment/runner proof.
