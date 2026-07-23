# Skills Test Harness

Story 9.3 completes the deterministic harness for built-in Skill suites. The harness
does not try to execute skill prose. Instead, it validates the real runtime
behavior that exists today:

- the target skill is selected in isolation
- trigger-based skills load from representative raw files
- the emitted skill context contains required guidance snippets
- unrelated evidence does not load the Skill or leak its guidance

Every suite reports four coverage categories:

- `expected_triggers`: a positive scenario selects the Skill through its tool,
  filename trigger, or declared content marker
- `expected_outputs`: a positive scenario checks one or more required guidance
  substrings
- `evidence_assumptions`: a positive scenario provides an explicit assessment
  tool, contributor summary, and deterministic raw-file fixture
- `safety_constraints`: a negative scenario proves unrelated evidence does not
  select the Skill and checks that Skill guidance is absent

The `coverage.complete` field is true only when all four categories are present.
The `trust_requirement` result evaluates the manifest `trust_level`.
`verified` and `core` Skills require complete coverage and every scenario to
pass. Missing or incomplete suites fail that trust requirement and cause the
CLI/CI harness command to exit nonzero. Experimental and deprecated Skills
still report coverage and scenario failures, but incomplete coverage alone does
not block their trust classification.

Harness summary states:

- `passing`: every scenario passed
- `failing`: one or more scenarios failed, including malformed scenario JSON
- `missing`: the suite path resolved but no scenario files were present; CLI and CI treat this as non-passing

## Scenario layout

Each built-in skill keeps scenarios under the manifest path declared by
`test_suite_path`, currently `tests/skill-tests/<skill>/`.

Example:

```text
tests/skill-tests/terraform/
├── README.md
└── basic-selection.json
```

Scenario file shape:

```json
{
  "name": "terraform-basic-selection",
  "description": "Loads the Terraform skill for a Terraform contributor.",
  "assessment_tool": "terraform",
  "contributor_summary": "Terraform changes update networking and storage resources.",
  "raw_files": {
    "main.tf": "resource \"aws_security_group\" \"db\" {}"
  },
  "expect_selected": true,
  "expected_substrings": [
    "Security group or firewall rule with `0.0.0.0/0`"
  ],
  "expected_absent_substrings": []
}
```

Positive scenarios declare evidence through `assessment_tool`,
`contributor_summary`, and `raw_files`; `expected_substrings` verifies emitted
guidance. Add a negative scenario with `expect_selected: false` and at least one
`expected_absent_substrings` entry to lock the suite's safety boundary.

## CLI usage

Run all built-in skill suites:

```bash
deploywhisper skill test
```

Run selected skills only:

```bash
deploywhisper skill test terraform docker
```

Emit machine-readable JSON for automation:

```bash
deploywhisper skill test terraform --json
```

## CI integration

- Local CI now runs the full harness through `bash scripts/ci-local.sh`
- Pull requests run changed skill suites through `scripts/test-changed-skills.sh`
- Changed-skill detection watches both `skills/*.md` and `tests/skill-tests/<skill>/`

## Public results

The skills API exposes harness status through:

- `GET /api/v1/skills`
- `GET /api/v1/skills/{id}`
- `GET /api/v1/skills/{id}/test-results`

The test-results response includes scenario results, coverage by required
category, and the trust-level requirement decision with actionable failures.
