# Receiver reconciliation after coordinated restore

Story 16.18, packets 18.2/18.3; proposed implementation contract, 2026-11-10.
This document requests independent technical review before implementation. It is
not delivered proof, a live receiver qualification, or a release-readiness claim.

## Problem and authority

Coordinated restore invalidates every account authentication generation, including
the receiver's service account. Existing `HandoffService._receiver` requires its
current generation to equal the generation captured in the immutable target
snapshot. Consequently an old consumed operation cannot authenticate even a
status request or a terminal receipt after restore. Changing the environment
secret does not repair that generation mismatch.

AC3/AC4 authorize recovering retained external work while preventing new action
from restored authority. Add a narrowly scoped reconciliation credential; retain
the original snapshot, decision, payload, grant consumption and operation bytes.
Do not exempt receiver accounts from restore invalidation or relax ordinary
receiver authentication. Unconsumed grants remain invalidated.

The issuer is the existing verified global human configuration owner, also
authorized as the operation's project/workspace automation administrator. Reuse
`infra_automation_targets._admin(..., mutation=True)`, including
`guard_global_configuration`, rather than trusting a host username, actor header,
cached role, human account flag alone, or an implicit legacy administrator. The
fresh human session must survive all existing Origin/profile/CSRF/current-account
and membership checks. The global administrator already controls protected
receiver credential references; issuance remains inside that existing trust
boundary. Application audit is not tamper-proof against the host/database owner.

## Operator interface

Add only this local command to `cli.automation_operations`:

```text
./.venv/bin/python -m cli.automation_operations --control /private/deploywhisper/control receiver-recovery-issue --operation <operation-id> --token-file <fresh-human-session-file> --csrf-file <csrf-file> --reason-file <screened-reason-file> --output <new-private-receiver-token-file>
```

Read inputs through `cli.identity._private_input`; publish the issued token using
`cli.identity._issue_to_file` and its exclusive, no-follow, owner-only 0600 file
handling. Reserve the output inode before issuing. Return an existing
`IssuedCredential`-compatible value containing `SecretStr` and expiry only to
that private writer. Never print the bearer, put it in argv/environment/audit or
accept it through a browser settings form. CLI stdout contains bounded nonsecret
status only. Existing outputs are never overwritten.

If issuance commits but file publication or its acknowledgement fails, the
credential remains valid but unavailable. An explicit new issue command rotates
the verifier and invalidates that lost credential. Do not replay issuance
automatically or attempt to recover its plaintext from storage.

No new HTTP issuer, receiver URL, protocol field, generic machine issuer,
wire audience value, execution mode or dependency is introduced. Logical
authority remains explicitly reconciliation-only. An operator
transfers the private file to the existing operator-controlled receiver through
its protected mechanism. Existing HTTPS receiver routes and `ReceiverCredential`
carry it as an opaque bearer in the same way they carry existing receiver
credentials. This transfer and actual receiver configuration remain an explicit
live qualification obligation.

## Issuance transaction

The new service operation accepts an operation identifier and screened reason.
It is callable only with the fresh human credentials above. Inside the same
reserved `authorized_session` transaction:

1. Require the configured `RecoveryStore`; reject absence, mismatched CLI control
   path, uninitialized/partial state, or a different database. Hold the existing
   participation lock. `store.assert_ready(effects=False, session=session)` must
   agree with the database on installation, generation and phase; issuance
   specifically requires `reconciliation_required`.
2. Load the exact retained operation through `HandoffService._load`, preserving
   all existing canonical payload/binding/snapshot/receipt checks. Require a
   consumed grant and its valid nonempty original consumption receipt. Deny an
   unconsumed, invalidated or missing grant, broken operation/lock, mismatched
   scope/receiver, or unavailable immutable material. Derive a closed mode on
   the server; it is never caller input. `status_terminal` requires existing
   consumed/accepted/running/delivery-unknown state and the canonical lock still
   held by this operation's run. `status_only` permits an already verified
   succeeded/failed operation only when an exact retained signed terminal fact
   matches state, binding, source and consumed receipt; its lock must be held or
   resolved for that same captured run. A terminal row alone is insufficient.
3. Require the original receiver principal still exists, is enabled, is a
   nonadmin service account, and matches the original operation's receiver
   identity. Capture its *current* authentication generation. Do not depend on
   the old requester/reviewer session or enable the disabled automation feature.
4. Read time after acquiring the reserved transaction. Check the recovery-state,
   operation, grant-consumption, parent-run and existing reconciliation-credential
   clock floors. Cap the new credential's TTL at the current project's
   `credential_ttl_seconds` (existing 60–3600-second bounds); do not extend the
   original decision/grant/evidence/action deadlines. Reconciliation may occur
   after those old deadlines. Preserve the precise observed issuance clock floor
   and use whole-second, exclusive expiry; backward clocks deny rather than
   creating a longer window.
5. Generate at least 256 random bits using `secrets`, with fixed prefix
   `receiver-reconcile-v1-`. Store only a domain-separated SHA-256 verifier over
   the complete bearer. The token is never deterministic/reconstructable.
6. Insert or CAS-rotate the operation's current sidecar. First issuance uses an
   absent row; rotation advances its strictly bounded version and supersedes
   the previous verifier atomically. Serialization plus CAS prevents concurrent
   issuances from leaving two current tokens. Explicit operator rotation is a
   new issue, not an idempotent replay of the old plaintext.
   Bound successful issues to 100 per operation per global restore generation,
   with the counter retained in the current sidecar and advanced atomically.
   Quota/counter failure must not replace the prior verifier.
7. Charge the existing run/project/global storage accounting for the retained
   sidecar, duplicated canonical scalar representations, append-only audit and
   bounded bookkeeping. Use conservative positive charging on rotation rather
   than adding a general negative quota adjustment. Refuse quota/disk exhaustion
   atomically, retaining the previous verifier and all unknown locks. Audit the
   human issuer/scope/target/reason/time and before/after nonsecret binding
   digests; never persist a bearer or raw receipt copy unnecessarily.
8. Recheck human authority, installation/generation/phase, current receiver
   generation, operation/consumed receipt/lock identity, clock and expiry before
   commit/return. No external callback, raw file write or network operation runs
   inside this transaction. Publish the bearer only after successful commit.

## Retained sidecar and migration

Allocate migration `042` after the inspected `041_add_operator_recovery` head.
Keep its ORM definition in a separate module and integrate metadata loading and
effective schema/startup guard checks through the existing migration discipline.
No immutable operation, target snapshot, grant receipt or frozen wire changes.

Use one current sidecar row per operation with restrictive foreign keys and
explicit bounds. Required fields are:

- Operation ID, original receiver binding digest and original consumed-receipt
  digest; project/workspace and original receiver principal/receiver ID.
- Installation ID and current global restore generation.
- Current receiver authentication version, current verifier hash, sidecar
  version, issued/expiry/last-observed timestamps and human issuer identity.
- Issuer authentication and scoped membership versions, plus the bounded issue
  count for the current global restore generation.
- A nonsecret binding digest covering all authorization-bearing fields.
- The server-derived closed mode, `status_terminal` or `status_only`. Rotation
  may narrow the former to the latter after verified terminal completion; it
  cannot upgrade `status_only` to `status_terminal`.

Bound identifiers/digests with existing contracts, versions/generations to safe
integers, verifier length to 64 hex characters, timestamps and TTL as above.
Keep application-created issuer audit append-only through the existing audit
guards. The current sidecar may rotate its verifier/current generation/issuer/
time only with a version advance and monotonic floor. Its original operation,
scope, receiver and original binding/consumption identity never transfer. Permit
monotonic observation-floor updates without changing authorization-bearing
fields; deny replacement/deletion and arbitrary immutable-field updates.

Normal schema startup must reject partial/missing/weakened 042 guards and missing
columns/constraints; it must not silently repair them using `create_all`.
Downgrade must refuse retained sidecar history rather than silently erase a
recovery fence. Another restore invalidates imported sidecars automatically
because their generation differs from the outside ledger and current database.

## Receiver use and strict privilege ceiling

Extend `_receiver` with an explicit internal `reconciliation_only=False` argument.
The default preserves its current authentication byte-for-byte. A bearer with
the recovery prefix is rejected by the default branch before any ordinary
secret comparison. Only these owners opt in:

- `receiver_status`: return the exact retained status/consumed receipt for its
  bound operation. Preserve existing binding checks for typed status messages.
- `callback`: recovery credentials admit only a signed `outcome` with terminal
  `succeeded`/`failed` state and the existing required sequences/nonces. Deny
  accepted/running/cancel/status progress callbacks with this credential.
  `status_only` always denies callback, even for otherwise matching bytes.
- A private terminal helper called by `callback` only after the signed envelope
  has been verified and durably retained in that same reserved transaction.
  Preserve the original binding/message, consumed grant, held lock, broken flag,
  monotonic time and sibling/parent reconciliation checks. It records proof of
  the *old* operation, never a replacement action.

The existing public `resolve_terminal(message, credential)` has no signed
callback envelope or nonce admission. It must continue ordinary authentication
and explicitly reject recovery bearers. Share terminal transition mechanics in
the private helper; do not expose a public `recovery_verified` boolean or grant
recovery authority by calling the public unsigned-message method.

Recovery validation compares the complete token verifier in constant time and
rechecks exact operation, scope, original receipt/binding digests, installation,
global generation, current enabled receiver account/generation, clock floors,
expiry and the sidecar's current version in the same reserved transaction. Deny
missing/configuration-unavailable material. Recheck immediately before terminal
effects and response construction after any material work. A credential cannot
authorize another operation, even for the same receiver/target/project.

Also deny if the recorded human issuer is disabled, revoked, no longer a global
human administrator, or has different authentication/scoped membership versions.
Re-evaluate their current `automation.admin` on the exact operation scope and
`settings.manage` on all protected projects from current account/membership
rows; no synthetic human session or cached principal is created. These are
additional deny-only checks, not authorization from public comparison fields.
Use existing SQLAlchemy repositories and a closed internal authentication result
that distinguishes ordinary receiver authority from recovery status/terminal
authority. The unchanged wire audience alone cannot widen the recovery token's
closed operation set.

The terminal callback HMAC continues to cover the existing exact callback bytes;
the issued private recovery token supplies the signing/authentication secret for
this narrowly bound channel. Original source/binding/receipt validation remains
mandatory. This is a delegation by the existing protected credential owner, not
independent attestation of an infrastructure action by the application.
Recheck the token's live stamp/time after bounded callback body validation/HMAC
and before the retained fact, operation, lock or parent-run mutation. The outcome
audit explicitly identifies recovery authentication and its human issuer/current
generation rather than implying the pre-restore receiver credential survived.

`bootstrap`, `consume` and `authorize_action` never opt in and must reject every
recovery bearer. They must not release original grant plaintext, consume a new
grant, issue a fresh action admission, refresh an approval, recollect, replan,
resend delivery or create a replacement operation. Ordinary credentials retain
all previous checks. Original pre-restore credentials remain rejected.

Issuance requires recovery phase; validation may retain status access after
successful recovery completion in the same generation until its original short
expiry. Terminal reconciliation still observes existing terminal-state/replay
guards. Token expiry/rotation, another restore, receiver generation change or
account disable deny new use. Human reads and the existing reasoned uncertainty
break remain separate recovery choices, never substitute proof of success.

## Existing reference receiver recovery

Add an explicit terminal-only recovery method to `ReferenceReceiver`; do not
route recovery through `run()` or a blanket `flush_callbacks()`. The ordinary
methods can revisit action admission or send nonterminal progress, while the
new credential intentionally forbids both.

The recovery method requires an existing protected local ledger row in exact
`complete` phase, the original canonical consume message/payload/binding, the
exact retained server consumption receipt and a stored terminal callback for
that same operation. Retain the local action-mode and original completed marker
or saved-plan receipt consistency checks. An absent row, `intent`, `received`,
`action_started` or `reconcile` phase is not terminal proof. Those phases remain
uncertain and require observation or an explicit uncertainty break; the method
cannot relabel them success/failure.

First obtain authenticated status using the recovery bearer and compare the
operation/binding/consumption receipt exactly. If `callback_ack` matches the
exact original terminal callback's sequence, nonce and full-envelope digest,
or a previously retained recovery candidate, record delivery without another
callback. If server state is terminal and that exact acknowledgement is absent,
stay unresolved: `status_only` cannot re-sign/send or invent a replacement fact.
For an eligible nonterminal server operation only, sign the original terminal
envelope with the new private recovery secret, preserving the original exact
message, source, sequence and nonce. Before sending, durably retain that signed
envelope and its digest in a protected local recovery outbox; retain the
original callback unchanged. The outbox stores no bearer. Bound outbox candidates
to the same 100-rotation limit so a lost reply followed by credential rotation
can still recognize a previously accepted exact envelope digest.

After send failure or an ambiguous response, status can acknowledge delivery only
when its retained `callback_ack` exactly matches the original envelope or one of
the durably retained recovery outbox candidates and the consumed receipt still
matches. A conflicting nonce/sequence/binding/receipt stays unresolved. Never
create a new nonce/sequence to bypass an already accepted callback, recreate an
action fence, execute a tool, inspect current custody as a new authorization,
bootstrap, consume or request action admission. Repeated recovery and receiver
process restart can only deliver/recognize the existing completed outcome; the
action count must remain unchanged.

## Required deterministic proof before claiming this contract

Use the real file-backed SQLite/service fixture and an actual coordinated
backup/restore, with explicitly synthetic receiver/custody material:

1. Consume an operation, backup/restore, prove every old session/receiver token
   and old grant/action path denies while the original receipt/lock survives.
2. Recover a fresh human session, issue the protected reconciliation token,
   retrieve the exact old receipt, submit a signed terminal outcome for that
   same operation, and reconcile the existing lock/parent subject to siblings.
3. Recovery token denies bootstrap, consume, action authorization, the public
   unsigned `resolve_terminal` service operation, another
   operation/scope/receiver, nonterminal callbacks, changed original binding/
   receipt/source, malformed secret/audience and invalid signature.
4. Nonadmin, wrong workspace, stale session/CSRF, absent or mismatched control,
   ordinary ready phase, unconsumed/broken or unverified-terminal operation, quota/disk failure,
   clock regression and exact expiry deny without mutating state/locks/audits.
5. Concurrent rotation yields one current verifier; old/lost plaintext is never
   recoverable. Fault after sidecar/audit/storage mutation rolls back all three.
   Another restore/current receiver-generation change invalidates the token.
6. CLI output is private/exclusive/no-follow and secret-free on stdout/errors;
   failed file publication is recoverable only through explicit rotation.
7. Existing normal receiver tests and exact API/CLI/infra/automation shards pass;
   runtime source changes require renewed qualification integrity/drift checks.
8. The actual protected `ReferenceReceiver` ledger survives a process restart and
   delivers or recognizes a stored completed outcome using only recovery
   status/callback operations. Lost original/recovery acknowledgement and
   subsequent token rotation never increment the action count; unfinished or
   uncertain local phases never become fabricated terminal proof.
9. Already accepted terminal callbacks with lost acknowledgements remain
   recoverable after restore and credential rotation via `status_only` exact
   acknowledgement matching. Conflicting/missing acknowledgements deny without
   a callback or mode upgrade.

No fixture proves real protected token transfer, a production receiver's durable
action fence, infrastructure outcome, self-service pilot or release support.
Those live profile obligations remain open until their exact evidence exists.

Issuance and audit-reason screening must explicitly reject the
`receiver-reconcile-v1-` prefix and reflected credential material, following the
existing runner-credential reason boundary. Generic pattern redaction alone
does not establish coverage for the newly introduced credential family.
