"""Unified risk scoring logic."""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from typing import Any, Literal

from pydantic import BaseModel, Field

from analysis.interaction_risk import InteractionRisk, detect_interaction_risks
from evidence.models import ContextCompleteness
from llm.providers import generate_completion_with_settings
from parsers.base import (
    NON_MUTATING_ACTIONS,
    ParseBatchResult,
    UnifiedChange,
    normalize_change_action,
)
from services.settings_service import resolve_provider_runtime
from services.topology_service import STALE_AFTER_DAYS

RiskSeverity = Literal["low", "medium", "high", "critical"]
DeployRecommendation = Literal["go", "caution", "no-go"]

SEVERITY_ORDER: dict[RiskSeverity, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
SEVERITY_SCORE: dict[RiskSeverity, int] = {
    "low": 18,
    "medium": 42,
    "high": 72,
    "critical": 92,
}
INSUFFICIENT_CONTEXT_WARNING = (
    "Insufficient context: missing or stale topology, parser coverage, evidence "
    "coverage, or incident history requires reviewer verification before treating "
    "this result as low risk."
)
CONTEXT_REGENERATION_TODO = (
    "Re-run analysis after improving topology, parser, evidence, or incident context."
)
ACTION_BASE_SEVERITY = {
    "no-op": "low",
    "apply": "low",
    "create": "low",
    "modify": "medium",
    "read": "low",
    "replace": "high",
    "destroy": "high",
}
CATEGORY_BASE_SEVERITY = {
    "networking/ingress": "high",
    "namespace": "high",
    "iam/rbac": "high",
    "storage": "medium",
    "addon/config": "medium",
    "labels/annotations": "low",
    "compute/workload": "medium",
    "data/service": "medium",
    "pipeline/automation": "medium",
    "generic infrastructure": "medium",
}
logger = logging.getLogger(__name__)


class RiskContributor(BaseModel):
    evidence_id: str | None = Field(
        default=None, description="Evidence item that produced this contributor"
    )
    source_file: str = Field(..., description="Source file for the contributing change")
    tool: str = Field(..., description="Tool that produced the change")
    resource_id: str = Field(..., description="Resource affected by the change")
    action: str = Field(..., description="Change action")
    contribution: int = Field(..., description="Contribution to the final score")
    summary: str = Field(..., description="Human-readable explanation")
    normalized_action: str = Field(
        default="modify", description="Normalized lifecycle action"
    )
    resource_category: str = Field(
        default="generic infrastructure", description="Resource blast-radius category"
    )
    blast_radius: str = Field(
        default="unknown", description="Plain-English blast-radius summary"
    )
    downstream_scope: int | None = Field(
        default=None, description="Approximate downstream service/resource count"
    )
    security_flags: list[str] = Field(
        default_factory=list, description="Detected security-sensitive findings"
    )
    environment: str = Field(
        default="unknown", description="Inferred target environment"
    )
    severity: RiskSeverity = Field(
        default="medium", description="Per-change severity classification"
    )
    reasoning: str = Field(
        default="", description="Explicit explanation for this change score"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Parser-specific normalized metadata for this contributor",
    )


class RiskAssessment(BaseModel):
    score: int = Field(..., description="Overall bounded risk score")
    severity: RiskSeverity = Field(..., description="Severity classification")
    recommendation: DeployRecommendation = Field(
        ..., description="Advisory recommendation"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Overall verdict confidence"
    )
    top_risk: str = Field(..., description="Most important risk summary")
    top_risk_contributors: list[str] = Field(
        default_factory=list,
        description="Evidence IDs that most influenced the final verdict",
    )
    contributors: list[RiskContributor] = Field(
        default_factory=list, description="Score contributors"
    )
    interaction_risks: list[InteractionRisk] = Field(
        default_factory=list, description="Cross-tool interaction findings"
    )
    context_completeness: ContextCompleteness = Field(
        default_factory=ContextCompleteness,
        description="Structured signal describing how complete the supporting context was",
    )
    partial_context: bool = Field(..., description="Whether some files failed to parse")
    warnings: list[str] = Field(default_factory=list, description="Assessment warnings")
    source: Literal["heuristic-only", "heuristic+llm"] = Field(
        default="heuristic-only",
        description="Whether the structured risk assessment was heuristic-only or LLM-assisted",
    )


def _context_confidence_level(context_score: float) -> str:
    if context_score >= 0.85:
        return "high"
    if context_score >= 0.7:
        return "medium"
    return "low"


def _context_followup_todos(context: ContextCompleteness) -> list[str]:
    todos = list(context.context_todos)
    if context.topology_freshness_days is None:
        todos.append("Import or refresh topology context for this project/workspace.")
    elif context.topology_freshness_days > STALE_AFTER_DAYS:
        todos.append("Refresh stale topology context for this project/workspace.")
    if context.incident_index_size == 0:
        todos.append("Import relevant incident history for this project/workspace.")
    if context.parser_success_rate < 1.0:
        todos.append("Review parser errors and resubmit supported artifacts.")
    if context.evidence_success_rate < 1.0:
        todos.append("Review evidence extraction gaps for supported artifacts.")
    if not todos:
        todos.append(CONTEXT_REGENERATION_TODO)
    return list(dict.fromkeys(todos))


def apply_context_uncertainty(assessment: RiskAssessment) -> RiskAssessment:
    """Apply context completeness constraints to the overall verdict."""
    context = assessment.context_completeness
    if context.context_score < 0.7:
        context.insufficient_context = True
        if not context.uncertainty:
            context.uncertainty = (
                "Insufficient context: missing or stale topology, parser coverage, "
                "evidence coverage, or incident history prevents a confident "
                "low-risk verdict."
            )
    context.confidence_level = (
        "low"
        if context.insufficient_context
        else _context_confidence_level(context.context_score)
    )
    if context.insufficient_context and not context.context_todos:
        context.context_todos = _context_followup_todos(context)
    assessment.confidence = round(
        min(float(assessment.confidence), context.context_score),
        2,
    )
    if not context.insufficient_context:
        return assessment

    if INSUFFICIENT_CONTEXT_WARNING not in assessment.warnings:
        assessment.warnings.append(INSUFFICIENT_CONTEXT_WARNING)
    if assessment.recommendation == "go":
        assessment.recommendation = "caution"
    if assessment.severity == "low":
        assessment.severity = "medium"
        assessment.score = max(assessment.score, SEVERITY_SCORE["medium"])
    if not assessment.top_risk.startswith("INSUFFICIENT CONTEXT:"):
        assessment.top_risk = (
            "INSUFFICIENT CONTEXT: Missing or stale context prevents a confident "
            f"low-risk verdict. {assessment.top_risk}"
        )
    return assessment


def _normalize_action(action: str) -> str:
    return normalize_change_action(action)


def _severity_max(left: RiskSeverity, right: RiskSeverity) -> RiskSeverity:
    return left if SEVERITY_ORDER[left] >= SEVERITY_ORDER[right] else right


def _raise_severity(level: RiskSeverity, steps: int = 1) -> RiskSeverity:
    order = min(4, SEVERITY_ORDER[level] + steps)
    for severity, severity_order in SEVERITY_ORDER.items():
        if severity_order == order:
            return severity
    return "critical"


def _resource_category(change: UnifiedChange) -> str:
    identifier = change.resource_id.lower()
    summary = change.summary.lower()
    if change.tool == "kubernetes":
        kind = identifier.split("/", 1)[0]
        kind_map = {
            "deployment": "compute/workload",
            "statefulset": "compute/workload",
            "daemonset": "compute/workload",
            "pod": "compute/workload",
            "job": "compute/workload",
            "cronjob": "compute/workload",
            "replicaset": "compute/workload",
            "service": "networking/ingress",
            "ingress": "networking/ingress",
            "networkpolicy": "networking/ingress",
            "gateway": "networking/ingress",
            "httproute": "networking/ingress",
            "ingressclass": "networking/ingress",
            "storageclass": "storage",
            "persistentvolume": "storage",
            "persistentvolumeclaim": "storage",
            "csidriver": "storage",
            "csinode": "storage",
            "configmap": "addon/config",
            "secret": "addon/config",
            "role": "iam/rbac",
            "clusterrole": "iam/rbac",
            "rolebinding": "iam/rbac",
            "clusterrolebinding": "iam/rbac",
            "serviceaccount": "iam/rbac",
            "namespace": "namespace",
            "horizontalpodautoscaler": "workload-support",
            "poddisruptionbudget": "workload-support",
            "limitrange": "workload-support",
            "resourcequota": "workload-support",
        }
        return kind_map.get(kind, "generic infrastructure")
    if any(
        token in identifier
        for token in (
            "security_group",
            "vpc",
            "subnet",
            "ingress",
            "load_balancer",
            "alb",
            "route53",
            "gateway",
        )
    ):
        return "networking/ingress"
    if identifier.startswith("namespace/") or " namespace " in summary:
        return "namespace"
    if any(
        token in identifier
        for token in ("iam_", "clusterrole", "rolebinding", "serviceaccount", "rbac")
    ):
        return "iam/rbac"
    if any(
        token in identifier
        for token in (
            "storageclass",
            "persistentvolume",
            "persistentvolumeclaim",
            "db_instance",
            "efs",
            "rds",
            "csi",
        )
    ):
        return "storage"
    if any(
        token in identifier
        for token in ("configmap", "secret", "addon", "helm_release", "eks_addon")
    ):
        return "addon/config"
    if "label" in identifier or "annotation" in identifier:
        return "labels/annotations"
    if any(
        token in identifier
        for token in (
            "deployment/",
            "statefulset/",
            "daemonset/",
            "eks_cluster",
            "node_group",
            "ecs_service",
        )
    ):
        return "compute/workload"
    if any(
        token in identifier
        for token in (
            "bucket",
            "queue",
            "topic",
            "database",
            "redis",
            "cache",
            "resource/",
        )
    ):
        return "data/service"
    if change.tool == "jenkins":
        return "pipeline/automation"
    return "generic infrastructure"


def _environment(
    change: UnifiedChange, raw_files: dict[str, bytes | None] | None = None
) -> str:
    raw_content = raw_files.get(change.source_file) if raw_files else None
    content_text = raw_content.decode("utf-8", errors="ignore") if raw_content else ""
    text = " ".join(
        [change.source_file, change.resource_id, change.summary, content_text]
    ).lower()
    ordered_patterns = [
        (
            "preproduction",
            [
                r"\bpreproduction\b",
                r"\bpre-production\b",
                r"\bpreprod\b",
                r"\bpre-prod\b",
                r"\bnonprod\b",
                r"\bnon-prod\b",
            ],
        ),
        ("staging", [r"\bstaging\b", r"\bstg\b"]),
        ("development", [r"\bdevelopment\b", r"\bdev\b", r"\bsandbox\b", r"\btest\b"]),
        ("qa", [r"\bqa\b"]),
        ("uat", [r"\buat\b"]),
        ("production", [r"\bproduction\b", r"\bprod\b", r"\blive\b"]),
    ]
    for label, patterns in ordered_patterns:
        if any(re.search(pattern, text) for pattern in patterns):
            return label
    return "unknown"


def _resource_to_services(
    topology: dict | None,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    if not topology or not isinstance(topology, dict):
        return {}, {}
    services = topology.get("services", [])
    resource_map: dict[str, list[str]] = {}
    graph: dict[str, list[str]] = {}
    for service in services if isinstance(services, list) else []:
        if not isinstance(service, dict):
            continue
        service_id = str(service.get("id", "")).strip()
        if not service_id:
            continue
        graph[service_id] = [
            str(target).strip()
            for target in service.get("downstream", [])
            if str(target).strip()
        ]
        for resource_key in service.get("resource_keys", []):
            resource_map.setdefault(str(resource_key), []).append(service_id)
    return resource_map, graph


def _downstream_scope(change: UnifiedChange, topology: dict | None) -> int | None:
    resource_map, graph = _resource_to_services(topology)
    matched = resource_map.get(change.resource_id, [])
    if matched:
        seen: set[str] = set(matched)
        queue: deque[str] = deque(matched)
        while queue:
            current = queue.popleft()
            for downstream in graph.get(current, []):
                if downstream in seen:
                    continue
                seen.add(downstream)
                queue.append(downstream)
        return len(seen)
    return None


def _security_flags(
    change: UnifiedChange, raw_files: dict[str, bytes | None] | None = None
) -> list[str]:
    raw_content = raw_files.get(change.source_file) if raw_files else None
    text = raw_content.decode("utf-8", errors="ignore").lower() if raw_content else ""
    flags: list[str] = []
    if "amazons3fullaccess" in text and any(
        token in change.resource_id.lower()
        for token in ("iam", "node_group", "role", "policy")
    ):
        flags.append("Overly permissive IAM policy detected (AmazonS3FullAccess).")
    if re.search(
        r"(endpoint_public_access|publicaccess|public_access)\s*[:=]\s*(true|yes)", text
    ):
        flags.append("Public endpoint access enabled.")
    if re.search(r"(kms|encryption).{0,40}(false|disabled)", text):
        flags.append("KMS encryption appears disabled.")
    if re.search(r"(logging|cluster_log|loggings?).{0,40}(false|disabled|\[\])", text):
        flags.append("Operational logging appears disabled.")
    open_sg = (
        ("protocol" in text and "-1" in text and "0.0.0.0/0" in text)
        or (
            "from_port" in text
            and "0" in text
            and "to_port" in text
            and "0" in text
            and "0.0.0.0/0" in text
        )
        or (
            "cidrip: 0.0.0.0/0" in text
            and (
                "securitygroupingress" in text
                or "security group" in change.summary.lower()
            )
        )
    )
    if open_sg:
        flags.append("Open security group rule detected (protocol -1 / 0.0.0.0/0).")
    return flags


def _blast_radius_text(
    category: str, downstream_scope: int | None, normalized_action: str
) -> str:
    if normalized_action == "no-op":
        return "no planned change"
    if normalized_action == "read":
        return "read-only lookup; no infrastructure mutation planned"
    if downstream_scope is None:
        if normalized_action == "apply":
            return "unknown downstream impact — standalone manifest without cluster context"
        return "unknown downstream impact — no topology context available"
    if category == "networking/ingress":
        return f"High blast radius; likely touches ingress paths and up to {downstream_scope} downstream services."
    if category == "namespace":
        return f"High blast radius; namespace-level changes can affect up to {downstream_scope} scoped resources/services."
    if category == "iam/rbac":
        return f"Security-sensitive scope affecting permissions and up to {downstream_scope} dependent workloads."
    return f"Estimated downstream scope: {downstream_scope} service(s)/resource groups."


def _heuristic_reasoning(change: UnifiedChange, contributor: RiskContributor) -> str:
    parts = [
        f"{change.tool.title()} {change.resource_id} is a {contributor.normalized_action} change",
        f"in the {contributor.resource_category} category",
        f"targeting {contributor.environment}.",
    ]
    if contributor.normalized_action in NON_MUTATING_ACTIONS:
        parts.append(contributor.blast_radius + ".")
    elif contributor.downstream_scope is not None:
        parts.append(
            f"It may affect {contributor.downstream_scope} downstream service(s) or resource groups."
        )
    else:
        parts.append(contributor.blast_radius + ".")
    if contributor.security_flags:
        parts.append("Security flags: " + "; ".join(contributor.security_flags))
    return " ".join(parts)


def _heuristic_severity(
    change: UnifiedChange, contributor: RiskContributor
) -> RiskSeverity:
    if contributor.normalized_action in NON_MUTATING_ACTIONS:
        return "low"
    if contributor.normalized_action == "apply":
        if contributor.security_flags:
            return "high" if len(contributor.security_flags) == 1 else "critical"
        if (
            contributor.resource_category in {"namespace", "iam/rbac"}
            and contributor.environment == "production"
        ):
            return "medium"
        if (
            contributor.resource_category == "networking/ingress"
            and contributor.environment == "production"
        ):
            return "medium"
        return "low"
    severity = ACTION_BASE_SEVERITY[contributor.normalized_action]
    severity = _severity_max(
        severity, CATEGORY_BASE_SEVERITY[contributor.resource_category]
    )
    if contributor.normalized_action in {"destroy", "replace"} and (
        contributor.resource_category
        in {
            "networking/ingress",
            "namespace",
            "iam/rbac",
            "data/service",
        }
    ):
        severity = "critical"
    if contributor.environment == "production" and contributor.normalized_action in {
        "modify",
        "replace",
        "destroy",
    }:
        severity = _raise_severity(severity)
    if contributor.downstream_scope is not None and contributor.downstream_scope >= 5:
        severity = _raise_severity(severity)
    if contributor.security_flags:
        severity = _severity_max(severity, "high")
        if len(contributor.security_flags) >= 2:
            severity = "critical"
    return severity


def _build_contributor(
    change: UnifiedChange,
    *,
    topology: dict | None = None,
    raw_files: dict[str, bytes | None] | None = None,
) -> RiskContributor:
    normalized_action = _normalize_action(change.action)
    resource_category = _resource_category(change)
    downstream_scope = _downstream_scope(change, topology)
    security_flags = (
        []
        if normalized_action in NON_MUTATING_ACTIONS
        else _security_flags(change, raw_files)
    )
    environment = _environment(change, raw_files=raw_files)
    draft = RiskContributor(
        source_file=change.source_file,
        tool=change.tool,
        resource_id=change.resource_id,
        action=change.action,
        contribution=0,
        summary=change.summary,
        normalized_action=normalized_action,
        resource_category=resource_category,
        blast_radius=_blast_radius_text(
            resource_category, downstream_scope, normalized_action
        ),
        downstream_scope=downstream_scope,
        security_flags=security_flags,
        environment=environment,
        metadata=dict(change.metadata),
    )
    draft.severity = _heuristic_severity(change, draft)
    draft.reasoning = _heuristic_reasoning(change, draft)
    draft.contribution = _contribution_score(draft)
    return draft


def _contribution_score(contributor: RiskContributor) -> int:
    if contributor.normalized_action in NON_MUTATING_ACTIONS:
        return 0
    return min(
        100,
        SEVERITY_SCORE[contributor.severity]
        + (
            min(contributor.downstream_scope * 3, 12)
            if contributor.downstream_scope is not None
            else 0
        )
        + (
            8
            if contributor.environment == "production"
            and contributor.normalized_action != "create"
            else 0
        )
        + min(len(contributor.security_flags) * 10, 20),
    )


def _sanitize_scope_claims(text: str, contributors: list[RiskContributor]) -> str:
    allowed_scopes = {
        contributor.downstream_scope
        for contributor in contributors
        if contributor.downstream_scope is not None
    }

    def replace_numeric_scope(match: re.Match[str]) -> str:
        number = int(match.group("count"))
        if number in allowed_scopes:
            return match.group(0)
        return "unknown downstream impact — standalone manifest without cluster context"

    sanitized = re.sub(
        r"(?i)(affects?|impacts?)\s+(?P<count>\d+)\s+downstream\s+(services?|workloads?|resources?)",
        replace_numeric_scope,
        text,
    )
    sanitized = re.sub(
        r"(?i)(?P<count>\d+)\s+downstream\s+(services?|workloads?|resources?)",
        replace_numeric_scope,
        sanitized,
    )
    if not allowed_scopes:
        sanitized = re.sub(
            r"(?i)\b(high|wide|large)\s+blast\s+radius\b",
            "unknown downstream impact",
            sanitized,
        )
    return sanitized


def _assessment_prompt_payload(
    contributors: list[RiskContributor], partial_context: bool
) -> str:
    payload = {
        "policy": {
            "go_rule": "GO only when every change is Low or Medium and there are no security flags.",
            "no_go_rule": "NO-GO when any change is High or Critical, or any security violation is present.",
            "rollup_rule": "Overall severity must equal the highest individual resource severity.",
        },
        "partial_context": partial_context,
        "changes": [contributor.model_dump() for contributor in contributors],
    }
    return json.dumps(payload, indent=2)


def _assessment_system_prompt() -> str:
    return "\n".join(
        [
            "You are DeployWhisper's deployment-risk assessor.",
            "Score each normalized infrastructure change individually using the structured context provided.",
            "Treat create/modify/destroy differently: brand-new creates are usually lower risk than modifying or destroying an existing production resource.",
            "When a change action is 'apply', the input is a standalone manifest/template without verified previous state; do not assume modify or destroy.",
            "Resource category matters: networking/ingress, namespace, and IAM/RBAC changes have high blast radius; storage class is medium; addon/config is low-medium; labels/annotations are low unless combined with security risk.",
            "Use environment hints: prod/production/live should be treated as production.",
            "Any security finding such as overly permissive IAM, public endpoint access, disabled encryption, disabled logging, or open security group rules should push the affected item to at least High and may justify Critical.",
            "Never fabricate downstream service counts, blast-radius numbers, or impact scope. If scope is unknown, say 'unknown downstream impact — standalone manifest without cluster context'.",
            "Return JSON with keys: overall_severity, recommendation, top_risk, overall_reasoning, change_scores.",
            "Each change_scores item must contain: source_file, resource_id, severity, reasoning.",
            "Recommendation must be either 'go' or 'no-go'.",
            "Overall severity must be the highest severity from the scored items.",
            "Do not invent context beyond the payload. Use the payload wording when referencing blast radius, security flags, and downstream scope.",
        ]
    )


def _apply_llm_scores(
    contributors: list[RiskContributor],
    *,
    partial_context: bool,
    completion_client=None,
) -> tuple[list[RiskContributor], str | None, bool]:
    if not contributors:
        return contributors, None, False

    runtime = resolve_provider_runtime()
    try:
        prompt_messages = [
            {"role": "system", "content": _assessment_system_prompt()},
            {
                "role": "user",
                "content": _assessment_prompt_payload(contributors, partial_context),
            },
        ]
        raw_response = generate_completion_with_settings(
            prompt_messages,
            provider=runtime["provider"],
            model=runtime["model"],
            api_base=runtime["api_base"],
            api_key=runtime["api_key"],
            local_mode=runtime["local_mode"],
            completion_client=completion_client,
        )
        payload = json.loads(raw_response)
    except Exception as exc:  # noqa: BLE001
        return (
            contributors,
            f"LLM severity assessment unavailable; falling back to heuristic matrix: {exc}",
            False,
        )

    by_key = {
        (item["source_file"], item["resource_id"]): item
        for item in payload.get("change_scores", [])
        if isinstance(item, dict)
    }
    updated: list[RiskContributor] = []
    for contributor in contributors:
        llm_item = by_key.get((contributor.source_file, contributor.resource_id))
        if not llm_item:
            updated.append(contributor)
            continue
        severity = str(llm_item.get("severity", contributor.severity)).lower()
        if severity not in SEVERITY_ORDER:
            updated.append(contributor)
            continue
        if contributor.normalized_action in NON_MUTATING_ACTIONS:
            contributor.severity = "low"
            contributor.contribution = 0
            updated.append(contributor)
            continue
        contributor.severity = severity  # type: ignore[assignment]
        contributor.reasoning = _sanitize_scope_claims(
            str(llm_item.get("reasoning", contributor.reasoning)), [contributor]
        )
        contributor.contribution = _contribution_score(contributor)
        updated.append(contributor)
    return updated, None, True


def _build_top_risk(
    contributors: list[RiskContributor], interaction_risks: list[InteractionRisk]
) -> str:
    if interaction_risks:
        return interaction_risks[0].summary
    if not contributors:
        return "No normalized changes available for scoring."
    top = contributors[0]
    return f"{top.severity.upper()}: {top.resource_id} — {top.reasoning}"


def _overall_recommendation(
    contributors: list[RiskContributor],
) -> DeployRecommendation:
    if any(contributor.security_flags for contributor in contributors):
        return "no-go"
    highest = max(
        (SEVERITY_ORDER[contributor.severity] for contributor in contributors),
        default=1,
    )
    return "go" if highest <= SEVERITY_ORDER["medium"] else "no-go"


def _overall_score(
    contributors: list[RiskContributor], interaction_risks: list[InteractionRisk]
) -> int:
    if not contributors:
        return 0
    ranked = sorted(
        contributors, key=lambda contributor: contributor.contribution, reverse=True
    )
    highest = ranked[0].contribution
    secondary = 0.0
    for contributor in ranked[1:]:
        if contributor.severity == "critical":
            secondary += contributor.contribution * 0.2
        elif contributor.severity == "high":
            secondary += contributor.contribution * 0.12
        else:
            secondary += contributor.contribution * 0.03
    cascading_bonus = (
        12
        if sum(
            1
            for contributor in contributors
            if contributor.severity in {"high", "critical"}
        )
        >= 2
        else 0
    )
    interaction_bonus = min(
        sum(item.contribution_bonus for item in interaction_risks), 12
    )
    return min(100, round(highest + secondary + cascading_bonus + interaction_bonus))


def score_changes(
    changes: list[UnifiedChange],
    partial_context: bool = False,
    *,
    topology: dict | None = None,
    raw_files: dict[str, bytes | None] | None = None,
    completion_client=None,
) -> RiskAssessment:
    contributors = [
        _build_contributor(change, topology=topology, raw_files=raw_files)
        for change in changes
    ]
    if contributors and all(
        contributor.normalized_action in NON_MUTATING_ACTIONS
        for contributor in contributors
    ):
        llm_warning = None
        llm_used = False
    else:
        contributors, llm_warning, llm_used = _apply_llm_scores(
            contributors,
            partial_context=partial_context,
            completion_client=completion_client,
        )
    contributors.sort(
        key=lambda contributor: (
            SEVERITY_ORDER[contributor.severity],
            contributor.contribution,
        ),
        reverse=True,
    )
    interaction_risks = detect_interaction_risks(changes)
    warnings: list[str] = []
    if partial_context:
        warnings.append(
            "Analysis used partial context because one or more files failed to parse."
        )
    if llm_warning:
        warnings.append(llm_warning)

    score = _overall_score(contributors, interaction_risks)
    severity = contributors[0].severity if contributors else "low"
    recommendation = _overall_recommendation(contributors)
    top_risk = _build_top_risk(contributors, interaction_risks)

    return RiskAssessment(
        score=score,
        severity=severity,
        recommendation=recommendation,
        top_risk=top_risk,
        top_risk_contributors=[],
        contributors=contributors,
        interaction_risks=interaction_risks,
        partial_context=partial_context,
        warnings=warnings,
        source="heuristic+llm" if llm_used else "heuristic-only",
    )


def score_parse_batch(
    batch: ParseBatchResult,
    *,
    topology: dict | None = None,
    raw_files: dict[str, bytes | None] | None = None,
    completion_client=None,
) -> RiskAssessment:
    changes: list[UnifiedChange] = []
    for file_result in batch.files:
        if file_result.status == "parsed":
            changes.extend(file_result.changes)
    return score_changes(
        changes,
        partial_context=batch.has_partial_context,
        topology=topology,
        raw_files=raw_files,
        completion_client=completion_client,
    )
