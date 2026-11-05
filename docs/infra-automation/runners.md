# Runner health and collection recovery

Open **InfraFlow → Runners** in a concrete project workspace. The view uses scoped server responses; switching project/workspace or losing account access clears sensitive UI state. Runner administration requires a production-eligible HTTPS human session and project administrator permission. Maintainers can inspect health. Local HTTP development sessions show an explicit unavailable state and cannot issue runner credentials.

## Reading health

Connectivity is evaluated by the server: online means a heartbeat no older than 60 seconds, stale means older than 60 but no older than 180 seconds, and offline means missing/older evidence. Future timestamps are reported as a clock problem. The displayed evaluation time and heartbeat age identify the snapshot; polling is not independent proof that a runner remains connected.

Registration, credential validity, configured profile and connectivity are separate facts. An online runner can still be revoked, expired, incompatible or busy. A configured profile is not a remote attestation: health never certifies isolation, source truth or trusted evidence. The currently qualified runtime remains the bounded offline ARM64/OpenTofu profile documented in [collection](collection.md).

Before enrollment, the operator installs the protected tool/source/collection profile described in that guide. The server exposes configured profile choices and required tags; the browser supplies no executable, shell command or provider secret.

## One-time enrollment and rotation

1. Select the configured profile, review tags and enter an administrative reason.
2. Issue enrollment once. The reveal contains the one-use token and enrollment JSON needed by the existing runner CLI. Copy deliberately into separate operator-owned mode 0600 files; do not put bearer values in shell arguments, URLs, chat or logs. Clipboard history may retain copied values.
3. Redeem with the existing private-file interface:

```sh
python -m cli.runner enroll --url https://your-deploywhisper-host \
  --enrollment-file /private/enrollment.json \
  --credential-file /private/enrollment-token \
  --output /private/runner-credential.token
```

4. Close the reveal after transferring it. Closing, expiry, context/session/authorization changes or unmounting clear the secret; it cannot be revealed again. Rotation invalidates the previous runner credential and also reveals its replacement only once.

No secret enters browser storage, a query cache, automatic clipboard copying, audit metadata or a download URL. The reveal lifetime uses fresh server time plus a monotonic browser budget; changing the browser wall clock cannot extend it.

An uncertain response is not retried. A nonsecret pending marker prevents same-session navigation from enabling a blind repeat. A late verified response can identify the completed runner without redisplaying its secret. Inspect registrations and revoke authority you can identify; a different runner's revocation does not prove an unknown enrollment was resolved. Revocation remains available to authorized administrators when collection execution is disabled. It does not confirm that previously accepted external work has stopped.

## Starting and observing collection

From a published workflow revision, review the configured source/profile requirements and enter its validated inputs. Source references supplied through inputs remain unresolved in the preview; the admitted run records the actual immutable source. Starting uses the existing run API and its current authorization/version checks.

Routing uses the existing finite wait of zero seconds. No eligible runner, wrong profile/tool/version/tags, stale heartbeat, unavailable credentials or a busy runner produces a bounded correction. There is no silent local fallback. Readiness is advisory; the actual admission transaction rechecks current authority and availability.

Run detail presents recorded milestones: source bound into the immutable run snapshot, collection attempt state, server-screened upload received/finalized, and shared analysis. Unobserved internal phases remain explicitly unobserved. The read evaluation time is separate from an event timestamp; a timestamp is shown only when retained evidence supplies it. Collector assertions are reported provenance, not independent server attestation. Finalized manifests do not disappear from the timeline when upload staging is cleaned up.

Screened logs remain optional and bounded. Sequence gaps/truncation are explicit; missing per-chunk timestamps are not invented. Polling preserves focused controls and announces meaningful stage changes rather than every chunk or timestamp. Late/outdated responses trigger bounded correction and then a manual refresh notice; consequential controls require current matching versions.

## Cancellation and unknown outcomes

Cancellation records a request first. A cancellation request, confirmation that owned processes stopped, and confirmation that external work stopped are different facts. Where retained server evidence cannot prove termination, the UI says so. Cancellation cannot undo an accepted external action.

Unknown handoffs retain their target locks and the existing reconciliation path. Do not resend blindly. Check the recorded receiver outcome or use the authorized reconciliation action with a reason. New source/evidence requires a new run and review; neither a health badge nor a successful analysis is deployment authorization.

## Verification boundary

Story 16.15 uses separate backend-for-UI and rendered-UI branches. The required HTTP composed lane checks real local-profile access/denial/disabled states at `http://localhost:8080`; component browser fault models are labelled synthetic and cannot qualify real enrollment. Positive same-origin HTTPS enrollment and authenticated isolated-runner browser acceptance remain pending the explicit verification-contract decision. See [readiness and limits](../verification/infra-automation/16-15/readiness.md). No new dependency, apply/destroy command or arbitrary runner command is introduced.
