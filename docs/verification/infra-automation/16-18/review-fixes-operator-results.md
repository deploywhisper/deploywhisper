# Final review-fix operator exercise

Passed on **2026-11-10**, using final production image
`sha256:2c652ba689e6c6d6e02d7be7dc054ea4cbc093c46bb87341846824acc1a5c3e8`.
This was a local agent exercise against disposable synthetic state, not an
independent human self-service or production-profile pilot.

The structured [record](review-fixes-operator-results.json) retains 31 named
checks, exact commands, nonsecret initialization journals and digests, resource
identities, source witnesses and cleanup verification.

## Runtime and isolation

- Python **3.11.17**, Linux ARM64/LinuxKit 6.12.54,
  Docker **29.1.3**, nonroot application image user.
- Real migrations initialized fresh schema **042**. All **209** packaged runtime
  source hashes matched the current host before the exercise and again afterward.
  Operator recovery source SHA-256:
  `5baba5a96e1c4e6d07a534b0a56c7a87dd3e9a1a79b223bc56ae391f4ad67fbd`.
- Unique container and four named volumes separated domain, outside ledger,
  backups and private operator files. Every container used `--network none`.
  API requests used Docker exec and the container's own
  `http://localhost:8080` loopback. There were **no host ports or host mounts**;
  the original application and host port8080 were not touched.

## Actual initialization interruption and resume

The production CLI entrypoint ran twice with process-local standard-library
fault wrappers. The first injected an I/O exception after the complete intent
was durably published but before database binding; it returned1 and retained
`initializing`, with zero database-binding rows. The second retried initialization
and injected an I/O exception after the binding transaction committed but before
publishing ledger `ready`; it returned1 and retained the exact same intent,
installation identity, generation and lifecycle-lock inode. The database binding
matched that intent exactly.

Unpatched `python -m cli.automation_operations ... resume` then reached `ready`
using the same identity and lock. A second resume returned the exact ready result.
The actual nonsecret initializing journal, its digest, database identity and
observed lock inode are retained in the JSON checks. These are controlled
exception-boundary exercises, not process-kill or host-power-loss qualification.
No production source or on-disk marker was edited to create the interruption.

## Actual normal CLI/API path

| Exercise | Result |
| --- | --- |
| Private one-use CLI setup/bootstrap; explicit project-membership bootstrap | Passed; project administration required a real authenticated membership |
| Typed settings read and audited disabled-policy save | HTTP200 |
| CLI account-recovery/password rotation | Old session401; new login200; live SQLite/WAL descriptors remained valid |
| Backup while application holds shared lifecycle lock | CLI exit1 |
| Stop application and capture coordinated database/artifact/custody backup | CLI exit0 |
| First offline restore | Generation4; `reconciliation_required` |
| Old SID after restore / fresh login | HTTP401 /200 |
| Retained run and audit reads | HTTP200; empty run history, one actual policy audit with identical digest |
| Re-enable before completing recovery | HTTP503 |
| Fresh global/project administrator completes recovery through private CLI | `ready`; no replacement approval or external operation |
| Restart after completion | Policy remains disabled; fresh post-restore session remains valid |
| Restore identical backup again | Generation5; previous ready-session401; fresh login200 |
| Final schema/integrity/foreign keys | 042 /`ok` /0 violations |
| Synthetic custody bytes | Original digest retained |

The second restore intentionally ends in `reconciliation_required`; its disposable
resources are removed. Repeated restore advances generation without reviving the
previous ready session. No receiver operation was fabricated. R4's purge/older-
backup refusal belongs to the separate real Alembic042 regression tests and is
not claimed as a live-history exercise here.

## Commands and cleanup

```text
python3 /tmp/dw16-18-review-fixes-operator.py sha256:2c652ba689e6c6d6e02d7be7dc054ea4cbc093c46bb87341846824acc1a5c3e8
# exit0; 31 named checks; cleanup_complete=true
```

The understood temporary harness reused the earlier operator/offline loopback
helpers. Its complete command inventory and harness/log SHA-256 are retained in
the structured record. Passwords, one-use credentials, session cookies and CSRF
values traveled through stdin or mode0600 files inside the private operator
volume and are excluded from evidence.

All five owned resources (application container and four volumes) were removed;
separate Docker inspect calls confirmed each absent. No host credential file,
repository `.env` or application data was read or mounted. No product source,
dependency, external account or public artifact was changed by this exercise.
The mandatory independent human pilot and broader release/support qualification
remain open; this finite smoke is not a replacement for those gates or for the
separate capacity record.
