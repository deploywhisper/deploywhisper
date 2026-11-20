"""Screen selected observation metadata before persistence and digesting."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import re
from typing import Iterable

from cloud.base import (
    LiveContextSnapshot,
    ReadStatus,
    build_snapshot,
    validate_snapshot,
)
from services.content_security import (
    redact_text,
    redact_value,
    sensitive_artifact_values,
)

_NUMERIC_TOKEN = re.compile(
    r"(?<![0-9.])[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?(?![0-9.])"
)
_RAW_MARKERS = (
    "rawstate",
    "rawplan",
    "rawresponse",
    "rawcontent",
    "rawartifact",
    "rawiac",
    "terraformstate",
    "terraformplan",
    "tfstate",
    "planbytes",
    "statejson",
    "planjson",
)
_ACCOUNT = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")
_RAW_FIELDS = {
    "rawstate",
    "statejson",
    "tfstate",
    "terraformstate",
    "rawplan",
    "planjson",
    "terraformplan",
    "planbytes",
    "userdata",
    "cloudinit",
    "bootstrap",
    "script",
    "rawresponse",
    "rawcontent",
    "rawartifact",
    "rawiac",
    "payload",
    "body",
    "content",
}


def _raw_name(name: str) -> bool:
    parts = [re.sub(r"[^a-z0-9]", "", part) for part in re.split(r"[.:]", name.lower())]
    return any(
        part in _RAW_FIELDS
        or "userdata" in part
        or any(marker in part for marker in _RAW_MARKERS)
        or part.endswith(
            ("startupscript", "customdata", "startupscriptbase64", "customdatabase64")
        )
        or part.startswith(
            ("userdata", "rawstate", "rawplan", "terraformstate", "terraformplan")
        )
        for part in parts
    )


def _private_name(name: str) -> bool:
    # Ask the existing boundary to classify the key rather than maintaining a
    # parallel credential-name vocabulary here.
    probe = "cloud-screening-probe-value"
    return redact_value({name: probe}).get(name) != probe


def _numeric_value(value: object) -> Decimal | None:
    if type(value) not in (int, float, str):
        return None
    try:
        numeric = Decimal(str(value))
    except InvalidOperation:
        return None
    return numeric if numeric.is_finite() else None


def _screen_numeric_text(value: str, secrets: set[Decimal]) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if _numeric_value(token) in secrets:
            return "[REDACTED]"
        # In an identifier such as resource-8675309 the hyphen is a separator,
        # not a negative sign. Preserve it while screening the numeric echo.
        if (
            token.startswith(("-", "+"))
            and match.start() > 0
            and value[match.start() - 1].isalnum()
            and _numeric_value(token[1:]) in secrets
        ):
            return token[0] + "[REDACTED]"
        return token

    return _NUMERIC_TOKEN.sub(replace, value)


def _raw_scalar(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if "\n" in value or "\r" in value or "\x00" in value:
        return True
    if value.lstrip().startswith(("{", "[")):
        try:
            return isinstance(json.loads(value), (dict, list))
        except ValueError:
            pass
    return False


def redact_snapshot(
    snapshot: LiveContextSnapshot,
    *,
    mask_accounts: bool = True,
    sensitive_values: Iterable[str] = (),
    account_identifiers: Iterable[str] = (),
    address_map_out: dict[str, str] | None = None,
) -> LiveContextSnapshot:
    """Return a newly validated digest over redacted, account-maskable metadata.

    Opaque scope_id is server-issued identity, never an account display. It is
    retained unchanged; sensitive material in that identity rejects the snapshot.
    Masking supports AWS numeric IDs and explicitly supplied provider account IDs.
    This is a selected-metadata boundary, not general-purpose PII classification.
    When supplied, the caller's private address map receives the exact mapping
    after validation, so related diagnostics can use the same screened addresses.
    """
    source = validate_snapshot(snapshot)
    raw = source.model_dump(mode="json", exclude={"digest", "partial"})
    records = []
    blocked_values: set[str] = set()
    numeric_secrets: set[Decimal] = set()
    for resource in raw["resources"]:
        row = dict(resource)
        row["identity"] = dict(
            resource["identity"], tags=dict(resource["identity"]["tags"])
        )
        row["facts"] = {fact["name"]: fact["value"] for fact in resource["facts"]}
        for name, value in list(row["facts"].items()) + list(
            row["identity"]["tags"].items()
        ):
            if _private_name(name) or _raw_name(name):
                numeric = _numeric_value(value)
                if numeric is not None:
                    numeric_secrets.add(numeric)
            if (
                (_raw_name(name) or _raw_scalar(value))
                and isinstance(value, str)
                and value
            ):
                blocked_values.add(value)
        records.append(row)
    raw["resources"] = records
    provided = tuple(sensitive_values)
    for value in provided:
        numeric = _numeric_value(value)
        if numeric is not None:
            numeric_secrets.add(numeric)
    known = tuple(
        value
        for value in provided
        + tuple(blocked_values)
        + sensitive_artifact_values(json.dumps(raw).encode("utf-8"))
        if _numeric_value(value) not in numeric_secrets
    )
    # Keep numeric private fields out of the generic screening pass after
    # collecting them. Otherwise that helper discovers strings such as a PIN1
    # and rewrites incidental digits in public region/time protocol fields.
    projected = dict(raw)
    projected["resources"] = [
        dict(
            row,
            facts={
                name: value
                for name, value in row["facts"].items()
                if not (_private_name(name) or _raw_name(name))
            },
            identity=dict(
                row["identity"],
                tags={
                    name: value
                    for name, value in row["identity"]["tags"].items()
                    if not (_private_name(name) or _raw_name(name))
                },
            ),
        )
        for row in records
    ]
    screened = redact_value(projected, sensitive_values=known)
    if (
        screened["scope_id"] != source.scope_id
        or _screen_numeric_text(source.scope_id, numeric_secrets) != source.scope_id
        or redact_text(source.scope_id, sensitive_values=known) != source.scope_id
    ):
        raise ValueError("Authorized scope identity contains sensitive material")
    for name in ("provider", "project_id", "regions", "issued_actions"):
        if screened[name] != raw[name]:
            raise ValueError("Snapshot protocol metadata contains sensitive material")
    accounts = tuple(
        sorted(
            set(account_identifiers) | set(_ACCOUNT.findall(source.scope)),
            key=len,
            reverse=True,
        )
    )
    changed = screened != raw
    blocked = source.redaction_status == "sensitive_blocked"

    def text(value: str) -> str:
        nonlocal changed
        clean = _screen_numeric_text(
            redact_text(value, sensitive_values=known), numeric_secrets
        )
        if mask_accounts:
            clean = _ACCOUNT.sub("[MASKED_ACCOUNT]", clean)
            for account in accounts:
                if account:
                    clean = clean.replace(account, "[MASKED_ACCOUNT]")
        changed = changed or clean != value
        return clean

    for field in ("scope",):
        screened[field] = text(screened[field])
    for original, row in zip(records, screened["resources"]):
        removed = False
        facts = []
        for name, old_value in original["facts"].items():
            clean_name = text(name)
            if (
                _raw_name(name)
                or _private_name(name)
                or _raw_scalar(old_value)
                or clean_name != name
            ):
                removed = True
                continue
            value = row["facts"][name]
            if type(value) in (int, float) and _numeric_value(value) in numeric_secrets:
                value = "[REDACTED]"
            elif isinstance(value, str):
                value = text(value)
            elif (
                mask_accounts
                and type(value) in (int, float)
                and value == int(value)
                and (
                    str(int(value)) in accounts
                    or (
                        _ACCOUNT.fullmatch(str(int(value)))
                        and re.sub(r"[^a-z0-9]", "", name.lower())
                        in {"account", "accountid", "awsaccountid"}
                    )
                )
            ):
                value = "[MASKED_ACCOUNT]"
            removed = removed or value != old_value
            facts.append({"name": clean_name, "value": value})
        row["facts"] = facts
        tags = []
        for name, old_value in original["identity"]["tags"].items():
            if _raw_name(name) or _private_name(name) or _raw_scalar(old_value):
                removed = True
                continue
            key = text(name)
            value = text(row["identity"]["tags"][name])
            # Secret-bearing dictionary keys are removed, not replaced by an
            # ambiguous shared marker. Numeric account masking is safe in tags.
            if (
                redact_text(name, sensitive_values=known) != name
                or _screen_numeric_text(name, numeric_secrets) != name
            ):
                removed = True
                continue
            tags.append((key, value))
            removed = removed or value != old_value
        row["identity"]["tags"] = tags
        for name, value in list(row["identity"].items()):
            if isinstance(value, str):
                row["identity"][name] = text(value)
        for name in ("cause", "missing_permission"):
            if isinstance(row[name], str):
                row[name] = text(row[name])
        if removed:
            blocked = changed = True
            if row["status"] == ReadStatus.READ.value:
                row["status"] = ReadStatus.PARTIAL.value
                row["cause"] = "sensitive_fields_removed"
    screened["redaction_status"] = (
        "sensitive_blocked"
        if blocked
        else "redacted"
        if changed or source.redaction_status == "redacted"
        else "none"
    )
    result = build_snapshot(**screened)
    if address_map_out is not None:
        address_map_out.update(
            (original["identity"]["address"], row["identity"]["address"])
            for original, row in zip(records, screened["resources"])
        )
    return result
