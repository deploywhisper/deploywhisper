---
name: ansible
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [.yml, .yaml]
token_budget: 1600
tags: [ansible, automation, iac]
description: Deep Ansible operational knowledge covering dangerous module classification, idempotency violations, inventory targeting risks, privilege escalation patterns, and handler ordering pitfalls.
test_suite_path: tests/skill-tests/ansible
trigger_content_patterns: [hosts, tasks, roles, become, ansible, playbook, handlers]
---

## Dangerous module classification

### Destructive modules (CRITICAL)
- `file` with `state: absent` — deletes files or entire directory trees; recursive deletion on wrong path is catastrophic
- `user` with `state: absent` and `remove: true` — deletes user account AND home directory with all data
- `mysql_db` / `postgresql_db` with `state: absent` — drops the database; irreversible without backup
- `ec2_instance` / `gce_instance` with `state: absent` — terminates cloud instances
- `docker_container` with `state: absent` and `keep_volumes: false` — destroys container AND its data volumes
- `k8s` with `state: absent` — deletes Kubernetes resources; can cascade through owner references

### Non-idempotent modules (HIGH)
- `command` — executes arbitrary shell commands; has no built-in idempotency; runs every time regardless of current state
- `shell` — same as command but through a shell interpreter; even more dangerous because of pipe/redirect side effects
- `raw` — sends raw commands over SSH without module wrapper; no change detection, no error handling, no idempotency
- `script` — uploads and executes a local script on remote host; runs every time, no state check
- `expect` — automates interactive commands; inherently non-idempotent and fragile

### Sensitive modules (HIGH)
- `copy` with `content` parameter containing secrets — secrets end up in Ansible logs, facts cache, and potentially in version control
- `template` rendering credential files — verify `mode: '0600'` and `owner` are set; world-readable credential files are a common oversight
- `lineinfile` / `blockinfile` — modifies files in place; repeated runs with wrong `regexp` can duplicate lines or corrupt config files
- `cron` — installs cron jobs; missing `name` parameter causes duplicate entries on every run
- `authorized_key` with `exclusive: true` — removes ALL other SSH keys for the user; can lock out other admins

### Safe modules (LOW risk when used correctly)
- `apt` / `yum` / `dnf` with `state: present` — idempotent package installation
- `service` / `systemd` with `state: started/stopped` — idempotent service management
- `file` with `state: directory` or `state: file` — idempotent file/directory creation
- `template` / `copy` with `backup: yes` — creates backup before overwriting

## Idempotency violations

### Common anti-patterns
- `command` or `shell` without `creates` or `removes` guards — runs every time; use `creates: /path/to/output` to skip if file already exists
- `command` or `shell` without `changed_when` — always reports "changed" even if the command was a no-op; misleads operators about actual system state
- `shell: "echo 'line' >> /etc/config"` — appends the line on EVERY run; use `lineinfile` instead for idempotent file editing
- Task using `register` result but no conditional on next task — downstream tasks always execute regardless of whether the registered command did anything
- `when: result.rc == 0` after a `command` that always succeeds — the conditional provides no useful gating

### Missing guard patterns
- Tasks that should use `when: ansible_facts['os_family'] == 'Debian'` but apply universally — OS-specific commands break on wrong distribution
- Package installation without version pinning — `apt: name=nginx` installs whatever the latest version is; use `name=nginx=1.24.0-1` for deterministic deployments
- Tasks that check `stat` for file existence but don't use `register` + `when` to gate subsequent steps

## Inventory targeting risks

### Production targeting (CRITICAL)
- Play with `hosts: all` = CRITICAL — targets every host in the inventory; in mixed environments this includes production, staging, dev, and infrastructure hosts simultaneously
- Play targeting production group without `--limit` in CI/CD = HIGH — no guardrail against running on all production servers
- Play targeting parent group that contains production subgroup = HIGH — `hosts: webservers` may include `prod-webservers` and `staging-webservers`
- `serial: 100%` or no `serial` on production group = HIGH — all hosts process simultaneously; a bad task takes down every server at once
- Missing `max_fail_percentage` — one host failure doesn't stop the play from destroying remaining hosts

### Safe targeting patterns
- `serial: 1` or `serial: "25%"` for production — processes hosts in batches; limits blast radius of a bad change
- `max_fail_percentage: 10` — stops the play if more than 10% of hosts fail; prevents cascading failure
- `any_errors_fatal: true` for critical tasks — stops ALL hosts on the first error anywhere
- `run_once: true` for tasks that should only execute on one host (database migrations, cluster operations)

## Privilege escalation patterns

### Dangerous escalation (HIGH)
- `become: true` at play level without `become_user` — escalates to root for EVERY task in the play, including tasks that don't need root
- Tasks modifying `/etc/sudoers` or `/etc/sudoers.d/` — syntax error in sudoers file locks out ALL sudo access; always use `visudo --check` or `validate` parameter
- Tasks modifying PAM configuration (`/etc/pam.d/`) — misconfiguration can lock out all logins, including SSH
- Tasks modifying SSH configuration (`/etc/ssh/sshd_config`) without `validate: 'sshd -t -f %s'` — syntax error locks out SSH access permanently on next restart
- Tasks modifying firewall rules (`iptables`, `ufw`, `firewalld`) without ensuring SSH port remains open — can lock out Ansible itself

### Best practices
- Use `become: true` at task level, not play level — only escalate when needed
- Always use `validate` parameter on critical config files: `validate: 'nginx -t -c %s'`, `validate: 'sshd -t -f %s'`, `validate: 'visudo -cf %s'`
- Use `backup: yes` on critical file modifications — creates timestamped backup before overwriting

## Variable precedence risks

### Precedence conflicts (MEDIUM)
- `extra-vars` (-e) always win over everything — can silently override role defaults, group_vars, and host_vars without warning
- `group_vars/all` overriding role defaults unexpectedly — role developers expect their defaults to apply unless explicitly overridden
- Multiple group memberships causing variable merging conflicts — host in both `webservers` and `production` groups may get conflicting variable values depending on group file ordering
- `set_fact` overriding variables mid-play — subsequent tasks get the new value, but handlers still see the original value
- `include_vars` with `hash_behaviour: merge` vs `replace` — merge combines dictionaries, replace overwrites entirely; default is replace, which can lose nested keys

### Variable safety
- Sensitive variables (`passwords`, `api_keys`, `tokens`) should be in `ansible-vault` encrypted files, not plain text group_vars
- Variables with `no_log: true` on tasks that handle secrets — prevents secret values from appearing in Ansible output and logs
- `default()` filter on optional variables — prevents `undefined variable` errors from crashing the play

## Handler ordering risks

### Handler pitfalls (MEDIUM)
- Handlers execute in DEFINITION order, not notification order — if handler A is defined after handler B but notified first, B still runs before A
- Multiple tasks notifying the same handler — handler runs only ONCE at the end of the block, not once per notification; this is usually desired but can surprise operators
- `flush_handlers` in the middle of a play — forces all pending handlers to execute immediately; if a handler fails, subsequent tasks in the play still run (handlers don't block play execution by default)
- Handler that restarts a service while a health check task follows immediately — the service may not be ready when the health check runs; add a `wait_for` task after flush
- Handlers in included roles — handler names must be globally unique across all roles; duplicate names cause only one handler to execute

### Block error handling
- `rescue` block only catches task failures, not handler failures — a failing handler in a `block` is NOT caught by `rescue`
- `always` block runs regardless of task or rescue outcome — use for cleanup that must happen (remove temp files, restore config)
- Nested blocks with error handling — inner rescue can mask errors from outer block; keep nesting shallow

## Ansible-specific failure modes

- SSH connection timeout on large inventories — default `forks: 5` means only 5 hosts processed in parallel; increase for large inventories but watch for connection storms
- `gather_facts: true` (default) adds 5-15 seconds per host — disable with `gather_facts: false` when facts aren't needed; use `setup` module selectively for specific fact subsets
- Ansible control node running out of memory on very large inventories (>1000 hosts) — each host fork uses 50-100MB; limit forks or use `mitogen` strategy for lower memory footprint
- Python version mismatch between control node and target — Ansible requires Python on target hosts; Python 2 EOL means some modules behave differently on legacy hosts
- `ansible.cfg` in current directory overriding system config — CI/CD runners may pick up unexpected config from repo checkout
