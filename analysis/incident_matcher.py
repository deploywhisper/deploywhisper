"""Incident matching access helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

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
    confidence_label: Literal["high", "medium", "low"] = Field(
        default="low", description="Human-readable confidence bucket."
    )
    reason: str = Field(
        default="", description="Why the incident or public pattern matched."
    )
    evidence: list[str] = Field(
        default_factory=list, description="Concrete evidence supporting the match."
    )
    matched_signals: list[str] = Field(
        default_factory=list,
        description="Specific tokens, services, or risk signals that matched.",
    )
    affected_services: list[str] = Field(
        default_factory=list,
        description="Services affected in the matched incident or pattern.",
    )
    prevention_notes: list[str] = Field(
        default_factory=list,
        description="Prevention guidance from the incident or public pattern.",
    )
    verification_guidance: list[str] = Field(
        default_factory=list,
        description="Human verification steps before acting on the match.",
    )
    summary: str = Field(..., description="Short operational explanation")

    @model_validator(mode="before")
    @classmethod
    def _derive_confidence_label(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("confidence_label"):
            return value
        return {
            **value,
            "confidence_label": _confidence_label(value.get("confidence", 0.0)),
        }


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

LOW_CONFIDENCE_FLOOR = 0.05
GENERIC_SERVICE_SEGMENTS = {
    "api",
    "app",
    "auth",
    "backend",
    "frontend",
    "job",
    "service",
    "server",
    "web",
    "worker",
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


def _confidence_label(confidence: Any) -> Literal["high", "medium", "low"]:
    try:
        numeric_confidence = float(confidence or 0.0)
    except (TypeError, ValueError):
        numeric_confidence = 0.0
    if numeric_confidence >= 0.5:
        return "high"
    if numeric_confidence >= 0.35:
        return "medium"
    return "low"


def _extract_markdown_list_section(content: str, section_title: str) -> list[str]:
    lines = content.splitlines()
    in_section = False
    values: list[str] = []
    wanted = _section_title_aliases(section_title)
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            title = _normalize_section_title(stripped.lstrip("#").strip())
            if in_section and title not in wanted:
                break
            in_section = title in wanted
            continue
        if not in_section or not stripped:
            continue
        if stripped.startswith(("- ", "* ")):
            values.append(stripped[2:].strip())
        elif not values:
            values.append(stripped)
    return values


def _normalize_section_title(title: str) -> str:
    normalized = re.sub(r"[_:-]+", " ", title.casefold())
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    return normalized


def _section_title_aliases(section_title: str) -> set[str]:
    normalized = _normalize_section_title(section_title)
    aliases = {normalized}
    if normalized.endswith("s"):
        aliases.add(normalized[:-1])
    else:
        aliases.add(f"{normalized}s")
    return aliases


def _sorted_signals(signals: set[str], limit: int = 8) -> list[str]:
    return sorted(signals, key=lambda signal: (len(signal), signal), reverse=True)[
        :limit
    ]


def _text_segments(text: str) -> set[str]:
    return {segment for segment in re.findall(r"[a-z0-9]+", text.casefold()) if segment}


def _meaningful_service_segments(service: str) -> set[str]:
    return {
        segment
        for segment in _text_segments(service)
        if len(segment) > 2 and segment not in GENERIC_SERVICE_SEGMENTS
    }


def _service_matches_change(service: str, change_text: str) -> bool:
    normalized = service.strip().casefold()
    if not normalized:
        return False
    if normalized in _tokenize(change_text):
        return True
    meaningful_segments = _meaningful_service_segments(normalized)
    if not meaningful_segments:
        return False
    return meaningful_segments <= _text_segments(change_text)


def _affected_service_bonus(
    affected_services: list[str], change_text: str
) -> tuple[float, list[str]]:
    matched_services = [
        service
        for service in affected_services
        if _service_matches_change(service, change_text)
    ]
    return min(len(matched_services) * 0.18, 0.35), matched_services


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
                    confidence_label="high",
                    reason=(
                        "The change appears to expose administrative or data-plane "
                        "network access to the public internet."
                    ),
                    evidence=[_evidence_line(change)],
                    matched_signals=[
                        signal
                        for signal in ["0.0.0.0/0", "::/0", "ssh", "rdp", "ingress"]
                        if signal in _change_text(change)
                    ],
                    affected_services=[change.resource_id],
                    prevention_notes=[
                        "Use a trusted administrative access path instead of broad public ingress.",
                        "Time-bound any exception and verify compensating controls before deployment.",
                    ],
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
                    confidence_label="high",
                    reason=(
                        "The change appears to destroy or replace a stateful resource "
                        "where data loss or prolonged recovery is a common failure mode."
                    ),
                    evidence=[_evidence_line(change)],
                    matched_signals=[
                        normalize_change_action(change.action),
                        _resource_type(change),
                    ],
                    affected_services=[change.resource_id],
                    prevention_notes=[
                        "Require a tested backup, restore, or migration path before deployment.",
                        "Confirm retention and deletion protection match the intended recovery posture.",
                    ],
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
    min_similarity: float = LOW_CONFIDENCE_FLOOR,
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
        content = candidate.get("content", "")
        incident_text = " ".join(
            [
                candidate.get("title", ""),
                candidate.get("severity", ""),
                candidate.get("source_file", ""),
                content,
            ]
        )
        incident_tokens = _tokenize(incident_text)
        if not incident_tokens:
            continue
        overlap = change_tokens & incident_tokens
        union = change_tokens | incident_tokens
        affected_services = _extract_markdown_list_section(content, "Affected services")
        service_bonus, matched_services = _affected_service_bonus(
            affected_services, change_text
        )
        if not overlap and not matched_services:
            continue
        similarity = len(overlap) / max(len(union), 1)
        similarity = min(
            1.0,
            similarity
            + _severity_bonus(candidate.get("severity", "unknown"))
            + _recency_bonus(candidate.get("incident_date"))
            + service_bonus,
        )
        if similarity < min_similarity:
            continue
        rounded_similarity = round(similarity, 2)
        matched_signals = _sorted_signals(overlap | set(matched_services))
        confidence_label = _confidence_label(rounded_similarity)
        prevention_notes = _extract_markdown_list_section(content, "Prevention notes")
        label_prefix = f"{confidence_label.title()}-confidence"
        matches.append(
            IncidentMatch(
                incident_id=candidate["id"],
                match_type="organization_incident",
                public_pattern_id=None,
                title=candidate["title"],
                severity=candidate["severity"],
                source_file=candidate["source_file"],
                incident_date=candidate.get("incident_date"),
                similarity=rounded_similarity,
                confidence=rounded_similarity,
                confidence_label=confidence_label,
                reason=(
                    "The current change shares deployment tokens with an "
                    "organization-specific prior incident record."
                ),
                evidence=[
                    f"matched signals: {', '.join(matched_signals)}",
                    f"incident source: {candidate['source_file']}",
                ],
                matched_signals=matched_signals,
                affected_services=matched_services or affected_services,
                prevention_notes=prevention_notes,
                verification_guidance=[
                    "Compare the current change path against the prior incident timeline.",
                    "Confirm whether the same affected service, dependency, or rollback path applies.",
                ],
                summary=(
                    f"{label_prefix} organization-specific incident match: "
                    f"'{candidate['title']}' ({candidate['severity']}) at "
                    f"{round(similarity * 100)}% confidence."
                ),
            )
        )

    matches.extend(public_pattern_matches)
    matches.sort(key=lambda match: match.similarity, reverse=True)
    return matches
