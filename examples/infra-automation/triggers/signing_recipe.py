"""Version-matched signing recipe; importing or running this file sends nothing."""

from __future__ import annotations

import secrets
import time
from importlib import import_module
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
config = import_module("config")
signing = import_module("infra_automation.trigger_signing")

WEBHOOK_PATH = "/api/v1/infra-automation/triggers/webhook"


def build_headers(
    *, key_id: str, secret_env_ref: str, body: bytes, path: str = WEBHOOK_PATH
) -> dict[str, str]:
    """Sign the same bytes the caller will send, using a fresh nonce each time.

    Keep returned headers out of logs. The secret is read from the named
    environment reference and is never returned. The caller owns authenticated
    transport, an exact configured origin and the unchanged request bytes.
    """
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    signature = signing.sign_request(
        config.trigger_secret(secret_env_ref),
        key_id=key_id,
        method="POST",
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        signing.KEY_ID_HEADER: key_id,
        signing.TIMESTAMP_HEADER: timestamp,
        signing.NONCE_HEADER: nonce,
        signing.SIGNATURE_HEADER: signature,
    }


if __name__ == "__main__":
    print(
        "Import build_headers; this example does not send requests or print credentials."
    )
