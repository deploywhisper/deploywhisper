---
name: git
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [.diff, .patch, .gitdiff]
token_budget: 1200
tags: [git, diff, review]
description: Git-based change context intelligence covering commit analysis, sensitive file detection, branch risk signals, author patterns, and co-change analysis. This skill is always loaded because Git context enriches every other tool's analysis.
test_suite_path: tests/skill-tests/git
always_load: true
---

## Sensitive file detection

### Auto-block from LLM transmission (CRITICAL)
These file patterns must NEVER be sent to external LLM providers. If detected in uploaded files, exclude content from LLM payload and display a prominent warning to the user.

- `.env`, `.env.local`, `.env.production`, `.env.*` — environment variables often contain API keys, database credentials, and secrets
- `*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx` — TLS certificates and private keys
- `id_rsa`, `id_ed25519`, `id_ecdsa`, `*.pub` (private key counterparts) — SSH keys
- `kubeconfig`, `.kube/config`, `kube.config` — Kubernetes cluster credentials with admin access
- `credentials`, `credentials.json`, `credentials.xml` — generic credential stores
- `*.tfstate`, `*.tfstate.backup` — Terraform state files contain every resource attribute including passwords, connection strings, and private IPs
- `terraform.tfvars` containing `password`, `secret`, `token`, `key` variables — inspect variable names, not just filename
- `aws_credentials`, `.aws/credentials`, `.aws/config` — AWS access keys and session tokens
- `gcloud-service-account*.json`, `*-sa-key.json` — GCP service account keys
- `.npmrc`, `.pypirc` with auth tokens — package registry credentials
- `vault-token`, `.vault-token`, `vault.json` — HashiCorp Vault access tokens
- `docker-compose*.yml` with `environment` sections containing hardcoded secrets

### Sensitive content patterns (HIGH)
Even in non-sensitive filenames, flag if content contains:
- Strings matching `AKIA[0-9A-Z]{16}` — AWS access key ID pattern
- Strings matching `ghp_[a-zA-Z0-9]{36}` — GitHub personal access token
- Strings matching `sk-[a-zA-Z0-9]{48}` — OpenAI API key pattern
- Strings matching `xox[bpors]-[a-zA-Z0-9-]+` — Slack token pattern
- Variables named `password`, `secret`, `token`, `api_key`, `apikey`, `access_key`, `private_key` with string literal values
- Base64-encoded blocks longer than 100 characters in YAML/JSON values — may be encoded credentials

## Commit context analysis

### Commit message signals (MEDIUM)
- Commit message containing `hotfix`, `urgent`, `emergency`, `ASAP`, `quick fix` = MEDIUM — rushed changes are more likely to have errors; flag for extra review attention
- Commit message containing `revert`, `rollback`, `undo` = informational — indicates a previous change caused problems; the original change and this revert should be understood together
- Commit message referencing a ticket/issue (e.g., `JIRA-1234`, `#456`, `fixes #789`) = positive signal — change is tracked and has context
- Commit message with no ticket reference on infrastructure files = MEDIUM — untracked infrastructure change; may bypass change management process
- Very short commit messages (`fix`, `update`, `test`, `wip`) on production infrastructure files = MEDIUM — suggests the change wasn't carefully considered
- Commit message mentioning `temporary`, `hack`, `workaround`, `TODO` = MEDIUM — indicates technical debt being introduced intentionally

### Change magnitude signals
- Single commit touching more than 10 infrastructure files = HIGH — large blast radius change; should be broken into smaller, reviewable chunks
- Single commit mixing infrastructure changes with application code changes = MEDIUM — infrastructure and application should be deployed independently; coupled changes increase rollback complexity
- Commit with more lines deleted than added in infrastructure files = informational — net reduction in infrastructure; verify nothing critical was removed
- Empty commit or merge commit with no diff = informational — may be a pipeline trigger or branch synchronization; no analysis needed

## Branch risk signals

### Deployment source risks (HIGH)
- Deploying from a branch other than `main`, `master`, or `release/*` = HIGH — non-standard deployment source; may contain unreviewed or in-progress changes
- Deploying from a branch with `force-push` in its recent history = CRITICAL — force-push rewrites history; commits may have been removed or altered without review; the deployment artifact may not match what was code-reviewed
- Deploying from a branch that is behind `main` by more than 20 commits = MEDIUM — stale branch; infrastructure may have changed significantly since the branch was created; merge conflicts or missing dependencies are likely
- Deploying from a branch with unresolved merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) = CRITICAL — conflict markers in YAML or HCL files cause parse failures; in some cases they may be silently ignored by lenient parsers, creating malformed infrastructure

### Branch hygiene signals
- Branch name containing `experiment`, `test`, `poc`, `spike` = HIGH if deploying to production — these branch names indicate exploratory work that shouldn't reach production
- Multiple unreviewed commits on the branch = MEDIUM — changes may not have been peer-reviewed; especially risky for infrastructure modifications
- Branch with no associated pull request = MEDIUM — bypasses the code review process; direct pushes to deploy branches should require justification

## Author risk signals

### Author context (MEDIUM)
- First-time contributor to infrastructure files = HIGH — new to the IaC codebase; changes deserve extra review attention regardless of the contributor's seniority
- Changes to infrastructure files by an author who primarily commits application code = MEDIUM — infrastructure requires different expertise; application developers may not understand Terraform state implications or K8s resource management nuances
- Commits outside normal working hours (22:00-06:00 local time) on non-incident branches = MEDIUM — late-night changes correlate with higher error rates; not a hard rule but worth flagging
- Multiple authors modifying the same infrastructure file in the same PR = informational — indicates collaborative infrastructure change; verify changes don't conflict

### Review status
- PR with zero approvals deploying to production = HIGH — no peer review on infrastructure change
- PR with approvals from team members who don't own the affected infrastructure = MEDIUM — approval may lack domain expertise
- PR approved more than 5 days ago without re-approval = MEDIUM — infrastructure context may have changed since the review; consider re-review

## Co-change analysis

### Missing co-changes (HIGH)
- Terraform security group change without corresponding application configuration change = informational — new ports opened may need application config to use them
- Kubernetes deployment image change without ConfigMap or Secret update = informational — new application version may expect new configuration
- Ansible role update without inventory change = informational — new role variables may need inventory-level overrides
- Jenkinsfile deploy stage change without corresponding infrastructure change = informational — deployment process changed but infrastructure target is the same; verify compatibility
- Dockerfile base image change without Kubernetes resource limit update = MEDIUM — new base image may have different memory/CPU footprint; resource limits may need adjustment

### Historical co-change patterns
- Files that historically change together (detected from git log) but only one is present in the current changeset = MEDIUM — potential missing co-change; common example: Terraform module source changed but module variable file not updated
- Infrastructure files that always change in pairs (e.g., `main.tf` and `variables.tf`) but only one is modified = LOW — may indicate incomplete change
