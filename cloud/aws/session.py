"""Lazy ambient credentials with qualified mechanisms and canonical transport only."""

from __future__ import annotations
import os
import logging
from pathlib import Path
import re


def validate_config(config):
    if (
        not isinstance(config, dict)
        or set(config) != {"region"}
        or not isinstance(config["region"], str)
        or re.fullmatch(
            r"(?:us|eu|ap|sa|ca|me|af|il|mx)-(?:[a-z]+-)?[a-z]+-[1-9]", config["region"]
        )
        is None
    ):
        raise ValueError("AWS configuration denied")
    return config.copy()


def _silence_sdk_logs():
    # Botocore debug records contain Authorization headers and session tokens.
    # Disable at the SDK logger before record construction, rather than trying
    # to sanitize records after they have reached handlers or capture sinks.
    for namespace in ("botocore", "boto3", "urllib3"):
        logging.getLogger(namespace).setLevel(logging.CRITICAL + 1)
    for name, logger in tuple(logging.Logger.manager.loggerDict.items()):
        if (
            name == "botocore"
            or name.startswith("botocore.")
            or name == "boto3"
            or name.startswith("boto3.")
            or name == "urllib3"
            or name.startswith("urllib3.")
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
            from botocore.config import Config

            sdk = session(
                mechanisms=self._mechanisms,
                credentials_file=self._credentials_file,
                trusted_profile=self._profile,
            )
            if sdk.get_credentials() is None:
                raise PermissionError("Ambient credentials unavailable")
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
                    s3={"addressing_style": "path"},
                ),
            )
            _silence_sdk_logs()
            return client
        except Exception:
            raise PermissionError("AWS session unavailable") from None
