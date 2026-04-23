# GitHub App Mode

DeployWhisper now supports an advanced self-hosted GitHub App adapter alongside the Marketplace Action.

## Why this exists

- Action-first mode keeps repository-local workflow ownership simple and best matches the project's local-first trust posture.
- Advanced self-hosted GitHub App mode adds richer GitHub-native capabilities like checks, webhook-driven PR automation, and OAuth-based team installation.
- Combined mode lets teams keep the Action for explicit workflow control while enabling their own self-hosted GitHub App for checks and installation UX.

## Modes

### Action-only

- Use `deploywhisper/analyze-action@v1`
- Best when teams want only workflow-file driven execution
- No GitHub App registration required

### Advanced self-hosted GitHub App

- Create a private or internal GitHub App in your own GitHub account or organization
- Point its webhook and OAuth callback URLs at your own DeployWhisper server
- Enable PR automation with `DEPLOYWHISPER_GITHUB_APP_PR_EVENTS_ENABLED=true`
- Use `/api/v1/github/app/oauth/start` to begin the user authorization flow
- Follow the operator guide in [`docs/github-app-self-hosted-setup.md`](./github-app-self-hosted-setup.md)

### Combined mode

- Keep the Action for explicit workflow dispatch and PR comments
- Install your own self-hosted GitHub App for checks API integration and richer installation/auth flows
- Both paths still use the same DeployWhisper analysis core and persisted report/share contracts

## Positioning

- Default recommendation: `Action-first`
- Advanced option: `self-hosted GitHub App`
- Deferred: public hosted GitHub App / Marketplace SaaS rollout

The current open-source product is intentionally not positioned around a public hosted GitHub App. Teams that want GitHub App behavior should create and run their own app against their own DeployWhisper instance.

## Required environment variables

- `DEPLOYWHISPER_GITHUB_APP_ENABLED=true`
- `DEPLOYWHISPER_GITHUB_APP_ID`
- `DEPLOYWHISPER_GITHUB_APP_SLUG`
- `DEPLOYWHISPER_GITHUB_APP_CLIENT_ID`
- `DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET`
- `DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET`
- `DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY` or `DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY_PATH`
- `APP_BASE_URL` or `PUBLIC_APP_URL`

Optional:

- `DEPLOYWHISPER_GITHUB_APP_PR_EVENTS_ENABLED=true`
- `DEPLOYWHISPER_GITHUB_APP_CHECKS_ENABLED=true`
- `DEPLOYWHISPER_GITHUB_APP_API_BASE_URL`
- `DEPLOYWHISPER_GITHUB_APP_AUTHORIZE_URL`
- `DEPLOYWHISPER_GITHUB_APP_ACCESS_TOKEN_URL`

## Runtime behavior

- Webhook verification uses `X-Hub-Signature-256`
- Pull request webhook actions `opened`, `reopened`, and `synchronize` can trigger automatic advisory analyses when PR automation is enabled
- Supported changed artifacts are downloaded from GitHub, filtered through the shared intake rules, and sent through the existing parse/assess/persist pipeline
- Check runs are advisory-only: `success` for `GO`, `neutral` for `CAUTION`, `failure` for `NO-GO`
- Shared report URLs remain the deep-link target for richer investigation

## OAuth and installation flow

1. Start the user authorization flow at `/api/v1/github/app/oauth/start`
2. GitHub redirects back to `/api/v1/github/app/oauth/callback`
3. DeployWhisper exchanges the code for a GitHub App user access token
4. The callback page hands the maintainer off to the GitHub App installation URL

## Operator guide

Use the detailed operator runbook in [`docs/github-app-self-hosted-setup.md`](./github-app-self-hosted-setup.md) to:

1. Create a private/self-hosted GitHub App in your own account or organization
2. Configure callback URL(s) to your DeployWhisper instance
3. Configure webhook URL and secret
4. Request repository permissions for `checks`, `pull_requests`, and `contents`
5. Subscribe to `pull_request` webhooks
6. Install the app only into the repositories or organizations you control

## Deferred hosted mode

Public hosted / Marketplace GitHub App rollout is intentionally deferred. If that changes later, it should be treated as a separate product and trust-boundary decision rather than implied by the current open-source self-hosted mode.

## OpenSSL note

DeployWhisper signs GitHub App JWTs by calling the system `openssl` binary. Ensure OpenSSL is available in the runtime image or host where the app adapter will run.
