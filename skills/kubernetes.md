---
name: kubernetes
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [.yaml, .yml]
token_budget: 1800
tags: [kubernetes, containers, orchestration]
description: Deep Kubernetes operational knowledge covering workload safety, rolling update risks, RBAC escalation, network policy gaps, and resource management pitfalls.
test_suite_path: tests/skill-tests/kubernetes
trigger_content_patterns: [apiVersion, kind, metadata, spec.containers, spec.replicas]
---

## Critical risk patterns

### Workload security (CRITICAL)
- Container running as root (`securityContext.runAsUser: 0` or missing `runAsNonRoot: true`) = CRITICAL — container escape vulnerabilities grant host-level access
- Privileged container (`securityContext.privileged: true`) = CRITICAL — full access to host kernel, devices, and network stack; equivalent to root on the node
- `hostNetwork: true` = CRITICAL — container shares the node's network namespace; can intercept traffic from other pods on the same node
- `hostPID: true` or `hostIPC: true` = HIGH — container can see and signal all processes on the host node
- Missing `securityContext.readOnlyRootFilesystem: true` = MEDIUM — writable filesystem increases attack surface for malware persistence
- Container image with `latest` tag = HIGH — non-deterministic deployments; the same manifest can produce different containers on different nodes
- Container image from untrusted registry (not your private ECR/GCR/ACR) = HIGH — supply chain attack vector
- Image without digest pinning (using tag instead of `image@sha256:...`) = MEDIUM — tag can be overwritten in the registry

### Missing resource controls (HIGH)
- No `resources.limits.memory` set = HIGH — a single pod can consume all node memory and trigger OOM kills on other pods via the kernel OOM killer
- No `resources.limits.cpu` set = MEDIUM — pod can starve other workloads of CPU; less severe than memory because CPU is compressible
- No `resources.requests` set = HIGH — scheduler cannot make informed placement decisions; pods may land on overcommitted nodes
- `resources.requests` much lower than `resources.limits` (>4x ratio) = MEDIUM — indicates over-commitment; the pod claims little but uses a lot, causing node pressure
- `resources.limits.memory` lower than application baseline = HIGH — pod will be OOM-killed repeatedly, causing CrashLoopBackOff

### Replica and availability risks (HIGH)
- `spec.replicas: 1` in production = HIGH — single point of failure; any pod disruption causes full outage
- `spec.replicas` reduced from current value = MEDIUM — capacity reduction during a change is risky; validate that remaining capacity handles peak load
- No `PodDisruptionBudget` for production workloads = HIGH — voluntary disruptions (node drains, cluster upgrades) can evict all pods simultaneously
- PDB with `maxUnavailable: 100%` or `minAvailable: 0` = CRITICAL — defeats the purpose of the PDB; all pods can be evicted at once

## Rolling update risks

### Deployment strategy
- `strategy.rollingUpdate.maxUnavailable` set too high (>25%) = HIGH — too many pods terminate before replacements are ready; causes capacity dip during rollout
- `strategy.rollingUpdate.maxSurge: 0` with `maxUnavailable: 0` = CRITICAL — deadlock; Kubernetes cannot create new pods or remove old ones
- `strategy.type: Recreate` in production = CRITICAL — all old pods are killed before new pods start; guarantees downtime during deployment
- Missing `minReadySeconds` = MEDIUM — new pods are considered ready immediately; a pod that passes readiness probe once but fails under load will still receive traffic

### Probe configuration
- No `readinessProbe` defined = CRITICAL — Kubernetes sends traffic to pods that may not be ready to serve; causes errors during rollout and after restarts
- No `livenessProbe` defined = MEDIUM — stuck/deadlocked pods are never restarted; process is running but not functional
- `livenessProbe` with aggressive timing (`periodSeconds < 5`, `failureThreshold < 3`) = HIGH — healthy but briefly slow pods get killed unnecessarily, causing restart loops
- `livenessProbe` and `readinessProbe` pointing to the same endpoint with same thresholds = MEDIUM — when the service is degraded, you want it removed from load balancer (readiness) but not killed (liveness); same config means degraded = killed
- `startupProbe` missing on slow-starting applications = HIGH — liveness probe kills the pod before the application finishes initialization
- `initialDelaySeconds` too short for applications with long startup (JVM, .NET, ML model loading) = HIGH — pod killed during warmup

### Image and container changes
- Image tag change (e.g., `v2.14.1` → `v2.15.0`) = MEDIUM-HIGH — new code rolling into production; risk scales with change magnitude
- Base image change (e.g., `node:18-alpine` → `node:20-alpine`) = HIGH — runtime version change can introduce subtle behavior differences
- `imagePullPolicy: Never` with a tag (not digest) = HIGH — uses whatever image is cached on the node; different nodes may run different versions
- `imagePullPolicy: Always` with `latest` tag = CRITICAL — every pod restart pulls whatever is currently tagged latest; non-deterministic

## RBAC and access control

### Role escalation risks
- `ClusterRole` with `verbs: ["*"]` on any resource = CRITICAL — wildcard permissions grant full control
- `ClusterRole` with `resources: ["*"]` = CRITICAL — applies to every resource type in the cluster
- `ClusterRoleBinding` granting cluster-admin to a ServiceAccount used by a workload = CRITICAL — compromised pod gets full cluster access
- New `RoleBinding` or `ClusterRoleBinding` creation = HIGH — always review who/what is getting access and to what resources
- ServiceAccount with `automountServiceAccountToken: true` (default) in pods that don't need API access = MEDIUM — unnecessary credential exposure

### Secret management
- `Secret` data changed = HIGH — verify the secret content is correct; wrong database password or API key causes runtime failures across all pods mounting the secret
- `Secret` referenced in environment variables instead of volume mounts = MEDIUM — environment variables appear in process listings, crash dumps, and log output
- `ConfigMap` change that is mounted as a volume = MEDIUM — existing pods see the change after kubelet sync delay (60-90 seconds by default); no restart needed but timing is unpredictable
- `ConfigMap` change referenced via `envFrom` = HIGH — requires pod restart to pick up changes; running pods continue with old values until restarted

## Network policy risks

- Production namespace without any `NetworkPolicy` = HIGH — all pods can communicate with all other pods in the cluster; no microsegmentation
- `NetworkPolicy` with empty `ingress` or `egress` rules = MEDIUM — blocks all traffic in that direction; can isolate pods unintentionally
- `NetworkPolicy` with `podSelector: {}` (empty selector) = note — selects ALL pods in the namespace; verify this is intentional
- Removing a `NetworkPolicy` = HIGH — instantly opens traffic that was previously restricted
- `NetworkPolicy` referencing a label that no pod currently has = MEDIUM — policy exists but has no effect; may indicate a misconfiguration

## Resource management pitfalls

### HPA and scaling
- `HorizontalPodAutoscaler` targeting the same deployment as a manual `replicas` field = CRITICAL — HPA and manual replica count fight each other; HPA overwrites manual changes
- HPA `minReplicas: 1` in production = HIGH — autoscaler can scale down to single instance, creating a SPOF
- HPA `maxReplicas` too high without corresponding node capacity = MEDIUM — pods will be stuck in Pending if cluster autoscaler can't provision nodes fast enough
- HPA `targetCPUUtilizationPercentage` too low (<30%) = MEDIUM — wasteful over-provisioning; too high (>80%) = HIGH — insufficient headroom for traffic spikes, pods may become unresponsive before new ones are ready
- VPA and HPA targeting the same resource on CPU = CRITICAL — conflicting recommendations cause flapping

### Storage
- `PersistentVolumeClaim` access mode change = HIGH — may require PV recreation, causing data access interruption
- `PersistentVolume` reclaim policy `Delete` on production data = CRITICAL — volume and data destroyed when PVC is deleted
- `StorageClass` change on existing PVC = not supported — requires PVC recreation and data migration
- `emptyDir` used for data that must survive pod restarts = HIGH — data is lost when pod is evicted, rescheduled, or OOM-killed

## Namespace and context

- Changes targeting `kube-system` namespace = CRITICAL — core cluster components; mistakes here affect the entire cluster
- Changes targeting `default` namespace in production = MEDIUM — indicates poor namespace hygiene; production workloads should have dedicated namespaces
- Resource quotas or limit ranges being reduced = HIGH — may cause existing pods to exceed new limits; new pods may fail to schedule
- Namespace deletion = CRITICAL — destroys all resources in the namespace including persistent volume claims (data loss)
