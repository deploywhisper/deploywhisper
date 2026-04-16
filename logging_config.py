"""Structured logging configuration for DeployWhisper."""

from __future__ import annotations

import logging
from logging.config import dictConfig

from config import settings


def configure_logging() -> None:
    """Configure a minimal structured logger for the foundation scaffold."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "structured",
                }
            },
            "root": {
                "handlers": ["console"],
                "level": settings.log_level,
            },
        }
    )


logger = logging.getLogger(__name__)
