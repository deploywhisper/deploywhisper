# Contributing Skills

Story 9.6 defines the repository workflow for contributing or updating built-in
skills. The goal is to make skill changes reviewable, deterministic, and
publishable without requiring contributors to guess the review bar.

## Before you open a PR

1. Create or update the skill markdown file under `skills/<skill>.md`
2. Add or update deterministic scenarios under `tests/skill-tests/<skill>/`
3. Validate the manifest:

```bash
deploywhisper skill lint skills/<skill>.md
```

4. Run the harness for the changed skill:

```bash
deploywhisper skill test <skill>
```

## Pull request workflow

- Target `develop` from a Git Flow `feature/*` branch.
- Select the Skill template at `.github/PULL_REQUEST_TEMPLATE/skill.md`.
- Skill PRs should include:
  - the skill id and version
  - the risk patterns introduced or changed
  - the lint and harness commands that were run
  - any additional domain reviewer and the review focus

## Automated checks on skill PRs

Pull requests targeting `main` or `develop` already run the normal CI pipeline.
For skill changes specifically, the changed-skill automation now does both:

- manifest lint for changed `skills/*.md`
- deterministic harness execution for changed skills and their scenario suites

Failures include field- or scenario-specific output in the job log. CI also
uploads `changed-skill-harness.log` on failure so contributors can inspect the
same actionable feedback after the job ends.

The changed-skill gate watches:

- `skills/*.md`
- `tests/skill-tests/<skill>/`

## Reviewer assignment

Skill contribution surfaces are covered explicitly in `.github/CODEOWNERS` so
GitHub requests the Skill maintainer review path for:

- `skills/`
- `tests/skill-tests/`
- `.github/PULL_REQUEST_TEMPLATE/skill.md`
- `docs/contributing/skills.md`

Marketplace curation rules for badges and delisting live in
`docs/skills/curation.md`.

## Merge and publish

After a skill change merges to `main`, the `Publish Skills Registry` workflow
syncs changed skills into `deploywhisper/skills-registry` when this secret is
configured:

- `DEPLOYWHISPER_SKILLS_REGISTRY_PUSH_TOKEN`

The publish job exports each changed built-in skill into the registry checkout
under `skills/<skill>/` with:

- `skill.md`
- `manifest.json`
- `tests/scenarios/`

A failed manifest lint or harness check stops the workflow before any registry
checkout, commit, or push. The publish job repeats both checks after a merge so
the registry does not depend only on pull-request branch protection. No pull
request event can publish a Skill; publication runs only from `main` or by an
authorized manual dispatch.

If the token is not configured, the workflow exits cleanly with a notice
instead of failing unrelated merges.

## Contribution rules

- Keep skill content focused on deterministic review guidance, not executable
  automation.
- Use synthetic examples only; never include real secrets, account ids, or
  production-only hostnames.
- Keep manifest ids aligned with the markdown filename stem.
- Update scenarios whenever you change guidance so the harness stays meaningful.
