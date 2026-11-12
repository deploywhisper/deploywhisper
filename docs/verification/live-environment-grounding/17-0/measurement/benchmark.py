"""Disposable controlled-replay benchmark; no AWS client or network is used."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import socket
import subprocess
import threading
import time

from cost_model import estimate_cost

CONTRACT_PATH = Path(__file__).parent.parent / "coverage" / "coverage.json"
SCOPE = {"partition": "aws", "region": "us-east-1", "account": "000000000000"}


def load_contract():
    return json.loads(CONTRACT_PATH.read_text())


FAMILIES = tuple(load_contract()["families"])


def identity(family, index):
    suffix = f"{index:017x}"
    prefixes = {
        "aws_instance": "i-",
        "aws_security_group": "sg-",
        "aws_network_interface": "eni-",
        "aws_subnet": "subnet-",
        "aws_vpc": "vpc-",
        "aws_route_table": "rtb-",
        "aws_ebs_volume": "vol-",
        "aws_ebs_snapshot": "snap-",
    }
    if family in prefixes:
        return prefixes[family] + suffix
    if family.startswith("aws_lb"):
        resource = {
            "aws_lb": f"loadbalancer/app/synthetic/{index:016x}",
            "aws_lb_target_group": f"targetgroup/synthetic/{index:016x}",
            "aws_lb_listener": f"listener/app/synthetic/{index:016x}/{index:016x}",
        }[family]
        return f"arn:aws:elasticloadbalancing:us-east-1:000000000000:{resource}"
    if family == "aws_lambda_event_source_mapping":
        return f"00000000-0000-0000-0000-{index:012d}"
    if family == "aws_sqs_queue":
        return f"https://sqs.us-east-1.amazonaws.com/000000000000/synthetic-{index}"
    if family == "aws_route53_record":
        return "ZSYNTHETIC"
    return f"synthetic-{index}"


def generate_plan():
    changes = []
    modules = []
    for module_index in range(40):
        resources = []
        for family_index, family in enumerate(FAMILIES):
            index = module_index * 25 + family_index
            address = f"module.stack[{module_index}].{family}.resource"
            values = {
                "id": identity(family, index),
                "name": (
                    f"synthetic-{index}.example.invalid."
                    if family == "aws_route53_record"
                    else f"synthetic-{index}"
                ),
                "arn": identity(family, index)
                if family.startswith("aws_lb")
                else f"arn:aws:lambda:us-east-1:000000000000:function:synthetic-{index}",
                "cluster_arn": "arn:aws:ecs:us-east-1:000000000000:cluster/synthetic-cluster",
                "function_arn": f"arn:aws:lambda:us-east-1:000000000000:function:synthetic-{index}",
                "event_source_arn": f"arn:aws:sqs:us-east-1:000000000000:synthetic-{index}",
                "zone_id": "ZSYNTHETIC",
                "record_type": "A",
                "tags": {"environment": "test", "owner": "synthetic"},
            }
            arn_resources = {
                "aws_ecs_cluster": ("ecs", "cluster/" + values["name"]),
                "aws_ecs_service": (
                    "ecs",
                    "service/synthetic-cluster/" + values["name"],
                ),
                "aws_eks_cluster": ("eks", "cluster/" + values["name"]),
                "aws_dynamodb_table": ("dynamodb", "table/" + values["name"]),
                "aws_sqs_queue": ("sqs", values["name"]),
                "aws_db_instance": ("rds", "db:" + values["name"]),
                "aws_rds_cluster": ("rds", "cluster:" + values["name"]),
            }
            if family in arn_resources:
                service, resource_part = arn_resources[family]
                values["arn"] = (
                    f"arn:aws:{service}:us-east-1:000000000000:{resource_part}"
                )
            # Every family has four creates, four deletes and32 updates.
            actions = (
                ["create"]
                if module_index % 10 == 0
                else ["delete"]
                if module_index % 10 == 1
                else ["update"]
            )
            before = None if actions == ["create"] else values
            after = (
                None
                if actions == ["delete"]
                else dict(
                    values, tags={"environment": "test", "owner": "synthetic-next"}
                )
            )
            changes.append(
                {
                    "address": address,
                    "mode": "managed",
                    "type": family,
                    "name": "resource",
                    "change": {"actions": actions, "before": before, "after": after},
                }
            )
            if before is not None:
                resources.append(
                    {
                        "address": address,
                        "mode": "managed",
                        "type": family,
                        "name": "resource",
                        "values": before,
                    }
                )
        modules.append(
            {"address": f"module.stack[{module_index}]", "resources": resources}
        )
    return {
        "format_version": "1.2",
        "qualification_scope": dict(SCOPE),
        "terraform_version": "synthetic-not-a-tool-export",
        "prior_state": {"values": {"root_module": {"child_modules": modules}}},
        "resource_changes": changes,
    }


def render(value, bindings):
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return bindings[value[2:-1]]
    if isinstance(value, list):
        return [render(item, bindings) for item in value]
    if isinstance(value, dict):
        return {key: render(item, bindings) for key, item in value.items()}
    return value


def bindings_for(plan, resource):
    # The harness scope is trusted configuration, never a plan-supplied URL.
    if plan["qualification_scope"] != SCOPE:
        raise ValueError("unqualified measurement scope")
    values = dict(resource["change"]["before"])
    name = values["name"]
    if not name or any(
        char not in "abcdefghijklmnopqrstuvwxyz0123456789-_." for char in name
    ):
        raise ValueError("unqualified synthetic name")
    values.update(SCOPE)
    values["canonical_queue_url"] = (
        f"https://sqs.{SCOPE['region']}.amazonaws.com/{SCOPE['account']}/{name}"
    )
    return values


def build_calls(plan):
    contract = load_contract()
    calls = []
    for resource in plan["resource_changes"]:
        if resource["change"]["before"] is None:
            continue
        # Select the family's frozen primary request, preserving every fixed limit.
        operation_key = contract["families"][resource["type"]]["operations"][0]
        operation = contract["operations"][operation_key]
        bindings = bindings_for(plan, resource)
        call = {
            "address": resource["address"],
            "family": resource["type"],
            "contract_operation": operation_key,
            "service": operation["service"],
            "operation": operation["operation"],
            "params": render(operation["params"], bindings),
        }
        postfilter = expected_postfilter(resource["type"], bindings)
        if postfilter is not None:
            call["postfilter"] = postfilter
        calls.append(call)
    return calls


def expected_postfilter(family, bindings):
    if family == "aws_lambda_event_source_mapping":
        return {
            "UUID": bindings["id"],
            "FunctionArn": bindings["function_arn"],
            "EventSourceArn": bindings["event_source_arn"],
        }
    if family == "aws_route53_record":
        return {
            "Name": bindings["name"],
            "Type": bindings["record_type"],
            "SetIdentifier": bindings.get("set_identifier"),
        }
    return None


def validate_contract_calls(plan, calls):
    contract = load_contract()
    resources = {r["address"]: r for r in plan["resource_changes"]}
    for call in calls:
        resource = resources[call["address"]]
        operation_keys = contract["families"][resource["type"]]["operations"]
        key = call["contract_operation"]
        if key not in operation_keys:
            raise ValueError("operation outside frozen family")
        operation = contract["operations"][key]
        bindings = bindings_for(plan, resource)
        expected = render(operation["params"], bindings)
        if (call["service"], call["operation"], call["params"]) != (
            operation["service"],
            operation["operation"],
            expected,
        ):
            raise ValueError("request differs from frozen template")
        if call.get("family") != resource["type"]:
            raise ValueError("request differs from recorded family")
        if call.get("postfilter") != expected_postfilter(resource["type"], bindings):
            raise ValueError("response filter differs from recorded identity")


def matches_postfilter(call, response_record):
    required = {
        "aws_lambda_event_source_mapping": {"UUID", "FunctionArn", "EventSourceArn"},
        "aws_route53_record": {"Name", "Type", "SetIdentifier"},
    }.get(call.get("family"))
    if call.get("contract_operation") == "event_mapping":
        required = {"UUID", "FunctionArn", "EventSourceArn"}
    if (call.get("service"), call.get("operation")) == (
        "route53",
        "ListResourceRecordSets",
    ):
        required = {"Name", "Type", "SetIdentifier"}
    postfilter = call.get("postfilter")
    if required is not None and (
        not isinstance(postfilter, dict) or set(postfilter) != required
    ):
        return False
    if required is not None:
        for key, value in postfilter.items():
            if key == "SetIdentifier" and value is None:
                continue
            if not isinstance(value, str) or not value:
                return False
    return all(
        response_record.get(key) == value for key, value in (postfilter or {}).items()
    )


def validate_sdk_models(calls):
    import botocore
    from botocore.loaders import Loader
    from botocore.session import Session
    from botocore.validate import validate_parameters

    session = Session()
    trusted_data = str(Path(botocore.__file__).resolve().parent / "data")
    session.register_component(
        "data_loader",
        Loader(extra_search_paths=[trusted_data], include_default_search_paths=False),
    )
    models = {}
    started = time.monotonic()
    for call in calls:
        service = call["service"]
        if service not in models:
            models[service] = session.get_service_model(service)
        operation = models[service].operation_model(call["operation"])
        validate_parameters(call["params"], operation.input_shape)
    return {
        "validated_requests": len(calls),
        "elapsed_seconds": time.monotonic() - started,
        "provider_calls": 0,
    }


def measure(
    calls,
    *,
    latency=0.05,
    deadline=15,
    concurrency=4,
    budget=100,
    cancel=None,
    throttle_every=0,
    backoff=0.01,
    per_call_timeout=2,
):
    for value, minimum in ((concurrency, 1), (budget, 0), (throttle_every, 0)):
        if type(value) is not int or value < minimum:
            raise ValueError("invalid integer measurement bound")
    for value, positive in (
        (deadline, True),
        (latency, False),
        (backoff, False),
        (per_call_timeout, True),
    ):
        try:
            finite = math.isfinite(value)
        except (TypeError, OverflowError):
            finite = False
        if (
            type(value) not in (int, float)
            or not finite
            or value < 0
            or (positive and value == 0)
        ):
            raise ValueError("invalid finite measurement duration")
    cancel = cancel or threading.Event()
    started = time.monotonic()
    end = started + deadline
    issued = completed = throttled = active = peak = backoff_events = 0
    lock = threading.Lock()

    def replay_read(index):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(active, peak)
        try:
            # Cooperative replay transport models a bounded per-call timeout.
            interrupted = cancel.wait(
                max(0, min(latency, per_call_timeout, end - time.monotonic()))
            )
            finished_at = time.monotonic()
            if interrupted or finished_at >= end or latency > per_call_timeout:
                return "unread", finished_at
            return (
                "throttled"
                if throttle_every and (index + 1) % throttle_every == 0
                else "complete",
                finished_at,
            )
        finally:
            with lock:
                active -= 1

    pending = set()
    cooldown_until = started

    def record(done):
        nonlocal completed, throttled, cooldown_until, backoff_events
        for future in done:
            if future.cancelled():
                continue
            status, finished_at = future.result()
            if finished_at >= end:
                continue
            completed += status == "complete"
            throttled += status == "throttled"
            if status == "throttled":
                cooldown_until = max(cooldown_until, finished_at + backoff)
                backoff_events += 1

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        while pending or issued < min(budget, len(calls)):
            # Cooldown prevents dispatch, never accounting for completed work.
            done = {future for future in pending if future.done()}
            pending -= done
            record(done)
            if cancel.is_set() or time.monotonic() >= end:
                break
            if not pending and issued >= min(budget, len(calls)):
                break
            if time.monotonic() < cooldown_until:
                cancel.wait(
                    min(
                        0.005,
                        cooldown_until - time.monotonic(),
                        max(0, end - time.monotonic()),
                    )
                )
                continue
            while len(pending) < concurrency and issued < min(budget, len(calls)):
                if cancel.is_set() or time.monotonic() >= end:
                    break
                pending.add(executor.submit(replay_read, issued))
                issued += 1
            if not pending:
                break
            done, pending = wait(
                pending,
                timeout=min(0.01, max(0, end - time.monotonic())),
                return_when=FIRST_COMPLETED,
            )
            record(done)
        for future in pending:
            future.cancel()
    # Cooperative running reads have stopped now. Count only results completed
    # before the original deadline, including those finished during finalization.
    record(pending)
    return {
        "issued": issued,
        "completed": completed,
        "throttled": throttled,
        "unread": len(calls) - completed,
        "partial": completed < len(calls),
        "peak_concurrency": peak,
        "backoff_events": backoff_events,
        "elapsed_seconds": time.monotonic() - started,
        "intended": len(calls),
        "budget": budget,
        "deadline_seconds": deadline,
        "retries": 0,
    }


def no_network(*args, **kwargs):
    raise RuntimeError("network prohibited in controlled replay")


def hardware_identity():
    system = platform.system()
    cpu = "unknown" if system == "Darwin" else platform.processor() or "unknown"
    model = "unknown"
    if system == "Darwin":
        values = []
        for key in ("machdep.cpu.brand_string", "hw.model"):
            try:
                result = subprocess.run(
                    ["/usr/sbin/sysctl", "-n", key],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                values.append(result.stdout.strip() or "unknown")
            except (OSError, subprocess.SubprocessError):
                values.append("unknown")
        cpu, model = values
    return {
        "cpu": cpu,
        "model": model,
        "identity_source": "detected; unavailable values explicitly unknown",
        "system": system,
        "release": platform.release(),
        "machine": platform.machine(),
        "logical_cpus": os.cpu_count(),
    }


def finite_rate(value):
    if isinstance(value, bool):
        raise argparse.ArgumentTypeError("rate must be a finite nonnegative number")
    try:
        rate = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise argparse.ArgumentTypeError(
            "rate must be a finite nonnegative number"
        ) from error
    if not math.isfinite(rate) or rate < 0:
        raise argparse.ArgumentTypeError("rate must be a finite nonnegative number")
    return rate


def main():
    socket.socket.connect = no_network
    socket.create_connection = no_network
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--usd-per-1000-calls", type=finite_rate, default=0.005)
    args = parser.parse_args()
    start = time.monotonic()
    plan = generate_plan()
    calls = build_calls(plan)
    validate_contract_calls(plan, calls)
    planning_elapsed = time.monotonic() - start
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    runs = {
        "normal_50ms": measure(calls, latency=0.05),
        "slow_200ms": measure(calls, latency=0.2),
        "deadline_1000ms": measure(calls, latency=1, deadline=1),
        "throttled": measure(calls, latency=0.001, throttle_every=5),
    }
    stop = threading.Event()
    stop.set()
    runs["cancelled_before_dispatch"] = measure(calls, cancel=stop)
    result = {
        "scope": "disposable controlled-replay feasibility, not live provider latency or production profile qualification",
        "hardware": hardware_identity(),
        "python": platform.python_version(),
        "fixture": {
            "generator": "measurement/benchmark.py::generate_plan",
            "provenance": "synthetic AWS-like plan, not Terraform/OpenTofu export",
            "resources": 1000,
            "families": 25,
            "updates": 800,
            "deletes": 100,
            "creates": 100,
            "intended_calls": len(calls),
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        },
        "planning_elapsed_seconds": planning_elapsed,
        "sdk_shape_validation": validate_sdk_models(calls),
        "runs": runs,
        "defaults": {
            "total_deadline_seconds": 15,
            "concurrency": 4,
            "call_budget": 100,
            "per_call_timeout_seconds": 2,
            "hidden_sdk_retries": 0,
            "reason": "100 calls at200ms with4workers needs approximately5seconds;15seconds provides scheduling and throttling margin.1000ms failure scenario proves partial return at deadline. Large900-call manifests intentionally truncate at100, never imply complete coverage.",
        },
        "cost_estimate": estimate_cost(calls, budget=100, region=SCOPE["region"]),
        "sensitivity_estimate": {
            "basis": "explicit qualification planning input, not a provider quote or guaranteed upper bound; apply the command-line rate uniformly as a sensitivity input",
            "usd_per_1000_calls_input": args.usd_per_1000_calls,
            "budget100_estimated_request_usd": 100 * args.usd_per_1000_calls / 1000,
            "full900_estimated_request_usd": len(calls)
            * args.usd_per_1000_calls
            / 1000,
            "actual_provider_calls": 0,
            "actual_provider_charge_usd": 0,
            "excluded": [
                "region/service-specific tariffs",
                "data transfer",
                "tax",
                "free tiers",
            ],
            "pricing_reference": "https://aws.amazon.com/s3/pricing/",
            "pricing_note": "AWS documents that request prices differ by request type and service. No claim that the input is the exact tariff of every sampled operation. Product cost estimation remains out of scope.",
        },
        "limitations": [
            "Replay latency is an injected scenario, never an AWS performance measurement.",
            "SDK model validation proves request shape, not IAM authorization or provider response semantics.",
            "No raw state or real account identifiers are retained; all account components are synthetic000000000000.",
            "Cooperative replay cancellation is not proof that a real SDK socket stops at a deadline; production implementation must bound actual transport and process lifetime.",
            "A live AWS operator profile and production security review remain later-story gates, not claims of this feasibility exercise.",
        ],
    }
    if args.fixture:
        args.fixture.write_bytes(encoded)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
