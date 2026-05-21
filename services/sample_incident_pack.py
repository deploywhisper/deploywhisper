"""Safe sample incident pack helpers."""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from services.incident_service import ingest_incident_document


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_PACK_DIR = REPO_ROOT / "samples" / "incidents" / "safe-pack-v1"
MANIFEST_NAME = "manifest.json"

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
REAL_ORGANIZATION_TERMS = {
    "airbnb",
    "amazon",
    "apple",
    "aws",
    "aws_security_group_rule",
    "cloudflare",
    "deploywhisper",
    "facebook",
    "github",
    "google",
    "hashicorp",
    "microsoft",
    "netflix",
    "openai",
    "shopify",
    "slack",
    "stripe",
    "terraform",
    "uber",
}


class SampleIncidentRecord(BaseModel):
    """A sample incident document with safety declarations."""

    source_file: str
    content: str
    sample: bool = False
    provenance: str = ""
    permission: str = ""
    contains_real_customer_data: bool = True
    contains_real_organization_names: bool = True
    contains_non_public_postmortem: bool = True
    limitations: list[str] = Field(default_factory=list)


class SampleIncidentPackInspection(BaseModel):
    """Inspection result for the bundled sample incident pack."""

    pack_id: str
    title: str = ""
    loaded_by_default: bool = False
    safe: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: str = ""
    limitations: list[str] = Field(default_factory=list)
    records: list[SampleIncidentRecord] = Field(default_factory=list)


def inspect_sample_incident_pack(
    pack_dir: Path | None = None,
) -> SampleIncidentPackInspection:
    """Inspect the bundled sample pack before loading it anywhere."""
    pack_dir = pack_dir or DEFAULT_SAMPLE_PACK_DIR
    manifest_path = pack_dir / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return SampleIncidentPackInspection(
            pack_id="missing",
            safe=False,
            errors=[f"Sample pack manifest not found: {manifest_path}"],
        )
    except json.JSONDecodeError as exc:
        return SampleIncidentPackInspection(
            pack_id="invalid",
            safe=False,
            errors=[f"Sample pack manifest is invalid JSON: {exc}"],
        )

    records: dict[str, str] = {}
    for item in manifest.get("records", []):
        source_file = item.get("source_file") if isinstance(item, dict) else None
        if not isinstance(source_file, str) or not source_file:
            continue
        record_path = pack_dir / source_file
        try:
            records[source_file] = record_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return SampleIncidentPackInspection(
                pack_id=str(manifest.get("pack_id") or "unknown"),
                title=str(manifest.get("title") or ""),
                loaded_by_default=bool(manifest.get("loaded_by_default")),
                safe=False,
                errors=[f"Sample incident record not found: {record_path}"],
                provenance=str(manifest.get("provenance") or ""),
                limitations=[
                    str(item)
                    for item in manifest.get("limitations", [])
                    if isinstance(item, str) and item.strip()
                ],
            )

    return inspect_sample_incident_documents(
        records,
        pack_id=str(manifest.get("pack_id") or "unknown"),
        title=str(manifest.get("title") or ""),
        loaded_by_default=bool(manifest.get("loaded_by_default")),
        provenance=str(manifest.get("provenance") or ""),
        limitations=[
            str(item)
            for item in manifest.get("limitations", [])
            if isinstance(item, str) and item.strip()
        ],
        manifest_sample=bool(manifest.get("sample")),
    )


def inspect_sample_incident_documents(
    documents: dict[str, str],
    *,
    pack_id: str = "ad-hoc",
    title: str = "",
    loaded_by_default: bool = False,
    provenance: str = "",
    limitations: list[str] | None = None,
    manifest_sample: bool = True,
) -> SampleIncidentPackInspection:
    """Inspect supplied sample incident documents for safety declarations."""
    errors: list[str] = []
    warnings: list[str] = []
    records: list[SampleIncidentRecord] = []
    limitations = limitations or []

    if not manifest_sample:
        errors.append("Manifest must declare sample: true.")
    if loaded_by_default:
        errors.append("Sample incident packs must not be loaded by default.")
    if pack_id != "ad-hoc" and not provenance:
        errors.append("Sample incident pack manifest must declare provenance.")
    if pack_id != "ad-hoc" and not limitations:
        errors.append("Sample incident pack manifest must declare limitations.")
    manifest_text = " ".join([pack_id, title, provenance, *limitations])
    errors.extend(_unsafe_text_errors("manifest", manifest_text))

    for source_file, content in sorted(documents.items()):
        record = _parse_sample_record(source_file, content)
        records.append(record)
        errors.extend(_record_safety_errors(record))
        errors.extend(_unsafe_content_errors(record))

    if not records:
        errors.append("Sample incident pack must contain at least one record.")

    return SampleIncidentPackInspection(
        pack_id=pack_id,
        title=title,
        loaded_by_default=loaded_by_default,
        safe=not errors,
        errors=errors,
        warnings=warnings,
        provenance=provenance,
        limitations=limitations,
        records=records,
    )


def load_safe_sample_incident_pack(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> dict[str, Any]:
    """Explicitly load the safe sample incident pack into a project scope."""
    inspection = inspect_sample_incident_pack()
    if not inspection.safe:
        raise ValueError(
            "Sample incident pack failed safety inspection: "
            + "; ".join(inspection.errors)
        )

    loaded_records = [
        ingest_incident_document(
            record.source_file,
            record.content,
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
        for record in inspection.records
    ]
    return {
        "pack_id": inspection.pack_id,
        "loaded": len(loaded_records),
        "records": loaded_records,
    }


def _parse_sample_record(source_file: str, content: str) -> SampleIncidentRecord:
    return SampleIncidentRecord(
        source_file=source_file,
        content=content,
        sample=_value_is_yes(_field_value(content, "Sample data")),
        provenance=_field_value(content, "Provenance"),
        permission=_field_value(content, "Permission"),
        contains_real_customer_data=_value_is_yes(
            _field_value(content, "Contains real customer data")
        ),
        contains_real_organization_names=_value_is_yes(
            _field_value(content, "Contains real organization names")
        ),
        contains_non_public_postmortem=_value_is_yes(
            _field_value(content, "Contains non-public postmortem content")
        ),
        limitations=_bullet_values_after(content, "Limitations"),
    )


def _field_value(content: str, field_name: str) -> str:
    prefix = f"{field_name}:"
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(prefix.lower()):
            return stripped[len(prefix) :].strip()
    return ""


def _bullet_values_after(content: str, field_name: str) -> list[str]:
    values: list[str] = []
    in_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.lower() == f"{field_name}:".lower():
            in_section = True
            continue
        if not in_section:
            continue
        if not stripped:
            if values:
                break
            continue
        if not stripped.startswith("- "):
            break
        values.append(stripped[2:].strip())
    return values


def _value_is_yes(value: str) -> bool:
    return value.strip().lower() in {"yes", "true"}


def _value_is_no(value: str) -> bool:
    return value.strip().lower() in {"no", "false"}


def _record_safety_errors(record: SampleIncidentRecord) -> list[str]:
    errors: list[str] = []
    prefix = f"{record.source_file}:"
    if not record.sample:
        errors.append(f"{prefix} sample data declaration must be yes.")
    if not record.provenance:
        errors.append(f"{prefix} provenance declaration is required.")
    if not record.permission:
        errors.append(f"{prefix} permission declaration is required.")
    if not _value_is_no(_field_value(record.content, "Contains real customer data")):
        errors.append(f"{prefix} must declare that it contains no real customer data.")
    if not _value_is_no(
        _field_value(record.content, "Contains real organization names")
    ):
        errors.append(
            f"{prefix} must declare that it contains no real organization names."
        )
    if not _value_is_no(
        _field_value(record.content, "Contains non-public postmortem content")
    ):
        errors.append(
            f"{prefix} must declare no non-public postmortem content is included."
        )
    if not record.limitations:
        errors.append(f"{prefix} limitations declaration is required.")
    return errors


def _unsafe_content_errors(record: SampleIncidentRecord) -> list[str]:
    return _unsafe_text_errors(record.source_file, record.content)


def _unsafe_text_errors(source_name: str, content: str) -> list[str]:
    errors: list[str] = []
    lower_content = content.lower()
    for term in sorted(REAL_ORGANIZATION_TERMS):
        if re.search(rf"\b{re.escape(term)}\b", lower_content):
            errors.append(
                f"{source_name}: possible real organization name found: {term}."
            )
    for email in EMAIL_PATTERN.findall(content):
        if not _is_example_email(email):
            errors.append(f"{source_name}: possible real email address: {email}.")
    for match in IPV4_PATTERN.findall(content):
        if not _is_allowed_sample_ip(match):
            errors.append(f"{source_name}: possible real IP address found: {match}.")
    return errors


def _is_example_email(value: str) -> bool:
    return value.lower().endswith(
        ("@example.com", "@example.net", "@example.org", "@example.invalid")
    )


def _is_allowed_sample_ip(value: str) -> bool:
    if value == "0.0.0.0":
        return True
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return (
        ip in ipaddress.ip_network("192.0.2.0/24")
        or ip in ipaddress.ip_network("198.51.100.0/24")
        or ip in ipaddress.ip_network("203.0.113.0/24")
    )
