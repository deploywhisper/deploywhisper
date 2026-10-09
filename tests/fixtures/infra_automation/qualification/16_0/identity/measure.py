"""Reproduce sanitized WP2 results without writing credentials or raw test logs."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import platform
from pathlib import Path
import secrets
import sqlite3
import ssl
import statistics
import io
import unittest
import sys
import time

spec = importlib.util.spec_from_file_location(
    "infra_identity_measurement", Path(__file__).with_name("prototype.py")
)
prototype = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prototype)


def measure(*, destination=None):
    root = Path(__file__).resolve().parents[6]
    password = secrets.token_urlsafe(24)
    samples = []
    for _ in range(7):
        start = time.perf_counter()
        verifier = prototype.password_verifier(password)
        samples.append((time.perf_counter() - start) * 1000)
    verify_start = time.perf_counter()
    verified = prototype.verify_password(password, verifier)
    verify_ms = (time.perf_counter() - verify_start) * 1000
    if not verified:
        print(
            json.dumps(
                {
                    "qualification_disposition": "measured crypto verification failed; accepted artifact not overwritten",
                    "verification_succeeded": False,
                    "matrix_metrics": "unverified",
                }
            )
        )
        return 1
    sys.path.insert(0, str(root))
    suite = unittest.defaultTestLoader.loadTestsFromName(
        "tests.test_infra.test_infra_automation_identity_qualification"
    )
    outcome = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    if not outcome.wasSuccessful():
        print(
            json.dumps(
                {
                    "qualification_disposition": "prototype checks failed; accepted artifact not overwritten",
                    "tests_run": outcome.testsRun,
                    "failures": len(outcome.failures),
                    "errors": len(outcome.errors),
                    "matrix_metrics": "unverified",
                }
            )
        )
        return 1
    matrix_metrics = importlib.import_module(
        "tests.test_infra.test_infra_automation_identity_qualification"
    ).IdentityQualificationTests.matrix_metrics
    if matrix_metrics is None:
        print(
            json.dumps(
                {
                    "qualification_disposition": "matrix unverified; accepted artifact not overwritten"
                }
            )
        )
        return 1
    checks = [
        {
            "command": "./.venv/bin/python -m unittest tests.test_infra.test_infra_automation_identity_qualification -v",
            "exit_code": 0 if outcome.wasSuccessful() else 1,
            "tests_run": outcome.testsRun,
            "failures": len(outcome.failures),
            "errors": len(outcome.errors),
        }
    ]
    result = {
        "story": "16.0",
        "packet": "WP2",
        "scope": "disposable-qualification-only",
        "production_routes_tables_or_dependencies_added": False,
        "qualification_disposition": "prototype checks pass; production integration and independent adequacy review pending",
        "crypto_adequacy": {
            "decision": "existing primitives adequate for bounded disposable experiment; no dependency request",
            "rationale": "supported PBKDF2-SHA256 600000 work factor, random salts, fixed verifier parser, constant-time digest comparison and bounded authentication work",
            "public_maintainer_security_approval": "pending",
            "production_hardware_cost_review": "pending",
            "primary_sources": [
                "https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#pbkdf2",
                "https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#session-id-entropy",
                "https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html",
            ],
        },
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "openssl": ssl.OPENSSL_VERSION,
            "sqlite": sqlite3.sqlite_version,
        },
        "installed_versions": {
            name: importlib.metadata.version(name)
            for name in (
                "fastapi",
                "starlette",
                "httpx",
                "cryptography",
                "ruff",
                "bandit",
            )
        },
        "crypto": {
            "algorithm": "PBKDF2-HMAC-SHA256",
            "iterations": prototype.ITERATIONS,
            "salt_bits": 128,
            "derived_key_bits": 256,
            "session_bootstrap_csrf_bits": 256,
            "persisted_authentication": "SHA-256 hashes only",
            "fixed_parameter_parser": True,
            "verification_succeeded": verified,
            "hash_sample_count": len(samples),
            "hash_ms_min": round(min(samples), 3),
            "hash_ms_median": round(statistics.median(samples), 3),
            "hash_ms_max": round(max(samples), 3),
            "verify_ms": round(verify_ms, 3),
        },
        "bounds": {
            "credential_utf8_bytes_max": 1024,
            "credential_utf8_bytes_min_for_creation": 15,
            "principal_characters_max": 128,
            "auth_derivations_in_flight_max": 1,
            "account_attempts_per_60_seconds": 5,
            "global_attempts_per_60_seconds": 20,
            "auth_queue": "no-wait-denial",
            "bootstrap_ttl_seconds": 300,
            "session_idle_seconds": 300,
            "session_absolute_seconds": 3600,
            "http_json_body_bytes_max": 4096,
        },
        "test_cases": outcome.testsRun,
        "matrix": {
            "audiences": list(prototype.AUDIENCES),
            "roles": list(prototype.ROLE_CAPABILITIES),
            "scopes": ["project", "workspace"],
            "capabilities": list(prototype.CAPABILITIES),
            **matrix_metrics,
        },
        "checks": checks,
        "red_phase": {
            "command": "./.venv/bin/python -m unittest tests.test_infra.test_infra_automation_identity_qualification -v",
            "exit_code": 1,
            "reason": "prototype absent; expected FileNotFoundError before implementation",
        },
        "review_regressions": {
            "tests_first": True,
            "red_cases": [
                "rotation past original one-hour authentication deadline incorrectly allowed",
                "lone-surrogate credential raised UnicodeEncodeError",
                "measurement failure-artifact regression lacked guarded destination interface",
                "measured crypto verification failure incorrectly published accepted artifact",
                "malformed/non-object/oversized JSON and non-scalar scope requests raised errors",
            ],
            "final_outcome": "all regression assertions pass",
        },
        "limitations": [
            "Disposable harness only; no Story 16.1/16.2 implementation or independent human security approval",
            "No browser TLS/proxy integration, production concurrency/load, capacity or password-reset delivery proof",
            "Global rate limiter is single-process and resets on restart; production persistent abuse controls remain downstream",
            "Machine protocol capabilities/enrollment attempt binding remain WP3/WP5/WP6 and owning stories; generic human routes deny every machine audience",
            "Host/root/DB administrators remain trusted; no memory zeroization claim",
            "Installed Starlette warns about httpx TestClient deprecation; no dependency changes authorized",
        ],
    }
    if destination is None:
        destination = (
            root / "docs/verification/infra-automation/16-0/wp2-identity-results.json"
        )
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "checks": checks,
                "hash_ms_median": result["crypto"]["hash_ms_median"],
                "test_cases": result["test_cases"],
            },
            indent=2,
        )
    )
    return 0 if all(check["exit_code"] == 0 for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(measure())
