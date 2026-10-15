"""Bounded pagination contexts preserve scope and insertion snapshots."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
import unittest

from infra_automation.lifecycle import LifecycleError
from infra_automation.lifecycle_cursors import CursorStore


class LifecycleCursorTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.store = CursorStore(clock=lambda: self.now)
        self.binding = {
            "principal": "human-1",
            "authentication_version": 1,
            "membership_version": 2,
            "project_id": 3,
            "workspace_id": None,
            "family": "workflows",
        }
        self.position = (datetime(2026, 10, 14), "workflow-1")

    def begin(self, store=None, cursor=None, **changes):
        arguments = dict(
            binding=self.binding, limit=25, cursor=cursor, snapshot_sequence=100
        )
        arguments.update(changes)
        return (store or self.store).begin(**arguments)

    def token(self, store=None):
        store = store or self.store
        state = self.begin(store)
        return state, store.finish(
            state, position=self.position, last_sequence=90, has_more=True
        )

    def conflict(self, operation):
        with self.assertRaises(LifecycleError) as caught:
            operation()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertNotIn("human-1", str(caught.exception))

    def test_continuation_keeps_snapshot_and_fixed_expiry(self):
        state, page = self.token()
        self.now += 300
        following = self.begin(cursor=page.next_cursor, snapshot_sequence=200)
        self.assertEqual(following.snapshot_sequence, 100)
        self.assertEqual(following.snapshot_id, state.snapshot_id)
        self.assertEqual(following.before, self.position)
        self.assertEqual(following.expires_at, state.expires_at)
        final = self.store.finish(
            following,
            position=(self.position[0] - timedelta(seconds=1), "workflow-2"),
            last_sequence=80,
            has_more=False,
        )
        self.assertIsNone(final.next_cursor)
        self.assertFalse(final.truncated)
        self.assertFalse(final.gap)
        self.assertEqual(final.last_sequence, 80)

    def test_binding_and_page_size_cannot_change(self):
        _, page = self.token()
        for field, value in self.binding.items():
            with self.subTest(field=field):
                altered = {**self.binding, field: "changed"}
                self.conflict(
                    lambda: self.begin(cursor=page.next_cursor, binding=altered)
                )
        self.conflict(lambda: self.begin(cursor=page.next_cursor, limit=26))
        # The caller cannot mutate the captured dictionary through its original.
        self.binding["principal"] = "other"
        self.conflict(lambda: self.begin(cursor=page.next_cursor))

    def test_tampered_malformed_and_restarted_tokens_fail_closed(self):
        _, page = self.token()
        token = page.next_cursor
        altered = token[:-1] + ("0" if token[-1] != "0" else "1")
        for value in (altered, "", "x" * 129, "../../credential", 1, "é" * 97):
            with self.subTest(value=repr(value)[:16]):
                self.conflict(lambda: self.begin(cursor=value))
        self.conflict(lambda: self.begin(CursorStore(), cursor=token))

    def test_expiry_is_monotonic_and_not_extended_by_pagination(self):
        state, page = self.token()
        self.now += 899
        following = self.begin(cursor=page.next_cursor)
        next_page = self.store.finish(
            following, position=self.position, last_sequence=90, has_more=True
        )
        self.now += 1
        self.conflict(lambda: self.begin(cursor=page.next_cursor))
        self.conflict(lambda: self.begin(cursor=next_page.next_cursor))
        self.conflict(
            lambda: self.store.finish(
                state, position=self.position, last_sequence=90, has_more=True
            )
        )

    def test_signature_covers_the_stored_snapshot_and_position(self):
        _, page = self.token()
        token_id = page.next_cursor.split(".")[0]
        saved = self.store._states[token_id]
        for changes in (
            {"snapshot_sequence": 101},
            {"snapshot_id": "different-snapshot"},
            {"before": (self.position[0], "different-row")},
            {"expires_at": saved.expires_at + 1},
        ):
            with self.subTest(changes=changes):
                self.store._states[token_id] = replace(saved, **changes)
                self.conflict(lambda: self.begin(cursor=page.next_cursor))
        self.store._states[token_id] = saved
        self.begin(cursor=page.next_cursor)

    def test_eviction_is_bounded_and_never_reopens_a_cursor(self):
        small = CursorStore(max_states=2, clock=lambda: self.now)
        _, first = self.token(small)
        _, second = self.token(small)
        _, third = self.token(small)
        self.conflict(lambda: self.begin(small, cursor=first.next_cursor))
        self.begin(small, cursor=second.next_cursor)
        self.begin(small, cursor=third.next_cursor)

    def test_tokens_and_contexts_are_bounded_immutable_and_nonreflective(self):
        state, page = self.token()
        self.assertRegex(page.next_cursor, r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
        self.assertLessEqual(len(page.next_cursor), 128)
        self.assertNotIn("human-1", page.next_cursor)
        with self.assertRaises(FrozenInstanceError):
            state.snapshot_sequence = 999
        self.assertIsInstance(state.binding, tuple)
        for changes in (
            {"limit": True},
            {"limit": 101},
            {"snapshot_sequence": -1},
            {"snapshot_sequence": True},
            {"binding": {"principal": "x" * 257}},
            {"binding": {"principal": []}},
            {"binding": {str(index): index for index in range(33)}},
        ):
            with self.subTest(changes=changes):
                self.conflict(lambda: self.begin(**changes))

    def test_concurrent_pages_have_independent_bound_positions(self):
        def issue(index):
            state = self.begin()
            position = (self.position[0], f"workflow-{index}")
            page = self.store.finish(
                state, position=position, last_sequence=index, has_more=True
            )
            restored = self.begin(cursor=page.next_cursor)
            self.assertEqual(restored.before, position)
            return page.next_cursor

        with ThreadPoolExecutor(max_workers=8) as workers:
            tokens = list(workers.map(issue, range(100)))
        self.assertEqual(len(set(tokens)), 100)

    def test_invalid_store_bounds_and_page_metadata_are_rejected(self):
        for options in ({"max_states": 1025}, {"ttl_seconds": 901}, {"max_states": 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                CursorStore(**options)
        state = self.begin()
        for arguments in (
            {"position": None, "last_sequence": 1, "has_more": True},
            {"position": self.position, "last_sequence": 101, "has_more": True},
            {"position": self.position, "last_sequence": True, "has_more": True},
            {"position": self.position, "last_sequence": 1, "has_more": 1},
        ):
            with self.subTest(arguments=arguments):
                self.conflict(lambda: self.store.finish(state, **arguments))
