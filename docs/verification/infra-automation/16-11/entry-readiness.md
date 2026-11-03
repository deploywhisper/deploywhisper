# Story 16.11 entry assessment — 2026-11-02

The implementation branch is
`feature/16-11-github-receiver-reconciliation`, based on `develop` at `0e197ce`
(Story 16.10, PR #206). Story 16.9 merged at `501d789`; the sprint tracker marks
16.0, 16.9 and 16.10 done. The story's original unresolved-dependency preparation
text predates these results. Those dependencies permit bounded implementation;
they do not establish live receiver or GitHub qualification.

## Owning contract and order

Architecture §25.9 permits fixture-tested operation refinements in the owning
story. Packet 1 adds internal GitHub acceptance/observation DTOs and fixed GET
resources to the existing pinned transport. It leaves frozen receiver-v1 bytes,
target snapshot bytes, workflow-v2 and legacy GitHub clients unchanged. Operator
credential/origin settings already supplied by 16.10 are reused.

Implement the five story packets in their declared order. Each needs its own
code, focused proof, documentation and review. Packet 1's local tests cannot
replace its explicitly required sandbox dispatch. Packets 2–5 remain unchecked
until their implementations and required proof exist. The existing human run
screen does not qualify external outcome UX.

## External configuration still required

No dedicated 16.11 qualification target or credential reference was found in
the repository's configuration. A value-free runtime check of
`config.handoff_credentials` also confirmed zero configured dispatch references
and zero receiver references. The operator must identify an owned disposable
GitHub repository, dispatchable harmless workflow, protected reviewed branch/tag
and SHA, numeric repository/workflow identities, and a dedicated dispatch
credential reference in the existing protected operator environment. Secret
values must not be supplied in chat, fixtures, documentation or git.

The selected workflow must accept the two nonsecret inputs `operation_id` and
`binding_digest`. Neither a one-use grant nor a receiver credential belongs in
GitHub dispatch inputs or event history. The authenticated receiver rendezvous
and durable admission are later packet work; Packet 1 installs no production
delivery port and enables no apply operation.

An asynchronous configuration question has been sent. General `gh` access and
legacy GitHub App credentials do not identify the required qualification target.
Record live dispatch as **not run** until the dedicated configuration exists.
Keep the story in progress; do not claim all acceptance criteria or move it to
review on local adapter tests alone.

## Remaining qualification boundaries

Receiver ledger crash recovery, actual protected synthetic saved bytes,
authenticated callbacks/replay fencing, proof-specific parent reconciliation
and composed run UI/browser evidence belong to Packets 2–5. Mutable material
witness and real collected-plan integration must also retain the earlier
qualified profile boundaries. No synthetic test result is universal production
support or an exactly-once deployment guarantee.
