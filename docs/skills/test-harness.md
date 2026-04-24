# Skills Test Harness

Story 4.3 adds a deterministic harness for built-in skill suites. The harness
does not try to execute skill prose. Instead, it validates the real runtime
behavior that exists today:

- the target skill is selected in isolation
- trigger-based skills load from representative raw files
- the emitted skill context contains required guidance snippets

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
