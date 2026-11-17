"""Lazy ambient credentials with qualified mechanisms and canonical transport only."""

from __future__ import annotations
import os
import logging
from pathlib import Path
import re
import threading

from cloud.aws.allowlist import _CATALOG


def validate_config(config):
    if (
        not isinstance(config, dict)
        or set(config) != {"region"}
        or not isinstance(config["region"], str)
        or re.fullmatch(
            r"(?:us|eu|ap|sa|ca|me|af|il|mx)-[a-z]+-[1-9]", config["region"]
        )
        is None
    ):
        raise ValueError("AWS configuration denied")
    return config.copy()


def _silence_sdk_logs():
    # Botocore debug records contain Authorization headers and session tokens.
    # Disable at the SDK logger before record construction, rather than trying
    # to sanitize records after they have reached handlers or capture sinks.
    for namespace in ("botocore", "boto3"):
        logging.getLogger(namespace).setLevel(logging.CRITICAL + 1)
    for name, logger in tuple(logging.Logger.manager.loggerDict.items()):
        if (
            name == "botocore"
            or name.startswith("botocore.")
            or name == "boto3"
            or name.startswith("boto3.")
        ):
            if isinstance(logger, logging.Logger):
                logger.disabled = True


def session(*, mechanisms=("env",), credentials_file=None, trusted_profile=None):
    if (
        not mechanisms
        or set(mechanisms) - {"env", "shared-credentials-file"}
        or ("shared-credentials-file" in mechanisms and not credentials_file)
        or (credentials_file and "shared-credentials-file" not in mechanisms)
        or (trusted_profile and "shared-credentials-file" not in mechanisms)
    ):
        raise ValueError("credential mechanism denied")
    # Import only after the trusted operator selects a mechanism. Never import on dry-run.
    import botocore.session
    from botocore.loaders import Loader
    from botocore.configprovider import ConstantProvider

    _silence_sdk_logs()
    sdk = botocore.session.get_session()
    # Never trust AWS_DATA_PATH or the user model directory for API/endpoint data.
    trusted_data = str(Path(botocore.__file__).resolve().parent / "data")
    sdk.register_component(
        "data_loader",
        Loader(extra_search_paths=[trusted_data], include_default_search_paths=False),
    )
    sdk.set_config_variable("config_file", os.devnull)
    sdk.set_config_variable("credentials_file", credentials_file or os.devnull)
    if trusted_profile:
        sdk.set_config_variable("profile", trusted_profile)
    else:
        sdk.set_config_variable("profile", None)
    sdk.get_component("config_store").set_config_provider(
        "profile", ConstantProvider(trusted_profile)
    )
    resolver = sdk.get_component("credential_provider")
    resolver.providers = [p for p in resolver.providers if p.METHOD in mechanisms]
    return sdk


class SessionError(PermissionError):
    """A safe session failure with a closed diagnostic category."""

    def __init__(self, cause="session_unavailable"):
        if cause not in {
            "sdk_unavailable",
            "credentials_unavailable",
            "session_unavailable",
            "request_refused",
        }:
            cause = "session_unavailable"
        self.cause = cause
        super().__init__("AWS session unavailable")


def _fence_client(client, service):
    """Permit one approved API operation and never delegate retry decisions.

    Botocore's S3 redirect handler can issue HeadBucket from needs-retry even
    when normal retry configuration allows one attempt. These guards run before
    that handler and before any nested operation constructs a request.
    """
    from botocore.exceptions import ClientError

    allowed = {
        row["operation"]
        for row in _CATALOG["operations"].values()
        if row["service"] == service
    }
    lock = threading.Lock()
    used = False

    def before_parameters(model, **kwargs):
        nonlocal used
        with lock:
            if used or model.name not in allowed:
                raise SessionError("request_refused")
            used = True

    def no_retry(response=None, caught_exception=None, operation=None, **kwargs):
        if caught_exception is not None:
            raise caught_exception
        if response is not None:
            http_response, parsed = response
            if http_response.status_code >= 300 or parsed.get("Error"):
                raise ClientError(parsed, operation.name)

    # Hierarchical events run operation-specific handlers before generic ones,
    # regardless of register_first. Bind exact operation events so this fence
    # precedes S3's service-wide redirect/discovery handlers.
    event_service = client.meta.service_model.service_id.hyphenize()
    for operation in client.meta.service_model.operation_names:
        client.meta.events.register_first(
            f"before-parameter-build.{event_service}.{operation}",
            before_parameters,
            unique_id="deploywhisper-single-approved-operation-" + operation,
        )
        if operation in allowed:
            client.meta.events.register_first(
                f"needs-retry.{event_service}.{operation}",
                no_retry,
                unique_id="deploywhisper-no-implicit-retry-" + operation,
            )
    return client


class AmbientSession:
    """Trusted server-only credential selection; never accept this from requests."""

    def __init__(
        self, *, mechanisms=("env",), credentials_file=None, trusted_profile=None
    ):
        if (
            not mechanisms
            or set(mechanisms) - {"env", "shared-credentials-file"}
            or ("shared-credentials-file" in mechanisms and not credentials_file)
            or (credentials_file and "shared-credentials-file" not in mechanisms)
            or (trusted_profile and "shared-credentials-file" not in mechanisms)
        ):
            raise ValueError("Credential mechanism denied")
        self._mechanisms = tuple(mechanisms)
        self._credentials_file = credentials_file
        self._profile = trusted_profile

    def create_client(self, service, config, *, timeout=2.0):
        config = validate_config(config)
        try:
            try:
                from botocore.config import Config
            except ImportError:
                raise SessionError("sdk_unavailable") from None

            sdk = session(
                mechanisms=self._mechanisms,
                credentials_file=self._credentials_file,
                trusted_profile=self._profile,
            )
            try:
                credentials = sdk.get_credentials()
            except Exception:
                raise SessionError("credentials_unavailable") from None
            if credentials is None:
                raise SessionError("credentials_unavailable")
            client = sdk.create_client(
                service,
                region_name=config["region"],
                use_ssl=True,
                verify=True,
                config=Config(
                    ignore_configured_endpoint_urls=True,
                    proxies={},
                    connect_timeout=timeout / 2,
                    read_timeout=timeout / 2,
                    retries={"total_max_attempts": 1},
                    s3={"addressing_style": "path", "use_arn_region": False},
                ),
            )
            _silence_sdk_logs()
            return _fence_client(client, service)
        except SessionError:
            raise
        except Exception:
            raise SessionError("session_unavailable") from None
