# Self-Hosted GitHub App Setup

This guide shows how a user or team creates a private/self-hosted DeployWhisper GitHub App in their own GitHub account or organization and points it at their own DeployWhisper server.

This is the recommended GitHub App model for the open-source product.

## When to use this

Use this guide if you want:

- Action-first as the default integration mode
- GitHub check runs and webhook-driven PR analysis
- your own DeployWhisper server to receive and analyze PR artifacts
- no dependency on a public hosted DeployWhisper GitHub App

## What this model means

- You create the GitHub App in your own GitHub account or organization
- GitHub sends webhooks to your own DeployWhisper server
- Your own DeployWhisper server fetches changed PR artifacts
- Your own DeployWhisper server creates advisory check runs and report links
- The app does not need to be public or listed on GitHub Marketplace
- App creation, account or organization selection, and repository selection happen in GitHub's own Developer Settings and Install App UI

## Prerequisites

- A reachable DeployWhisper base URL such as `https://deploywhisper.example.com`
- A DeployWhisper instance running the Story 3.6 GitHub App adapter code
- Ability to set environment variables on that DeployWhisper instance
- Admin access to the GitHub account or organization where the GitHub App will live

## DeployWhisper server settings

Set these on your DeployWhisper server:

- `DEPLOYWHISPER_GITHUB_APP_ENABLED=true`
- `DEPLOYWHISPER_GITHUB_APP_ID`
- `DEPLOYWHISPER_GITHUB_APP_SLUG`
- `DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET`
- `DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY` or `DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY_PATH`
- `APP_BASE_URL` or `PUBLIC_APP_URL`

Optional:

- `DEPLOYWHISPER_GITHUB_APP_CLIENT_ID` and `DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET` if you intentionally enable the optional OAuth helper route
- `DEPLOYWHISPER_GITHUB_APP_PR_EVENTS_ENABLED=true`
- `DEPLOYWHISPER_GITHUB_APP_CHECKS_ENABLED=true`
- `DEPLOYWHISPER_GITHUB_APP_API_BASE_URL`
- `DEPLOYWHISPER_GITHUB_APP_AUTHORIZE_URL`
- `DEPLOYWHISPER_GITHUB_APP_ACCESS_TOKEN_URL`

If you enable GitHub check runs, `APP_BASE_URL` or `PUBLIC_APP_URL` must be a
reachable DeployWhisper URL. GitHub uses that public report URL for the PR
Details link.

## GitHub UI steps

### 1. Open GitHub App settings

1. Sign in to GitHub as the account or org admin that will own the app
2. Open `Settings`
3. Open `Developer settings`
4. Click `GitHub Apps`
5. Click `New GitHub App`

### 2. Fill the basic app fields

Recommended values:

- GitHub App name:
  `DeployWhisper`
- Description:
  `Advisory-only deployment risk analysis for pull requests using your own DeployWhisper server.`
- Homepage URL:
  `https://<your-deploywhisper-base-url>`
- Callback URL:
  `https://<your-deploywhisper-base-url>/api/v1/github/app/oauth/callback`
- If you are not using the optional OAuth helper route, leave user authorization disabled or treat this callback URL as optional setup metadata. The normal self-hosted setup path does not require OAuth.
- Setup URL:
  Leave blank unless you later build a dedicated install UI
- Webhook URL:
  `https://<your-deploywhisper-base-url>/api/v1/github/app/webhook`
- Webhook secret:
  Use a long random value and store the same value in `DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET`

### 3. Keep the app private to your account or org

- Do not publish the app to GitHub Marketplace
- Do not depend on a public hosted listing
- Install it only on repositories or organizations you control

### 4. Configure permissions

Repository permissions:

- `Checks`: `Read and write`
- `Pull requests`: `Read-only`
- `Contents`: `Read-only`
- `Metadata`: default

### 5. Subscribe to webhook events

Enable:

- `Pull request`

### 6. Create app credentials

After creating the app:

1. Copy the GitHub App `App ID`
2. Generate a private key and download the `.pem`
3. Copy the app slug from the GitHub App URL

Map them into DeployWhisper:

- `DEPLOYWHISPER_GITHUB_APP_ID=<App ID>`
- `DEPLOYWHISPER_GITHUB_APP_SLUG=<your app slug>`
- `DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET=<same webhook secret configured in GitHub>`
- `DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY_PATH=<path to pem>`
  or
- `DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY=<pem contents>`
- `APP_BASE_URL=https://<your-deploywhisper-base-url>`

Also set:

- `DEPLOYWHISPER_GITHUB_APP_PR_EVENTS_ENABLED=true`
- `DEPLOYWHISPER_GITHUB_APP_CHECKS_ENABLED=true`

Only set `DEPLOYWHISPER_GITHUB_APP_CLIENT_ID` and
`DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET` when you intentionally enable the
optional OAuth helper route. They are not required for the manual setup path.

## Installation steps

1. Open the GitHub App settings page
2. Click `Install App`
3. Choose your account or organization
4. Select the repositories you want the app to access
5. Complete the installation

## Verification checklist

1. Open a PR in an installed repository that changes supported deployment artifacts
2. Confirm GitHub delivers the webhook successfully
3. Confirm DeployWhisper receives the webhook
4. Confirm DeployWhisper downloads the changed files within the shared 50 MB limit
5. Confirm DeployWhisper persists a report
6. Confirm a check run named `DeployWhisper / Risk Analysis` appears on the PR
7. Confirm the check remains advisory-only and does not block merge on its own
8. Confirm the report link opens your own DeployWhisper server
9. Confirm branch protection does not list `DeployWhisper / Risk Analysis` as a required status check

## Troubleshooting

### GitHub does not deliver webhooks

- Confirm the app is installed on the repository or organization that owns the PR
- Confirm the app subscribes to the `Pull request` event
- Confirm the webhook URL is reachable from GitHub
- Confirm `DEPLOYWHISPER_GITHUB_APP_ENABLED=true`

### Webhook signature verification fails

- Confirm the GitHub webhook secret exactly matches `DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET`
- Confirm GitHub is sending the `X-Hub-Signature-256` header
- Rotate the webhook secret in both GitHub and DeployWhisper if the value may have leaked

### Check run is not created

- Confirm repository permission `Checks` is set to `Read and write`
- Confirm `DEPLOYWHISPER_GITHUB_APP_CHECKS_ENABLED=true`
- Confirm `APP_BASE_URL` or `PUBLIC_APP_URL` points at the reachable DeployWhisper base URL
- Confirm the app installation still has access to the repository

### Pull request files are not analyzed

- Confirm repository permissions include `Pull requests: Read-only` and `Contents: Read-only`
- Confirm the PR changes supported deployment artifacts
- Confirm the changed artifacts stay within the shared 50 MB analysis-session limit
- Check DeployWhisper logs for unsupported file-type or sensitive-file rejection messages

### Installation was revoked or repository access changed

- Re-open the GitHub App settings page
- Click `Install App`
- Confirm the account or organization and selected repositories are still correct
- Reinstall or update repository access from GitHub's UI

### Branch protection blocks merge on DeployWhisper

DeployWhisper is advisory-only. Remove `DeployWhisper / Risk Analysis` from
required status checks in GitHub branch protection. Teams can still read the
check result, but DeployWhisper should not be configured as the component that
blocks merges.

## Action-first recommendation

For most teams, the recommended rollout order is:

1. Start with the DeployWhisper GitHub Action
2. Confirm your DeployWhisper instance and report links are working
3. Add the self-hosted GitHub App only if you want richer GitHub-native checks and webhook automation

## Combined mode

Combined mode means:

- Action handles explicit workflow execution and PR comments
- Self-hosted GitHub App handles checks API and webhook automation after installation from GitHub's UI

Both still point at your own DeployWhisper server.

## What is intentionally deferred

This guide does not cover:

- public hosted GitHub App rollout
- GitHub Marketplace listing/publication
- a SaaS trust model where other users send PR data to a third-party hosted DeployWhisper service

Those are separate product decisions and are intentionally deferred from the current open-source self-hosted deployment model.

## Optional OAuth helper route

The repository includes OAuth start/callback endpoints for advanced setups, but they are not required for the standard self-hosted GitHub App path. The standard path is:

1. Create the GitHub App in GitHub Developer Settings
2. Configure webhook, permissions, events, and private key
3. Install the app from GitHub's own `Install App` UI
4. Configure DeployWhisper environment variables
5. Verify webhook delivery and advisory check runs

Do not store GitHub client secrets, webhook secrets, private keys, or user access tokens in the application database.
