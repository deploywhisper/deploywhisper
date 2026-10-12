"""Owned synthetic external-provider executable; emits booleans only."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys

json.load(sys.stdin)
result = {"sentinel_absent": str("QUALIFICATION_SECRET" not in os.environ)}
for label, address in (("metadata", "169.254.169.254"), ("egress", "1.1.1.1")):
    try:
        with socket.create_connection((address, 80), timeout=0.25):
            result[label + "_denied"] = "False"
    except OSError:
        result[label + "_denied"] = "True"
result["uid"] = str(os.getuid())
status = Path("/proc/self/status").read_text().splitlines()
fields = dict(line.split(":", 1) for line in status if ":" in line)
result["seccomp_enforced"] = str(fields["Seccomp"].strip() == "2")
result["no_new_privileges"] = str(fields["NoNewPrivs"].strip() == "1")
result["capabilities_dropped"] = str(int(fields["CapEff"].strip(), 16) == 0)
try:
    with Path("/opt/qualification/tofurc").open("ab"):
        result["catalog_immutable"] = "False"
except OSError:
    result["catalog_immutable"] = "True"
if os.environ.get("LOCAL_PROBE") == "1":
    try:
        with socket.create_connection(("probe-sink", 8000), timeout=1):
            result["approved_local_allowed"] = "True"
    except OSError:
        result["approved_local_allowed"] = "False"
print(json.dumps(result))
