"""Structured logging configuration for DeployWhisper."""

from __future__ import annotations

import logging
from copy import copy
from logging.config import dictConfig

from config import settings
from services.content_security import redact_text


class SafeFormatter(logging.Formatter):
    """Redact rendered log messages and retain exception classes only."""

    def format(self, record: logging.LogRecord) -> str:
        safe_record = copy(record)
        safe_record.msg = redact_text(record.getMessage())
        safe_record.args = ()
        # Other handlers can cache full exception text on the shared record.
        safe_record.exc_text = None
        safe_record.stack_info = None
        return redact_text(super().format(safe_record))

    def formatException(self, exc_info) -> str:
        return exc_info[0].__name__


class PayloadLogFilter(logging.Filter):
    """Drop SDK payload dumps and SQL statements with bound parameters."""

    _payload_loggers = (
        "httpx",
        "httpcore",
        "openai",
        "anthropic",
        "google.genai",
        "urllib3",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno <= logging.INFO and any(
            record.name == name or record.name.startswith(f"{name}.")
            for name in ("sqlalchemy.engine", "sqlalchemy.pool")
        ):
            return False
        return not (
            record.levelno <= logging.DEBUG
            and any(
                record.name == name or record.name.startswith(f"{name}.")
                for name in self._payload_loggers
            )
        )


def configure_logging() -> None:
    """Configure a minimal structured logger for the foundation scaffold."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "()": SafeFormatter,
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "filters": {"payload_boundary": {"()": PayloadLogFilter}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "structured",
                    "filters": ["payload_boundary"],
                }
            },
            "root": {
                "handlers": ["console"],
                "level": settings.log_level,
            },
            "loggers": {
                name: {"handlers": [], "propagate": True}
                for name in ("alembic", "uvicorn", "uvicorn.error", "uvicorn.access")
            },
        }
    )


logger = logging.getLogger(__name__)
