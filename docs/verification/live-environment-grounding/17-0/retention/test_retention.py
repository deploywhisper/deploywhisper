"""Retention decision examples; no database or product purge implementation."""

import unittest
from retention_spike import disposition


class RetentionTests(unittest.TestCase):
    def test_active_report_prevents_purge(self):
        self.assertEqual(disposition(100, 10, 20, [110]), "retain")

    def test_unknown_report_lifetime_prevents_purge(self):
        self.assertEqual(disposition(100, 10, 20, [None]), "retain")

    def test_unreferenced_expired_payload_can_be_removed(self):
        self.assertEqual(disposition(100, 10, 20, []), "purge_payload_keep_digest")

    def test_age_is_observation_time_for_imports_too(self):
        self.assertEqual(disposition(29, 10, 20, []), "retain")
        self.assertEqual(disposition(30, 10, 20, []), "purge_payload_keep_digest")

    def test_future_observation_and_invalid_ttl_fail_closed(self):
        for args in [(10, 20, 30, []), (10, 0, -1, []), (True, 0, 1, [])]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                disposition(*args)
