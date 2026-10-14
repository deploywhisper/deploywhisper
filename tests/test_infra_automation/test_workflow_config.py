"""Application-owned limit configuration cannot widen the pure contract."""

from dataclasses import replace
import unittest
from unittest.mock import patch

from pydantic import ValidationError

import config
from infra_automation.contracts import ValidationLimits


class WorkflowConfigTests(unittest.TestCase):
    def test_application_factory_passes_lowered_limits(self):
        configured = replace(
            config.settings,
            workflow_validation_max_bytes=4096,
            workflow_validation_max_depth=8,
            workflow_validation_max_steps=10,
            workflow_validation_max_inputs=5,
            workflow_validation_max_errors=3,
        )
        with patch.object(config, "settings", configured):
            self.assertEqual(
                config.workflow_validation_limits(),
                ValidationLimits(
                    max_bytes=4096,
                    max_depth=8,
                    max_steps=10,
                    max_inputs=5,
                    max_errors=3,
                ),
            )

    def test_application_factory_rejects_invalid_or_widened_limits(self):
        for field, maximum in ValidationLimits().model_dump().items():
            for value in (0, maximum + 1):
                with self.subTest(field=field, value=value):
                    configured = replace(
                        config.settings, **{"workflow_validation_" + field: value}
                    )
                    with patch.object(config, "settings", configured):
                        with self.assertRaises(ValidationError):
                            config.workflow_validation_limits()
