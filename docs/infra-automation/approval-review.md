# Approval review packet for the React UI

This separately delivered backend-for-UI contract supports Story16.9. It adds a
reviewer-aware read and high/critical confirmation to the durable decisions from
Story16.8. Production target/custody material remains unavailable by default;
synthetic scoped ports qualify this contract without enabling remote actions.

## Read the exact packet

`GET /api/v1/infra-automation/approvals/{id}?project_id=1&workspace_id=1`
requires a verified human session, live review capability and report access in the
selected scope. Reads do not require CSRF or write approval audit events. Scope
mismatch/inaccessibility uses the existing generic denial. The response uses the
standard `data`/`meta` envelope, `Cache-Control: no-store`, and a closed integer
version1 contract. Unknown or coerced protocol literals fail validation.

The typed packet separates these facts:

- `receipt`: exact retained generation/version, binding and historical outcome.
- `report`: bounded confidence/context, blast radius, rollback, recommendation,
  severity and report identity derived from verified stored export bytes, plus
  the permanent report URL. Summary screening never rewrites those bytes.
- `action`: an equivalent typed payload summary of the bound authorization kind,
  target/environment, receiver/pipeline identity, source identity and unit/payload
  digests. Uploaded repository/commit remain explicitly unavailable.
- `context`: current reviewer eligibility, server-selected decision model,
  required confirmation phrases, evaluation time, individual deadlines and their
  effective minimum including the run deadline. This is descriptive data, never
  an authorization credential. Unknown/unavailable proof disables submission.
- `attribution`: the actual retained decision event's actor/type/role/scope/reason,
  time and state digests. Current membership never substitutes for history.
- `can_export_audit`: a descriptive projection of the existing admin-only scoped
  export permission; the export endpoint independently rechecks it.

Feature-off, missing material or an unavailable decision clock preserve authorized
historical packet/receipt reads while submission stays blocked. An unavailable
clock has `evaluated_at: null` and explicit guidance; no current time is invented.
Corrupt retained data remains unavailable. Bounded/screened summary omissions are
marked rather than silently presented as complete evidence. Raw artifacts, plan
bytes, grants, credentials and secret-bearing paths are excluded.

## Submit deliberately and recover receipts

Existing POST `/approvals/{id}/decision` still requires explicit outcome, nonblank
screened reason, expected version, binding digest, live human authority and CSRF.
It additionally accepts a bounded optional `confirmation` string. High/critical
severity comes from the retained report and requires an exact server-selected
phrase:

| Outcome/model | Required phrase |
| --- | --- |
| Shared approval | `APPROVE <canonical_target>` |
| Single-operator approval | `ACKNOWLEDGE <canonical_target>` |
| Rejection | `REJECT <canonical_target>` |

Missing/wrong confirmation fails before a decision or audit transition commits.
Lower severities retain their existing behavior. Canonical no-go stays advisory
and is evaluated separately by workflow policy; insufficient mandatory context
and hard gate failures cannot be overridden by a reason or confirmation. Shared
requesters remain excluded; no client field selects acknowledgement mode.

Every mutation rechecks the full current packet, membership, policy, clock floors
and earliest deadlines. After a conflict, connection loss or ambiguous response,
read the exact approval ID before allowing another submission. A recorded
version/generation is a durable receipt, not a request to replay the mutation.
Existing CAS preserves one decision; no second generation is minted by recovery.
The frontend must clear transient forms/eligibility on identity or scope changes.

## Audit identity and trust boundary

Decision transitions use a versioned screened decision-state projection for their
before/after digests, independent of report bytes and binding identity. Creation
can have no prior state; request replay does not create another generation.
Legacy events are retained as recorded and identified without inventing missing
state digests or historical roles. Existing application append-only SQL guards
and admin-only scoped JSON export are reused; no audit subsystem or permission
expansion is added. DB/host administrators remain trusted.

## Review and decide in the browser

Open **Infra Automation → Approvals** in the selected project. The inbox at
`/infra-automation/approvals` filters the records already loaded; recorded
pending status does not establish current eligibility. Load older pages when
needed. Each review link identifies the exact run and approval in that scope.

The review screen shows the retained action and report context before decision
controls: authorization kind, registered target/payload, source, policy,
confidence, blast radius, rollback, full fingerprints and absolute UTC deadlines.
Retained collection time, source verification and redaction version are visible
alongside evidence/approval expiry and readable remaining validity. Remaining
time uses monotonic elapsed time from the read start, including response transit;
it cannot renew a server deadline or grant authority. Source verification describes
the server evaluation shown on the packet, not a new credential.
The permanent report link uses the protected report read. Screened or unavailable
details are explicitly labeled. An eligible advisory no-go still requires a
deliberate decision and reason; a hard eligibility failure disables both actions.

Choose approve, reject or the server-selected acknowledgement action. The modal
keeps keyboard focus inside, requires a reason and, for high/critical severity,
the exact displayed confirmation phrase. Escape cancels confirmation and returns
focus. Expiry preserves the local reason while disabling submission. Switching
project or identity clears the local form. Single-operator acknowledgement
explicitly makes no independent-review claim.

The browser rechecks session and current packet before posting once. It never
automatically retries a decision. After a lost response it disables another
submission until an exact-ID read recovers current state. An advancing terminal
receipt resolves uncertainty. An unchanged pending
read cannot prove the earlier request stopped, so another submission stays
blocked until a recorded outcome or operator recovery. A definite server rejection
permits a corrected manual attempt after refresh; invalid success bodies, network
loss and unknown server outcomes do not. Concurrent decisions
close stale confirmation and focus the existing receipt. A role revocation
removes protected review content; unavailable reads cannot leave usable stale
controls. The server still independently authorizes every request.

Receipts show retained attribution and state digests. Authorized administrators
can download bounded, paginated scoped audit JSON; its completeness flag reports
whether all pages were read. Other accounts do not receive an export control.
An export with a reported gap or unfinished final page is explicitly incomplete;
consumed continuation pages do not make a fully read snapshot incomplete.
The export contains screened application audit data and shares the DB/host-admin
trust limit described above.

Browser evidence and disposable-fixture instructions are recorded in
[Story16.9 verification](../verification/infra-automation/16-9/results.md).
