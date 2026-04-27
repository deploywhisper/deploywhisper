# Story 3.9: Self-Hosted GitHub App Setup Documentation

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a team admin,
I want clear instructions for creating and installing the GitHub App from GitHub Developer Settings,
so that my team can run GitHub App mode without relying on a DeployWhisper-hosted SaaS app.

## Acceptance Criteria

1. Given a team wants GitHub App mode, when they read the operator docs, then they can create a private/internal GitHub App from GitHub Developer Settings without using any DeployWhisper-hosted SaaS app.
2. Given the admin is configuring the app, when they follow the docs, then they can set the webhook URL, optional callback URL, app visibility, repository permissions, and subscribed pull request events correctly.
3. Given the app is created, when the admin configures DeployWhisper, then the docs map each GitHub value to the correct environment variable and clearly mark secrets/private keys as environment-backed only.
4. Given the app is installed from GitHub's UI, when the admin chooses account/organization and repositories, then the docs explain how repository selection affects webhook and check-run behavior.
5. Given setup fails, when the admin reads troubleshooting, then they see specific remediation for missing permissions, revoked installation, unreachable webhook URL, invalid signature, missing public base URL for check-run details, and accidental required-status-check configuration.
6. Given the setup is complete, when the admin follows the verification checklist, then they can confirm webhook delivery, PR artifact analysis, advisory check-run creation, non-blocking behavior, and report-link behavior.
7. Automated checks or doc-focused tests cover the documented configuration examples where practical, and existing GitHub App service/API tests remain green.

### Requirement Traceability

- Primary PRD requirements: `WRK-03`, `WRK-05`, `WRK-07`
- Supporting PRD / NFR / differentiation requirements: `ADM-01`, `NFR-SEC-02`, `NFR-SEC-03`, `DIF-03`, `DIF-04`
- Coverage intent: `Delta`
- Story alignment note: This story keeps GitHub App mode self-hosted and user-owned. Users create and install their own GitHub App from GitHub's Developer Settings UI; DeployWhisper only documents and supports that setup.

## Tasks / Subtasks

- [ ] Align GitHub App docs with the self-hosted product decision. (AC: 1)
  - [ ] State clearly that DeployWhisper will not provide or require a SaaS-hosted GitHub App for this roadmap.
  - [ ] Position the GitHub App as an advanced self-hosted option; keep GitHub Action as the default/recommended path.
  - [ ] Remove wording that implies DeployWhisper must own a public hosted GitHub App or hosted installation flow.
- [ ] Document GitHub Developer Settings setup. (AC: 1, 2)
  - [ ] Walk through GitHub UI path: Settings or organization settings → Developer settings → GitHub Apps → New GitHub App.
  - [ ] Document recommended app name, homepage URL, webhook URL, webhook secret, and app visibility.
  - [ ] Document optional callback URL only as an optional helper if the existing OAuth route remains enabled; do not make OAuth required for normal setup.
  - [ ] Document required repository permissions: checks read/write, pull requests read, contents read, metadata default.
  - [ ] Document required event subscription: pull request.
- [ ] Document DeployWhisper environment configuration. (AC: 3)
  - [ ] Map App ID, app slug, webhook secret, private key, public base URL, PR events flag, and checks flag to the existing environment variables.
  - [ ] Mark `DEPLOYWHISPER_GITHUB_APP_CLIENT_ID` and `DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET` as optional OAuth-helper settings, not required for manual setup.
  - [ ] State that private keys, webhook secrets, and client secrets must remain outside the database and should be supplied through environment or secret manager configuration.
- [ ] Document installation and repository selection from GitHub UI. (AC: 4)
  - [ ] Explain Install App flow from the GitHub App settings page.
  - [ ] Explain account/organization selection and repository selection.
  - [ ] Explain that only selected repositories send eligible webhooks and receive check runs.
- [ ] Add troubleshooting and verification guidance. (AC: 5, 6)
  - [ ] Cover missing permissions, revoked installation, unreachable webhook URL, invalid `X-Hub-Signature-256`, missing `APP_BASE_URL` / `PUBLIC_APP_URL`, and required-status-check misconfiguration.
  - [ ] Include verification checklist for webhook delivery, supported-artifact analysis, persisted report, check run, report link, advisory-only behavior, and 50 MB intake limit.
- [ ] Preserve and validate existing runtime behavior. (AC: 7)
  - [ ] Run existing GitHub App service/API tests after documentation edits.
  - [ ] Add lightweight docs/example validation if the repo already has a suitable documentation test pattern.
  - [ ] Do not add new product flows, hosted-app assumptions, persistent GitHub credential storage, or a tenant model.

## Dev Notes

- The user's product decision is explicit: DeployWhisper will not be hosted as a SaaS product for GitHub App mode. Users should create the app themselves from GitHub Developer Settings and point it at their own DeployWhisper instance.
- Story 3.6 already added a self-hosted GitHub App adapter surface in `integrations/github/app_service.py` and `api/routes/github_app.py`. Do not rebuild that implementation for this story unless docs verification exposes a concrete bug.
- Existing docs already include much of the intended manual setup path in `docs/github-app-self-hosted-setup.md`; this story should make the decision unambiguous and remove any implication that OAuth is required.
- If the current OAuth start/callback route remains in code, document it as optional helper behavior only. The normal setup path is GitHub UI creation and installation.
- Preserve the Action-first recommendation. For most users, `deploywhisper github init` and the GitHub Action remain the lowest-friction path.
- Preserve the local-first boundary: a user's own DeployWhisper server receives webhooks and fetches changed PR artifacts. Do not introduce any flow where raw infrastructure artifacts are sent to a DeployWhisper-hosted SaaS service.
- Preserve advisory-first behavior: check runs may show success/neutral/failure but must not become an enforcement mechanism owned by DeployWhisper.

### Project Structure Notes

- Expected implementation surfaces:
  - `docs/github-app.md`
  - `docs/github-app-self-hosted-setup.md`
  - `README.md` only if its GitHub App setup language is stale
  - `tests/test_services/test_github_app_service.py` and `tests/test_api/test_github_app.py` for existing runtime regression checks
- Avoid touching database, OAuth persistence, tenant management, or hosted-app infrastructure for this story.
- Do not place GitHub-specific setup logic into analysis services, parsers, risk scoring, or report rendering.

### Previous Story Intelligence

- Story 3.6 implemented the self-hosted GitHub App adapter and reopened real-operator verification.
- Story 3.6 tightened PR artifact download to enforce the shared 50 MB intake limit.
- Story 3.8 implemented `deploywhisper github init` with Action-first setup and advanced self-hosted GitHub App notes.
- Existing docs already emphasize private/self-hosted GitHub App setup and defer public hosted/Marketplace rollout.

### References

- [Epics](../planning-artifacts/epics.md)
- [PRD](../planning-artifacts/prd.md)
- [Architecture](../planning-artifacts/architecture.md)
- [Project Context](../project-context.md)
- [Story 3.6](3-6-github-app.md)
- [Story 3.8](3-8-installation-wizard.md)
- [GitHub App docs](../../docs/github-app.md)
- [Self-hosted GitHub App setup](../../docs/github-app-self-hosted-setup.md)

## Dev Agent Record

### Agent Model Used

`gpt-5.4`

### Debug Log References

### Completion Notes List

- Story corrected after product decision clarification: GitHub App mode is self-hosted/manual setup documentation, not an OAuth-backed hosted installation product.

### File List
