"""Disposable sourced request-cost estimate; no provider request is issued."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

CATALOG_PATH = Path(__file__).with_name("cost-rates.json")


def load_catalog():
    return json.loads(CATALOG_PATH.read_text())


def _rate(value):
    if isinstance(value, bool):
        raise ValueError("invalid provider rate")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid provider rate") from exc
    if not result.is_finite() or result < 0 or not math.isfinite(float(result)):
        raise ValueError("invalid provider rate")
    return result


def _json_amount(value):
    amount = float(value)
    if not math.isfinite(amount):
        raise ValueError("request cost exceeds finite JSON number range")
    return amount


def _scope_supported(call):
    params = call.get("params", {})
    if not isinstance(params, dict):
        return False
    if call["service"] == "sqs":
        queue = params.get("QueueUrl")
        if not isinstance(queue, str):
            return False
        parts = urlsplit(queue)
        return (
            parts.scheme == "https"
            and parts.netloc == "sqs.us-east-1.amazonaws.com"
            and not parts.query
            and not parts.fragment
            and not parts.path.endswith(".fifo")
        )
    if call["service"] == "s3":
        bucket = params.get("Bucket")
        return (
            isinstance(bucket, str)
            and bool(bucket)
            and not bucket.startswith("arn:")
            and not bucket.endswith(("--x-s3", "--ol-s3", "-s3alias", ".mrap"))
        )
    return True


def _estimate(calls, catalog):
    counts = Counter()
    unknown = Counter()
    for call in calls:
        if not isinstance(call, dict) or any(
            not isinstance(call.get(key), str) or not call[key]
            for key in ("service", "operation")
        ):
            raise ValueError("invalid manifest call")
        action = call["service"] + ":" + call["operation"]
        counts[action] += 1
        if action not in catalog["operations"] or not _scope_supported(call):
            unknown[action] += 1
    rows = []
    subtotal = Decimal(0)
    for action, count in sorted(counts.items()):
        item = catalog["operations"].get(action)
        known_count = count - unknown[action]
        price = _rate(item["usd_per_request"]) if item else None
        charge = price * known_count if price is not None else Decimal(0)
        subtotal += charge
        rows.append(
            {
                "action": action,
                "calls": count,
                "priced_calls": known_count,
                "unknown_calls": unknown[action],
                "usd_per_request": _json_amount(price) if price is not None else None,
                "classification": item["classification"] if item else "unknown",
                "source_ids": item["source_ids"] if item else [],
                "known_request_subtotal_usd": _json_amount(charge),
                "estimated_request_usd": None
                if unknown[action]
                else _json_amount(charge),
            }
        )
    return {
        "status": "unknown_rates" if unknown else "complete_estimate",
        "intended_calls": len(calls),
        "priced_calls": len(calls) - sum(unknown.values()),
        "unknown_actions": sorted(unknown),
        "estimated_request_usd": None if unknown else _json_amount(subtotal),
        "known_request_subtotal_usd": _json_amount(subtotal),
        "per_action": rows,
    }


def estimate_cost(calls, *, budget=100, region="us-east-1", catalog=None):
    """Estimate the ordered manifest and its attempt-budget prefix before free tiers."""
    if type(budget) is not int or budget < 0:
        raise ValueError("attempt budget must be a nonnegative integer")
    if not isinstance(calls, list):
        raise ValueError("manifest must be a list")
    catalog = load_catalog() if catalog is None else catalog
    if not isinstance(region, str) or region != catalog["region"]:
        raise ValueError("region has no qualified pricing catalog")
    for item in catalog["operations"].values():
        _rate(item["usd_per_request"])
        if not item.get("source_ids") or any(
            source not in catalog["sources"] for source in item["source_ids"]
        ):
            raise ValueError("provider rate lacks evidence")
    return {
        "region": region,
        "currency": catalog["currency"],
        "observed_on": catalog["observed_on"],
        "estimate_kind": catalog["estimate_kind"],
        "budget": budget,
        "full_manifest": _estimate(calls, catalog),
        "budget_prefix": _estimate(calls[:budget], catalog),
        "assumptions": catalog["scope_assumptions"],
        "exclusions": catalog["exclusions"],
        "actual_provider_calls": 0,
        "actual_provider_charge_usd": 0,
    }
