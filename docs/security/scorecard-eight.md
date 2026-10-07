# Verified security posture target: Scorecard 8

The 2026-10-07 baseline is 6.7/10 on `046b020`. The user requests a genuinely published score of at least 8. The implementation spec is `_bmad-output/implementation-artifacts/spec-gh-131-scorecard-eight.md`.

## Controls being implemented

- Complete SHA256 runtime/dev locks and enforced installs across Docker and delivery workflows, with reproducible input manifests and compatible dependency resolution.
- Official container digests and automated Docker update proposals.
- A real coverage-guided ClusterFuzzLite target for production redaction/parsing, synthetic seed corpus, deterministic invariant tests, packaged execution and hosted CI evidence.
- Enabled GitHub private vulnerability reporting and a linked policy describing supported releases, acknowledgement/assessment targets and coordinated disclosure.
- Protected `develop` and `main` against force-push and deletion through active ruleset `24634960`, with no bypass actors. Ordinary direct pushes remain possible; this is basic history protection rather than a claim of required human review or required pre-merge CI.

## Administrative evidence and recovery

Before mutation, private reporting was disabled and both existing branch rulesets were disabled. Existing rulesets included obsolete check names (GitGuardian and Test — ui-llm), so they were not activated blindly. New history-only rules protect both long-lived branches; GitHub reports `protected: true` for each. The disabled rulesets remain unchanged. Prior state and exact created-rule response are saved under `/private/tmp/score8-*-before.json` and `/private/tmp/score8-history-protection-created.json` for this session. Maintainers can remove ruleset 24634960 to revert these two new safeguards; disabling private reporting reverts that separate setting.

Required reviews and merge policy are pending the user's independent-reviewer decision. No collaborator role is changed, no approval is invented, and no existing release is modified or retroactively called signed. Signing/provenance need concrete versioned release artifacts; best-practices badge registration and contributor diversity require genuine external participation.

## Verification standard

Completion requires actual hash-enforced installs and rejection of bad hashes, lint/actionlint, appropriate full local and composed-app tests, nonzero packaged fuzz coverage, hosted workflow success, layered review, and a Scorecard API/badge report of at least 8 tied to the published commit. A configured workflow alone is not proof of executed fuzzing. The risk-weighted planning estimate of about 8.0 is not a claimed result.

Results and remaining limitations will be appended after validation. Existing issue [#131](https://github.com/deploywhisper/deploywhisper/issues/131) retains ownership of controls that remain incomplete.

## Local verification completed

Hash-enforced runtime/dev installs passed on clean Linux Python3.10/3.11, and a real pip tampered-hash probe was rejected. Locks regenerate byte-identically. Runtime/dev/fuzz audits are clean. The packaged fuzzer passed in a separate pinned, network-disabled runner:15,116 executions in61seconds, coverage757→1,038, features1,714→3,535; official runner build checks pass.

All three independent review layers completed. One documentation/update-flow gap was fixed; review recheck found no remaining introduced defect. A pre-existing CLI fixture incorrectly assumed a local provider was unavailable; it now injects an unavailable synthetic completion client without weakening degraded assertions. Initial live-provider failure is retained in logs, final deterministic shard passed.

Final local CI:1,805 tests across nine directories, all suites passed (one optional skip). Smoke521tests with one optional skip; affected shard458passed+222subtests; frontend56tests; all17rebuilt Compose browser tests passed with no skips. Original app restored healthy and only disposable test volume removed. Ruff/actionlint passed. Existing sample-data Bandit B104 remains unchanged. Hosted execution and published >=8 result remain pending.
