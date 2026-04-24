# Contributing Skills

Story 4.6 defines the repository workflow for contributing or updating built-in
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

- Use the skill template at `.github/PULL_REQUEST_TEMPLATE/skill.md`
- Skill PRs should include:
  - the skill id and version
  - the risk patterns introduced or changed
  - the lint and harness commands that were run
  - notes for domain reviewers or curators when needed

## Automated checks on skill PRs

Pull requests targeting `main` or `develop` already run the normal CI pipeline.
For skill changes specifically, the changed-skill automation now does both:

- manifest lint for changed `skills/*.md`
- deterministic harness execution for changed skills and their scenario suites

The changed-skill gate watches:

- `skills/*.md`
- `tests/skill-tests/<skill>/`

## Reviewer assignment

Skill contribution surfaces are covered explicitly in `.github/CODEOWNERS` so
GitHub can assign the maintainer review path for:

- `skills/`
- `tests/skill-tests/`
- `.github/PULL_REQUEST_TEMPLATE/skill.md`
- `docs/contributing/skills.md`

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

If the token is not configured, the workflow exits cleanly with a notice
instead of failing unrelated merges.

## Contribution rules

- Keep skill content focused on deterministic review guidance, not executable
  automation.
- Use synthetic examples only; never include real secrets, account ids, or
  production-only hostnames.
- Keep manifest ids aligned with the markdown filename stem.
- Update scenarios whenever you change guidance so the harness stays meaningful.
