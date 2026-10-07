"""Coverage-guided checks of the production credential-screening boundary."""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import sys
from urllib.parse import quote

# Permit direct developer execution; the packaged binary bundles these imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def check_input(data: bytes) -> None:
    """Exercise arbitrary artifacts and verify generated credential invariants."""
    from services.content_security import (
        REDACTED,
        redact_text,
        redact_value,
        sensitive_artifact_values,
    )

    data = data[:4096]
    text = data.decode("utf-8", errors="replace")
    assert isinstance(redact_text(text), str)
    values = sensitive_artifact_values(data)
    assert values == tuple(sorted(set(values)))
    assert all(
        isinstance(value, str) and value and value != REDACTED for value in values
    )

    # Hex encoding keeps the generated credential unambiguous in every format;
    # mutation still varies its length, content, container, and safe surroundings.
    secret = "synthetic-fuzz-" + data[:64].hex()
    mode = data[0] % 5 if data else 0
    if mode == 0:
        payload = {"api_key": secret, "echo": secret, "description": text}
        artifact = json.dumps(payload).encode()
    elif mode == 1:
        payload = {"kind": "Secret", "stringData": {"opaque": secret}, "echo": secret}
        artifact = f"kind: Secret\nstringData:\n  opaque: {secret}\n".encode()
    elif mode == 2:
        encoded = base64.b64encode(secret.encode()).decode()
        payload = {"kind": "Secret", "data": {"opaque": encoded}, "echo": secret}
        artifact = f"kind: Secret\ndata:\n  opaque: {encoded}\n".encode()
    elif mode == 3:
        payload = {
            "before": {"opaque": secret},
            "before_sensitive": {"opaque": True},
            "echo": secret,
        }
        artifact = json.dumps(payload).encode()
    else:
        payload = {
            "Parameters": {"Credential": {"NoEcho": True, "Default": secret}},
            "echo": secret,
        }
        artifact = json.dumps(payload).encode()

    original = copy.deepcopy(payload)
    screened = redact_value(payload)
    assert payload == original, "redaction mutated its input"
    assert screened["echo"] == REDACTED, "a sibling credential echo escaped screening"
    assert secret not in json.dumps(screened), (
        "a generated credential escaped screening"
    )
    assert redact_value(screened) == screened, "structured redaction is not stable"
    discovered = sensitive_artifact_values(artifact)
    assert secret in discovered, "artifact screening missed a generated credential"
    assert secret not in redact_text(f"api_key={secret}")
    assert secret not in redact_text(secret, sensitive_values=(secret,))
    encoded_assignment = quote(f"api_key={secret}", safe="")
    assert redact_text(encoded_assignment) == REDACTED


def main() -> None:
    import atheris

    with atheris.instrument_imports():
        from services import content_security  # noqa: F401

    atheris.Setup(sys.argv, atheris.instrument_func(check_input))
    atheris.Fuzz()


if __name__ == "__main__":
    main()
