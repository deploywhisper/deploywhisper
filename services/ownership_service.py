"""Ownership context helpers for reports."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatchcase
import re
from typing import Any

from evidence.models import OwnerSignal
from parsers.base import ParseBatchResult, UnifiedChange, is_non_mutating_action
from services.intake_service import (
    EXTERNAL_ARTIFACT_PREFIX,
    UNSAFE_ARTIFACT_PREFIX,
    artifact_name_has_traversal,
    artifact_name_is_ownership_untrusted,
    artifact_name_is_traversal_normalized,
)

CODEOWNERS_LOOKUP_ORDER = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
CODEOWNERS_MAX_BYTES = 3_000_000
OWNERSHIP_CONTEXT_TODO = (
    "Add CODEOWNERS or ownership mapping for analyzed files/resources."
)
HANDLE_OWNER_PATTERN = re.compile(
    r"^@[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
    r"(?:/[A-Za-z0-9](?:[A-Za-z0-9-]{0,98}[A-Za-z0-9])?)?$"
)
EMAIL_OWNER_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.,;:!?]+$")
TOPOLOGY_OWNER_LABEL_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._/ -]{0,126}[A-Za-z0-9])?$"
)


@dataclass(frozen=True)
class CodeownersMatch:
    owners: tuple[str, ...]
    pattern: str
    source_ref: str


@dataclass(frozen=True)
class OwnershipContext:
    owner_signals: tuple[OwnerSignal, ...]
    escalation_hints: tuple[str, ...]
    unmapped_subjects: tuple[str, ...]
    context_todos: tuple[str, ...]


@dataclass(frozen=True)
class CodeownersSource:
    source_ref: str
    content: str
    readable: bool = True
    root_prefix: str = ""


@dataclass(frozen=True)
class _CodeownersRule:
    pattern: str
    owners: tuple[str, ...]
    source_ref: str
    root_prefix: str


def _clean_texts(values: list[Any]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _normalized_subject(path: str) -> str:
    normalized = str(path or "").strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _untrusted_display_subject(subject: str) -> str:
    normalized = _normalized_subject(subject)
    normalized_lower = normalized.lower()
    labels_by_prefix = {
        UNSAFE_ARTIFACT_PREFIX: "untrusted upload",
        EXTERNAL_ARTIFACT_PREFIX: "external artifact",
    }
    for prefix, label in labels_by_prefix.items():
        prefix_lower = prefix.lower()
        if normalized_lower == prefix_lower:
            return f"{label}: unknown-file"
        if normalized_lower.startswith(f"{prefix_lower}/"):
            display_subject = normalized[len(prefix) + 1 :] or "unknown-file"
            return f"{label}: {display_subject}"
    return normalized or "unknown-file"


def _is_codeowners_source(name: str) -> bool:
    return _codeowners_lookup_match(name) is not None


def _codeowners_lookup_match(name: str) -> tuple[str, str] | None:
    normalized = _normalized_subject(name)
    for source_ref in CODEOWNERS_LOOKUP_ORDER:
        if normalized == source_ref:
            return source_ref, ""
    for source_ref in sorted(CODEOWNERS_LOOKUP_ORDER, key=len, reverse=True):
        suffix = f"/{source_ref}"
        if normalized.endswith(suffix):
            root_prefix = normalized[: -len(suffix)].strip("/")
            if root_prefix:
                return source_ref, root_prefix
    return None


def _decode_codeowners_content(raw_content: bytes | str | None) -> str | None:
    if raw_content is None:
        return None
    if isinstance(raw_content, str):
        return raw_content.removeprefix("\ufeff")
    try:
        return raw_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _split_codeowners_rule(line: str) -> tuple[str, list[str]] | None:
    pattern_chars: list[str] = []
    index = 0
    while index < len(line):
        char = line[index]
        if char == "\\" and index + 1 < len(line):
            next_char = line[index + 1]
            pattern_chars.append(" " if next_char == " " else next_char)
            index += 2
            continue
        if char.isspace():
            pattern = "".join(pattern_chars).strip()
            owners = line[index:].split()
            return (pattern, owners) if pattern else None
        pattern_chars.append(char)
        index += 1
    pattern = "".join(pattern_chars).strip()
    return (pattern, []) if pattern else None


def _strip_codeowners_comment(line: str) -> str:
    escaped = False
    chars: list[str] = []
    for char in line:
        if char == "#" and not escaped:
            break
        chars.append(char)
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    return "".join(chars).strip()


def _valid_owner_token(owner: str) -> bool:
    if HANDLE_OWNER_PATTERN.match(owner):
        return True
    return EMAIL_OWNER_PATTERN.match(owner) is not None


def _codeowners_source_key(source_ref: str, root_prefix: str) -> str:
    return f"{root_prefix}\0{source_ref}"


def uploaded_codeowners_sources(
    files: list[tuple[str, bytes | str | None]],
) -> tuple[CodeownersSource, ...]:
    """Extract uploaded CODEOWNERS content using GitHub's lookup order."""
    by_ref: dict[str, CodeownersSource] = {}
    for name, raw_content in files:
        if (
            artifact_name_has_traversal(name)
            or artifact_name_is_traversal_normalized(name)
            or artifact_name_is_ownership_untrusted(name)
        ):
            continue
        lookup_match = _codeowners_lookup_match(name)
        if lookup_match is None:
            continue
        source_ref, root_prefix = lookup_match
        source_key = _codeowners_source_key(source_ref, root_prefix)
        if source_key in by_ref:
            continue
        content = _decode_codeowners_content(raw_content)
        if content is None:
            by_ref[source_key] = CodeownersSource(
                source_ref=_normalized_subject(name),
                content="",
                readable=False,
                root_prefix=root_prefix,
            )
            continue
        readable = len(content.encode("utf-8")) <= CODEOWNERS_MAX_BYTES
        by_ref[source_key] = CodeownersSource(
            source_ref=_normalized_subject(name),
            content=content if readable else "",
            readable=readable,
            root_prefix=root_prefix,
        )
    root_prefixes = sorted({source.root_prefix for source in by_ref.values()})
    sources: list[CodeownersSource] = []
    for root_prefix in root_prefixes:
        for source_ref in CODEOWNERS_LOOKUP_ORDER:
            source = by_ref.get(_codeowners_source_key(source_ref, root_prefix))
            if source is not None:
                sources.append(source)
                break
    if "" in root_prefixes:
        rootless_sources = [source for source in sources if source.root_prefix == ""]
        prefixed_sources = [source for source in sources if source.root_prefix != ""]
        return tuple(rootless_sources + prefixed_sources)
    return tuple(sources)


def _load_codeowners_rules(
    sources: tuple[CodeownersSource, ...] = (),
) -> list[_CodeownersRule]:
    rules: list[_CodeownersRule] = []
    seen_roots: set[str] = set()
    for source in sources:
        root_key = _normalized_subject(source.root_prefix)
        if root_key in seen_roots:
            continue
        seen_roots.add(root_key)
        if (
            not source.readable
            or len(source.content.encode("utf-8")) > CODEOWNERS_MAX_BYTES
        ):
            continue
        for line in source.content.splitlines():
            stripped = _strip_codeowners_comment(line)
            if not stripped or stripped.startswith("#"):
                continue
            parsed = _split_codeowners_rule(stripped)
            if parsed is None:
                continue
            pattern, owners = parsed
            if _unsupported_codeowners_pattern(pattern):
                continue
            cleaned_owners = _clean_texts(owners)
            if cleaned_owners and not all(
                _valid_owner_token(owner) for owner in cleaned_owners
            ):
                continue
            rules.append(
                _CodeownersRule(
                    pattern=pattern,
                    owners=tuple(cleaned_owners),
                    source_ref=source.source_ref,
                    root_prefix=source.root_prefix,
                )
            )
    return rules


def _unsupported_codeowners_pattern(pattern: str) -> bool:
    return pattern.startswith("!")


def _split_path(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def _segment_match(pattern_segment: str, subject_segment: str) -> bool:
    return fnmatchcase(subject_segment, pattern_segment)


def _segments_match(
    pattern_segments: list[str],
    subject_segments: list[str],
) -> bool:
    if not pattern_segments:
        return not subject_segments
    pattern_head, *pattern_tail = pattern_segments
    if pattern_head == "**":
        return any(
            _segments_match(pattern_tail, subject_segments[index:])
            for index in range(len(subject_segments) + 1)
        )
    if not subject_segments:
        return False
    return _segment_match(pattern_head, subject_segments[0]) and _segments_match(
        pattern_tail,
        subject_segments[1:],
    )


def _collapse_globstar_directory_segments(pattern_segments: list[str]) -> list[str]:
    collapsed: list[str] = []
    for index, segment in enumerate(pattern_segments):
        if segment == "**" and index < len(pattern_segments) - 1:
            continue
        collapsed.append(segment)
    return collapsed


def _directory_segments_match(
    pattern_segments: list[str],
    subject_segments: list[str],
) -> bool:
    if len(subject_segments) < len(pattern_segments):
        return False
    return _segments_match(pattern_segments, subject_segments[: len(pattern_segments)])


def _path_pattern_matches(
    pattern_segments: list[str],
    subject_segments: list[str],
    *,
    directory_match: bool,
) -> bool:
    if _segments_match(pattern_segments, subject_segments):
        return True
    collapsed_segments = _collapse_globstar_directory_segments(pattern_segments)
    if collapsed_segments != pattern_segments and _segments_match(
        collapsed_segments,
        subject_segments,
    ):
        return True
    if directory_match:
        return _directory_segments_match(pattern_segments, subject_segments)
    return False


def _pattern_matches(pattern: str, subject: str) -> bool:
    normalized_subject = _normalized_subject(subject)
    if pattern == "*":
        return True
    normalized_pattern = pattern.strip().replace("\\", "/")
    if not normalized_pattern:
        return False
    anchored = normalized_pattern.startswith("/")
    directory_pattern = normalized_pattern.endswith("/")
    normalized_pattern = normalized_pattern.strip("/")
    subject_segments = _split_path(normalized_subject)
    pattern_segments = _split_path(normalized_pattern)
    if not pattern_segments:
        return False
    has_slash = "/" in normalized_pattern
    has_glob = any(marker in normalized_pattern for marker in "*?[")
    if anchored and not has_slash:
        if directory_pattern or not has_glob:
            return _directory_segments_match(pattern_segments, subject_segments)
        return len(subject_segments) == 1 and _segment_match(
            pattern_segments[0],
            subject_segments[0],
        )

    if not has_slash:
        if directory_pattern or not has_glob:
            return any(
                _directory_segments_match(pattern_segments, subject_segments[index:])
                for index in range(len(subject_segments))
            )
        return fnmatchcase(
            normalized_subject.rsplit("/", maxsplit=1)[-1], normalized_pattern
        )

    directory_match = directory_pattern or pattern_segments[-1] == "**"
    if anchored:
        return _path_pattern_matches(
            pattern_segments,
            subject_segments,
            directory_match=directory_match,
        )

    return _path_pattern_matches(
        pattern_segments,
        subject_segments,
        directory_match=directory_match,
    )


def _match_codeowners(
    subject: str,
    rules: list[_CodeownersRule],
    *,
    prefixed_roots: tuple[str, ...] = (),
) -> CodeownersMatch | None:
    matched: CodeownersMatch | None = None
    for rule in rules:
        if not rule.root_prefix and _subject_is_under_prefixed_root(
            subject,
            prefixed_roots,
        ):
            continue
        relative_subject = _subject_for_rule(subject, rule.root_prefix)
        if relative_subject is not None and _pattern_matches(
            rule.pattern, relative_subject
        ):
            matched = CodeownersMatch(
                owners=rule.owners,
                pattern=rule.pattern,
                source_ref=rule.source_ref,
            )
    return matched


def _subject_is_under_prefixed_root(
    subject: str, prefixed_roots: tuple[str, ...]
) -> bool:
    normalized_subject = _normalized_subject(subject)
    for root in prefixed_roots:
        normalized_root = _normalized_subject(root)
        if not normalized_root:
            continue
        if normalized_subject == normalized_root or normalized_subject.startswith(
            f"{normalized_root}/"
        ):
            return True
    return False


def _subject_for_rule(subject: str, root_prefix: str) -> str | None:
    normalized_subject = _normalized_subject(subject)
    normalized_prefix = _normalized_subject(root_prefix)
    if not normalized_prefix:
        return normalized_subject
    if normalized_subject == normalized_prefix:
        return ""
    prefix = f"{normalized_prefix}/"
    if normalized_subject.startswith(prefix):
        return normalized_subject[len(prefix) :]
    return None


def _service_owners(service: dict[str, Any]) -> list[str]:
    owners: list[str] = []
    owner = service.get("owner")
    if isinstance(owner, str):
        owners.append(owner)
    raw_owners = service.get("owners")
    if isinstance(raw_owners, list):
        owners.extend(value for value in raw_owners if isinstance(value, str))
    return [
        owner
        for owner in _clean_texts(owners)
        if _valid_owner_token(owner) or TOPOLOGY_OWNER_LABEL_PATTERN.fullmatch(owner)
    ]


def _topology_source_ref(topology: dict[str, Any] | None) -> str | None:
    if not isinstance(topology, dict):
        return None
    metadata = topology.get("metadata")
    if not isinstance(metadata, dict):
        return None
    import_metadata = metadata.get("import")
    if not isinstance(import_metadata, dict):
        return None
    source_ref = str(import_metadata.get("source_ref") or "").strip()
    return source_ref or None


def _resource_aliases(change: UnifiedChange) -> list[str]:
    aliases = change.metadata.get("resource_aliases", [])
    if not isinstance(aliases, list):
        return []
    return _clean_texts(aliases)


def _services_by_resource(
    topology: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(topology, dict):
        return {}
    services = topology.get("services")
    if not isinstance(services, list):
        return {}
    by_resource: dict[str, list[dict[str, Any]]] = {}
    for service in services:
        if not isinstance(service, dict):
            continue
        resource_keys = service.get("resource_keys")
        if not isinstance(resource_keys, list):
            continue
        for resource_key in _clean_texts(resource_keys):
            by_resource.setdefault(resource_key, []).append(service)
    return by_resource


def _matched_services_for_change(
    change: UnifiedChange,
    services_by_resource: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    exact_matches = services_by_resource.get(change.resource_id, [])
    if exact_matches:
        if _services_resolve_to_one_owner_context(exact_matches):
            return _unique_service_matches(
                [(change.resource_id, service) for service in exact_matches]
            )
        return []

    alias_matches: list[tuple[str, dict[str, Any]]] = []
    for resource_id in _resource_aliases(change):
        for service in services_by_resource.get(resource_id, []):
            alias_matches.append((resource_id, service))
    if _services_resolve_to_one_owner_context(
        [service for _, service in alias_matches]
    ):
        return _unique_service_matches(alias_matches)
    return []


def _has_service_candidates_for_change(
    change: UnifiedChange,
    services_by_resource: dict[str, list[dict[str, Any]]],
) -> bool:
    if services_by_resource.get(change.resource_id):
        return True
    return any(
        services_by_resource.get(resource_id)
        for resource_id in _resource_aliases(change)
    )


def _service_label(service: dict[str, Any]) -> str:
    label = str(service.get("label") or "").strip()
    if label:
        return label
    return str(service.get("id") or "").strip()


def _service_id(service: dict[str, Any]) -> str | None:
    service_id = str(service.get("id") or "").strip()
    return service_id or None


def _service_identity(service: dict[str, Any]) -> str:
    return _service_id(service) or _service_label(service)


def _service_owner_signature(service: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(_service_owners(service)))


def _services_resolve_to_one_owner_context(services: list[dict[str, Any]]) -> bool:
    signatures_by_identity: dict[str, set[tuple[str, ...]]] = {}
    owner_signatures: set[tuple[str, ...]] = set()
    for service in services:
        identity = _service_identity(service)
        if not identity:
            return False
        owner_signatures.add(_service_owner_signature(service))
        signatures_by_identity.setdefault(identity, set()).add(
            _service_owner_signature(service)
        )
    if len(owner_signatures) == 1 and next(iter(owner_signatures), ()):
        return True
    return len(signatures_by_identity) == 1 and all(
        len(signatures) == 1 for signatures in signatures_by_identity.values()
    )


def _unique_service_matches(
    matches: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    unique: list[tuple[str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for resource_id, service in matches:
        service_key = _service_id(service) or _service_label(service)
        key = (resource_id, service_key)
        if key in seen:
            continue
        seen.add(key)
        unique.append((resource_id, service))
    return unique


def _change_ownership_subject(
    change: UnifiedChange,
    *,
    fallback_file_name: str,
) -> str:
    resource_id = str(change.resource_id or "").strip()
    if resource_id:
        return resource_id
    source_file = str(change.source_file or "").strip()
    if source_file:
        return f"{source_file}:unknown-resource"
    file_name = str(fallback_file_name or "").strip()
    if file_name:
        return f"{file_name}:unknown-resource"
    return "unknown-resource"


def _file_signal(subject: str, match: CodeownersMatch) -> OwnerSignal:
    owners = list(match.owners)
    hint = f"Escalate file review for {subject} to {', '.join(owners)}."
    return OwnerSignal(
        scope="file",
        subject=subject,
        owners=owners,
        source="CODEOWNERS",
        source_ref=match.source_ref,
        matched_pattern=match.pattern,
        escalation_hint=hint,
    )


def _service_signal(
    *,
    service: dict[str, Any],
    resource_id: str,
    source_ref: str | None,
) -> OwnerSignal | None:
    owners = _service_owners(service)
    if not owners:
        return None
    subject = _service_label(service)
    if not subject:
        return None
    hint = f"Escalate service review for {subject} to {', '.join(owners)}."
    return OwnerSignal(
        scope="service",
        subject=subject,
        owners=owners,
        source="topology",
        source_ref=source_ref,
        resource_id=resource_id,
        service_id=_service_id(service),
        escalation_hint=hint,
    )


def _dedupe_signals(signals: list[OwnerSignal]) -> list[OwnerSignal]:
    unique: list[OwnerSignal] = []
    seen: set[tuple[Any, ...]] = set()
    for signal in signals:
        key = (
            signal.scope,
            signal.subject,
            tuple(signal.owners),
            signal.source,
            signal.source_ref,
            signal.resource_id,
            signal.service_id,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(signal)
    return unique


def build_ownership_context(
    parse_batch: ParseBatchResult,
    *,
    topology: dict[str, Any] | None = None,
    codeowners_sources: tuple[CodeownersSource, ...] = (),
) -> OwnershipContext:
    """Build deterministic ownership hints for analyzed files and resources."""
    rules = _load_codeowners_rules(codeowners_sources)
    prefixed_roots = tuple(
        _clean_texts([source.root_prefix for source in codeowners_sources])
    )
    signals: list[OwnerSignal] = []
    unmapped_subjects: list[str] = []
    file_owned_subjects: set[str] = set()
    file_unmapped_candidates: set[str] = set()
    untrusted_file_unmapped_candidates: set[str] = set()
    unknown_file_candidates: set[str] = set()
    files_with_service_ownership: set[str] = set()
    files_with_unresolved_changes: set[str] = set()
    files_with_mutating_changes: set[str] = set()

    analyzed_files = [
        file_result
        for file_result in parse_batch.files
        if file_result.status == "failed"
        or (file_result.status == "parsed" and file_result.changes)
    ]
    for file_result in analyzed_files:
        subject = _normalized_subject(file_result.file_name)
        if not subject:
            if file_result.status == "failed":
                unmapped_subjects.append("unknown-file")
            else:
                unknown_file_candidates.add(subject)
            continue
        if artifact_name_is_ownership_untrusted(subject):
            unmapped_subjects.append(_untrusted_display_subject(subject))
            if file_result.status != "failed":
                untrusted_file_unmapped_candidates.add(subject)
            continue
        match = _match_codeowners(subject, rules, prefixed_roots=prefixed_roots)
        if match is None or not match.owners:
            file_unmapped_candidates.add(subject)
            continue
        signals.append(_file_signal(subject, match))
        file_owned_subjects.add(subject)

    services_by_resource = _services_by_resource(topology)
    topology_source_ref = _topology_source_ref(topology)
    parsed_files = [
        file_result
        for file_result in analyzed_files
        if file_result.status == "parsed" and file_result.changes
    ]
    for file_result in parsed_files:
        for change in file_result.changes:
            if is_non_mutating_action(change.action):
                continue
            files_with_mutating_changes.add(_normalized_subject(file_result.file_name))
            matched_services = _matched_services_for_change(
                change, services_by_resource
            )
            if not matched_services:
                if (
                    not _has_service_candidates_for_change(change, services_by_resource)
                    and _normalized_subject(file_result.file_name)
                    in file_owned_subjects
                ):
                    continue
                unmapped_subjects.append(
                    _change_ownership_subject(
                        change,
                        fallback_file_name=file_result.file_name,
                    )
                )
                files_with_unresolved_changes.add(
                    _normalized_subject(file_result.file_name)
                )
                continue
            for resource_id, service in matched_services:
                signal = _service_signal(
                    service=service,
                    resource_id=resource_id,
                    source_ref=topology_source_ref,
                )
                if signal is None:
                    subject = _service_label(service) or _change_ownership_subject(
                        change,
                        fallback_file_name=file_result.file_name,
                    )
                    unmapped_subjects.append(subject)
                    files_with_unresolved_changes.add(
                        _normalized_subject(file_result.file_name)
                    )
                    continue
                signals.append(signal)
                files_with_service_ownership.add(
                    _normalized_subject(file_result.file_name)
                )

    parsed_file_subjects = {
        _normalized_subject(file_result.file_name) for file_result in parsed_files
    }
    for subject in sorted(file_unmapped_candidates):
        if (
            subject in parsed_file_subjects
            and subject not in files_with_mutating_changes
        ):
            continue
        if (
            subject in parsed_file_subjects
            and subject in files_with_service_ownership
            and subject not in files_with_unresolved_changes
        ):
            continue
        unmapped_subjects.append(subject)
    for subject in sorted(unknown_file_candidates):
        if (
            subject in files_with_service_ownership
            and subject not in files_with_unresolved_changes
        ):
            continue
        if subject in files_with_unresolved_changes:
            continue
        unmapped_subjects.append("unknown-file")
    cleared_untrusted_subjects = {
        subject
        for subject in untrusted_file_unmapped_candidates
        if subject in files_with_service_ownership
        and subject not in files_with_unresolved_changes
    }
    if cleared_untrusted_subjects:
        cleared_subject_counts = Counter(cleared_untrusted_subjects)
        cleared_subject_counts.update(
            _untrusted_display_subject(subject)
            for subject in cleared_untrusted_subjects
        )
        retained_unmapped_subjects: list[str] = []
        for subject in unmapped_subjects:
            if cleared_subject_counts[subject] > 0:
                cleared_subject_counts[subject] -= 1
                continue
            retained_unmapped_subjects.append(subject)
        unmapped_subjects = retained_unmapped_subjects

    unique_signals = _dedupe_signals(signals)
    escalation_hints = tuple(
        _clean_texts([signal.escalation_hint for signal in unique_signals])
    )
    unique_unmapped = tuple(_clean_texts(unmapped_subjects))
    todos = (OWNERSHIP_CONTEXT_TODO,) if unique_unmapped else ()
    return OwnershipContext(
        owner_signals=tuple(unique_signals),
        escalation_hints=escalation_hints,
        unmapped_subjects=unique_unmapped,
        context_todos=todos,
    )
