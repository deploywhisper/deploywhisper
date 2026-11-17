"""Registry success and explicit unsupported provider failures."""

import unittest
from unittest.mock import Mock, patch
from cloud.registry import (
    CONNECTORS,
    CloudProviderError,
    UnknownProviderError,
    UnimplementedProviderError,
    create_connector,
    register_connector,
)


class RegistryTests(unittest.TestCase):
    def test_unknown_and_unimplemented_are_distinct(self):
        with self.assertRaises(UnknownProviderError):
            create_connector("unknown")
        for provider in ("aws", "azure", "gcp"):
            with (
                self.subTest(provider=provider),
                self.assertRaises(UnimplementedProviderError),
            ):
                create_connector(provider)

    def test_reference_factory_is_called_only_when_resolved(self):
        factory = Mock()
        with patch.dict(CONNECTORS, {}, clear=True):
            register_connector("reference", factory)
            factory.assert_not_called()
            self.assertIs(create_connector("reference"), factory.return_value)
            factory.assert_called_once_with()
            with self.assertRaises(ValueError):
                register_connector("reference", factory)

    def test_registry_rejects_ambiguous_names_and_nonfactories(self):
        for name in ("", "AWS", "aws/endpoint", " https://host", "a b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                register_connector(name, Mock())
        with self.assertRaises(TypeError):
            register_connector("test", object())

    def test_invalid_factory_result_is_an_explicit_failure(self):
        with patch.dict(CONNECTORS, {"broken": lambda: None}, clear=True):
            with self.assertRaises(CloudProviderError):
                create_connector("broken")

    def test_unimplemented_slot_can_be_installed_explicitly(self):
        factory = Mock()
        with patch.dict(CONNECTORS, {"aws": None}, clear=True):
            register_connector("aws", factory)
            self.assertIs(create_connector("aws"), factory.return_value)
            with self.assertRaises(ValueError):
                register_connector("aws", factory)
