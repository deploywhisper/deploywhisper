# Story 16.17 entry review

Independent native review on 2026-11-05 cleared bounded implementation using the
actual 16.0, 16.4 and 16.11 evidence and the implemented scoped history portion of
16.15. Current collection/isolation integrity passed nine tests and 73 subtests.
The separate positive HTTPS enrollment and real-runner browser gates in 16.15
remain open; this story does not claim to close them.

## Reviewed interfaces

- Authenticate exact bounded bytes before JSON construction on fixed signed POST
  routes. Bind protocol domain, key ID, method, raw path, timestamp, nonce and
  body SHA-256 with length prefixes; use constant-time HMAC verification.
- Separate durable nonce reservation from operation idempotency. Consume a valid
  authenticated nonce before parsing, preserve it after subsequent rejection,
  retain it through its signing window, and persist a monotonic server clock.
  Fresh nonces may recover the same accepted operation; changed operation bytes
  cannot reuse its idempotency identity.
- Load a protected SHA-pinned manifest containing environment key references,
  concrete scope, source/revision allowlists and expected account/membership/
  restore versions. Keys and profile drift remain live authorization inputs.
- Provision service/agent identities through verified human administration.
  Their password material is inert, their global-admin flag is false, and their
  effective capabilities remain read/request. No account is created at startup.
- Add a closed machine authority subtype while retaining byte-identical human
  authority serialization. Recheck the whole machine authority at admission,
  claim and later effects; credential expiry caps the run window.
- Keep CLI as a bounded HTTP adapter with protected credential files, pinned
  origin and no credential-bearing redirects. Human sessions retain Origin/CSRF;
  machine calls never gain publication or decision privileges.
- Capture origin through the authenticated server entrypoint and actual principal
  type. The CLI channel is not an attestation of a particular executable.
  Later human review does not rewrite the machine requester's origin.
- Render origin in existing scoped history/detail surfaces using the real APIs.
  Preserve the approved UI components and composed-app browser evidence rules.

Estimated review units: signing/replay 2–3; authority/admission/persistence 4–5;
CLI parity 2–3; origins/types/docs/browser proof 2–3. These estimates are not
calendar promises or production qualification.

## Initial proof

The pure protocol packet passed 12 tests and 63 subtests, including a fixed wire
vector, exact-byte mutations, exclusive 300-second skew, strict bounds and
nonreflective errors. Independent review reran these tests and checked skew and
reference boundaries. Durable authority, integration and browser acceptance must
still be recorded by the implementation before completion.
