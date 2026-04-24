---
name: jenkins
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [Jenkinsfile, .jenkinsfile, jenkins.groovy]
token_budget: 1400
tags: [jenkins, ci-cd, pipelines]
description: Deep Jenkins pipeline safety knowledge covering approval gate analysis, credential exposure patterns, agent security, deployment stage risks, and shared library vulnerabilities.
test_suite_path: tests/skill-tests/jenkins
trigger_content_patterns: [pipeline, stage, agent, steps, post, input, parallel]
---

## Approval gate analysis

### Removed gates (CRITICAL)
- `input` step removed from before a production deploy stage = CRITICAL — human approval was required and is now bypassed; deployments go straight to production without review
- `input` step with `submitter` parameter removed or changed = HIGH — changes who can approve; removing submitter means ANYONE can approve
- `timeout` removed from `input` step = MEDIUM — without timeout, a stale approval request blocks the pipeline forever; with timeout, auto-rejection prevents zombie pipelines
- `input` step moved from before deploy to after deploy = CRITICAL — approval happens after the change is already in production; defeats the purpose entirely

### Weakened gates (HIGH)
- `input` step moved inside a `parallel` block = HIGH — approval may be requested simultaneously for multiple environments; operator can accidentally approve prod thinking they're approving staging
- `input` message changed to be less specific = MEDIUM — vague approval messages ("Continue?") don't communicate what's being approved; should specify environment, version, and change summary
- `when` condition on deploy stage changed from `branch 'main'` to `branch '*'` = HIGH — production deploy now triggers from any branch, including feature branches and PRs
- `when` condition removed entirely from deploy stage = CRITICAL — deploy stage runs unconditionally on every pipeline execution

## Credential exposure patterns

### Direct exposure (CRITICAL)
- Environment variable set to credential value without `credentials()` helper — `env.DB_PASSWORD = 'actual-password'` exposes the password in pipeline logs, Blue Ocean UI, and build artifacts
- `echo` or `println` of a variable that contains credentials = CRITICAL — Jenkins masks known credential IDs but not arbitrary variables containing secrets
- `sh` step with credentials interpolated in the command string — `sh "curl -u ${USER}:${PASSWORD} https://api..."` exposes credentials in the shell process listing and Jenkins build log
- `writeFile` with credential content without subsequent `archiveArtifacts` exclusion = HIGH — credential file may end up in build artifacts

### Proper credential patterns
- `credentials('credential-id')` binding in `environment` block — Jenkins auto-masks the value in logs
- `withCredentials([...])` block wrapping only the steps that need access — limits exposure scope
- `sshagent(['ssh-key-id'])` for SSH operations — key is loaded into agent memory, not written to disk
- `secretText` / `usernamePassword` / `certificate` credential types — each has specific binding syntax

### CI/CD secret leaks (HIGH)
- `Jenkinsfile` committed to repo with hardcoded secrets = CRITICAL — secrets are in version control history permanently; even after removal, they exist in git history
- `parameters` block with `defaultValue` containing secrets = HIGH — default values are visible in the Jenkins UI and API
- `stash`/`unstash` of files containing secrets between stages = MEDIUM — stashed files are stored on the Jenkins controller; accessible to other builds if not cleaned up
- `archiveArtifacts` including `.env` files, config files with secrets, or credential files = CRITICAL — artifacts are downloadable by anyone with build access

## Agent security

### Execution environment risks (HIGH)
- `agent any` in production pipeline = HIGH — pipeline runs on ANY available agent, including untrusted or shared agents; production pipelines should target specific labeled agents
- `agent { label 'master' }` or `agent { label 'built-in' }` = CRITICAL — running on the Jenkins controller exposes the entire Jenkins configuration, credential store, and all job definitions
- `agent { docker { image 'untrusted:latest' } }` = HIGH — running build in an untrusted container image; supply chain attack vector
- `agent` changed from specific label to `any` = HIGH — regression in agent targeting; production builds may run on development agents

### Sandbox restrictions
- `@NonCPS` annotation on methods = HIGH — bypasses the Groovy sandbox; can execute arbitrary code on the Jenkins controller
- `@Grab` annotation importing external dependencies = CRITICAL — downloads and executes arbitrary code from Maven Central at runtime
- Script approval requests in the Jenkins admin console = MEDIUM — indicates the pipeline is using APIs not in the sandbox whitelist; review what API access is being requested
- `load` step loading external Groovy scripts = HIGH — loaded scripts bypass the Jenkinsfile sandbox unless also sandboxed

## Deployment stage risks

### Deployment patterns (HIGH)
- Deploy stage without preceding test stage = HIGH — deploying untested code; the pipeline structure should enforce test → build → deploy ordering
- Deploy stage in `parallel` block with test stage = HIGH — deploy runs simultaneously with tests, not after them; deploy may complete before tests fail
- Deploy stage without `post { failure { ... } }` rollback block = HIGH — if deployment fails mid-way, there's no automated recovery
- Deploy stage using `sh 'kubectl apply'` without `--dry-run` validation step first = MEDIUM — applying directly without pre-validation; add a dry-run stage before the actual apply

### Rollback and recovery
- Missing `post { failure { } }` block = MEDIUM — no automated action on pipeline failure; at minimum should notify a Slack channel or PagerDuty
- Missing `post { always { } }` cleanup block = MEDIUM — temporary files, Docker containers, and test artifacts are not cleaned up; causes disk space issues over time
- `post { unstable { } }` not defined = LOW — unstable builds (test failures that don't fail the pipeline) may need different handling than full failures
- Retry block with `retry(count)` > 3 = MEDIUM — excessive retries can mask transient errors and delay failure notification; 3 retries is usually sufficient

### Canary and progressive deployment
- Deploy stage going from canary/blue-green to direct deployment = CRITICAL — regression in deployment safety; removes the ability to test with a subset of traffic before full rollout
- `sleep` step used for manual canary validation = MEDIUM — fragile; pipeline blocks for a fixed duration regardless of whether canary is healthy; use a health check loop instead
- Weight-based traffic shifting without health check gate between increments = HIGH — traffic shifts to new version even if it's unhealthy

## Shared library risks

### Library version changes (HIGH)
- `@Library('my-shared-lib@main')` — always uses latest main branch; library change affects ALL pipelines using it simultaneously; a bug in the library breaks every pipeline at once
- Library version changed from pinned tag to branch reference = HIGH — moves from deterministic to non-deterministic behavior
- Library version changed from one tag to another = MEDIUM — review the library changelog for breaking changes
- New `@Library` import added = MEDIUM — introduces dependency on external code; verify the library source is trusted
- Library function signature changed — downstream pipelines using old signature will fail; library authors should maintain backward compatibility

### Library security
- Shared library with `@Grab` dependencies = CRITICAL — external dependency resolution at runtime; can be hijacked via dependency confusion
- Shared library accessing `Jenkins.instance` = CRITICAL — has full access to the Jenkins controller, all credentials, all job configurations
- Shared library modifying global state = HIGH — `env` modifications in a library function affect all subsequent stages in the calling pipeline
- Untrusted shared library (not configured as "trusted" in Jenkins admin) = runs in sandbox — but sandbox escapes exist; review carefully

## Pipeline structure risks

### Resource management
- No `timeout(time: X, unit: 'MINUTES')` on the pipeline = MEDIUM — a stuck build can run indefinitely, consuming an agent slot
- No `timestamps()` option = LOW — makes debugging timing issues difficult; always enable
- `disableConcurrentBuilds()` removed = HIGH — concurrent builds of the same pipeline can cause race conditions on shared resources (same deployment target, same Docker registry tag)
- `buildDiscarder(logRotator(...))` removed or retention increased significantly = MEDIUM — Jenkins controller disk fills up with build logs and artifacts

### Parameter risks
- Pipeline parameter type changed from `choice` to `string` = MEDIUM — removes input validation; users can now enter arbitrary values instead of picking from approved list
- New `booleanParam` defaulting to `true` for a destructive action = HIGH — destructive action is ON by default; operators must actively opt out
- Parameter name changed — all upstream jobs, trigger configurations, and scripts referencing the old parameter name will break silently (pass null/empty instead of failing)
