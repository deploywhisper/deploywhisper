# InfraFlow branding — 2026-11-04

The approved display name is **InfraFlow**, with Lucide **Workflow** as its
navigation icon. The common navigation component applies this to Dashboard,
History and the shared shell, immediately before Settings. Authorized feature
headings, signed-out/no-project headings, accessibility labels, account/setup
copy, API adapter errors and current operator guides use the new name.

The feature subtitle is "Infrastructure workflows with evidence and approvals."
README introduces InfraFlow as current development work rather than changing the
released v1.4.0 claims. Generic CI automation terminology and historic frozen
qualification records retain their original meaning. Stable URLs, protocol names,
capabilities, technical identifiers and stored data are compatible.

Validation:

- `npm run ui:typecheck` — passed.
- `npm run ui:test` — 314 tests and2 adapter checks passed.
- `npm run ui:build` — passed; existing nonblocking bundle-size advisory.
- `BASE_URL=http://localhost:8080 npm run test:ui-review -- project-actions.spec.ts local-account.spec.ts` —9 passed,9.9seconds against the real production Compose image and isolated tmpfs fixture.
- Read-only composed check verified actual `svg.lucide-workflow`, InfraFlow h1,
  immediate-before-Settings order and zero axe violations in the checked main
  content at1440/760. [Screenshots](screenshots/) retained.
- Independent adversarial diff review: no actionable findings.
- Repository Ruff lint/format495 and committed diff checks passed.
- No Python or versioned server contract change; prior backend qualification
  remains applicable. The focused frontend and composed checks cover the rename.

The disposable stack is removed after proof. The normal application is rebuilt
with the same persistent volume; no test project or account is placed there.
Historical screenshots remain historical evidence; current branding proof is
shown here and the refreshed project/account screenshots.
