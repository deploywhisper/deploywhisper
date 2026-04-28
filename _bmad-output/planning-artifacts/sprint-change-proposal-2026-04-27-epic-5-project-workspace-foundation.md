# Sprint Change Proposal: Epic 5 Project Workspace Foundation

Date: 2026-04-27
Project: deploywhisper
Workflow: bmad-correct-course

## 1. Issue Summary

Epic 5 currently assumes reports and context can be meaningfully persisted before there is a stable project/workspace container. That breaks down once multiple teams or repositories use the same DeployWhisper instance: history, topology, deployment outcomes, and reviewer feedback become a flat list of unrelated analyses.

The product needs a lightweight SonarQube-style project/workspace model before the current Epic 5 topology and feedback work starts. This is a scoping feature, not an enterprise auth feature.

## 2. Decision

Add a new first story to Epic 5:

- `E5-S1: Project workspace foundation`

Then shift the existing Epic 5 story sequence down by one so topology import foundation becomes `E5-S2`.

## 3. Recommended Scope

Include:

- project key and display name
- optional description, repository URL, and default branch
- UI project selection/creation before manual upload
- API/CLI analysis submission by `project_key` or `project_id`
- GitHub integration support for explicit project key or repository-derived default
- project-scoped reports, topology, history, outcomes, and feedback
- legacy-data mapping to a default/unassigned project

Explicitly exclude:

- multi-tenant enterprise orgs
- RBAC
- SSO
- per-team permissions
- hosted SaaS scoping

## 4. Impact

This change keeps Epic 5 in the correct place. Project/workspace scoping is part of the context moat because all later topology, drift, history, outcome, and calibration features need a stable isolation unit.

It does not require a new epic. It does require:

- Epic 5 renumbering
- sprint status renumbering
- story artifact regeneration for the Epic 5 set
- PRD and architecture updates for project-scoped analysis

## 5. Handoff

Scope classification: Moderate.

Implementation order:

1. `E5-S1 Project workspace foundation`
2. `E5-S2 Topology import foundation and source registry`
3. remaining Epic 5 stories in the corrected order

Success criteria:

- reports are no longer a flat global pile
- GitHub action flows can map to a stable project automatically
- project scoping exists without introducing enterprise tenancy/auth scope
