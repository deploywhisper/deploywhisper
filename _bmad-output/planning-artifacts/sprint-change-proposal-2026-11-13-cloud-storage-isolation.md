# Story 17.1 storage isolation correction

Date:2026-11-13. Classification: **minor direct implementation adjustment**, no product scope or acceptance-criteria change. Authority: the existing user request to complete Story17.1 and workspace autonomy/no-Epic16-dependency requirements. Independent interface review approved the corrected direction; no separate product-scope approval is represented as obtained.

## 1. Trigger and evidence

The initial dedicated snapshot table was added to shared models/tables.py and global Alembic revision043. Full localCI exposed65 operator-recovery errors and4 qualification/preflight failures: the released recovery profile requires core revision042 and the shared model/database sources are qualification-bound. Updating qualification hashes or weakening recovery would create precisely the prohibited cross-epic dependency. Log: `/tmp/story17-1-ci.log` (to be retained under the failed-approach suffix before final rerun).

Released source hashes: models/database.py c6f7720843eab0354a7eb1e525b43de8995f90c9c9f6080982fccdc33d254000; models/tables.py e9fbc075b8ab25713e8deeaadf57e2dd31aebc73afacd1e02bffb58a26d26e18. These must remain byte-identical.

## 2. Impact analysis

Epic17 scope, priority, sequence and Story17.1 AC1–7 remain unchanged. Epic16 code, tests, qualification evidence and released migration history remain untouched. No PRD/MVP or UI/UX changes are needed. Architecture§26.5 and the implementation record clarify independent cloud schema ownership. CI/package registration and source Literal additions remain additive.

## 3. Selected approach

- Move the snapshot ORM class into models/cloud_snapshots.py with its own declarative registry/metadata and a direct Column FK to the released Project table. No relationship/backref or core metadata mutation.
- Move cloud DDL, immutable guards and strict validation into an independent cloud schema namespace, version1 recorded in an existing AppSetting metadata key. No global Alembic revision43; core head remains042.
- Initialize schema atomically inside the checked server UOW on explicit enabled configuration, before provider construction. Default-off analysis/startup initializes no cloud tables. Existing/missing schema/version markers must agree; partial/unknown schemas fail explicitly. Reads of a never-initialized store return missing; mutation/admission cannot pretend readiness.
- Keep all validated properties: WITHOUT ROWID, same-key INSERT/REPLACE refusal, one-way expiry tombstones, actual-clock/report-reference guards, project-FK cascade/config cleanup, canonical redaction/digest validation and atomic evidence publication.
- Restore only this task's shared core-file and head-expectation edits. Preserve CI/Docker/module packaging changes and all newly added security regressions.

Rejected: refreshing Epic16 qualification hashes without executing its real qualification; changing frozen recovery code; skipping failing baseline tests. A second database/file store is unnecessary and complicates atomic report references.

Effort: bounded model/schema move and fixture update, followed by one fresh validation pass. Risk: moderate schema lifecycle change, reduced shared-runtime surface. No dependencies or provider SDKs added. Timeline: additional implementation/verification work; no release scheduling change.

## 4. Concrete edit proposals

Architecture§26.5 OLD: current-slice entities are migrated, without namespace detail. NEW: cloud snapshot schema has its own validated version/metadata namespace and explicit opt-in initialization; core schema head and qualified model sources remain unchanged.

Implementation plan packet1.4 OLD: global043 + shared ORM/bootstrap edits. NEW: separate model registry and cloud-owned initializer/version marker, retaining the same snapshot/service/evidence interfaces.

Story acceptance text and PRD requirements: unchanged. Story Dev Agent Record/File List will record the changed persistence paths, failed-approach evidence and final tests. UI/UX: N/A.

## 5. Handoff and success criteria

Developer storage owner performs the move and preserves every immutable/retention regression. Service owner initializes/checks the independent schema within the existing authorization port. Test owner updates only new cloud fixtures; old head expectations return to released values. Root updates documentation, packaging checks and final validation.

Success: released models/database.py and models/tables.py hashes exact; core Alembic head042; no new imports from the other epic; default-off baseline suites pass; new cloud/evidence/storage/service tests and import/network isolation pass; actual Docker runtime imports the new package without provider SDKs and boots the unchanged core with cloud disabled.

## Change checklist

- [x]1.1–1.3 Story/technical trigger/evidence identified.
- [x]2.1–2.5 Epic remains feasible; no new/reordered epic or story.
- [x]3.1 PRD unchanged; implementation restored to its independence requirement.
- [x]3.2 Architecture namespace clarification identified.
- [N/A]3.3 No UI/UX change.
- [x]3.4 CI/docs/packaging impacts recorded.
- [x]4.1 Direct adjustment selected; moderate technical risk, bounded effort.
- [N/A]4.2 No completed story rollback; only uncommitted failed implementation edits are replaced.
- [N/A]4.3 No MVP reduction or new goals.
- [x]4.4 Rationale and alternatives recorded.
- [x]5.1–5.5 Proposal/impact/approach/handoff defined.
- [x]6.1–6.2 Proposal independently reviewed for technical feasibility.
- [N/A]6.3 No new product/privilege/irreversible decision: existing task authorization applies to this minor implementation correction. No new approval is fabricated.
- [N/A]6.4 No backlog restructuring.
- [x]6.5 Developer handoff and concrete validation criteria established.

## Implementation completion

The minor correction is implemented and independently re-reviewed. All120focused tests/121subtests,84isolation tests,2,224root tests,3,723localCI tests and the exact API/CLI/infra shard passed. Runtime Docker proves Python3.11/non-root/noSDK/noNode, explicit reference enablement and unchanged core restart. Released core source hashes and migration head remain unchanged. Story17.1 is ready for code review; no product scope or privilege changes were introduced.
