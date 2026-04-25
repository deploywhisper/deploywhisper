# Sprint Change Proposal: Meta-Provider to Direct Provider SDK Migration

**Date:** 2026-04-24
**Project:** DeployWhisper
**Triggered by:** Operational pain from meta-provider dependency management during active delivery
**Mode Assumed:** Batch
**Recommended Scope:** Moderate
**Selected Approach:** Hybrid of Direct Adjustment + staged compatibility-preserving migration
**Implementation Status:** Completed by brownfield hardening stories `BH-S1` through `BH-S5` on 2026-04-25. This proposal is retained as the decision record that initiated the migration.

---

## 1. Issue Summary

### Problem Statement

DeployWhisper previously used an external meta-provider package as the narrative-provider abstraction layer, but the repo saw operational friction that was disproportionate to the value that package provided for this codebase.

This creates four concrete problems:

1. security posture concerns from the meta-provider dependency chain
2. transitive dependency conflicts and resolver instability in CI
3. avoidable coupling between DeployWhisper and a meta-provider SDK for a narrow narrative-only use case
4. increased risk that future provider-native capabilities such as MCP and richer tool integration arrive later or less cleanly through the abstraction layer

### Change Category

- Technical course correction during active implementation
- Operational hardening of the narrative-provider boundary
- Architecture clarification for future provider and MCP work

### Evidence

The implementation shape at proposal time was clear:

- DeployWhisper already centralizes provider invocation behind a narrow boundary
  - [llm/providers.py](../../llm/providers.py:1)
  - [llm/narrator.py](../../llm/narrator.py:88)
- Provider selection and readiness are already centralized in one service
  - [services/settings_service.py](../../services/settings_service.py:46)
- The current product posture is local-first, narrative-last, and advisory-only
  - [prd.md](./prd.md:202)
  - [architecture.md](./architecture.md:51)
- At proposal time, the repo still pinned the external meta-provider directly; the completed `BH-S4` migration removed it from runtime manifests
  - [requirements.txt](../../requirements.txt:7)
  - [pyproject.toml](../../pyproject.toml:18)
- Historical story artifacts explicitly assumed an external meta-provider as the provider-independence layer
  - [archived-story-set-2026-04-20/4-1-configure-narrative-provider-settings.md](../implementation-artifacts/archived-story-set-2026-04-20/4-1-configure-narrative-provider-settings.md:23)

### Why The Trigger Is Legitimate

This is not a speculative rewrite request.

DeployWhisper's LLM role is intentionally constrained:

- narrative generation runs after deterministic scoring
- narrative failure already degrades safely
- provider settings are admin-controlled
- raw IaC is kept local and only structured summaries cross the provider boundary

That means DeployWhisper does not need a broad multi-provider abstraction to protect a complex agent runtime. It needs a stable, reviewable, repo-owned adapter boundary for a small number of provider operations.

---

## 2. Impact Analysis

### Checklist Status

- [x] 1.1 Trigger identified
- [x] 1.2 Core problem defined
- [x] 1.3 Evidence gathered
- [x] 2.1 Current epic plan still viable
- [x] 2.2 Epic-level changes identified
- [x] 2.3 Future provider and MCP work reviewed for impact
- [x] 2.4 No full roadmap reset required
- [x] 2.5 Existing shipped behavior should be preserved
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
- [x] 6.3 User approval captured by execution of `BH-S1` through `BH-S5`
- [x] 6.4 Artifact updates executed in PRD, architecture, epics, and project context

### Epic Impact

No existing epic is invalidated.

This change is best treated as a **brownfield hardening track** that protects and clarifies existing provider functionality while preserving the six-epic roadmap.

The roadmap remains valid:

- Epic 1 still owns evidence-before-narrative discipline
- Epic 3 still owns workflow-native delivery
- Epic 4 still owns skills ecosystem work
- Epic 5 and later work still own future provider and MCP-adjacent extension points

What changes is the architectural interpretation of provider independence:

- **OLD:** provider independence is achieved through an external meta-provider package
- **NEW:** provider independence is achieved through a DeployWhisper-owned adapter contract using direct provider SDKs where warranted

### Story Impact

The current refreshed epics do not need wholesale resequencing, but they do need an explicit implementation track for this migration.

Recommended new brownfield stories:

- `BH-S1` Lock current provider-boundary behavior with regression tests
- `BH-S2` Introduce internal provider adapter contract and adapter registry
- `BH-S3` Migrate OpenAI, Anthropic, Gemini, and Ollama to direct SDK adapters
- `BH-S4` Migrate OpenRouter, Groq, and xAI to a compatibility adapter and remove the legacy meta-provider dependency
- `BH-S5` Add provider capability metadata and MCP readiness hooks

### PRD Impact

Moderate documentation impact, low product-scope impact.

The PRD already supports this course correction:

- provider settings remain an admin capability
- local-only operation remains a core requirement
- raw IaC staying local remains unchanged
- advisory-first behavior remains unchanged

What is missing is explicit wording that provider abstraction is **owned by DeployWhisper** and should remain swappable independently of any single third-party meta-SDK.

### Architecture Impact

Moderate.

The architecture needs one explicit adjustment:

- describe narrative-provider integration as an internal adapter layer
- define which providers are first-class direct adapters vs compatibility adapters
- document how future MCP capability is modeled without prematurely promising one-provider lock-in

### UX Impact

Low.

No user-facing review flow needs redesign.

Admin settings language should eventually become more precise:

- provider choice remains exposed
- local-only mode remains exposed
- readiness validation remains exposed
- future capability display may show structured-output / local-only / MCP support metadata

### Technical Impact

Code changes can stay narrow if the repo preserves current boundaries:

- keep [llm/narrator.py](../../llm/narrator.py:88) stable
- keep [services/settings_service.py](../../services/settings_service.py:46) as the authority for provider selection and readiness
- turn [llm/providers.py](../../llm/providers.py:1) into a facade over repo-owned adapters

New dependencies become explicit and reviewable:

- `openai`
- `anthropic`
- `google-genai`
- `ollama`

Secondary providers should not force equal first-class complexity on day one:

- `openrouter`
- `groq`
- `xai`

These should start as compatibility-adapter integrations unless product usage justifies first-class native adapters later.

---

## 3. Recommended Approach

### Option 1: Direct Adjustment

**Status:** Viable and recommended
**Effort:** Moderate
**Risk:** Moderate but bounded

Introduce a DeployWhisper-owned provider adapter contract, migrate primary providers to direct SDKs, keep the public narrative boundary stable, then remove the legacy meta-provider dependency after parity is verified.

Why viable:

- the current repo already has the right abstraction seams
- the LLM use case is narrow
- the local-first product contract reduces feature-surface complexity
- the migration can be split into reviewable phases

### Option 2: Potential Rollback

**Status:** Not recommended
**Effort:** Medium
**Risk:** Medium

Rolling back to a single-provider solution would reduce complexity, but it would conflict with the current admin-provider settings story and reduce strategic flexibility before the provider picture is intentionally narrowed.

### Option 3: PRD MVP Review

**Status:** Not required
**Effort:** Low
**Risk:** Low

This is not a scope-reduction event. The product still needs multi-provider support and fully local Ollama mode. The correction is architectural, not product-definitional.

### Recommended Approach

**Selected approach:** Direct adjustment with staged compatibility safeguards.

The correct path is:

1. freeze existing provider behavior with tests
2. introduce an internal adapter contract without changing caller contracts
3. move primary providers to direct SDK adapters
4. keep lower-priority providers behind a compatibility adapter
5. remove the legacy meta-provider dependency only after parity and validation are complete

This keeps the migration reviewable and avoids a rewrite disguised as refactoring.

### Target Provider Support Model

**Tier 1: First-class direct adapters**

- `ollama`
- `openai`
- `anthropic`
- `gemini`

**Tier 2: Supported compatibility adapters**

- `openrouter`
- `groq`
- `xai`

**Tier 3: Future / on-demand**

- any additional provider only when there is a clear product or operational reason

### MCP Positioning

This change should make MCP possible later without combining MCP delivery into the migration itself.

The architecture should reserve capability flags for:

- `supports_structured_output`
- `supports_remote_mcp`
- `supports_local_mcp`
- `supports_tool_approval`
- `supports_local_only_mode`

This prevents current planning from overcommitting to a single provider while still making future MCP work intentional.

---

## 4. Detailed Change Proposals

### 4.1 PRD Updates

**Artifact:** [prd.md](./prd.md)

#### Change A: Clarify provider-boundary ownership

**Section:** Administration and customization

**OLD**

- `ADM-01` Admins shall configure narrative provider settings

**NEW**

- `ADM-01` Admins shall configure narrative provider settings through a DeployWhisper-owned provider adapter boundary that preserves cross-surface behavior and keeps provider secrets out of persistence.

**Rationale**

This keeps the product requirement intact while removing the implicit assumption that a third-party meta-SDK is the abstraction layer.

#### Change B: Add provider-adapter operability requirement

**Section:** Operability and architecture

**OLD**

- `NFR-OPS-01` through `NFR-OPS-04`

**NEW**

- Add `NFR-OPS-05`: Narrative provider integrations shall be isolated behind an internal adapter interface so providers can be added, removed, upgraded, or capability-scoped without rewriting UI, API, CLI, or report persistence flows.

**Rationale**

This is the requirement-level anchor for the migration.

#### Change C: Tighten security / supply-chain language

**Section:** Trust and security or adjacent implementation note

**OLD**

- security language focuses on raw IaC and credential persistence

**NEW**

- add guidance that the narrative integration path should minimize unnecessary dependency and supply-chain surface where direct provider SDKs satisfy the needed capability more safely

**Rationale**

This records the reason the course correction exists without changing product scope.

### 4.2 Architecture Updates

**Artifact:** [architecture.md](./architecture.md)

#### Change A: Replace externally implied provider abstraction with internal adapter layer

**Section:** System context / high-level component view / narrative-service description

**OLD**

- LLM provider integration is described generically and may be interpreted as provider independence being delegated externally

**NEW**

- narrative generation is implemented through a DeployWhisper-owned provider adapter layer
- structured summaries remain the only provider payload boundary
- direct SDKs are preferred for first-class providers

**Rationale**

This aligns the architecture with the intended technical control point.

#### Change B: Add provider support tiers and capability model

**Section:** New subsection under platform or narrative architecture

**NEW**

- Tier 1 direct adapters: Ollama, OpenAI, Anthropic, Gemini
- Tier 2 compatibility adapters: OpenRouter, Groq, xAI
- capability metadata fields for future MCP/tooling support

**Rationale**

This avoids pretending all providers deserve identical architectural weight.

#### Change C: Update project structure

**Section:** Repo structure

**OLD**

- `llm/narrator.py`
- `llm/providers.py`
- `llm/summary_builder.py`

**NEW**

- `llm/narrator.py`
- `llm/providers.py`
- `llm/adapters/base.py`
- `llm/adapters/registry.py`
- `llm/adapters/openai_adapter.py`
- `llm/adapters/anthropic_adapter.py`
- `llm/adapters/gemini_adapter.py`
- `llm/adapters/ollama_adapter.py`
- `llm/adapters/openai_compatible_adapter.py`
- `llm/summary_builder.py`

**Rationale**

This is the minimal structural expression of the migration.

#### Change D: Add ADR for direct SDK preference

**Section:** ADRs

**NEW**

- prefer direct provider SDKs over external meta-provider abstractions for the narrative path
- reason: dependency risk, resolver churn, narrow repo use case, and future provider-native MCP/tool divergence

**Rationale**

This stops future re-litigation without rationale.

### 4.3 Epic Updates

**Artifact:** [epics.md](./epics.md)

#### Change A: Extend baseline-vs-roadmap note

**Section:** Baseline vs Roadmap

**OLD**

- provider settings and local-only mode are described as existing baseline

**NEW**

- clarify that the baseline includes provider settings and local-only mode, but the provider abstraction itself is subject to brownfield hardening from external meta-provider use to repo-owned adapters

**Rationale**

Prevents future implementers from assuming the current dependency choice is architecture gospel.

#### Change B: Add brownfield hardening track

**Section:** New section after compact traceability matrix or after Epic 6

**NEW**

- `BH-S1` Lock provider-boundary behavior with regression tests
- `BH-S2` Introduce provider adapter contract and registry
- `BH-S3` Migrate direct adapters for OpenAI / Anthropic / Gemini / Ollama
- `BH-S4` Migrate compatibility adapters for OpenRouter / Groq / xAI and remove the legacy meta-provider dependency
- `BH-S5` Add provider capability metadata and MCP readiness hooks

Each story should specify that:

- report schema must stay stable
- degraded fallback must stay stable
- admin provider settings behavior must stay stable
- raw IaC locality guarantees must stay stable

**Rationale**

This makes the work visible without disturbing the main six-epic roadmap.

#### Change C: Add traceability note

**Section:** Compact FR/NFR Traceability Matrix

**NEW**

- `ADM-01..02`, `NFR-SEC-01..05`, and new `NFR-OPS-05` are additionally enforced by the brownfield provider-migration track

**Rationale**

This prevents the migration from becoming an untracked engineering side quest.

### 4.4 Project Context Regeneration

**Artifact:** [_bmad-output/project-context.md](../project-context.md)

**OLD**

- project context still describes the LLM layer as backed by the previous meta-provider

**NEW**

- project context should be regenerated after the architecture/PRD/epic updates so future implementation guidance reflects the direct-adapter model

**Rationale**

This prevents stale implementation guidance from undoing the planning fix.

### 4.5 Historical Artifact Handling

**Artifact:** archived implementation story files

**OLD**

- archived provider-settings story states the earlier meta-provider abstraction as an accepted solution

**NEW**

- do not rewrite archived artifacts
- treat this sprint change proposal as the superseding decision record

**Rationale**

History should remain honest. Correction belongs in new planning artifacts, not rewritten history.

---

## 5. Implementation Handoff

**Status:** Completed. The handoff below records the execution plan that was followed by `BH-S1` through `BH-S5`.

### Scope Classification

**Moderate**

This is not a full replan, but it is larger than a direct single-story edit. It requires backlog organization plus a tightly-scoped engineering migration.

### Handoff Recipients

- **Product / Planning owner**
  - approve the course correction
  - accept PRD / architecture / epic wording changes
- **Developer**
  - implement the adapter migration in staged PRs
- **Reviewer / Architect**
  - validate that provider behavior, locality guarantees, and report contracts remain intact

### Proposed Execution Order

1. update planning artifacts
2. regenerate project context
3. create brownfield implementation stories
4. implement `BH-S1`
5. implement `BH-S2`
6. implement `BH-S3`
7. implement `BH-S4`
8. implement `BH-S5` if MCP-readiness metadata is wanted now

### Success Criteria

- Legacy meta-provider package removed from runtime dependency path
- provider settings UX/API remain stable
- Ollama local-only mode still works
- OpenAI, Anthropic, Gemini, and Ollama run through direct adapters
- OpenRouter, Groq, and xAI still work through a compatibility path
- narrative degradation behavior remains unchanged
- report schema and persisted provider metadata remain unchanged or intentionally versioned
- project docs and project-context no longer describe an external meta-provider as the core provider abstraction

### Immediate Next Step

Completed on 2026-04-25. The original next step was:

Create the exact doc edits in:

- [prd.md](./prd.md)
- [architecture.md](./architecture.md)
- [epics.md](./epics.md)

Then regenerate:

- [_bmad-output/project-context.md](../project-context.md)

After those planning artifacts are aligned, create the brownfield implementation story set and begin with regression-test locking before any dependency change.

---

## 6. Proposed Doc-Edit Handoff Summary

- Issue addressed: the previous external meta-provider created operational pain and is no longer the best abstraction for DeployWhisper's narrative path
- Change scope: Moderate
- Artifacts updated: `prd.md`, `architecture.md`, `epics.md`, `project-context.md`
- Implementation completed: `BH-S1` through `BH-S5`
