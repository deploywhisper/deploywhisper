"""Disposable offline feasibility prototype. Never constructs an AWS client."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
import os
from pathlib import Path
import platform
import socket
import sys
import threading
import time

BASE = Path(__file__).parent
ROOT = BASE.parents[4]
ALLOWED = {
    "ec2:DescribeInstances": ("aws_instance", "InstanceIds"),
    "ec2:DescribeSecurityGroups": ("aws_security_group", "GroupIds"),
    "rds:DescribeDBInstances": ("aws_db_instance", "DBInstanceIdentifier"),
}


def assert_read_only(actions):
    for action in actions:
        if not action.split(":", 1)[-1].startswith(
            ("Describe", "Get", "List", "BatchGet", "Head")
        ):
            raise ValueError("mutating action rejected")


def readiness(
    *,
    rfc_accepted,
    dependency_approved,
    feasibility_complete,
    no_blocking_gaps,
    independent_review,
):
    return (
        "READY"
        if all(
            (
                rfc_accepted,
                dependency_approved,
                feasibility_complete,
                no_blocking_gaps,
                independent_review,
            )
        )
        else "NOT READY"
    )


def policy_actions():
    policy = json.loads((BASE / "policy.json").read_text())
    if policy["Version"] != "2012-10-17" or len(policy["Statement"]) != 1:
        raise ValueError("unexpected policy shape")
    statement = policy["Statement"][0]
    if (
        set(statement) != {"Effect", "Action", "Resource"}
        or statement["Effect"] != "Allow"
    ):
        raise ValueError("unexpected policy statement")
    return set(statement["Action"])


def authorize(action, params, construct):
    if action not in ALLOWED:
        raise PermissionError("action not allow-listed")
    assert_read_only({action})
    return construct(action, params)


def validate_config(config):
    # Intentionally narrow prototype; no arbitrary endpoint, role, account or profile.
    if set(config) - {"region"} or config.get("region", "us-east-1") not in {
        "us-east-1",
        "us-west-2",
    }:
        raise ValueError("configuration denied")
    return config.copy()


def extract(plan):
    if plan.get("format_version") not in {"1.0", "1.1", "1.2"}:
        raise ValueError("unqualified format")
    prior = {}

    def walk(module):
        for resource in module.get("resources", []):
            prior[resource["address"]] = resource.get("values")
        for child in module.get("child_modules", []):
            walk(child)

    walk((plan.get("prior_state") or {}).get("values", {}).get("root_module", {}))
    rows = []
    for resource in plan.get("resource_changes", []):
        address = resource["address"]
        change = resource["change"]
        values = prior.get(address)
        source = "prior_state"
        if values is None:
            values = change.get("before")
            source = "change.before" if values is not None else "missing"
        status = "recorded" if values is not None else "unknown"
        if values is None and change.get("actions") == ["create"]:
            status = "no_live_counterpart"
        rows.append(
            {
                "address": address,
                "type": resource["type"],
                "values": values,
                "source": source,
                "status": status,
            }
        )
    return rows


def dry_run(plan):
    calls = []
    for row in extract(plan):
        if row["status"] != "recorded":
            continue
        for action, (family, param) in ALLOWED.items():
            if family == row["type"]:
                identity = row["values"].get("id")
                if identity:
                    calls.append(
                        {
                            "action": action,
                            "params": {
                                param: identity
                                if family == "aws_db_instance"
                                else [identity]
                            },
                        }
                    )
    return calls


def screened_observation(value, secret):
    # Existing application redaction boundary, not a parallel model.
    sys.path.insert(0, str(ROOT))
    from services.content_security import redact_value

    return redact_value(value, sensitive_values=(secret,))


def collect(
    calls, *, deadline=0.2, concurrency=4, budget=100, delay=0.002, cancel=None
):
    """Cooperative fake provider; a real SDK needs socket timeouts and retries bounded separately."""
    cancel = cancel or threading.Event()
    started = time.monotonic()
    end = started + deadline
    issued = 0
    completed = 0
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_read(call):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            cancel.wait(max(0, min(delay, end - time.monotonic())))
            return time.monotonic() < end and not cancel.is_set()
        finally:
            with lock:
                active -= 1

    pending = set()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        while pending or issued < min(len(calls), budget):
            if cancel.is_set() or time.monotonic() >= end:
                break
            while len(pending) < concurrency and issued < min(len(calls), budget):
                pending.add(executor.submit(fake_read, calls[issued]))
                issued += 1
            done, pending = wait(
                pending,
                timeout=max(0, end - time.monotonic()),
                return_when=FIRST_COMPLETED,
            )
            completed += sum(future.result() for future in done)
        for future in pending:
            future.cancel()
    elapsed = time.monotonic() - started
    return {
        "issued": issued,
        "completed": completed,
        "partial": completed < len(calls),
        "elapsed_seconds": elapsed,
        "peak_concurrency": peak,
        "total_intended": len(calls),
    }


def no_network(*args, **kwargs):
    raise RuntimeError("network forbidden by offline qualification")


def main():
    socket.socket = no_network
    if sys.argv[1:] == ["dry-run"]:
        if any(key.startswith("AWS_") for key in os.environ):
            raise RuntimeError("dry-run qualification requires empty AWS environment")
        print(
            json.dumps(
                {
                    "calls": dry_run(json.loads((BASE / "plan.json").read_text())),
                    "issued": 0,
                }
            )
        )
        return
    assert_read_only(ALLOWED)
    if policy_actions() != set(ALLOWED):
        raise RuntimeError("policy mismatch")
    plan = json.loads((BASE / "plan.json").read_text())
    template = plan["resource_changes"][0]
    large = {
        "format_version": "1.2",
        "resource_changes": [
            dict(
                template,
                address=f"aws_instance.web[{index}]",
                change={
                    "actions": ["update"],
                    "before": {"id": f"i-{index:017x}"},
                    "after": {"id": f"i-{index:017x}"},
                },
            )
            for index in range(1000)
        ],
    }
    calls = dry_run(large)
    reports = {
        name: collect(calls, **params)
        for name, params in {
            "bounded": {"deadline": 0.2, "concurrency": 4, "budget": 100},
            "deadline": {
                "deadline": 0.03,
                "concurrency": 4,
                "budget": 1000,
                "delay": 0.02,
            },
            "complete": {"deadline": 2, "concurrency": 8, "budget": 1000},
        }.items()
    }
    output = {
        "profile": "offline synthetic only; no provider qualification",
        "hardware": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
        },
        "python": platform.python_version(),
        "fixture": {
            "resources": 1000,
            "bytes": len(json.dumps(large).encode()),
            "sha256": __import__("hashlib")
            .sha256(json.dumps(large, sort_keys=True).encode())
            .hexdigest(),
            "provenance": "generated synthetic EC2 update plan; no real tool exports",
        },
        "runs": reports,
        "provider_calls": 0,
        "actual_provider_cost_usd": 0,
        "cost_model": {
            "assumed_usd_per_1000_calls": 0.01,
            "bounded_estimated_usd": reports["bounded"]["issued"] * 0.01 / 1000,
            "status": "hypothetical sensitivity input, not AWS pricing",
        },
        "proposed_defaults": {
            "total_deadline_seconds": 15,
            "concurrency": 4,
            "call_budget": 100,
            "per_call_timeout_seconds": 2,
            "status": "candidate only; fake-provider timings cannot establish production defaults",
        },
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
