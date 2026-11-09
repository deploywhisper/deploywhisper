# Signed intake and CLI examples

These files are templates, not deployment fixtures or qualification results.
They contain synthetic IDs and source pins; the manifest deliberately expires in
the past. Replace them with values from your own authenticated setup before use.
No signing secret, human session, password, infrastructure state or binary plan
belongs in this directory.

Read [the trigger and CLI guide](../../../docs/infra-automation/triggers.md) first.
The JSON files cover:

- `key-manifest.example.json`: protected server configuration; account and scope
  versions come from the human-admin provisioning response.
- `signed-credentials.example.json`: sender/CLI metadata with an environment key
  reference. Its origin must exactly match the configured application origin.
- `cli-run.example.json`: signed CLI request; source origin is `cli`.
- `webhook-request.example.json`: signed webhook request; source origin is
  `webhook`. A PR sender instead uses `pull_request` and supplies `pr_ref`.
- `human-run.example.json`: existing human `RunRequest` shape.

Copy templates to operator-owned locations. The server manifest and CLI
credential file require mode 0400/0600; credentials must not be committed. Keep the
same request file and idempotency key when resolving an uncertain submission.
Each invocation signs a fresh nonce; editing or reencoding that request file is
a different byte-level operation.

`signing_recipe.py` imports the repository's signing implementation rather than
duplicating it. Running it sends no request and prints no key or signature. A
sender can import `build_headers` and send the original body once using a pinned,
verified origin and a bounded transport that refuses redirects. The guide shows
the version-matched transport recipe. This example is intended to run from this
repository's environment, not as an independently supported SDK.
