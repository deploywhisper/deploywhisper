"""Disposable AWS SDK boundary probe; no product connector or live calls."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

ACTION = "ec2:DescribeInstances"


def validate_config(config):
    if set(config) != {"region"} or config["region"] not in {"us-east-1", "us-west-2"}:
        raise ValueError("configuration denied")
    return config.copy()


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


def authorize(action, params, construct):
    if action != ACTION:
        raise PermissionError("action denied before construction")
    if (
        set(params) != {"InstanceIds"}
        or not isinstance(params["InstanceIds"], list)
        or not 1 <= len(params["InstanceIds"]) <= 100
        or not all(
            isinstance(value, str)
            and re.fullmatch(r"i-(?:[0-9a-f]{8}|[0-9a-f]{17})", value)
            for value in params["InstanceIds"]
        )
    ):
        raise ValueError("unbounded or malformed resource selection")
    return construct()


def client(action, config):
    if action != ACTION:
        raise PermissionError("action denied before session construction")
    config = validate_config(config)
    from botocore.config import Config

    sdk = session()
    if sdk.get_credentials() is None:
        raise PermissionError("explicit operator credentials unavailable")
    return sdk.create_client(
        "ec2",
        region_name=config["region"],
        use_ssl=True,
        verify=True,
        config=Config(
            ignore_configured_endpoint_urls=True,
            proxies={},
            connect_timeout=1,
            read_timeout=1,
            retries={"total_max_attempts": 1},
        ),
    )


def dispatch(action, params, sdk_client):
    from botocore.exceptions import ClientError

    def issue():
        try:
            response = sdk_client.describe_instances(**params)
        except ClientError as error:
            # Provider messages and request IDs may contain credentials/estate data.
            code = error.response.get("Error", {}).get("Code", "")
            cause = (
                code
                if code in {"AccessDenied", "UnauthorizedOperation", "Throttling"}
                else "provider_error"
            )
            return {
                "status": "unreadable",
                "missing_permission": action,
                "cause": cause,
            }
        return {
            "status": "incomplete" if response.get("NextToken") else "recorded",
            "instance_count": sum(
                len(row.get("Instances", []))
                for row in response.get("Reservations", [])
            ),
        }

    return authorize(action, params, issue)


def manifest(identities):
    calls = []
    for identity in identities:
        params = {"InstanceIds": [identity]}
        authorize(ACTION, params, lambda: None)
        calls.append({"action": ACTION, "params": params})
    return calls


if __name__ == "__main__":
    if sys.argv[1:] != ["dry-run"]:
        raise SystemExit("offline probe supports dry-run only")
    print(
        json.dumps(
            {
                "calls": manifest(["i-00000000000000001"]),
                "issued": 0,
                "sdk_imported": any(
                    key.startswith(("boto3", "botocore")) for key in sys.modules
                ),
            }
        )
    )
