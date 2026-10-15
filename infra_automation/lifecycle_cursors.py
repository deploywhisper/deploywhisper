"""Ephemeral signed pagination state for the singleton application profile."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import hmac
import json
import re
import secrets
from threading import RLock
import time

from infra_automation.contracts import SAFE_INTEGER
from infra_automation.lifecycle import CursorEnvelope, LifecycleError

BindingValue = str | int | None
Position = tuple[datetime, str]
_TOKEN = re.compile(r"[0-9a-f]{32}\.[0-9a-f]{64}", re.ASCII)
_IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", re.ASCII)


@dataclass(frozen=True)
class PageState:
    """Immutable query context; never a replacement for live authorization."""

    snapshot_id: str
    snapshot_sequence: int
    before: Position | None
    binding: tuple[tuple[str, BindingValue], ...]
    limit: int
    expires_at: float


def _integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _binding(value: dict[str, BindingValue]) -> tuple[tuple[str, BindingValue], ...]:
    if not isinstance(value, dict) or not 1 <= len(value) <= 32:
        raise LifecycleError(409)
    for key, item in value.items():
        if (
            type(key) is not str
            or not 1 <= len(key) <= 64
            or not _IDENTIFIER.fullmatch(key)
        ):
            raise LifecycleError(409)
        if item is None or _integer(item, -SAFE_INTEGER, SAFE_INTEGER):
            continue
        if type(item) is str and len(item) <= 256:
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeError:
                raise LifecycleError(409) from None
            continue
        raise LifecycleError(409)
    return tuple(sorted(value.items()))


class CursorStore:
    """Bounded process-local contexts signed with a random process-local key.

    Continuations remain replayable until their original expiry. Eviction and
    process restart invalidate tokens; neither creates a fresh pagination scope.
    The caller must authorize each page and constrain its rows by both the saved
    insertion sequence and descending timestamp/ID position.
    """

    def __init__(
        self,
        *,
        max_states: int = 1024,
        ttl_seconds: int = 900,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not _integer(max_states, 1, 1024) or not _integer(ttl_seconds, 1, 900):
            raise ValueError("Invalid cursor store bounds.")
        self._max_states = max_states
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._key = secrets.token_bytes(32)
        self._states: OrderedDict[str, PageState] = OrderedDict()
        self._lock = RLock()

    def _expire(self, now: float) -> None:
        # Pages may be finished out of order, so expiry need not follow insertion.
        for token_id, state in tuple(self._states.items()):
            if state.expires_at <= now:
                del self._states[token_id]

    def _signature(self, token_id: str, state: PageState) -> str:
        context = {
            "token_id": token_id,
            "snapshot_id": state.snapshot_id,
            "snapshot_sequence": state.snapshot_sequence,
            "before": (
                [state.before[0].isoformat(), state.before[1]]
                if state.before is not None
                else None
            ),
            "binding": state.binding,
            "limit": state.limit,
            "expires_at": state.expires_at,
        }
        payload = json.dumps(
            context, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def begin(
        self,
        *,
        binding: dict[str, BindingValue],
        limit: int,
        cursor: str | None,
        snapshot_sequence: int,
    ) -> PageState:
        bounded_binding = _binding(binding)
        if not _integer(limit, 1, 100) or not _integer(
            snapshot_sequence, 0, SAFE_INTEGER
        ):
            raise LifecycleError(409)
        with self._lock:
            now = self._clock()
            self._expire(now)
            if cursor is None:
                return PageState(
                    snapshot_id=secrets.token_hex(16),
                    snapshot_sequence=snapshot_sequence,
                    before=None,
                    binding=bounded_binding,
                    limit=limit,
                    expires_at=now + self._ttl_seconds,
                )
            if type(cursor) is not str or not _TOKEN.fullmatch(cursor):
                raise LifecycleError(409)
            token_id, signature = cursor.split(".")
            state = self._states.get(token_id)
            if (
                state is None
                or not hmac.compare_digest(signature, self._signature(token_id, state))
                or state.binding != bounded_binding
                or state.limit != limit
            ):
                raise LifecycleError(409)
            return state

    def finish(
        self,
        state: PageState,
        *,
        position: Position | None,
        last_sequence: int,
        has_more: bool,
    ) -> CursorEnvelope:
        if (
            not isinstance(state, PageState)
            or type(has_more) is not bool
            or not _integer(last_sequence, 0, state.snapshot_sequence)
            or (has_more and position is None)
        ):
            raise LifecycleError(409)
        if position is not None and (
            type(position) is not tuple
            or len(position) != 2
            or type(position[0]) is not datetime
            or type(position[1]) is not str
            or not _IDENTIFIER.fullmatch(position[1])
        ):
            raise LifecycleError(409)
        with self._lock:
            now = self._clock()
            self._expire(now)
            if state.expires_at <= now:
                raise LifecycleError(409)
            next_cursor = None
            if has_more:
                next_state = replace(state, before=position)
                token_id = secrets.token_hex(16)
                next_cursor = f"{token_id}.{self._signature(token_id, next_state)}"
                while len(self._states) >= self._max_states:
                    self._states.popitem(last=False)
                self._states[token_id] = next_state
            return CursorEnvelope(
                snapshot_id=state.snapshot_id,
                next_cursor=next_cursor,
                limit=state.limit,
                last_sequence=last_sequence,
                truncated=has_more,
            )


cursor_store = CursorStore()
