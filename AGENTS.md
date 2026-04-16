# AGENTS.md

## Repository guidance
- Prefer BMAD skills from `.agents/skills` for structured planning, architecture, implementation, and review.
- Start by using `bmad-help` to inspect project state and recommend the next step.
- Important project context and conventions are located in `_bmad-output/project-context.md` when that file exists.

## Project expectations
- This repository is being developed with a DevOps and cloud platform mindset.
- Favor infrastructure as code, CI/CD automation, observability, security, rollback safety, and cost awareness.
- Prefer small, reviewable changes with validation after each change.
- For larger changes, prefer formal BMAD planning over ad-hoc implementation.

## Validation
- After changing code or config, run the repo’s relevant lint, test, and build commands before closing the task.
