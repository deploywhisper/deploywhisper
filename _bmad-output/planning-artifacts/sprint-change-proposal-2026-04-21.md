# Sprint Change Proposal: Repository and External Slug Rename

**Date:** 2026-04-21
**Project:** DeployWhisper
**Triggered by:** User-requested product/repository identity correction during active delivery
**Mode Assumed:** Batch
**Recommended Scope:** Moderate
**Selected Approach:** Hybrid of Direct Adjustment + compatibility-preserving rollout

---

## 1. Issue Summary

### Problem Statement

The repository and some external-facing references still use the old slug `ai-deploy-whisper`, while the product, CLI, package, and most user-facing branding already use `DeployWhisper` / `deploywhisper`.

This creates three problems:

1. brand inconsistency across GitHub, docs, and release automation
2. avoidable future churn if the repo slug is corrected later
3. risk of breakage if the rename is done as a blanket string replacement instead of a compatibility-managed change

### Change Category

- New requirement emerged from stakeholders
- Strategic product-identity correction

### Evidence

The current state is already partially migrated:

- Product/UI/CLI/package are already aligned to `DeployWhisper` / `deploywhisper`
  - [pyproject.toml](../../pyproject.toml:6)
  - [config.py](../../config.py:11)
  - [README.md](../../README.md:5)
- External repository references still use `ai-deploy-whisper`
  - [README.md](../../README.md:12)
  - [CONTRIBUTING.md](../../CONTRIBUTING.md:41)
  - [docs/ci.md](../../docs/ci.md:3)
  - [release.yml](../../.github/workflows/release.yml:35)
  - [ci.yml](../../.github/workflows/ci.yml:356)
- Planning/BMad metadata still uses the old repo slug
  - [_bmad/bmm/config.yaml](../../_bmad/bmm/config.yaml:6)
  - [_bmad-output/project-context.md](../../_bmad-output/project-context.md:2)
  - [_bmad-output/planning-artifacts/epics.md](../../_bmad-output/planning-artifacts/epics.md:5)
  - [_bmad-output/planning-artifacts/ux-design-specification.md](../../_bmad-output/planning-artifacts/ux-design-specification.md:27)
- Git remote still points to the old slug
  - `origin git@github.com:pramodksahoo/ai-deploy-whisper.git`

---

## 2. Impact Analysis

### Checklist Status

- [x] 1.1 Trigger identified
- [x] 1.2 Core problem defined
- [x] 1.3 Evidence gathered
- [x] 2.1 Current epic still viable
- [x] 2.2 Epic-level changes identified
- [x] 2.3 Future epics reviewed for rename impact
- [x] 2.4 No new epic required
- [x] 2.5 Epic priority/order unchanged
- [x] 3.1 PRD conflict checked
- [x] 3.2 Architecture impact checked
- [x] 3.3 UX impact checked
- [x] 3.4 Secondary artifact impact checked
- [x] 4.1 Direct adjustment evaluated
- [x] 4.2 Rollback evaluated
- [x] 4.3 MVP review evaluated
- [x] 4.4 Recommended path selected
- [x] 5.1 Issue summary created
- [x] 5.2 Impact documented
- [x] 5.3 Recommendation documented
- [x] 5.4 High-level action plan defined
- [x] 5.5 Handoff plan defined
- [x] 6.1 Review complete
- [x] 6.2 Proposal internally consistent
- [ ] 6.3 User approval pending
- [!] 6.4 Artifact updates pending execution

### Epic Impact

No epic is invalidated. No resequencing is required.

This is a cross-cutting documentation, release-automation, and repository-identity change, not a product-scope change. It should be executed as operational hardening and branding alignment alongside current sprint work.

### PRD Impact

Minimal functional impact.

- The PRD product name is already `DeployWhisper`.
- No MVP scope, goals, or requirement families change.
- Only references that imply the project/repository slug should be normalized where they still say `ai-deploy-whisper`.

### Architecture Impact

Low-to-moderate operational impact.

The architecture already prefers `DeployWhisper` as the product identity and `deploywhisper` as the command/package identity. The risky area is external integration metadata:

- GitHub repository URLs
- container image names and package links
- release workflow annotations and published asset text
- repo-root path references baked into docs

### UX / Branding Impact

Low product-risk, medium consistency value.

- The visible brand is already `DeployWhisper`.
- Existing wordmark/image assets may remain if the artwork already matches `DeployWhisper`.
- Asset filenames do not need to be renamed for correctness if image contents are already correct.
- If a future design refresh is desired, handle that as a separate branding task.

### Secondary Artifact Impact

The following non-code artifacts need controlled updates:

- GitHub remote and repository settings
- README badges and links
- CONTRIBUTING clone/build examples
- CI and release workflow image names and package links
- BMad config and generated planning metadata
- Any absolute repo-local markdown links that embed `/ai-deploy-whisper/`

---

## 3. Path Forward Evaluation

### Option 1: Direct Adjustment

**Status:** Viable
**Effort:** Medium
**Risk:** Low-to-Medium

Update repository slug and all external references while preserving current runtime identifiers that already work.

Why viable:

- Most internal identifiers are already correct.
- The remaining change set is well-bounded.
- GitHub provides repository redirects for renamed repositories.

### Option 2: Potential Rollback

**Status:** Not viable
**Effort:** High
**Risk:** Medium

There is nothing to roll back product-wise. The repo is already partially migrated toward the desired identity. Undoing existing `DeployWhisper` / `deploywhisper` naming would increase churn and move in the wrong direction.

### Option 3: PRD MVP Review

**Status:** Not needed
**Effort:** Low
**Risk:** Low

The original MVP remains fully achievable. This is not a scope reduction or strategic product pivot.

### Recommended Approach

**Selected approach:** Hybrid of Option 1 with compatibility safeguards.

The correct solution is:

1. rename the GitHub repository to `deploywhisper`
2. update repo-internal references that are external-facing or metadata-facing
3. preserve working runtime/internal identifiers unless there is a concrete operational reason to change them
4. publish one compatibility window for old image/tag references where practical

This gives naming consistency without risking unnecessary breakage.

---

## 4. Detailed Change Proposals

### 4.1 Repository Identity

**Artifact:** GitHub repository settings and local git remote

**OLD**

- Repository slug: `ai-deploy-whisper`
- Remote: `git@github.com:pramodksahoo/ai-deploy-whisper.git`

**NEW**

- Repository slug: `deploywhisper`
- Remote: `git@github.com:pramodksahoo/deploywhisper.git`

**Rationale**

This is the source-of-truth rename. Everything else should align to this.

### 4.2 External Documentation and Badges

**Artifacts:** [README.md](../../README.md), [CONTRIBUTING.md](../../CONTRIBUTING.md), [docs/ci.md](../../docs/ci.md)

**OLD**

- GitHub badge URLs and links reference `pramodksahoo/ai-deploy-whisper`
- clone/build examples use `ai-deploy-whisper`
- some markdown links embed the current absolute repo path

**NEW**

- Switch all public GitHub URLs to `pramodksahoo/deploywhisper`
- Update clone/build examples to `deploywhisper`
- Replace repo-specific absolute markdown links with stable relative links where possible

**Rationale**

These are the first things users copy. They must match the new repo slug and survive future local folder renames.

### 4.3 CI / Release / Image Publishing

**Artifacts:** [.github/workflows/ci.yml](../../.github/workflows/ci.yml), [.github/workflows/release.yml](../../.github/workflows/release.yml), [docker-compose.yml](../../docker-compose.yml)

**OLD**

- CI scratch image tags still use `ai-deploy-whisper`
- release workflow comments reference old GHCR package path
- commented image examples reference `ghcr.io/pramodksahoo/ai-deploy-whisper`

**NEW**

- Update image examples and workflow references to `deploywhisper`
- If release publishing is already live, publish both:
  - `ghcr.io/pramodksahoo/deploywhisper:<tag>`
  - compatibility alias or migration note for `ghcr.io/pramodksahoo/ai-deploy-whisper:<tag>`
- Keep service/container names like `deploywhisper` and data volume names unchanged

**Rationale**

External artifact consumers break more easily than docs readers. This needs a compatibility-aware rollout.

### 4.4 BMad / Planning Metadata

**Artifacts:** [_bmad/bmm/config.yaml](../../_bmad/bmm/config.yaml), [_bmad-output/project-context.md](../../_bmad-output/project-context.md), [_bmad-output/planning-artifacts/epics.md](../../_bmad-output/planning-artifacts/epics.md), [_bmad-output/planning-artifacts/ux-design-specification.md](../../_bmad-output/planning-artifacts/ux-design-specification.md)

**OLD**

- `project_name: ai-deploy-whisper`
- generated planning text still references `ai-deploy-whisper`

**NEW**

- `project_name: deploywhisper`
- planning metadata and generated prose updated where they refer to repository/project slug rather than product name

**Rationale**

This keeps future BMad outputs aligned with the canonical repo identity.

### 4.5 Internal Runtime Identifiers To Preserve

**Artifacts:** [config.py](../../config.py), [pyproject.toml](../../pyproject.toml), [docker-compose.yml](../../docker-compose.yml), [api/routes/analyses.py](../../api/routes/analyses.py), [ui/theme.py](../../ui/theme.py)

**KEEP AS-IS**

- Product display name `DeployWhisper`
- CLI/package slug `deploywhisper`
- database filename `deploywhisper.db`
- compose service name `deploywhisper`
- volume name `deploywhisper-data`
- header names like `X-DeployWhisper-*`
- theme storage key `deploywhisper-theme`

**Rationale**

These are already correct or operationally stable. Renaming them now adds risk without value.

### 4.6 Brand Images / Logo Assets

**Artifacts:** `docs/assets/*`

**Recommendation**

- Do **not** rename asset files just because the repository slug changes.
- Only regenerate artwork if the visual text/logo itself is wrong.
- If the current images already say `DeployWhisper`, leave them untouched.

**Rationale**

Binary asset renames create extra diff churn and broken references with little benefit.

---

## 5. Recommended Implementation Plan

### Phase 1: Source-of-Truth Rename

1. Rename GitHub repository from `ai-deploy-whisper` to `deploywhisper`
2. Update local `origin` remote
3. Confirm GitHub redirects old repo URLs correctly

### Phase 2: Safe Repo Patch

1. Update public docs, badges, and clone/build examples
2. Update CI/release workflow repo and image references
3. Update BMad config and generated planning metadata that still use the old slug
4. Replace fragile absolute local markdown links with relative links where practical

### Phase 3: Compatibility Verification

1. Run full repo validation
2. Verify README badges and release links resolve
3. Verify CI and release workflows still produce expected tags/links
4. If image publishing is live, provide a migration note for old image consumers

---

## 6. MVP Impact and Risk Assessment

### MVP Impact

No PRD or MVP reduction required.

This is a branding and external-identity correction only. It does not change product scope, access-surface behavior, or architecture boundaries.

### Risk Assessment

- **Technical risk:** Low if internal runtime names are preserved
- **Operational risk:** Medium if GHCR/image/release references are changed without compatibility handling
- **Documentation risk:** Low
- **User confusion risk:** Reduced after rename

### What Must Not Change

- CLI command `deploywhisper`
- persisted DB path `sqlite:///data/deploywhisper.db`
- existing service/volume names unless separately planned
- local-first / advisory-first behavior
- API/UI/CLI shared-core architecture

---

## 7. Handoff Plan

### Scope Classification

**Moderate**

This is bigger than a single doc tweak but not a strategic replan.

### Handoff Recipients

- **Developer agent**
  - execute repo-internal doc/workflow/config updates
  - keep internal runtime names stable
  - validate CI/doc/release references
- **Repository owner / maintainer**
  - rename the GitHub repository
  - confirm package/release/redirect behavior
  - update any external settings not stored in git

### Success Criteria

- GitHub repository slug is `deploywhisper`
- All public repo references in docs/workflows point to `deploywhisper`
- Internal stable identifiers remain unchanged unless explicitly justified
- CI, tests, and release metadata still pass
- Old repo URLs still redirect correctly after rename

---

## 8. Final Recommendation

Proceed with a **compatibility-first repository rename**.

Do **not** perform a blanket rename across every occurrence of `ai-deploy-whisper`, `DeployWhisper`, and `deploywhisper`.

Instead:

- rename the repository slug
- patch only external-facing and metadata-facing old-slug references
- preserve stable runtime/internal identifiers that already use `DeployWhisper` / `deploywhisper`
- avoid unnecessary asset and storage renames

This is the path most likely to give you the clean final identity you want while minimizing breakage.
