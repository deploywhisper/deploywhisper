"""Evidence extraction from normalized parser output."""

from __future__ import annotations

import hashlib
from urllib.parse import quote

from evidence.models import EvidenceItem, RiskSeverity
from parsers.base import NormalizedChange, ParseBatchResult

SEVERITY_ORDER: dict[RiskSeverity, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
ACTION_BASE_SEVERITY: dict[str, RiskSeverity] = {
    "apply": "low",
    "create": "low",
    "modify": "medium",
    "replace": "medium",
    "update": "medium",
    "destroy": "high",
    "delete": "high",
}
HIGH_RISK_TOKENS = {
    "security_group",
    "securitygroup",
    "firewall",
    "vpc",
    "subnet",
    "route",
    "gateway",
    "ingress",
    "egress",
    "iam",
    "role",
    "policy",
    "rbac",
    "clusterrole",
    "rolebinding",
    "serviceaccount",
    "namespace",
    "privilege",
}
MEDIUM_RISK_TOKENS = {
    "deployment",
    "statefulset",
    "daemonset",
    "job",
    "cronjob",
    "storage",
    "persistentvolume",
    "bucket",
    "database",
    "module",
    "node_group",
    "eks",
    "ecs",
    "deploy",
    "release",
    "rollback",
    "function",
    "lambda",
}


def _normalize_action(action: str) -> str:
    parts = action.split("+")
    for candidate in (
        "apply",
        "destroy",
        "delete",
        "modify",
        "update",
        "replace",
        "create",
    ):
        if candidate in parts:
            return candidate
    return "modify"


def _max_severity(left: RiskSeverity, right: RiskSeverity) -> RiskSeverity:
    return left if SEVERITY_ORDER[left] >= SEVERITY_ORDER[right] else right


def _build_evidence_id(change: NormalizedChange, source_ref: str) -> str:
    seed = "|".join((change.change_id, source_ref))
    return f"ev-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _build_source_ref(change: NormalizedChange) -> str:
    source_file = quote(change.source_file, safe="/._-")
    resource_id = quote(change.resource_id, safe="/._-")
    action = quote(change.action, safe="+._-")
    return f"{change.tool}://{source_file}#{resource_id}?action={action}"


def _severity_hint(change: NormalizedChange) -> RiskSeverity:
    severity = ACTION_BASE_SEVERITY.get(_normalize_action(change.action), "medium")
    resource_id = change.resource_id.lower()
    if resource_id.startswith("service/"):
        return _max_severity(severity, "high")
    if resource_id.startswith("configmap/"):
        return severity

    lowered = f"{change.resource_id} {change.summary}".lower()
    if any(token in lowered for token in HIGH_RISK_TOKENS):
        return _max_severity(severity, "high")
    if any(token in lowered for token in MEDIUM_RISK_TOKENS):
        return _max_severity(severity, "medium")
    return severity


class EvidenceExtractor:
    """Translate normalized parser changes into evidence-domain items."""

    def extract(self, change: NormalizedChange) -> list[EvidenceItem]:
        handler = getattr(self, f"extract_{change.tool}", None)
        if handler is None:
            return [self._build_item(change)]
        return handler(change)

    def extract_batch(self, batch: ParseBatchResult) -> list[EvidenceItem]:
        evidence_items: list[EvidenceItem] = []
        for file_result in batch.files:
            if file_result.status != "parsed":
                continue
            for change in file_result.changes:
                evidence_items.extend(self.extract(change))
        return evidence_items

    def extract_terraform(self, change: NormalizedChange) -> list[EvidenceItem]:
        return [self._build_item(change)]

    def extract_kubernetes(self, change: NormalizedChange) -> list[EvidenceItem]:
        return [self._build_item(change)]

    def extract_ansible(self, change: NormalizedChange) -> list[EvidenceItem]:
        return [self._build_item(change)]

    def extract_jenkins(self, change: NormalizedChange) -> list[EvidenceItem]:
        return [self._build_item(change)]

    def extract_cloudformation(self, change: NormalizedChange) -> list[EvidenceItem]:
        return [self._build_item(change)]

    def _build_item(self, change: NormalizedChange) -> EvidenceItem:
        source_ref = _build_source_ref(change)
        return EvidenceItem(
            evidence_id=_build_evidence_id(change, source_ref),
            analysis_id=0,
            finding_id=f"pending:{change.change_id}",
            source_type="artifact",
            source_ref=source_ref,
            summary=change.summary,
            severity_hint=_severity_hint(change),
            deterministic=True,
            confidence=1.0,
            related_change_ids=[change.change_id],
        )


def extract_evidence(change: NormalizedChange) -> list[EvidenceItem]:
    """Extract evidence items for one normalized change."""
    return EvidenceExtractor().extract(change)


def extract_batch_evidence(batch: ParseBatchResult) -> list[EvidenceItem]:
    """Extract evidence items for every parsed change in one batch."""
    return EvidenceExtractor().extract_batch(batch)
