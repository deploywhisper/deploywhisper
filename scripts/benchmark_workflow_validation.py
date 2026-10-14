#!/usr/bin/env python3
"""Standalone workflow-v2 measurement; import has no benchmark or file effects."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import time
from typing import Any

import pydantic
import yaml

import infra_automation
from infra_automation.contracts import RegistryContract
from infra_automation.workflow_validation import validate_workflow

CASE = "fifty-step-mixed-and-corpus"
REFERENCE_MEMORY = 8 * 1024**3


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def environment() -> dict[str, Any]:
    """Capture actual allocation, including affinity and cgroup/rlimit ceilings."""
    affinity = (
        sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    )
    controls = {
        name: _read("/sys/fs/cgroup/" + name)
        for name in (
            "cpu.max",
            "cpuset.cpus.effective",
            "memory.max",
            "cpu/cpu.cfs_quota_us",
            "cpu/cpu.cfs_period_us",
            "cpuset/cpuset.cpus",
            "memory/memory.limit_in_bytes",
        )
    }
    cpu_quota = None
    try:
        if controls["cpu.max"] and controls["cpu.max"].split()[0] != "max":
            quota, period = controls["cpu.max"].split()
            cpu_quota = int(quota) / int(period)
        elif (
            controls["cpu/cpu.cfs_quota_us"]
            and int(controls["cpu/cpu.cfs_quota_us"]) > 0
        ):
            cpu_quota = int(controls["cpu/cpu.cfs_quota_us"]) / int(
                controls["cpu/cpu.cfs_period_us"] or "0"
            )
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    cpu_bounds = [
        float(value)
        for value in (len(affinity) if affinity else os.cpu_count(), cpu_quota)
        if value is not None
    ]
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    memory_bounds = [
        value for value in (soft, hard) if value != resource.RLIM_INFINITY and value > 0
    ]
    for key in ("memory.max", "memory/memory.limit_in_bytes"):
        value = controls[key]
        if value and value.isdecimal() and int(value) < 2**60:
            memory_bounds.append(int(value))
    cpu_info = _read("/proc/cpuinfo") or ""
    memory_total = next(
        (
            int(line.split()[1]) * 1024
            for line in (_read("/proc/meminfo") or "").splitlines()
            if line.startswith("MemTotal:")
        ),
        None,
    )
    cpu_model = next(
        (
            line.split(":", 1)[1].strip()
            for line in cpu_info.splitlines()
            if line.startswith(("model name", "Hardware")) and ":" in line
        ),
        platform.processor() or "unreported",
    )
    return {
        "os": platform.system(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_model": cpu_model,
        "logical_cpu_count": os.cpu_count(),
        "affinity_cpus": affinity,
        "effective_cpu_ceiling": min(cpu_bounds) if cpu_bounds else None,
        "memory_ceiling_bytes": min(memory_bounds) if memory_bounds else None,
        "kernel_visible_memory_bytes": memory_total,
        "rlimit_address_space_bytes": {"soft": soft, "hard": hard},
        "cgroup_controls": controls,
        "python": platform.python_version(),
        "pydantic": pydantic.__version__,
        "pyyaml": yaml.__version__,
        "virtualization": "Host/container boundary is reported by the invoking operator; affinity and quotas are recorded, not inferred hardware ownership.",
    }


def source_hashes() -> dict[str, str]:
    package = Path(infra_automation.__file__).parent
    return {
        path.name: digest(path.read_bytes()) for path in sorted(package.glob("*.py"))
    }


def run_benchmark(
    corpus: Path, *, samples: int = 1000, warmup: int = 100
) -> dict[str, Any]:
    if type(samples) is not int or samples < 1 or type(warmup) is not int or warmup < 0:
        raise ValueError("Samples must be positive and warmup nonnegative integers.")
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # All fixture I/O, encoding, registry construction and oracle preparation precede timing.
    corpus_bytes = corpus.read_bytes()
    rows = json.loads(corpus_bytes)
    matching = [row for row in rows if row.get("case") == CASE]
    if len(matching) != 1:
        raise ValueError("Corpus must contain exactly one declared fifty-step case.")
    row = matching[0]
    payload = canonical(row["definition"])
    registry = RegistryContract.model_validate_json(
        json.dumps({"profiles": row["profiles"]})
    )
    expected = validate_workflow(payload, registry_contract=registry)
    definition = expected.definition
    if (
        not expected.valid
        or definition is None
        or expected.canonical_bytes is None
        or len(definition.steps) != 50
    ):
        raise ValueError("Benchmark corpus must validate as a fifty-step workflow.")
    expected_ids = {step.id for step in definition.steps}
    if (
        set(expected.topological_order) != expected_ids
        or len(expected.topological_order) != 50
    ):
        raise ValueError("Benchmark corpus has an invalid traversal result.")
    order = {name: index for index, name in enumerate(expected.topological_order)}
    if any(
        order[parent] >= order[step.id]
        for step in definition.steps
        for parent in step.depends_on
    ):
        raise ValueError("Benchmark traversal violates a prerequisite.")
    if expected.digest != digest(expected.canonical_bytes):
        raise ValueError("Benchmark oracle has inconsistent canonical content.")
    durations: list[float] = []
    failures = {"warmup": 0, "measured": 0}
    for index in range(warmup + samples):
        started = time.perf_counter_ns()
        result = validate_workflow(payload, registry_contract=registry)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        correct = (
            result.valid
            and not result.errors
            and not result.truncated
            and result.canonical_bytes == expected.canonical_bytes
            and result.digest == expected.digest
            and result.canonicalization == "tuple-json-utf8-v1"
            and result.topological_order == expected.topological_order
        )
        phase = "warmup" if index < warmup else "measured"
        failures[phase] += int(not correct)
        if phase == "measured":
            durations.append(elapsed_ms)
    durations.sort()
    percentiles = {
        f"p{percentile}_ms": durations[math.ceil(percentile / 100 * samples) - 1]
        for percentile in (50, 95, 99)
    }
    host = environment()
    source = source_hashes()
    reasons = []
    if host["os"] != "Linux":
        reasons.append("Reference qualification requires Linux.")
    if host["effective_cpu_ceiling"] != 4:
        reasons.append("Reference qualification requires a recorded four-CPU ceiling.")
    if host["memory_ceiling_bytes"] != REFERENCE_MEMORY:
        reasons.append(
            "Reference qualification requires a recorded eight-GiB memory ceiling."
        )
    if (warmup, samples) != (100, 1000):
        reasons.append("Qualification requires exactly 100 warmups and 1000 samples.")
    if any(failures.values()):
        reasons.append("One or more correctness checks failed.")
    if percentiles["p95_ms"] >= 500:
        reasons.append("The p95 latency must be below 500 ms.")
    return {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workflow_version": 2,
        "case": CASE,
        "step_count": 50,
        "warmup": warmup,
        "samples": samples,
        "failures": failures,
        "percentile_method": "nearest rank",
        **percentiles,
        "timed_scope": "validate_workflow only; preloaded bytes and immutable registry; correctness checked after every invocation",
        "corpus_file_digest": digest(corpus_bytes),
        "case_payload_digest": digest(payload),
        "canonical_workflow_digest": expected.digest,
        "canonicalization": expected.canonicalization,
        "harness_digest": digest(Path(__file__).read_bytes()),
        "source_files": source,
        "source_digest": digest(canonical(source)),
        "environment": host,
        "qualified": not reasons,
        "qualification_failures": reasons,
        "qualification_scope": "Standalone structural validator only; no production execution, isolation or mixed-runner qualification.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=100)
    args = parser.parse_args(argv)
    report = run_benchmark(args.corpus, samples=args.samples, warmup=args.warmup)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "qualified",
                    "samples",
                    "failures",
                    "p50_ms",
                    "p95_ms",
                    "p99_ms",
                    "qualification_failures",
                )
            },
            indent=2,
        )
    )
    return int(any(report["failures"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
