# PR 222 CodeQL repair

CodeQL alert [127](https://github.com/deploywhisper/deploywhisper/security/code-scanning/127) reported `py/redos` in the SQL transaction guard. Repeated comment alternatives allowed exponential backtracking before a non-commit statement. The new isolated-process regression timed out after 10 seconds against the old matcher.

The guard now advances one cursor through whitespace, semicolons, BOMs and SQLite comments. Each block/line comment search starts after the preceding consumed token; no suffix is repeatedly rescanned. A fixed COMMIT/END keyword expression checks only the first remaining token. Commit ownership, caught-attempt invalidation and rollback checks are unchanged.

New regressions cover the reported 10,000-fragment comment input before SELECT, long prefixes before END, mixed BOM/semicolon/comment/CRLF prefixes, comment-only statements, unterminated comments and commit words inside comments/string literals. The hostile SELECT regression runs in a subprocess with a ten-second deadline so a recurrence cannot hang the suite.

Validation before push:

- Focused cloud/evidence/storage/service/migration pytest suite: **127 tests and 145 subtests passed** (`/tmp/pr222-codeql-focused.log`).
- SDK/network isolation: **90 tests passed** (`/tmp/pr222-codeql-isolation.log`).
- Repo-wide `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`: passed (671 files).
- Scoped mypy and high-severity/high-confidence Bandit on `services/cloud_context_service.py`: passed (no Bandit issues).
- Independent reviewer reran actual admission with crafted 40,005-character comment prefixes, mixed prefixes, first block-comment closure and lone-CR/unterminated comment cases; no remaining issue found. SELECT returned normally; END was rejected with zero durable reports.
- Existing full local CI/root/exact-shard qualification is preserved in `review-fixes-2026-11-16.json`. A fresh root smoke is also being executed for this follow-up; remote CodeQL must confirm alert closure for the pushed revision.

Only the transaction-prefix matcher, its admission regressions and story/evidence documentation change. No dependencies, schemas or public interfaces change. UI validation not applicable.
