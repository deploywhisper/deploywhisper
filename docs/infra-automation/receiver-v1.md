# Protected reference receiver v1

The reference receiver performs one harmless synthetic marker insertion in its
local SQLite ledger. It never invokes Terraform/OpenTofu, providers, shell
commands, or a replanning step. This implements receiver durability and custody;
it does not establish live provider or hosted-runner qualification.

`infra_automation.receiver_runtime.ReferenceReceiver(root, server,
callback_secret)` accepts an authenticated `ReceiverServer` port with
`bootstrap(operation_id, binding_digest)`, `consume(message, grant_token)`,
`status(operation_id)`, `authorize_action(operation_id)`, and `callback(envelope)`.
`run(operation_id, binding_digest)` resumes the operation and returns its phase,
counted synthetic actions, original receipt, and callback delivery state.
`flush_callbacks()` retries only persisted outbox envelopes. The optional
`checkpoint(name)` constructor hook supports fault qualification, not deployment
configuration.

The example HTTPS adapter in `examples/infra-automation/receiver/run.py` uses the
receiver-only `/api/v1/infra-automation/handoffs/{id}` routes (`receipt`, `consume`,
`status`, `authorize-action`, `outcome`). TLS certificate verification is enabled;
redirects and non-HTTPS origins are rejected. Bearer credentials are sent only in
headers. Provision `DEPLOYWHISPER_SERVER_ORIGIN`, `DEPLOYWHISPER_RECEIVER_ID`,
`DEPLOYWHISPER_RECEIVER_SECRET`, and `DEPLOYWHISPER_RECEIVER_ROOT` on the protected
host. The receiver secret is the registered receiver credential, also used for
callback signing. Neither it nor the consume grant is persisted in the ledger.
The workflow dispatch accepts only operation identity and binding digest.

## Local custody

Use `ProtectedCustody(root).publish(handle, original_bytes, collected_source,
expires_at)` on the receiver host before approval, then bind the returned
`Custody` value into the decision. `collected_source` must exactly match the
version-expanded frozen receiver collected provenance. The original synthetic
bytes must begin with `deploywhisper-synthetic-v1\n`. Publication accepts at most
8 MiB, rejects an existing handle, writes owner-only immutable-mode files, fsyncs
files and directories, and publishes with a kernel-exclusive no-overwrite rename under an owner-only
lock. Linux `renameat2(RENAME_NOREPLACE)` and macOS
`renameatx_np(RENAME_EXCL)` are supported; other platforms fail closed.
Abandoned `.pending-*` directories are never eligible custody and may be removed
by the operator when no publisher is running.

`verify(binding)` opens directory-relative descriptors with no-follow checks,
requires owner UID, 0700 directories, 0400 regular files with one link, and
compares persisted source, handle, expiry, device, inode, size, and SHA-256 digest.
It rejects missing files, symlinks, hardlinks, replacement, overwrite, changed
permissions, source mismatch, and expired evidence. The verified descriptor and
byte snapshot remain held through the counted action. The action consumes that
snapshot, never a filename reopened after checking. Advisory requests and
receivers lacking local exact custody cannot run the action. A cloud-hosted
runner without that custody therefore fails closed.

Provision the receiver root under a trusted parent on a local filesystem. The
root and all receiver state belong to one dedicated OS UID and must not be
writable by other users. SQLite is single-host storage; shared network volumes
and multiple hosts are outside this contract. Owner-only files protect against
other users, not a compromised receiver UID or administrator. Do not place real
plans, credentials, or production evidence in the examples or repository.

## Recovery and outcomes

The durable sequence is intent, original authenticated consumed receipt, action
fence, synthetic effect, completion plus callback outbox. Cross-process flock
serializes the owner-only SQLite ledger, with FULL synchronous commits before
each boundary. An identical invocation returns existing state. A changed binding
digest conflicts. Canonical bootstrap message and semantic payload bytes are
persisted and checked against the frozen binding before consume.

After a crash with intent but no local receipt, the receiver asks authenticated
server status for the original receipt. It never retries consume or obtains a
replacement grant. If no original receipt exists, it remains at intent and
requires operator reconciliation. Once receipt recovery succeeds, current server
authorization and exact local custody are checked before starting the action.
The final authorization read occurs after bounded custody verification, with
verified bytes held. Local expiry is checked after that read and again immediately
before the synthetic effect. This narrows the admission window; it does not claim
a universal atomic transaction with an external authority or provider.
Revoked authority or changed custody denies execution.

A crash after the action fence is uncertain even when the local synthetic count
is zero: recovery moves to `reconcile`, emits `delivery_unknown`, and never
repeats the action. A crash after local completion retries the existing callback
without adding an action. Delivery failure does not erase the receipt or effect.
Use the server's explicit operator reconciliation surface for uncertain work;
never delete a receiver ledger to force a retry.

Callbacks persist the complete envelope before transmission: `version`,
`operation_id`, `run_id`, `binding_digest`, `source_identity_digest`, `nonce`,
`sequence`, frozen receiver `message`, and `signature`. One terminal callback has
outbox sequence 1 and frozen outcome message sequence 2; retries retain both
sequence and nonce. The signature is `sha256:` plus HMAC-SHA256 of
`deploywhisper-receiver-callback-v1\0` followed by canonical envelope JSON excluding
`signature`. Source identity hashes the canonical frozen provenance source.
Server acknowledgment permits marking the outbox delivered; it does not start
another action. The server denies duplicate nonce/sequence callbacks. If a
response is lost or a retry receives that denial, authenticated status must return
`callback_ack` with the exact persisted envelope digest, nonce, and sequence, plus
the same operation/binding and original consumed receipt. Only that exact proof
permits marking the existing callback delivered; a matching terminal state alone
is insufficient.

## Verification scope

`tests/test_infra_automation/test_receiver_runtime.py` launches real subprocesses
and kills them at intent, server consume, local receipt, action fence, effect,
and completion boundaries. Independent process races verify at most one local
synthetic count. Callback response loss tests stable signed replay. Actual
protected temporary files exercise byte tampering, replacement, links, expiry,
and source changes in `test_receiver_custody.py`.

These checks prove process-crash recovery on the test filesystem. They do not
simulate host power loss, prove remote GitHub dispatch, or constitute live TLS,
provider, or production-secret evidence.
