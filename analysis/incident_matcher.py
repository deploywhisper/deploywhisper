"""Incident matching access helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from parsers.base import UnifiedChange, normalize_change_action
from services.incident_service import get_incident_records


class IncidentMatch(BaseModel):
    incident_id: int = Field(..., description="Matched incident identifier")
    match_type: Literal["organization_incident", "public_risk_pattern"] = Field(
        default="organization_incident",
        description="Whether the match came from org incident memory or public patterns.",
    )
    public_pattern_id: str | None = Field(
        default=None, description="Built-in public risk pattern identifier."
    )
    title: str = Field(..., description="Incident title")
    severity: str = Field(..., description="Incident severity")
    source_file: str = Field(..., description="Incident source file")
    incident_date: str | None = Field(
        default=None, description="Incident date if available"
    )
    similarity: float = Field(..., description="Similarity score between 0 and 1")
    confidence: float = Field(
        default=0.0, description="Confidence that this memory signal applies."
    )
    reason: str = Field(
        default="", description="Why the incident or public pattern matched."
    )
    evidence: list[str] = Field(
        default_factory=list, description="Concrete evidence supporting the match."
    )
    verification_guidance: list[str] = Field(
        default_factory=list,
        description="Human verification steps before acting on the match.",
    )
    summary: str = Field(..., description="Short operational explanation")


def load_incident_candidates(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> list[dict]:
    """Return stored incident records for future similarity matching."""
    return get_incident_records(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )


TOKEN_PATTERN = re.compile(r"[a-z0-9_./-]+", re.IGNORECASE)
STOP_WORDS = {
    "terraform",
    "kubernetes",
    "deployment",
    "resource",
    "resources",
    "changed",
    "change",
    "included",
    "analysis",
    "set",
    "stage",
    "modify",
    "create",
    "delete",
    "destroy",
    "service",
}


ADMIN_INGRESS_PORTS = {"22", "3389", "5432", "3306", "6379", "9200", "9300"}
STATEFUL_RESOURCE_TYPES = {
    "aws_db_instance",
    "aws_rds_cluster",
    "aws_dynamodb_table",
    "aws_elasticache_cluster",
    "aws_elasticache_replication_group",
    "aws_s3_bucket",
    "aws_ebs_volume",
    "azurerm_postgresql_server",
    "azurerm_mssql_server",
    "azurerm_storage_account",
    "google_sql_database_instance",
    "google_storage_bucket",
    "persistentvolume",
    "persistentvolumeclaim",
}


def _metadata_text_parts(value: Any) -> list[str]:
    if isinstance(value, dict):
        parts: list[str] = []
        for key, nested in value.items():
            parts.append(str(key))
            parts.extend(_metadata_text_parts(nested))
        return parts
    if isinstance(value, list | tuple | set):
        parts = []
        for nested in value:
            parts.extend(_metadata_text_parts(nested))
        return parts
    if value is None:
        return []
    return [str(value)]


def _change_text(change: UnifiedChange) -> str:
    metadata_text = " ".join(_metadata_text_parts(change.metadata))
    return " ".join(
        str(part or "")
        for part in [
            change.source_file,
            change.tool,
            change.resource_id,
            change.action,
            change.summary,
            metadata_text,
        ]
    ).lower()


def _evidence_line(change: UnifiedChange) -> str:
    return (
        f"{change.source_file}: {change.resource_id} "
        f"({normalize_change_action(change.action)}) - {change.summary}"
    )


def _matches_wide_open_ingress(change: UnifiedChange) -> bool:
    if isinstance(change.metadata.get("network_ingress_rules"), list):
        return _matches_structured_wide_open_ingress(change)
    text = _change_text(change)
    has_public_cidr = "0.0.0.0/0" in text or "::/0" in text
    has_ingress_signal = any(
        signal in text
        for signal in (
            "ingress",
            "security_group",
            "security group",
            "firewall",
            "network security group",
        )
    )
    has_admin_port_signal = (
        "ssh" in text
        or "rdp" in text
        or any(f"port {port}" in text for port in ADMIN_INGRESS_PORTS)
        or any(f":{port}" in text for port in ADMIN_INGRESS_PORTS)
    )
    return has_public_cidr and has_ingress_signal and has_admin_port_signal


def _matches_structured_wide_open_ingress(change: UnifiedChange) -> bool:
    resource_type = _resource_type(change)
    if resource_type and (
        "security_group" not in resource_type and "firewall" not in resource_type
    ):
        return False
    rules = change.metadata.get("network_ingress_rules")
    if not isinstance(rules, list):
        return False
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        cidrs = [
            str(cidr)
            for cidr in [
                *(rule.get("cidr_blocks") or []),
                *(rule.get("ipv6_cidr_blocks") or []),
            ]
        ]
        if not any(cidr in {"0.0.0.0/0", "::/0"} for cidr in cidrs):
            continue
        if _rule_exposes_admin_port(rule):
            return True
    return False


def _rule_exposes_admin_port(rule: dict[str, Any]) -> bool:
    protocol = str(rule.get("protocol") or "").lower()
    if protocol in {"-1", "all", "any"}:
        return True
    from_port = _int_or_none(rule.get("from_port"))
    to_port = _int_or_none(rule.get("to_port"))
    if from_port is None or to_port is None:
        return False
    low, high = sorted((from_port, to_port))
    return any(low <= int(port) <= high for port in ADMIN_INGRESS_PORTS)


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resource_type(change: UnifiedChange) -> str:
    metadata_type = change.metadata.get("resource_type")
    if isinstance(metadata_type, str) and metadata_type.strip():
        return metadata_type.strip().lower()
    parts = [part for part in change.resource_id.lower().split(".") if part]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else ""


def _matches_stateful_destroy(change: UnifiedChange) -> bool:
    if normalize_change_action(change.action) not in {"destroy", "replace"}:
        return False
    return _resource_type(change) in STATEFUL_RESOURCE_TYPES


def find_public_risk_pattern_matches(
    changes: list[UnifiedChange],
) -> list[IncidentMatch]:
    """Return built-in public risk pattern matches for fresh installs."""
    matches: list[IncidentMatch] = []
    for change in changes:
        if _matches_wide_open_ingress(change):
            matches.append(
                IncidentMatch(
                    incident_id=0,
                    match_type="public_risk_pattern",
                    public_pattern_id="public-ingress-wide-open",
                    title="Wide-open administrative ingress",
                    severity="high",
                    source_file=change.source_file,
                    incident_date=None,
                    similarity=0.86,
                    confidence=0.86,
                    reason=(
                        "The change appears to expose administrative or data-plane "
                        "network access to the public internet."
                    ),
                    evidence=[_evidence_line(change)],
                    verification_guidance=[
                        "Confirm whether the public CIDR is intentional and time-bound.",
                        "Restrict administrative ingress to trusted networks or a managed access path.",
                        "Verify compensating controls such as just-in-time access, MFA, and alerting.",
                    ],
                    summary=(
                        "Public risk pattern match: wide-open administrative ingress "
                        "has caused common deployment incidents."
                    ),
                )
            )
        if _matches_stateful_destroy(change):
            matches.append(
                IncidentMatch(
                    incident_id=0,
                    match_type="public_risk_pattern",
                    public_pattern_id="public-stateful-resource-destroy",
                    title="Stateful resource replacement or deletion",
                    severity="high",
                    source_file=change.source_file,
                    incident_date=None,
                    similarity=0.82,
                    confidence=0.82,
                    reason=(
                        "The change appears to destroy or replace a stateful resource "
                        "where data loss or prolonged recovery is a common failure mode."
                    ),
                    evidence=[_evidence_line(change)],
                    verification_guidance=[
                        "Confirm a tested backup, restore, or migration path exists.",
                        "Check retention, deletion protection, and rollback timing.",
                        "Review downstream services that depend on the stateful resource.",
                    ],
                    summary=(
                        "Public risk pattern match: stateful resource deletion or "
                        "replacement can create recovery and data-loss incidents."
                    ),
                )
            )
    matches.sort(key=lambda match: match.confidence, reverse=True)
    return matches


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if len(token) > 2 and token.lower() not in STOP_WORDS
    }


def _severity_bonus(severity: str) -> float:
    severity = severity.lower()
    if severity == "critical":
        return 0.08
    if severity == "high":
        return 0.05
    if severity == "medium":
        return 0.02
    return 0.0


def _recency_bonus(incident_date: str | None) -> float:
    if not incident_date:
        return 0.0
    try:
        parsed = datetime.fromisoformat(incident_date.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age_days = max((datetime.now(UTC) - parsed).days, 0)
    if age_days <= 30:
        return 0.06
    if age_days <= 180:
        return 0.03
    if age_days <= 365:
        return 0.015
    return 0.0


def find_incident_matches(
    changes: list[UnifiedChange],
    min_similarity: float = 0.2,
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> list[IncidentMatch]:
    """Return incident matches ranked by simple token overlap."""
    public_pattern_matches = find_public_risk_pattern_matches(changes)
    candidates = load_incident_candidates(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    if not candidates:
        return public_pattern_matches

    change_text = " ".join(
        " ".join([change.source_file, change.tool, change.resource_id, change.summary])
        for change in changes
    )
    change_tokens = _tokenize(change_text)
    if not change_tokens:
        return public_pattern_matches

    matches: list[IncidentMatch] = []
    for candidate in candidates:
        incident_text = " ".join(
            [
                candidate.get("title", ""),
                candidate.get("severity", ""),
                candidate.get("source_file", ""),
                candidate.get("content", ""),
            ]
        )
        incident_tokens = _tokenize(incident_text)
        if not incident_tokens:
            continue
        overlap = change_tokens & incident_tokens
        union = change_tokens | incident_tokens
        similarity = len(overlap) / max(len(union), 1)
        similarity = min(
            1.0,
            similarity
            + _severity_bonus(candidate.get("severity", "unknown"))
            + _recency_bonus(candidate.get("incident_date")),
        )
        if similarity < min_similarity:
            continue
        matches.append(
            IncidentMatch(
                incident_id=candidate["id"],
                match_type="organization_incident",
                public_pattern_id=None,
                title=candidate["title"],
                severity=candidate["severity"],
                source_file=candidate["source_file"],
                incident_date=candidate.get("incident_date"),
                similarity=round(similarity, 2),
                confidence=round(similarity, 2),
                reason=(
                    "The current change shares deployment tokens with an "
                    "organization-specific incident record."
                ),
                evidence=[
                    f"overlap: {', '.join(sorted(overlap)[:8])}",
                    f"incident source: {candidate['source_file']}",
                ],
                verification_guidance=[
                    "Compare the current change path against the prior incident timeline.",
                    "Confirm whether the same affected service, dependency, or rollback path applies.",
                ],
                summary=(
                    f"Similar to prior incident '{candidate['title']}' "
                    f"({candidate['severity']}) with {round(similarity * 100)}% token overlap."
                ),
            )
        )

    matches.extend(public_pattern_matches)
    matches.sort(key=lambda match: match.similarity, reverse=True)
    return matches
