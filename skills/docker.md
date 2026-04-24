---
name: docker
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [Dockerfile, dockerfile, .dockerfile, docker-compose.yml, docker-compose.yaml, compose.yml, compose.yaml]
token_budget: 1200
tags: [docker, containers, supply-chain]
description: Container image and build risk knowledge covering Dockerfile security patterns, image provenance, multi-stage build risks, compose file analysis, and runtime container security.
test_suite_path: tests/skill-tests/docker
---

## Dockerfile risk patterns

### Running as root (CRITICAL)
- No `USER` instruction in the Dockerfile = CRITICAL — container runs as root by default; if the container is compromised, the attacker has root-level access within the container and potentially the host (with certain volume mounts or kernel exploits)
- `USER root` set after a non-root USER instruction = HIGH — reverts to root for subsequent layers; common mistake when installing system packages late in the build
- `USER` instruction only in intermediate build stage, not in final runtime stage = CRITICAL — multi-stage build where the builder runs as non-root but the final image runs as root

### Dangerous instructions (HIGH)
- `COPY . .` or `ADD . .` without `.dockerignore` = HIGH — copies EVERYTHING from the build context including `.git/`, `.env`, `node_modules/`, credentials files, and local development configs into the image
- `ADD` with remote URL = HIGH — downloads and extracts files from the internet at build time; URL content can change between builds (non-deterministic); use `COPY` + explicit `curl`/`wget` with checksum verification instead
- `RUN chmod 777` on any directory = HIGH — world-writable directories inside the container; any process can modify files
- `RUN apt-get install -y` without `--no-install-recommends` = MEDIUM — installs unnecessary recommended packages, increasing image size and attack surface
- `RUN curl | sh` or `RUN wget -O - | sh` = CRITICAL — executes remote scripts without verification; classic supply chain attack vector; download, verify checksum, then execute as separate steps
- `ENV` with secret values (passwords, tokens, API keys) = CRITICAL — environment variables are baked into the image layer metadata; anyone with image access can extract them with `docker inspect` or `docker history`

### Unpinned dependencies (HIGH)
- Base image with `latest` tag: `FROM node:latest` = HIGH — image content changes without notice; builds are non-reproducible; a base image update can break the application silently
- Base image with major version only: `FROM python:3` = MEDIUM — resolves to latest 3.x minor and patch; `FROM python:3.11.9-slim-bookworm` is deterministic
- Base image without digest: prefer `FROM python:3.11.9@sha256:abc123...` = MEDIUM — even pinned tags can be overwritten in registries; digest pinning guarantees exact image content
- `RUN pip install package` without version pin = MEDIUM — installs latest version at build time; breaks when package releases a backward-incompatible update
- `RUN npm install` without `package-lock.json` copied first = MEDIUM — dependency resolution is non-deterministic without lockfile; different builds may get different dependency versions
- `RUN apt-get update && apt-get install -y package` without version pin = LOW-MEDIUM — acceptable for system packages but note that builds are not perfectly reproducible

### Layer optimization (LOW-MEDIUM)
- Separate `RUN apt-get update` and `RUN apt-get install` = MEDIUM — if the install layer is cached but update is not, the cache uses a stale package index; always combine: `RUN apt-get update && apt-get install -y ... && rm -rf /var/lib/apt/lists/*`
- Package manager cache not cleaned in the same RUN instruction = LOW — increases image size unnecessarily; cache files persist in the layer
- `COPY` of large directories before `COPY` of dependency lockfiles = MEDIUM — invalidates Docker layer cache on every source code change; copy lockfiles first, install dependencies, then copy source code
- More than 15 layers in the final image = LOW — excessive layers increase pull time and storage; combine related RUN instructions

## Image provenance

### Registry trust (HIGH)
- Image from Docker Hub without official or verified publisher status = MEDIUM — community images may contain malware, crypto miners, or backdoors; prefer official images or your organization's private registry
- Image from a public registry not in the organization's approved list = HIGH — supply chain risk; all base images should come from a curated allowlist
- Image without a vulnerability scan report = MEDIUM — use `docker scout`, `trivy`, or `grype` to scan before deployment
- Image with known CRITICAL CVEs in scan results = HIGH — vulnerabilities in base image or installed packages

### Image signing and verification
- Images not signed with Docker Content Trust or Cosign/Sigstore = MEDIUM — no guarantee the image wasn't tampered with between build and deployment
- Image pulled by tag (not digest) in production K8s manifests = MEDIUM — tag can be overwritten in the registry; use `image@sha256:...` for immutable references
- Multi-arch image used without specifying platform = LOW — Docker selects the platform automatically, but behavior may vary between build environments (CI vs local development)

## Multi-stage build risks

### Secret leakage between stages (CRITICAL)
- `COPY --from=builder /app/.env /app/.env` = CRITICAL — copies secrets from build stage into runtime image; secrets that should only exist during build (npm tokens, pip credentials) end up in the final image
- Build arguments (`ARG`) with secret values without using `--mount=type=secret` = HIGH — ARG values are visible in image layer metadata; use BuildKit secrets mount: `RUN --mount=type=secret,id=npm,target=/root/.npmrc npm install`
- `COPY --from=builder /root/.aws /root/.aws` = CRITICAL — AWS credentials from builder stage leaked into runtime image

### Stage dependency issues
- Final stage `COPY --from=builder` missing critical runtime files = causes runtime failure (not a security risk but a reliability risk)
- Final stage inheriting a different base image than expected — `FROM node:slim` (runtime) vs `FROM node:latest` (build); native dependencies compiled in build stage may not work on slim runtime (missing shared libraries)
- Build stage with `RUN npm run build` but missing build artifacts in COPY = build succeeds but deployed image is broken

## Docker Compose analysis

### Security risks in Compose (HIGH)
- `privileged: true` on any service = CRITICAL — container gets full access to host kernel; equivalent to running as root on the host machine
- `network_mode: host` = HIGH — container shares the host's network namespace; can bind to any host port and see all network traffic
- `pid: host` = HIGH — container can see all host processes; combined with `privileged`, allows container escape
- `volumes` mounting sensitive host paths:
  - `/var/run/docker.sock:/var/run/docker.sock` = CRITICAL — container can control the Docker daemon; can spawn new privileged containers, access any volume, and effectively has root on the host
  - `/etc/shadow`, `/etc/passwd` = CRITICAL — host authentication files exposed
  - `/` or `/root` = CRITICAL — entire host filesystem or root home directory accessible
  - `/var/log` = MEDIUM — host logs may contain sensitive information
- `cap_add: [SYS_ADMIN]` or `cap_add: [ALL]` = HIGH — Linux capabilities that approach root-level access

### Configuration risks (MEDIUM)
- `restart: always` without health check = MEDIUM — container restarts indefinitely even if the application is broken; combine with `healthcheck` to prevent restart loops
- `ports` exposing database or cache ports to the host (3306, 5432, 6379, 27017) = HIGH — database accessible from the host network; should use internal Docker networking only
- `environment` section with inline secrets instead of `secrets` or `.env` file reference = HIGH — secrets visible in `docker compose config` output and in the compose file in version control
- Missing `mem_limit` or `deploy.resources.limits.memory` = MEDIUM — container can consume all host memory; always set memory limits in production
- `depends_on` without `condition: service_healthy` = MEDIUM — dependent service starts before dependency is ready; only checks that the container started, not that the application inside is healthy

### Networking risks
- Services on the default bridge network in production = MEDIUM — all containers can communicate with each other; use custom networks to isolate services
- `expose` without corresponding `ports` = informational — container port is documented but not published to host; not a risk, but verify it's intentional
- Multiple services binding to the same host port = will fail at startup — `ports: "8080:80"` on two services causes port conflict; use different host ports or a reverse proxy

## Runtime container security

### Volume and data risks
- Named volume removed from compose file = HIGH — data in the volume persists on the host but is no longer managed by compose; orphaned data
- Anonymous volumes (no name specified) = MEDIUM — data is lost when the container is recreated; not suitable for persistent data
- `tmpfs` mount for `/tmp` = positive — prevents temporary file persistence; good security practice
- Volume mount with `:rw` (default) when `:ro` would suffice = LOW — principle of least privilege; read-only mounts reduce the risk of container writing to host filesystem

### Container lifecycle
- `stop_grace_period` too short (< 10s) for services with in-flight requests = MEDIUM — application may not finish processing requests before SIGKILL; default 10s is usually sufficient but increase for long-running operations
- No `logging` driver configuration = LOW — defaults to `json-file` which can fill disk; configure `max-size` and `max-file` options or use a centralized logging driver
- `init: true` not set for services that spawn child processes = MEDIUM — zombie processes accumulate; `init: true` adds a tiny init system that reaps child processes properly

## Dockerfile change risk assessment

| Change type | Risk level | Rationale |
|---|---|---|
| Base image tag change | HIGH | New OS, new packages, new vulnerabilities, potential breaking changes |
| Base image digest change | MEDIUM | Controlled update, but content changes |
| USER instruction added/changed | HIGH | Affects permission model for all subsequent instructions |
| EXPOSE port change | MEDIUM | May require corresponding K8s service/ingress update |
| COPY/ADD source path change | MEDIUM | Different files included in image |
| RUN with package install | MEDIUM | New dependencies, new attack surface |
| ENV change | LOW-HIGH | Depends on variable (PORT vs SECRET) |
| ENTRYPOINT/CMD change | HIGH | Changes how the container starts; wrong entrypoint = broken container |
| HEALTHCHECK change | MEDIUM | Affects readiness detection in orchestrators |
| .dockerignore change | MEDIUM | Affects what enters the build context |
