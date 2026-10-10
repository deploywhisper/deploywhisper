"""Read-only summary vectors against the externally pinned action runtime."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

path = Path("/private/tmp/16-0-action-runtime-pinned-readonly.py")
expected = "98433dc82dbfd9b4b3d12a5f268d01ca504525ae0bc2c1aed8c7107b293edb0d"
if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
    raise ValueError("Pinned external action runtime bytes required")
spec = importlib.util.spec_from_file_location("pinned_action", path)
action = importlib.util.module_from_spec(spec)
spec.loader.exec_module(action)
base = {
    "data": {
        "persisted_report": {"id": 17, "report_schema_version": "v2"},
        "share_summary": {
            "markdown": "Synthetic advisory only",
            "json_payload": {"report_link": "https://example.invalid/reports/17"},
        },
    }
}
reference = action._success_summary(
    analysis_payload=base, changed_files=[], uploaded_files=[], skipped_files=[]
)
for block in ({"version": 1}, {"version": 99}):
    augmented = json.loads(json.dumps(base))
    augmented["data"]["persisted_report"]["infra_automation_provenance"] = block
    if (
        action._success_summary(
            analysis_payload=augmented,
            changed_files=[],
            uploaded_files=[],
            skipped_files=[],
        )
        != reference
    ):
        raise ValueError("Optional metadata changed existing action summary")
print(
    json.dumps(
        {
            "consumer": "pinned external action _success_summary",
            "cases": 3,
            "passed": True,
            "commit": "3b37ed72bfb2d201030bef873268f2170794b160",
            "full_action_integration": False,
        }
    )
)
