# WP4 real-tool containment prerequisite

Responsible contributor: Codex. Observation: 2026-10-09.
Status: **blocked before execution**. No containment case passed.

The selected profile remains a disposable non-root Linux sandbox with
preinstalled pinned OpenTofu/Terraform and provider catalog, controlled local
dependencies, distinct collector/receiver identities and no real credentials.
The current host is Darwin. Docker CLI 29.1.3 is present, but the read-only
image-inventory command exited 1 because its daemon is unavailable. Neither
`tofu` nor `terraform` resolves on PATH. No approved immutable image,
tool/provider pins or source/profile manifest has been supplied for this
qualification. A working Docker daemon alone would not resolve those gaps.

Executed read-only commands:

```sh
/usr/local/bin/docker --version
docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}' > /private/tmp/story16-docker-inventory.txt 2>&1
```

The version command exited 0. Image enumeration exited 1. PATH and platform
checks used Python `shutil.which` and `platform.system`; their sanitized
results are in [wp4-containment-results.json](wp4-containment-results.json).
The diagnostic log stays private; it contains no qualification outputs and
is not part of the committed packet. No image download, dependency/tool
installation, profile substitution or infrastructure mutation was performed.

## Required operator prerequisite

Provide the approved Linux sandbox profile and immutable image/tool/provider
catalog pins, with tools already installed, synthetic no-cloud source and
controlled offline/local dependencies. Then execute the story's actual-tool
plan/provider probes and all hostile-path, Git-config, environment, egress,
resource, disk/output and descendant-process tests. Record UID/capabilities,
mounts, seccomp/network policy, separate identities and source/image/tool/
provider digests. Keep plan/state and raw logs in protected private custody.

No fake binary or host Python subprocess qualifies this gate. WP5's synthetic
receiver tests may establish protocol mechanics; they cannot establish AC6's
real immutable binary-plan custody, OS identity separation or storage policy.
IR-02 and the complete WP4/WP5 acceptance gates therefore remain open.
