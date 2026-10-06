"""Local credential screening for prompts, reports, snapshots, and errors."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any, Iterable, get_args
from urllib.parse import quote, quote_plus, unquote

import yaml
from config import configured_credential_values
from parsers.cloudformation_parser import _CloudFormationLoader
from evidence.models import (
    ContextSourceType,
    EvidenceSourceType,
    DeterminismLevel,
    FindingEvidenceClassification,
    ContextSourceFreshness,
    OwnerSignalScope,
    RiskSeverity,
    DeployRecommendation,
    ContextConfidenceLevel,
)

REDACTED = "[REDACTED]"
BLOCKED_CONTENT = (
    "[Sensitive artifact content blocked; review the redaction status in the report.]"
)
REDACTION_WARNING = "Sensitive content was redacted from report data; sensitive artifact snapshots were blocked."
_SECRET_NAME = r"(?:[\w.-]*(?:password|passwd|api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|token|credentials?|private[_-]?key|connection[_-]?string))"
# Start once per maximal identifier, including dotted/hyphenated names. Word
# boundaries would restart the greedy prefix at every dot or hyphen.
_ASSIGNMENT_PREFIX = rf"(?P<prefix>(?<![\w.-]){_SECRET_NAME}(?![\w.-])[\"']?\s*[:=]\s*)"
_ASSIGNMENT = re.compile(
    _ASSIGNMENT_PREFIX
    + r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|''|[^'\\])*'|[^\s,;\}\]\"']+)",
    re.IGNORECASE | re.DOTALL,
)
_BLOCK_ASSIGNMENT = re.compile(
    _ASSIGNMENT_PREFIX
    + r"[|>](?:[+-][1-9]?|[1-9][+-]?)?[ \t]*(?:\#[^\r\n]*)?\r?\n"
    + r"(?P<value>(?:(?:[ \t]+[^\r\n]*|[ \t]*)\r?\n|[ \t]+[^\r\n]*$)+)",
    re.IGNORECASE,
)
_HEREDOC_ASSIGNMENT = re.compile(
    "(?i:"
    + _ASSIGNMENT_PREFIX
    + ")"
    + r"<<-?(?P<delimiter>[A-Za-z_][A-Za-z0-9_]*)[ \t]*\r?\n"
    + r"(?P<value>.*?)(?:^[ \t]*(?P=delimiter)[ \t]*(?:\r?\n|$)|\Z)",
    re.MULTILINE | re.DOTALL,
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----.*?"
    r"(?:-----END (?:[A-Z0-9]+ )?PRIVATE KEY-----|$)",
    re.DOTALL,
)
_TOKEN = re.compile(
    r"\b(?:AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{12,})\b"
)
_AUTHORIZATION = re.compile(
    r"(?i)(\b(?:authorization[\"']?\s*[:=]\s*[\"']?\s*)?"
    r"\b(?:bearer|basic)\s+)(?P<credential>[A-Za-z0-9._~+/=-]+)"
)
_URL_CREDENTIAL = re.compile(
    r"((?<![\w+.-])[a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/@]+:(?P<credential>[^\s/@]+)@"
)
_QUERY_PARAMETER = re.compile(
    r"(?P<prefix>[?&])(?P<name>[^=&\s\"'<>#]+)=(?P<credential>[^&#\s\"'<>]*)"
)
_SENSITIVE_QUERY_NAMES = {
    "code",
    "state",
    "session",
    "sessionid",
    "session_id",
    "sig",
    "signature",
    "key",
    "authorization",
    "samlresponse",
}

_SEVERITIES = set(get_args(RiskSeverity))
_ACTIONS = {
    "create",
    "modify",
    "replace",
    "destroy",
    "delete",
    "apply",
    "no-op",
    "read",
    "update",
}
_SOURCES = set(get_args(ContextSourceType)) | set(get_args(EvidenceSourceType))
_PROTOCOL_VALUES = {
    "severity": _SEVERITIES,
    "overall_severity": _SEVERITIES,
    "severity_hint": _SEVERITIES,
    "recommendation": set(get_args(DeployRecommendation)),
    "action": _ACTIONS,
    "normalized_action": _ACTIONS,
    "operation": _ACTIONS,
    "tool": {
        "terraform",
        "kubernetes",
        "ansible",
        "jenkins",
        "cloudformation",
        "unsupported",
    },
    "source_type": _SOURCES,
    "source_kind": _SOURCES,
    "kind": {"secret"},
    "determinism_level": set(get_args(DeterminismLevel)),
    "status": {
        "accepted",
        "excluded",
        "failed",
        "sensitive",
        "parsed",
        "skipped",
        "ready",
        "pending",
        "persisted",
    },
    "intake_status": {"ready", "unsupported", "sensitive"},
    "parse_status": {"parsed", "failed", "skipped"},
    "redaction_status": {"none", "redacted", "sensitive_blocked", "unknown"},
    "confidence_level": set(get_args(ContextConfidenceLevel)),
    "confidence_label": set(get_args(ContextConfidenceLevel)),
    "complexity": set(get_args(ContextConfidenceLevel)),
    "evidence_classification": set(get_args(FindingEvidenceClassification)),
    "freshness_status": set(get_args(ContextSourceFreshness)),
    "incident_index_freshness_status": set(get_args(ContextSourceFreshness)),
    "scope": set(get_args(OwnerSignalScope)),
    "match_type": {"organization_incident", "public_risk_pattern"},
    "source": {
        "llm",
        "fallback",
        "heuristic-only",
        "heuristic+llm",
        "environment",
        "database",
    },
    "report_schema_version": {"v1", "v2"},
}
_SECRET_SUFFIXES = (
    "password",
    "passwd",
    "apikey",
    "accesskey",
    "secret",
    "secretkey",
    "token",
    "credential",
    "credentials",
    "privatekey",
    "connectionstring",
)
_RAW_CONTENT_KEYS = {
    "rawartifact",
    "rawcontent",
    "rawprompt",
    "rawresponse",
    "rawiac",
    "artifactcontent",
}


def _secret_key(key: str) -> bool:
    return re.sub(r"[^a-z0-9]", "", key.lower()).endswith(_SECRET_SUFFIXES)


def _sensitive_query_name(value: str) -> bool:
    for _ in range(9):
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded
    return value.lower() in _SENSITIVE_QUERY_NAMES or _secret_key(value)


def _sensitive_variants(item: str) -> set[str]:
    variants = {item, item.strip(), "".join(item.splitlines()).strip()}
    variants.difference_update({"", REDACTED, REDACTED[:-1]})
    return variants | {
        encoded
        for value in variants
        for encoded in (
            quote(value, errors="surrogatepass"),
            quote(value, safe="", errors="surrogatepass"),
            quote_plus(value, errors="surrogatepass"),
        )
    }


def _text_sensitive_values(text: str) -> set[str]:
    found: set[str] = set()
    for match in _ASSIGNMENT.finditer(text):
        raw = match.group("value")
        literal = raw[1:-1] if raw.startswith(('"', "'")) else raw
        found.update(_sensitive_variants(literal))
        if raw.startswith('"'):
            # HCL quoted strings share JSON escapes, plus eight-digit Unicode.
            # Decode only supported escapes; never evaluate source expressions.
            def decode_escape(escape: re.Match[str]) -> str:
                value = escape.group(0)[1:]
                if value.startswith(("u", "U")):
                    try:
                        return chr(int(value[1:], 16))
                    except ValueError:
                        return escape.group(0)
                return {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}[value]

            decoded = re.sub(
                r'\\(?:[nrt"\\]|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})',
                decode_escape,
                literal,
            )
            found.update(_sensitive_variants(decoded))
    for pattern in (_BLOCK_ASSIGNMENT, _HEREDOC_ASSIGNMENT):
        for match in pattern.finditer(text):
            found.update(_sensitive_variants(match.group("value")))
    found.difference_update({"|", ">"})
    for pattern, group in (
        (_TOKEN, 0),
        (_PRIVATE_KEY, 0),
        (_AUTHORIZATION, "credential"),
        (_URL_CREDENTIAL, "credential"),
    ):
        for match in pattern.finditer(text):
            found.update(_sensitive_variants(match.group(group)))
    for match in _QUERY_PARAMETER.finditer(text):
        if _sensitive_query_name(match.group("name")):
            found.update(_sensitive_variants(unquote(match.group("credential"))))
    return found


def redact_text(value: str, *, sensitive_values: Iterable[str] = ()) -> str:
    """Redact recognizable, configured, and locally identified credentials."""
    return _redact_text(
        value, sensitive_values=tuple(sensitive_values) + configured_credential_values()
    )


def redact_reference(
    value: str | None, *, sensitive_values: Iterable[str] = ()
) -> str | None:
    """Screen references and metadata with bounded decoding, preserving safe values."""
    if value is None:
        return None
    values = tuple(sensitive_values) + configured_credential_values()
    candidate = value
    for _ in range(9):
        if _redact_text(candidate, sensitive_values=values) != candidate:
            return REDACTED
        decoded = unquote(candidate)
        if decoded == candidate:
            return value
        candidate = decoded
    return REDACTED


def _redact_text(value: str, *, sensitive_values: Iterable[str] = ()) -> str:
    """Apply lexical screening with the caller's prepared credential context."""
    # Consume whole scalar bodies before replacing their header or delimiter.
    text = _HEREDOC_ASSIGNMENT.sub(lambda m: m.group("prefix") + REDACTED + "\n", value)
    text = _BLOCK_ASSIGNMENT.sub(lambda m: m.group("prefix") + REDACTED + "\n", text)
    variants = {
        variant for item in sensitive_values for variant in _sensitive_variants(item)
    }
    for secret in sorted(variants, key=len, reverse=True):
        if secret and secret != REDACTED:
            text = (
                re.sub(rf"(?<!\w){re.escape(secret)}(?!\w)", lambda _: REDACTED, text)
                if len(secret) < 4
                else text.replace(secret, REDACTED)
            )
    text = _PRIVATE_KEY.sub(REDACTED, text)
    text = _TOKEN.sub(REDACTED, text)
    text = _AUTHORIZATION.sub(lambda match: match.group(1) + REDACTED, text)
    text = _URL_CREDENTIAL.sub(lambda match: match.group(1) + REDACTED + "@", text)

    def replace_assignment(match: re.Match[str]) -> str:
        raw = match.group("value")
        # Keep a stable marker when screening an already redacted payload.
        if raw in {REDACTED, REDACTED[:-1]} or raw.strip("\"'") == REDACTED:
            return match.group(0)
        quote = raw[0] if raw.startswith(('"', "'")) else ""
        return match.group("prefix") + quote + REDACTED + quote

    text = _ASSIGNMENT.sub(replace_assignment, text)
    return _QUERY_PARAMETER.sub(
        lambda match: (
            match.group("prefix") + match.group("name") + "=" + REDACTED
            if _sensitive_query_name(match.group("name"))
            else match.group(0)
        ),
        text,
    )


def _screen_value(
    value: Any,
    sensitive_values: tuple[str, ...],
    found: set[str],
    changed: list[bool] | None = None,
) -> Any:
    active: set[int] = set()
    memo: dict[tuple[int, bool], Any] = {}
    hidden: dict[tuple[int, bool], Any] = {}
    hiding: set[int] = set()
    mask_memo: dict[tuple[int, int], Any] = {}
    # Masked values and parsed JSON strings create temporary containers. Retain
    # their sources so object IDs cannot be reused within these memo tables.
    memo_sources: list[Any] = []

    def mark_changed() -> None:
        if changed is not None:
            changed[0] = True

    def collect(item: str) -> None:
        # Block scalars carry a trailing newline; derived explanations often do not.
        found.update(_sensitive_variants(item))

    def hide(item: Any, depth: int = 0, *, encoded: bool = False) -> Any:
        if depth > 32 or id(item) in hiding:
            mark_changed()
            return BLOCKED_CONTENT
        mark_changed()
        if isinstance(item, bytes):
            collect(item.decode("utf-8", errors="replace"))
            collect(base64.b64encode(item).decode("ascii"))
            return REDACTED
        if isinstance(item, str):
            if item and item != REDACTED:
                collect(item)
                if encoded:
                    try:
                        normalized = re.sub(r"[ \t\r\n]", "", item)
                        decoded = base64.b64decode(normalized, validate=True).decode(
                            "utf-8"
                        )
                    except (ValueError, binascii.Error, UnicodeDecodeError):
                        pass
                    else:
                        collect(normalized)
                        collect(decoded)
            return REDACTED
        if isinstance(item, (dict, list, tuple)):
            cache_key = (id(item), encoded)
            if cache_key in hidden:
                return hidden[cache_key]
            hiding.add(id(item))
            try:
                result = (
                    {
                        str(key): hide(nested, depth + 1, encoded=encoded)
                        for key, nested in item.items()
                    }
                    if isinstance(item, dict)
                    else [hide(nested, depth + 1, encoded=encoded) for nested in item]
                )
                hidden[cache_key] = result
                memo_sources.append(item)
                return result
            finally:
                hiding.remove(id(item))
        # Safe YAML may resolve unquoted values to dates or other scalar types.
        if item is not None and not isinstance(item, bool):
            found.add(str(item))
        return REDACTED if item is not None else None

    def masked(item: Any, mask: Any, depth: int = 0) -> Any:
        if mask is True:
            return hide(item)
        if depth > 32:
            mark_changed()
            return BLOCKED_CONTENT
        cache_key = (id(item), id(mask))
        if cache_key in mask_memo:
            return mask_memo[cache_key]
        if isinstance(item, dict) and isinstance(mask, dict):
            result = {}
            mask_memo[cache_key] = result
            memo_sources.extend((item, mask))
            result.update(
                (key, masked(nested, mask.get(key), depth + 1))
                for key, nested in item.items()
            )
            return result
        if isinstance(item, list) and isinstance(mask, list):
            result = []
            mask_memo[cache_key] = result
            memo_sources.extend((item, mask))
            result.extend(
                masked(nested, mask[index] if index < len(mask) else None, depth + 1)
                for index, nested in enumerate(item)
            )
            return result
        return item

    def walk(item: Any, depth: int = 0, *, metadata: bool = False) -> Any:
        if isinstance(item, str):
            found.update(_text_sensitive_values(item))
            safe = _redact_text(item, sensitive_values=sensitive_values)
            if safe != item:
                mark_changed()
            return safe
        if not isinstance(item, (dict, list, tuple)):
            if (
                metadata
                and isinstance(item, (int, float))
                and not isinstance(item, bool)
                and str(item) in sensitive_values
            ):
                mark_changed()
                return REDACTED
            return item
        if id(item) in active or depth > 32:
            mark_changed()
            return BLOCKED_CONTENT
        cache_key = (id(item), metadata)
        if cache_key in memo:
            return memo[cache_key]
        active.add(id(item))
        try:
            if isinstance(item, (list, tuple)):
                result = [walk(nested, depth + 1, metadata=metadata) for nested in item]
                memo[cache_key] = result
                memo_sources.append(item)
                return result
            result = {}
            secret_object = str(item.get("kind", "")).lower() == "secret"
            secret_env = isinstance(item.get("name"), str) and _secret_key(item["name"])
            for key, nested in item.items():
                key_text = str(key)
                normalized = re.sub(r"[^a-z0-9]", "", key_text.lower())
                if key in {"before", "after", "values"}:
                    nested = masked(
                        nested,
                        item.get(f"{key}_sensitive", item.get("sensitive_values")),
                    )
                if normalized in _RAW_CONTENT_KEYS:
                    safe = BLOCKED_CONTENT
                    mark_changed()
                elif (
                    _secret_key(key_text)
                    or (secret_object and key in {"data", "stringData"})
                    or (secret_env and key == "value")
                    or (item.get("sensitive") is True and key == "value")
                    or (item.get("NoEcho") is True and key == "Default")
                ):
                    safe = hide(nested, encoded=secret_object and key == "data")
                elif key_text.endswith("_json") and isinstance(nested, str):
                    try:
                        decoded = json.loads(nested)
                    except (ValueError, TypeError):
                        safe = walk(nested, depth + 1, metadata=metadata)
                    else:
                        # JSON has no aliases, so this equality cannot expand a DAG.
                        screened = walk(decoded, depth + 1, metadata=metadata)
                        safe = json.dumps(screened) if screened != decoded else nested
                elif (
                    not metadata
                    and isinstance(nested, str)
                    and nested.lower() in _PROTOCOL_VALUES.get(key_text, set())
                ):
                    # Public enums retain their meaning even if a short secret
                    # happens to have the same spelling as an enum value.
                    safe = _redact_text(nested)
                    if safe != nested:
                        mark_changed()
                else:
                    safe = walk(
                        nested,
                        depth + 1,
                        metadata=metadata or normalized == "metadata",
                    )
                safe_key = _redact_text(
                    key_text, sensitive_values=sensitive_values if metadata else ()
                )
                if safe_key != key_text:
                    mark_changed()
                result[safe_key] = safe
            memo[cache_key] = result
            memo_sources.append(item)
            return result
        finally:
            active.remove(id(item))

    return walk(value)


def redact_value(value: Any, *, sensitive_values: Iterable[str] = ()) -> Any:
    """Screen nested JSON-like data without mutating the caller's objects."""
    found = {
        variant
        for item in tuple(sensitive_values) + configured_credential_values()
        for variant in _sensitive_variants(item)
    }
    # Collect from the whole input first so sibling order cannot expose an echo.
    _screen_value(value, (), found)
    return _screen_value(value, tuple(found), set())


def sensitive_artifact_values(raw_content: bytes | None) -> tuple[str, ...]:
    """Identify credential values locally, including K8s data and TF sensitive masks."""
    if not raw_content:
        return ()
    text = raw_content.decode("utf-8", errors="replace")
    found = _text_sensitive_values(text)
    if redact_text(text) != text and not found:
        # Authorization and credential-bearing URLs also block the snapshot.
        found.add(text)
    try:
        if text.lstrip().startswith(("{", "[")):
            try:
                documents = [json.loads(text)]
            except ValueError:
                documents = yaml.load_all(text, Loader=_CloudFormationLoader)  # nosec B506
        else:
            # YAML permits quoted keys, spacing and tags; lexical filters miss them.
            # Reuse the SafeLoader-derived CF loader; intrinsic tags remain inert.
            documents = yaml.load_all(text, Loader=_CloudFormationLoader)  # nosec B506
        for document in documents:
            changed = [False]
            _screen_value(document, (), found, changed)
            if changed[0] and not found:
                found.add(text)
    except (ValueError, yaml.YAMLError, RecursionError):
        # Failed parser messages are handled separately; never expose their input.
        pass
    return tuple(sorted(value for value in found if value and value != REDACTED))


def sensitive_submission_values(
    files: Iterable[tuple[str, bytes | None]],
) -> tuple[str, ...]:
    """Collect filename and artifact credentials locally across a submission."""
    found: set[str] = set()
    for filename, raw_content in files:
        found.update(_text_sensitive_values(filename))
        found.update(sensitive_artifact_values(raw_content))
    return tuple(sorted(found))
